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
import json
import re
import sqlite3
import time
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
"""


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

    def get_knowledge_graph(
        self,
        ctx: AccessContext,
        max_nodes: int = 60,
    ) -> dict[str, Any]:
        """Builds a Semantic Concept Knowledge Graph (Concepts, Insights, Skills & Tasks — NOT raw file listings)."""
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

        # 0. Root Semantic Hub
        hub_id = "concept:cortical-second-brain"
        seen_ids.add(hub_id)
        nodes.append(
            {
                "id": hub_id,
                "key": "cortical-second-brain",
                "label": "Cortical Second Brain",
                "kind": "hub",
                "category": "memoria",
                "summary": "Nucleo semantico 3+1 livelli (Light, Medium, High, Max) con Grafo dei Concetti, Voce Dual-Path e Orchestratore Multi-Agente.",
                "summary_medium": "Architettura cognitiva locale che separa la memoria strutturata a 3+1 livelli dalle capacità procedurali (Skill) e collega i concetti chiave estratti dai compiti svolti.",
                "sources": ["/"],
            }
        )

        with self._connect() as conn:
            # 1. Extract Semantic Concepts from accessible Wiki knowledge (excluding raw directory listings)
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
                path_to_primary_concept[doc_path] = primary_id

                if primary_id not in concept_by_slug:
                    cat = _infer_category(primary_title, raw)
                    c_node = {
                        "id": primary_id,
                        "key": primary_slug,
                        "label": primary_title[:32],
                        "kind": "concept",
                        "category": cat,
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
                            "relation": "pilastro",
                            "kind": "concept_link",
                        }
                    )
                else:
                    if doc_path not in concept_by_slug[primary_id]["sources"]:
                        concept_by_slug[primary_id]["sources"].append(doc_path)

                # Extract up to 3 sub-concepts per document and link them to the primary concept
                for sub_title in extracted_titles[1:4]:
                    sub_slug = _slugify(sub_title)
                    sub_id = f"concept:{sub_slug}"
                    if sub_id == primary_id or len(nodes) >= max_nodes:
                        continue
                    if sub_id not in concept_by_slug:
                        cat = _infer_category(sub_title, raw)
                        sub_node = {
                            "id": sub_id,
                            "key": sub_slug,
                            "label": sub_title[:32],
                            "kind": "concept",
                            "category": cat,
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

            # 2. If the Wiki has very few documents yet, seed core architectural concepts so the graph is immediately rich
            default_core_concepts = [
                (
                    "memoria-3plus1-merkle",
                    "Memoria 3+1 Livelli",
                    "memoria",
                    "Sintesi gerarchica deterministica: L1 Light (~50 tok), L2 Medium (~250 tok), L3 High (~1000 tok), +1 Max integrale.",
                ),
                (
                    "orchestratore-multi-agente",
                    "Orchestratore Multi-Agente",
                    "agenti",
                    "Coordinamento su richiesta tra Analyst, Implementer e Reviewer con isolamento della memoria di task.",
                ),
                (
                    "voce-neurale-anti-eco",
                    "Voce Neurale & Scudo Anti-Eco",
                    "voce",
                    "Sintesi vocale espressiva italiana con isolamento dell'eco degli altoparlanti e barge-in tramite wake-word.",
                ),
                (
                    "adaptive-permission-gate",
                    "Adaptive Permission Gate",
                    "sicurezza",
                    "Guardrail deterministici contro comandi distruttivi e apprendimento progressivo dei pattern approvati.",
                ),
            ]
            for slug, label, cat, desc in default_core_concepts:
                cid = f"concept:{slug}"
                if cid not in seen_ids and len(nodes) < max_nodes:
                    seen_ids.add(cid)
                    c_node = {
                        "id": cid,
                        "key": slug,
                        "label": label,
                        "kind": "concept",
                        "category": cat,
                        "summary": desc,
                        "summary_medium": desc,
                        "sources": ["/"],
                    }
                    concept_by_slug[cid] = c_node
                    nodes.append(c_node)
                    edges.append(
                        {
                            "source": hub_id,
                            "target": cid,
                            "relation": "pilastro",
                            "kind": "concept_link",
                        }
                    )

            # 3. Task Episodes (active & archived traces connected to concepts)
            ep_rows = conn.execute(
                """SELECT * FROM task_episodes
                   WHERE tenant_id = ? AND workspace_id = ?
                   ORDER BY created_at DESC LIMIT 18""",
                (ctx.tenant_id, ctx.workspace_id),
            ).fetchall()
            for ep in ep_rows:
                ep_dict = dict(ep)
                nid = f"episode:{ep_dict['episode_id']}"
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
                        "summary": trace[:220] or ep_dict.get("goal", ""),
                        "sources": [f"task:{ep_dict['episode_id']}"],
                    }
                )
                # Connect task episode to matching category concept or hub
                linked = False
                for cid, cnode in concept_by_slug.items():
                    if cnode.get("category") == cat:
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

            # 4. Curated Memory Insights (connected to concepts)
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
                    seen_ids.add(nid)
                    cat = _infer_category(ins["category"], ins["insight_text"])
                    nodes.append(
                        {
                            "id": nid,
                            "key": ins["insight_id"],
                            "label": f"💡 {ins['category'][:24]}",
                            "kind": "insight",
                            "category": cat,
                            "summary": ins["insight_text"],
                            "sources": ["conversazione"],
                        }
                    )
                    target_cid = next(
                        (cid for cid, cn in concept_by_slug.items() if cn.get("category") == cat),
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

            # 5. Learned Skills (connected to concepts)
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
                    seen_ids.add(nid)
                    cat = _infer_category(sk["name"], sk["description"])
                    nodes.append(
                        {
                            "id": nid,
                            "key": sk["skill_id"],
                            "label": f"⚡ {sk['name'][:26]}",
                            "kind": "skill",
                            "category": cat,
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

            # 6. High-level Macro-Graph edges (mapped from file subtrees to their primary concept)
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
            },
        }
