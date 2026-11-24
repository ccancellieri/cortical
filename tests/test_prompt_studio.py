"""Comprehensive stdlib unit & integration tests for Cortical Prompt Studio (`cortical next` — ADR-017)."""

from __future__ import annotations

import http.client
import io
import json
import socket
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from cortical.analytics.dashboard import export_static_dashboard
from cortical.cli import main as cli_main
from cortical.composers.prompt_studio import (
    LoopMemoryStore,
    create_ephemeral_elicitor_server,
    evaluate_five_trigger_gate,
    generate_adaptive_questions,
    harvest_prompt_context,
    run_ephemeral_browser_elicitor,
    run_next_prompt_flow,
    synthesize_continuation_prompt,
)
from cortical.config import DEFAULT_CONFIG
from cortical.harnesses.adapters import ALL_HARNESSES, plan_sync, resolve_user_paths
from cortical.harnesses.hooks import install_harness_hooks
from cortical.mcp_server import CorticalMCPServer
from cortical.privacy.vault import PrivacyVault


class TestPromptStudioAndEphemeralElicitor(unittest.TestCase):
    def test_context_harvester_loop_memory_learning_and_privacy_firewall(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "docs" / "adr").mkdir(parents=True)
            (root / "docs" / "adr" / "ADR-017-prompt-studio.md").write_text(
                "# ADR-017: Cortical Prompt Studio\n", encoding="utf-8"
            )
            db_path = root / "vault.db"
            vault = PrivacyVault(db_path)
            vault.ingest("Public architecture uses PostgreSQL and TOON.", alias="arch_safe", policy="auto", profile="medium")
            vault.ingest(
                "CEO salary IBAN IT60X0542811101000000123456 secret sk-abcdef1234567890abcdef",
                alias="board_secret",
                policy="fail_closed",
                profile="max_security",
            )

            store = LoopMemoryStore(repo_root=root, data_dir=root / ".cortical_data")
            ctx1 = harvest_prompt_context(
                "Add TOON benchmark for alice@acme.example with key sk-1234567890abcdefghij",
                repo_root=root,
                vault_db=db_path,
                loop_store=store,
                target="hybrid",
                allow_gh=False,
            )
            self.assertTrue(ctx1["remote_egress"])
            self.assertTrue(ctx1["seed_raw_had_pii"])
            self.assertNotIn("alice@acme.example", ctx1["seed"])
            self.assertNotIn("sk-1234567890abcdefghij", ctx1["seed"])
            # max_security item MUST be blocked from remote context
            safe_uris = [a["uri"] for a in ctx1["safe_vault_aliases"]]
            self.assertIn("@private:arch_safe", safe_uris)
            self.assertNotIn("@private:board_secret", safe_uris)
            self.assertEqual(ctx1["blocked_local_only_count"], 1)
            self.assertNotIn("board_secret", ctx1["toon_packet"])

            qs1 = generate_adaptive_questions(ctx1)
            self.assertGreaterEqual(len(qs1), 2)
            prompt1 = synthesize_continuation_prompt(
                ctx1,
                qs1,
                answers={"execution_strategy": "minimal_patch"},
                comments={"execution_strategy": "Focus on deterministic unit tests for secret@corp.example"},
                directives="Always run tests via .venv\nAvoid adding third-party packages",
            )
            self.assertNotIn("secret@corp.example", prompt1)
            self.assertNotIn("IT60X0542811101000000123456", prompt1)

            rec1 = store.record_outcome(
                seed=ctx1["seed"],
                target="argon",
                answers={"execution_strategy": "minimal_patch"},
                comments={"execution_strategy": "Keep diffs small"},
                directives="Always run tests via .venv\nAvoid adding third-party packages",
                confidence_score=0.88,
                mode_used="browser_submitted",
                synthesized_prompt=prompt1,
                issue=60,
                last_commit="abc1234",
            )
            self.assertEqual(rec1["iteration_count"], 1)
            self.assertTrue(Path(rec1["prompt_path"]).is_file())

            # Second loop learns preferred_target, answered_preferences & rejected_approaches
            ctx2 = harvest_prompt_context(
                "Implement cortical next CLI parser flags",
                repo_root=root,
                vault_db=db_path,
                loop_store=store,
                allow_gh=False,
            )
            self.assertEqual(ctx2["loop_memory"]["preferred_target"], "argon")
            self.assertIn("Avoid adding third-party packages", ctx2["loop_memory"]["rejected_approaches"])
            qs2 = generate_adaptive_questions(ctx2)
            self.assertEqual(qs2[0]["default"], "minimal_patch")
            prompt2 = synthesize_continuation_prompt(ctx2, qs2)
            self.assertIn("Avoid adding third-party packages", prompt2)

    def test_ephemeral_loopback_security_dns_rebinding_token_and_socket_closure(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store = LoopMemoryStore(repo_root=root, data_dir=root / ".cortical_data")
            ctx = harvest_prompt_context("Refine cortical doctor diagnostics", repo_root=root, loop_store=store, allow_gh=False)
            gate = evaluate_five_trigger_gate(ctx)
            qs = generate_adaptive_questions(ctx)

            # 1. Direct protocol checks: DNS rebinding Host rejection (421), bad token (403), cross-origin POST (403)
            httpd, tok, _state, _done = create_ephemeral_elicitor_server(ctx, qs, gate, loop_store=store)
            port = httpd.server_address[1]
            t = threading.Thread(target=lambda: [httpd.handle_request() for _ in range(4)], daemon=True)
            t.start()
            try:
                # Evil Host header -> 421 Misdirected Request
                c1 = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
                c1.putrequest("GET", f"/elicit?token={tok}", skip_host=True)
                c1.putheader("Host", "evil.attacker.rebind:80")
                c1.endheaders()
                r1 = c1.getresponse()
                r1.read()
                self.assertEqual(r1.status, 421)
                c1.close()

                # Missing/wrong token -> 403 Forbidden
                c2 = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
                c2.request("GET", "/elicit?token=wrong-token", headers={"Host": f"127.0.0.1:{port}"})
                r2 = c2.getresponse()
                r2.read()
                self.assertEqual(r2.status, 403)
                c2.close()

                # Cross-origin POST -> 403 Forbidden
                c3 = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
                c3.request(
                    "POST",
                    f"/submit?token={tok}",
                    body=json.dumps({"token": tok}),
                    headers={"Host": f"127.0.0.1:{port}", "Origin": "https://evil.example", "Content-Type": "application/json"},
                )
                r3 = c3.getresponse()
                r3.read()
                self.assertEqual(r3.status, 403)
                c3.close()

                # Valid GET -> 200 HTML
                c4 = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
                c4.request("GET", f"/elicit?token={tok}", headers={"Host": f"127.0.0.1:{port}"})
                r4 = c4.getresponse()
                body_html = r4.read().decode("utf-8")
                self.assertEqual(r4.status, 200)
                self.assertIn("Cortical Prompt Studio", body_html)
                c4.close()
            finally:
                t.join(timeout=3)
                httpd.server_close()

            # 2. Full end-to-end submission lifecycle + template save + guaranteed immediate port closure
            ready_info: dict[str, object] = {}

            def _client_submit(url: str, bound_port: int, session_tok: str) -> None:
                ready_info["port"] = bound_port

                def _post() -> None:
                    conn = http.client.HTTPConnection("127.0.0.1", bound_port, timeout=3)
                    conn.request(
                        "POST",
                        f"/save-template?token={session_tok}",
                        body=json.dumps({"token": session_tok, "name": "Neon QA Loop", "target": "neon", "prompt": "# QA Template"}),
                        headers={"Host": f"127.0.0.1:{bound_port}", "Content-Type": "application/json"},
                    )
                    rt = conn.getresponse()
                    rt.read()
                    self.assertEqual(rt.status, 200)

                    conn.request(
                        "POST",
                        f"/submit?token={session_tok}",
                        body=json.dumps({
                            "token": session_tok,
                            "seed": "Verify cortical next browser flow",
                            "target": "neon",
                            "answers": {"execution_strategy": "targeted_tdd"},
                            "comments": {"execution_strategy": "Check keyboard shortcuts"},
                            "directives": "Zero external CDNs",
                        }),
                        headers={"Host": f"127.0.0.1:{bound_port}", "Content-Type": "application/json"},
                    )
                    rs = conn.getresponse()
                    rs.read()
                    self.assertEqual(rs.status, 200)
                    conn.close()

                threading.Thread(target=_post, daemon=True).start()

            res = run_ephemeral_browser_elicitor(
                ctx,
                qs,
                gate,
                loop_store=store,
                timeout_sec=5.0,
                open_browser=False,
                on_ready=_client_submit,
            )
            self.assertTrue(res["submitted"])
            self.assertTrue(res["port_closed"])
            self.assertEqual(len(store.load()["templates"]), 1)

            # Prove ephemeral port is IMMEDIATELY closed (zero lingering listener!)
            closed_port = int(ready_info["port"])  # type: ignore[arg-type]
            with self.assertRaises(OSError):
                with socket.create_connection(("127.0.0.1", closed_port), timeout=0.3):
                    pass

    def test_five_trigger_confidence_gate_auto_mode_mcp_cli_and_8_harness_sync(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data_dir = root / ".cortical_data"
            db_path = data_dir / "vault.db"

            # High-confidence well-scoped seed -> autonomous synthesis without escalation
            auto_ok = run_next_prompt_flow(
                "Add unit test for TOON compression roundtrip in cortical compression package",
                mode="auto_if_confident",
                target="pi",
                open_browser=False,
                allow_gh=False,
                repo_root=root,
                vault_db=db_path,
                data_dir=data_dir,
            )
            self.assertTrue(auto_ok["ok"])
            self.assertEqual(auto_ok["mode_used"], "auto_synthesized")
            self.assertFalse(auto_ok["escalated"])
            self.assertGreaterEqual(auto_ok["confidence_gate"]["confidence_score"], 0.72)

            # Destructive + ambiguous seed -> triggers irreversibility gate and escalates
            risky = run_next_prompt_flow(
                "rm -rf production maybe?",
                mode="auto",
                target="hybrid",
                open_browser=False,
                allow_gh=False,
                repo_root=root,
                vault_db=db_path,
                data_dir=data_dir,
            )
            self.assertTrue(risky["escalated"])
            self.assertIn("irreversibility", risky["confidence_gate"]["triggered_gates"])
            self.assertLess(risky["confidence_gate"]["confidence_score"], 0.50)

            # MCP Tool + Native MCP Prompt verification
            mcp = CorticalMCPServer(vault_db=db_path)
            t_call = mcp.handle_request({
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "cortical_next_prompt",
                    "arguments": {"seed": "Verify cortical doctor JSON output", "mode": "auto", "target": "argon"},
                },
            })
            self.assertFalse(t_call["result"]["isError"])
            self.assertIn("Argon", t_call["result"]["structuredContent"]["prompt"])

            p_list = mcp.handle_request({"jsonrpc": "2.0", "id": 2, "method": "prompts/list", "params": {}})
            prompt_names = [p["name"] for p in p_list["result"]["prompts"]]
            self.assertIn("cortical-next-prompt", prompt_names)
            p_get = mcp.handle_request({
                "jsonrpc": "2.0",
                "id": 3,
                "method": "prompts/get",
                "params": {"name": "cortical-next-prompt", "arguments": {"seed": "Check sync rollback", "target": "pi"}},
            })
            self.assertIn("Check sync rollback", p_get["result"]["messages"][0]["content"]["text"])

            # CLI `cortical next --resume` & `cortical prompt` alias
            out_md = root / "next_prompt.md"
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc1 = cli_main(["next", "--resume", "--mode", "auto", "--no-open", "--repo-root", str(root), "--db", str(db_path), "--out", str(out_md), "--json"])
                rc2 = cli_main(["prompt", "Check vault audit", "--mode", "auto", "--no-open", "--repo-root", str(root), "--db", str(db_path), "--json"])
            self.assertEqual(rc1, 0)
            self.assertEqual(rc2, 0)
            self.assertTrue(out_md.is_file())

            # 8-Harness sync + OpenCode /next command + SPA Prompt Studio tab
            paths = resolve_user_paths("macos", home=root / "home")
            hw = {"os": "macos", "total_ram_gb": 16.0, "free_ram_gb": 10.0, "vram_gb": 11.2, "unified_memory": True, "binaries": {}}
            changes = plan_sync(DEFAULT_CONFIG, hw, {"recommended_by_role": {}}, repo_root=root, vault_db_path=db_path, user_paths=paths)
            self.assertEqual({c.harness for c in changes}, set(ALL_HARNESSES))
            agy_rules = next(c for c in changes if c.harness == "antigravity" and c.kind == "markdown")
            self.assertIn("/next", agy_rules.content)
            self.assertIn("cortical_next_prompt", agy_rules.content)

            hk_res = install_harness_hooks(["opencode"], home=root / "home", os_name="macos", dry_run=True)
            self.assertTrue(any(f["path"].endswith("commands/next.md") for f in hk_res["files"]))

            s_path, _ = export_static_dashboard(root / "spa_out", config=DEFAULT_CONFIG, public_docs=True)
            spa_html = s_path.read_text(encoding="utf-8")
            self.assertIn("Prompt Studio", spa_html)
            self.assertIn("renderPromptStudio", spa_html)


if __name__ == "__main__":
    unittest.main()
