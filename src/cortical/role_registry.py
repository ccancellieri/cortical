"""Extensible Role & Capability Registry for Cortical Harness.

Centralizes model assignment, per-role context window budgets, effort levels,
and tool permissions across all Cortical subsystems (voice intent, memory
curation, browser automation, skill compilation, multi-agent swarm, and custom
user/plugin-defined roles).
"""

from __future__ import annotations

import dataclasses
from typing import Any, Optional

from .context_window import clamp_context_window, get_model_context_window


@dataclasses.dataclass
class RoleSpec:
    """Declarative specification for an operational role or tool handler."""

    role_id: str
    label: str
    description: str
    default_model: str
    default_context_window: int = 32768
    default_effort: str = "medium"
    tools: list[str] = dataclasses.field(default_factory=list)
    builtin: bool = True

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


DEFAULT_ROLE_SPECS: tuple[RoleSpec, ...] = (
    RoleSpec(
        role_id="coordinator",
        label="Coordinator",
        description="Orchestrazione task, sintesi finale e coordinamento team",
        default_model="qwen3.8:27b-iq2_xs",
        default_context_window=32768,
        default_effort="medium",
        tools=["read", "bash", "wiki_search", "wiki_navigate"],
    ),
    RoleSpec(
        role_id="analyst",
        label="Analyst",
        description="Ispezione codebase, ricerca e pianificazione",
        default_model="qwen3.8:27b-iq2_xs",
        default_context_window=32768,
        default_effort="medium",
        tools=["read", "grep", "find", "ls", "bash"],
    ),
    RoleSpec(
        role_id="implementer",
        label="Implementer",
        description="Modifica file, scrittura codice ed esecuzione comandi",
        default_model="qwen3.8:27b-iq2_xs",
        default_context_window=32768,
        default_effort="medium",
        tools=["read", "edit", "write", "bash", "grep", "find", "ls"],
    ),
    RoleSpec(
        role_id="reviewer",
        label="Reviewer",
        description="Verifica test, fact-check e controllo qualità",
        default_model="qwen3.8:27b-iq2_xs",
        default_context_window=32768,
        default_effort="medium",
        tools=["read", "bash", "wiki_verify_citation"],
    ),
    RoleSpec(
        role_id="chat",
        label="Chat Generale",
        description="Conversazione contestuale e Q&A sul Second Brain",
        default_model="qwen3.8:27b-iq2_xs",
        default_context_window=32768,
        default_effort="medium",
        tools=["wiki_search", "wiki_navigate"],
    ),
    RoleSpec(
        role_id="voice_intent",
        label="Voice Intent (System 1)",
        description="Interpretazione rapida della trascrizione audio e routing vocale",
        default_model="qwen2.5:1.5b",
        default_context_window=8192,
        default_effort="low",
        tools=["chrome_search", "chrome_read_page", "meteo_forecast"],
    ),
    RoleSpec(
        role_id="memory_curator",
        label="Memory Curator (3+1)",
        description="Sintesi a 4 livelli (L1-L3 +1), titoli brevi e compressione paragrafi",
        default_model="qwen3.8:27b-iq2_xs",
        default_context_window=16384,
        default_effort="low",
        tools=["wiki_record_episode", "wiki_upsert_concept"],
    ),
    RoleSpec(
        role_id="browser_agent",
        label="Browser Agent (Chrome)",
        description="Navigazione Chrome, compilazione form e sintesi pagine web",
        default_model="qwen3.8:27b-iq2_xs",
        default_context_window=16384,
        default_effort="medium",
        tools=["chrome_search", "chrome_read_page", "chrome-devtools"],
    ),
    RoleSpec(
        role_id="skill_compiler",
        label="Skill Compiler",
        description="Distillazione di skill procedurali riusabili da discussioni concluse",
        default_model="qwen3.8:27b-iq2_xs",
        default_context_window=16384,
        default_effort="low",
        tools=["wiki_create_research_doc"],
    ),
)


def get_all_roles(orch_cfg: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    """Returns built-in and user/plugin-registered roles with resolved model and context window."""
    cfg = orch_cfg if isinstance(orch_cfg, dict) else {}
    model_windows = cfg.get("model_context_windows") if isinstance(cfg.get("model_context_windows"), dict) else {}
    role_windows = cfg.get("role_context_windows") if isinstance(cfg.get("role_context_windows"), dict) else {}
    role_efforts = cfg.get("role_efforts") if isinstance(cfg.get("role_efforts"), dict) else {}
    custom_roles = cfg.get("custom_roles") if isinstance(cfg.get("custom_roles"), dict) else {}

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for spec in DEFAULT_ROLE_SPECS:
        seen.add(spec.role_id)
        cfg_key = f"{spec.role_id}_model"
        model_id = str(cfg.get(cfg_key) or spec.default_model).strip()
        win = clamp_context_window(
            role_windows.get(spec.role_id) or get_model_context_window(model_id, model_windows, fallback=spec.default_context_window),
            fallback=spec.default_context_window,
        )
        eff = str(role_efforts.get(spec.role_id) or spec.default_effort).strip().lower()
        if eff not in {"low", "medium", "high"}:
            eff = spec.default_effort
        out.append({
            "id": spec.role_id,
            "role_id": spec.role_id,
            "label": spec.label,
            "description": spec.description,
            "model": model_id,
            "context_window": win,
            "effort": eff,
            "tools": list(spec.tools),
            "builtin": True,
        })

    for rid, raw in custom_roles.items():
        if not isinstance(raw, dict) or rid in seen:
            continue
        clean_id = str(rid).strip().lower().replace(" ", "_")
        if not clean_id:
            continue
        model_id = str(cfg.get(f"{clean_id}_model") or raw.get("model") or "qwen3.8:27b-iq2_xs").strip()
        win = clamp_context_window(
            role_windows.get(clean_id) or raw.get("context_window") or get_model_context_window(model_id, model_windows),
            fallback=32768,
        )
        eff = str(role_efforts.get(clean_id) or raw.get("effort") or "medium").strip().lower()
        if eff not in {"low", "medium", "high"}:
            eff = "medium"
        tools = [str(t).strip() for t in (raw.get("tools") or []) if str(t).strip()]
        out.append({
            "id": clean_id,
            "role_id": clean_id,
            "label": str(raw.get("label") or clean_id.replace("_", " ").title()),
            "description": str(raw.get("description") or "Ruolo/Tool personalizzato"),
            "model": model_id,
            "context_window": win,
            "effort": eff,
            "tools": tools,
            "builtin": False,
        })
    return out


def add_custom_role(
    orch_cfg: Optional[dict[str, Any]],
    role_id: str,
    label: str = "",
    description: str = "",
    model: str = "qwen3.8:27b-iq2_xs",
    context_window: int = 16384,
    effort: str = "medium",
    tools: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Adds or updates a custom role in orchestrator config and returns updated dict."""
    clean_id = str(role_id or "").strip().lower().replace(" ", "_")
    if not clean_id or not all(c.isalnum() or c == "_" for c in clean_id):
        raise ValueError("Invalid role id (use lowercase letters, numbers, underscores)")
    if any(s.role_id == clean_id for s in DEFAULT_ROLE_SPECS):
        raise ValueError(f"Role '{clean_id}' is built-in and cannot be overwritten as custom")
    eff = str(effort or "medium").strip().lower()
    if eff not in {"low", "medium", "high"}:
        eff = "medium"
    cfg = dict(orch_cfg) if isinstance(orch_cfg, dict) else {}
    custom = dict(cfg.get("custom_roles") or {})
    custom[clean_id] = {
        "label": str(label or clean_id.replace("_", " ").title()).strip(),
        "description": str(description or "Ruolo/Tool personalizzato").strip(),
        "model": str(model or "qwen3.8:27b-iq2_xs").strip(),
        "context_window": clamp_context_window(context_window, fallback=16384),
        "effort": eff,
        "tools": [str(t).strip() for t in (tools or []) if str(t).strip()],
    }
    cfg["custom_roles"] = custom
    return cfg


def delete_custom_role(orch_cfg: Optional[dict[str, Any]], role_id: str) -> dict[str, Any]:
    """Removes a custom role from orchestrator config."""
    clean_id = str(role_id or "").strip().lower().replace(" ", "_")
    if any(s.role_id == clean_id for s in DEFAULT_ROLE_SPECS):
        raise ValueError(f"Cannot delete built-in role '{clean_id}'")
    cfg = dict(orch_cfg) if isinstance(orch_cfg, dict) else {}
    custom = dict(cfg.get("custom_roles") or {})
    if clean_id not in custom:
        raise ValueError(f"Custom role '{clean_id}' not found")
    custom.pop(clean_id, None)
    cfg["custom_roles"] = custom
    return cfg


def resolve_role_execution(orch_cfg: Optional[dict[str, Any]], role_id: str) -> dict[str, Any]:
    """Resolves model, context window, effort, and tools for a given role_id."""
    rid = str(role_id or "coordinator").strip().lower()
    for r in get_all_roles(orch_cfg):
        if r["role_id"] == rid:
            return r
    return {
        "id": rid,
        "role_id": rid,
        "label": rid.title(),
        "description": "Ruolo dinamico",
        "model": str((orch_cfg or {}).get("coordinator_model") or "qwen3.8:27b-iq2_xs"),
        "context_window": 32768,
        "effort": "medium",
        "tools": ["read", "bash"],
        "builtin": False,
    }
