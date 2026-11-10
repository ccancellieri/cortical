"""Standard Model Context Protocol (MCP) Server for Cortical Second Brain (`cortical-wiki-mcp`).

Implements JSON-RPC 2.0 over stdio so `pi` (via `.pi/agent/mcp.json`) or any MCP host
can deterministically navigate, search, crawl, fact-check, and record task episodes.
"""

from __future__ import annotations

import dataclasses
import json
import os
import sys
from pathlib import Path
from typing import Any

from .crawler import DeterministicMerkleCrawler
from .db import AccessContext, CorticalWikiDB, DepthTier
from .fact_check import CitationVerifier

MCP_TOOLS = [
    {
        "name": "wiki_navigate",
        "description": (
            "Navigate the deterministic Merkle-tree Second Brain at a specific synthesis depth: "
            "'light' (~50 tokens), 'medium' (~250 tokens), 'high' (~1000 tokens), or 'max' (full raw content)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "default": "/"},
                "depth": {
                    "type": "string",
                    "enum": ["light", "medium", "high", "max"],
                    "default": "light",
                },
                "include_children": {"type": "boolean", "default": True},
                "principal_id": {"type": "string", "default": "local_owner"},
            },
        },
    },
    {
        "name": "wiki_search",
        "description": "Full-text FTS5 search across the Second Brain with RBAC filtering and depth projection.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "depth": {
                    "type": "string",
                    "enum": ["light", "medium", "high", "max"],
                    "default": "medium",
                },
                "limit": {"type": "integer", "default": 10},
                "principal_id": {"type": "string", "default": "local_owner"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "wiki_crawl_delta",
        "description": "Run the deterministic parallel Merkle-tree crawler on a directory, updating only modified branches.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "root_dir": {"type": "string"},
                "principal_id": {"type": "string", "default": "local_owner"},
            },
            "required": ["root_dir"],
        },
    },
    {
        "name": "wiki_verify_citation",
        "description": "Verify a claim and quoted span against a source path using deterministic span check + NLI decision model.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "claim_text": {"type": "string"},
                "source_path": {"type": "string"},
                "quoted_span": {"type": "string"},
                "principal_id": {"type": "string", "default": "local_owner"},
            },
            "required": ["claim_text", "source_path", "quoted_span"],
        },
    },
    {
        "name": "wiki_record_episode",
        "description": "Record a completed agentic task episode and link it in the High-Level Macro-Graph.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "episode_id": {"type": "string"},
                "title": {"type": "string"},
                "goal": {"type": "string"},
                "outcome_status": {"type": "string"},
                "learned_summary": {"type": "string"},
                "skills_used": {"type": "array", "items": {"type": "string"}},
                "relations": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["episode_id", "title", "goal", "outcome_status", "learned_summary"],
        },
    },
]


class CorticalWikiMCPServer:
    """JSON-RPC 2.0 MCP Server handler for Cortical Second Brain."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        default_db = os.environ.get(
            "CORTICAL_WIKI_DB",
            str(Path.home() / ".cortical_data" / "wiki.db"),
        )
        self.db = CorticalWikiDB(db_path or default_db)
        self.crawler = DeterministicMerkleCrawler(self.db)
        self.verifier = CitationVerifier(self.db)

    def handle_request(self, req: dict[str, Any]) -> dict[str, Any] | None:
        method = req.get("method")
        req_id = req.get("id")
        params = req.get("params") or {}

        if method == "notifications/initialized":
            return None

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "cortical-wiki-mcp", "version": "0.1.0"},
                },
            }

        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": MCP_TOOLS},
            }

        if method == "tools/call":
            name = params.get("name")
            args = params.get("arguments") or {}
            try:
                output = self._dispatch_tool(name, args)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(output, indent=2)}],
                        "isError": False,
                    },
                }
            except Exception as exc:  # noqa: BLE001
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": f"Error: {exc}"}],
                        "isError": True,
                    },
                }

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }

    def _dispatch_tool(self, name: str, args: dict[str, Any]) -> Any:
        ctx = AccessContext(
            tenant_id=args.get("tenant_id", "default"),
            workspace_id=args.get("workspace_id", "main"),
            principal_id=args.get("principal_id", "local_owner"),
        )
        if name == "wiki_navigate":
            return self.db.navigate(
                ctx,
                path=args.get("path", "/"),
                depth=DepthTier(args.get("depth", "light")),
                include_children=bool(args.get("include_children", True)),
            )
        if name == "wiki_search":
            return self.db.search(
                ctx,
                query=args["query"],
                depth=DepthTier(args.get("depth", "medium")),
                limit=int(args.get("limit", 10)),
            )
        if name == "wiki_crawl_delta":
            stats = self.crawler.crawl_directory(args["root_dir"], ctx=ctx)
            return dataclasses.asdict(stats)
        if name == "wiki_verify_citation":
            res = self.verifier.verify_and_record(
                ctx,
                claim_text=args["claim_text"],
                source_path=args["source_path"],
                quoted_span=args["quoted_span"],
            )
            return dataclasses.asdict(res)
        if name == "wiki_record_episode":
            return self.db.record_episode(
                ctx,
                episode_id=args["episode_id"],
                title=args["title"],
                goal=args["goal"],
                outcome_status=args["outcome_status"],
                learned_summary=args["learned_summary"],
                skills_used=args.get("skills_used"),
                relations=args.get("relations"),
            )
        raise ValueError(f"Unknown tool: {name}")


def main() -> None:
    server = CorticalWikiMCPServer()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        req = json.loads(line)
        resp = server.handle_request(req)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
