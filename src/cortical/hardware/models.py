"""Hardware-aware Model Catalog, Dynamic Variable-Quantization Support, Downloader & Custom Builder."""

from __future__ import annotations

import copy
import shutil
import subprocess
from typing import Any, Optional

from .context_window import compute_dynamic_num_ctx

BUILTIN_MODEL_CATALOG: list[dict[str, Any]] = [
    {
        "model_id": "qwen2.5:1.5b",
        "runner": "ollama",
        "pull_ref": "ollama pull qwen2.5:1.5b",
        "memory_gb": 1.0,
        "native_ctx": 32768,
        "quantization": "Q4_K_M",
        "is_variable_quant": False,
        "roles": ["router", "ner"],
        "notes": "Fits completely in 4 GB VRAM; ultra-fast intent routing & JSON NER.",
    },
    {
        "model_id": "qwen2.5:3b",
        "runner": "ollama",
        "pull_ref": "ollama pull qwen2.5:3b",
        "memory_gb": 2.0,
        "native_ctx": 32768,
        "quantization": "Q4_K_M",
        "is_variable_quant": False,
        "roles": ["router", "ner", "fast_coder"],
        "notes": "Fits comfortably in 4 GB VRAM for hybrid laptops; strong JSON extraction.",
    },
    {
        "model_id": "qwen3:8b",
        "runner": "ollama",
        "pull_ref": "ollama pull qwen3:8b",
        "memory_gb": 5.2,
        "native_ctx": 32768,
        "quantization": "Q4_K_M",
        "is_variable_quant": False,
        "roles": ["daily_coder", "reviewer"],
        "notes": "Fast tool-calling reviewer & hybrid offload coder on 16 GB laptops.",
    },
    {
        "model_id": "qwen3.5:9b-q3_k_xl",
        "runner": "ollama",
        "pull_ref": "ollama pull hf.co/unsloth/Qwen3.5-9B-GGUF:UD-Q3_K_XL",
        "memory_gb": 5.1,
        "native_ctx": 131072,
        "quantization": "Unsloth Dynamic UD-Q3_K_XL",
        "is_variable_quant": True,
        "roles": ["daily_coder", "long_context", "reviewer"],
        "notes": "Variable-precision Unsloth dynamic quant (5.1 GB, up to 131K ctx).",
    },
    {
        "model_id": "qwen3.8:27b-iq2_xxs",
        "runner": "ollama",
        "pull_ref": "ollama pull hf.co/unsloth/Qwen3.8-27B-GGUF:UD-IQ2_XXS",
        "memory_gb": 7.2,
        "native_ctx": 32768,
        "quantization": "Unsloth Dynamic UD-IQ2_XXS",
        "is_variable_quant": True,
        "roles": ["deep_reasoner", "orchestrator"],
        "notes": "Runs 27B deep reasoning cleanly on 16 GB unified RAM in 7.2 GB.",
    },
    {
        "model_id": "qwen3.8:27b-q4_xxs",
        "runner": "ollama",
        "pull_ref": "ollama pull qwen3.8:27b-q4_xxs",
        "memory_gb": 8.1,
        "native_ctx": 32768,
        "quantization": "Unsloth Variable 4-bit XXS",
        "is_variable_quant": True,
        "roles": ["deep_reasoner", "orchestrator"],
        "notes": "Variable 4-bit XXS (~8.1 GB): deep reasoning, architecture & orchestration on 16 GB unified RAM.",
    },
    {
        "model_id": "qwen2.5-coder:32b",
        "runner": "ollama",
        "pull_ref": "ollama pull qwen2.5-coder:32b",
        "memory_gb": 19.5,
        "native_ctx": 32768,
        "quantization": "Q4_K_M",
        "is_variable_quant": False,
        "roles": ["deep_reasoner", "daily_coder"],
        "notes": "Workstation-class coder for 32+ GB RAM / 24+ GB VRAM machines.",
    },
]


def list_all_models(custom_models: Optional[list[dict[str, Any]]] = None) -> list[dict[str, Any]]:
    """Returns built-in catalog merged with user-configured custom models (custom entries override by model_id)."""
    by_id: dict[str, dict[str, Any]] = {m["model_id"]: copy.deepcopy(m) for m in BUILTIN_MODEL_CATALOG}
    for cm in (custom_models or []):
        mid = str(cm.get("model_id") or "").strip()
        if not mid:
            continue
        by_id[mid] = {
            "model_id": mid,
            "runner": str(cm.get("runner") or "ollama"),
            "pull_ref": str(cm.get("pull_ref") or f"ollama pull {mid}"),
            "memory_gb": float(cm.get("memory_gb") or 5.0),
            "native_ctx": int(cm.get("native_ctx") or 32768),
            "quantization": str(cm.get("quantization") or "custom"),
            "is_variable_quant": bool(cm.get("is_variable_quant", False)),
            "roles": list(cm.get("roles") or ["daily_coder"]),
            "notes": str(cm.get("notes") or "User-configured custom model."),
            "custom": True,
        }
    return list(by_id.values())


def evaluate_model_fit(model: dict[str, Any], hw: dict[str, Any]) -> dict[str, Any]:
    """Assesses whether a model fits GPU VRAM, Unified RAM, or Hybrid offload cleanly."""
    mem_req = float(model.get("memory_gb") or 5.0)
    total_ram = float(hw.get("total_ram_gb") or 16.0)
    vram = float(hw.get("vram_gb") or 0.0)
    unified = bool(hw.get("unified_memory"))
    native_ctx = int(model.get("native_ctx") or 32768)

    if unified:
        headroom = total_ram - mem_req
        if headroom >= 5.0:
            fit = "optimal_unified"
            reason = f"Fits unified memory ({mem_req:.1f} GB / {total_ram:.0f} GB, ~{headroom:.1f} GB OS/KV margin)"
        elif headroom >= 3.0:
            fit = "tight_unified"
            reason = f"Runs swap-free with bounded num_ctx ({mem_req:.1f} GB / {total_ram:.0f} GB)"
        else:
            fit = "too_large"
            reason = f"Exceeds safe unified memory budget ({mem_req:.1f} GB vs {total_ram:.0f} GB)"
    else:
        if vram >= mem_req + 1.0:
            fit = "optimal_vram"
            reason = f"Fits 100% in GPU VRAM ({mem_req:.1f} GB <= {vram:.1f} GB VRAM)"
        elif total_ram >= mem_req + 6.0 and vram >= 3.5:
            fit = "hybrid_ram_vram"
            reason = f"Runs in hybrid VRAM+RAM offload ({vram:.1f} GB VRAM + {total_ram:.0f} GB RAM)"
        elif total_ram >= mem_req + 6.0:
            fit = "cpu_ram_only"
            reason = f"CPU RAM offload only ({mem_req:.1f} GB in {total_ram:.0f} GB RAM; slower)"
        else:
            fit = "too_large"
            reason = f"Exceeds safe RAM+VRAM budget ({mem_req:.1f} GB)"

    rec_ctx = compute_dynamic_num_ctx(
        base_ctx=native_ctx,
        model_id=str(model.get("model_id") or ""),
        ram_available_gb=float(hw.get("free_ram_gb") or max(4.0, total_ram * 0.5)),
        vram_gb=vram,
        unified_memory=unified,
        model_ram_gb=mem_req,
    )
    return {
        "model_id": model["model_id"],
        "fit": fit,
        "viable": fit != "too_large",
        "recommended_num_ctx": rec_ctx,
        "reason": reason,
    }


def recommend_models_for_hardware(
    hw: dict[str, Any],
    custom_models: Optional[list[dict[str, Any]]] = None,
    installed_models: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Decides optimal local models to keep or download per role based on real hardware tier."""
    tier_info = hw.get("classification") or {}
    if not tier_info.get("local_llm_viable", True):
        return {
            "tier": tier_info.get("tier", "tier_0_lean"),
            "local_llm_viable": False,
            "recommended_by_role": {},
            "candidates": [],
            "to_download": [],
            "note": tier_info.get("recommendation", "Skip local model downloads on Lean hardware."),
        }

    installed_set = {
        str(m.get("name") if isinstance(m, dict) else m).strip().lower()
        for m in (installed_models if installed_models is not None else hw.get("installed_ollama_models") or [])
        if (m.get("name") if isinstance(m, dict) else m)
    }

    catalog = list_all_models(custom_models)
    candidates: list[dict[str, Any]] = []
    for m in catalog:
        fit = evaluate_model_fit(m, hw)
        is_inst = m["model_id"].lower() in installed_set or any(m["model_id"].split(":")[0].lower() == i.split(":")[0] and m["quantization"].lower() in i for i in installed_set)
        candidates.append({**m, **fit, "installed": is_inst})

    def _pick(role: str, prefer_variable: bool = False) -> Optional[dict[str, Any]]:
        viable = [c for c in candidates if c["viable"] and role in (c.get("roles") or [])]
        if not viable:
            return None
        rank_fit = {"optimal_vram": 5, "optimal_unified": 5, "hybrid_ram_vram": 4, "tight_unified": 3, "cpu_ram_only": 1}
        viable.sort(
            key=lambda c: (
                rank_fit.get(c["fit"], 0),
                1 if (prefer_variable and c.get("is_variable_quant")) else 0,
                1 if c["installed"] else 0,
                float(c.get("memory_gb") or 0.0),
            ),
            reverse=True,
        )
        return viable[0]

    rec_roles: dict[str, dict[str, Any]] = {}
    for role, pref_var in (("router", False), ("ner", False), ("daily_coder", True), ("deep_reasoner", True), ("orchestrator", True)):
        chosen = _pick(role, prefer_variable=pref_var)
        if chosen:
            rec_roles[role] = {
                "model_id": chosen["model_id"],
                "quantization": chosen["quantization"],
                "memory_gb": chosen["memory_gb"],
                "recommended_num_ctx": chosen["recommended_num_ctx"],
                "fit": chosen["fit"],
                "installed": chosen["installed"],
                "pull_ref": chosen["pull_ref"],
            }

    seen_dl: set[str] = set()
    to_download: list[dict[str, str]] = []
    for info in rec_roles.values():
        mid = info["model_id"]
        if not info["installed"] and mid not in seen_dl:
            seen_dl.add(mid)
            to_download.append({"model_id": mid, "pull_ref": info["pull_ref"]})

    return {
        "tier": tier_info.get("tier", "tier_1b_unified_16_24"),
        "local_llm_viable": True,
        "recommended_by_role": rec_roles,
        "candidates": candidates,
        "to_download": to_download,
    }


def add_custom_model(config: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    """Adds or updates a user-defined (or variable-quantized) model in config."""
    mid = str(spec.get("model_id") or "").strip()
    if not mid:
        raise ValueError("model_id is required")
    entry = {
        "model_id": mid,
        "runner": str(spec.get("runner") or "ollama"),
        "pull_ref": str(spec.get("pull_ref") or f"ollama pull {mid}"),
        "memory_gb": float(spec.get("memory_gb") or 5.0),
        "native_ctx": int(spec.get("native_ctx") or 32768),
        "quantization": str(spec.get("quantization") or "variable-quant"),
        "is_variable_quant": bool(spec.get("is_variable_quant", False)),
        "roles": list(spec.get("roles") or ["daily_coder"]),
        "notes": str(spec.get("notes") or "Custom user model"),
    }
    models = [copy.deepcopy(m) for m in (config.get("custom_models") or []) if str(m.get("model_id") or "").strip() != mid]
    models.append(entry)
    config["custom_models"] = models
    return entry


def remove_custom_model(config: dict[str, Any], model_id: str) -> bool:
    """Removes a custom model entry by model_id."""
    before = list(config.get("custom_models") or [])
    after = [m for m in before if str(m.get("model_id") or "").strip() != model_id.strip()]
    config["custom_models"] = after
    return len(after) < len(before)


def pull_model(model_id: str, runner: str = "ollama", dry_run: bool = False) -> dict[str, Any]:
    """Pulls a model via Ollama CLI (or returns exact command in dry-run)."""
    mid = str(model_id or "").strip()
    if runner != "ollama":
        return {"ok": False, "model_id": mid, "command": [], "error": f"Auto-pull only implemented for ollama, use runner CLI for '{runner}'."}
    cmd = ["ollama", "pull", mid]
    if dry_run:
        return {"ok": True, "dry_run": True, "model_id": mid, "command": " ".join(cmd)}
    if not shutil.which("ollama"):
        return {"ok": False, "model_id": mid, "command": " ".join(cmd), "error": "ollama binary not found in PATH"}
    proc = subprocess.run(cmd, check=False)
    return {"ok": proc.returncode == 0, "dry_run": False, "model_id": mid, "command": " ".join(cmd), "returncode": proc.returncode}
