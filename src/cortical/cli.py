"""Cortical Unified Command Line Interface (`cortical`)."""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

from .grounding import extract_weather_intent, fetch_weather_forecast
from .hardware.profiler import HardwareProfiler
from .permissions.gate import AdaptivePermissionGate
from .server import run_live_server
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

    # 9. serve (Live HTTP + Voice + Second Brain Daemon)
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
