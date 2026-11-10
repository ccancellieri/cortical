"""Comprehensive Single-Shot Test Suite for Cortical (All 5 Wiki Pillars, MCP, Permissions, Hardware, Voice)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from cortical.cli import main as cli_main
from cortical.grounding import extract_weather_intent, fetch_weather_forecast
from cortical.hardware.profiler import HardwareProfiler
from cortical.memory import MemoryCurator, is_ephemeral_utterance, is_explicit_task_request
from cortical.permissions.gate import AdaptivePermissionGate
from cortical.server import CorticalLiveService, shape_expressive_italian_text
from cortical.skills_hub import CorticalSkillHub
from cortical.voice.engine import CorticalVoiceEngine, is_self_echo, is_stop_command, strip_wake_word
from cortical.wiki.crawler import DeterministicMerkleCrawler
from cortical.wiki.db import AccessContext, CorticalWikiDB, DepthTier
from cortical.wiki.fact_check import CitationVerifier
from cortical.wiki.mcp_server import CorticalWikiMCPServer

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "api_fixtures.json"


class TestCorticalSystem(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
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

    def test_10_self_echo_isolation_and_explicit_only_tasks(self) -> None:
        """Tests that Cortical ignores its own spoken response (anti-echo) and creates tasks ONLY when explicitly asked."""
        voice = CorticalVoiceEngine(reflex_llm_fn=lambda q: f"Risposta sintetica per {q}")

        # 1. Normal question -> System 1 (must NOT create a task automatically)
        res1 = voice.handle_utterance("Hei Cortical, analizza brevemente come funziona il meteo")
        self.assertEqual(res1.route, "system1_reflex")
        self.assertIsNone(res1.dispatched_task_goal)
        self.assertFalse(is_explicit_task_request("procedi cerca il meteo a roma per domani"))
        self.assertFalse(is_explicit_task_request("apri chrome e controlla le notizie"))
        self.assertTrue(is_explicit_task_request("crea un task per rifattorizzare il modulo wiki"))

        # 2. If microphone hears Cortical's own response right after speaking, it must be isolated & ignored
        echo_res = voice.handle_utterance(res1.spoken_response)
        self.assertEqual(echo_res.route, "ignored_echo")
        self.assertEqual(echo_res.spoken_response, "")
        self.assertTrue(is_self_echo("Risposta sintetica per analizza", res1.spoken_response, 2.0))

        # 3. Acoustic Speaker-Bleed Shield: while TTS is speaking, un-prefixed mic bleed is ignored,
        #    whereas explicit wake-word ("Ehi Cortical...") or stop-word ("Fermati") barges in cleanly.
        bleed_res = voice.handle_utterance(
            "parole distorte dall altoparlante mentre parla",
            from_mic=True,
            tts_currently_speaking=True,
        )
        self.assertEqual(bleed_res.route, "ignored_echo")

        barge_res = voice.handle_utterance(
            "Ehi Cortical, che ore sono?",
            from_mic=True,
            tts_currently_speaking=True,
        )
        self.assertEqual(barge_res.route, "system1_reflex")

    def test_11_smart_memory_curator_and_task_archival(self) -> None:
        """Tests bounded chat buffer (max 20), ephemeral filtering, LLM curation, closing questions, and compact task archival."""
        db = CorticalWikiDB(self.wiki_db_path)
        curator = MemoryCurator(
            db,
            llm_fn=lambda p: '{"save": true, "topic": "architettura", "insight": "L utente preferisce memoria isolata per task."}',
        )

        # 1. Ephemeral queries must be flagged as ephemeral and NEVER saved to durable memory_insights
        self.assertTrue(is_ephemeral_utterance("che ore sono"))
        self.assertTrue(is_ephemeral_utterance("procedi cerca il meteo a roma per domani"))
        ephem_res = curator.record_chat_turn("procedi cerca il meteo a roma per domani", "Domani a Roma 18 gradi.")
        self.assertTrue(ephem_res["is_ephemeral"])
        self.assertFalse(ephem_res["curated_saved"])
        self.assertEqual(len(curator.list_insights()), 0)

        # 2. Durable technical preferences are curated and saved intelligently
        dur_res = curator.record_chat_turn(
            "Ricorda che per questo progetto preferisco sempre isolare la memoria per ogni singolo task.",
            "Perfetto, memorizzo questa regola architetturale.",
        )
        self.assertFalse(dur_res["is_ephemeral"])
        self.assertTrue(dur_res["curated_saved"])
        self.assertEqual(len(curator.list_insights()), 1)

        # 3. Chat buffer stays bounded to MAX_CHAT_BUFFER_TURNS (20)
        for i in range(25):
            curator.record_chat_turn(f"che ore sono turno {i}", f"Sono le 10:{i:02d}")
        self.assertLessEqual(len(curator.get_recent_chat(limit=50)), 20)

        # 4. Task lifecycle: Active with isolated working notes -> Closing Questions -> Compact Archived Trace
        ctx = AccessContext()
        db.record_episode(
            ctx,
            episode_id="task-101",
            title="Task Test Isolamento",
            goal="Ottimizzare la memoria del Second Brain",
            outcome_status="active",
            learned_summary="Log dettagliato temporaneo del task...",
            skills_used=["cortical-second-brain"],
            relations=[{"relation": "modifies", "target_type": "subtree", "target_id": "/architecture.md"}],
        )
        curator.add_task_working_note("task-101", "Nota di lavoro 1: test benchmark")
        curator.add_task_working_note("task-101", "Nota di lavoro 2: verifica indice")
        self.assertEqual(len(curator.get_task_working_notes("task-101")), 2)

        preview = curator.prepare_task_closure("task-101")
        self.assertEqual(preview["working_notes_count"], 2)
        self.assertGreaterEqual(len(preview["closing_questions"]), 1)

        archived = curator.archive_task("task-101", user_closing_notes="Confermato, tieni solo traccia sintetica.")
        self.assertEqual(archived["status"], "archived")
        self.assertEqual(archived["purged_working_notes"], 2)
        self.assertEqual(len(curator.get_task_working_notes("task-101")), 0)
        self.assertTrue(archived["archived_trace"])

    def test_12_mcp_knowledge_graph_and_weather_grounding(self) -> None:
        """Tests standard MCP `wiki_get_knowledge_graph` visualizer payload and Rome weather intent extraction."""
        intent = extract_weather_intent("procedi cerca il meteo a roma per domani")
        self.assertIsNotNone(intent)
        assert intent is not None
        self.assertEqual(intent["city"], "Roma")
        self.assertEqual(intent["day_offset"], 1)
        self.assertTrue(intent["open_browser"])

        # Offline-safe weather forecast structure check (without opening browser)
        forecast = fetch_weather_forecast("Roma", day_offset=1, open_browser=False)
        self.assertEqual(forecast["city"], "Roma")
        self.assertEqual(forecast["day_label"], "domani")
        self.assertIn("Previsioni meteo per Roma", forecast["summary_it"])

        # Standard MCP `wiki_get_knowledge_graph` call via CorticalLiveService `/api/mcp`
        db = CorticalWikiDB(self.wiki_db_path)
        DeterministicMerkleCrawler(db).crawl_directory(self.sample_docs)
        svc = CorticalLiveService(self.wiki_db_path, self.perm_db_path)
        st, mcp_resp = svc.handle_api(
            "POST",
            "/api/mcp",
            {},
            {
                "jsonrpc": "2.0",
                "id": 99,
                "method": "tools/call",
                "params": {"name": "wiki_get_knowledge_graph", "arguments": {"max_nodes": 30}},
            },
        )
        self.assertEqual(st, 200)
        graph_data = json.loads(mcp_resp["result"]["content"][0]["text"])
        self.assertIn("nodes", graph_data)
        self.assertIn("edges", graph_data)
        self.assertGreaterEqual(graph_data["stats"]["node_count"], 3)
        node_kinds = {n.get("kind") for n in graph_data["nodes"]}
        self.assertIn("concept", node_kinds)
        self.assertNotIn("file", node_kinds)
        self.assertNotIn("dir", node_kinds)

    def test_13_skills_hub_3plus1_synthesis_and_task_deletion(self) -> None:
        """Tests expressive Italian TTS shaping, parallel 3+1 memory vs procedural skills, and task deletion."""
        # 1. Expressive Italian text naturalization
        shaped = shape_expressive_italian_text("Cielo poco nuvoloso (min 12°C, max 24°C, pioggia 10%) su API MCP.")
        self.assertIn("gradi", shaped)
        self.assertIn("per cento", shaped)
        self.assertNotIn("(", shaped)

        # 2. CorticalSkillHub parallel lanes: 3+1 Memory Tier Skills + Procedural Domain Skills
        db = CorticalWikiDB(self.wiki_db_path)
        DeterministicMerkleCrawler(db).crawl_directory(self.sample_docs)
        skills_dir = self.root / ".pi" / "skills"
        hub = CorticalSkillHub(db, skills_dir)

        discovered_names = {s.name for s in hub.discover_skills()}
        self.assertIn("cortical-memory-l1-light", discovered_names)
        self.assertIn("cortical-memory-l2-medium", discovered_names)
        self.assertIn("cortical-memory-l3-high", discovered_names)
        self.assertIn("cortical-multiagent-orchestrator", discovered_names)

        # Enhance a technical prompt -> selects right 3+1 tier skill + procedural skills + team roster
        enh = hub.enhance_prompt("Rifattorizza il modulo di sicurezza RBAC e verifica le citazioni nella wiki")
        self.assertEqual(enh["mode"], "enhanced")
        self.assertEqual(enh["recommended_depth"], "high")
        self.assertEqual(enh["memory_tier_skill"], "cortical-memory-l3-high")
        self.assertGreaterEqual(len(enh["team_roster"]), 2)
        self.assertIn("CORTICAL HARNESS", enh["context_injection"])

        # 3. Task 3+1 discussion synthesis + learned skill compilation + task deletion
        curator = MemoryCurator(db)
        ctx = AccessContext()
        db.record_episode(
            ctx,
            episode_id="task-skill-202",
            title="Automazione Pipeline Test RBAC",
            goal="Creare una procedura ripetibile per validare i permessi relazionali RBAC",
            outcome_status="active",
            learned_summary="Pipeline RBAC verificata con 3 step deterministici.",
            skills_used=["cortical-multiagent-orchestrator"],
            relations=[{"relation": "modifies", "target_type": "subtree", "target_id": "/security/rbac.md"}],
        )
        curator.add_task_working_note("task-skill-202", "Step 1: lettura schema acl_permissions")
        curator.add_task_working_note("task-skill-202", "Step 2: esecuzione query parametrizzata con ruolo reader")
        curator.add_task_working_note("task-skill-202", "Step 3: verifica blocco path non autorizzati")

        synth = hub.synthesize_task_discussion_3plus1(
            "task-skill-202",
            user_closing_notes="Ottimo pattern riutilizzabile: crea una skill per validare RBAC in futuro.",
        )
        self.assertEqual(synth["status"], "synthesized")
        self.assertTrue(synth["l1_light"])
        self.assertTrue(synth["l2_medium"])
        self.assertTrue(synth["l3_high"])
        self.assertTrue(synth["l4_max_raw"])

        compiled = hub.evaluate_and_compile_skill(
            "task-skill-202",
            user_closing_notes="Crea una skill riutilizzabile per validare RBAC.",
        )
        self.assertTrue(compiled["created"])
        self.assertTrue(Path(compiled["skill_path"]).exists())

        # 4. Task deletion endpoint removes task and working notes completely
        svc = CorticalLiveService(self.wiki_db_path, self.perm_db_path, repo_root=self.root)
        st_del, del_res = svc.handle_api("POST", "/api/tasks/delete", {}, {"episode_id": "task-skill-202"})
        self.assertEqual(st_del, 200)
        self.assertEqual(del_res["status"], "deleted")
        self.assertEqual(del_res["deleted_episode"], 1)

    def test_14_scoped_context_attachments_and_concept_config_delete(self) -> None:
        """Tests accented character TTS unescaping, ChatGPT-style context attachments, concept config and deletion."""
        # 1. Accented characters and escaped unicode sanitization (prevents 'barra inversa 00...')
        raw_escaped = "Oggi a Roma la citt\\u00e0 ha una temperatura di 20\\u00b0C e l'attivit\\u00e0 \\u00e8 terminata."
        clean_speech = shape_expressive_italian_text(raw_escaped)
        self.assertIn("città", clean_speech)
        self.assertIn("attività", clean_speech)
        self.assertIn("è", clean_speech)
        self.assertIn("gradi", clean_speech)
        self.assertNotIn("\\u00", clean_speech)
        self.assertNotIn("barra", clean_speech)

        # 2. Scoped Context Attachments
        db = CorticalWikiDB(self.wiki_db_path)
        ctx = AccessContext()
        test_file = self.root / "sample_attachment.py"
        test_file.write_text("def calculate_metrics():\n    return {'cyclomatic': 4, 'loc': 18}\n", encoding="utf-8")

        att_res = db.attach_context_item(
            ctx,
            scope_id="chat",
            item_type="file",
            item_ref=str(test_file),
            depth_tier="medium",
        )
        self.assertTrue(att_res["attachment_id"])
        self.assertEqual(att_res["item_type"], "file")
        self.assertIn("/attached/chat/sample_attachment.py", att_res["wiki_paths"])

        # Context items appear in list
        active_atts = db.list_context_attachments(ctx, scope_id="chat")
        self.assertEqual(len(active_atts), 1)
        self.assertEqual(active_atts[0]["attachment_id"], att_res["attachment_id"])

        # Detach removes the item and transient wiki node
        det_res = db.detach_context_item(ctx, att_res["attachment_id"])
        self.assertTrue(det_res["detached"])
        self.assertEqual(len(db.list_context_attachments(ctx, scope_id="chat")), 0)

        # 3. Concept Configuration and Core Protection
        # Update orchestrator loops
        cfg_res = db.update_concept_config(
            ctx,
            "concept:orchestratore-multi-agente",
            {"max_agent_loops": 14, "implementer_model": "qwen2.5:3b"},
        )
        self.assertEqual(cfg_res["config"]["max_agent_loops"], 14)
        self.assertEqual(cfg_res["config"]["implementer_model"], "qwen2.5:3b")

        # Deleting a framework core concept is strictly blocked
        with self.assertRaises(PermissionError):
            db.delete_concept_node(ctx, "concept:orchestratore-multi-agente")

        # User-developed concept deletion succeeds
        db.upsert_merkle_node(
            ctx,
            path="/attached/user/custom_module.py",
            parent_path="/",
            node_type="file",
            content_hash="h1",
            subtree_hash="s1",
            summary_light="Light summary of custom module",
            summary_medium="Medium summary of custom module",
            summary_high="High summary",
            raw_content="# Custom Module\n**Algoritmo Predittivo**\nCodice personalizzato...",
        )
        graph = db.get_knowledge_graph(ctx)
        user_cids = [n["id"] for n in graph["nodes"] if not n.get("is_framework_core")]
        self.assertTrue(any("algoritmo-predittivo" in cid for cid in user_cids))

        target_cid = next(cid for cid in user_cids if "algoritmo-predittivo" in cid)
        del_user = db.delete_concept_node(ctx, target_cid)
        self.assertTrue(del_user["deleted"])

        # 4. Verify 3 new Reviewer, PR Contract, and Agent Alignment skills are present
        skills_dir = self.root / ".pi" / "skills"
        hub = CorticalSkillHub(db, skills_dir)
        skill_ids = {s.skill_id for s in hub.list_skills()}
        self.assertIn("ai-reviewer-mandate-and-complexity", skill_ids)
        self.assertIn("pr-contract-and-diff-constrainer", skill_ids)
        self.assertIn("agent-instructions-alignment", skill_ids)


if __name__ == "__main__":
    unittest.main()



