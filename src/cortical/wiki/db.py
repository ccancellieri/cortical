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
        """Builds the unified Knowledge Graph (Merkle roots/files + Tasks + Curated Insights + Edges)."""
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        with self._connect() as conn:
            # 1. Merkle nodes (prioritize directories and top-level files)
            m_rows = conn.execute(
                """SELECT path, parent_path, node_type, summary_light, subtree_hash
                   FROM merkle_nodes
                   WHERE tenant_id = ? AND workspace_id = ?
                   ORDER BY CASE WHEN node_type = 'dir' THEN 0 ELSE 1 END, LENGTH(path) ASC
                   LIMIT ?""",
                (ctx.tenant_id, ctx.workspace_id, max_nodes),
            ).fetchall()
            for r in m_rows:
                if not self.check_access(ctx, r["path"], write=False):
                    continue
                nid = f"subtree:{r['path']}"
                seen_ids.add(nid)
                nodes.append(
                    {
                        "id": nid,
                        "key": r["path"],
                        "label": r["path"] if r["path"] == "/" else r["path"].split("/")[-1],
                        "kind": "dir" if r["node_type"] == "dir" else "file",
                        "summary": r["summary_light"],
                        "hash": r["subtree_hash"][:10],
                    }
                )
                if r["parent_path"]:
                    parent_id = f"subtree:{r['parent_path']}"
                    edges.append(
                        {
                            "source": parent_id,
                            "target": nid,
                            "relation": "contains",
                            "kind": "merkle",
                        }
                    )

            # 2. Task episodes (active & archived traces)
            ep_rows = conn.execute(
                """SELECT * FROM task_episodes
                   WHERE tenant_id = ? AND workspace_id = ?
                   ORDER BY created_at DESC LIMIT 25""",
                (ctx.tenant_id, ctx.workspace_id),
            ).fetchall()
            for ep in ep_rows:
                ep_dict = dict(ep)
                nid = f"episode:{ep_dict['episode_id']}"
                seen_ids.add(nid)
                state = ep_dict.get("lifecycle_state", ep_dict.get("outcome_status", "active"))
                trace = ep_dict.get("archived_trace") or ep_dict.get("learned_summary", "")
                nodes.append(
                    {
                        "id": nid,
                        "key": ep_dict["episode_id"],
                        "label": ep_dict["title"][:28],
                        "kind": "task_archived" if state == "archived" else "task_active",
                        "state": state,
                        "summary": trace[:180],
                    }
                )

            # 3. Curated Memory Insights (if table initialized)
            has_insights = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='memory_insights'"
            ).fetchone()
            if has_insights:
                ins_rows = conn.execute(
                    """SELECT * FROM memory_insights
                       WHERE tenant_id = ? AND workspace_id = ?
                       ORDER BY created_at DESC LIMIT 20""",
                    (ctx.tenant_id, ctx.workspace_id),
                ).fetchall()
                for ins in ins_rows:
                    nid = f"episode:{ins['insight_id']}"
                    seen_ids.add(nid)
                    nodes.append(
                        {
                            "id": nid,
                            "key": ins["insight_id"],
                            "label": f"💡 {ins['category']}",
                            "kind": "insight",
                            "summary": ins["insight_text"],
                        }
                    )

            # 4. High-level Macro-Graph edges
            e_rows = conn.execute(
                """SELECT * FROM macro_edges
                   WHERE tenant_id = ? AND workspace_id = ?
                   ORDER BY created_at DESC LIMIT 60""",
                (ctx.tenant_id, ctx.workspace_id),
            ).fetchall()
            for ed in e_rows:
                src = f"{ed['source_type']}:{ed['source_id']}"
                dst = f"{ed['target_type']}:{ed['target_id']}"
                if src in seen_ids and dst in seen_ids:
                    edges.append(
                        {
                            "source": src,
                            "target": dst,
                            "relation": ed["relation"],
                            "kind": "macro",
                        }
                    )

        for n in nodes:
            n.setdefault("type", n.get("kind", "file"))

        return {
            "nodes": nodes,
            "edges": edges,
            "stats": {
                "node_count": len(nodes),
                "edge_count": len(edges),
            },
        }
