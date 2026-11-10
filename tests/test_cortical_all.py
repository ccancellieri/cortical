"""Comprehensive Single-Shot Test Suite for Cortical (All 5 Wiki Pillars, MCP, Permissions, Hardware, Voice)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from cortical.cli import main as cli_main
from cortical.hardware.profiler import HardwareProfiler
from cortical.permissions.gate import AdaptivePermissionGate
from cortical.server import CorticalLiveService
from cortical.voice.engine import CorticalVoiceEngine, is_stop_command, strip_wake_word
from cortical.wiki.crawler import DeterministicMerkleCrawler
from cortical.wiki.db import AccessContext, CorticalWikiDB, DepthTier
from cortical.wiki.fact_check import CitationVerifier
from cortical.wiki.mcp_server import CorticalWikiMCPServer

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "api_fixtures.json"


class TestCorticalSystem(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.wiki_db_path = self.root / "wiki.db"
        self.perm_db_path = self.root / "perm.db"
        self.sample_docs = self.root / "docs"
        self.sample_docs.mkdir(parents=True, exist_ok=True)

        (self.sample_docs / "architecture.md").write_text(
            "# Cortical Architecture\n"
            "Cortical uses a 4-tier deterministic Merkle tree with light, medium, high, and max levels.\n"
            "It pairs hierarchical summaries with a high-level episode macro-graph.\n",
            encoding="utf-8",
        )
        sub_dir = self.sample_docs / "security"
        sub_dir.mkdir()
        (sub_dir / "rbac.md").write_text(
            "# Relational Permissions\n"
            "Access control is enforced in SQLite and PostgreSQL via acl_permissions.\n",
            encoding="utf-8",
        )

        self.fixtures = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_1_merkle_crawler_4_tiers_and_delta_skip(self) -> None:
        """Tests Pillar 1 & 4: Parallel Merkle indexing, 4 depth tiers, and O(1) unchanged delta skip."""
        db = CorticalWikiDB(self.wiki_db_path)
        crawler = DeterministicMerkleCrawler(db, max_workers=2)

        stats1 = crawler.crawl_directory(self.sample_docs)
        self.assertEqual(stats1.files_scanned, 2)
        self.assertEqual(stats1.files_updated, 2)
        self.assertEqual(stats1.files_skipped_unchanged, 0)
        self.assertTrue(stats1.root_subtree_hash)

        # Second crawl without changes must skip 100% of files and directories
        stats2 = crawler.crawl_directory(self.sample_docs)
        self.assertEqual(stats2.files_updated, 0)
        self.assertEqual(stats2.files_skipped_unchanged, 2)
        self.assertEqual(stats2.dirs_updated, 0)
        self.assertEqual(stats2.root_subtree_hash, stats1.root_subtree_hash)

        # Verify 4 depth tiers (light < medium <= high <= max)
        ctx = AccessContext()
        nav_light = db.navigate(ctx, "/architecture.md", depth=DepthTier.LIGHT)
        nav_med = db.navigate(ctx, "/architecture.md", depth=DepthTier.MEDIUM)
        nav_high = db.navigate(ctx, "/architecture.md", depth=DepthTier.HIGH)
        nav_max = db.navigate(ctx, "/architecture.md", depth=DepthTier.MAX)

        self.assertEqual(nav_light["depth_tier"], "light")
        self.assertIn("Cortical Architecture", nav_light["content"])
        self.assertIn("Structure:", nav_med["content"])
        self.assertIn("HIGH-DEPTH SYNTHESIS", nav_high["content"])
        self.assertIn("high-level episode macro-graph", nav_max["content"])

    def test_2_multi_tenancy_and_relational_rbac(self) -> None:
        """Tests Pillar 3 & 5: Multi-tenant isolation and relational path-prefix ACLs."""
        db = CorticalWikiDB(self.wiki_db_path)
        crawler = DeterministicMerkleCrawler(db)
        owner_ctx = AccessContext(tenant_id="org_a", workspace_id="ws1", principal_id="admin")
        crawler.crawl_directory(self.sample_docs, ctx=owner_ctx)

        # Grant guest read access ONLY to /architecture.md, denying /security
        db.grant_permission("org_a", "ws1", "guest_user", "/", can_read=True, can_write=False)
        db.grant_permission("org_a", "ws1", "guest_user", "/security", can_read=False, can_write=False)

        guest_ctx = AccessContext(tenant_id="org_a", workspace_id="ws1", principal_id="guest_user")
        allowed_doc = db.navigate(guest_ctx, "/architecture.md", depth="light")
        self.assertEqual(allowed_doc["path"], "/architecture.md")

        with self.assertRaises(PermissionError):
            db.navigate(guest_ctx, "/security/rbac.md", depth="light")

        # Search results for guest must also filter out /security/rbac.md
        hits = db.search(guest_ctx, "Permissions SQLite Cortical", depth="light")
        hit_paths = [h["path"] for h in hits]
        self.assertNotIn("/security/rbac.md", hit_paths)

    def test_3_fact_checking_with_json_fixtures(self) -> None:
        """Tests Pillar 2: 2-Stage Citation Verifier (verbatim span + fixture NLI decision model)."""
        db = CorticalWikiDB(self.wiki_db_path)
        DeterministicMerkleCrawler(db).crawl_directory(self.sample_docs)
        verifier = CitationVerifier(db, fixture_path=FIXTURE_PATH)
        ctx = AccessContext()

        # 1. Verified claim (exact span + NLI entailment from JSON fixture)
        res_ok = verifier.verify_and_record(
            ctx,
            claim_text="Cortical uses a 4-tier deterministic Merkle tree with light, medium, high, and max levels.",
            source_path="/architecture.md",
            quoted_span="Cortical uses a 4-tier deterministic Merkle tree with light, medium, high, and max levels.",
        )
        self.assertEqual(res_ok.verdict, "verified")
        self.assertTrue(res_ok.span_verified)

        # 2. Refuted claim (span exists, but NLI detects contradiction)
        res_refuted = verifier.verify_and_record(
            ctx,
            claim_text="Cortical requires a 100GB cloud GPU cluster to index markdown files.",
            source_path="/architecture.md",
            quoted_span="Cortical uses a 4-tier deterministic Merkle tree with light, medium, high, and max levels.",
        )
        self.assertEqual(res_refuted.verdict, "refuted")

        # 3. Fabricated quote (span does not exist in document)
        res_missing = verifier.verify_and_record(
            ctx,
            claim_text="Cortical uses quantum entanglement.",
            source_path="/architecture.md",
            quoted_span="This sentence does not exist in the file.",
        )
        self.assertEqual(res_missing.verdict, "unverified")
        self.assertFalse(res_missing.span_verified)

    def test_4_macro_graph_and_mcp_server(self) -> None:
        """Tests High-Level Episode Macro-Graph and standard JSON-RPC 2.0 MCP Server."""
        mcp = CorticalWikiMCPServer(db_path=self.wiki_db_path)

        init_resp = mcp.handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        self.assertEqual(init_resp["result"]["serverInfo"]["name"], "cortical-wiki-mcp")

        crawl_resp = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "wiki_crawl_delta",
                    "arguments": {"root_dir": str(self.sample_docs)},
                },
            }
        )
        self.assertFalse(crawl_resp["result"]["isError"])

        ep_resp = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "wiki_record_episode",
                    "arguments": {
                        "episode_id": "ep-001",
                        "title": "Initial Architecture Indexing",
                        "goal": "Index architecture docs and verify Merkle hashes",
                        "outcome_status": "completed",
                        "learned_summary": "4-tier Merkle tree skips unchanged subtrees in O(1).",
                        "skills_used": ["cortical-second-brain"],
                        "relations": [
                            {
                                "relation": "modifies",
                                "target_type": "subtree",
                                "target_id": "/architecture.md",
                            }
                        ],
                    },
                },
            }
        )
        self.assertFalse(ep_resp["result"]["isError"])

        nav_resp = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "wiki_navigate",
                    "arguments": {"path": "/architecture.md", "depth": "light"},
                },
            }
        )
        nav_data = json.loads(nav_resp["result"]["content"][0]["text"])
        self.assertEqual(len(nav_data["macro_relations"]), 1)
        self.assertEqual(nav_data["macro_relations"][0]["source_id"], "ep-001")

    def test_5_adaptive_permission_gate(self) -> None:
        """Tests Hard Guardrails, Zero Focus Stealing block, and Progressive Approval Learning."""
        gate = AdaptivePermissionGate(self.perm_db_path, auto_approve_threshold=2)

        # 1. Hard blocks (rm -rf /, pass.txt leak, focus stealing AXRaise)
        self.assertEqual(gate.evaluate("bash", {"command": "rm -rf /"}).verdict, "deny")
        self.assertEqual(gate.evaluate("bash", {"command": "cat /tmp/pass.txt"}).verdict, "deny")
        self.assertEqual(
            gate.evaluate("bash", {"command": "osascript -e 'set frontmost to true'"}).verdict,
            "deny",
        )

        # 2. Safe read-only commands allowed immediately
        self.assertEqual(gate.evaluate("bash", {"command": "git status"}).verdict, "allow")

        # 3. Medium-risk dev command starts as 'ask', then auto-approves after 2 approvals
        cmd_args = {"command": "pytest tests/"}
        d1 = gate.evaluate("bash", cmd_args)
        self.assertEqual(d1.verdict, "ask")

        gate.record_user_feedback("bash", cmd_args, approved=True)
        d2 = gate.record_user_feedback("bash", cmd_args, approved=True)
        self.assertEqual(d2.verdict, "allow")
        self.assertLess(d2.risk_score, d1.risk_score)

    def test_6_hardware_profiler_and_existing_endpoint_reuse(self) -> None:
        """Tests Hardware Auto-Profiler across Linux 4GB MX250 laptop (reusing :8080) and Mac M2 Pro."""
        profiler = HardwareProfiler()

        linux_specs = self.fixtures["hardware_profiles"]["linux_laptop_mx250"]
        linux_prof = profiler.detect(override_specs=linux_specs)
        linux_rec = profiler.recommend_models(linux_prof)

        self.assertEqual(linux_prof.tier, "tier1_constrained")
        self.assertTrue(linux_rec.reuse_existing_endpoint)
        self.assertEqual(linux_rec.active_base_url, "http://127.0.0.1:8080/v1")
        self.assertIn("LFM2.5-1.2B", linux_rec.fast_reflex_model)

        mac_specs = self.fixtures["hardware_profiles"]["mac_m2_pro_16gb"]
        mac_prof = profiler.detect(override_specs=mac_specs)
        mac_rec = profiler.recommend_models(mac_prof)
        self.assertEqual(mac_prof.tier, "tier2_pro_16gb")
        self.assertIn("Qwen3-8B", mac_rec.orchestrator_model)

        out_cfg = profiler.generate_pi_configs(self.root / ".pi_test", self.root, profile=mac_prof)
        self.assertTrue(Path(out_cfg["mcp_config_path"]).exists())

    def test_7_dual_path_voice_engine(self) -> None:
        """Tests resilient barge-in stop words, 'hei cortical' wake word, voice permission approval, and System 1 vs System 2 routing."""
        self.assertTrue(is_stop_command("Ehi Cortical basta"))
        self.assertTrue(is_stop_command("Hei Cortical basta"))
        self.assertTrue(is_stop_command("hey peppe ba sta per favore"))
        self.assertTrue(is_stop_command("fer ma ti subito"))
        self.assertFalse(is_stop_command("Ehi Cortical, raccontami una storia abbastanza lunga"))

        had_wake, rem = strip_wake_word("Hei Cortical, che ore sono?")
        self.assertTrue(had_wake)
        self.assertEqual(rem, "che ore sono")

        # Built-in clock reflex without external LLM
        voice_builtin = CorticalVoiceEngine()
        clock_res = voice_builtin.handle_utterance("hei cortical che ore sono")
        self.assertEqual(clock_res.route, "system1_reflex")
        self.assertIn("Sono le", clock_res.spoken_response)

        db = CorticalWikiDB(self.wiki_db_path)
        gate = AdaptivePermissionGate(self.perm_db_path)
        reflex_map = self.fixtures["reflex_responses"]
        voice = CorticalVoiceEngine(
            wiki_db=db,
            permission_gate=gate,
            reflex_llm_fn=lambda q: reflex_map.get(q, f"OK:{q}"),
        )

        # System 1 Fast Reflex
        r1 = voice.handle_utterance("Ehi Cortical, che ore sono?")
        self.assertEqual(r1.route, "system1_reflex")
        self.assertIn("18:10", r1.spoken_response)

        # System 2 Async Agentic Delegation
        r2 = voice.handle_utterance("Ehi Cortical, orchestra un sottoagente e analizza il progetto")
        self.assertEqual(r2.route, "system2_agentic")
        self.assertTrue(r2.dispatched_task_goal)

        # Status check on active background subagent
        r_status = voice.handle_utterance("Cortical, a che punto sono gli agenti?")
        self.assertEqual(r_status.route, "status_report")
        self.assertIn("1 task attivi", r_status.spoken_response)

        # Voice approval for pending Adaptive Permission Gate
        voice.register_pending_permission("bash", {"command": "npm test"})
        r_perm = voice.handle_utterance("Ehi Cortical, approva e ricorda sempre")
        self.assertEqual(r_perm.route, "permission_feedback")
        self.assertEqual(r_perm.permission_updated, "allow")

    def test_8_cli_entrypoints(self) -> None:
        """Tests CLI subcommands end-to-end."""
        rc = cli_main(
            [
                "--db",
                str(self.wiki_db_path),
                "crawl",
                str(self.sample_docs),
            ]
        )
        self.assertEqual(rc, 0)

    def test_9_live_service_endpoints(self) -> None:
        """Tests the live HTTP & Voice service handler (`CorticalLiveService`)."""
        db = CorticalWikiDB(self.wiki_db_path)
        DeterministicMerkleCrawler(db).crawl_directory(self.sample_docs)

        svc = CorticalLiveService(self.wiki_db_path, self.perm_db_path)
        st, health = svc.handle_api("GET", "/health", {}, {})
        self.assertEqual(st, 200)
        self.assertEqual(health["status"], "ok")

        st_nav, nav = svc.handle_api(
            "GET",
            "/api/wiki/navigate",
            {"path": ["/architecture.md"], "depth": ["light"]},
            {},
        )
        self.assertEqual(st_nav, 200)
        self.assertEqual(nav["depth_tier"], "light")

        st_voice, v_res = svc.handle_api(
            "POST",
            "/api/voice",
            {},
            {"utterance": "Ehi Cortical, orchestra un sottoagente per i test", "speak": False},
        )
        self.assertEqual(st_voice, 200)
        self.assertEqual(v_res["route"], "system2_agentic")

