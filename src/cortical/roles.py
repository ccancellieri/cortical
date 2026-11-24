"""Canonical Model Role Abstraction Registry & Resolver (Python 3.10+ stdlib only).

Eliminates hardcoded concrete model tags across CLI, MCP, LiteLLM router, 8 harnesses,
shared rule files (`AGENTS.md`, `GEMINI.md`, `CLAUDE.md`), Privacy Vault, and static UI.
"""

from __future__ import annotations

from typing import Any, Optional

MODEL_ROLES: dict[str, dict[str, Any]] = {
    "router": {
        "alias": "cortical-router",
        "label": "Fast Triage & Intent Router",
        "description": "Ultra-fast classification, intent routing, and lightweight JSON formatting (1-3 GB).",
        "fallbacks": ("fast_coder", "daily_coder"),
        "default_model": "qwen2.5:1.5b",
    },
    "ner": {
        "alias": "cortical-ner",
        "label": "Offline Privacy NER",
        "description": "Local JSON Named-Entity Recognition for PII & custom-term sanitization (1-3 GB).",
        "fallbacks": ("router", "fast_coder", "daily_coder"),
        "default_model": "qwen2.5:1.5b",
    },
    "fast_coder": {
        "alias": "cortical-fast",
        "label": "Fast Local Worker",
        "description": "Low-latency boilerplate edits, log parsing, test triage, and sub-task offload (3-6 GB).",
        "fallbacks": ("daily_coder", "router"),
        "default_model": "qwen3.5:9b-q3_k_xl",
    },
    "daily_coder": {
        "alias": "cortical-coder",
        "label": "Balanced Daily Coder",
        "description": "Daily coding, refactoring, tool calling, and long-context repository scans (5-8 GB).",
        "fallbacks": ("fast_coder", "deep_reasoner", "router"),
        "default_model": "qwen3.5:9b-q3_k_xl",
    },
    "reviewer": {
        "alias": "cortical-reviewer",
        "label": "Code & Diff Reviewer",
        "description": "PR diff critique, architectural invariant checks, and security review (5-9 GB).",
        "fallbacks": ("daily_coder", "deep_reasoner", "fast_coder"),
        "default_model": "qwen3.5:9b-q3_k_xl",
    },
    "summarizer": {
        "alias": "cortical-summarizer",
        "label": "Summarizer & Memory Distiller",
        "description": "Bulk file/log summarization, 3+1 Brain distillation, and ROI recaps (1.5-6 GB).",
        "fallbacks": ("fast_coder", "daily_coder", "router"),
        "default_model": "qwen2.5:1.5b",
    },
    "deep_reasoner": {
        "alias": "cortical-deep",
        "label": "Deep Reasoner & Architect",
        "description": "Multi-step debugging, architecture design, and variable-quant deep reasoning (7-16+ GB).",
        "fallbacks": ("orchestrator", "daily_coder"),
        "default_model": "qwen3.8:27b-iq2_xxs",
    },
    "orchestrator": {
        "alias": "cortical-orchestrator",
        "label": "Primary Orchestrator / Supervisor",
        "description": "Top-level coordinator across 8 harnesses (local deep model or remote cloud supervisor).",
        "fallbacks": ("deep_reasoner", "daily_coder"),
        "default_model": "qwen3.8:27b-iq2_xxs",
    },
    "vision": {
        "alias": "cortical-vision",
        "label": "Local Vision & OCR",
        "description": "Offline image OCR, scanned PDF extraction, and chart anonymization (2-6 GB).",
        "fallbacks": (),
        "default_model": "minicpm-ocr:latest",
    },
    "embedder": {
        "alias": "cortical-embed",
        "label": "Local Semantic Embedder",
        "description": "Optional local embeddings for workspace wiki retrieval and semantic search.",
        "fallbacks": (),
        "default_model": "nomic-embed-text",
    },
}

_ALIAS_TO_ROLE: dict[str, str] = {
    meta["alias"]: role for role, meta in MODEL_ROLES.items()
}
_ALIAS_TO_ROLE.update({
    "local-default": "daily_coder",
    "architect": "deep_reasoner",
    "ocr": "vision",
    "long_context": "daily_coder",
})


def role_for_alias(role_or_alias: str) -> Optional[str]:
    """Normalizes a role name (`daily_coder`), `@role:<name>`, or alias (`cortical-fast`) to a canonical role key."""
    raw = str(role_or_alias or "").strip().lower()
    if raw.startswith("@role:"):
        raw = raw[6:].strip()
    if raw in MODEL_ROLES:
        return raw
    return _ALIAS_TO_ROLE.get(raw)


def resolve_role_model(
    role_or_alias: str,
    config: Optional[dict[str, Any]] = None,
    *,
    rec_models: Optional[dict[str, Any]] = None,
    default: str = "",
) -> str:
    """Resolves a semantic role or alias to the user's configured or hardware-recommended concrete model ID."""
    cfg = config or {}
    by_role = cfg.get("models_by_role") or {}
    priv = cfg.get("privacy") or {}
    rec_by_role = (rec_models or {}).get("recommended_by_role") or {}

    canonical = role_for_alias(role_or_alias)
    if canonical is None:
        raw = str(role_or_alias or "").strip()
        return raw or default

    def _lookup_one(rkey: str) -> str:
        if rkey == "vision" and str(priv.get("vision_model") or "").strip():
            return str(priv["vision_model"]).strip()
        if rkey == "ner" and str(priv.get("ner_model") or "").strip():
            return str(priv["ner_model"]).strip()
        rec_entry = rec_by_role.get(rkey) or {}
        if rec_entry.get("installed") and str(rec_entry.get("model_id") or "").strip():
            return str(rec_entry["model_id"]).strip()
        if str(by_role.get(rkey) or "").strip():
            return str(by_role[rkey]).strip()
        if str(rec_entry.get("model_id") or "").strip():
            return str(rec_entry["model_id"]).strip()
        return ""

    direct = _lookup_one(canonical)
    if direct:
        return direct
    for fb in MODEL_ROLES[canonical]["fallbacks"]:
        found = _lookup_one(fb)
        if found:
            return found
    if canonical in {"fast_coder", "daily_coder", "reviewer"} and str(cfg.get("active_model") or "").strip():
        return str(cfg["active_model"]).strip()
    return default or str(MODEL_ROLES[canonical]["default_model"])


def resolve_all_roles(
    config: Optional[dict[str, Any]] = None,
    *,
    rec_models: Optional[dict[str, Any]] = None,
) -> dict[str, dict[str, Any]]:
    """Returns the complete role-to-model mapping table for CLI, MCP, router, and dashboard UI."""
    cfg = config or {}
    by_role = cfg.get("models_by_role") or {}
    priv = cfg.get("privacy") or {}
    rec_by_role = (rec_models or {}).get("recommended_by_role") or {}
    out: dict[str, dict[str, Any]] = {}
    for role, meta in MODEL_ROLES.items():
        resolved = resolve_role_model(role, cfg, rec_models=rec_models)
        if (role == "vision" and priv.get("vision_model")) or (role == "ner" and priv.get("ner_model")) or by_role.get(role):
            src = "config"
        elif (rec_by_role.get(role) or {}).get("model_id"):
            src = "recommended"
        else:
            src = "default"
        out[role] = {
            "role": role,
            "alias": meta["alias"],
            "label": meta["label"],
            "description": meta["description"],
            "model_id": resolved,
            "source": src,
        }
    return out


def normalize_role_or_model(
    value: Optional[str],
    config: Optional[dict[str, Any]] = None,
    *,
    default_role: str = "daily_coder",
    rec_models: Optional[dict[str, Any]] = None,
) -> str:
    """Resolves `@role:<name>`, canonical role key, or router alias to a concrete model ID; passes explicit model IDs through."""
    raw = str(value or "").strip()
    if not raw:
        return resolve_role_model(default_role, config, rec_models=rec_models)
    if role_for_alias(raw) is not None:
        return resolve_role_model(raw, config, rec_models=rec_models)
    return raw
