"""Self-Curating `SKILL.md` Workflows (#1) & Bidirectional `MEMORY.md` Sync (#3).

100% clean-room Apache-2.0, Python 3.10+ stdlib only, zero-PII verified.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from ..compression.engine import fit_to_token_budget
from ..config import DEFAULT_VAULT_DB, default_data_dir, invoke_configured_runner, load_cortical_config
from ..roles import resolve_role_model
from .sanitizer import pseudonymize_structured
from .vault import PrivacyVault, _verify_zero_residual_pii

_MEM_START = "<!-- CORTICAL-MEMORY:START -->"
_MEM_END = "<!-- CORTICAL-MEMORY:END -->"


def _upsert_block(existing: str, block_body: str, start: str, end: str) -> str:
    body = f"{start}\n{block_body.rstrip()}\n{end}\n"
    if start in existing and end in existing:
        before, _, rest = existing.partition(start)
        _, _, after = rest.partition(end)
        tail = after.lstrip("\n")
        return before + body + (("\n" + tail) if tail else "")
    prefix = existing.rstrip() + "\n\n" if existing.strip() else ""
    return prefix + body


def _strip_block(text: str, start: str, end: str) -> str:
    if start not in text or end not in text:
        return text.strip()
    before, _, rest = text.partition(start)
    _, _, after = rest.partition(end)
    return (before.rstrip() + "\n\n" + after.lstrip()).strip()


def _safe_text(text: str, custom_terms: Optional[list[str]] = None) -> str:
    """Guarantees zero residual PII/secrets before exporting to versioned Markdown files."""
    if not text:
        return ""
    if _verify_zero_residual_pii(text, custom_terms):
        masked, _ = pseudonymize_structured(text, redact=False, custom_terms=custom_terms)
        return masked
    return text


def curate_skills_from_memory(
    *,
    vault_db: Optional[Path | str] = None,
    skills_dir: Optional[Path | str] = None,
    handoff_path: Optional[Path | str] = None,
    use_local_llm: bool = False,
    config: Optional[dict[str, Any]] = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Compiles verified procedural workflows from LocalBrain & handoff into `.agents/skills/cortical-self-curated/SKILL.md`."""
    cfg = config if config is not None else load_cortical_config()
    terms = list((cfg.get("privacy") or {}).get("custom_terms") or []) or None
    v_db = Path(vault_db or DEFAULT_VAULT_DB)
    s_root = Path(skills_dir or (Path.cwd() / ".agents" / "skills"))
    target = s_root / "cortical-self-curated" / "SKILL.md"

    skills_entries: list[dict[str, str]] = []
    if v_db.is_file():
        vault = PrivacyVault(v_db)
        snap = vault.brain.get_snapshot(include_local_only=False)
        for sk in (snap.get("by_skill") or snap.get("skills") or []):
            title = _safe_text(str(sk.get("title") or "").strip(), terms)
            proc = _safe_text(str(sk.get("procedure_md") or sk.get("procedure") or "").strip(), terms)
            if title and proc:
                skills_entries.append({"title": title, "procedure": proc})

    h_path = Path(handoff_path or (default_data_dir() / "brain" / "handoff.json"))
    handoff_note = ""
    if h_path.is_file():
        try:
            hd = json.loads(h_path.read_text(encoding="utf-8"))
            goal = _safe_text(str(hd.get("goal") or "").strip(), terms)
            summary = _safe_text(str(hd.get("summary") or "").strip(), terms)
            if goal or summary:
                handoff_note = f"- **Latest Verified Goal:** {goal}\n- **Distilled Outcome:** {summary}"
        except Exception:  # noqa: BLE001
            pass

    lines = [
        "---",
        "name: cortical-self-curated",
        "description: Auto-curated zero-PII workflows and role-abstracted guardrails distilled from Cortical LocalBrain and verified sessions.",
        "---",
        "",
        "# Cortical Self-Curated Workflows",
        "",
        "## Core Role-Abstracted Operating Rules",
        "- Never hardcode concrete model tags in prompts or scripts; use semantic roles (`@role:router`, `@role:ner`, `@role:fast_coder`, `@role:daily_coder`, `@role:reviewer`, `@role:summarizer`, `@role:deep_reasoner`, `@role:orchestrator`, `@role:vision`).",
        "- Offload bulk summaries, diff reviews, and private vault analysis locally via `cortical_local_offload(role=...)`.",
        "- Compress large structured JSON/logs via `cortical_compress` (`TOON`) before passing state to a remote supervisor.",
        "- Protect official `server.json` & `glama.json` manifests and run `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q` before committing.",
    ]

    if handoff_note:
        lines.extend(["", "## Recent Verified Session Pattern", handoff_note])

    if skills_entries:
        lines.extend(["", "## Distilled LocalBrain Procedures"])
        for entry in skills_entries[:12]:
            lines.extend(["", f"### {entry['title']}", entry["procedure"]])

    content = "\n".join(lines).rstrip() + "\n"
    if use_local_llm and skills_entries:
        try:
            model_id = resolve_role_model("summarizer", cfg)
            refined = invoke_configured_runner(
                f"Tighten these curated agent skill procedures into concise, imperative Markdown bullets (keep YAML frontmatter intact):\n\n{content[:4000]}",
                system_prompt="Return clean Markdown only. Never introduce PII or hardcoded model tags.",
                config=cfg,
                model_override=model_id,
                max_tokens=700,
                timeout=30.0,
                role="skill_curation",
            )
            if refined and refined.strip().startswith("---") and not _verify_zero_residual_pii(refined, terms):
                content = refined.strip() + "\n"
        except Exception:  # noqa: BLE001
            pass

    old = target.read_text(encoding="utf-8") if target.is_file() else None
    action = "create" if old is None else ("unchanged" if old == content else "update")
    if not dry_run and action != "unchanged":
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    return {
        "path": str(target),
        "action": action,
        "skills_count": len(skills_entries),
        "handoff_included": bool(handoff_note),
        "dry_run": dry_run,
    }


def sync_memory_markdown(
    *,
    vault_db: Optional[Path | str] = None,
    memory_path: Optional[Path | str] = None,
    direction: str = "export",
    num_ctx: int = 65536,
    max_share: float = 0.15,
    config: Optional[dict[str, Any]] = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Bidirectional zero-PII sync between Cortical LocalBrain L1/L2 and human-readable `MEMORY.md`."""
    cfg = config if config is not None else load_cortical_config()
    terms = list((cfg.get("privacy") or {}).get("custom_terms") or []) or None
    v_db = Path(vault_db or DEFAULT_VAULT_DB)
    m_path = Path(memory_path or (Path.cwd() / "MEMORY.md"))
    dir_norm = str(direction or "export").strip().lower()

    vault = PrivacyVault(v_db)
    imported_notes = False
    exported_concepts = 0
    action = "unchanged"

    if dir_norm in {"import", "both"} and m_path.is_file():
        human_notes = _strip_block(m_path.read_text(encoding="utf-8"), _MEM_START, _MEM_END)
        # Ignore trivial headers-only content
        cleaned = re.sub(r"(?m)^#.*$", "", human_notes).strip()
        if cleaned and not dry_run:
            vault.ingest(
                human_notes,
                alias="memory_md_notes",
                policy="auto",
                profile="medium",
                custom_terms=terms,
                config=cfg,
                task_tags=["memory", "notes"],
            )
            imported_notes = True

    if dir_norm in {"export", "both"}:
        snap = vault.brain.get_snapshot(include_local_only=False)
        blocks: list[dict[str, Any]] = []
        for idx, c in enumerate(snap.get("by_concept") or snap.get("concepts") or []):
            title = _safe_text(str(c.get("title") or c.get("slug") or c.get("concept_id") or "Concept"), terms)
            summary = _safe_text(str(c.get("summary") or ""), terms)
            kws = ", ".join(str(k) for k in (c.get("keywords") or [])[:8])
            if summary:
                blocks.append({
                    "alias": str(c.get("slug") or c.get("concept_id") or f"c_{idx}"),
                    "title": f"{title} ({kws})" if kws else title,
                    "content": summary,
                    "priority": 100 - idx,
                })
        exported_concepts = len(blocks)
        sized = fit_to_token_budget(blocks, num_ctx=num_ctx, max_share=max_share) if blocks else {"used_tokens": 0, "budget_tokens": int(num_ctx * max_share), "markdown": "_No chat-safe L1/L2 concepts distilled yet._"}
        block_body = (
            "## Cortical Consolidated Memory (L1/L2 — Zero Cloud PII)\n"
            f"_Synced from LocalBrain · Budget: {sized['used_tokens']}/{sized['budget_tokens']} tok · `max_security` items excluded._\n\n"
            + sized["markdown"]
        )
        old = m_path.read_text(encoding="utf-8") if m_path.is_file() else "# Project Memory\n"
        updated = _upsert_block(old, block_body, _MEM_START, _MEM_END)
        action = "create" if not m_path.is_file() else ("unchanged" if old == updated else "update")
        if not dry_run and action != "unchanged":
            m_path.parent.mkdir(parents=True, exist_ok=True)
            m_path.write_text(updated, encoding="utf-8")

    return {
        "path": str(m_path),
        "direction": dir_norm,
        "action": action,
        "exported_concepts": exported_concepts,
        "imported_notes": imported_notes,
        "dry_run": dry_run,
    }
