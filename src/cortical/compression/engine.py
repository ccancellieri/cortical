"""Multi-format deterministic compressor (`TOON` / compact JSON / YAML / CSV / logs) & context budget sizing."""

from __future__ import annotations

import json
import re
from typing import Any

from ..hardware.context_window import estimate_tokens
from .toon import decode_toon, encode_toon

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def _compress_logs_or_text(text: str) -> tuple[str, str]:
    cleaned = _ANSI_RE.sub("", text)
    lines = [ln.rstrip() for ln in cleaned.splitlines()]
    out: list[str] = []
    prev: str | None = None
    repeat_cnt = 0
    for ln in lines:
        norm = re.sub(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?\s*", "", ln)
        if not ln.strip():
            continue
        if prev is not None and norm == prev:
            repeat_cnt += 1
            continue
        if repeat_cnt > 0:
            out.append(f"  [repeated x{repeat_cnt}]")
            repeat_cnt = 0
        out.append(ln)
        prev = norm
    if repeat_cnt > 0:
        out.append(f"  [repeated x{repeat_cnt}]")
    return ("\n".join(out), "log_compacted")


def compress_structured(
    text: str,
    *,
    fmt: str = "auto",
    min_saving_pct: float = 10.0,
) -> dict[str, Any]:
    """Deterministically compresses structured payloads (JSON->TOON with >=10% guard, XML/YAML/logs)."""
    raw = str(text or "")
    raw_tok = estimate_tokens(raw)
    eff_fmt = fmt.lower().strip()

    if eff_fmt in {"auto", "json"}:
        s = raw.strip()
        if (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]")):
            try:
                parsed = json.loads(s)
                compact = json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
                toon_txt = encode_toon(parsed)
                # Guard: verify exact lossless round-trip AND >= min_saving_pct vs compact JSON
                roundtrip_ok = decode_toon(toon_txt) == parsed
                comp_tok = estimate_tokens(compact)
                toon_tok = estimate_tokens(toon_txt)
                saving_vs_compact = ((comp_tok - toon_tok) / max(1, comp_tok)) * 100.0
                if roundtrip_ok and saving_vs_compact >= min_saving_pct:
                    chosen, used_fmt = toon_txt, "toon"
                else:
                    chosen, used_fmt = compact, "compact_json"
                out_tok = estimate_tokens(chosen)
                return {
                    "compressed": chosen,
                    "format_used": used_fmt,
                    "lossless": True,
                    "raw_tokens_est": raw_tok,
                    "compressed_tokens_est": out_tok,
                    "saving_pct": round(max(0.0, ((raw_tok - out_tok) / max(1, raw_tok)) * 100.0), 2),
                }
            except Exception:  # noqa: BLE001
                if eff_fmt == "json":
                    pass

    if eff_fmt in {"auto", "xml", "yaml"} and (raw.lstrip().startswith("<") or eff_fmt == "xml"):
        compact_xml = re.sub(r">\s+<", "><", re.sub(r"<!--.*?-->", "", raw, flags=re.S)).strip()
        out_tok = estimate_tokens(compact_xml)
        return {
            "compressed": compact_xml,
            "format_used": "compact_xml",
            "lossless": True,
            "raw_tokens_est": raw_tok,
            "compressed_tokens_est": out_tok,
            "saving_pct": round(max(0.0, ((raw_tok - out_tok) / max(1, raw_tok)) * 100.0), 2),
        }

    comp_txt, used_fmt = _compress_logs_or_text(raw)
    out_tok = estimate_tokens(comp_txt)
    return {
        "compressed": comp_txt,
        "format_used": used_fmt,
        "lossless": False,
        "raw_tokens_est": raw_tok,
        "compressed_tokens_est": out_tok,
        "saving_pct": round(max(0.0, ((raw_tok - out_tok) / max(1, raw_tok)) * 100.0), 2),
    }


def fit_to_token_budget(
    blocks: list[dict[str, Any]],
    num_ctx: int,
    max_share: float = 0.15,
) -> dict[str, Any]:
    """Auto-sizes and compresses memory/context blocks to stay <= `max_share` of effective `num_ctx`."""
    budget = max(256, int(max(4096, num_ctx) * max(0.02, min(0.5, max_share))))
    ordered = sorted(blocks, key=lambda b: int(b.get("priority") or 0), reverse=True)
    selected: list[dict[str, Any]] = []
    used = 0
    for b in ordered:
        content = str(b.get("content") or "")
        comp = compress_structured(content)
        text = comp["compressed"]
        tok = comp["compressed_tokens_est"]
        if used + tok <= budget:
            selected.append({**b, "content": text, "tokens_est": tok, "format_used": comp["format_used"]})
            used += tok
        elif used < budget:
            rem_chars = max(80, (budget - used) * 4)
            trimmed = text[:rem_chars].rsplit("\n", 1)[0] if "\n" in text[:rem_chars] else text[:rem_chars]
            t_tok = estimate_tokens(trimmed)
            if trimmed:
                selected.append({**b, "content": trimmed + "\n...", "tokens_est": t_tok, "format_used": comp["format_used"], "truncated": True})
                used += t_tok
            break
        else:
            break
    return {
        "budget_tokens": budget,
        "used_tokens": used,
        "blocks": selected,
        "markdown": "\n\n".join(
            f"### {b.get('title', b.get('alias', 'context'))}\n{b['content']}" for b in selected
        ),
    }
