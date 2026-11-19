"""Pluggable model context discovery & RAM/VRAM-aware dynamic `num_ctx` scaling (Python stdlib only)."""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Optional

DEFAULT_MAX_CONTEXT_WINDOW = 200000

DEFAULT_MODEL_CONTEXT_WINDOWS: dict[str, int] = {
    "qwen2.5:1.5b": 32768,
    "qwen2.5:3b": 32768,
    "qwen3:8b": 32768,
    "qwen3.5:9b": 131072,
    "qwen3.5:9b-q3_k_xl": 131072,
    "qwen3.8:27b-iq2_xxs": 32768,
    "qwen3.8:27b-q4_xxs": 32768,
    "qwen2.5-coder:32b": 32768,
}

ModelContextProvider = Callable[[str], Optional[dict[str, Any]]]
_MODEL_CONTEXT_PROVIDERS: list[ModelContextProvider] = []
_MODEL_METADATA_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def get_configured_max_context_window(max_ctx: Optional[int] = None) -> int:
    """Returns configured max context ceiling (`CORTICAL_MAX_CONTEXT_WINDOW` or default 200k)."""
    if max_ctx is not None:
        return max(2048, int(max_ctx))
    raw = os.environ.get("CORTICAL_MAX_CONTEXT_WINDOW", "").strip()
    if raw.isdigit():
        return max(2048, int(raw))
    return DEFAULT_MAX_CONTEXT_WINDOW


def register_model_context_provider(provider: ModelContextProvider) -> None:
    """Registers a custom `(model_id) -> {'context_length': int, 'parameter_size': str}` metadata provider."""
    if provider not in _MODEL_CONTEXT_PROVIDERS:
        _MODEL_CONTEXT_PROVIDERS.append(provider)


def discover_active_ollama_model(base_url: Optional[str] = None, timeout: float = 0.8) -> Optional[str]:
    """Auto-discovers the active (`/api/ps`) or first local (`/api/tags`) Ollama model."""
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
    """Queries registered providers and Ollama `/api/show` for native `context_length` and parameter size."""
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
        m_ctx = re.search(r"num_ctx\s+(\d+)", str(data.get("parameters") or ""))
        if m_ctx and "context_length" not in meta:
            meta["context_length"] = int(m_ctx.group(1))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        pass
    _MODEL_METADATA_CACHE[mid] = (now, meta)
    return meta


def get_model_context_window(
    model_id: str,
    max_ctx: Optional[int] = None,
    auto_discover: bool = True,
) -> int:
    """Returns effective native context window capped at `max_ctx` (default 200k)."""
    cap = get_configured_max_context_window(max_ctx)
    mid = str(model_id or "").strip().lower()
    if auto_discover:
        meta = inspect_ollama_model_metadata(model_id)
        if int(meta.get("context_length") or 0) > 0:
            return min(cap, int(meta["context_length"]))
    if mid in DEFAULT_MODEL_CONTEXT_WINDOWS:
        return min(cap, DEFAULT_MODEL_CONTEXT_WINDOWS[mid])
    for known, win in DEFAULT_MODEL_CONTEXT_WINDOWS.items():
        if known.split(":")[0] in mid:
            return min(cap, win)
    return min(cap, 32768)


def _infer_model_footprint_gb(model_id: str, model_ram_gb: Optional[float] = None) -> float:
    if model_ram_gb is not None and model_ram_gb > 0:
        return float(model_ram_gb)
    low = str(model_id or "").lower()
    if "27b" in low and ("q4_xxs" in low or "4bit" in low or "4-bit" in low):
        return 8.1
    if "27b" in low and ("iq2_xxs" in low or "xxs" in low):
        return 7.2
    if "32b" in low or "27b" in low:
        return 16.0 if "32b" in low else 12.0
    if "9b" in low and "q3" in low:
        return 5.1
    if "8b" in low or "9b" in low:
        return 5.2
    if "3b" in low:
        return 2.0
    if "1.5b" in low or "2b" in low:
        return 1.2
    return 5.0


def compute_dynamic_num_ctx(
    base_ctx: int = 32768,
    model_id: str = "",
    *,
    ram_available_gb: Optional[float] = None,
    vram_gb: Optional[float] = None,
    unified_memory: bool = True,
    model_ram_gb: Optional[float] = None,
    max_ctx: Optional[int] = None,
) -> int:
    """Scales `num_ctx` cleanly within RAM/VRAM bounds so 4 GB VRAM laptops & 16 GB unified Macs stay swap-free."""
    cap = get_configured_max_context_window(max_ctx)
    native = min(cap, max(4096, int(base_ctx or 32768)))
    footprint = _infer_model_footprint_gb(model_id, model_ram_gb)
    avail = float(ram_available_gb) if ram_available_gb is not None else 12.0

    # Discrete low-VRAM hybrid laptop (e.g. 4-6 GB VRAM + 16 GB system RAM)
    if not unified_memory and vram_gb is not None and 0.0 < float(vram_gb) <= 6.5:
        if footprint <= float(vram_gb) - 0.8:
            budget_gb = max(0.8, float(vram_gb) - footprint - 0.5)
            tokens_est = int(budget_gb * 8192)
            stepped = max(8192, min(native, (tokens_est // 4096) * 4096 or 8192))
            return min(stepped, 16384)
        # Hybrid CPU+GPU spill: bound tightly to avoid latency collapse
        return min(native, 16384 if avail >= 8.0 else 8192)

    headroom = max(0.5, avail - (footprint * 0.45 if unified_memory else 1.2))
    # Approximate KV cache capacity (~1 GB -> ~10K tokens for 8B/9B GQA, denser for 27B)
    kv_per_gb = 6144 if "27b" in model_id.lower() or "32b" in model_id.lower() else 10240
    budget_tok = int(headroom * kv_per_gb)
    rounded = max(4096, (budget_tok // 4096) * 4096)
    return max(4096, min(native, rounded))


def estimate_tokens(text: str) -> int:
    """Fast heuristic token count (~4 chars/token, zero external tokenizer dependency)."""
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)
