"""Continuous local Auto-Tuner (0 cloud tokens) optimizing models, `num_ctx`, and context budgets."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from ..config import DEFAULT_TELEMETRY_DB, ensure_telemetry_schema, load_cortical_config, save_cortical_config
from ..hardware.models import recommend_models_for_hardware
from ..hardware.probe import probe_hardware


def analyze_and_tune(
    *,
    config: Optional[dict[str, Any]] = None,
    hw: Optional[dict[str, Any]] = None,
    db_path: Path | str | None = None,
    apply_changes: bool = False,
    config_path: Optional[Path] = None,
) -> dict[str, Any]:
    """Inspects local telemetry & hardware fit and recommends or applies model/num_ctx/budget improvements."""
    cfg = config or load_cortical_config()
    hw_info = hw or probe_hardware(runners_probe=False)
    rec = recommend_models_for_hardware(hw_info, custom_models=cfg.get("custom_models"))

    target_db = Path(db_path or os.environ.get("CORTICAL_TELEMETRY_DB") or DEFAULT_TELEMETRY_DB)
    model_perf: dict[str, dict[str, Any]] = {}
    if target_db.is_file():
        with ensure_telemetry_schema(target_db) as conn:
            for r in conn.execute("SELECT model, elapsed_sec, total_tokens, status FROM agent_runs").fetchall():
                m = str(r["model"] or "unknown")
                slot = model_perf.setdefault(m, {"runs": 0, "tokens": 0, "elapsed": 0.0, "failures": 0})
                slot["runs"] += 1
                slot["tokens"] += int(r["total_tokens"] or 0)
                slot["elapsed"] += float(r["elapsed_sec"] or 0.0)
                if r["status"] != "completed":
                    slot["failures"] += 1

    rec_roles = rec.get("recommended_by_role") or {}
    daily = (rec_roles.get("daily_coder") or {}).get("model_id") or cfg.get("active_model")
    reasoner = (rec_roles.get("deep_reasoner") or {}).get("model_id") or daily
    eff_ctx = int((rec_roles.get("daily_coder") or {}).get("recommended_num_ctx") or 16384)
    max_share = float((cfg.get("compression") or {}).get("max_context_share") or 0.15)
    recommended_budget = max(256, int(eff_ctx * max_share))

    suggestions: list[str] = []
    if daily and daily != cfg.get("active_model"):
        suggestions.append(f"Set daily active_model -> `{daily}` (swap-safe for `{rec.get('tier')}` at `num_ctx={eff_ctx}`).")
    if reasoner and reasoner != (cfg.get("models_by_role") or {}).get("deep_reasoner"):
        suggestions.append(f"Assign deep_reasoner/orchestrator -> `{reasoner}` (variable quant fits RAM headroom).")
    for m_id, st in model_perf.items():
        avg_s = st["elapsed"] / max(1, st["runs"])
        if avg_s > 90.0 or st["failures"] > 0:
            suggestions.append(f"Local model `{m_id}` avg {avg_s:.1f}s ({st['failures']} failures): bound `num_ctx` to {min(eff_ctx, 16384)} or shift light steps to router model.")
    if not suggestions:
        suggestions.append(f"Configuration balanced for `{rec.get('tier')}`; memory injection capped at {recommended_budget} tokens ({int(max_share * 100)}% of {eff_ctx}).")

    applied = False
    if apply_changes:
        if daily:
            cfg["active_model"] = daily
        cfg.setdefault("models_by_role", {})
        for role_k, info in rec_roles.items():
            cfg["models_by_role"][role_k] = info["model_id"]
        save_cortical_config(cfg, config_path=config_path)
        applied = True

    return {
        "tier": rec.get("tier"),
        "applied": applied,
        "recommended_by_role": rec_roles,
        "recommended_context_budget_tokens": recommended_budget,
        "observed_model_stats": model_perf,
        "suggestions": suggestions,
    }
