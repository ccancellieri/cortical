"""Zero-cloud-token ROI analytics (mtime+size cached remote transcripts + local `agent_runs`)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Optional

from ..config import DEFAULT_TELEMETRY_DB, ensure_telemetry_schema

CLOUD_RATES_USD_PER_1M = {
    "cloud_standard": {"input": 3.0, "cache_read": 0.30, "output": 15.0},
    "cloud_economy": {"input": 0.50, "cache_read": 0.05, "output": 2.0},
}


def _estimate_cost(in_tok: int, cache_tok: int, out_tok: int, preset: str = "cloud_standard") -> float:
    rates = CLOUD_RATES_USD_PER_1M.get(preset) or CLOUD_RATES_USD_PER_1M["cloud_standard"]
    return round((in_tok * rates["input"] + cache_tok * rates["cache_read"] + out_tok * rates["output"]) / 1_000_000.0, 4)


def _default_brain_dir() -> Path:
    return Path.home() / ".gemini" / "antigravity" / "brain"


def collect_remote_transcript_usage(
    brain_dir: Optional[Path] = None,
    conversation_id: Optional[str] = None,
    cache_path: Optional[Path] = None,
) -> dict[str, Any]:
    """Scans local Antigravity transcripts using `(path, mtime_ns, size)` caching to avoid reparsing unchanged logs."""
    root = Path(brain_dir) if brain_dir is not None else _default_brain_dir()
    if not root.is_dir():
        return {"chat_count": 0, "input_tokens": 0, "cache_read_tokens": 0, "output_tokens": 0, "active_tokens": 0, "chats": []}

    c_file = Path(cache_path or ".cortical_data/transcript_cache.json")
    try:
        disk_cache: dict[str, Any] = json.loads(c_file.read_text(encoding="utf-8")) if c_file.is_file() else {}
    except Exception:  # noqa: BLE001
        disk_cache = {}

    pattern = f"{conversation_id}*/.system_generated/logs/transcript.jsonl" if conversation_id else "*/.system_generated/logs/transcript.jsonl"
    chats: list[dict[str, Any]] = []
    cache_dirty = False
    for fp in sorted(root.glob(pattern)):
        try:
            st = fp.stat()
            sig = [int(st.st_mtime_ns), int(st.st_size)]
            key = str(fp)
            if disk_cache.get(key, {}).get("sig") == sig:
                parsed = disk_cache[key]["data"]
            else:
                in_t = cache_t = out_t = lt_in = lt_cache = lt_out = lt_steps = lt_tools = 0
                for raw_line in fp.read_text(encoding="utf-8", errors="replace").splitlines():
                    if not raw_line.strip():
                        continue
                    try:
                        obj = json.loads(raw_line)
                    except json.JSONDecodeError:
                        continue
                    if obj.get("type") == "USER_INPUT":
                        lt_in = lt_cache = lt_out = lt_steps = lt_tools = 0
                        continue
                    usage = obj.get("usage")
                    if isinstance(usage, dict):
                        i = int(usage.get("input_tokens") or 0)
                        c = int(usage.get("cache_read_tokens") or 0)
                        o = int(usage.get("output_tokens") or 0)
                        in_t += i
                        cache_t += c
                        out_t += o
                        lt_in += i
                        lt_cache += c
                        lt_out += o
                    if obj.get("type") == "PLANNER_RESPONSE":
                        lt_steps += 1
                        lt_tools += len(obj.get("tool_calls") or [])
                parsed = {
                    "conversation_id": fp.parents[2].name,
                    "input_tokens": in_t,
                    "cache_read_tokens": cache_t,
                    "output_tokens": out_t,
                    "active_tokens": in_t + out_t,
                    "last_turn": {
                        "input_tokens": lt_in,
                        "cache_read_tokens": lt_cache,
                        "output_tokens": lt_out,
                        "active_tokens": lt_in + lt_out,
                        "planner_steps": lt_steps,
                        "tool_calls": lt_tools,
                    },
                }
                disk_cache[key] = {"sig": sig, "data": parsed}
                cache_dirty = True
            chats.append(parsed)
        except OSError:
            continue

    if cache_dirty and brain_dir is None:
        try:
            c_file.parent.mkdir(parents=True, exist_ok=True)
            c_file.write_text(json.dumps(disk_cache), encoding="utf-8")
        except OSError:
            pass

    tot_in = sum(c["input_tokens"] for c in chats)
    tot_cache = sum(c["cache_read_tokens"] for c in chats)
    tot_out = sum(c["output_tokens"] for c in chats)
    return {
        "chat_count": len(chats),
        "input_tokens": tot_in,
        "cache_read_tokens": tot_cache,
        "output_tokens": tot_out,
        "active_tokens": tot_in + tot_out,
        "chats": chats,
    }


def collect_local_runs(db_path: Path | str | None = None, window_sec: float = 1800.0) -> dict[str, Any]:
    """Aggregates real local LLM `agent_runs` globally and for the active turn window."""
    target = Path(db_path or os.environ.get("CORTICAL_TELEMETRY_DB") or DEFAULT_TELEMETRY_DB)
    if not target.is_file():
        return {"global": {"run_count": 0, "total_tokens": 0, "elapsed_sec": 0.0, "models": []}, "active_window": {"run_count": 0, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "elapsed_sec": 0.0, "models": []}}

    now = time.time()
    with ensure_telemetry_schema(target) as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM agent_runs ORDER BY finished_at DESC LIMIT 1000").fetchall()]

    real_rows = [r for r in rows if not str(r.get("provider") or "").lower().startswith("mock")]
    recent = [r for r in real_rows if (now - float(r.get("finished_at") or 0.0)) <= window_sec]

    def _agg(items: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "run_count": len(items),
            "input_tokens": sum(int(r.get("input_tokens") or 0) for r in items),
            "output_tokens": sum(int(r.get("output_tokens") or 0) for r in items),
            "total_tokens": sum(int(r.get("total_tokens") or 0) for r in items),
            "elapsed_sec": round(sum(float(r.get("elapsed_sec") or 0.0) for r in items), 2),
            "models": list(dict.fromkeys(str(r.get("model") or "") for r in items if r.get("model"))),
        }

    return {"global": _agg(real_rows), "active_window": _agg(recent)}


def build_roi_report(
    *,
    db_path: Path | str | None = None,
    brain_dir: Optional[Path] = None,
    conversation_id: Optional[str] = None,
    preset: str = "cloud_standard",
) -> dict[str, Any]:
    """Builds unified local/remote/ROI metrics with zero remote tokens."""
    loc = collect_local_runs(db_path=db_path)
    rem = collect_remote_transcript_usage(brain_dir=brain_dir, conversation_id=conversation_id)
    target_chat = (rem.get("chats") or [{}])[0]
    lt = target_chat.get("last_turn") or {}
    aw = loc["active_window"]

    t_rem_act = int(lt.get("active_tokens") or 0)
    t_loc_tot = int(aw.get("total_tokens") or 0)
    offload_pct = round((t_loc_tot / max(1, t_loc_tot + t_rem_act)) * 100.0, 2)
    return {
        "generated_at": time.time(),
        "local": loc,
        "remote": rem,
        "current_turn": {
            "remote": {**lt, "estimated_cost_usd": _estimate_cost(int(lt.get("input_tokens") or 0), int(lt.get("cache_read_tokens") or 0), int(lt.get("output_tokens") or 0), preset)},
            "local": {**aw, "usd_saved_est": _estimate_cost(int(aw["input_tokens"]), 0, int(aw["output_tokens"]), preset)},
            "offload_share_pct": offload_pct,
        },
    }


def format_roi_markdown(report: dict[str, Any]) -> str:
    """Formats a compact per-turn Markdown summary."""
    ct = report.get("current_turn") or {}
    r = ct.get("remote") or {}
    l = ct.get("local") or {}
    models = ", ".join(l.get("models") or []) or "none"
    return "\n".join([
        "### Cortical Token & Offload Report (0 Cloud Tokens Used)",
        "",
        "| Scope | Tokens (In / Out / Active) | Execution | Cost / Saved |",
        "| --- | --- | --- | --- |",
        f"| **Remote Cloud (Turn)** | {r.get('input_tokens', 0):,} in · {r.get('output_tokens', 0):,} out · {r.get('active_tokens', 0):,} act ({r.get('cache_read_tokens', 0):,} cache) | {r.get('planner_steps', 0)} steps · {r.get('tool_calls', 0)} tools | ~${r.get('estimated_cost_usd', 0.0):.2f} |",
        f"| **Cortical Local (Window)** | {l.get('input_tokens', 0):,} in · {l.get('output_tokens', 0):,} out · {l.get('total_tokens', 0):,} tot | {l.get('run_count', 0)} runs · {l.get('elapsed_sec', 0.0):.1f}s ({models}) | $0 · **Saved ~${l.get('usd_saved_est', 0.0):.2f}** ({ct.get('offload_share_pct', 0.0):.1f}% offload) |",
    ])
