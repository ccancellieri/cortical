"""Standard Model Context Protocol (MCP) Server for Cortical Second Brain (`cortical-wiki-mcp`).

Implements JSON-RPC 2.0 over stdio so `pi` (via `.pi/agent/mcp.json`) or any MCP host
can deterministically navigate, search, crawl, fact-check, and record task episodes.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from ..grounding import (
    ensure_chrome_debug_instance,
    extract_weather_intent,
    fetch_weather_forecast,
    format_page_reading_response,
    open_url_via_cdp_http,
    read_active_chrome_page,
    visual_chrome_navigate_and_search,
)
from ..memory import MemoryCurator
from ..permissions.gate import AdaptivePermissionGate
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
    {
        "name": "chrome_ensure_debug",
        "description": "Ensure a debuggable Chrome instance on 127.0.0.1:9222 is active (reuses running instance or spawns an isolated one) and optionally opens a URL.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "port": {"type": "integer", "default": 9222},
                "url": {"type": "string", "default": ""},
                "background": {"type": "boolean", "default": False},
            },
        },
    },
    {
        "name": "chrome_navigate_search",
        "description": "Open a website in Chrome remote-debugging instance and optionally fill/submit a search query.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "site": {"type": "string", "default": ""},
                "query": {"type": "string", "default": ""},
                "url": {"type": "string", "default": ""},
                "focus": {"type": "boolean", "default": True},
                "lang": {"type": "string", "default": "auto"},
            },
        },
    },
    {
        "name": "chrome_read_active_page",
        "description": "Read or summarize the active Chrome tab content (IT/EN).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["read", "summarize"], "default": "summarize"},
                "lang": {"type": "string", "default": "it"},
            },
        },
    },
    {
        "name": "weather_forecast",
        "description": "Fetch verified real-time weather forecast (Open-Meteo) for a city and day offset (0=today, 1=tomorrow).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "default": "Roma"},
                "day_offset": {"type": "integer", "default": 1},
                "query": {"type": "string", "default": ""},
                "open_chrome": {"type": "boolean", "default": False},
            },
        },
    },
    {
        "name": "wiki_upsert_concept",
        "description": (
            "Create or update a Second Brain concept configuration and optionally persist a 4-tier "
            "memory node (L1 light, L2 medium, L3 high, +1 max raw) in the deterministic wiki."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "concept_id": {"type": "string"},
                "updates": {"type": "object", "default": {}},
                "path": {"type": "string", "default": ""},
                "summary_light": {"type": "string", "default": ""},
                "summary_medium": {"type": "string", "default": ""},
                "summary_high": {"type": "string", "default": ""},
                "raw_content": {"type": "string", "default": ""},
                "principal_id": {"type": "string", "default": "local_owner"},
            },
            "required": ["concept_id"],
        },
    },
    {
        "name": "wiki_get_egress_audit",
        "description": "Inspect blocked outbound network/secret egress attempts recorded by Cortical's security gate.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 20},
            },
        },
    },
    {
        "name": "wiki_create_research_doc",
        "description": (
            "Compile a structured Markdown research document from Chrome/web findings, save it safely under "
            "docs/research/ (or a workspace subdir), and index all 4 tiers (L1-L3+1) in the Second Brain."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "slug": {"type": "string", "default": ""},
                "summary_l1": {"type": "string", "default": ""},
                "summary_l2": {"type": "string", "default": ""},
                "summary_l3": {"type": "string", "default": ""},
                "sections": {"type": "array", "items": {"type": "object"}, "default": []},
                "sources": {"type": "array", "items": {"type": "object"}, "default": []},
                "output_dir": {"type": "string", "default": "docs/research"},
                "principal_id": {"type": "string", "default": "local_owner"},
            },
            "required": ["title", "sections"],
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
        repo_root = Path(__file__).resolve().parents[3]
        self.repo_root = repo_root
        agents_skills = repo_root / ".agents" / "skills"
        legacy_skills = repo_root / ".pi" / "skills"
        resolved_default_skills = str(
            agents_skills if (agents_skills.exists() or not legacy_skills.exists()) else legacy_skills
        )
        default_skills = os.environ.get("CORTICAL_SKILLS_DIR", resolved_default_skills)
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
        if name == "chrome_ensure_debug":
            res = ensure_chrome_debug_instance(
                port=args.get("port"),
                background=bool(args.get("background", False)),
            )
            url_arg = str(args.get("url") or "").strip()
            if res.get("active") and url_arg:
                res["opened_tab"] = open_url_via_cdp_http(url_arg, port=res.get("port"))
            return res
        if name == "chrome_navigate_search":
            return visual_chrome_navigate_and_search(
                site=args.get("site") or None,
                query=args.get("query") or None,
                url=args.get("url") or None,
                focus=bool(args.get("focus", True)),
                lang=str(args.get("lang") or "auto"),
            )
        if name == "chrome_read_active_page":
            page = read_active_chrome_page()
            mode = str(args.get("mode") or "summarize")
            lang = str(args.get("lang") or "it")
            return {**page, "mode": mode, "summary": format_page_reading_response(page, mode=mode, lang=lang)}
        if name == "weather_forecast":
            city = str(args.get("city") or "Roma")
            day_offset = int(args.get("day_offset", 1))
            q_txt = str(args.get("query") or "").strip()
            if q_txt:
                intent = extract_weather_intent(q_txt)
                if intent:
                    city = intent["city"]
                    day_offset = intent["day_offset"]
            return fetch_weather_forecast(
                city=city,
                day_offset=day_offset,
                open_chrome=bool(args.get("open_chrome", False)),
            )
        if name == "wiki_upsert_concept":
            cid = str(args["concept_id"]).strip()
            updates = args.get("updates") if isinstance(args.get("updates"), dict) else {}
            res = self.db.update_concept_config(ctx, cid, updates)
            node_path = str(args.get("path") or "").strip()
            raw_content = str(args.get("raw_content") or "")
            if node_path and (raw_content or args.get("summary_light") or args.get("summary_medium") or args.get("summary_high")):
                raw_txt = raw_content or str(args.get("summary_high") or args.get("summary_medium") or args.get("summary_light") or "")
                chash = hashlib.sha256(raw_txt.encode("utf-8")).hexdigest()
                s_light = str(args.get("summary_light") or raw_txt[:160])
                s_med = str(args.get("summary_medium") or raw_txt[:600])
                s_high = str(args.get("summary_high") or raw_txt[:2000])
                self.db.upsert_merkle_node(
                    ctx,
                    path=node_path,
                    parent_path="/".join(node_path.split("/")[:-1]) or "/",
                    node_type="file",
                    content_hash=chash,
                    subtree_hash=chash,
                    summary_light=s_light,
                    summary_medium=s_med,
                    summary_high=s_high,
                    raw_content=raw_txt,
                )
                res["node_path"] = node_path
            return res
        if name == "wiki_get_egress_audit":
            gate = AdaptivePermissionGate(self.db.db_path)
            events = gate.list_egress_events(limit=int(args.get("limit", 20)))
            return {"count": len(events), "events": events}
        if name == "wiki_create_research_doc":
            title = str(args["title"]).strip()
            raw_slug = str(args.get("slug") or title).strip().lower()
            safe_slug = re.sub(r"[^a-z0-9_-]+", "-", raw_slug).strip("-") or "research-doc"
            rel_dir = str(args.get("output_dir") or "docs/research").strip()
            base_root = self.repo_root.resolve()
            target_dir = (base_root / rel_dir).resolve()
            if not str(target_dir).startswith(str(base_root)):
                raise ValueError(f"Unsafe output_dir outside workspace: {rel_dir}")
            target_dir.mkdir(parents=True, exist_ok=True)
            doc_path = target_dir / f"{safe_slug}.md"

            sections = args.get("sections") or []
            sources = args.get("sources") or []
            s_l1 = str(args.get("summary_l1") or f"Research brief: {title}")[:200]
            s_l2 = str(args.get("summary_l2") or s_l1)[:600]
            lines = [f"# {title}", "", f"> **Executive Summary (L1):** {s_l1}", ""]
            if s_l2 and s_l2 != s_l1:
                lines.extend(["## Overview", "", s_l2, ""])
            for sec in sections:
                if isinstance(sec, dict):
                    hd = str(sec.get("heading") or "Section").strip()
                    bd = str(sec.get("body") or "").strip()
                    lines.extend([f"## {hd}", "", bd, ""])
                elif isinstance(sec, str) and sec.strip():
                    lines.extend([sec.strip(), ""])
            if sources:
                lines.extend(["## Sources", ""])
                for src in sources:
                    if isinstance(src, dict):
                        stitle = str(src.get("title") or src.get("url") or "Source").strip()
                        surl = str(src.get("url") or "").strip()
                        snip = str(src.get("snippet") or "").strip()
                        bullet = f"- [{stitle}]({surl})" if surl else f"- {stitle}"
                        if snip:
                            bullet += f" — {snip}"
                        lines.append(bullet)
                    else:
                        lines.append(f"- {src}")
                lines.append("")
            raw_md = "\n".join(lines).strip() + "\n"
            doc_path.write_text(raw_md, encoding="utf-8")

            s_l3 = str(args.get("summary_l3") or raw_md[:2000])
            chash = hashlib.sha256(raw_md.encode("utf-8")).hexdigest()
            wiki_node_path = f"/{rel_dir.strip('/')}/{safe_slug}.md"
            try:
                self.db.grant_permission(ctx.tenant_id, ctx.workspace_id, ctx.principal_id, "/", can_write=True)
            except Exception:  # noqa: BLE001
                pass
            self.db.upsert_merkle_node(
                ctx,
                path=wiki_node_path,
                parent_path=f"/{rel_dir.strip('/')}",
                node_type="file",
                content_hash=chash,
                subtree_hash=chash,
                summary_light=s_l1,
                summary_medium=s_l2,
                summary_high=s_l3,
                raw_content=raw_md,
            )
            return {
                "status": "created",
                "file_path": str(doc_path),
                "wiki_path": wiki_node_path,
                "bytes": len(raw_md.encode("utf-8")),
                "tiers_indexed": ["light", "medium", "high", "max"],
            }
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
