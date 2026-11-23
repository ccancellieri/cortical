"""`cortical apply` — atomic, reversible, zero-server handoff from the static dashboard to the machine.

A `cortical-plan.json` bundle (exported by `settings.html`) carries pending config edits, custom
variable-quant models, vault policy changes, and harnesses to sync. `apply_plan()` validates it,
snapshots every touched file into ONE timestamped backup (manifest compatible with
`cortical sync --rollback <id>`), then applies everything idempotently. Python stdlib only.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Optional

from .config import DEFAULT_CONFIG, DEFAULT_CONFIG_PATH, DEFAULT_VAULT_DB, _deep_merge, load_cortical_config
from .harnesses.adapters import ALL_HARNESSES, FileChange

PLAN_SCHEMA = "cortical-plan/v1"
_POLICIES = {"auto", "fail_closed", "fail_open"}
_PROFILES = {"max_security", "low", "medium", "max_context"}
_ROUTING_MODES = {"auto", "full_local", "cloud_first"}


class PlanError(ValueError):
    """Raised when a plan bundle fails validation (nothing is written)."""


def read_clipboard_text() -> str:
    """Reads OS clipboard via stdlib subprocess (`pbpaste` / `wl-paste` / `xclip` / `xsel` / PowerShell)."""
    if sys.platform == "darwin":
        candidates = [["pbpaste"]]
    elif sys.platform.startswith("win"):
        candidates = [["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"]]
    else:
        candidates = [["wl-paste", "--no-newline"], ["xclip", "-o", "-selection", "clipboard"], ["xsel", "--clipboard", "--output"]]
    tried: list[str] = []
    for cmd in candidates:
        if not shutil.which(cmd[0]):
            tried.append(cmd[0])
            continue
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5, check=False)
        except Exception:  # noqa: BLE001
            tried.append(cmd[0])
            continue
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout
        tried.append(cmd[0])
    raise PlanError(
        "Clipboard unavailable or empty (tried: " + ", ".join(tried or ["none"]) + "). "
        "Save the bundle with 'Download cortical-plan.json' and run: cortical apply cortical-plan.json"
    )


def load_plan(source: str | Path | dict[str, Any]) -> dict[str, Any]:
    if isinstance(source, dict):
        return copy.deepcopy(source)
    raw = str(source)
    p = Path(raw).expanduser()
    text = p.read_text(encoding="utf-8") if p.is_file() else raw
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PlanError(f"Plan is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise PlanError("Plan root must be a JSON object.")
    return data


def validate_plan(plan: dict[str, Any], *, current_vault: Optional[dict[str, dict[str, Any]]] = None) -> list[str]:
    """Returns a list of human-readable validation errors (empty list = valid)."""
    errs: list[str] = []
    if plan.get("schema") != PLAN_SCHEMA:
        errs.append(f"schema must be '{PLAN_SCHEMA}' (got {plan.get('schema')!r}).")

    patch = plan.get("config_patch") or {}
    if not isinstance(patch, dict):
        errs.append("config_patch must be an object.")
        patch = {}
    unknown = sorted(k for k in patch if k not in DEFAULT_CONFIG)
    if unknown:
        errs.append(f"config_patch has unknown top-level keys: {', '.join(unknown)}.")
    if "max_context_window" in patch:
        v = patch["max_context_window"]
        if not isinstance(v, int) or not (4096 <= v <= 1_000_000):
            errs.append("max_context_window must be an integer between 4096 and 1000000.")
    comp = patch.get("compression") or {}
    if "max_context_share" in comp and not (0.05 <= float(comp["max_context_share"]) <= 0.30):
        errs.append("compression.max_context_share must be between 0.05 and 0.30.")
    if "min_toon_saving_pct" in comp and not (0 <= float(comp["min_toon_saving_pct"]) <= 80):
        errs.append("compression.min_toon_saving_pct must be between 0 and 80.")
    rt = patch.get("routing") or {}
    if "mode" in rt and rt["mode"] not in _ROUTING_MODES:
        errs.append(f"routing.mode must be one of {sorted(_ROUTING_MODES)}.")
    orch = patch.get("orchestrator") or {}
    if orch:
        if "mode" in orch and orch["mode"] not in {"local", "remote"}:
            errs.append("orchestrator.mode must be 'local' or 'remote'.")
        if "context_strategy" in orch and orch["context_strategy"] not in {"auto_max", "fixed"}:
            errs.append("orchestrator.context_strategy must be 'auto_max' or 'fixed'.")
        if "fixed_num_ctx" in orch:
            fc = orch["fixed_num_ctx"]
            if not isinstance(fc, int) or not (4096 <= fc <= 1_000_000):
                errs.append("orchestrator.fixed_num_ctx must be an integer between 4096 and 1000000.")
        if "timeout_sec" in orch:
            ts = orch["timeout_sec"]
            if not isinstance(ts, int) or not (0 <= ts <= 3600):
                errs.append("orchestrator.timeout_sec must be an integer between 0 and 3600.")
        ake = str(orch.get("api_key_env") or "").strip()
        if ake and (ake.startswith(("sk-", "AIza", "ghp_", "pplx-")) or len(ake) > 64 or not ake.replace("_", "").isalnum()):
            errs.append("orchestrator.api_key_env must be an environment variable name (e.g. GEMINI_API_KEY), never a raw secret.")
    pv = patch.get("privacy") or {}
    if "default_policy" in pv and pv["default_policy"] not in _POLICIES:
        errs.append(f"privacy.default_policy must be one of {sorted(_POLICIES)}.")
    if "default_profile" in pv and pv["default_profile"] not in _PROFILES:
        errs.append(f"privacy.default_profile must be one of {sorted(_PROFILES)}.")

    for i, m in enumerate(plan.get("custom_models") or []):
        if not str(m.get("model_id") or "").strip():
            errs.append(f"custom_models[{i}].model_id is required.")
        try:
            if not (0.1 <= float(m.get("memory_gb", 0)) <= 512):
                errs.append(f"custom_models[{i}].memory_gb must be between 0.1 and 512.")
            if not (512 <= int(m.get("native_ctx", 0)) <= 2_000_000):
                errs.append(f"custom_models[{i}].native_ctx must be between 512 and 2000000.")
        except (TypeError, ValueError):
            errs.append(f"custom_models[{i}] has non-numeric memory_gb/native_ctx.")

    vault_now = current_vault or {}
    for i, vu in enumerate(plan.get("vault_updates") or []):
        alias = str(vu.get("alias") or "")
        prof = vu.get("profile")
        pol = vu.get("policy")
        if not alias:
            errs.append(f"vault_updates[{i}].alias is required.")
            continue
        if prof is not None and prof not in _PROFILES:
            errs.append(f"vault_updates[{i}].profile invalid.")
        if pol is not None and pol not in _POLICIES:
            errs.append(f"vault_updates[{i}].policy invalid.")
        if prof == "max_security" and pol not in (None, "fail_closed"):
            errs.append(f"vault_updates[{i}] ({alias}): max_security items are fail_closed only.")
        cur = vault_now.get(alias)
        if cur is not None and cur.get("local_only") and prof not in (None, "max_security"):
            errs.append(f"vault_updates[{i}] ({alias}): refusing to downgrade a LOCAL-ONLY max_security item via plan; use 'cortical vault update' interactively.")
        if cur is not None and cur.get("local_only") and pol == "fail_open":
            errs.append(f"vault_updates[{i}] ({alias}): fail_open is forbidden on LOCAL-ONLY items.")

    sh = plan.get("sync_harnesses", [])
    if sh not in ("all", None) and not isinstance(sh, list):
        errs.append("sync_harnesses must be 'all' or a list of harness ids.")
    elif isinstance(sh, list):
        bad = [h for h in sh if h not in ALL_HARNESSES]
        if bad:
            errs.append(f"Unknown harnesses: {', '.join(bad)}. Valid: {', '.join(ALL_HARNESSES)}.")
    return errs


def _default_plan_changes(cfg: dict[str, Any], harnesses: list[str]) -> list[FileChange]:
    from .hardware.models import recommend_models_for_hardware
    from .hardware.probe import probe_hardware
    from .harnesses.adapters import plan_sync

    hw = probe_hardware(runners_probe=False)
    rec = recommend_models_for_hardware(hw, custom_models=cfg.get("custom_models"), installed_models=hw.get("installed_ollama_models"))
    return plan_sync(cfg, hw, rec, harnesses=harnesses)


def apply_plan(
    plan_source: str | Path | dict[str, Any],
    *,
    dry_run: bool = False,
    config_path: Optional[Path] = None,
    vault_db: Optional[Path] = None,
    backup_root: Optional[Path] = None,
    plan_changes_fn: Optional[Callable[[dict[str, Any], list[str]], list[FileChange]]] = None,
    regenerate_dashboard: Optional[str] = None,
) -> dict[str, Any]:
    plan = load_plan(plan_source)
    cfg_path = Path(config_path or os.environ.get("CORTICAL_CONFIG_PATH") or DEFAULT_CONFIG_PATH).expanduser()
    v_db = Path(vault_db or os.environ.get("CORTICAL_VAULT_DB") or DEFAULT_VAULT_DB).expanduser()

    vault = None
    current_vault: dict[str, dict[str, Any]] = {}
    if plan.get("vault_updates") and v_db.is_file():
        from .privacy.vault import PrivacyVault

        vault = PrivacyVault(v_db)
        current_vault = {it["alias"]: it for it in vault.list_items(include_local_only=True)}

    errors = validate_plan(plan, current_vault=current_vault)
    missing = [vu.get("alias") for vu in plan.get("vault_updates") or [] if vu.get("alias") and vu.get("alias") not in current_vault]
    if missing:
        errors.append(f"Unknown vault aliases: {', '.join(missing)}.")
    if errors:
        raise PlanError("Plan validation failed:\n  - " + "\n  - ".join(errors))

    # 1. Compose new config (deep merge + custom model upserts)
    base_cfg = load_cortical_config(config_path=cfg_path)
    new_cfg = _deep_merge(base_cfg, plan.get("config_patch") or {})
    if plan.get("custom_models"):
        by_id = {m["model_id"]: m for m in new_cfg.get("custom_models") or []}
        for m in plan["custom_models"]:
            entry = {
                "model_id": str(m["model_id"]).strip(),
                "runner": str(m.get("runner") or "ollama"),
                "memory_gb": float(m["memory_gb"]),
                "native_ctx": int(m["native_ctx"]),
                "quantization": str(m.get("quantization") or "custom"),
                "is_variable_quant": bool(m.get("is_variable_quant", False)),
                "roles": list(m.get("roles") or ["daily_coder"]),
                "pull_ref": str(m.get("pull_ref") or f"ollama pull {m['model_id']}"),
                "notes": str(m.get("notes") or "Added via cortical apply"),
            }
            by_id[entry["model_id"]] = entry
        new_cfg["custom_models"] = list(by_id.values())

    cfg_text = json.dumps(new_cfg, indent=2, ensure_ascii=False) + "\n"
    old_text = cfg_path.read_text(encoding="utf-8") if cfg_path.is_file() else ""
    changes: list[FileChange] = []
    if cfg_text != old_text:
        changes.append(FileChange("cortical-config", cfg_path, cfg_text, "json", "update" if cfg_path.is_file() else "create", "cortical.config.json"))

    # 2. Harness sync plan (computed against the NEW config)
    sh = plan.get("sync_harnesses") or []
    targets = list(ALL_HARNESSES) if sh == "all" else list(sh)
    if targets:
        changes.extend((plan_changes_fn or _default_plan_changes)(new_cfg, targets))
    pending = [c for c in changes if c.action != "unchanged"]
    vault_updates = list(plan.get("vault_updates") or [])

    summary: dict[str, Any] = {
        "dry_run": dry_run,
        "backup_id": None,
        "changes": [{"harness": c.harness, "path": str(c.path), "action": c.action, "detail": c.detail} for c in changes],
        "changed_count": len(pending),
        "vault_updates": [{"alias": v["alias"], "profile": v.get("profile"), "policy": v.get("policy")} for v in vault_updates],
        "custom_models": [m.get("model_id") for m in plan.get("custom_models") or []],
        "dashboard": None,
    }
    if dry_run or (not pending and not vault_updates):
        return summary

    # 3. Single atomic backup (manifest format == apply_sync -> rollback_sync compatible)
    b_root = Path(backup_root or (Path.home() / ".cortical" / "backups"))
    bid = time.strftime("%Y%m%d-%H%M%S") + "-apply"
    bdir = b_root / bid
    bdir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, Any]] = []
    targets_to_snapshot = [c.path for c in pending] + ([v_db] if vault_updates else [])
    for idx, path in enumerate(targets_to_snapshot):
        existed = path.is_file()
        snap = f"{idx:03d}_{path.name}.bak"
        if existed:
            shutil.copyfile(path, bdir / snap)
        manifest.append({"target_path": str(path), "existed": existed, "backup_file": snap if existed else None})
    (bdir / "manifest.json").write_text(json.dumps({"backup_id": bid, "source": "cortical apply", "entries": manifest}, indent=2), encoding="utf-8")
    summary["backup_id"] = bid
    summary["backup_dir"] = str(bdir)

    # 4. Apply (on failure, auto-rollback everything from this backup)
    try:
        for c in pending:
            c.path.parent.mkdir(parents=True, exist_ok=True)
            c.path.write_text(c.content, encoding="utf-8")
            c_hash = hashlib.sha256(c.content.encode("utf-8")).hexdigest()[:16]
            for m in manifest:
                if m["target_path"] == str(c.path):
                    m["sha256_after"] = c_hash
        if vault_updates and vault is not None:
            for vu in vault_updates:
                prof = vu.get("profile")
                pol = "fail_closed" if prof == "max_security" else vu.get("policy")
                vault.re_sanitize(vu["alias"], profile=prof, policy=pol, custom_terms=vu.get("custom_terms"), config=new_cfg)
    except Exception as exc:
        from .harnesses.adapters import rollback_sync

        rollback_sync(bid, backup_root=b_root)
        raise PlanError(f"Apply failed and was rolled back ({bid}): {exc}") from exc

    (bdir / "manifest.json").write_text(json.dumps({"backup_id": bid, "source": "cortical apply", "entries": manifest}, indent=2), encoding="utf-8")

    out_dir = regenerate_dashboard or plan.get("regenerate_dashboard")
    if out_dir:
        from .analytics.dashboard import export_static_dashboard

        s_path, _ = export_static_dashboard(Path(out_dir), config=new_cfg)
        summary["dashboard"] = str(s_path)
    return summary
