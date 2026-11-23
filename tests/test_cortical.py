"""Comprehensive 100%-offline unit test suite for redesigned Cortical Control Plane."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
import zipfile
import zlib
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from cortical.analytics.benchmark import run_comparative_benchmark
from cortical.analytics.dashboard import build_dashboard_env, export_static_dashboard, render_static_settings_html
from cortical.analytics.roi import build_roi_report, format_roi_markdown
from cortical.analytics.tuner import analyze_and_tune
from cortical.cli import main as cli_main
from cortical.compression.engine import compress_structured, fit_to_token_budget
from cortical.compression.toon import decode_toon, encode_toon
from cortical.composers.tools import build_serve_mcp_command, inspect_composed_tools, serve_mcp_http
from cortical.config import (
    DEFAULT_CONFIG,
    default_data_dir,
    ensure_telemetry_schema,
    invoke_configured_runner,
    load_cortical_config,
    register_runner_adapter,
    save_cortical_config,
)
from cortical.harnesses.adapters import (
    ALL_HARNESSES,
    apply_sync,
    get_harness_presend_matrix,
    plan_sync,
    resolve_user_paths,
    rollback_sync,
)
from cortical.hardware.context_window import (
    compute_dynamic_num_ctx,
    get_model_context_window,
    register_model_context_provider,
)
from cortical.hardware.models import (
    add_custom_model,
    pull_model,
    recommend_models_for_hardware,
    remove_custom_model,
)
from cortical.hardware.probe import classify_hardware_tier
from cortical.mcp_server import CorticalMCPServer
from cortical.privacy.sanitizer import (
    FailClosedError,
    classify_and_sanitize,
    ensure_privacy_ignore_files,
    extract_text_and_strip_metadata,
    register_vision_adapter,
)
from cortical.privacy.vault import PrivacyVault

FIXTURES_PATH = Path(__file__).resolve().parent / "fixtures" / "api_fixtures.json"


def _load_fixtures() -> dict:
    return json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))


class TestHardwareAndModels(unittest.TestCase):
    def test_classify_all_five_tiers_and_fixtures(self) -> None:
        fx = _load_fixtures()["hardware_profiles"]

        # Tier 0 Lean
        t0 = classify_hardware_tier({"total_ram_gb": 8.0, "free_ram_gb": 3.0, "vram_gb": 0.0, "unified_memory": False, "disk_free_gb": 40.0})
        self.assertEqual(t0["tier"], "tier_0_lean")
        self.assertFalse(t0["local_llm_viable"])

        # Tier 1A Hybrid Laptop (16GB RAM + 4GB VRAM NVIDIA MX250 from fixture)
        mx = fx["linux_laptop_mx250"]
        t1a = classify_hardware_tier({
            "total_ram_gb": mx["ram_total_gb"],
            "free_ram_gb": 10.0,
            "vram_gb": mx["vram_gb"],
            "unified_memory": mx["unified_memory"],
            "disk_free_gb": 80.0,
        })
        self.assertEqual(t1a["tier"], "tier_1a_hybrid_laptop")
        self.assertTrue(t1a["local_llm_viable"])

        # Tier 1B Unified 16GB (Apple M2 Pro fixture)
        m2 = fx["mac_m2_pro_16gb"]
        t1b = classify_hardware_tier({
            "total_ram_gb": m2["ram_total_gb"],
            "free_ram_gb": 11.0,
            "vram_gb": m2["vram_gb"],
            "unified_memory": m2["unified_memory"],
            "disk_free_gb": 80.0,
        })
        self.assertEqual(t1b["tier"], "tier_1b_unified_16_24")
        self.assertIn("27B", t1b["recommendation"])

        # Tier 2 Workstation & Tier 3 Studio
        t2 = classify_hardware_tier({"total_ram_gb": 32.0, "free_ram_gb": 22.0, "vram_gb": 24.0, "unified_memory": False, "disk_free_gb": 200.0})
        t3 = classify_hardware_tier({"total_ram_gb": 64.0, "free_ram_gb": 48.0, "vram_gb": 48.0, "unified_memory": True, "disk_free_gb": 500.0})
        self.assertEqual(t2["tier"], "tier_2_workstation")
        self.assertEqual(t3["tier"], "tier_3_studio")

    def test_recommend_variable_quant_27b_and_custom_models(self) -> None:
        hw_tier0 = {"total_ram_gb": 8.0, "free_ram_gb": 3.0, "vram_gb": 0.0, "unified_memory": False}
        hw_tier0["classification"] = classify_hardware_tier(hw_tier0)
        rec0 = recommend_models_for_hardware(hw_tier0)
        self.assertFalse(rec0["local_llm_viable"])
        self.assertEqual(rec0["recommended_by_role"], {})

        hw_1b = {"total_ram_gb": 16.0, "free_ram_gb": 11.5, "vram_gb": 11.2, "unified_memory": True}
        hw_1b["classification"] = classify_hardware_tier(hw_1b)
        rec1b = recommend_models_for_hardware(hw_1b, installed_models=[])
        deep = rec1b["recommended_by_role"]["deep_reasoner"]
        self.assertEqual(deep["model_id"], "qwen3.8:27b-q4_xxs")
        self.assertEqual(deep["memory_gb"], 8.1)
        self.assertGreaterEqual(deep["recommended_num_ctx"], 16384)

        cfg = json.loads(json.dumps(DEFAULT_CONFIG))
        entry = add_custom_model(cfg, {
            "model_id": "custom/coder:q4_xxs",
            "memory_gb": 6.5,
            "native_ctx": 65536,
            "quantization": "Unsloth Q4_XXS",
            "is_variable_quant": True,
            "roles": ["daily_coder", "deep_reasoner"],
        })
        self.assertEqual(entry["model_id"], "custom/coder:q4_xxs")
        self.assertTrue(remove_custom_model(cfg, "custom/coder:q4_xxs"))
        self.assertFalse(remove_custom_model(cfg, "custom/coder:q4_xxs"))

        dry = pull_model("qwen3.8:27b-q4_xxs", dry_run=True)
        self.assertTrue(dry["ok"])
        self.assertTrue(dry["dry_run"])
        self.assertEqual(dry["command"], "ollama pull qwen3.8:27b-q4_xxs")

    def test_dynamic_ctx_and_provider_registration(self) -> None:
        ctx_ok = compute_dynamic_num_ctx(32768, "qwen3.8:27b-q4_xxs", ram_available_gb=12.0, unified_memory=True, model_ram_gb=8.1)
        ctx_tight = compute_dynamic_num_ctx(32768, "qwen3.8:27b-q4_xxs", ram_available_gb=3.0, unified_memory=True, model_ram_gb=8.1)
        self.assertEqual(ctx_ok, 32768)
        self.assertEqual(ctx_tight, 4096)

        register_model_context_provider(lambda mid: {"context_length": 65536, "parameter_size": "27B"} if mid == "mock:27b" else None)
        win = get_model_context_window("mock:27b")
        self.assertEqual(win, 65536)


class TestCompression(unittest.TestCase):
    def test_toon_roundtrip_and_saving_guard(self) -> None:
        payload = {
            "meta": {"env": "prod:eu", "note": "hello, world"},
            "items": [
                {"id": 1, "name": "alpha", "ok": True, "score": 9.5},
                {"id": 2, "name": "beta, inc", "ok": False, "score": 8.0},
                {"id": 3, "name": "123", "ok": True, "score": 7.25},
                {"id": 4, "name": "true", "ok": False, "score": 6.0},
            ],
        }
        encoded = encode_toon(payload)
        decoded = decode_toon(encoded)
        self.assertEqual(decoded, payload)

        # Uniform table compresses >=10% better than compact JSON
        uniform_big = {"rows": [{"id": i, "mod": f"m{i}", "status": "ok", "local": True} for i in range(15)]}
        comp = compress_structured(json.dumps(uniform_big, indent=2), fmt="json", min_saving_pct=10.0)
        self.assertEqual(comp["format_used"], "toon")
        self.assertTrue(comp["lossless"])
        self.assertGreater(comp["saving_pct"], 50.0)

        # When saving is below threshold guard, falls back cleanly to compact_json
        tiny = compress_structured('{"a": 1, "b": 2}', fmt="json", min_saving_pct=90.0)
        self.assertEqual(tiny["format_used"], "compact_json")

        # XML and ANSI log compaction
        xml_c = compress_structured("<root>\n  <!-- ignore -->\n  <item>ok</item>\n</root>", fmt="xml")
        self.assertEqual(xml_c["compressed"], "<root><item>ok</item></root>")

        log_raw = "\x1b[32mINFO ok\x1b[0m\n" * 6
        log_c = compress_structured(log_raw, fmt="log")
        self.assertEqual(log_c["format_used"], "log_compacted")
        self.assertIn("[repeated x5]", log_c["compressed"])

    def test_fit_to_token_budget(self) -> None:
        blocks = [
            {"alias": "b1", "content": "A " * 800, "priority": 90},
            {"alias": "b2", "content": "B " * 800, "priority": 80},
        ]
        fitted = fit_to_token_budget(blocks, num_ctx=4096, max_share=0.15)
        self.assertLessEqual(fitted["budget_tokens"], int(4096 * 0.15) + 1)
        self.assertLessEqual(fitted["used_tokens"], fitted["budget_tokens"] + 32)


class TestPrivacyVault(unittest.TestCase):
    def test_zero_false_positives_and_dynamic_policies(self) -> None:
        prose = (
            "Architectural Summary: Cortical Control Plane connects Serena Language Server, "
            "Dynamic Context Scaling, Python Stdlib, and Apache License."
        )
        clean = classify_and_sanitize(prose, policy="auto", profile="medium")
        self.assertEqual(clean["resolved_policy"], "fail_open")
        self.assertFalse(clean["requires_confirmation"])
        self.assertEqual(clean["sanitized_text"], prose)

        pii_text = f"{prose}\nContact: alice@example.org, IBAN IT60X0542811101000000123456, Project Orion."
        masked = classify_and_sanitize(pii_text, policy="auto", profile="medium", custom_terms=["Project Orion"])
        self.assertEqual(masked["resolved_policy"], "fail_closed")
        self.assertTrue(masked["requires_confirmation"])
        self.assertNotIn("alice@example.org", masked["sanitized_text"])
        self.assertNotIn("IT60X0542811101000000123456", masked["sanitized_text"])
        self.assertNotIn("Project Orion", masked["sanitized_text"])
        self.assertIn("Cortical Control Plane", masked["sanitized_text"])
        self.assertIn("Serena Language Server", masked["sanitized_text"])

        # FailClosedError on failed local NER under fail_closed
        with self.assertRaises(FailClosedError):
            classify_and_sanitize(
                pii_text,
                policy="fail_closed",
                profile="medium",
                use_local_ner=True,
                llm_fn=lambda _p: (_ for _ in ()).throw(RuntimeError("offline")),
            )

        # Successful injectable local JSON NER (tests both {"entities": [...]} and direct list)
        ner_res = classify_and_sanitize(
            "Internal review with mario rossi for Client Alpha.",
            policy="fail_closed",
            profile="low",
            use_local_ner=True,
            llm_fn=lambda _p: json.dumps({"entities": [
                {"text": "mario rossi", "category": "PERSON_NAME"},
                {"text": "Client Alpha", "category": "ORG"},
            ]}),
        )
        self.assertNotIn("mario rossi", ner_res["sanitized_text"])
        self.assertNotIn("Client Alpha", ner_res["sanitized_text"])

    def test_ooxml_metadata_strip_and_channels_1_to_3(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tpath = Path(tmp)
            docx_path = tpath / "sensitive_contract.docx"
            with zipfile.ZipFile(docx_path, "w") as zf:
                zf.writestr("docProps/core.xml", "<cp:coreProperties><dc:creator>Real Author</dc:creator></cp:coreProperties>")
                zf.writestr("word/document.xml", "<w:t>Agreement for bob@acme.example and €5,000 budget.</w:t>")

            ignores = ensure_privacy_ignore_files(tpath)
            self.assertEqual(len(ignores), 3)
            self.assertTrue((tpath / ".geminiignore").is_file())

            vault = PrivacyVault(tpath / "vault.db")
            ing1 = vault.ingest(docx_path, alias="contract_pub", policy="auto", profile="medium")
            self.assertEqual(ing1["resolved_policy"], "fail_closed")
            self.assertNotIn("bob@acme.example", ing1["sanitized_preview"])
            self.assertNotIn("Real Author", ing1["sanitized_preview"])

            ing2 = vault.ingest("Secret key sk-1234567890abcdefghij", alias="local_sec", policy="fail_closed", profile="max_security")
            self.assertTrue(ing2["local_only"])

            res_list = vault.list_resources(include_local_only=False)
            aliases = [r["uri"] for r in res_list]
            self.assertIn("cortical://private/contract_pub", aliases)
            self.assertNotIn("cortical://private/local_sec", aliases)

            with self.assertRaises(FailClosedError):
                vault.read_resource("local_sec", allow_local_only=False)
            local_ok = vault.read_resource("local_sec", allow_local_only=True)
            self.assertNotIn("sk-1234567890abcdefghij", local_ok["text"])

            # Channel 2 budgeted markdown
            md = vault.export_sanitized_memory_markdown(num_ctx=16384, max_share=0.15)
            self.assertIn("@private:contract_pub", md)
            self.assertNotIn("local_sec", md)

            # Channel 3 pre-send verification matrix
            sample_f = tpath / "note.txt"
            sample_f.write_text("Send to clara@example.net", encoding="utf-8")
            ic_pi = vault.intercept_pre_send("pi", "Check attached note", [sample_f])
            self.assertTrue(ic_pi["supported"])
            self.assertTrue(ic_pi["blocked_raw_upload"])
            self.assertNotIn("clara@example.net", ic_pi["proposed_remote_prompt"])

            ic_dsh = vault.intercept_pre_send("dsh", "Check attached note", [sample_f])
            self.assertTrue(ic_dsh["supported"])

            ic_agy = vault.intercept_pre_send("antigravity", "Check attached note", [sample_f])
            self.assertFalse(ic_agy["supported"])


class TestComposersAndHarnesses(unittest.TestCase):
    def test_cross_platform_composers_sync_and_rollback(self) -> None:
        tools_mac = inspect_composed_tools("macos")
        tools_win = inspect_composed_tools("windows")
        self.assertIn("brew", tools_mac["rtk"]["install_cmd"].lower())
        self.assertEqual(tools_win["rtk"]["install_cmd"], "cargo install rtk")

        cmd = build_serve_mcp_command("serena", Path("."), port=9121)
        self.assertIn("9121", cmd)
        srv = serve_mcp_http("cortical", Path("."), port=9122, dry_run=True)
        self.assertTrue(srv["dry_run"])
        self.assertEqual(srv["url"], "http://127.0.0.1:9122/mcp")

        with tempfile.TemporaryDirectory() as tmp:
            fake_home = Path(tmp) / "home"
            fake_app = Path(tmp) / "appdata"
            paths_mac = resolve_user_paths("macos", home=fake_home)
            paths_lin = resolve_user_paths("linux", home=fake_home, xdg_config=fake_home / ".xdg")
            paths_win = resolve_user_paths("windows", home=fake_home, appdata=fake_app)
            self.assertIn(".gemini", str(paths_mac["antigravity"]["mcp"]))
            self.assertIn(".xdg", str(paths_lin["opencode"]["config"]))
            self.assertIn("appdata", str(paths_win["opencode"]["config"]))

            # Preserve unrelated pre-existing keys across JSON/TOML configs
            paths_mac["antigravity"]["mcp"].parent.mkdir(parents=True, exist_ok=True)
            paths_mac["antigravity"]["mcp"].write_text(json.dumps({
                "mcpServers": {"user-existing": {"command": "echo", "args": ["ok"]}}
            }), encoding="utf-8")
            paths_mac["codex"]["config"].parent.mkdir(parents=True, exist_ok=True)
            paths_mac["codex"]["config"].write_text('model = "gpt-5"\n', encoding="utf-8")

            hw = {"os": "macos", "total_ram_gb": 16.0, "free_ram_gb": 11.0, "vram_gb": 11.2, "unified_memory": True, "binaries": {"serena": "serena"}}
            hw["classification"] = classify_hardware_tier(hw)
            rec = recommend_models_for_hardware(hw, installed_models=[])

            self.assertEqual(len(ALL_HARNESSES), 8)
            self.assertIn("dsh", ALL_HARNESSES)
            self.assertTrue(get_harness_presend_matrix()["dsh"])

            changes = plan_sync(
                DEFAULT_CONFIG,
                hw,
                rec,
                vault_markdown="## Vault\n- safe",
                repo_root=fake_home / "repo",
                vault_db_path=fake_home / "vault.db",
                user_paths=paths_mac,
            )
            harnesses_covered = {c.harness for c in changes}
            self.assertEqual(harnesses_covered, set(ALL_HARNESSES))

            backup_root = Path(tmp) / "backups"
            res = apply_sync(changes, backup_root=backup_root)
            self.assertIsNotNone(res["backup_id"])
            self.assertGreater(res["changed_count"], 5)

            merged_agy = json.loads(paths_mac["antigravity"]["mcp"].read_text(encoding="utf-8"))
            self.assertIn("user-existing", merged_agy["mcpServers"])
            self.assertIn("cortical-mcp", merged_agy["mcpServers"])
            codex_txt = paths_mac["codex"]["config"].read_text(encoding="utf-8")
            self.assertIn('model = "gpt-5"', codex_txt)
            self.assertIn("[mcp_servers.cortical_mcp]", codex_txt)
            dsh_txt = paths_mac["dsh"]["settings"].read_text(encoding="utf-8")
            self.assertIn("@deepseek-ai/dsh-mcp-client", dsh_txt)

            rb = rollback_sync(res["backup_id"], backup_root=backup_root)
            self.assertGreater(rb["restored"], 0)
            restored_agy = json.loads(paths_mac["antigravity"]["mcp"].read_text(encoding="utf-8"))
            self.assertNotIn("cortical-mcp", restored_agy["mcpServers"])
            self.assertEqual(paths_mac["codex"]["config"].read_text(encoding="utf-8"), 'model = "gpt-5"\n')
            self.assertFalse(paths_mac["dsh"]["settings"].exists())


class TestMCPConfigAnalyticsAndCLI(unittest.TestCase):
    def test_config_telemetry_and_mcp_server(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tpath = Path(tmp)
            cfg_p = tpath / "cortical.config.json"
            cfg = load_cortical_config(cfg_p)
            cfg["active_model"] = "qwen3.8:27b-q4_xxs"
            save_cortical_config(cfg, cfg_p)
            reloaded = load_cortical_config(cfg_p)
            self.assertEqual(reloaded["active_model"], "qwen3.8:27b-q4_xxs")

            telem_db = tpath / "vault.db"
            ensure_telemetry_schema(telem_db).close()
            register_runner_adapter("mock_local", lambda sys_p, usr_p, _cfg: f"LOCAL_OK: {usr_p[:30]}")
            with patch.dict(os.environ, {"CORTICAL_TELEMETRY_DB": str(telem_db)}):
                cfg["active_runner"] = "mock_local"
                ans = invoke_configured_runner("Summarize architecture", config=cfg, model_override="qwen3.8:27b-q4_xxs")
                self.assertIn("LOCAL_OK", ans)

                srv = CorticalMCPServer(vault_db=telem_db)
                init_r = srv.handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
                self.assertEqual(init_r["result"]["serverInfo"]["name"], "cortical-mcp")

                list_r = srv.handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
                self.assertEqual(len(list_r["result"]["tools"]), 7)

                h_save = srv.handle_request({
                    "jsonrpc": "2.0", "id": 11, "method": "tools/call",
                    "params": {"name": "cortical_handoff", "arguments": {"action": "save", "goal": "Test handoff", "summary": "Step 1 done", "next_step": "Run pi", "source_harness": "antigravity"}},
                })
                self.assertIn("Test handoff", h_save["result"]["content"][0]["text"])
                h_load = srv.handle_request({
                    "jsonrpc": "2.0", "id": 12, "method": "tools/call",
                    "params": {"name": "cortical_handoff", "arguments": {"action": "load"}},
                })
                self.assertIn("Run pi", h_load["result"]["content"][0]["text"])

                srv.handle_request({
                    "jsonrpc": "2.0", "id": 3, "method": "tools/call",
                    "params": {"name": "cortical_ingest_private", "arguments": {"path_or_text": "Email test@example.org", "alias": "memo"}},
                })
                res_r = srv.handle_request({"jsonrpc": "2.0", "id": 4, "method": "resources/read", "params": {"uri": "cortical://private/memo"}})
                self.assertNotIn("test@example.org", res_r["result"]["contents"][0]["text"])

                pr_r = srv.handle_request({"jsonrpc": "2.0", "id": 5, "method": "prompts/get", "params": {"name": "cortical-private", "arguments": {"alias": "memo"}}})
                self.assertIn("memo", pr_r["result"]["messages"][0]["content"]["text"])
                self.assertIsNone(srv.handle_request({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}))
                for pa in ({}, {"alias": ""}, {"alias": "nope"}, {"alias": "@private:mem"}):
                    r_ = srv.handle_request({"jsonrpc": "2.0", "id": 9, "method": "prompts/get", "params": {"name": "cortical-private", "arguments": pa}})
                    self.assertIn("result", r_)
                    self.assertIn("memo", r_["result"]["messages"][0]["content"]["text"])
                c_ = srv.handle_request({"jsonrpc": "2.0", "id": 10, "method": "completion/complete", "params": {"argument": {"name": "alias", "value": "me"}}})
                self.assertEqual(c_["result"]["completion"]["values"], ["memo"])

    def test_analytics_and_cli_smoke(self) -> None:
        bench = run_comparative_benchmark()
        self.assertEqual(bench["lean_mcp"]["tool_count"], 7)
        self.assertEqual(bench["compression_before_vs_after"]["format_used"], "toon")
        self.assertGreater(bench["compression_before_vs_after"]["saving_vs_compact_pct"], 50.0)

        with tempfile.TemporaryDirectory() as tmp:
            tpath = Path(tmp)
            s_html, h_html = export_static_dashboard(tpath / "out", config=DEFAULT_CONFIG, public_docs=True)
            self.assertTrue(s_html.is_file())
            self.assertTrue(h_html.is_file())

            cfg_p = tpath / "c.json"
            tuned = analyze_and_tune(config=json.loads(json.dumps(DEFAULT_CONFIG)), apply_changes=True, config_path=cfg_p)
            self.assertTrue(tuned["applied"])
            self.assertTrue(cfg_p.is_file())

            roi = build_roi_report(db_path=tpath / "none.db", brain_dir=tpath / "no_brain")
            self.assertIn("Cortical Token & Offload Report", format_roi_markdown(roi))

            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertEqual(cli_main(["bench", "--compare", "--json"]), 0)
                self.assertEqual(cli_main(["models", "list", "--json"]), 0)
                self.assertEqual(cli_main(["serve-mcp", "cortical", "--dry-run", "--json"]), 0)
                self.assertEqual(cli_main(["dashboard", "--out-dir", str(tpath / "html"), "--json"]), 0)
            self.assertIn("compression_before_vs_after", buf.getvalue())


def _build_synthetic_pdf(text: str, *, compressed: bool = True, author: str = "Secret PDF Author") -> bytes:
    """Builds a minimal syntactically valid single-page PDF with optional FlateDecode stream & metadata."""
    stream_body = f"BT\n/F1 12 Tf\n72 720 Td\n({text}) Tj\nET\n".encode("latin-1")
    if compressed:
        stream_data = zlib.compress(stream_body)
        stream_hdr = f"<< /Length {len(stream_data)} /Filter /FlateDecode >>".encode("ascii")
    else:
        stream_data = stream_body
        stream_hdr = f"<< /Length {len(stream_data)} >>".encode("ascii")

    objs = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>\nendobj\n",
        b"4 0 obj\n" + stream_hdr + b"\nstream\n" + stream_data + b"\nendstream\nendobj\n",
        f"5 0 obj\n<< /Author ({author}) /Title (Private Report) >>\nendobj\n".encode("latin-1"),
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objs:
        offsets.append(len(out))
        out.extend(obj)
    xref_pos = len(out)
    out.extend(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode("ascii"))
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    out.extend(f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R /Info 5 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode("ascii"))
    return bytes(out)


class TestFileBackedZeroServerVault(unittest.TestCase):
    def test_compressed_pdf_extraction_empty_pdf_fail_closed_and_vault_crud(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tpath = Path(tmp)
            pdf_path = tpath / "alsa.pdf"
            pdf_path.write_bytes(_build_synthetic_pdf("Cliente Mario Rossi Email mario@example.org IBAN IT60X0542811101000000123456", compressed=True))

            # Force stdlib zlib + Tj extractor path even when host has pdftotext
            with patch("shutil.which", return_value=None):
                txt, meta = extract_text_and_strip_metadata(pdf_path)
            self.assertIn("pdf:/Author", meta)
            self.assertIn("Mario Rossi", txt)
            self.assertNotIn("Secret PDF Author", txt)

            empty_pdf = tpath / "scanned.pdf"
            empty_pdf.write_bytes(b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n")
            with patch("shutil.which", return_value=None):
                with self.assertRaises(FailClosedError):
                    extract_text_and_strip_metadata(empty_pdf)

            vault = PrivacyVault(tpath / "vault.db")
            ing = vault.ingest_bytes("alsa.pdf", pdf_path.read_bytes(), profile="max_security", custom_terms=["Mario Rossi"])
            self.assertEqual(ing["alias"], "alsa")
            self.assertTrue(ing["local_only"])
            # Persists disk JSON mirror cleanly
            self.assertTrue((tpath / "vault" / "alsa.json").is_file())

            # Local management lists max_security; cloud MCP resources hide it
            all_items = vault.list_items(include_local_only=True)
            self.assertEqual(len(all_items), 1)
            self.assertEqual(all_items[0]["alias"], "alsa")
            self.assertEqual(vault.list_resources(include_local_only=False), [])

            # Re-sanitize to medium with extra custom term makes it chat-safe
            upd = vault.re_sanitize("alsa", profile="medium", custom_terms=["Cliente"])
            self.assertFalse(upd["local_only"])
            self.assertEqual(len(vault.list_resources(include_local_only=False)), 1)
            read_ok = vault.read_resource("alsa", allow_local_only=False)
            self.assertNotIn("mario@example.org", read_ok["text"])
            self.assertNotIn("Mario Rossi", read_ok["text"])

            self.assertTrue(vault.delete_item("alsa"))
            self.assertEqual(vault.list_items(), [])
            self.assertFalse((tpath / "vault" / "alsa.json").exists())

    def test_static_ui_json_tombstone_inbox_ingest_and_cli_vault(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tpath = Path(tmp)
            db_p = tpath / "vault.db"
            vault = PrivacyVault(db_p)

            # 1. Static UI drops a max_security JSON record directly in .cortical_data/vault/alsa.json
            vault.vault_dir.mkdir(parents=True, exist_ok=True)
            (vault.vault_dir / "alsa.json").write_text(json.dumps({
                "alias": "alsa",
                "source_name": "alsa.pdf",
                "resolved_policy": "fail_closed",
                "profile": "max_security",
                "local_only": True,
                "format_used": "text",
                "sanitized_content": "ALSA extracted text with [REDACTED]",
                "entity_count": 2,
                "tokens_est": 8,
                "updated_at": 2000000000.0,
            }), encoding="utf-8")

            # Vault immediately sees max_security locally while cloud MCP keeps blocking it
            items = vault.list_items(include_local_only=True)
            self.assertEqual([i["alias"] for i in items], ["alsa"])
            self.assertTrue(items[0]["local_only"])
            self.assertEqual(vault.list_resources(include_local_only=False), [])
            local_read = vault.read_resource("alsa", allow_local_only=True)
            self.assertIn("[REDACTED]", local_read["text"])

            # 2. Static UI writes tombstone deletion -> sync_from_disk() deletes from SQLite & removes tombstone
            (vault.vault_dir / "alsa.json").write_text(json.dumps({"alias": "alsa", "deleted": True}), encoding="utf-8")
            self.assertEqual(vault.list_items(include_local_only=True), [])
            self.assertFalse((vault.vault_dir / "alsa.json").exists())

            # 3. Complex PDF dropped in vault_inbox/ -> automatically extracted, sanitized, JSON-mirrored & raw PDF shredded
            vault.inbox_dir.mkdir(parents=True, exist_ok=True)
            pdf_bytes = _build_synthetic_pdf("ALSA Confidential bob@alsa.example IBAN IT60X0542811101000000123456", compressed=True)
            (vault.inbox_dir / "alsa.pdf").write_bytes(pdf_bytes)
            (vault.inbox_dir / "alsa.pdf.meta.json").write_text(json.dumps({
                "alias": "alsa",
                "policy": "auto",
                "profile": "max_security",
                "custom_terms": ["ALSA Confidential"],
            }), encoding="utf-8")

            items_after = vault.list_items(include_local_only=True)
            self.assertEqual([i["alias"] for i in items_after], ["alsa"])
            self.assertFalse((vault.inbox_dir / "alsa.pdf").exists())
            self.assertFalse((vault.inbox_dir / "alsa.pdf.meta.json").exists())

            # 4. CLI vault list / show --local-ok / update / delete smoke tests
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertEqual(cli_main(["vault", "list", "--db", str(db_p), "--json"]), 0)
                self.assertEqual(cli_main(["vault", "show", "alsa", "--local-ok", "--db", str(db_p), "--json"]), 0)
                self.assertEqual(cli_main(["vault", "update", "alsa", "--profile", "medium", "--db", str(db_p), "--json"]), 0)
                self.assertEqual(cli_main(["vault", "delete", "alsa", "--db", str(db_p), "--json"]), 0)
            self.assertIn("alsa", buf.getvalue())

            # 5. Static HTML contains zero localhost/port refs & includes pure-JS DecompressionStream + Vault UI
            static_html = render_static_settings_html(cfg=DEFAULT_CONFIG, public_docs=True)
            self.assertIn("DecompressionStream", static_html)
            self.assertIn("showDirectoryPicker", static_html)
            self.assertIn("img-canvas", static_html)
            self.assertNotIn("localhost:8765", static_html)
            self.assertNotIn("cortical.cli ui", static_html)

    def test_data_dir_vision_ocr_keep_terms_and_watch_cli(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tpath = Path(tmp)
            with patch.dict(os.environ, {"CORTICAL_DATA_DIR": str(tpath / "DocsCortical")}):
                self.assertEqual(default_data_dir(), tpath / "DocsCortical")

            # Image OCR requires vision_model under fail_closed
            png_path = tpath / "receipt.png"
            png_path.write_bytes(b"\x89PNG\r\n\x1a\nfake")
            with self.assertRaises(FailClosedError):
                extract_text_and_strip_metadata(png_path, vision_model="")

            # Registered local vision adapter extracts text + drops EXIF metadata
            try:
                register_vision_adapter(lambda _b, m: f"OCR[{m}]: Mario Rossi mario@example.org KeepBrand")
                txt, meta = extract_text_and_strip_metadata(png_path, vision_model="qwen2.5vl:3b")
                self.assertIn("image:exif-dropped", meta)
                self.assertIn("Mario Rossi", txt)

                # keep_terms preserves explicitly whitelisted tokens while masking PII
                db_p = tpath / "vault.db"
                vault = PrivacyVault(db_p)
                vault.inbox_dir.mkdir(parents=True, exist_ok=True)
                (vault.inbox_dir / "receipt.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
                (vault.inbox_dir / "receipt.png.meta.json").write_text(json.dumps({
                    "alias": "receipt",
                    "profile": "medium",
                    "custom_terms": ["Mario Rossi", "KeepBrand"],
                    "keep_terms": ["KeepBrand"],
                    "vision_model": "qwen2.5vl:3b",
                    "source_name": "receipt.png",
                }), encoding="utf-8")

                buf = io.StringIO()
                with redirect_stdout(buf):
                    self.assertEqual(cli_main(["watch", "--once", "--db", str(db_p)]), 0)
                item = vault.read_resource("receipt", allow_local_only=True)
                self.assertIn("KeepBrand", item["text"])
                self.assertNotIn("Mario Rossi", item["text"])
                self.assertNotIn("mario@example.org", item["text"])
            finally:
                register_vision_adapter(None)

            env = build_dashboard_env(public=True)
            self.assertIn("setup_cmd", env)
            self.assertIn("watch_cmd", env)
            self.assertIn("qwen2.5vl:3b", env["vision_suggestions"])

    def test_brain_3plus1_factorization_routing_threshold_and_capabilities(self) -> None:
        from cortical.analytics.roi import evaluate_routing_state
        from cortical.hardware.probe import _probe_ollama_capabilities

        # 1. Mock Ollama /api/show capability probing (`vision` detected on qwen3.5)
        class _MockResp:
            def __init__(self, body: str) -> None:
                self._b = body.encode("utf-8")
            def read(self) -> bytes:
                return self._b
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False

        with patch("urllib.request.urlopen", return_value=_MockResp(json.dumps({"capabilities": ["completion", "vision", "tools", "thinking"]}))):
            caps = _probe_ollama_capabilities("qwen3.5:9b-q3_k_xl")
        self.assertIn("vision", caps)
        self.assertIn("thinking", caps)

        # Model without mmproj (projector_info=None & empty model_info vision keys) must NOT advertise vision
        with patch("urllib.request.urlopen", return_value=_MockResp(json.dumps({"capabilities": ["completion", "vision", "tools"], "projector_info": None, "model_info": {"general.architecture": "qwen35"}}))):
            caps_no_proj = _probe_ollama_capabilities("qwen3.5:9b-q3_k_xl")
        self.assertNotIn("vision", caps_no_proj)
        self.assertIn("completion", caps_no_proj)

        # 2. 3+1 Brain: public file returns raw at `max`; private returns sanitized at `max`; concepts/skills factorized
        with tempfile.TemporaryDirectory() as tmp:
            tpath = Path(tmp)
            db_p = tpath / "vault.db"
            vault = PrivacyVault(db_p)
            vault.ingest(
                "1. Install uv tool\n2. Run pytest suite\n3. Deploy docker container for service alpha",
                alias="deploy_a",
                policy="fail_open",
                profile="max_context",
            )
            vault.ingest(
                "1. Install uv tool\n2. Run pytest suite\n3. Deploy docker container for Mario Rossi (mario@example.org)",
                alias="deploy_b",
                policy="auto",
                profile="medium",
                custom_terms=["Mario Rossi"],
            )
            pub_max = vault.read_resource("deploy_a", tier="max")
            self.assertIn("service alpha", pub_max["text"])
            priv_l1 = vault.read_resource("deploy_b", tier="light")
            self.assertIn("L1 LIGHT", priv_l1["text"])
            self.assertNotIn("mario@example.org", priv_l1["text"])
            priv_max = vault.read_resource("deploy_b", tier="max")
            self.assertNotIn("Mario Rossi", priv_max["text"])

            snap = vault.brain.get_snapshot(include_local_only=True)
            self.assertEqual(snap["stats"]["files"], 2)
            # Shared concepts/skills factorized (fewer than 2 separate unmerged entries!)
            self.assertEqual(snap["stats"]["concepts"], 1)
            self.assertEqual(snap["stats"]["skills"], 1)
            self.assertEqual(sorted(snap["by_concept"][0]["sources"]), ["deploy_a", "deploy_b"])

            # 3. MCP Server tier read + cortical://brain resource + routing threshold switch
            srv = CorticalMCPServer(vault_db=db_p)
            tr = srv.handle_request({"jsonrpc": "2.0", "id": 11, "method": "tools/call", "params": {"name": "cortical_vault_read", "arguments": {"alias": "deploy_b", "tier": "light"}}})
            self.assertIn("L1 LIGHT", tr["result"]["content"][0]["text"])
            br = srv.handle_request({"jsonrpc": "2.0", "id": 12, "method": "resources/read", "params": {"uri": "cortical://brain"}})
            self.assertIn("deploy_a", br["result"]["contents"][0]["text"])

            cfg_low = json.loads(json.dumps(DEFAULT_CONFIG))
            cfg_low["routing"] = {"mode": "auto", "cloud_budget_tokens": 100000, "cloud_token_threshold": 150000}
            rs_auto = evaluate_routing_state(config=cfg_low, db_path=db_p, brain_dir=tpath / "none")
            self.assertEqual(rs_auto["effective_mode"], "full_local")

            cfg_low["routing"] = {"mode": "cloud_first", "cloud_budget_tokens": 200000, "cloud_token_threshold": 50000}
            rs_cf = evaluate_routing_state(config=cfg_low, db_path=db_p, brain_dir=tpath / "none")
            self.assertEqual(rs_cf["effective_mode"], "cloud")

    def test_15_pi_chrome_profile_sync_and_form_parser(self) -> None:
        from cortical.config import DEFAULT_CONFIG
        from cortical.harnesses.adapters import plan_sync
        from cortical.harnesses.chrome import _PageParser, discover_chrome_profiles

        with tempfile.TemporaryDirectory() as tmp:
            fake_home = Path(tmp) / "home"
            (fake_home / ".pi" / "agent").mkdir(parents=True)
            pi_paths = {
                "pi": {
                    "mcp": fake_home / ".pi" / "agent" / "mcp.json",
                    "settings": fake_home / ".pi" / "agent" / "settings.json",
                    "models": fake_home / ".pi" / "agent" / "models.json",
                    "rules": fake_home / ".pi" / "agent" / "AGENTS.md",
                }
            }
            plan = plan_sync(DEFAULT_CONFIG, {}, {}, harnesses=["pi"], repo_root=Path(__file__).resolve().parent.parent, user_paths=pi_paths)
            mcp_changes = [c for c in plan if c.path.name == "mcp.json"]
            self.assertEqual(len(mcp_changes), 1)
            mcp_data = json.loads(mcp_changes[0].content)
            self.assertIn("chrome", mcp_data["mcpServers"])
            self.assertEqual(mcp_data["mcpServers"]["chrome"]["exposure"], "direct")
            self.assertIn("--autoConnect", mcp_data["mcpServers"]["chrome"]["args"])

            chrome_dir = Path(tmp) / "Chrome"
            chrome_dir.mkdir()
            (chrome_dir / "Local State").write_text(
                json.dumps({"profile": {"info_cache": {"Default": {"user_name": "ccancellieri@gmail.com", "name": "Carlo"}}}}),
                encoding="utf-8",
            )
            disc = discover_chrome_profiles(system_dir=chrome_dir)
            self.assertEqual(disc["profiles"][0]["email"], "ccancellieri@gmail.com")

        parser = _PageParser("https://jobs.example.org/apply")
        parser.feed("<html><title>Geo Job</title><body><form><input name='email' required/></form><a href='/cv'>CV</a></body></html>")
        self.assertEqual(parser.title, "Geo Job")
        self.assertEqual(parser.forms[0]["name"], "email")
        self.assertEqual(parser.links[0]["url"], "https://jobs.example.org/cv")

    def test_16_collect_pi_local_runs_and_roi_cumulative(self) -> None:
        from cortical.analytics.roi import collect_pi_local_runs

        with tempfile.TemporaryDirectory() as tmp:
            sess_dir = Path(tmp) / "sessions"
            sess_dir.mkdir()
            (sess_dir / "s1.jsonl").write_text(
                "\n".join([
                    json.dumps({"timestamp": "2026-11-22T17:00:00Z", "message": {"role": "assistant", "provider": "router", "model": "qwen3.5:9b-q3_k_xl", "usage": {"input": 10000, "output": 500, "totalTokens": 10500}}}),
                    json.dumps({"timestamp": "2026-11-22T17:01:00Z", "message": {"role": "assistant", "provider": "anthropic", "model": "claude-sonnet", "usage": {"input": 2000, "output": 200, "totalTokens": 2200}}}),
                ]) + "\n",
                encoding="utf-8",
            )
            runs = collect_pi_local_runs(pi_sessions_dir=sess_dir)
            self.assertEqual(len(runs), 1)
            self.assertEqual(runs[0]["total_tokens"], 10500)
            self.assertEqual(runs[0]["model"], "qwen3.5:9b-q3_k_xl")

    def test_17_vault_task_tags_and_mcp_task_context(self) -> None:
        from cortical.mcp_server import CorticalMCPServer

        with tempfile.TemporaryDirectory() as tmp:
            srv = CorticalMCPServer(vault_db=Path(tmp) / "vault.db")
            srv._dispatch_tool("cortical_ingest_private", {
                "path_or_text": "Contratto ESA geoid-dynastore con budget cloud 100 EUR",
                "alias": "esa_note",
                "profile": "medium",
                "task_tags": ["ESA-Apply", "#unsloth"],
            })
            srv._dispatch_tool("cortical_ingest_private", {
                "path_or_text": "Codice fiscale RSSMRA80A01H501U privato",
                "alias": "secret_id",
                "profile": "max_security",
                "task_tags": ["esa-apply"],
            })
            ctx = srv._dispatch_tool("cortical_vault_read", {"task_tag": "esa-apply", "tier": "light"})
            self.assertEqual(ctx["count"], 1)
            self.assertEqual(ctx["documents"][0]["alias"], "esa_note")
            self.assertIn("secret_id", ctx["blocked_max_security_aliases"])

    def test_18_composed_tools_test_helper(self) -> None:
        from cortical.composers.tools import test_composed_tool

        bad = test_composed_tool("unknown_nonexistent_tool")
        self.assertFalse(bad["ok"])
        rtk_res = test_composed_tool("rtk")
        self.assertIn("installed", rtk_res)
        if rtk_res["installed"]:
            self.assertTrue(rtk_res["ok"])

    def test_19_vault_auto_tagging_default_tags(self) -> None:
        from cortical.privacy.vault import PrivacyVault

        with tempfile.TemporaryDirectory() as tmp:
            v = PrivacyVault(Path(tmp) / "vault.db")
            p = Path(tmp) / "contratto_consulenza.md"
            p.write_text("Accordo quadro per servizi cloud con Mario Rossi.", encoding="utf-8")
            ing = v.ingest(p, alias="acc_quadro", profile="medium")
            self.assertIn("contract", ing["task_tags"])
            self.assertIn("notes", ing["task_tags"])
            ctx = v.read_task_context("contract", tier="light")
            self.assertEqual(ctx["count"], 1)
            self.assertEqual(ctx["documents"][0]["alias"], "acc_quadro")

    def test_20_workspace_autodiscovery_and_cortical_init(self) -> None:
        from cortical.workspace import (
            discover_workspace_root,
            init_workspace,
            read_workspace_config,
            resolve_default_db,
            resolve_default_export_dir,
        )

        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "demo_repo"
            nested = proj / "src" / "pkg"
            nested.mkdir(parents=True)
            (proj / ".git").mkdir()

            self.assertEqual(discover_workspace_root(nested), proj.resolve())
            res = init_workspace(proj, update_gitignore=True, sync_ignores=True)
            self.assertTrue(res["ok"])
            self.assertTrue((proj / ".cortical" / "wiki.db").is_file())
            self.assertTrue((proj / ".cortical" / "config.json").is_file())
            self.assertTrue((proj / ".cortical" / "exports").is_dir())
            self.assertTrue((proj / ".cortical" / "logs").is_dir())
            self.assertIn(".cortical/", (proj / ".gitignore").read_text(encoding="utf-8"))
            self.assertTrue((proj / ".corticalignore").is_file())
            for ig in (".claudeignore", ".cursorignore", ".geminiignore"):
                txt = (proj / ig).read_text(encoding="utf-8")
                self.assertIn("# CORTICAL:START", txt)
                self.assertIn(".cortical/", txt)

            # Idempotent second run does not duplicate .gitignore entry
            res2 = init_workspace(proj, update_gitignore=True, sync_ignores=True)
            self.assertFalse(res2["gitignore_updated"])
            self.assertEqual((proj / ".gitignore").read_text(encoding="utf-8").count(".cortical/"), 1)

            # Auto-discovery from nested subdir resolves <root>/.cortical/wiki.db and exports/
            old_env = os.environ.pop("CORTICAL_VAULT_DB", None)
            try:
                self.assertEqual(resolve_default_db(None, start_dir=nested), (proj / ".cortical" / "wiki.db").resolve())
                self.assertEqual(resolve_default_export_dir(None, start_dir=nested), (proj / ".cortical" / "exports").resolve())
            finally:
                if old_env is not None:
                    os.environ["CORTICAL_VAULT_DB"] = old_env

            cfg = read_workspace_config(proj / ".cortical")
            self.assertEqual(cfg["db_path"], ".cortical/wiki.db")


if __name__ == "__main__":
    unittest.main()
