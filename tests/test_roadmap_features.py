"""Tests for #40 Cryptographic Audit Ledger, #41 Native Hooks, #42/#25 Profile Bundles, and #43 Metal/Telemetry."""

from __future__ import annotations

import copy
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from cortical.analytics.roi import collect_multi_harness_local_runs  # noqa: E402
from cortical.analytics.snapshot import build_dashboard_snapshot  # noqa: E402
from cortical.cli import main as cli_main  # noqa: E402
from cortical.config import DEFAULT_CONFIG  # noqa: E402
from cortical.hardware.context_window import compute_hardware_context_profile  # noqa: E402
from cortical.harnesses.hooks import HOOK_TARGETS, inspect_harness_hooks, install_harness_hooks  # noqa: E402
from cortical.privacy.vault import FailClosedError, PrivacyVault  # noqa: E402
from cortical.profile import PROFILE_SCHEMA, diff_profile_bundles, export_profile_bundle, import_profile_bundle  # noqa: E402


class TestCryptographicAuditLedger(unittest.TestCase):
    def test_hash_chain_records_blocked_egress_never_stores_pii_and_detects_tamper(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db_p = Path(td) / "vault.db"
            vault = PrivacyVault(db_p)
            vault.ingest("Secret contract for alice@acme.example IT60X0542811101000000123456", alias="contract_a", policy="fail_closed", profile="medium")
            vault.ingest("Top secret salary SSN 123-45-6789 alice@acme.example", alias="tax_max", policy="fail_closed", profile="max_security")

            with self.assertRaises(FailClosedError):
                vault.read_resource("tax_max", allow_local_only=False)
            safe = vault.read_resource("contract_a", allow_local_only=False)
            self.assertIn("[EMAIL_1]", safe["text"])

            ver = vault.verify_audit_ledger()
            self.assertTrue(ver["ok"])
            self.assertEqual(ver["total_entries"], 4)
            self.assertEqual(ver["blocked_egress_count"], 2)  # ingest max_security + blocked read
            self.assertIsNone(ver["broken_at_seq"])

            rows = vault.get_audit_ledger(limit=10)
            serialized = json.dumps(rows)
            self.assertNotIn("alice@acme.example", serialized)
            self.assertNotIn("123-45-6789", serialized)

            # CLI smoke check on `vault audit --verify --json`
            with mock.patch("builtins.print") as mp:
                rc = cli_main(["vault", "audit", "--verify", "--db", str(db_p), "--json"])
            self.assertEqual(rc, 0)
            cli_out = json.loads(mp.call_args[0][0])
            self.assertTrue(cli_out["verify"]["ok"])

            # Mutating one row invalidates hash chain cleanly
            with sqlite3.connect(str(db_p)) as conn:
                conn.execute("UPDATE privacy_audit_ledger SET blocked_egress = 0 WHERE seq = 3")
            tampered = vault.verify_audit_ledger()
            self.assertFalse(tampered["ok"])
            self.assertEqual(tampered["broken_at_seq"], 3)


class TestNativeHarnessHooks(unittest.TestCase):
    def test_install_inspect_and_idempotency_across_all_hook_targets(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            pre = inspect_harness_hooks(home=home, os_name="macos")
            self.assertTrue(all(not pre[t]["installed"] for t in HOOK_TARGETS))

            dry = install_harness_hooks(home=home, os_name="macos", dry_run=True)
            self.assertEqual(dry["changed_count"], 8)
            self.assertTrue(all(not inspect_harness_hooks(home=home, os_name="macos")[t]["installed"] for t in HOOK_TARGETS))

            res = install_harness_hooks(home=home, os_name="macos", dry_run=False)
            self.assertEqual(res["changed_count"], 8)
            post = inspect_harness_hooks(home=home, os_name="macos")
            self.assertTrue(all(post[t]["installed"] and post[t]["in_sync"] for t in HOOK_TARGETS))

            # Second install is idempotent (0 changes)
            again = install_harness_hooks(home=home, os_name="macos", dry_run=False)
            self.assertEqual(again["changed_count"], 0)
            self.assertTrue((home / ".claude" / "hooks" / "cortical_pretool.py").is_file())
            self.assertTrue((home / ".dsh" / "plugins" / "cortical-cordis-hook.mjs").is_file())
            self.assertTrue((home / ".cortical" / "hooks" / "litellm_cortical_guard.py").is_file())


class TestPortableZeroSecretProfiles(unittest.TestCase):
    def test_export_scrubs_secrets_and_home_diff_and_import_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            fake_home = Path(td) / "home"
            fake_home.mkdir()
            cfg = copy.deepcopy(DEFAULT_CONFIG)
            cfg["orchestrator"]["mode"] = "remote"
            cfg["orchestrator"]["provider"] = "gemini"
            cfg["orchestrator"]["api_key_env"] = "sk-live-SHOULD-NEVER-EXPORT-123456"
            cfg["privacy"]["crawl_folder"] = str(fake_home / "Dropbox" / "work")

            hw = {"total_ram_gb": 16.0, "vram_gb": 11.2, "unified_memory": True, "classification": {"tier": "tier_1b_unified_16_24", "label": "Tier 1B Unified"}}
            bundle = export_profile_bundle(cfg, hw, home=fake_home)
            self.assertEqual(bundle["schema"], PROFILE_SCHEMA)
            self.assertEqual(bundle["config_patch"]["orchestrator"]["api_key_env"], "")
            self.assertEqual(bundle["config_patch"]["privacy"]["crawl_folder"], "~/Dropbox/work")
            self.assertNotIn("sk-live", json.dumps(bundle))

            # Diff & import roundtrip
            bundle["config_patch"]["orchestrator"]["api_key_env"] = "GEMINI_API_KEY"
            peer = copy.deepcopy(bundle)
            peer["hardware_tier"] = "tier_2_desktop"
            peer["config_patch"]["harnesses"]["dsh"] = False
            delta = diff_profile_bundles(bundle, peer)
            self.assertFalse(delta["tier_comparison"]["same_tier"])
            self.assertIn("dsh", delta["harness_deltas"])

            cfg_out = Path(td) / "cortical.config.json"
            imp = import_profile_bundle(peer, dry_run=False, config_path=cfg_out)
            self.assertEqual(imp["imported_profile_schema"], PROFILE_SCHEMA)
            loaded = json.loads(cfg_out.read_text(encoding="utf-8"))
            self.assertEqual(loaded["orchestrator"]["api_key_env"], "GEMINI_API_KEY")
            self.assertFalse(loaded["harnesses"]["dsh"])


class TestDualMetalAndMultiHarnessTelemetry(unittest.TestCase):
    def test_metal_profile_arena_fields_and_multi_harness_local_logs(self) -> None:
        prof = compute_hardware_context_profile(
            "qwen3.8:27b-iq2_xxs",
            {"total_ram_gb": 16.0, "free_ram_gb": 4.0, "unified_memory": True, "vram_gb": 10.67, "memory_pressure_level": 1},
        )
        self.assertEqual(prof["gguf_arena_overhead_gb"], 0.65)
        self.assertTrue(prof["zero_copy_safe"])

        with tempfile.TemporaryDirectory() as td:
            h = Path(td)
            # Claude Code local log
            c_log = h / ".claude" / "projects" / "proj1" / "sess.jsonl"
            c_log.parent.mkdir(parents=True)
            c_log.write_text(json.dumps({"message": {"provider": "router", "model": "qwen3.5:9b-q3_k_xl", "usage": {"input_tokens": 1200, "output_tokens": 300}}}) + "\n", encoding="utf-8")
            # Codex local log (plus one remote gpt-5 entry that must be ignored)
            x_log = h / ".codex" / "sessions" / "s1.jsonl"
            x_log.parent.mkdir(parents=True)
            x_log.write_text(
                json.dumps({"provider": "ollama", "model": "cortical-deep", "usage": {"prompt_tokens": 2000, "completion_tokens": 400}}) + "\n"
                + json.dumps({"provider": "openai", "model": "gpt-5", "usage": {"input_tokens": 9999, "output_tokens": 999}}) + "\n",
                encoding="utf-8",
            )
            # OpenCode & dsh logs
            o_log = h / ".local" / "share" / "opencode" / "s.jsonl"
            o_log.parent.mkdir(parents=True)
            o_log.write_text(json.dumps({"providerID": "local", "modelID": "qwen2.5:1.5b", "tokens": {"input": 500, "output": 100}}) + "\n", encoding="utf-8")
            d_log = h / ".dsh" / "logs" / "run.jsonl"
            d_log.parent.mkdir(parents=True)
            d_log.write_text(json.dumps({"provider": "router", "model": "cortical-fast", "usage": {"input_tokens": 800, "output_tokens": 200}}) + "\n", encoding="utf-8")

            runs = collect_multi_harness_local_runs(home=h)
            self.assertEqual(len(runs), 4)
            provs = {r["provider"].split(":")[0] for r in runs}
            self.assertEqual(provs, {"claude-code", "codex", "opencode", "dsh"})
            self.assertEqual(sum(r["total_tokens"] for r in runs), 5500)

        snap = build_dashboard_snapshot(public_docs=True)
        self.assertTrue(snap["vault"]["audit_ledger"]["ok"])
        self.assertIn("roles", snap["models"])
        self.assertGreaterEqual(len(snap["models"]["roles"]), 10)


class TestModelRoleAbstractionAndWatchFix(unittest.TestCase):
    def test_role_registry_aliases_fallbacks_and_shared_rules(self) -> None:
        from cortical.harnesses.adapters import _build_shared_rules_md
        from cortical.roles import MODEL_ROLES, normalize_role_or_model, resolve_all_roles, resolve_role_model

        self.assertEqual(len(MODEL_ROLES), 10)
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["models_by_role"]["reviewer"] = "custom-reviewer:14b"
        cfg["models_by_role"]["summarizer"] = ""
        cfg["models_by_role"]["fast_coder"] = "custom-fast:4b"
        cfg["privacy"]["vision_model"] = "custom-ocr:latest"

        self.assertEqual(resolve_role_model("reviewer", cfg), "custom-reviewer:14b")
        self.assertEqual(resolve_role_model("cortical-reviewer", cfg), "custom-reviewer:14b")
        self.assertEqual(resolve_role_model("@role:summarizer", cfg), "custom-fast:4b")  # fallback chain
        self.assertEqual(resolve_role_model("vision", cfg), "custom-ocr:latest")
        self.assertEqual(normalize_role_or_model("explicit-model:7b", cfg), "explicit-model:7b")
        self.assertEqual(len(resolve_all_roles(cfg)), 10)

        rules = _build_shared_rules_md("", "custom-fast:4b", "http://127.0.0.1:4000/v1", {"serena": True})
        self.assertIn("@role:orchestrator", rules)
        self.assertIn("cortical_local_offload(role=", rules)
        self.assertNotIn("qwen3.5:9b-q3_k_xl", rules)

    def test_watch_sync_from_disk_uses_config_vision_model_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db_p = root / "vault.db"
            cfg_p = root / "cortical.config.json"
            cfg = copy.deepcopy(DEFAULT_CONFIG)
            cfg["privacy"]["vision_model"] = "minicpm-ocr:latest"
            cfg_p.write_text(json.dumps(cfg), encoding="utf-8")

            v = PrivacyVault(db_p)
            v.inbox_dir.mkdir(parents=True, exist_ok=True)
            img = v.inbox_dir / "receipt.png"
            img.write_bytes(b"\x89PNG\r\n\x1a\nfake")
            (v.inbox_dir / "receipt.png.meta.json").write_text(json.dumps({"alias": "ocr_receipt", "policy": "fail_closed", "profile": "medium"}), encoding="utf-8")

            with mock.patch.dict(os.environ, {"CORTICAL_CONFIG_PATH": str(cfg_p)}), \
                 mock.patch("cortical.privacy.sanitizer.ocr_image_local", return_value="Invoice for alice@acme.example EUR 100") as mocked_ocr:
                res = v.sync_from_disk(process_inbox=True)
            self.assertEqual(res["inbox_processed"], 1)
            self.assertEqual(mocked_ocr.call_args.kwargs.get("model"), "minicpm-ocr:latest")
            item = v.read_resource("ocr_receipt", allow_local_only=False)
            self.assertIn("[EMAIL_1]", item["text"])

    def test_self_curation_and_bidirectional_memory_sync(self) -> None:
        from cortical.privacy.curation import curate_skills_from_memory, sync_memory_markdown

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db_p = root / "vault.db"
            v = PrivacyVault(db_p)
            v.ingest("# Architecture\n1. Run doctor\n2. Sync harnesses\nContact alice@acme.example", alias="ops_guide", policy="auto", profile="medium")
            v.ingest("Top secret salary ledger IT60X0542811101000000123456", alias="secret_ledger", policy="fail_closed", profile="max_security")

            skills_dir = root / "skills"
            cur = curate_skills_from_memory(vault_db=db_p, skills_dir=skills_dir, handoff_path=root / "none.json")
            self.assertEqual(cur["action"], "create")
            skill_txt = Path(cur["path"]).read_text(encoding="utf-8")
            self.assertIn("name: cortical-self-curated", skill_txt)
            self.assertIn("@role:summarizer", skill_txt)
            self.assertNotIn("alice@acme.example", skill_txt)
            self.assertNotIn("IT60X0542811101000000123456", skill_txt)

            mem_p = root / "MEMORY.md"
            mem_p.write_text("# My Notes\nPrefer stdlib-only solutions.\n", encoding="utf-8")
            exp = sync_memory_markdown(vault_db=db_p, memory_path=mem_p, direction="both")
            self.assertEqual(exp["action"], "update")
            self.assertTrue(exp["imported_notes"])
            self.assertGreaterEqual(exp["exported_concepts"], 1)
            mem_txt = mem_p.read_text(encoding="utf-8")
            self.assertIn("Prefer stdlib-only solutions.", mem_txt)
            self.assertIn("CORTICAL-MEMORY:START", mem_txt)
            self.assertNotIn("IT60X0542811101000000123456", mem_txt)

    def test_mcp_local_offload_reads_file_paths_locally_and_blocks_vault_dirs(self) -> None:
        from cortical.mcp_server import CorticalMCPServer

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src_f = root / "sample.py"
            src_f.write_text("def hello():\n    return 'world'\n" * 40, encoding="utf-8")
            vault_f = root / ".cortical_data" / "secret.txt"
            vault_f.parent.mkdir(parents=True)
            vault_f.write_text("TOP SECRET NEVER READ", encoding="utf-8")

            mcp = CorticalMCPServer(vault_db=root / "vault.db")
            captured: dict[str, str] = {}

            def _fake_runner(prompt: str, **kw: object) -> str:
                captured["prompt"] = prompt
                captured["model"] = str(kw.get("model_override") or "")
                return "Concise summary: hello() returns world."

            with mock.patch("cortical.mcp_server.invoke_configured_runner", side_effect=_fake_runner):
                out = mcp._dispatch_tool(
                    "cortical_local_offload",
                    {"role": "summarizer", "file_paths": [str(src_f), str(vault_f)], "prompt": "Summarize"},
                )
            self.assertTrue(out["completed_locally"])
            self.assertEqual(out["files_read_locally"], [str(src_f)])
            self.assertGreater(out["raw_file_tokens_saved_est"], 100)
            self.assertNotIn("TOP SECRET NEVER READ", captured["prompt"])

    def test_zero_runner_privacy_vault_and_toon_operate_100pct_offline(self) -> None:
        import zipfile
        from cortical.compression.engine import compress_structured
        from cortical.config import DEFAULT_CONFIG
        from cortical.privacy.sanitizer import FailClosedError
        from cortical.privacy.vault import PrivacyVault

        offline_cfg = copy.deepcopy(DEFAULT_CONFIG)
        offline_cfg["active_runner"] = "lm_studio"
        offline_cfg["runners"]["lm_studio"]["base_url"] = "http://127.0.0.1:9/v1"
        offline_cfg["privacy"]["use_local_ner"] = False

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            md_f = root / "spec.md"
            md_f.write_text(
                "Architecture uses PostgreSQL and FastAPI. Contact: alice@acme.example, IBAN IT60X0542811101000000123456.",
                encoding="utf-8",
            )
            docx_f = root / "contract.docx"
            with zipfile.ZipFile(docx_f, "w") as zf:
                zf.writestr("docProps/core.xml", "<cp:coreProperties><dc:creator>Hidden Author</dc:creator></cp:coreProperties>")
                zf.writestr(
                    "word/document.xml",
                    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                    "<w:body><w:p><w:t>Secret client bob@acme.example on Kubernetes cluster</w:t></w:p></w:body></w:document>",
                )
            pdf_f = root / "invoice.pdf"
            pdf_f.write_bytes(
                b"%PDF-1.4\n1 0 obj << /Author (Secret Corp) >> endobj\n"
                b"stream\nBT (Billing carol@acme.example PostgreSQL node) Tj ET\nendstream\n%%EOF"
            )

            vault = PrivacyVault(root / "vault.db")
            r_md = vault.ingest(str(md_f), alias="spec_doc", policy="auto", profile="medium", config=offline_cfg)
            r_docx = vault.ingest(str(docx_f), alias="secret_docx", policy="fail_closed", profile="max_security", config=offline_cfg)
            r_pdf = vault.ingest(str(pdf_f), alias="inv_pdf", policy="auto", profile="medium", config=offline_cfg)

            self.assertGreaterEqual(r_md["entity_count"], 2)
            self.assertTrue(r_docx["local_only"])
            self.assertGreaterEqual(r_pdf["entity_count"], 1)

            safe_md = vault.read_resource("spec_doc", allow_local_only=False)
            self.assertIn("PostgreSQL", safe_md["text"])
            self.assertNotIn("alice@acme.example", safe_md["text"])

            with self.assertRaises(FailClosedError):
                vault.read_resource("secret_docx", allow_local_only=False, remote_egress=True)

            audit = vault.verify_audit_ledger()
            self.assertTrue(audit["ok"])
            self.assertGreaterEqual(audit["blocked_egress_count"], 1)

            payload = json.dumps([{"id": i, "service": "PostgreSQL", "status": "ok"} for i in range(12)], indent=2)
            comp = compress_structured(payload)
            self.assertEqual(comp["format_used"], "toon")
            self.assertGreater(comp["saving_pct"], 30.0)

    def test_multi_runner_ocr_sync_router_and_constructive_offline_diagnostics(self) -> None:
        import io
        from cortical.cli import main as cli_main
        from cortical.composers.router import render_litellm_config_yaml
        from cortical.config import DEFAULT_CONFIG, resolve_active_runner_endpoint
        from cortical.harnesses.adapters import plan_sync, resolve_user_paths
        from cortical.mcp_server import CorticalMCPServer
        from cortical.privacy.sanitizer import ocr_image_local

        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["active_runner"] = "unsloth"
        r_name, r_type, v1_url = resolve_active_runner_endpoint(cfg, v1=True)
        self.assertEqual((r_name, r_type, v1_url), ("unsloth", "openai_compatible", "http://127.0.0.1:8888/v1"))

        captured_req: dict[str, str] = {}

        class _FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self) -> bytes:
                return json.dumps({"choices": [{"message": {"content": "Transcribed via Unsloth VLM"}}]}).encode("utf-8")

        def _fake_urlopen(req, timeout=10):
            captured_req["url"] = req.full_url
            captured_req["body"] = req.data.decode("utf-8")
            return _FakeResp()

        with mock.patch("urllib.request.urlopen", side_effect=_fake_urlopen):
            ocr_txt = ocr_image_local(b"\x89PNG\r\n\x1a\nfake", model="qwen2.5vl:3b", config=cfg)
        self.assertEqual(ocr_txt, "Transcribed via Unsloth VLM")
        self.assertEqual(captured_req["url"], "http://127.0.0.1:8888/v1/chat/completions")
        self.assertIn("image_url", captured_req["body"])

        cfg_lm = copy.deepcopy(DEFAULT_CONFIG)
        cfg_lm["active_runner"] = "lm_studio"
        yaml_txt = render_litellm_config_yaml(cfg_lm)
        self.assertIn("model: openai/", yaml_txt)
        self.assertIn("api_base: http://127.0.0.1:1234/v1", yaml_txt)

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            paths = resolve_user_paths(os_name="macos", home=root)
            changes = plan_sync(
                cfg_lm,
                {"os": "macos", "total_ram_gb": 16.0, "free_ram_gb": 10.0, "unified_memory": True, "vram_gb": 11.2, "binaries": {}},
                {"recommended_by_role": {"daily_coder": {"model_id": "local-coder", "recommended_num_ctx": 32768}}},
                harnesses=["pi"],
                user_paths=paths,
                repo_root=root,
                vault_db_path=root / "vault.db",
            )
            pi_mod = next(c for c in changes if c.path.name == "models.json")
            self.assertIn("http://127.0.0.1:1234/v1", pi_mod.content)
            self.assertIn('"lm_studio"', pi_mod.content)

            dead_cfg = copy.deepcopy(DEFAULT_CONFIG)
            dead_cfg["active_runner"] = "lm_studio"
            dead_cfg["runners"]["lm_studio"]["base_url"] = "http://127.0.0.1:9/v1"
            mcp = CorticalMCPServer(vault_db=root / "vault.db")
            with mock.patch("cortical.mcp_server.load_cortical_config", return_value=dead_cfg):
                off = mcp._dispatch_tool("cortical_local_offload", {"prompt": "ping"})
            self.assertFalse(off["completed_locally"])
            self.assertTrue(off["zero_llm_stdlib_active"])
            self.assertIn("Tier-1 Zero-LLM Stdlib", off["response"])
            self.assertIn("LM Studio", off["response"])

            buf = io.StringIO()
            with mock.patch("pathlib.Path.home", return_value=root), \
                 mock.patch("sys.stdout", buf):
                rc = cli_main(["sync", "--harness", "antigravity", "--repo-root", str(root), "--db", str(root / "vault.db")])
            self.assertEqual(rc, 0)
            self.assertIn("Undo anytime: cortical sync --rollback", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
