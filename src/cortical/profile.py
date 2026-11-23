"""Portable zero-secret Team & Dotfile Profile Bundles (`cortical profile export|diff|import`)."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any, Optional

from .apply import PLAN_SCHEMA, apply_plan, validate_plan
from .config import load_cortical_config
from .hardware.probe import classify_hardware_tier

PROFILE_SCHEMA = "cortical-profile/v1"

_SECRET_RE = re.compile(
    r"^(?:sk-|AIza|gh[pous]_|github_pat_|AKIA|pplx-|xox[bpa]-)",
    re.IGNORECASE,
)

_PORTABLE_KEYS: tuple[str, ...] = (
    "active_runner",
    "active_model",
    "max_context_window",
    "orchestrator",
    "models_by_role",
    "composers",
    "harnesses",
    "privacy",
    "routing",
    "compression",
    "report",
)


def _scrub_home(val: Any, home_prefixes: tuple[str, ...]) -> Any:
    """Normalizes absolute home directory prefixes (raw and resolved) to `~` recursively."""
    if isinstance(val, str):
        out = val
        for pref in home_prefixes:
            if pref:
                out = out.replace(pref, "~")
        return out
    if isinstance(val, list):
        return [_scrub_home(v, home_prefixes) for v in val]
    if isinstance(val, dict):
        return {k: _scrub_home(v, home_prefixes) for k, v in val.items()}
    return val


def _is_raw_secret(value: str) -> bool:
    raw = str(value or "").strip()
    if not raw:
        return False
    return bool(_SECRET_RE.match(raw) or len(raw) > 64 or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", raw))


def export_profile_bundle(
    config: Optional[dict[str, Any]] = None,
    hw: Optional[dict[str, Any]] = None,
    *,
    home: Optional[Path] = None,
) -> dict[str, Any]:
    """Exports a portable, secret-free `cortical-profile/v1` bundle."""
    cfg = copy.deepcopy(config if config is not None else load_cortical_config())
    h_raw = Path(home or Path.home())
    prefixes = tuple(dict.fromkeys([str(h_raw.resolve()), str(h_raw)]))
    tier_info = (hw or {}).get("classification") or (classify_hardware_tier(hw) if hw else {"tier": "portable", "label": "Portable Profile"})

    patch: dict[str, Any] = {}
    for k in _PORTABLE_KEYS:
        if k in cfg:
            patch[k] = _scrub_home(copy.deepcopy(cfg[k]), prefixes)

    # Guarantee zero secret tokens ever leave in orchestrator.api_key_env
    orch = patch.get("orchestrator") or {}
    if orch.get("api_key_env") and _is_raw_secret(str(orch["api_key_env"])):
        orch["api_key_env"] = ""
    if "privacy" in patch and isinstance(patch["privacy"], dict):
        patch["privacy"].pop("vault_db", None)

    custom_models = _scrub_home(copy.deepcopy(cfg.get("custom_models") or []), prefixes)
    return {
        "schema": PROFILE_SCHEMA,
        "hardware_tier": str(tier_info.get("tier") or "portable"),
        "hardware_summary": {
            "label": str(tier_info.get("label") or ""),
            "total_ram_gb": (hw or {}).get("total_ram_gb"),
            "vram_gb": (hw or {}).get("vram_gb"),
            "unified_memory": bool((hw or {}).get("unified_memory", False)),
        },
        "config_patch": patch,
        "custom_models": custom_models,
    }


def diff_profile_bundles(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """Computes structured differences between two `cortical-profile/v1` bundles or raw configs."""
    lp = left.get("config_patch") if isinstance(left.get("config_patch"), dict) else left
    rp = right.get("config_patch") if isinstance(right.get("config_patch"), dict) else right

    changed: dict[str, dict[str, Any]] = {}
    for k in sorted(set(lp.keys()) | set(rp.keys())):
        if lp.get(k) != rp.get(k):
            changed[k] = {"left": lp.get(k), "right": rp.get(k)}

    lm = {str(m.get("model_id")): m for m in (left.get("custom_models") or []) if m.get("model_id")}
    rm = {str(m.get("model_id")): m for m in (right.get("custom_models") or []) if m.get("model_id")}
    added_models = [rm[mid] for mid in sorted(set(rm) - set(lm))]
    removed_models = [lm[mid] for mid in sorted(set(lm) - set(rm))]

    lh = lp.get("harnesses") or {}
    rh = rp.get("harnesses") or {}
    harness_deltas = {
        h: {"left": lh.get(h), "right": rh.get(h)}
        for h in sorted(set(lh) | set(rh))
        if lh.get(h) != rh.get(h)
    }

    lt = str(left.get("hardware_tier") or "unknown")
    rt = str(right.get("hardware_tier") or "unknown")
    return {
        "changed_keys": sorted(changed.keys()),
        "changes": changed,
        "added_custom_models": added_models,
        "removed_custom_models": removed_models,
        "harness_deltas": harness_deltas,
        "tier_comparison": {"left": lt, "right": rt, "same_tier": lt == rt},
    }


def load_profile_bundle(source: str | Path | dict[str, Any]) -> dict[str, Any]:
    """Loads a `cortical-profile/v1` bundle from file path, inline JSON string, or dict."""
    if isinstance(source, dict):
        return copy.deepcopy(source)
    p = Path(str(source)).expanduser()
    raw = p.read_text(encoding="utf-8") if p.is_file() else str(source)
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Profile bundle root must be a JSON object.")
    return data


def import_profile_bundle(
    source: str | Path | dict[str, Any],
    *,
    dry_run: bool = False,
    config_path: Optional[Path] = None,
    sync_harnesses: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Validates and applies a portable `cortical-profile/v1` bundle via `cortical-plan/v1`."""
    bundle = load_profile_bundle(source)
    if bundle.get("schema") != PROFILE_SCHEMA:
        raise ValueError(f"Profile schema must be '{PROFILE_SCHEMA}' (got {bundle.get('schema')!r}).")

    patch = copy.deepcopy(bundle.get("config_patch") or {})
    orch = patch.get("orchestrator") or {}
    ake = str(orch.get("api_key_env") or "").strip()
    if ake and _is_raw_secret(ake):
        raise ValueError("Profile rejected: orchestrator.api_key_env contains a raw secret literal.")

    plan = {
        "schema": PLAN_SCHEMA,
        "config_patch": patch,
        "custom_models": list(bundle.get("custom_models") or []),
        "vault_updates": [],
        "sync_harnesses": list(sync_harnesses or []),
    }
    errs = validate_plan(plan)
    if errs:
        raise ValueError("Invalid profile bundle:\n  - " + "\n  - ".join(errs))

    res = apply_plan(plan, dry_run=dry_run, config_path=config_path)
    return {**res, "imported_profile_schema": PROFILE_SCHEMA, "hardware_tier": bundle.get("hardware_tier")}
