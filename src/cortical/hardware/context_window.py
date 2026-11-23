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
    "qwen3.8:27b-iq2_xxs": 131072,
    "qwen3.8:27b-q4_xxs": 32768,
    "qwen2.5-coder:32b": 32768,
    "cortical-fast": 131072,
    "cortical-deep": 131072,
    "local-default": 131072,
    "minicpm-ocr:latest": 8192,
    "cortical-vision": 8192,
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
    if "cortical-deep" in low or ("27b" in low and ("iq2_xxs" in low or "iq2" in low)):
        return 7.2
    if "27b" in low and ("q4_xxs" in low or "4bit" in low or "4-bit" in low):
        return 8.1
    if "27b" in low and "xxs" in low:
        return 7.2
    if "32b" in low or "27b" in low:
        return 16.0 if "32b" in low else 12.0
    if "cortical-fast" in low or "local-default" in low or ("9b" in low and "q3" in low):
        return 5.1
    if "8b" in low or "9b" in low:
        return 5.2
    if "ocr" in low or "vl" in low:
        return 2.1
    if "3b" in low:
        return 2.0
    if "1.5b" in low or "2b" in low:
        return 1.2
    return 5.0


def _infer_kv_tokens_per_gb(model_id: str, kv_tokens_per_gb: Optional[int] = None) -> int:
    """Returns approximate KV-cache capacity (tokens per GB VRAM/Unified RAM) for a model."""
    if kv_tokens_per_gb is not None and int(kv_tokens_per_gb) > 0:
        return int(kv_tokens_per_gb)
    low = str(model_id or "").lower()
    if any(k in low for k in ("qwen3.8", "qwen3.5", "iq2_xxs", "cortical-deep", "cortical-fast", "local-default")):
        return 24576
    if "27b" in low or "32b" in low:
        return 8192
    return 12288


def _round_ctx_step(tokens: int, native: int) -> int:
    """Rounds context down to a safe 4096-token step within [4096, native]."""
    step = 8192 if tokens >= 32768 else 4096
    rounded = max(4096, (int(tokens) // step) * step)
    return max(4096, min(native, rounded))


def compute_adaptive_timeout(
    model_id: str,
    *,
    num_ctx: int = 32768,
    is_remote: bool = False,
) -> int:
    """Computes safe HTTP/stream timeout in seconds for local deep reasoners vs fast/remote models."""
    if is_remote:
        return 240 if "research" in str(model_id or "").lower() else 180
    low = str(model_id or "").lower()
    if any(k in low for k in ("27b", "32b", "70b", "72b", "cortical-deep", "cortical-orchestrator")):
        return 900 if int(num_ctx) > 65536 else 600
    if any(k in low for k in ("7b", "8b", "9b", "14b", "cortical-fast", "local-default")):
        return 300
    return 180


def compute_dynamic_num_ctx(
    base_ctx: int = 32768,
    model_id: str = "",
    *,
    ram_available_gb: Optional[float] = None,
    vram_gb: Optional[float] = None,
    unified_memory: bool = True,
    model_ram_gb: Optional[float] = None,
    max_ctx: Optional[int] = None,
    total_ram_gb: Optional[float] = None,
    memory_pressure_level: int = 1,
    kv_tokens_per_gb: Optional[int] = None,
) -> int:
    """Scales `num_ctx` cleanly up to hardware RAM/VRAM ceiling without swap thrashing."""
    cap = get_configured_max_context_window(max_ctx)
    native = min(cap, max(4096, int(base_ctx or 32768)))
    footprint = _infer_model_footprint_gb(model_id, model_ram_gb)
    kv_per_gb = _infer_kv_tokens_per_gb(model_id, kv_tokens_per_gb)

    if not unified_memory and vram_gb is not None and 0.0 < float(vram_gb) <= 6.5:
        if footprint <= float(vram_gb) - 0.8:
            budget_gb = max(0.8, float(vram_gb) - footprint - 0.5)
            return min(16384, _round_ctx_step(int(budget_gb * 8192), native))
        avail_d = float(ram_available_gb) if ram_available_gb is not None else 10.0
        return min(native, 16384 if avail_d >= 8.0 else 8192)

    if not unified_memory and vram_gb is not None and float(vram_gb) > 6.5:
        kv_budget_d = max(0.5, float(vram_gb) - footprint - 1.0)
        return _round_ctx_step(int(kv_budget_d * kv_per_gb), native)

    if unified_memory and total_ram_gb is not None and float(total_ram_gb) > 0:
        tot = float(total_ram_gb)
        metal_limit = float(vram_gb) if (vram_gb is not None and float(vram_gb) > 0) else round(tot * 0.70, 2)
        os_reserve = max(3.5, round(tot * 0.27, 2))
        eff_budget = min(metal_limit, max(2.0, tot - os_reserve))
        scratch = 0.65
        kv_budget = max(0.4, eff_budget - footprint - scratch)
        if int(memory_pressure_level or 1) >= 4:
            kv_budget *= 0.5
        if tot <= 18.0:
            if footprint >= 6.5 and native > 65536:
                native = 65536
            elif footprint >= 4.5 and native > 98304:
                native = 98304
        return _round_ctx_step(int(kv_budget * kv_per_gb), native)

    avail = float(ram_available_gb) if ram_available_gb is not None else 12.0
    headroom = max(0.5, avail - (footprint * 0.45 if unified_memory else 1.2))
    legacy_kv = kv_per_gb if ("iq2_xxs" in str(model_id).lower() or "cortical-deep" in str(model_id).lower()) else (6144 if "27b" in str(model_id).lower() or "32b" in str(model_id).lower() else 10240)
    return _round_ctx_step(int(headroom * legacy_kv), native)


def compute_hardware_context_profile(
    model_id: str,
    hw: dict[str, Any],
    *,
    model_spec: Optional[dict[str, Any]] = None,
    max_ctx: Optional[int] = None,
) -> dict[str, Any]:
    """Returns detailed hardware-ceiling context sizing & adaptive timeout breakdown for CLI/UI."""
    spec = model_spec or {}
    tot = float(hw.get("total_ram_gb") or 16.0)
    free_ram = float(hw.get("free_ram_gb") or tot * 0.5)
    vram = float(hw.get("vram_gb") or 0.0)
    unified = bool(hw.get("unified_memory", False))
    pressure = int(hw.get("memory_pressure_level") or 1)
    weights = _infer_model_footprint_gb(model_id, spec.get("memory_gb"))
    native_ctx = int(spec.get("native_ctx") or get_model_context_window(model_id, max_ctx=max_ctx, auto_discover=False))
    kv_density = _infer_kv_tokens_per_gb(model_id, spec.get("kv_tokens_per_gb"))

    auto_ctx = compute_dynamic_num_ctx(
        base_ctx=native_ctx,
        model_id=model_id,
        ram_available_gb=free_ram,
        vram_gb=vram,
        unified_memory=unified,
        model_ram_gb=weights,
        max_ctx=max_ctx,
        total_ram_gb=tot,
        memory_pressure_level=pressure,
        kv_tokens_per_gb=kv_density,
    )
    metal_workset = vram if unified and vram > 0 else (round(tot * 0.70, 2) if unified else vram)
    os_reserve = max(3.5, round(tot * 0.27, 2))
    eff_budget = min(metal_workset, max(2.0, tot - os_reserve)) if unified else vram
    gguf_arena = 0.65 if unified else 1.0
    kv_budget = round(max(0.4, eff_budget - weights - gguf_arena), 2)
    return {
        "model_id": model_id,
        "native_ctx": native_ctx,
        "auto_max_num_ctx": auto_ctx,
        "weights_gb": round(weights, 2),
        "total_ram_gb": round(tot, 2),
        "free_ram_gb": round(free_ram, 2),
        "vram_gb": round(vram, 2),
        "metal_workset_gb": round(metal_workset, 2),
        "gguf_arena_overhead_gb": gguf_arena,
        "kv_budget_gb": kv_budget,
        "kv_tokens_per_gb": kv_density,
        "memory_pressure_level": pressure,
        "zero_copy_safe": bool(auto_ctx >= 32768 and pressure < 4),
        "adaptive_timeout_sec": compute_adaptive_timeout(model_id, num_ctx=auto_ctx, is_remote=False),
    }


def estimate_tokens(text: str) -> int:
    """Fast heuristic token count (~4 chars/token, zero external tokenizer dependency)."""
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)
