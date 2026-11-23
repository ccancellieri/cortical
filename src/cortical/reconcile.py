"""Single Source of Truth Drift Detection & Auto-Reconciliation across Models, Router, Services & Harnesses.

Python 3.10+ stdlib only (`dependencies = []`).
"""

from __future__ import annotations

import copy
import hashlib
import os
from pathlib import Path
from typing import Any, Optional

from .composers.router import render_litellm_config_yaml
from .composers.tools import inspect_composed_tools
from .config import default_data_dir, load_cortical_config, save_cortical_config
from .hardware.models import recommend_models_for_hardware
from .hardware.probe import probe_hardware
from .harnesses.adapters import apply_sync, plan_sync

REQUIRED_ROUTER_ALIASES: tuple[str, ...] = (
    "local-default",
    "cortical-fast",
    "cortical-deep",
    "cortical-vision",
)


def _match_installed_model(configured: str, installed: list[str]) -> Optional[str]:
    """Selects the closest installed model matching `configured` by exact tag or shared family/prefix."""
    if not installed:
        return None
    if configured in installed:
        return configured
    low_cfg = configured.lower()
    base = low_cfg.split(":", 1)[0]
    same_base = [m for m in installed if m.lower().split(":", 1)[0] == base]
    if same_base:
        # Prefer longest shared prefix (e.g. qwen3.8:27b-iq2_xxs for qwen3.8:27b-q4_xxs)
        return max(same_base, key=lambda cand: len(os.path.commonprefix([low_cfg, cand.lower()])))
    # Fallback by model size/family substring
    root_family = base.split("-", 1)[0].rstrip("0123456789.")
    if root_family:
        same_family = [m for m in installed if root_family in m.lower()]
        if same_family:
            return max(same_family, key=lambda cand: len(os.path.commonprefix([low_cfg, cand.lower()])))
    return installed[0]


def _normalize_installed_models(installed_models: list[Any]) -> list[str]:
    """Extracts model IDs cleanly whether callers pass strings or Ollama tag dicts."""
    out: list[str] = []
    for item in installed_models or []:
        if isinstance(item, dict):
            name = str(item.get("name") or item.get("model") or "").strip()
        else:
            name = str(item or "").strip()
        if name and name not in out:
            out.append(name)
    return out


def resolve_validated_models(cfg: dict[str, Any], installed_models: list[Any]) -> dict[str, Any]:
    """Validates `models_by_role` and `privacy.vision_model` against installed local models."""
    by_role = dict(cfg.get("models_by_role") or {})
    priv_vision = str((cfg.get("privacy") or {}).get("vision_model") or "").strip()
    norm_installed = _normalize_installed_models(installed_models)

    if not norm_installed:
        return {
            "checked": False,
            "installed_count": 0,
            "drifted": [],
            "resolved_by_role": by_role,
            "resolved_vision_model": priv_vision,
        }

    installed_set = set(norm_installed)
    drifted: list[dict[str, str]] = []
    resolved = dict(by_role)

    for role, model_id in by_role.items():
        mid = str(model_id or "").strip()
        if not mid or mid in installed_set:
            continue
        replacement = _match_installed_model(mid, norm_installed) or mid
        if replacement != mid:
            drifted.append({
                "role": role,
                "configured": mid,
                "replacement": replacement,
                "reason": "Configured model is not installed locally.",
            })
            resolved[role] = replacement

    resolved_vision = priv_vision
    if priv_vision and priv_vision not in installed_set:
        vision_cands = [m for m in norm_installed if any(k in m.lower() for k in ("ocr", "vl", "vision"))]
        replacement = _match_installed_model(priv_vision, vision_cands or norm_installed) or priv_vision
        if replacement != priv_vision:
            drifted.append({
                "role": "privacy.vision_model",
                "configured": priv_vision,
                "replacement": replacement,
                "reason": "Configured vision model is not installed locally.",
            })
            resolved_vision = replacement

    return {
        "checked": True,
        "installed_count": len(norm_installed),
        "drifted": drifted,
        "resolved_by_role": resolved,
        "resolved_vision_model": resolved_vision,
    }


def detect_router_drift(
    cfg: dict[str, Any],
    *,
    router_config_path: Optional[Path] = None,
    served_models: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Detects config SHA-256 drift vs expected `litellm_config.yaml` and missing runtime aliases."""
    yaml_path = Path(router_config_path) if router_config_path is not None else (default_data_dir() / "litellm_config.yaml")
    expected_yaml = render_litellm_config_yaml(cfg)
    expected_sha = hashlib.sha256(expected_yaml.encode("utf-8")).hexdigest()[:16]

    exists = yaml_path.is_file()
    disk_sha = hashlib.sha256(yaml_path.read_bytes()).hexdigest()[:16] if exists else ""
    router_enabled = bool((cfg.get("router") or {}).get("enabled", False))
    config_drift = (disk_sha != expected_sha) if (exists or router_enabled or router_config_path is not None) else False

    missing_aliases: list[str] = []
    runtime_drift = False
    if served_models is not None:
        served_set = set(served_models)
        missing_aliases = [a for a in REQUIRED_ROUTER_ALIASES if a not in served_set]
        runtime_drift = bool(missing_aliases)

    return {
        "path": str(yaml_path),
        "exists": exists,
        "enabled": router_enabled,
        "config_drift": config_drift,
        "runtime_drift": runtime_drift,
        "missing_aliases": missing_aliases,
        "expected_sha256": expected_sha,
        "disk_sha256": disk_sha,
        "expected_yaml": expected_yaml,
    }


def detect_all_drift(
    *,
    config: Optional[dict[str, Any]] = None,
    hw: Optional[dict[str, Any]] = None,
    served_models: Optional[list[str]] = None,
    router_config_path: Optional[Path] = None,
    user_paths: Optional[dict[str, dict[str, Path]]] = None,
    repo_root: Optional[Path] = None,
) -> dict[str, Any]:
    """Aggregates drift across models, LiteLLM router, harnesses, and composed OSS tools."""
    cfg = copy.deepcopy(config if config is not None else load_cortical_config())
    hw_info = hw if hw is not None else probe_hardware(runners_probe=True)
    installed = _normalize_installed_models(list(hw_info.get("installed_ollama_models") or []))

    model_res = resolve_validated_models(cfg, installed)
    router_res = detect_router_drift(cfg, router_config_path=router_config_path, served_models=served_models)

    rec = recommend_models_for_hardware(
        hw_info,
        custom_models=cfg.get("custom_models"),
        installed_models=installed,
    )
    planned = plan_sync(cfg, hw_info, rec, repo_root=repo_root, user_paths=user_paths)
    pending_harnesses = [
        {"harness": ch.harness, "path": str(ch.path), "action": ch.action, "detail": ch.detail}
        for ch in planned
        if ch.action != "unchanged"
    ]

    tools_map = inspect_composed_tools(os_name=hw_info.get("os"))
    tools_missing = [k for k, v in tools_map.items() if not v.get("installed")]
    tools_info = {
        "installed_count": sum(1 for v in tools_map.values() if v.get("installed")),
        "total_count": len(tools_map),
        "missing_tools": tools_missing,
        "by_tool": tools_map,
    }

    drift_count = (
        len(model_res["drifted"])
        + (1 if router_res["config_drift"] else 0)
        + (1 if router_res["runtime_drift"] else 0)
        + len(pending_harnesses)
    )
    return {
        "in_sync": drift_count == 0,
        "drift_count": drift_count,
        "models": model_res,
        "router": {k: v for k, v in router_res.items() if k != "expected_yaml"},
        "harnesses": {
            "pending_count": len(pending_harnesses),
            "pending": pending_harnesses,
        },
        "tools": tools_info,
    }


def reconcile_all(
    *,
    config: Optional[dict[str, Any]] = None,
    dry_run: bool = True,
    config_path: Optional[Path] = None,
    router_config_path: Optional[Path] = None,
    hw: Optional[dict[str, Any]] = None,
    served_models: Optional[list[str]] = None,
    user_paths: Optional[dict[str, dict[str, Path]]] = None,
    backup_root: Optional[Path] = None,
    repo_root: Optional[Path] = None,
) -> dict[str, Any]:
    """Detects drift and (when `dry_run=False`) reconciles config, router YAML, and harnesses."""
    cfg = copy.deepcopy(config if config is not None else load_cortical_config(config_path=config_path))
    hw_info = hw if hw is not None else probe_hardware(runners_probe=True)
    installed = _normalize_installed_models(list(hw_info.get("installed_ollama_models") or []))

    drift_before = detect_all_drift(
        config=cfg,
        hw=hw_info,
        served_models=served_models,
        router_config_path=router_config_path,
        user_paths=user_paths,
        repo_root=repo_root,
    )
    if dry_run:
        return {
            "dry_run": True,
            "applied": False,
            "backup_id": None,
            **drift_before,
        }

    updated_cfg = copy.deepcopy(cfg)
    cfg_dirty = False
    model_info = drift_before["models"]
    if model_info["drifted"]:
        updated_cfg["models_by_role"] = dict(model_info["resolved_by_role"])
        if model_info["resolved_vision_model"]:
            updated_cfg.setdefault("privacy", {})
            updated_cfg["privacy"]["vision_model"] = model_info["resolved_vision_model"]
        cfg_dirty = True

    if cfg_dirty:
        save_cortical_config(updated_cfg, config_path=config_path)

    # Refresh router config YAML if drifted (using updated_cfg)
    router_after = detect_router_drift(updated_cfg, router_config_path=router_config_path, served_models=served_models)
    router_written = False
    if router_after["config_drift"] or cfg_dirty:
        yaml_path = Path(router_after["path"])
        yaml_path.parent.mkdir(parents=True, exist_ok=True)
        yaml_path.write_text(router_after["expected_yaml"], encoding="utf-8")
        router_written = True

    rec = recommend_models_for_hardware(
        hw_info,
        custom_models=updated_cfg.get("custom_models"),
        installed_models=installed,
    )
    planned = plan_sync(updated_cfg, hw_info, rec, repo_root=repo_root, user_paths=user_paths)
    sync_res = apply_sync(planned, dry_run=False, backup_root=backup_root)

    return {
        "dry_run": False,
        "applied": bool(cfg_dirty or router_written or sync_res.get("changed_count", 0) > 0),
        "config_updated": cfg_dirty,
        "router_yaml_written": router_written,
        "backup_id": sync_res.get("backup_id"),
        "changed_harnesses": sync_res.get("changed_count", 0),
        **drift_before,
    }
