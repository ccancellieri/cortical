"""Cortical Unified Command Line Interface (`cortical`)."""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
from pathlib import Path

from .grounding import (
    extract_browser_intent,
    extract_page_read_intent,
    extract_weather_intent,
    fetch_weather_forecast,
    format_page_reading_response,
    read_active_chrome_page,
    visual_chrome_navigate_and_search,
)
from .hardware.profiler import HardwareProfiler
from .memory import MemoryCurator
from .permissions.gate import AdaptivePermissionGate
from .server import run_live_server
from .skills_hub import CorticalSkillHub
from .voice.engine import CorticalVoiceEngine
from .wiki.crawler import DeterministicMerkleCrawler
from .wiki.db import AccessContext, CorticalWikiDB, DepthTier
from .wiki.fact_check import CitationVerifier


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cortical",
        description="Cortical: Agentic Harness for pi, 4-Tier Merkle Second Brain & Dual-Path Voice Engine.",
    )
    parser.add_argument(
        "--db",
        default=str(Path.home() / ".cortical_data" / "wiki.db"),
        help="Path to Cortical Second Brain SQLite database.",
    )
    parser.add_argument(
        "--perm-db",
        default=str(Path.home() / ".cortical_data" / "permissions.db"),
        help="Path to Adaptive Permission Gate SQLite database.",
    )
    parser.add_argument(
        "--skills-dir",
        default=str(Path(__file__).resolve().parents[2] / ".pi" / "skills"),
        help="Path to Cortical skills directory.",
    )

    sub = parser.add_subparsers(dest="cmd", required=True)

    # 1. doctor / setup
    p_doc = sub.add_parser("doctor", help="Inspect hardware, discover local LLM/STT servers & write .pi config")
    p_doc.add_argument("--out-dir", default=".pi", help="Directory where mcp.json & hardware_profile.json are written")
    p_doc.add_argument("--repo-root", default=".", help="Repository root path")

    # 2. crawl
    p_crawl = sub.add_parser("crawl", help="Run deterministic Merkle-tree delta crawler on a directory")
    p_crawl.add_argument("directory", help="Directory to index")

    # 3. navigate
    p_nav = sub.add_parser("navigate", help="Navigate Merkle tree at depth light|medium|high|max")
    p_nav.add_argument("--path", default="/")
    p_nav.add_argument("--depth", choices=["light", "medium", "high", "max"], default="light")

    # 4. search
    p_search = sub.add_parser("search", help="Search FTS5 Second Brain with RBAC & depth projection")
    p_search.add_argument("query")
    p_search.add_argument("--depth", choices=["light", "medium", "high", "max"], default="medium")

    # 5. verify-citation
    p_ver = sub.add_parser("verify-citation", help="Verify a claim and quoted span against the Second Brain")
    p_ver.add_argument("--claim", required=True)
    p_ver.add_argument("--source", required=True)
    p_ver.add_argument("--span", required=True)

    # 6. check-permission
    p_perm = sub.add_parser("check-permission", help="Evaluate or update Adaptive Permission Gate")
    p_perm.add_argument("--tool", required=True)
    p_perm.add_argument("--args-json", default="{}")
    p_perm.add_argument("--approve", action="store_true")
    p_perm.add_argument("--deny", action="store_true")
    p_perm.add_argument("--remember", action="store_true")

    # 7. voice-eval
    p_voice = sub.add_parser("voice-eval", help="Evaluate a voice utterance through Cortical Dual-Path Voice Engine")
    p_voice.add_argument("utterance")

    # 8. weather (Real-Time Weather & Chrome Grounding)
    p_weather = sub.add_parser("weather", help="Fetch real-time weather forecast and optionally open Chrome")
    p_weather.add_argument("--city", default="Roma")
    p_weather.add_argument("--day-offset", type=int, default=1)
    p_weather.add_argument("--query", default="")
    p_weather.add_argument("--open-chrome", action="store_true")

    # 9. enhance-prompt (Skill & 3+1 Memory Router for pi)
    p_enh = sub.add_parser("enhance-prompt", help="Enhance prompt with 3+1 Wiki Memory, matched Skills, and Team Roster")
    p_enh.add_argument("--prompt", required=True)

    # 10. task-open (Explicit Multi-Agent Task Creation from pi or CLI)
    p_topen = sub.add_parser("task-open", help="Open an explicit task episode in the Second Brain")
    p_topen.add_argument("--goal", required=True)
    p_topen.add_argument("--episode-id", default="")

    # 11. task-close (Synthesize 3+1 Discussion Memory + Evaluate Skill + Archive Task)
    p_tclose = sub.add_parser("task-close", help="Close and archive a task, saving 3+1 synthesis and evaluating skill creation")
    p_tclose.add_argument("--episode-id", required=True)
    p_tclose.add_argument("--goal", default="")
    p_tclose.add_argument("--notes", default="")
    p_tclose.add_argument("--steps-json", default="[]")
    p_tclose.add_argument("--force-skill", action="store_true")

    # 12. task-delete (Permanently delete a task)
    p_tdel = sub.add_parser("task-delete", help="Permanently delete a task episode and its working notes")
    p_tdel.add_argument("--episode-id", required=True)

    # 13. skills-list (List Core, 3+1 Memory Tier, and Learned Skills)
    sub.add_parser("skills-list", help="List all active Cortical skills")

    # 14. context-attach (Attach File, Folder, Skill, or Plugin to Chat/Task Context)
    p_catt = sub.add_parser("context-attach", help="Attach a file, folder, skill, or plugin to a chat/task context")
    p_catt.add_argument("--scope-id", default="chat")
    p_catt.add_argument("--item-type", required=True, choices=["file", "folder", "skill", "plugin"])
    p_catt.add_argument("--item-ref", required=True)
    p_catt.add_argument("--depth", default="medium", choices=["light", "medium", "high", "max"])

    # 15. context-detach (Remove an attachment from Chat/Task Context)
    p_cdet = sub.add_parser("context-detach", help="Detach an item from a chat/task context")
    p_cdet.add_argument("--attachment-id", required=True)

    # 16. context-list (List active context attachments)
    p_clist = sub.add_parser("context-list", help="List active context attachments")
    p_clist.add_argument("--scope-id", default="")

    # 17. concept-config (Configure a framework or user concept)
    p_ccfg = sub.add_parser("concept-config", help="Update configuration parameters for a concept")
    p_ccfg.add_argument("--concept-id", required=True)
    p_ccfg.add_argument("--config-json", default="{}")

    # 18. concept-delete (Delete a user-developed concept)
    p_cdel = sub.add_parser("concept-delete", help="Delete a user-developed concept from memory")
    p_cdel.add_argument("--node-id", required=True)

    # 19. chrome-search (Visual Chrome Navigation & DOM Form Submission)
    p_csearch = sub.add_parser("chrome-search", help="Open Google Chrome in focus, fill search form and submit")
    p_csearch.add_argument("--site", default="")
    p_csearch.add_argument("--query", default="")
    p_csearch.add_argument("--url", default="")
    p_csearch.add_argument("--prompt", default="")
    p_csearch.add_argument("--background", action="store_true")

    # 20. chrome-read (Read or Summarize Open Active Chrome Tab)
    p_cread = sub.add_parser("chrome-read", help="Read and optionally summarize the active Chrome tab")
    p_cread.add_argument("--mode", choices=["read", "summarize"], default="summarize")

    # 21. serve (Live HTTP + Voice + Second Brain Daemon)
    p_serve = sub.add_parser("serve", help="Run the live Cortical HTTP, Voice & Second Brain service")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8765)

    args = parser.parse_args(argv)

    if args.cmd == "doctor":
        profiler = HardwareProfiler()
        summary = profiler.generate_pi_configs(args.out_dir, args.repo_root)
        print(json.dumps(summary, indent=2))
        return 0

    if args.cmd == "crawl":
        db = CorticalWikiDB(args.db)
        crawler = DeterministicMerkleCrawler(db)
        stats = crawler.crawl_directory(args.directory)
        print(json.dumps(dataclasses.asdict(stats), indent=2))
        return 0

    if args.cmd == "navigate":
        db = CorticalWikiDB(args.db)
        res = db.navigate(AccessContext(), path=args.path, depth=DepthTier(args.depth))
        print(json.dumps(res, indent=2))
        return 0

    if args.cmd == "search":
        db = CorticalWikiDB(args.db)
        res = db.search(AccessContext(), query=args.query, depth=DepthTier(args.depth))
        print(json.dumps(res, indent=2))
        return 0

    if args.cmd == "verify-citation":
        db = CorticalWikiDB(args.db)
        verifier = CitationVerifier(db)
        res = verifier.verify_and_record(
            AccessContext(),
            claim_text=args.claim,
            source_path=args.source,
            quoted_span=args.span,
        )
        print(json.dumps(dataclasses.asdict(res), indent=2))
        return 0

    if args.cmd == "check-permission":
        gate = AdaptivePermissionGate(args.perm_db)
        tool_args = json.loads(args.args_json)
        if args.approve or args.deny:
            dec = gate.record_user_feedback(
                args.tool,
                tool_args,
                approved=bool(args.approve and not args.deny),
                remember_always=args.remember,
            )
        else:
            dec = gate.evaluate(args.tool, tool_args)
        print(json.dumps(dataclasses.asdict(dec), indent=2))
        return 0

    if args.cmd == "voice-eval":
        db = CorticalWikiDB(args.db)
        gate = AdaptivePermissionGate(args.perm_db)
        voice = CorticalVoiceEngine(wiki_db=db, permission_gate=gate)
        res = voice.handle_utterance(args.utterance)
        print(json.dumps(dataclasses.asdict(res), indent=2))
        return 0

    if args.cmd == "weather":
        city = args.city
        day_offset = args.day_offset
        if args.query:
            intent = extract_weather_intent(args.query)
            if intent:
                city = intent["city"]
                day_offset = intent["day_offset"]
        res = fetch_weather_forecast(
            city=city,
            day_offset=day_offset,
            open_chrome=bool(args.open_chrome),
        )
        print(json.dumps(res, indent=2))
        return 0

    if args.cmd == "enhance-prompt":
        db = CorticalWikiDB(args.db)
        hub = CorticalSkillHub(db, args.skills_dir)
        res = hub.enhance_prompt(args.prompt)
        print(json.dumps(dataclasses.asdict(res), indent=2))
        return 0

    if args.cmd == "task-open":
        db = CorticalWikiDB(args.db)
        hub = CorticalSkillHub(db, args.skills_dir)
        ep_id = args.episode_id or f"pi-{int(time.time() * 1000) % 1000000}"
        enh = hub.enhance_prompt(args.goal)
        db.record_episode(
            AccessContext(),
            episode_id=ep_id,
            title=f"[{ep_id}] {args.goal[:52]}",
            goal=args.goal,
            outcome_status="active",
            learned_summary="Task multi-agente attivo in pi.",
            skills_used=[s["skill_id"] for s in enh.selected_skills],
            relations=[{"relation": "relates_to", "target_type": "subtree", "target_id": "/"}],
        )
        print(
            json.dumps(
                {
                    "episode_id": ep_id,
                    "goal": args.goal,
                    "status": "active",
                    "enhancement": dataclasses.asdict(enh),
                },
                indent=2,
            )
        )
        return 0

    if args.cmd == "task-close":
        db = CorticalWikiDB(args.db)
        curator = MemoryCurator(db)
        hub = CorticalSkillHub(db, args.skills_dir)
        steps = json.loads(args.steps_json)
        goal = args.goal or f"Task {args.episode_id}"
        synth = hub.synthesize_task_discussion_3plus1(
            episode_id=args.episode_id,
            goal=goal,
            discussion_steps=steps,
            user_closing_notes=args.notes,
        )
        skill_eval = hub.evaluate_and_compile_skill(
            episode_id=args.episode_id,
            goal=goal,
            lessons_learned=synth["lessons_learned"],
            discussion_steps=steps,
            force_create=bool(args.force_skill),
        )
        arch = curator.archive_task(args.episode_id, user_closing_notes=synth["light"])
        print(
            json.dumps(
                {
                    "archived": arch,
                    "synthesis_3plus1": synth,
                    "skill_evaluation": dataclasses.asdict(skill_eval),
                },
                indent=2,
            )
        )
        return 0

    if args.cmd == "task-delete":
        db = CorticalWikiDB(args.db)
        curator = MemoryCurator(db)
        res = curator.delete_task(args.episode_id)
        print(json.dumps(res, indent=2))
        return 0

    if args.cmd == "skills-list":
        db = CorticalWikiDB(args.db)
        hub = CorticalSkillHub(db, args.skills_dir)
        skills = [dataclasses.asdict(s) for s in hub.list_skills()]
        print(json.dumps({"skills": skills}, indent=2))
        return 0

    if args.cmd == "context-attach":
        db = CorticalWikiDB(args.db)
        res = db.attach_context_item(
            AccessContext(),
            scope_id=args.scope_id,
            item_type=args.item_type,
            item_ref=args.item_ref,
            depth_tier=args.depth,
        )
        print(json.dumps(res, indent=2))
        return 0

    if args.cmd == "context-detach":
        db = CorticalWikiDB(args.db)
        res = db.detach_context_item(AccessContext(), attachment_id=args.attachment_id)
        print(json.dumps(res, indent=2))
        return 0

    if args.cmd == "context-list":
        db = CorticalWikiDB(args.db)
        res = db.list_context_attachments(AccessContext(), scope_id=args.scope_id or None)
        print(json.dumps({"attachments": res}, indent=2))
        return 0

    if args.cmd == "concept-config":
        db = CorticalWikiDB(args.db)
        updates = json.loads(args.config_json)
        res = db.update_concept_config(AccessContext(), args.concept_id, updates)
        print(json.dumps(res, indent=2))
        return 0

    if args.cmd == "concept-delete":
        db = CorticalWikiDB(args.db)
        res = db.delete_concept_node(AccessContext(), args.node_id)
        print(json.dumps(res, indent=2))
        return 0

    if args.cmd == "chrome-search":
        site = args.site or None
        query = args.query or None
        url = args.url or None
        focus = not bool(args.background)
        if args.prompt:
            intent = extract_browser_intent(args.prompt)
            if intent:
                site = site or intent.get("site")
                query = query or intent.get("query")
                url = url or intent.get("url")
                focus = bool(intent.get("focus", focus))
        res = visual_chrome_navigate_and_search(site=site, query=query, url=url, focus=focus)
        print(json.dumps(res, indent=2))
        return 0

    if args.cmd == "chrome-read":
        page = read_active_chrome_page()
        summary = format_page_reading_response(page, mode=args.mode)
        print(json.dumps({**page, "mode": args.mode, "summary_it": summary}, indent=2))
        return 0

    if args.cmd == "serve":
        run_live_server(
            host=args.host,
            port=args.port,
            wiki_db_path=args.db,
            perm_db_path=args.perm_db,
        )
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
