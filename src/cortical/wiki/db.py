"""Relational & Hierarchical Second Brain Storage (SQLite WAL + FTS5 + RBAC + Macro-Graph).

Solves the 5 Knowledge Base Pillars:
1. Parallel Indexing with Hierarchical Summaries (`light`, `medium`, `high`, `max`).
2. Fact-Checking Ledger (`citations` table with deterministic span + NLI decision gate).
3. Multi-Tenancy (`tenant_id`, `workspace_id` isolation ready for cloud PostgreSQL sync).
4. Scalability (`merkle_nodes` tree + high-level `task_episodes` / `macro_edges` graph).
5. Relational Permissions (`acl_permissions` enforced in SQL queries).
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import sqlite3
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterator, Optional


class DepthTier(str, Enum):
    LIGHT = "light"    # ~50 tokens: compact index & one-line capability summary
    MEDIUM = "medium"  # ~250 tokens: executive summary & key structural facts
    HIGH = "high"      # ~1000 tokens: detailed architecture, claims, metrics, APIs
    MAX = "max"        # Full raw document / source code for specialized deep work


SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS tenants (
    tenant_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS workspaces (
    workspace_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    name TEXT NOT NULL,
    root_path TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (tenant_id, workspace_id),
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS acl_permissions (
    permission_id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    principal_id TEXT NOT NULL,
    path_prefix TEXT NOT NULL DEFAULT '/',
    can_read INTEGER NOT NULL DEFAULT 1,
    can_write INTEGER NOT NULL DEFAULT 0,
    UNIQUE(tenant_id, workspace_id, principal_id, path_prefix)
);

CREATE TABLE IF NOT EXISTS merkle_nodes (
    tenant_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    path TEXT NOT NULL,
    parent_path TEXT,
    node_type TEXT NOT NULL CHECK(node_type IN ('file', 'dir')),
    content_hash TEXT NOT NULL,
    subtree_hash TEXT NOT NULL,
    summary_light TEXT NOT NULL,
    summary_medium TEXT NOT NULL,
    summary_high TEXT NOT NULL,
    raw_content TEXT,
    token_estimate INTEGER NOT NULL DEFAULT 0,
    updated_at REAL NOT NULL,
    PRIMARY KEY (tenant_id, workspace_id, path)
);

CREATE INDEX IF NOT EXISTS idx_merkle_parent
    ON merkle_nodes(tenant_id, workspace_id, parent_path);

CREATE VIRTUAL TABLE IF NOT EXISTS merkle_fts USING fts5(
    tenant_id UNINDEXED,
    workspace_id UNINDEXED,
    path,
    summary_light,
    summary_medium,
    summary_high,
    raw_content
);

CREATE TABLE IF NOT EXISTS task_episodes (
    episode_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    title TEXT NOT NULL,
    goal TEXT NOT NULL,
    outcome_status TEXT NOT NULL,
    learned_summary TEXT NOT NULL,
    skills_used TEXT NOT NULL DEFAULT '[]',
    created_at REAL NOT NULL,
    PRIMARY KEY (tenant_id, workspace_id, episode_id)
);

CREATE TABLE IF NOT EXISTS macro_edges (
    edge_id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK(source_type IN ('episode', 'subtree')),
    source_id TEXT NOT NULL,
    relation TEXT NOT NULL CHECK(relation IN (
        'relates_to', 'derived_from', 'modifies', 'supersedes', 'contradicts', 'depends_on'
    )),
    target_type TEXT NOT NULL CHECK(target_type IN ('episode', 'subtree')),
    target_id TEXT NOT NULL,
    weight REAL NOT NULL DEFAULT 1.0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL,
    UNIQUE(tenant_id, workspace_id, source_type, source_id, relation, target_type, target_id)
);

CREATE TABLE IF NOT EXISTS citations (
    citation_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    claim_text TEXT NOT NULL,
    source_path TEXT NOT NULL,
    quoted_span TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    span_verified INTEGER NOT NULL,
    nli_label TEXT NOT NULL,
    nli_confidence REAL NOT NULL,
    verdict TEXT NOT NULL CHECK(verdict IN ('verified', 'refuted', 'unverified')),
    checked_at REAL NOT NULL,
    PRIMARY KEY (tenant_id, workspace_id, citation_id)
);

CREATE TABLE IF NOT EXISTS framework_concept_configs (
    tenant_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    concept_id TEXT NOT NULL,
    config_json TEXT NOT NULL DEFAULT '{}',
    updated_at REAL NOT NULL,
    PRIMARY KEY (tenant_id, workspace_id, concept_id)
);

CREATE TABLE IF NOT EXISTS deleted_concepts (
    tenant_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    concept_id TEXT NOT NULL,
    deleted_at REAL NOT NULL,
    PRIMARY KEY (tenant_id, workspace_id, concept_id)
);

CREATE TABLE IF NOT EXISTS scoped_context_attachments (
    attachment_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    scope_id TEXT NOT NULL DEFAULT 'chat',
    item_type TEXT NOT NULL CHECK(item_type IN ('file', 'folder', 'skill', 'plugin')),
    item_ref TEXT NOT NULL,
    label TEXT NOT NULL,
    depth_tier TEXT NOT NULL DEFAULT 'medium',
    summary_preview TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL,
    UNIQUE(tenant_id, workspace_id, scope_id, item_type, item_ref)
);
"""


DEFAULT_FRAMEWORK_CONCEPTS: dict[str, dict[str, Any]] = {
    "concept:cortical-second-brain": {
        "key": "cortical-second-brain",
        "label": "Cortical Second Brain",
        "kind": "hub",
        "category": "memoria",
        "summary": "Nucleo semantico 3+1 livelli (Light, Medium, High, Max) con Contesto Allegato, Grafo dei Concetti, Voce Dual-Path e Orchestratore Multi-Agente.",
        "summary_medium": "Architettura cognitiva locale che separa la memoria strutturata a 3+1 livelli dalle capacità procedurali (Skill) e carica nel contesto solo file, cartelle, skill e plugin esplicitamente allegati.",
        "default_config": {
            "default_wiki_depth": "medium",
            "auto_attach_chat_context": True,
            "strict_source_isolation": True,
        },
        "config_schema": [
            {"key": "default_wiki_depth", "label": "Livello Sintesi Default (3+1)", "type": "select", "options": ["light", "medium", "high", "max"]},
            {"key": "auto_attach_chat_context", "label": "Inietta Contesto Allegato nel Prompt", "type": "boolean"},
            {"key": "strict_source_isolation", "label": "Isola Sorgenti Non Allegate", "type": "boolean"},
        ],
    },
    "concept:orchestratore-multi-agente": {
        "key": "orchestratore-multi-agente",
        "label": "Orchestratore Multi-Agente",
        "kind": "concept",
        "category": "agenti",
        "summary": "Coordinamento su richiesta tra Analyst, Implementer e Reviewer con numero massimo di loop, modelli dedicati per ruolo e isolamento di task.",
        "summary_medium": "Gestisce il ciclo multi-agente su richiesta esplicita: permette di configurare quanti loop massimi gli agenti eseguono e quali modelli LLM usare per Analyst, Implementer e Reviewer.",
        "default_config": {
            "max_agent_loops": 6,
            "analyst_model": "qwen2.5:1.5b",
            "implementer_model": "qwen2.5:1.5b",
            "reviewer_model": "qwen2.5:1.5b",
            "llm_base_url": "http://127.0.0.1:11434/v1",
            "auto_compile_skills_on_close": True,
        },
        "config_schema": [
            {"key": "max_agent_loops", "label": "Loop Massimi Agenti (Max Iterations)", "type": "number", "min": 1, "max": 30},
            {"key": "analyst_model", "label": "Modello Ruolo Analyst (Ricerca & Piano)", "type": "text"},
            {"key": "implementer_model", "label": "Modello Ruolo Implementer (Codice & Azione)", "type": "text"},
            {"key": "reviewer_model", "label": "Modello Ruolo Reviewer (Verifica & Test)", "type": "text"},
            {"key": "llm_base_url", "label": "Endpoint OpenAI/Ollama Locale", "type": "text"},
            {"key": "auto_compile_skills_on_close", "label": "Compila Skill Automatica a Chiusura Task", "type": "boolean"},
        ],
    },
    "concept:memoria-3plus1-merkle": {
        "key": "memoria-3plus1-merkle",
        "label": "Memoria 3+1 Livelli",
        "kind": "concept",
        "category": "memoria",
        "summary": "Sintesi gerarchica deterministica: L1 Light (~50 tok), L2 Medium (~250 tok), L3 High (~1000 tok), +1 Max integrale con filtro chiacchierate.",
        "summary_medium": "Comprime file e cartelle allegate in 3 livelli di sintesi più il testo integrale (+1 Max) e mantiene il buffer conversazionale entro una finestra FIFO controllata.",
        "default_config": {
            "default_wiki_depth": "medium",
            "max_chat_buffer_turns": 20,
            "filter_ephemeral_chitchat": True,
            "ask_closing_questions": True,
        },
        "config_schema": [
            {"key": "default_wiki_depth", "label": "Profondità Default Sintesi 3+1", "type": "select", "options": ["light", "medium", "high", "max"]},
            {"key": "max_chat_buffer_turns", "label": "Max Turni Buffer Chiacchierate (FIFO)", "type": "number", "min": 5, "max": 100},
            {"key": "filter_ephemeral_chitchat", "label": "Filtra Domande Effimere (Ora/Meteo/Saluti)", "type": "boolean"},
            {"key": "ask_closing_questions", "label": "Domande di Consolidamento a Chiusura Task", "type": "boolean"},
        ],
    },
    "concept:voce-neurale-anti-eco": {
        "key": "voce-neurale-anti-eco",
        "label": "Voce Neurale & Scudo Anti-Eco",
        "kind": "concept",
        "category": "voce",
        "summary": "Sintesi vocale espressiva italiana con isolamento half-duplex dell'eco degli altoparlanti, audio ducking e barge-in con wake-word.",
        "summary_medium": "Impedisce all'assistente di ascoltare la propria voce dagli altoparlanti, modula la prosodia italiana e permette l'interruzione vocale controllata.",
        "default_config": {
            "default_voice": "IsabellaNeural",
            "speech_rate": "+4%",
            "echo_shield_cooldown_sec": 2.2,
            "require_wake_word_during_speech": True,
        },
        "config_schema": [
            {"key": "default_voice", "label": "Voce Neurale Predefinita", "type": "select", "options": ["IsabellaNeural", "GiuseppeNeural", "ElsaNeural", "DiegoNeural", "Federica"]},
            {"key": "speech_rate", "label": "Velocità Prosodia (es. +4%)", "type": "text"},
            {"key": "echo_shield_cooldown_sec", "label": "Finestra Scudo Anti-Eco (secondi)", "type": "number", "min": 0.5, "max": 10.0},
            {"key": "require_wake_word_during_speech", "label": "Richiedi 'Hey Cortical' durante Risposta", "type": "boolean"},
        ],
    },
    "concept:adaptive-permission-gate": {
        "key": "adaptive-permission-gate",
        "label": "Adaptive Permission Gate",
        "kind": "concept",
        "category": "sicurezza",
        "summary": "Guardrail deterministici contro comandi distruttivi, prevenzione furto focus finestra e apprendimento progressivo dei pattern approvati.",
        "summary_medium": "Valuta ogni comando di sistema prima dell'esecuzione, blocca pattern distruttivi e promuove ad auto-approvati i comandi sicuri confermati dall'utente.",
        "default_config": {
            "security_mode": "adaptive",
            "auto_approve_threshold": 2,
            "block_focus_stealing": True,
        },
        "config_schema": [
            {"key": "security_mode", "label": "Modalità Gate Sicurezza", "type": "select", "options": ["adaptive", "strict"]},
            {"key": "auto_approve_threshold", "label": "Soglia Conferme per Auto-Approvazione", "type": "number", "min": 1, "max": 10},
            {"key": "block_focus_stealing", "label": "Prevenzione Furto Focus Finestre GUI", "type": "boolean"},
        ],
    },
    "concept:ai-reviewer-mandate-complexity": {
        "key": "ai-reviewer-mandate-complexity",
        "label": "Mandato Reviewer & Metriche",
        "kind": "concept",
        "category": "agenti",
        "summary": "Mandato di revisione per codice AI e metriche oggettive: Cyclomatic < 10, Cognitive < 15, LOC < 50. Previene debito tecnico e over-generation.",
        "summary_medium": "Sposta il mandato da 'cattura bug ovvi' a 'verifica correttezza per la codebase, a questa scala e per il business'. Impedisce di saltare la review perché il codice sembra pulito.",
        "default_config": {
            "max_cyclomatic_complexity": 10,
            "max_cognitive_complexity": 15,
            "max_function_loc": 50,
            "enforce_strict_metrics": True,
        },
        "config_schema": [
            {"key": "max_cyclomatic_complexity", "label": "Soglia Massima Complessità Ciclica", "type": "number", "min": 5, "max": 25},
            {"key": "max_cognitive_complexity", "label": "Soglia Massima Complessità Cognitiva", "type": "number", "min": 5, "max": 30},
            {"key": "max_function_loc", "label": "Righe di Codice Massime per Funzione (LOC)", "type": "number", "min": 20, "max": 100},
            {"key": "enforce_strict_metrics", "label": "Blocca Funzioni Fuori Soglia", "type": "boolean"},
        ],
    },
    "concept:pr-contract-diff-constrainer": {
        "key": "pr-contract-diff-constrainer",
        "label": "Contratti PR & Diff Cap",
        "kind": "concept",
        "category": "architettura",
        "summary": "Vincoli di dimensione review per codice AI (diff max 250 righe, 3-5 file) e Golden Rule: la contribuzione deve valere più del tempo di review.",
        "summary_medium": "Forza una conversazione quando la PR supera la soglia ('questo potrebbe essere 3 PR'), impone verbi imperativi nei titoli, validazione del ticket collegato e pair programming.",
        "default_config": {
            "max_diff_lines": 250,
            "max_files_touched": 5,
            "require_linked_issue_assessment": True,
            "encourage_pair_programming": True,
        },
        "config_schema": [
            {"key": "max_diff_lines", "label": "Limite Righe Diff per PR (Diff Cap)", "type": "number", "min": 50, "max": 600},
            {"key": "max_files_touched", "label": "Massimo File Modificati per PR", "type": "number", "min": 1, "max": 15},
            {"key": "require_linked_issue_assessment", "label": "Verifica Obbligatoria Ticket Collegato", "type": "boolean"},
            {"key": "encourage_pair_programming", "label": "Suggerisci Pair Programming su PR Complesse", "type": "boolean"},
        ],
    },
    "concept:agent-instructions-alignment": {
        "key": "agent-instructions-alignment",
        "label": "Allineamento Zero-Drift (AGENTS.md)",
        "kind": "concept",
        "category": "architettura",
        "summary": "Single Artifact: il file di istruzioni per l'agente (AGENTS.md) è lo stesso standard di review. Zero drift ed eliminazione dei prompt ripetitivi.",
        "summary_medium": "Mantiene file esterni condivisi per standardizzare cosa sa l'AI sulle norme del team tra diverse sessioni di chat, prevenendo output inconsistenti tra sviluppatori.",
        "default_config": {
            "rules_file": "AGENTS.md",
            "zero_drift_review_standard": True,
            "standardize_team_norms": True,
        },
        "config_schema": [
            {"key": "rules_file", "label": "File Regole Condivise (es. AGENTS.md)", "type": "text"},
            {"key": "zero_drift_review_standard", "label": "Zero-Drift: Istruzioni Agente = Standard Review", "type": "boolean"},
            {"key": "standardize_team_norms", "label": "Standardizza Norme Team tra Sessioni", "type": "boolean"},
        ],
    },
}


@dataclass
class AccessContext:
    tenant_id: str = "default"
    workspace_id: str = "main"
    principal_id: str = "local_owner"


class CorticalWikiDB:
    """Thread-safe SQLite WAL engine for the 4-Tier Merkle Tree & Episode Macro-Graph."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextlib.contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA_SQL)

    def ensure_workspace(
        self,
        ctx: AccessContext,
        root_path: str = "/",
        can_write: bool = True,
    ) -> None:
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO tenants(tenant_id, name, created_at) VALUES (?, ?, ?)",
                (ctx.tenant_id, ctx.tenant_id, now),
            )
            conn.execute(
                """INSERT OR IGNORE INTO workspaces(workspace_id, tenant_id, name, root_path, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (ctx.workspace_id, ctx.tenant_id, ctx.workspace_id, root_path, now),
            )
            conn.execute(
                """INSERT OR REPLACE INTO acl_permissions(
                       tenant_id, workspace_id, principal_id, path_prefix, can_read, can_write
                   ) VALUES (?, ?, ?, '/', 1, ?)""",
                (ctx.tenant_id, ctx.workspace_id, ctx.principal_id, 1 if can_write else 0),
            )

    def grant_permission(
        self,
        tenant_id: str,
        workspace_id: str,
        principal_id: str,
        path_prefix: str,
        can_read: bool = True,
        can_write: bool = False,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO acl_permissions(
                       tenant_id, workspace_id, principal_id, path_prefix, can_read, can_write
                   ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    tenant_id,
                    workspace_id,
                    principal_id,
                    path_prefix,
                    1 if can_read else 0,
                    1 if can_write else 0,
                ),
            )

    def check_access(self, ctx: AccessContext, target_path: str, write: bool = False) -> bool:
        """Relational ACL check: finds the most specific matching path_prefix rule for principal."""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT path_prefix, can_read, can_write
                   FROM acl_permissions
                   WHERE tenant_id = ? AND workspace_id = ? AND principal_id = ?
                   ORDER BY LENGTH(path_prefix) DESC""",
                (ctx.tenant_id, ctx.workspace_id, ctx.principal_id),
            ).fetchall()
        for row in rows:
            prefix = row["path_prefix"]
            if target_path == prefix or target_path.startswith(prefix.rstrip("/") + "/") or prefix == "/":
                return bool(row["can_write"] if write else row["can_read"])
        return False

    def upsert_merkle_node(
        self,
        ctx: AccessContext,
        *,
        path: str,
        parent_path: Optional[str],
        node_type: str,
        content_hash: str,
        subtree_hash: str,
        summary_light: str,
        summary_medium: str,
        summary_high: str,
        raw_content: Optional[str] = None,
    ) -> None:
        if not self.check_access(ctx, path, write=True):
            raise PermissionError(f"Principal '{ctx.principal_id}' lacks write access to '{path}'")
        now = time.time()
        token_est = len((raw_content or summary_high).split())
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO merkle_nodes(
                       tenant_id, workspace_id, path, parent_path, node_type,
                       content_hash, subtree_hash, summary_light, summary_medium,
                       summary_high, raw_content, token_estimate, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    ctx.tenant_id,
                    ctx.workspace_id,
                    path,
                    parent_path,
                    node_type,
                    content_hash,
                    subtree_hash,
                    summary_light,
                    summary_medium,
                    summary_high,
                    raw_content,
                    token_est,
                    now,
                ),
            )
            conn.execute(
                "DELETE FROM merkle_fts WHERE tenant_id = ? AND workspace_id = ? AND path = ?",
                (ctx.tenant_id, ctx.workspace_id, path),
            )
            conn.execute(
                """INSERT INTO merkle_fts(
                       tenant_id, workspace_id, path, summary_light, summary_medium, summary_high, raw_content
                   ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    ctx.tenant_id,
                    ctx.workspace_id,
                    path,
                    summary_light,
                    summary_medium,
                    summary_high,
                    raw_content or "",
                ),
            )

    def get_node_hash(self, ctx: AccessContext, path: str) -> Optional[tuple[str, str]]:
        """Returns (content_hash, subtree_hash) if node exists and is readable."""
        if not self.check_access(ctx, path, write=False):
            return None
        with self._connect() as conn:
            row = conn.execute(
                """SELECT content_hash, subtree_hash FROM merkle_nodes
                   WHERE tenant_id = ? AND workspace_id = ? AND path = ?""",
                (ctx.tenant_id, ctx.workspace_id, path),
            ).fetchone()
            return (row["content_hash"], row["subtree_hash"]) if row else None

    def navigate(
        self,
        ctx: AccessContext,
        path: str = "/",
        depth: DepthTier | str = DepthTier.LIGHT,
        include_children: bool = True,
    ) -> dict[str, Any]:
        """Deterministic tree navigation at requested synthesis depth (`light`, `medium`, `high`, `max`)."""
        tier = DepthTier(depth)
        if not self.check_access(ctx, path, write=False):
            raise PermissionError(f"Principal '{ctx.principal_id}' lacks read access to '{path}'")

        with self._connect() as conn:
            node = conn.execute(
                """SELECT * FROM merkle_nodes
                   WHERE tenant_id = ? AND workspace_id = ? AND path = ?""",
                (ctx.tenant_id, ctx.workspace_id, path),
            ).fetchone()
            if not node:
                raise KeyError(f"Wiki path not found: {path}")

            children_rows = []
            if include_children:
                children_rows = conn.execute(
                    """SELECT path, node_type, subtree_hash, summary_light, summary_medium
                       FROM merkle_nodes
                       WHERE tenant_id = ? AND workspace_id = ? AND parent_path = ?
                       ORDER BY node_type ASC, path ASC""",
                    (ctx.tenant_id, ctx.workspace_id, path),
                ).fetchall()

            related_edges = conn.execute(
                """SELECT source_type, source_id, relation, target_type, target_id, weight
                   FROM macro_edges
                   WHERE tenant_id = ? AND workspace_id = ?
                     AND ((source_type = 'subtree' AND source_id = ?)
                          OR (target_type = 'subtree' AND target_id = ?))
                   ORDER BY weight DESC LIMIT 15""",
                (ctx.tenant_id, ctx.workspace_id, path, path),
            ).fetchall()

        payload = self._project_tier(dict(node), tier)
        payload["children"] = [
            {
                "path": c["path"],
                "node_type": c["node_type"],
                "subtree_hash": c["subtree_hash"],
                "summary": c["summary_light"] if tier == DepthTier.LIGHT else c["summary_medium"],
            }
            for c in children_rows
            if self.check_access(ctx, c["path"], write=False)
        ]
        payload["macro_relations"] = [dict(e) for e in related_edges]
        return payload

    def _project_tier(self, row: dict[str, Any], tier: DepthTier) -> dict[str, Any]:
        base: dict[str, Any] = {
            "path": row["path"],
            "parent_path": row["parent_path"],
            "node_type": row["node_type"],
            "content_hash": row["content_hash"],
            "subtree_hash": row["subtree_hash"],
            "depth_tier": tier.value,
        }
        if tier == DepthTier.LIGHT:
            base["content"] = row["summary_light"]
        elif tier == DepthTier.MEDIUM:
            base["content"] = row["summary_medium"]
            base["summary_light"] = row["summary_light"]
        elif tier == DepthTier.HIGH:
            base["content"] = row["summary_high"]
            base["summary_medium"] = row["summary_medium"]
        elif tier == DepthTier.MAX:
            base["content"] = row["raw_content"] or row["summary_high"]
            base["summary_high"] = row["summary_high"]
        return base

    def search(
        self,
        ctx: AccessContext,
        query: str,
        depth: DepthTier | str = DepthTier.MEDIUM,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """FTS5 search filtered by relational RBAC permissions and projected to requested depth tier."""
        tier = DepthTier(depth)
        safe_tokens = [t for t in query.replace('"', " ").split() if t.isalnum() or "_" in t]
        fts_query = " OR ".join(f'"{t}"' for t in safe_tokens) if safe_tokens else f'"{query}"'
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT m.*
                   FROM merkle_fts f
                   JOIN merkle_nodes m
                     ON m.tenant_id = f.tenant_id
                    AND m.workspace_id = f.workspace_id
                    AND m.path = f.path
                   WHERE f.tenant_id = ? AND f.workspace_id = ?
                     AND merkle_fts MATCH ?
                   ORDER BY rank
                   LIMIT ?""",
                (ctx.tenant_id, ctx.workspace_id, fts_query, limit * 2),
            ).fetchall()

        results: list[dict[str, Any]] = []
        for r in rows:
            if self.check_access(ctx, r["path"], write=False):
                results.append(self._project_tier(dict(r), tier))
                if len(results) >= limit:
                    break
        return results

    def record_episode(
        self,
        ctx: AccessContext,
        *,
        episode_id: str,
        title: str,
        goal: str,
        outcome_status: str,
        learned_summary: str,
        skills_used: list[str] | None = None,
        relations: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Logs a completed agentic task episode and links it in the High-Level Macro-Graph."""
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO task_episodes(
                       episode_id, tenant_id, workspace_id, title, goal,
                       outcome_status, learned_summary, skills_used, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    episode_id,
                    ctx.tenant_id,
                    ctx.workspace_id,
                    title,
                    goal,
                    outcome_status,
                    learned_summary,
                    json.dumps(skills_used or []),
                    now,
                ),
            )
            edges_created = 0
            for rel in relations or []:
                conn.execute(
                    """INSERT OR REPLACE INTO macro_edges(
                           tenant_id, workspace_id, source_type, source_id,
                           relation, target_type, target_id, weight, metadata_json, created_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        ctx.tenant_id,
                        ctx.workspace_id,
                        rel.get("source_type", "episode"),
                        rel.get("source_id", episode_id),
                        rel.get("relation", "relates_to"),
                        rel["target_type"],
                        rel["target_id"],
                        float(rel.get("weight", 1.0)),
                        json.dumps(rel.get("metadata", {})),
                        now,
                    ),
                )
                edges_created += 1
        return {"episode_id": episode_id, "edges_created": edges_created}

    def query_macro_graph(
        self,
        ctx: AccessContext,
        node_id: Optional[str] = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Returns high-level task episodes and their macro-graph edges."""
        with self._connect() as conn:
            episodes = conn.execute(
                """SELECT * FROM task_episodes
                   WHERE tenant_id = ? AND workspace_id = ?
                   ORDER BY created_at DESC LIMIT ?""",
                (ctx.tenant_id, ctx.workspace_id, limit),
            ).fetchall()
            if node_id:
                edges = conn.execute(
                    """SELECT * FROM macro_edges
                       WHERE tenant_id = ? AND workspace_id = ?
                         AND (source_id = ? OR target_id = ?)
                       ORDER BY weight DESC LIMIT ?""",
                    (ctx.tenant_id, ctx.workspace_id, node_id, node_id, limit),
                ).fetchall()
            else:
                edges = conn.execute(
                    """SELECT * FROM macro_edges
                       WHERE tenant_id = ? AND workspace_id = ?
                       ORDER BY created_at DESC LIMIT ?""",
                    (ctx.tenant_id, ctx.workspace_id, limit),
                ).fetchall()
        return {
            "episodes": [dict(e) for e in episodes],
            "edges": [dict(ed) for ed in edges],
        }

    def get_concept_config(
        self,
        ctx: AccessContext,
        concept_id: str,
    ) -> dict[str, Any]:
        """Returns the merged configuration dictionary for a framework or custom concept."""
        defaults = dict(
            DEFAULT_FRAMEWORK_CONCEPTS.get(concept_id, {}).get("default_config", {})
        )
        with self._connect() as conn:
            row = conn.execute(
                """SELECT config_json FROM framework_concept_configs
                   WHERE tenant_id = ? AND workspace_id = ? AND concept_id = ?""",
                (ctx.tenant_id, ctx.workspace_id, concept_id),
            ).fetchone()
        if row and row["config_json"]:
            try:
                overrides = json.loads(row["config_json"])
                if isinstance(overrides, dict):
                    defaults.update(overrides)
            except Exception:
                pass
        return defaults

    def update_concept_config(
        self,
        ctx: AccessContext,
        concept_id: str,
        updates: dict[str, Any],
    ) -> dict[str, Any]:
        """Updates and persists configuration parameters for a concept."""
        current = self.get_concept_config(ctx, concept_id)
        for k, v in updates.items():
            current[k] = v
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO framework_concept_configs(
                       tenant_id, workspace_id, concept_id, config_json, updated_at
                   ) VALUES (?, ?, ?, ?, ?)""",
                (ctx.tenant_id, ctx.workspace_id, concept_id, json.dumps(current), now),
            )
        return {
            "concept_id": concept_id,
            "is_framework_core": concept_id in DEFAULT_FRAMEWORK_CONCEPTS,
            "config": current,
            "updated_at": now,
        }

    def delete_concept_node(
        self,
        ctx: AccessContext,
        node_id: str,
    ) -> dict[str, Any]:
        """Deletes a user-developed concept/insight/skill/episode; blocks deletion of core framework concepts."""
        if node_id in DEFAULT_FRAMEWORK_CONCEPTS:
            raise PermissionError(
                f"Il concetto '{node_id}' è un pilastro fondamentale del framework Cortical e non può essere eliminato (puoi però configurarne i parametri)."
            )

        now = time.time()
        deleted_items = 0
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO deleted_concepts(
                       tenant_id, workspace_id, concept_id, deleted_at
                   ) VALUES (?, ?, ?, ?)""",
                (ctx.tenant_id, ctx.workspace_id, node_id, now),
            )
            deleted_items += 1

            if node_id.startswith("episode:"):
                ep_id = node_id.split(":", 1)[1]
                conn.execute(
                    "DELETE FROM task_episodes WHERE tenant_id = ? AND workspace_id = ? AND episode_id = ?",
                    (ctx.tenant_id, ctx.workspace_id, ep_id),
                )
                conn.execute(
                    """DELETE FROM macro_edges
                       WHERE tenant_id = ? AND workspace_id = ?
                         AND (source_id = ? OR target_id = ?)""",
                    (ctx.tenant_id, ctx.workspace_id, ep_id, ep_id),
                )
            elif node_id.startswith("insight:"):
                ins_id = node_id.split(":", 1)[1]
                has_ins = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='memory_insights'"
                ).fetchone()
                if has_ins:
                    conn.execute(
                        "DELETE FROM memory_insights WHERE tenant_id = ? AND workspace_id = ? AND insight_id = ?",
                        (ctx.tenant_id, ctx.workspace_id, ins_id),
                    )
            elif node_id.startswith("skill:"):
                sk_id = node_id.split(":", 1)[1]
                has_sk = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='learned_skills_registry'"
                ).fetchone()
                if has_sk:
                    conn.execute(
                        "DELETE FROM learned_skills_registry WHERE tenant_id = ? AND workspace_id = ? AND skill_id = ?",
                        (ctx.tenant_id, ctx.workspace_id, sk_id),
                    )
            elif node_id.startswith("concept:"):
                slug = node_id.split(":", 1)[1]
                m_rows = conn.execute(
                    """SELECT path, summary_light, summary_medium, raw_content
                       FROM merkle_nodes
                       WHERE tenant_id = ? AND workspace_id = ? AND node_type = 'file'""",
                    (ctx.tenant_id, ctx.workspace_id),
                ).fetchall()
                for r in m_rows:
                    p = str(r["path"])
                    stem_slug = re.sub(r"[^a-z0-9àèéìòù]+", "-", Path(p).stem.lower()).strip("-")
                    raw_low = str(r["raw_content"] or r["summary_light"] or "").lower()
                    if stem_slug == slug or slug.replace("-", " ") in raw_low:
                        conn.execute(
                            "DELETE FROM merkle_nodes WHERE tenant_id = ? AND workspace_id = ? AND path = ?",
                            (ctx.tenant_id, ctx.workspace_id, p),
                        )
                        conn.execute(
                            "DELETE FROM merkle_fts WHERE tenant_id = ? AND workspace_id = ? AND path = ?",
                            (ctx.tenant_id, ctx.workspace_id, p),
                        )

        return {"deleted": True, "node_id": node_id, "deleted_count": deleted_items}

    def clear_unattached_self_repo_nodes(
        self,
        ctx: AccessContext,
        self_repo_root: Optional[str | Path] = None,
    ) -> int:
        """Removes any merkle_nodes that were auto-crawled from Cortical's own repository unless explicitly attached."""
        attached_wiki_paths: set[str] = set()
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT metadata_json FROM scoped_context_attachments
                   WHERE tenant_id = ? AND workspace_id = ?""",
                (ctx.tenant_id, ctx.workspace_id),
            ).fetchall()
            for r in rows:
                try:
                    meta = json.loads(r["metadata_json"] or "{}")
                    for wp in meta.get("wiki_paths", []):
                        attached_wiki_paths.add(str(wp))
                except Exception:
                    pass

            # Identify self-repo internal paths (e.g. /src/cortical/*, /tests/test_cortical_all.py, /pyproject.toml)
            self_prefixes = (
                "/src/cortical",
                "/tests/test_cortical",
                "/scripts/setup.sh",
                "/scripts/start_live.sh",
                "/.pi/extensions/cortical-harness.ts",
                "/pyproject.toml",
                "/package.json",
                "/NOTICE",
                "/LICENSE",
            )
            m_rows = conn.execute(
                "SELECT path FROM merkle_nodes WHERE tenant_id = ? AND workspace_id = ?",
                (ctx.tenant_id, ctx.workspace_id),
            ).fetchall()
            removed = 0
            for mr in m_rows:
                p = str(mr["path"])
                if p in attached_wiki_paths:
                    continue
                if any(p == pref or p.startswith(pref + "/") for pref in self_prefixes):
                    conn.execute(
                        "DELETE FROM merkle_nodes WHERE tenant_id = ? AND workspace_id = ? AND path = ?",
                        (ctx.tenant_id, ctx.workspace_id, p),
                    )
                    conn.execute(
                        "DELETE FROM merkle_fts WHERE tenant_id = ? AND workspace_id = ? AND path = ?",
                        (ctx.tenant_id, ctx.workspace_id, p),
                    )
                    removed += 1
        return removed

    def attach_context_item(
        self,
        ctx: AccessContext,
        *,
        scope_id: str = "chat",
        item_type: str,
        item_ref: str,
        depth_tier: str = "medium",
        label: Optional[str] = None,
        inline_content: Optional[str] = None,
    ) -> dict[str, Any]:
        """Attaches a file, folder, skill, or plugin to a specific chat or task context (like ChatGPT / Claude Code)."""
        from .crawler import DEFAULT_IGNORE_DIRS, TEXT_EXTENSIONS, deterministic_extractive_summarizer

        item_type = item_type.lower().strip()
        if item_type not in {"file", "folder", "skill", "plugin"}:
            raise ValueError(f"Unsupported context item_type: {item_type}")

        scope_id = (scope_id or "chat").strip() or "chat"
        depth_tier = depth_tier if depth_tier in {"light", "medium", "high", "max"} else "medium"
        item_ref = item_ref.strip()
        if not item_ref:
            raise ValueError("item_ref cannot be empty")

        self.ensure_workspace(ctx, root_path="/", can_write=True)

        wiki_paths: list[str] = []
        summary_preview = ""
        resolved_label = label or Path(item_ref).name or item_ref

        if item_type == "file":
            p = Path(item_ref).expanduser()
            if p.exists() and p.is_file():
                raw_text = p.read_text(encoding="utf-8", errors="replace")[:48000]
                resolved_label = label or p.name
            else:
                raw_text = inline_content or f"# {resolved_label}\nAllegato contestuale: {item_ref}"
            wiki_path = f"/attached/{scope_id}/{resolved_label}"
            sums = deterministic_extractive_summarizer(wiki_path, raw_text, "file")
            chash = hashlib.sha256(raw_text.encode("utf-8", errors="replace")).hexdigest()
            self.upsert_merkle_node(
                ctx,
                path=wiki_path,
                parent_path="/",
                node_type="file",
                content_hash=chash,
                subtree_hash=chash,
                summary_light=sums["light"],
                summary_medium=sums["medium"],
                summary_high=sums["high"],
                raw_content=raw_text,
            )
            wiki_paths.append(wiki_path)
            summary_preview = sums.get(depth_tier if depth_tier != "max" else "high", sums["medium"])[:320]

        elif item_type == "folder":
            p = Path(item_ref).expanduser()
            resolved_label = label or p.name or item_ref
            folder_prefix = f"/attached/{scope_id}/{resolved_label}"
            collected_lights: list[str] = []
            if p.exists() and p.is_dir():
                count = 0
                for cur_root, dirs, files in os.walk(p):
                    dirs[:] = sorted(
                        d for d in dirs if d not in DEFAULT_IGNORE_DIRS and not d.startswith(".")
                    )
                    for fname in sorted(files):
                        if count >= 35:
                            break
                        fpath = Path(cur_root) / fname
                        if fpath.suffix.lower() not in TEXT_EXTENSIONS:
                            continue
                        try:
                            raw_text = fpath.read_text(encoding="utf-8", errors="replace")[:32000]
                        except Exception:
                            continue
                        rel = fpath.relative_to(p).as_posix()
                        wpath = f"{folder_prefix}/{rel}"
                        sums = deterministic_extractive_summarizer(wpath, raw_text, "file")
                        chash = hashlib.sha256(raw_text.encode("utf-8", errors="replace")).hexdigest()
                        self.upsert_merkle_node(
                            ctx,
                            path=wpath,
                            parent_path=folder_prefix,
                            node_type="file",
                            content_hash=chash,
                            subtree_hash=chash,
                            summary_light=sums["light"],
                            summary_medium=sums["medium"],
                            summary_high=sums["high"],
                            raw_content=raw_text,
                        )
                        wiki_paths.append(wpath)
                        collected_lights.append(sums["light"])
                        count += 1
            summary_preview = (
                f"Cartella '{resolved_label}' ({len(wiki_paths)} file indicizzati 3+1): "
                + " | ".join(collected_lights[:3])
            )[:320]

        elif item_type == "skill":
            resolved_label = label or item_ref
            summary_preview = f"Skill procedurale attiva nel contesto '{scope_id}': {resolved_label}"

        elif item_type == "plugin":
            resolved_label = label or item_ref
            summary_preview = f"Plugin / MCP attivo nel contesto '{scope_id}': {resolved_label}"

        now = time.time()
        att_id = f"att_{hashlib.sha1(f'{scope_id}:{item_type}:{item_ref}'.encode('utf-8')).hexdigest()[:10]}"
        meta = {"wiki_paths": wiki_paths, "full_ref": item_ref}
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO scoped_context_attachments(
                       attachment_id, tenant_id, workspace_id, scope_id,
                       item_type, item_ref, label, depth_tier, summary_preview,
                       metadata_json, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    att_id,
                    ctx.tenant_id,
                    ctx.workspace_id,
                    scope_id,
                    item_type,
                    item_ref,
                    resolved_label,
                    depth_tier,
                    summary_preview,
                    json.dumps(meta),
                    now,
                ),
            )
            # Clear from deleted_concepts if re-attached
            slug = re.sub(r"[^a-z0-9àèéìòù]+", "-", Path(resolved_label).stem.lower()).strip("-")
            if slug:
                conn.execute(
                    "DELETE FROM deleted_concepts WHERE tenant_id = ? AND workspace_id = ? AND concept_id = ?",
                    (ctx.tenant_id, ctx.workspace_id, f"concept:{slug}"),
                )

        return {
            "attachment_id": att_id,
            "scope_id": scope_id,
            "item_type": item_type,
            "item_ref": item_ref,
            "label": resolved_label,
            "depth_tier": depth_tier,
            "summary_preview": summary_preview,
            "wiki_paths": wiki_paths,
            "created_at": now,
        }

    def detach_context_item(
        self,
        ctx: AccessContext,
        attachment_id: str,
    ) -> dict[str, Any]:
        """Detaches an item from the chat/task context and removes its transient wiki nodes."""
        with self._connect() as conn:
            row = conn.execute(
                """SELECT * FROM scoped_context_attachments
                   WHERE tenant_id = ? AND workspace_id = ? AND attachment_id = ?""",
                (ctx.tenant_id, ctx.workspace_id, attachment_id),
            ).fetchone()
            if not row:
                return {"detached": False, "attachment_id": attachment_id}
            meta = json.loads(row["metadata_json"] or "{}")
            for wp in meta.get("wiki_paths", []):
                conn.execute(
                    "DELETE FROM merkle_nodes WHERE tenant_id = ? AND workspace_id = ? AND path = ?",
                    (ctx.tenant_id, ctx.workspace_id, wp),
                )
                conn.execute(
                    "DELETE FROM merkle_fts WHERE tenant_id = ? AND workspace_id = ? AND path = ?",
                    (ctx.tenant_id, ctx.workspace_id, wp),
                )
            conn.execute(
                """DELETE FROM scoped_context_attachments
                   WHERE tenant_id = ? AND workspace_id = ? AND attachment_id = ?""",
                (ctx.tenant_id, ctx.workspace_id, attachment_id),
            )
        return {"detached": True, "attachment_id": attachment_id}

    def list_context_attachments(
        self,
        ctx: AccessContext,
        scope_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Lists active context attachments for a chat or task scope."""
        with self._connect() as conn:
            if scope_id:
                rows = conn.execute(
                    """SELECT * FROM scoped_context_attachments
                       WHERE tenant_id = ? AND workspace_id = ? AND scope_id = ?
                       ORDER BY created_at DESC""",
                    (ctx.tenant_id, ctx.workspace_id, scope_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM scoped_context_attachments
                       WHERE tenant_id = ? AND workspace_id = ?
                       ORDER BY created_at DESC""",
                    (ctx.tenant_id, ctx.workspace_id),
                ).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            try:
                d["metadata"] = json.loads(d.get("metadata_json") or "{}")
            except Exception:
                d["metadata"] = {}
            out.append(d)
        return out

    def get_knowledge_graph(
        self,
        ctx: AccessContext,
        max_nodes: int = 60,
    ) -> dict[str, Any]:
        """Builds a Semantic Concept Knowledge Graph with protected configurable Framework Concepts and deletable User Concepts."""
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        concept_by_slug: dict[str, dict[str, Any]] = {}
        path_to_primary_concept: dict[str, str] = {}

        def _slugify(text: str) -> str:
            s = re.sub(r"[^a-z0-9àèéìòù]+", "-", text.lower()).strip("-")
            return s[:42] or "concetto"

        def _infer_category(label: str, body: str) -> str:
            low = f"{label} {body}".lower()
            if any(w in low for w in ("rbac", "acl", "permission", "permess", "security", "sicurezza", "guardrail")):
                return "sicurezza"
            if any(w in low for w in ("merkle", "memory", "memoria", "wiki", "3+1", "tier", "sqlite", "fts")):
                return "memoria"
            if any(w in low for w in ("voice", "voce", "tts", "audio", "speech", "echo", "barge")):
                return "voce"
            if any(w in low for w in ("agent", "multi-agent", "subagent", "orchestr", "pi", "mcp", "skill")):
                return "agenti"
            return "architettura"

        with self._connect() as conn:
            deleted_rows = conn.execute(
                "SELECT concept_id FROM deleted_concepts WHERE tenant_id = ? AND workspace_id = ?",
                (ctx.tenant_id, ctx.workspace_id),
            ).fetchall()
            deleted_set = {str(r["concept_id"]) for r in deleted_rows}

        # 0. Core Protected Framework Concepts (always present, non-deletable, live-configurable)
        hub_id = "concept:cortical-second-brain"
        for cid, meta in DEFAULT_FRAMEWORK_CONCEPTS.items():
            seen_ids.add(cid)
            cfg = self.get_concept_config(ctx, cid)
            c_node = {
                "id": cid,
                "key": meta["key"],
                "label": meta["label"],
                "kind": meta["kind"],
                "category": meta["category"],
                "is_framework_core": True,
                "deletable": False,
                "config": cfg,
                "config_schema": meta["config_schema"],
                "summary": meta["summary"],
                "summary_medium": meta["summary_medium"],
                "sources": ["framework:core"],
            }
            concept_by_slug[cid] = c_node
            nodes.append(c_node)
            if cid != hub_id:
                edges.append(
                    {
                        "source": hub_id,
                        "target": cid,
                        "relation": "pilastro",
                        "kind": "concept_link",
                    }
                )

        with self._connect() as conn:
            # 1. Extract User-Developed Concepts from accessible Wiki knowledge (deletable!)
            m_rows = conn.execute(
                """SELECT path, summary_light, summary_medium, summary_high, raw_content
                   FROM merkle_nodes
                   WHERE tenant_id = ? AND workspace_id = ? AND node_type = 'file'
                   ORDER BY LENGTH(path) ASC
                   LIMIT ?""",
                (ctx.tenant_id, ctx.workspace_id, max_nodes),
            ).fetchall()

            for r in m_rows:
                doc_path = str(r["path"])
                if not self.check_access(ctx, doc_path, write=False):
                    continue
                raw = str(r["raw_content"] or r["summary_high"] or r["summary_medium"] or "")
                headings = [
                    m.group(2).strip()
                    for m in re.finditer(r"^(#{1,3})\s+(.+)$", raw, flags=re.MULTILINE)
                    if len(m.group(2).strip()) >= 3
                ]
                bold_concepts = [
                    m.group(1).strip()
                    for m in re.finditer(r"\*\*([A-Za-zÀ-ÿ0-9][A-Za-zÀ-ÿ0-9\s\-/+]{3,34})\*\*", raw)
                ]
                extracted_titles: list[str] = []
                for h in headings + bold_concepts:
                    clean_h = re.sub(r"[`*_#]+", "", h).strip(" :-–—")
                    if clean_h and clean_h.lower() not in {"indice", "note", "esempio", "todo"}:
                        if clean_h not in extracted_titles:
                            extracted_titles.append(clean_h)

                if not extracted_titles:
                    stem = Path(doc_path).stem.replace("_", " ").replace("-", " ").title()
                    extracted_titles = [stem or "Concetto Dominio"]

                primary_title = extracted_titles[0]
                primary_slug = _slugify(primary_title)
                primary_id = f"concept:{primary_slug}"
                if primary_id in deleted_set:
                    continue
                path_to_primary_concept[doc_path] = primary_id

                if primary_id not in concept_by_slug:
                    cat = _infer_category(primary_title, raw)
                    c_node = {
                        "id": primary_id,
                        "key": primary_slug,
                        "label": primary_title[:32],
                        "kind": "concept",
                        "category": cat,
                        "is_framework_core": False,
                        "deletable": True,
                        "config": self.get_concept_config(ctx, primary_id),
                        "config_schema": [
                            {"key": "preferred_depth", "label": "Profondità Sintesi Concetto", "type": "select", "options": ["light", "medium", "high", "max"]},
                            {"key": "priority_weight", "label": "Peso Priorità nel Contesto", "type": "number", "min": 1, "max": 10},
                        ],
                        "summary": str(r["summary_light"] or primary_title)[:220],
                        "summary_medium": str(r["summary_medium"] or r["summary_light"] or "")[:500],
                        "summary_high": str(r["summary_high"] or "")[:1000],
                        "sources": [doc_path],
                    }
                    concept_by_slug[primary_id] = c_node
                    seen_ids.add(primary_id)
                    nodes.append(c_node)
                    edges.append(
                        {
                            "source": hub_id,
                            "target": primary_id,
                            "relation": "concetto_utente",
                            "kind": "concept_link",
                        }
                    )
                else:
                    if doc_path not in concept_by_slug[primary_id]["sources"]:
                        concept_by_slug[primary_id]["sources"].append(doc_path)

                # Extract up to 2 sub-concepts per document and link them to the primary concept
                for sub_title in extracted_titles[1:3]:
                    sub_slug = _slugify(sub_title)
                    sub_id = f"concept:{sub_slug}"
                    if sub_id == primary_id or sub_id in deleted_set or len(nodes) >= max_nodes:
                        continue
                    if sub_id not in concept_by_slug:
                        cat = _infer_category(sub_title, raw)
                        sub_node = {
                            "id": sub_id,
                            "key": sub_slug,
                            "label": sub_title[:32],
                            "kind": "concept",
                            "category": cat,
                            "is_framework_core": False,
                            "deletable": True,
                            "config": self.get_concept_config(ctx, sub_id),
                            "config_schema": [
                                {"key": "preferred_depth", "label": "Profondità Sintesi Concetto", "type": "select", "options": ["light", "medium", "high", "max"]},
                            ],
                            "summary": f"Concetto correlato a '{primary_title}': {str(r['summary_light'])[:160]}",
                            "summary_medium": str(r["summary_medium"] or r["summary_light"] or "")[:450],
                            "sources": [doc_path],
                        }
                        concept_by_slug[sub_id] = sub_node
                        seen_ids.add(sub_id)
                        nodes.append(sub_node)
                    edges.append(
                        {
                            "source": primary_id,
                            "target": sub_id,
                            "relation": "include",
                            "kind": "concept_link",
                        }
                    )

            # 2. Task Episodes (active & archived traces connected to concepts — deletable)
            ep_rows = conn.execute(
                """SELECT * FROM task_episodes
                   WHERE tenant_id = ? AND workspace_id = ?
                   ORDER BY created_at DESC LIMIT 18""",
                (ctx.tenant_id, ctx.workspace_id),
            ).fetchall()
            for ep in ep_rows:
                ep_dict = dict(ep)
                nid = f"episode:{ep_dict['episode_id']}"
                if nid in deleted_set:
                    continue
                seen_ids.add(nid)
                state = ep_dict.get("lifecycle_state", ep_dict.get("outcome_status", "active"))
                trace = ep_dict.get("archived_trace") or ep_dict.get("learned_summary", "")
                cat = _infer_category(ep_dict["title"], f"{ep_dict.get('goal', '')} {trace}")
                nodes.append(
                    {
                        "id": nid,
                        "key": ep_dict["episode_id"],
                        "label": ep_dict["title"][:30],
                        "kind": "task_archived" if state == "archived" else "task_active",
                        "category": cat,
                        "state": state,
                        "is_framework_core": False,
                        "deletable": True,
                        "summary": trace[:220] or ep_dict.get("goal", ""),
                        "sources": [f"task:{ep_dict['episode_id']}"],
                    }
                )
                linked = False
                for cid, cnode in concept_by_slug.items():
                    if cnode.get("category") == cat and cid != hub_id:
                        edges.append(
                            {
                                "source": nid,
                                "target": cid,
                                "relation": "alimenta",
                                "kind": "macro",
                            }
                        )
                        linked = True
                        break
                if not linked:
                    edges.append(
                        {
                            "source": nid,
                            "target": hub_id,
                            "relation": "alimenta",
                            "kind": "macro",
                        }
                    )

            # 3. Curated Memory Insights (connected to concepts — deletable)
            has_insights = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='memory_insights'"
            ).fetchone()
            if has_insights:
                ins_rows = conn.execute(
                    """SELECT * FROM memory_insights
                       WHERE tenant_id = ? AND workspace_id = ?
                       ORDER BY created_at DESC LIMIT 15""",
                    (ctx.tenant_id, ctx.workspace_id),
                ).fetchall()
                for ins in ins_rows:
                    nid = f"insight:{ins['insight_id']}"
                    if nid in deleted_set:
                        continue
                    seen_ids.add(nid)
                    cat = _infer_category(ins["category"], ins["insight_text"])
                    nodes.append(
                        {
                            "id": nid,
                            "key": ins["insight_id"],
                            "label": f"💡 {ins['category'][:24]}",
                            "kind": "insight",
                            "category": cat,
                            "is_framework_core": False,
                            "deletable": True,
                            "summary": ins["insight_text"],
                            "sources": ["conversazione"],
                        }
                    )
                    target_cid = next(
                        (cid for cid, cn in concept_by_slug.items() if cn.get("category") == cat and cid != hub_id),
                        hub_id,
                    )
                    edges.append(
                        {
                            "source": nid,
                            "target": target_cid,
                            "relation": "arricchisce",
                            "kind": "insight_link",
                        }
                    )

            # 4. Learned Skills (connected to concepts — deletable)
            has_learned = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='learned_skills_registry'"
            ).fetchone()
            if has_learned:
                sk_rows = conn.execute(
                    """SELECT * FROM learned_skills_registry
                       WHERE tenant_id = ? AND workspace_id = ?
                       ORDER BY created_at DESC LIMIT 12""",
                    (ctx.tenant_id, ctx.workspace_id),
                ).fetchall()
                for sk in sk_rows:
                    nid = f"skill:{sk['skill_id']}"
                    if nid in deleted_set:
                        continue
                    seen_ids.add(nid)
                    cat = _infer_category(sk["name"], sk["description"])
                    nodes.append(
                        {
                            "id": nid,
                            "key": sk["skill_id"],
                            "label": f"⚡ {sk['name'][:26]}",
                            "kind": "skill",
                            "category": cat,
                            "is_framework_core": False,
                            "deletable": True,
                            "summary": sk["description"],
                            "sources": [sk["skill_path"]],
                        }
                    )
                    src_ep = f"episode:{sk['source_episode_id']}"
                    edges.append(
                        {
                            "source": src_ep if src_ep in seen_ids else hub_id,
                            "target": nid,
                            "relation": "genera_skill",
                            "kind": "skill_link",
                        }
                    )

            # 5. High-level Macro-Graph edges (mapped from file subtrees to their primary concept)
            e_rows = conn.execute(
                """SELECT * FROM macro_edges
                   WHERE tenant_id = ? AND workspace_id = ?
                   ORDER BY created_at DESC LIMIT 60""",
                (ctx.tenant_id, ctx.workspace_id),
            ).fetchall()
            for ed in e_rows:
                src = f"{ed['source_type']}:{ed['source_id']}"
                dst = (
                    path_to_primary_concept.get(ed["target_id"], hub_id)
                    if ed["target_type"] == "subtree"
                    else f"{ed['target_type']}:{ed['target_id']}"
                )
                if src in seen_ids and dst in seen_ids and src != dst:
                    edges.append(
                        {
                            "source": src,
                            "target": dst,
                            "relation": ed["relation"],
                            "kind": "macro",
                        }
                    )

        for n in nodes:
            n.setdefault("type", n.get("kind", "concept"))

        return {
            "nodes": nodes,
            "edges": edges,
            "stats": {
                "node_count": len(nodes),
                "edge_count": len(edges),
                "concept_count": sum(1 for n in nodes if n.get("kind") in {"hub", "concept"}),
                "framework_core_count": sum(1 for n in nodes if n.get("is_framework_core")),
                "user_concept_count": sum(1 for n in nodes if not n.get("is_framework_core")),
            },
        }
