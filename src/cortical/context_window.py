"""Context window budgeting, multi-message chunking, and LLM paragraph summarization.

Prevents brutal character truncation by splitting long context along paragraph
boundaries, optionally summarizing older paragraphs via the local LLM, and
serializing chunks into multiple chat messages while tracking token occupancy.
"""

from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Optional

DEFAULT_MAX_CONTEXT_WINDOW = 200000

_MODEL_METADATA_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_MODEL_CONTEXT_PROVIDERS: list[Callable[[str], Optional[dict[str, Any]]]] = []


def get_configured_max_context_window(max_ctx: Optional[int] = None) -> int:
    """Returns the configurable global context cap (default 200k tokens)."""
    raw = max_ctx if max_ctx is not None else os.environ.get("CORTICAL_MAX_CONTEXT_WINDOW", DEFAULT_MAX_CONTEXT_WINDOW)
    try:
        val = int(raw)
    except (TypeError, ValueError):
        val = DEFAULT_MAX_CONTEXT_WINDOW
    return max(4096, min(262144, val))


def register_model_context_provider(provider_fn: Callable[[str], Optional[dict[str, Any]]]) -> None:
    """Registers a pluggable metadata resolver `(model_id) -> {context_length, parameter_size, ...}`."""
    if provider_fn not in _MODEL_CONTEXT_PROVIDERS:
        _MODEL_CONTEXT_PROVIDERS.append(provider_fn)


def discover_active_ollama_model(
    base_url: Optional[str] = None,
    timeout: float = 0.8,
) -> Optional[str]:
    """Auto-discovers the currently loaded (`/api/ps`) or first available (`/api/tags`) Ollama model."""
    root = (base_url or os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434").strip().rstrip("/")
    if root.endswith("/v1"):
        root = root[:-3]
    for ep in ("/api/ps", "/api/tags"):
        try:
            req = urllib.request.Request(f"{root}{ep}", method="GET")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            models = data.get("models") or []
            if models:
                name = str(models[0].get("name") or models[0].get("model") or "").strip()
                if name:
                    return name
        except Exception:  # noqa: BLE001
            continue
    return None


def inspect_ollama_model_metadata(
    model_id: str,
    base_url: Optional[str] = None,
    timeout: float = 1.0,
    cache_ttl_sec: float = 60.0,
) -> dict[str, Any]:
    """Queries Ollama `/api/show` to auto-discover native `context_length` and `parameter_size`."""
    mid = str(model_id or "").strip()
    if not mid:
        return {}
    now = time.time()
    cached = _MODEL_METADATA_CACHE.get(mid)
    if cached and (now - cached[0]) < cache_ttl_sec:
        return dict(cached[1])

    for prov in _MODEL_CONTEXT_PROVIDERS:
        try:
            res = prov(mid)
            if isinstance(res, dict) and res:
                _MODEL_METADATA_CACHE[mid] = (now, res)
                return dict(res)
        except Exception:  # noqa: BLE001
            continue

    root = (base_url or os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434").strip().rstrip("/")
    if root.endswith("/v1"):
        root = root[:-3]
    meta: dict[str, Any] = {}
    try:
        req = urllib.request.Request(
            f"{root}/api/show",
            data=json.dumps({"model": mid}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        details = data.get("details") or {}
        if details.get("parameter_size"):
            meta["parameter_size"] = str(details["parameter_size"])
        model_info = data.get("model_info") or {}
        for k, v in model_info.items():
            if str(k).endswith(".context_length") and isinstance(v, (int, float)) and int(v) > 0:
                meta["context_length"] = int(v)
                break
        params_txt = str(data.get("parameters") or "")
        m_ctx = re.search(r"num_ctx\s+(\d+)", params_txt)
        if m_ctx and "context_length" not in meta:
            meta["context_length"] = int(m_ctx.group(1))
    except Exception:  # noqa: BLE001
        pass
    _MODEL_METADATA_CACHE[mid] = (now, meta)
    return meta


DEFAULT_MODEL_CONTEXT_WINDOWS: dict[str, int] = {
    "qwen3.5:9b": 131072,
    "qwen3.5:9b-q3_k_xl": 131072,
    "hf.co/unsloth/Qwen3.5-9B-GGUF:UD-Q3_K_XL": 131072,
    "qwen3.5:14b": 131072,
    "qwen3.5:4b": 131072,
    "gemma3:12b": 131072,
    "devstral-small-2": 65536,
    "qwen3.8:27b-iq2_xxs": 32768,
    "hf.co/unsloth/Qwen3.8-27B-GGUF:UD-IQ2_XXS": 32768,
    "qwen3.8:27b-iq2_xs": 32768,
    "qwen3.8:27b": 32768,
    "qwen3:8b": 32768,
    "qwen2.5:1.5b": 32768,
}


def estimate_tokens(text: str) -> int:
    """Estimates token count (~4 chars/token) without external tokenizer dependencies."""
    s = str(text or "")
    if not s.strip():
        return 0
    return max(1, (len(s) + 3) // 4)


def clamp_context_window(
    value: Any,
    fallback: int = 32768,
    max_ctx: Optional[int] = None,
) -> int:
    """Clamps a configured context window to `[2048, max_ctx]` (default cap 200k)."""
    cap = get_configured_max_context_window(max_ctx)
    try:
        num = int(value)
    except (TypeError, ValueError):
        return min(fallback, cap)
    return max(2048, min(cap, num))


def get_model_context_window(
    model_id: str = "",
    configured_windows: Optional[dict[str, Any]] = None,
    fallback: int = 32768,
    max_ctx: Optional[int] = None,
    auto_discover: bool = True,
) -> int:
    """Resolves context window for `model_id` via config, pluggable `/api/show`, or defaults (<= 200k)."""
    cap = get_configured_max_context_window(max_ctx)
    mid = str(model_id or "").strip()
    if not mid and auto_discover:
        mid = discover_active_ollama_model() or ""
    if configured_windows and mid in configured_windows:
        return clamp_context_window(configured_windows[mid], fallback=fallback, max_ctx=cap)
    for prov in _MODEL_CONTEXT_PROVIDERS:
        try:
            res = prov(mid)
            if isinstance(res, dict) and res.get("context_length"):
                return clamp_context_window(res["context_length"], fallback=fallback, max_ctx=cap)
        except Exception:  # noqa: BLE001
            continue
    if mid in DEFAULT_MODEL_CONTEXT_WINDOWS:
        return min(cap, DEFAULT_MODEL_CONTEXT_WINDOWS[mid])
    if auto_discover and mid:
        meta = inspect_ollama_model_metadata(mid)
        if meta.get("context_length"):
            return clamp_context_window(meta["context_length"], fallback=fallback, max_ctx=cap)
    low = mid.lower()
    if "qwen3.5" in low:
        return min(cap, 131072)
    if "qwen3" in low or "qwen2.5" in low or "llama3" in low or "gemma" in low:
        return min(cap, 32768)
    return min(cap, fallback)


def get_system_memory_snapshot() -> dict[str, float]:
    """Returns real system RAM total and reclaimable/available GB without external dependencies."""
    total_gb = 16.0
    avail_gb = 6.0
    try:
        sys_name = platform.system()
        if sys_name == "Darwin":
            mem_bytes = int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], timeout=1.0).decode().strip())
            total_gb = round(mem_bytes / (1024 ** 3), 2)
            vm_out = subprocess.check_output(["vm_stat"], timeout=1.0).decode()
            ps_m = re.search(r"page size of (\d+) bytes", vm_out)
            page_bytes = int(ps_m.group(1)) if ps_m else 16384
            counts = dict(re.findall(r"Pages (free|inactive|speculative|purgeable):\s+(\d+)", vm_out))
            avail_pages = sum(int(counts.get(k, 0)) for k in ("free", "inactive", "purgeable"))
            avail_gb = round((avail_pages * page_bytes) / (1024 ** 3), 2)
        elif sys_name == "Linux" and os.path.exists("/proc/meminfo"):
            txt = open("/proc/meminfo", encoding="utf-8").read()
            m_tot = re.search(r"MemTotal:\s+(\d+)\s+kB", txt)
            m_avail = re.search(r"MemAvailable:\s+(\d+)\s+kB", txt)
            if m_tot:
                total_gb = round(int(m_tot.group(1)) / (1024 ** 2), 2)
            if m_avail:
                avail_gb = round(int(m_avail.group(1)) / (1024 ** 2), 2)
    except Exception:  # noqa: BLE001
        pass
    return {"ram_total_gb": total_gb, "ram_available_gb": avail_gb}


def compute_dynamic_num_ctx(
    base_ctx: int = 32768,
    model_id: str = "",
    *,
    ram_available_gb: Optional[float] = None,
    kv_quantized: Optional[bool] = None,
    max_ctx: Optional[int] = None,
    model_metadata: Optional[dict[str, Any]] = None,
) -> int:
    """Auto-scales `num_ctx` from active/discovered model metadata & live RAM headroom (cap 200k)."""
    cap = get_configured_max_context_window(max_ctx)
    eff_model = str(model_id or "").strip() or (discover_active_ollama_model() or "qwen3:8b")
    meta = dict(model_metadata) if model_metadata is not None else inspect_ollama_model_metadata(eff_model)
    avail = float(ram_available_gb if ram_available_gb is not None else get_system_memory_snapshot()["ram_available_gb"])
    if kv_quantized is None:
        kv_quantized = os.environ.get("OLLAMA_KV_CACHE_TYPE", "").strip().lower() in {"q8_0", "q4_0"}

    low = eff_model.lower()
    param_txt = str(meta.get("parameter_size") or "").lower()
    param_b = 0.0
    m_b = re.search(r"(\d+(?:\.\d+)?)\s*b", param_txt or low)
    if m_b:
        param_b = float(m_b.group(1))

    discovered_ctx = int(meta.get("context_length") or 0)

    # Rough KV cost (GB per 16k tokens FP16 vs quantized q8_0/q4_0)
    if (0 < param_b <= 4.5) or "1.5b" in low or "1.2b" in low or "4b" in low:
        kv_gb_per_16k = 0.25 if kv_quantized else 0.5
        native_cap = discovered_ctx or 131072
    elif "qwen3.5" in low:
        # Hybrid Gated DeltaNet architecture compresses KV overhead significantly
        kv_gb_per_16k = 0.45 if kv_quantized else 0.9
        native_cap = discovered_ctx or 131072
    elif "gemma3" in low or (10.0 <= param_b <= 13.0):
        kv_gb_per_16k = 0.7 if kv_quantized else 1.4
        native_cap = discovered_ctx or 131072
    elif param_b >= 24.0 or "27b" in low or "32b" in low or "devstral" in low:
        kv_gb_per_16k = 1.6 if kv_quantized else 3.2
        native_cap = discovered_ctx or 32768
    elif param_b >= 13.5 or "14b" in low:
        kv_gb_per_16k = 1.1 if kv_quantized else 2.2
        native_cap = discovered_ctx or 40960
    else:
        # 7B / 8B / 9B sweet spot
        kv_gb_per_16k = 0.9 if kv_quantized else 1.8
        native_cap = discovered_ctx or 40960

    native_cap = min(cap, max(4096, native_cap))
    os_reserve_gb = 2.0
    headroom = max(0.3, avail - os_reserve_gb)
    max_safe_ctx = int((headroom / max(0.2, kv_gb_per_16k)) * 16384)
    # Round to clean 4096-token steps inside [4096, native_cap]
    step = 4096
    safe_stepped = max(4096, min(native_cap, (max_safe_ctx // step) * step))
    target = clamp_context_window(base_ctx, fallback=32768, max_ctx=cap)
    if target > safe_stepped:
        return safe_stepped
    # If machine has abundant spare RAM (> 2x KV budget), allow scaling up toward min(native_cap, target + 8192)
    if headroom >= kv_gb_per_16k * 2.5 and target < safe_stepped:
        return min(safe_stepped, max(target, min(native_cap, target + 8192)))
    return max(4096, min(target, safe_stepped))


def split_into_paragraphs(text: str, max_para_tokens: int = 900) -> list[str]:
    """Splits text along paragraph (or sentence) boundaries without mid-word truncation."""
    raw = str(text or "").strip()
    if not raw:
        return []
    blocks = [b.strip() for b in re.split(r"\n\s*\n+", raw) if b.strip()]
    result: list[str] = []
    max_chars = max(200, max_para_tokens * 4)
    for blk in blocks:
        if len(blk) <= max_chars:
            result.append(blk)
            continue
        # Split oversized block on line or sentence boundaries
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", blk) if s.strip()]
        cur = ""
        for sent in sentences:
            if cur and len(cur) + len(sent) + 1 > max_chars:
                result.append(cur)
                cur = sent
            else:
                cur = f"{cur} {sent}".strip() if cur else sent
        if cur:
            result.append(cur)
    return result


def _summarize_paragraph_group(
    paragraphs: list[str],
    target_tokens: int,
    summarize_fn: Optional[Callable[[str, int], Optional[str]]] = None,
) -> list[str]:
    """Summarizes older paragraphs via local LLM or clean sentence-level compaction."""
    joined = "\n\n".join(paragraphs)
    if summarize_fn is not None:
        try:
            prompt = (
                f"Riassumi fedelmente i seguenti paragrafi mantenendo tutti i fatti tecnici, "
                f"percorsi file, nomi e decisioni, entro circa {target_tokens} token, senza troncare frasi:\n\n{joined}"
            )
            summary = summarize_fn(prompt, target_tokens)
            if summary and summary.strip():
                return split_into_paragraphs(summary.strip(), max_para_tokens=max(300, target_tokens))
        except Exception:  # noqa: BLE001
            pass

    # Deterministic fallback: keep leading + key sentences of each paragraph intact
    compacted: list[str] = []
    budget_chars = max(320, target_tokens * 4)
    used_chars = 0
    for p in paragraphs:
        sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", p) if s.strip()]
        if not sents:
            continue
        pick = sents[0]
        if len(sents) > 1 and len(pick) + len(sents[-1]) + 1 <= 360:
            pick = f"{pick} ... {sents[-1]}"
        if used_chars + len(pick) + 2 > budget_chars and compacted:
            break
        compacted.append(pick)
        used_chars += len(pick) + 2
    return compacted


def fit_context_to_window(
    *,
    system_prompt: str,
    user_prompt: str,
    extra_context: str = "",
    history_messages: Optional[list[dict[str, str]]] = None,
    context_window_tokens: int = 32768,
    reserve_output_tokens: int = 1500,
    summarize_fn: Optional[Callable[[str, int], Optional[str]]] = None,
    chunk_tokens: int = 1200,
    strategy_override: str = "auto",
) -> dict[str, Any]:
    """Fits context + history into the model window via multi-message chunking and LLM summarization.

    Never performs brutal mid-string truncation. Returns ready-to-send `messages`,
    `fitted_context` (for single-prompt runners), and `telemetry` (window & occupancy).
    """
    win = clamp_context_window(context_window_tokens)
    base_tokens = estimate_tokens(system_prompt) + estimate_tokens(user_prompt)
    avail_tokens = max(512, win - base_tokens - max(256, reserve_output_tokens))

    hist_list = [
        {"role": str(m["role"]), "content": str(m["content"])}
        for m in (history_messages or [])
        if m.get("role") in {"user", "assistant"} and str(m.get("content") or "").strip()
    ]
    paragraphs = split_into_paragraphs(extra_context, max_para_tokens=max(400, chunk_tokens // 2))

    ctx_tokens = sum(estimate_tokens(p) for p in paragraphs)
    hist_tokens = sum(estimate_tokens(m["content"]) for m in hist_list)
    strat_req = (strategy_override or "auto").strip().lower()
    strategy = "direct"

    # 1. If combined context + history exceeds budget (or summarize forced), summarize older paragraphs first
    if paragraphs and (strat_req == "summarize" or (strat_req != "direct" and ctx_tokens + hist_tokens > avail_tokens)):
        strategy = "llm_paragraph_summary" if summarize_fn is not None else "paragraph_compaction"
        # Reserve up to 35% of available budget for recent chat history
        hist_budget = min(hist_tokens, int(avail_tokens * 0.35))
        kept_hist: list[dict[str, str]] = []
        running_h = 0
        for m in reversed(hist_list):
            t = estimate_tokens(m["content"])
            if running_h + t <= hist_budget or not kept_hist:
                kept_hist.append(m)
                running_h += t
        hist_list = list(reversed(kept_hist))
        ctx_budget = max(320, avail_tokens - running_h)

        if ctx_tokens > ctx_budget:
            # Keep newest/tail paragraphs intact if possible, summarize earlier paragraphs
            tail_paras: list[str] = []
            tail_tok = 0
            tail_limit = int(ctx_budget * 0.55)
            idx = len(paragraphs) - 1
            while idx >= 0:
                pt = estimate_tokens(paragraphs[idx])
                if tail_tok + pt <= tail_limit or not tail_paras:
                    tail_paras.append(paragraphs[idx])
                    tail_tok += pt
                    idx -= 1
                else:
                    break
            tail_paras.reverse()
            head_paras = paragraphs[: idx + 1]
            if head_paras:
                head_budget = max(160, ctx_budget - tail_tok)
                summarized_head = _summarize_paragraph_group(head_paras, head_budget, summarize_fn=summarize_fn)
                paragraphs = summarized_head + tail_paras
            else:
                paragraphs = tail_paras

    # 2. Serialize paragraphs into multi-message chunks (so large context is split cleanly across messages)
    chunks: list[str] = []
    cur_chunk: list[str] = []
    cur_tok = 0
    per_chunk_limit = max(400, min(chunk_tokens, avail_tokens))
    for p in paragraphs:
        pt = estimate_tokens(p)
        if cur_chunk and cur_tok + pt > per_chunk_limit:
            chunks.append("\n\n".join(cur_chunk))
            cur_chunk = [p]
            cur_tok = pt
        else:
            cur_chunk.append(p)
            cur_tok += pt
    if cur_chunk:
        chunks.append("\n\n".join(cur_chunk))

    if len(chunks) > 1 and strategy == "direct":
        strategy = "multi_message"

    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    total_chunks = len(chunks)
    for i, ch in enumerate(chunks, start=1):
        prefix = f"[Contesto {i}/{total_chunks}]\n" if total_chunks > 1 else "[Contesto]\n"
        messages.append({"role": "user", "content": prefix + ch})
    messages.extend(hist_list)
    messages.append({"role": "user", "content": user_prompt})

    used_tokens = sum(estimate_tokens(m["content"]) for m in messages)
    occupancy_pct = round(min(100.0, (used_tokens / float(win)) * 100.0), 1)
    return {
        "messages": messages,
        "fitted_context": "\n\n".join(chunks),
        "telemetry": {
            "context_window_tokens": win,
            "used_tokens": used_tokens,
            "remaining_tokens": max(0, win - used_tokens),
            "occupancy_pct": occupancy_pct,
            "strategy": strategy,
            "chunks_count": total_chunks,
        },
    }
