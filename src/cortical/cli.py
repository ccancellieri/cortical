"""Cortical Unified Command Line Interface (`cortical`)."""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
from pathlib import Path

from .grounding import (
    ensure_chrome_debug_instance,
    extract_browser_intent,
    extract_page_read_intent,
    extract_url_page_and_forms,
    extract_weather_intent,
    fetch_weather_forecast,
    fill_form_in_chrome_or_playwright,
    format_page_reading_response,
    open_url_via_cdp_http,
    read_active_chrome_page,
    visual_chrome_navigate_and_search,
)
from .hardware.profiler import HardwareProfiler
from .memory import MemoryCurator
from .permissions.gate import AdaptivePermissionGate
from .portability import export_cortical_bundle, import_cortical_bundle, list_usb_volumes
from .remote_gateway import CorticalRemoteGateway
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
    repo_root = Path(__file__).resolve().parents[2]
    default_skills = repo_root / ".agents" / "skills"
    if not default_skills.exists() and (repo_root / ".pi" / "skills").exists():
        default_skills = repo_root / ".pi" / "skills"
    parser.add_argument(
        "--skills-dir",
        default=str(default_skills),
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
    p_crawl.add_argument("--llm", action="store_true", help="Use local Ollama for 3-tier semantic concept summaries")

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

    # 21. chrome-ensure (Ensure Unified Chrome Remote Debug Instance)
    p_cens = sub.add_parser("chrome-ensure", help="Reuse or launch an isolated Chrome Remote Debugging instance")
    p_cens.add_argument("--port", type=int, default=None)
    p_cens.add_argument("--url", default="")
    p_cens.add_argument("--background", action="store_true")

    # 21b. chrome-extract & chrome-fill (Structured DOM / Form Extraction & Filling)
    p_cext = sub.add_parser("chrome-extract", help="Fetch a URL via Chrome CDP/Playwright/HTTP and extract text, links & form fields")
    p_cext.add_argument("--url", required=True)

    p_cfill = sub.add_parser("chrome-fill", help="Fill form fields and optional file upload on a URL via Chrome CDP/Playwright")
    p_cfill.add_argument("--url", required=True)
    p_cfill.add_argument("--fields-json", required=True)
    p_cfill.add_argument("--upload", default="")
    p_cfill.add_argument("--submit", action="store_true")

    # 22. serve (Live HTTP + Voice + Second Brain Daemon)
    p_serve = sub.add_parser("serve", help="Run the live Cortical HTTP, Voice & Second Brain service")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8765)

    # 23. gateway (Optional Remote Gateway Key, Accounts, Tunnel & Invite CLI)
    p_gw = sub.add_parser("gateway", help="Manage optional Remote Gateway Key, Accounts (max_users), Tunnel & Invites")
    p_gw.add_argument("action", choices=["status", "config", "expose", "stop", "invite", "duckdns"], default="status")
    p_gw.add_argument("--port", type=int, default=8765)
    p_gw.add_argument("--provider", default="auto", choices=["auto", "localhost.run", "cloudflared", "pinggy"])
    p_gw.add_argument("--auth-enabled", choices=["true", "false"], default=None)
    p_gw.add_argument("--allow-localhost", choices=["true", "false"], default=None)
    p_gw.add_argument("--max-users", type=int, default=None)
    p_gw.add_argument("--rotate-key", action="store_true")
    p_gw.add_argument("--include-secret", action="store_true")
    p_gw.add_argument("--email", default="ccancellieri@hotmail.com")
    p_gw.add_argument("--public-url", default="")
    p_gw.add_argument("--duckdns-domain", default="")
    p_gw.add_argument("--duckdns-token", default=None)

    # 24. export / import (Portable USB Migration Bundle)
    p_exp = sub.add_parser("export", help="Export Cortical memory, tasks, chats & skills to a portable .tar.gz bundle (e.g. USB)")
    p_exp.add_argument("--output", default="", help="Destination .tar.gz path or USB folder (e.g. /Volumes/USB)")
    p_exp.add_argument("--volumes", action="store_true", help="List detected USB/external volumes and exit")

    p_imp = sub.add_parser("import", help="Import a Cortical .tar.gz backup bundle onto this machine")
    p_imp.add_argument("--input", required=True, help="Source .tar.gz bundle path")
    p_imp.add_argument("--mode", default="merge", choices=["merge", "replace"])

    p_tok = sub.add_parser("token-report", help="Generate zero-cloud-token local + remote usage & ROI report")
    p_tok.add_argument("--episode-id", default=None, help="Filter local runs by Cortical episode_id")
    p_tok.add_argument("--conversation-id", default=None, help="Filter remote transcript by conversation_id")
    p_tok.add_argument("--brain-dir", default=None, help="Custom Antigravity brain directory path")
    p_tok.add_argument("--narrative", action="store_true", help="Orchestrate concise ROI summary via local Ollama LLM")
    p_tok.add_argument("--lang", default=None, help="Report language: auto, it, en, es")
    p_tok.add_argument("--full", action="store_true", help="Print full multi-section global history instead of compact turn-only summary")
    p_tok.add_argument("--html", nargs="?", const="html/token_report.html", default=None, help="Export static HTML dashboard (default: html/token_report.html)")
    p_tok.add_argument("--open", action="store_true", help="Open generated HTML dashboard in default browser")
    p_tok.add_argument("--json", action="store_true", help="Output raw JSON instead of Markdown")

    p_wdb = sub.add_parser("wiki-dashboard", help="Export zero-server static Wiki Explorer & Maintenance HTML")
    p_wdb.add_argument("--output", default="html/wiki.html", help="Destination HTML path")
    p_wdb.add_argument("--open", action="store_true", help="Open generated Wiki HTML in default browser")

    p_wap = sub.add_parser("wiki-apply", help="Apply offline maintenance JSON patch exported from static Wiki Dashboard")
    p_wap.add_argument("patch", help="Path to wiki_maintenance_patch.json")

    p_wdis = sub.add_parser("wiki-distill", help="Distill knowledge from a subtree/context/episode via local LLM and discard heavy L4 Max blobs")
    p_wdis.add_argument("--target", required=True, help="Target ID or prefix (e.g. /src/cortical, root:private_notes, or episode_id)")
    p_wdis.add_argument("--kind", default="subtree", choices=["subtree", "context_root", "episode", "topic"], help="Target kind")
    p_wdis.add_argument("--keep-tier", default="l2", choices=["l1", "l2", "l3"], help="Tier depth to keep while discarding L4 Max")
    p_wdis.add_argument("--no-llm", action="store_true", help="Skip local LLM call and use deterministic distillation")

    p_san = sub.add_parser("sanitize", help="Strip metadata & pseudonymize/anonymize a file locally before cloud LLM use")
    p_san.add_argument("file", help="Path to source file (.txt, .md, .docx, .xlsx, .pdf, etc.)")
    p_san.add_argument("--profile", default=None, help="Privacy profile from cortical.config.json (max_security, low, medium, max_context, or custom)")
    p_san.add_argument("--out", default=None, help="Optional output file path for sanitized text")
    p_san.add_argument("--llm", action="store_true", help="Also rewrite GDPR quasi-identifiers via offline local LLM")
    p_san.add_argument("--redact", action="store_true", help="Use [REDACTED] instead of consistent [PERSON_1]/[EMAIL_1] pseudonyms")
    p_san.add_argument("--json", action="store_true", help="Output JSON summary (excluding local pseudonym map)")

    p_set = sub.add_parser("settings-dashboard", help="Export zero-server static Configuration Form HTML (html/settings.html)")
    p_set.add_argument("--output", default="html/settings.html", help="Destination HTML path")
    p_set.add_argument("--open", action="store_true", help="Open generated settings HTML in default browser")

    p_tpr = sub.add_parser("token-prune", help="Prune old granular agent_runs or reset counters")
    p_tpr.add_argument("--days", type=int, default=90, help="Retention window in days (default: 90)")
    p_tpr.add_argument("--reset", action="store_true", help="Reset all granular agent_runs counters")

    p_loop = sub.add_parser("local-loop", help="Run multi-model iterative local reasoning loop with @wiki/@concept/@skill refs & privacy sanitization")
    p_loop.add_argument("prompt", help="Task/question (supports @wiki:, @concept:, @skill:, @insight:, @root:, /local, /privacy:...)")
    p_loop.add_argument("--models", default="", help="Comma-separated local models chain (default from cortical.config.json local_loop)")
    p_loop.add_argument("--loops", type=int, default=3, help="Number of local refinement passes (default: 3)")
    p_loop.add_argument("--privacy", default=None, help="Privacy profile (max_security, low, medium, max_context)")
    p_loop.add_argument("--file", "--attach", dest="attach_files", action="append", default=None, help="Sensitive file(s) to sanitize locally (repeatable or comma-separated)")
    p_loop.add_argument("--max-tokens", type=int, default=1200, help="Max output tokens per local pass (default: 1200)")
    p_loop.add_argument("--context-chars", type=int, default=16000, help="Context character budget across attached files and Wiki refs (default: 16000)")
    p_loop.add_argument("--timeout", type=float, default=90.0, help="Per-pass runner timeout in seconds (default: 90.0)")
    p_loop.add_argument("--force-local", action="store_true", help="Block remote cloud forwarding even for complex tasks")
    p_loop.add_argument("--json", action="store_true", help="Print full JSON result instead of Markdown summary")

    args = parser.parse_args(argv)
    if ".cortical_data" in str(getattr(args, "db", "")):
        try:
            from .wiki_static import auto_apply_pending_wiki_patch

            auto_apply_pending_wiki_patch(CorticalWikiDB(args.db), repo_root=Path("."))
        except Exception:  # noqa: BLE001
            pass

    if args.cmd == "doctor":
        profiler = HardwareProfiler()
        summary = profiler.generate_pi_configs(args.out_dir, args.repo_root)
        print(json.dumps(summary, indent=2))
        return 0

    if args.cmd == "crawl":
        db = CorticalWikiDB(args.db)
        summarizer = None
        if getattr(args, "llm", False):
            from .wiki.crawler import make_ollama_3tier_summarizer

            summarizer = make_ollama_3tier_summarizer()
        crawler = DeterministicMerkleCrawler(db, summarizer=summarizer)
        stats = crawler.crawl_directory(args.directory)
        out = dataclasses.asdict(stats)
        html_dir = Path("html")
        if html_dir.is_dir() and ".cortical_data" in str(args.db):
            from .wiki_static import export_static_wiki_dashboard

            out["wiki_dashboard"] = export_static_wiki_dashboard(db, html_dir / "wiki.html")
        print(json.dumps(out, indent=2))
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
        use_local = bool(".cortical_data" in str(args.db))
        synth = hub.synthesize_task_discussion_3plus1(
            episode_id=args.episode_id,
            goal=goal,
            discussion_steps=steps,
            user_closing_notes=args.notes,
            use_local_llm=use_local,
        )
        skill_eval = hub.evaluate_and_compile_skill(
            episode_id=args.episode_id,
            goal=goal,
            lessons_learned=synth["lessons_learned"],
            discussion_steps=steps,
            force_create=bool(args.force_skill),
            use_local_llm=use_local,
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

    if args.cmd == "chrome-ensure":
        res = ensure_chrome_debug_instance(port=args.port, background=bool(args.background))
        if res.get("active") and args.url:
            tab = open_url_via_cdp_http(args.url, port=res.get("port"))
            res["opened_tab"] = tab
        print(json.dumps(res, indent=2))
        return 0 if res.get("active") else 1

    if args.cmd == "chrome-extract":
        res = extract_url_page_and_forms(args.url)
        print(json.dumps(res, indent=2))
        return 0 if res.get("ok") else 1

    if args.cmd == "chrome-fill":
        fields = json.loads(args.fields_json)
        res = fill_form_in_chrome_or_playwright(
            args.url,
            fields if isinstance(fields, dict) else {},
            upload_file=args.upload,
            submit=bool(args.submit),
        )
        print(json.dumps(res, indent=2))
        return 0 if res.get("ok") else 1

    if args.cmd == "serve":
        run_live_server(
            host=args.host,
            port=args.port,
            wiki_db_path=args.db,
            perm_db_path=args.perm_db,
        )
        return 0

    if args.cmd == "gateway":
        gw = CorticalRemoteGateway(args.db, local_port=args.port)
        if args.action == "status":
            print(json.dumps(gw.get_status(include_secret=bool(args.include_secret)), indent=2))
            return 0
        if args.action == "config":
            upd: dict[str, object] = {}
            if args.auth_enabled is not None:
                upd["auth_enabled"] = args.auth_enabled == "true"
            if args.allow_localhost is not None:
                upd["allow_localhost_bypass"] = args.allow_localhost == "true"
            if args.max_users is not None:
                upd["max_users"] = args.max_users
            if args.rotate_key:
                upd["rotate_key"] = True
            if args.duckdns_domain:
                upd["duckdns_domain"] = args.duckdns_domain
            if args.duckdns_token is not None:
                upd["duckdns_token"] = args.duckdns_token
            if args.public_url:
                upd["public_gateway_url"] = args.public_url
            print(json.dumps(gw.configure(upd), indent=2))
            return 0
        if args.action == "expose":
            res = gw.start_tunnel(provider=args.provider, local_port=args.port)
            print(json.dumps(res, indent=2))
            return 0 if res.get("ok") else 1
        if args.action == "stop":
            print(json.dumps(gw.stop_tunnel(), indent=2))
            return 0
        if args.action == "duckdns":
            res = gw.update_duckdns(
                domain=args.duckdns_domain or None,
                token=args.duckdns_token,
            )
            print(json.dumps(res, indent=2))
            return 0 if res.get("ok") else 1
        if args.action == "invite":
            res = gw.send_access_email(
                recipient_email=args.email,
                base_public_url=args.public_url or None,
            )
            print(json.dumps(res, indent=2))
            return 0

    if args.cmd == "export":
        if args.volumes:
            print(json.dumps({"volumes": list_usb_volumes()}, indent=2))
            return 0
        res = export_cortical_bundle(
            args.output or None,
            wiki_db_path=args.db,
            permissions_db_path=args.perm_db,
            skills_dir=args.skills_dir,
        )
        print(json.dumps(res, indent=2))
        return 0 if res.get("ok") else 1

    if args.cmd == "import":
        res = import_cortical_bundle(
            args.input,
            mode=args.mode,
            wiki_db_path=args.db,
            permissions_db_path=args.perm_db,
            skills_dir=args.skills_dir,
        )
        print(json.dumps(res, indent=2))
        return 0 if res.get("ok") else 1

    if args.cmd == "token-report":
        from .token_analytics import (
            build_token_report,
            export_static_token_dashboard,
            format_token_report_markdown,
        )

        db = CorticalWikiDB(args.db)
        report = build_token_report(
            db,
            episode_id=args.episode_id,
            conversation_id=args.conversation_id,
            brain_dir=Path(args.brain_dir) if args.brain_dir else None,
            include_narrative=bool(args.narrative),
            lang=getattr(args, "lang", None),
        )
        html_out = export_static_token_dashboard(report, Path(args.html)) if args.html else None
        if html_out is not None and getattr(args, "open", False):
            import webbrowser

            webbrowser.open(html_out.resolve().as_uri())
        if args.json:
            if html_out is not None:
                report["html_dashboard_path"] = str(html_out.resolve())
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            print(
                format_token_report_markdown(
                    report,
                    dashboard_path=html_out,
                    lang=getattr(args, "lang", None),
                    turn_only=not getattr(args, "full", False),
                )
            )
        return 0

    if args.cmd == "wiki-dashboard":
        from .wiki_static import export_static_wiki_dashboard

        db = CorticalWikiDB(args.db)
        res = export_static_wiki_dashboard(db, Path(args.output))
        if getattr(args, "open", False):
            import webbrowser

            webbrowser.open(Path(args.output).resolve().as_uri())
        print(json.dumps(res, indent=2))
        return 0

    if args.cmd == "wiki-apply":
        from .wiki_static import apply_wiki_maintenance_patch, export_static_wiki_dashboard

        db = CorticalWikiDB(args.db)
        patch = json.loads(Path(args.patch).read_text(encoding="utf-8"))
        res = apply_wiki_maintenance_patch(db, patch)
        html_dir = Path("html")
        if html_dir.is_dir() and ".cortical_data" in str(args.db):
            res["wiki_dashboard"] = export_static_wiki_dashboard(db, html_dir / "wiki.html")
        print(json.dumps(res, indent=2))
        return 0

    if args.cmd == "wiki-distill":
        from .wiki_static import export_static_wiki_dashboard

        db = CorticalWikiDB(args.db)
        hub = CorticalSkillHub(db, args.skills_dir)
        res = hub.distill_and_compact_knowledge(
            target_kind=args.kind,
            target_id=args.target,
            keep_tier=args.keep_tier,
            use_local_llm=not bool(args.no_llm),
        )
        html_dir = Path("html")
        if html_dir.is_dir() and ".cortical_data" in str(args.db):
            res["wiki_dashboard"] = export_static_wiki_dashboard(db, html_dir / "wiki.html")
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0

    if args.cmd == "sanitize":
        from .privacy_sanitizer import sanitize_file, sanitize_with_profile

        if getattr(args, "profile", None):
            payload = sanitize_with_profile(Path(args.file), profile_name=args.profile)
            txt = payload["sanitized_text"]
        else:
            res = sanitize_file(
                Path(args.file),
                redact=bool(args.redact),
                use_local_llm=bool(args.llm),
            )
            payload = res.to_dict(include_map=False)
            txt = res.sanitized_text
        if args.out:
            Path(args.out).write_text(txt, encoding="utf-8")
        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print(txt)
        return 0

    if args.cmd == "settings-dashboard":
        from .settings_static import export_static_settings_dashboard

        out_p = export_static_settings_dashboard(Path(args.output))
        if getattr(args, "open", False):
            import webbrowser

            webbrowser.open(out_p.resolve().as_uri())
        print(json.dumps({"output_path": str(out_p)}, indent=2))
        return 0

    if args.cmd == "token-prune":
        from .token_analytics import prune_old_token_data

        db = CorticalWikiDB(args.db)
        res = prune_old_token_data(db, retention_days=args.days, reset_all=bool(args.reset))
        print(json.dumps(res, indent=2))
        return 0

    if args.cmd == "local-loop":
        db = CorticalWikiDB(args.db)
        hub = CorticalSkillHub(db, args.skills_dir)
        model_list = [m.strip() for m in str(args.models or "").split(",") if m.strip()] or None
        attached: list[str] = []
        for item in (args.attach_files or []):
            for part in str(item).split(","):
                if part.strip():
                    attached.append(part.strip())
        res = hub.run_multi_model_local_loop(
            args.prompt,
            models=model_list,
            max_loops=int(args.loops),
            privacy_profile=args.privacy,
            attached_files=attached or None,
            force_local_only=bool(args.force_local),
            max_tokens=int(args.max_tokens),
            context_budget_chars=int(args.context_chars),
            timeout=float(args.timeout),
        )
        if args.json:
            print(json.dumps(res, indent=2, ensure_ascii=False))
        else:
            print(f"### Cortical Multi-Model Local Loop (`{res['episode_id']}`)")
            print(
                f"- **Models:** {' → '.join(res['models_used'])} · **Tokens Offloaded:** `{res.get('total_local_tokens', 0):,}` "
                f"in `{res.get('total_elapsed_sec', 0.0):.1f}s` · **Privacy:** `{res['privacy_profile']}` · **Completed Locally:** `{res['completed_locally']}`"
            )
            print(f"- **Distilled Insight (`{res['distilled_insight_id']}`):** {res['distilled_insight']}\n")
            print(res["local_answer"])
            if res["needs_remote_escalation"]:
                print("\n---\n" + res["sanitized_remote_prompt"])
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
