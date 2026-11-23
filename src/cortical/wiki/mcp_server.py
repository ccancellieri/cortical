"""Stdlib-only JSON-RPC 2.0 MCP Server exposing Cortical Wiki / Knowledge tools.

Exposes:
- `wiki_search`: FTS5 BM25 search scoped by `principal_id`
- `wiki_navigate`: Merkle-tree file explorer scoped by `principal_id`
- `wiki_crawl_delta`: Deterministic SHA-256 Merkle-tree delta / full re-index
- `wiki_record_episode`: Record episodic memory events scoped by `principal_id`
- `wiki_verify_citation`: Verify claims/citations against indexed documents
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

from ..workspace import resolve_default_db
from .store import KnowledgeStore

WIKI_TOOLS_SCHEMA: list[dict[str, Any]] = [
    {
        "name": "wiki_search",
        "description": "Search indexed knowledge documents using SQLite FTS5 BM25 scoped by `principal_id`.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "principal_id": {"type": "string", "default": "local_owner"},
                "limit": {"type": "integer", "default": 10},
                "depth": {"type": "integer", "default": 1},
            },
            "required": ["query"],
        },
    },
    {
        "name": "wiki_navigate",
        "description": "Navigate registered knowledge files and Merkle hashes scoped by `principal_id`.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "principal_id": {"type": "string", "default": "local_owner"},
                "root_id": {"type": "string"},
                "status_filter": {"type": "string", "enum": ["all", "indexed", "modified", "ignored", "error"], "default": "all"},
                "search_path": {"type": "string", "default": ""},
            },
        },
    },
    {
        "name": "wiki_crawl_delta",
        "description": "Run deterministic Merkle-tree delta crawl (or full re-index) on registered roots.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "root_id": {"type": "string"},
                "principal_id": {"type": "string", "default": "local_owner"},
                "full_reindex": {"type": "boolean", "default": False},
            },
        },
    },
    {
        "name": "wiki_record_episode",
        "description": "Record an episodic memory entry scoped by `principal_id`.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "summary": {"type": "string"},
                "principal_id": {"type": "string", "default": "local_owner"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "source_refs": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["title", "summary"],
        },
    },
    {
        "name": "wiki_verify_citation",
        "description": "Verify a claim or quote against indexed documents accessible to `principal_id`.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "claim": {"type": "string"},
                "principal_id": {"type": "string", "default": "local_owner"},
                "doc_id": {"type": "string"},
                "threshold": {"type": "number", "default": 0.45},
            },
            "required": ["claim"],
        },
    },
]


class WikiMCPServer:
    """JSON-RPC 2.0 stdio MCP server for multi-tenant Knowledge & Memory RAG."""

    def __init__(self, db_path: Optional[Path | str] = None) -> None:
        self.store = KnowledgeStore(db_path or resolve_default_db())

    def _dispatch_tool(self, name: str, args: dict[str, Any]) -> Any:
        pid = str(args.get("principal_id") or "local_owner")
        if name == "wiki_search":
            return {
                "results": self.store.search(
                    str(args.get("query") or ""),
                    principal_id=pid,
                    limit=int(args.get("limit") or 10),
                    depth=int(args.get("depth") if args.get("depth") is not None else 1),
                )
            }
        if name == "wiki_navigate":
            return self.store.navigate(
                principal_id=pid,
                root_id=args.get("root_id"),
                status_filter=args.get("status_filter"),
                search_path=str(args.get("search_path") or ""),
            )
        if name == "wiki_crawl_delta":
            return self.store.crawl_delta(
                root_id=args.get("root_id"),
                principal_id=pid,
                full_reindex=bool(args.get("full_reindex", False)),
            )
        if name == "wiki_record_episode":
            return self.store.record_episode(
                title=str(args.get("title") or ""),
                summary=str(args.get("summary") or ""),
                principal_id=pid,
                tags=args.get("tags"),
                source_refs=args.get("source_refs"),
            )
        if name == "wiki_verify_citation":
            return self.store.verify_citation(
                str(args.get("claim") or ""),
                principal_id=pid,
                doc_id=args.get("doc_id"),
                threshold=float(args.get("threshold") or 0.45),
            )
        raise ValueError(f"Unknown wiki tool: {name}")

    def handle_request(self, req: dict[str, Any]) -> Optional[dict[str, Any]]:
        method = req.get("method", "")
        rid = req.get("id")
        if rid is None and method.startswith("notifications/"):
            return None
        try:
            if method == "initialize":
                return {
                    "jsonrpc": "2.0",
                    "id": rid,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "cortical-wiki", "version": "0.3.0"},
                    },
                }
            if method == "tools/list":
                return {"jsonrpc": "2.0", "id": rid, "result": {"tools": WIKI_TOOLS_SCHEMA}}
            if method == "tools/call":
                p = req.get("params") or {}
                out = self._dispatch_tool(str(p.get("name") or ""), dict(p.get("arguments") or {}))
                return {
                    "jsonrpc": "2.0",
                    "id": rid,
                    "result": {"content": [{"type": "text", "text": json.dumps(out, ensure_ascii=False)}]},
                }
            return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"Method not found: {method}"}}
        except Exception as exc:  # noqa: BLE001
            return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32000, "message": str(exc)}}

    def serve_stdio(self) -> None:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except json.JSONDecodeError:
                continue
            resp = self.handle_request(req)
            if resp is not None:
                sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
                sys.stdout.flush()


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Cortical Wiki MCP stdio server")
    parser.add_argument("--db", default=None, help="Path to wiki.db")
    args = parser.parse_args(argv)
    WikiMCPServer(db_path=args.db).serve_stdio()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
