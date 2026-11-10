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

from ..memory import MemoryCurator
from ..skills_hub import CorticalSkillHub
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
    {
        "name": "wiki_get_knowledge_graph",
        "description": "Return the unified Knowledge Graph (Merkle subtree nodes, active/archived task traces, curated insights, and relational edges) via standard MCP.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "max_nodes": {"type": "integer", "default": 60},
                "principal_id": {"type": "string", "default": "local_owner"},
            },
        },
    },
    {
        "name": "wiki_archive_task",
        "description": "Archive an active task episode, purging isolated working notes and keeping only a compact trace connected to the Knowledge Graph.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "episode_id": {"type": "string"},
                "user_closing_answer": {"type": "string", "default": ""},
                "target_subtree": {"type": "string", "default": "/"},
            },
            "required": ["episode_id"],
        },
    },
    {
        "name": "wiki_delete_task",
        "description": "Permanently delete a task episode, its isolated working notes, and its macro-graph edges.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "episode_id": {"type": "string"},
            },
            "required": ["episode_id"],
        },
    },
    {
        "name": "wiki_enhance_prompt",
        "description": "Enhance a prompt with right-sized 3+1 Wiki Memory (L1/L2/L3/Max) + matched Procedural Skills + recommended Tools + Multi-Agent Team Roster.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "wiki_synthesize_discussion_3plus1",
        "description": "Synthesize a task's discussion at 3+1 levels (L1 Light, L2 Medium, L3 High, +1 Max) and optionally compile a reusable SKILL.md.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "episode_id": {"type": "string"},
                "goal": {"type": "string"},
                "discussion_steps": {"type": "array", "items": {"type": "object"}},
                "user_closing_notes": {"type": "string", "default": ""},
                "evaluate_skill": {"type": "boolean", "default": True},
                "force_create_skill": {"type": "boolean", "default": False},
            },
            "required": ["episode_id", "goal"],
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
        self.curator = MemoryCurator(self.db)
        default_skills = os.environ.get(
            "CORTICAL_SKILLS_DIR",
            str(Path(__file__).resolve().parents[3] / ".pi" / "skills"),
        )
        self.skill_hub = CorticalSkillHub(self.db, default_skills)

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
        if name == "wiki_get_knowledge_graph":
            return self.db.get_knowledge_graph(
                ctx,
                max_nodes=int(args.get("max_nodes", 60)),
            )
        if name == "wiki_archive_task":
            return self.curator.archive_task(
                ctx,
                episode_id=args["episode_id"],
                user_closing_answer=args.get("user_closing_answer", ""),
                target_subtree=args.get("target_subtree", "/"),
            )
        if name == "wiki_delete_task":
            return self.curator.delete_task(ctx, episode_id_optional=args["episode_id"])
        if name == "wiki_enhance_prompt":
            res = self.skill_hub.enhance_prompt(args["prompt"], ctx=ctx)
            return dataclasses.asdict(res)
        if name == "wiki_synthesize_discussion_3plus1":
            ep_id = args["episode_id"]
            goal = args["goal"]
            steps = args.get("discussion_steps") or []
            notes = args.get("user_closing_notes", "")
            synth = self.skill_hub.synthesize_task_discussion_3plus1(
                episode_id=ep_id,
                goal=goal,
                discussion_steps=steps,
                user_closing_notes=notes,
                ctx=ctx,
            )
            skill_eval = None
            if args.get("evaluate_skill", True):
                ev = self.skill_hub.evaluate_and_compile_skill(
                    episode_id=ep_id,
                    goal=goal,
                    lessons_learned=synth["lessons_learned"],
                    discussion_steps=steps,
                    force_create=bool(args.get("force_create_skill", False)),
                    ctx=ctx,
                )
                skill_eval = dataclasses.asdict(ev)
            return {"synthesis_3plus1": synth, "skill_evaluation": skill_eval}
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
