"""Unit & integration tests for Hybrid Local-First + Remote-Capable Orchestration (ADRs 013-015)."""

from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from cortical.analytics.snapshot import build_dashboard_snapshot  # noqa: E402
from cortical.apply import PLAN_SCHEMA, validate_plan  # noqa: E402
from cortical.composers.router import render_litellm_config_yaml  # noqa: E402
from cortical.config import DEFAULT_CONFIG, remote_orchestrator_active, resolve_orchestrator_spec  # noqa: E402
from cortical.hardware.context_window import (  # noqa: E402
    compute_adaptive_timeout,
    compute_dynamic_num_ctx,
    compute_hardware_context_profile,
)
from cortical.harnesses.adapters import ALL_HARNESSES, plan_sync, resolve_user_paths  # noqa: E402
from cortical.mcp_server import CorticalMCPServer  # noqa: E402
from cortical.privacy.vault import FailClosedError, PrivacyVault  # noqa: E402


class TestHardwareAutoCtxAndTimeouts(unittest.TestCase):
    def test_apple_silicon_16gb_unified_expands_deep_and_fast_ctx(self) -> None:
        hw_16g = {
            "total_ram_gb": 16.0,
            "free_ram_gb": 0.99,  # reproduces macOS vm_stat file-cache pressure trap
            "unified_memory": True,
            "vram_gb": 10.67,
            "memory_pressure_level": 1,
        }
        deep_ctx = compute_dynamic_num_ctx(
            131072,
            "qwen3.8:27b-iq2_xxs",
            ram_available_gb=hw_16g["free_ram_gb"],
            vram_gb=hw_16g["vram_gb"],
            unified_memory=True,
            model_ram_gb=7.2,
            total_ram_gb=16.0,
            memory_pressure_level=1,
        )
        fast_ctx = compute_dynamic_num_ctx(
            131072,
            "qwen3.5:9b-q3_k_xl",
            ram_available_gb=hw_16g["free_ram_gb"],
            vram_gb=hw_16g["vram_gb"],
            unified_memory=True,
            model_ram_gb=5.1,
            total_ram_gb=16.0,
            memory_pressure_level=1,
        )
        self.assertGreaterEqual(deep_ctx, 65536)
        self.assertEqual(deep_ctx, 65536)
        self.assertGreaterEqual(fast_ctx, 98304)

        prof = compute_hardware_context_profile("qwen3.8:27b-iq2_xxs", hw_16g)
        self.assertEqual(prof["auto_max_num_ctx"], 65536)
        self.assertEqual(prof["adaptive_timeout_sec"], 600)
        self.assertEqual(compute_adaptive_timeout("cortical-deep", num_ctx=65536, is_remote=False), 600)

    def test_multi_tier_hardware_and_fixed_vs_auto_strategy(self) -> None:
        tier_1a = {"total_ram_gb": 32.0, "free_ram_gb": 18.0, "unified_memory": False, "vram_gb": 8.0, "memory_pressure_level": 1}
        tier_3 = {"total_ram_gb": 64.0, "free_ram_gb": 42.0, "unified_memory": True, "vram_gb": 48.0, "memory_pressure_level": 1}

        c_1a = compute_hardware_context_profile("qwen3.5:9b-q3_k_xl", tier_1a)
        c_3 = compute_hardware_context_profile("qwen3.8:27b-iq2_xxs", tier_3)
        self.assertGreaterEqual(c_1a["auto_max_num_ctx"], 32768)
        self.assertEqual(c_3["auto_max_num_ctx"], 131072)

        cfg_fixed = copy.deepcopy(DEFAULT_CONFIG)
        cfg_fixed["orchestrator"]["context_strategy"] = "fixed"
        cfg_fixed["orchestrator"]["fixed_num_ctx"] = 32768
        spec = resolve_orchestrator_spec(cfg_fixed, hw=tier_3)
        self.assertEqual(spec["context_strategy"], "fixed")
        self.assertEqual(spec["effective_num_ctx"], 32768)
        self.assertEqual(spec["auto_max_num_ctx"], 131072)


class TestPiAndLiteLLMRouterFix(unittest.TestCase):
    def test_pi_models_and_litellm_yaml_emit_expanded_ctx_and_think_none(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            paths = resolve_user_paths(os_name="macos", home=home)
            cfg = copy.deepcopy(DEFAULT_CONFIG)
            cfg["router"]["enabled"] = True
            hw = {
                "os": "macos",
                "total_ram_gb": 16.0,
                "free_ram_gb": 1.2,
                "unified_memory": True,
                "vram_gb": 10.67,
                "memory_pressure_level": 1,
                "binaries": {"serena": "serena"},
            }
            rec = {
                "recommended_by_role": {
                    "daily_coder": {"model_id": "qwen3.5:9b-q3_k_xl"},
                    "deep_reasoner": {"model_id": "qwen3.8:27b-iq2_xxs"},
                    "router": {"model_id": "qwen2.5:1.5b"},
                }
            }
            changes = plan_sync(cfg, hw, rec, harnesses=["pi"], repo_root=ROOT, user_paths=paths)
            by_path = {ch.path.name: ch.content for ch in changes}
            models_doc = json.loads(by_path["models.json"])
            router_models = {m["id"]: m for m in models_doc["providers"]["router"]["models"]}

            for mid in ("cortical-deep", "qwen3.8:27b-iq2_xxs"):
                self.assertIn(mid, router_models)
                self.assertEqual(router_models[mid]["contextWindow"], 65536)
                self.assertEqual(router_models[mid]["samplingParams"]["reasoning_effort"], "none")
            self.assertEqual(router_models["cortical-fast"]["contextWindow"], 98304)

            settings_doc = json.loads(by_path["settings.json"])
            self.assertEqual(settings_doc["defaultProvider"], "router")
            self.assertEqual(settings_doc["defaultModel"], "cortical-deep")

            yaml_out = render_litellm_config_yaml(cfg, hw=hw)
            self.assertIn("model_name: cortical-deep", yaml_out)
            self.assertIn("num_ctx: 65536", yaml_out)
            self.assertIn("keep_alive: 30m", yaml_out)
            self.assertIn("reasoning_effort: none", yaml_out)
            self.assertIn("timeout: 600", yaml_out)
            self.assertIn("request_timeout: 600", yaml_out)


class TestMultiProviderHybrid8Harnesses(unittest.TestCase):
    def test_remote_providers_sync_all_8_harnesses_without_secret_leak_and_preserve_creds(self) -> None:
        providers = [
            ("gemini", "gemini-2.5-pro", "GEMINI_API_KEY"),
            ("anthropic", "claude-sonnet-4-5", "ANTHROPIC_API_KEY"),
            ("openai", "gpt-5", "OPENAI_API_KEY"),
            ("deepseek", "deepseek-chat", "DEEPSEEK_API_KEY"),
            ("openrouter", "google/gemini-2.5-flash", "OPENROUTER_API_KEY"),
        ]
        hw = {
            "os": "macos",
            "total_ram_gb": 16.0,
            "free_ram_gb": 10.0,
            "unified_memory": True,
            "vram_gb": 11.2,
            "memory_pressure_level": 1,
            "binaries": {"serena": "serena"},
        }
        rec = {
            "recommended_by_role": {
                "daily_coder": {"model_id": "qwen3.5:9b-q3_k_xl"},
                "deep_reasoner": {"model_id": "qwen3.8:27b-iq2_xxs"},
                "router": {"model_id": "qwen2.5:1.5b"},
            }
        }
        for prov, model_id, env_name in providers:
            with self.subTest(provider=prov), tempfile.TemporaryDirectory() as td:
                home = Path(td)
                paths = resolve_user_paths(os_name="macos", home=home)
                # Pre-existing user credentials/auth must be preserved cleanly
                paths["pi"]["models"].parent.mkdir(parents=True, exist_ok=True)
                paths["pi"]["models"].write_text(
                    json.dumps({"providers": {"existing_custom": {"baseUrl": "https://user.example/v1", "apiKey": "USER_CRED_PRESERVED"}}}),
                    encoding="utf-8",
                )
                paths["codex"]["config"].parent.mkdir(parents=True, exist_ok=True)
                paths["codex"]["config"].write_text('# existing user auth\nmodel = "user-kept"\n', encoding="utf-8")

                cfg = copy.deepcopy(DEFAULT_CONFIG)
                cfg["router"]["enabled"] = True
                cfg["orchestrator"] = {
                    "mode": "remote",
                    "provider": prov,
                    "model": model_id,
                    "api_key_env": env_name,
                    "endpoint": "",
                    "context_strategy": "auto_max",
                    "fixed_num_ctx": 65536,
                    "timeout_sec": 0,
                    "local_first_delegation": True,
                    "strict_remote_privacy": True,
                }
                self.assertTrue(remote_orchestrator_active(cfg))
                changes = plan_sync(cfg, hw, rec, harnesses=list(ALL_HARNESSES), repo_root=ROOT, user_paths=paths)
                touched_harnesses = {ch.harness for ch in changes}
                self.assertEqual(touched_harnesses, set(ALL_HARNESSES))

                joined = "\n".join(ch.content for ch in changes)
                self.assertIn(env_name, joined)
                self.assertIn("Zero-Leakage Remote Guard", joined)
                self.assertIn("cortical_local_offload", joined)
                self.assertNotIn("sk-", joined)

                pi_models = next(json.loads(c.content) for c in changes if c.harness == "pi" and c.path.name == "models.json")
                self.assertEqual(pi_models["providers"]["existing_custom"]["apiKey"], "USER_CRED_PRESERVED")
                self.assertIn(prov, pi_models["providers"])

                codex_toml = next(c.content for c in changes if c.harness == "codex" and c.path.name == "config.toml")
                self.assertIn('model = "user-kept"', codex_toml)
                self.assertIn(f'env_key = "{env_name}"', codex_toml)

                yaml_out = render_litellm_config_yaml(cfg, hw=hw)
                self.assertIn(f"os.environ/{env_name}", yaml_out)
                self.assertIn('{"cortical-orchestrator": ["cortical-deep", "cortical-fast"]}', yaml_out)

    def test_validate_plan_rejects_raw_api_secrets_in_api_key_env(self) -> None:
        for bad in ("sk-proj-1234567890abcdef", "AIzaSyD1234567890", "ghp_secret123456"):
            plan = {
                "schema": PLAN_SCHEMA,
                "config_patch": {"orchestrator": {"mode": "remote", "provider": "openai", "api_key_env": bad}},
            }
            errs = validate_plan(plan)
            self.assertTrue(any("api_key_env" in e for e in errs), f"Expected rejection for {bad!r}, got {errs}")


class TestZeroLeakageRemoteEgressChannels(unittest.TestCase):
    def test_channels_1_to_3_block_private_data_when_remote_orchestrator_active(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db_path = root / "vault.db"
            cfg_path = root / "cortical.config.json"
            vault = PrivacyVault(db_path)

            vault.ingest("SSN IT60X0542811101000000123456 private tax notes", alias="tax_doc", policy="fail_closed", profile="max_security")
            vault.ingest("Meeting note mentioning OrionSecretCodename with alice@acme.example", alias="team_note", policy="auto", profile="medium")

            # Channel 1 direct vault check under remote_egress=True + residual custom term
            with self.assertRaises(FailClosedError):
                vault.read_resource("tax_doc", allow_local_only=False, remote_egress=True)
            with self.assertRaises(FailClosedError):
                vault.read_resource("team_note", allow_local_only=False, remote_egress=True, custom_terms=["OrionSecretCodename"])

            # Channel 2 sanitized markdown export omits items with residual PII
            md = vault.export_sanitized_memory_markdown(num_ctx=65536, remote_egress=True, custom_terms=["OrionSecretCodename"])
            self.assertNotIn("OrionSecretCodename", md)

            # MCP Channel 1 + allow_local_only local offload path under remote config
            remote_cfg = copy.deepcopy(DEFAULT_CONFIG)
            remote_cfg["orchestrator"]["mode"] = "remote"
            remote_cfg["orchestrator"]["provider"] = "gemini"
            remote_cfg["orchestrator"]["api_key_env"] = "GEMINI_API_KEY"
            remote_cfg["privacy"]["custom_terms"] = ["OrionSecretCodename"]
            cfg_path.write_text(json.dumps(remote_cfg), encoding="utf-8")

            with mock.patch.dict(os.environ, {"CORTICAL_CONFIG_PATH": str(cfg_path)}):
                mcp = CorticalMCPServer(vault_db=db_path)
                listed = mcp.handle_request({"jsonrpc": "2.0", "id": 1, "method": "resources/list", "params": {}})
                uris = [r["uri"] for r in listed["result"]["resources"]]
                self.assertNotIn("cortical://private/tax_doc", uris)
                self.assertNotIn("cortical://private/team_note", uris)

                blocked_call = mcp.handle_request({
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": "cortical_vault_read", "arguments": {"alias": "team_note"}},
                })
                self.assertIn("error", blocked_call)

                with mock.patch("cortical.mcp_server.invoke_configured_runner", return_value="LOCAL_OFFLOAD_OK") as mocked_runner:
                    local_res = mcp.handle_request({
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "tools/call",
                        "params": {
                            "name": "cortical_local_offload",
                            "arguments": {"vault_alias": "tax_doc", "prompt": "Summarize tax doc offline"},
                        },
                    })
                    self.assertNotIn("error", local_res)
                    self.assertTrue(mocked_runner.called)

            # Channel 3 pre-send intercept masks prompt PII & sanitizes regular attachments, while blocking max_security items
            att = root / "contract.txt"
            att.write_text("Contract for alice@acme.example ref OrionSecretCodename", encoding="utf-8")
            inter = vault.intercept_pre_send(
                "pi",
                "Please review mail bob@acme.example for OrionSecretCodename",
                [att],
                config=remote_cfg,
            )
            self.assertTrue(inter["remote_egress_guarded"])
            self.assertTrue(inter["prompt_pii_masked"])
            self.assertTrue(inter["blocked_raw_upload"])
            self.assertNotIn("bob@acme.example", inter["proposed_remote_prompt"])
            self.assertNotIn("alice@acme.example", inter["proposed_remote_prompt"])
            self.assertNotIn("OrionSecretCodename", inter["proposed_remote_prompt"])

            max_att = root / "secret_tax.txt"
            max_att.write_text("Top secret salary ledger IT60X0542811101000000123456", encoding="utf-8")
            inter_max = vault.intercept_pre_send(
                "pi",
                "Check attached ledger",
                [max_att],
                profile="max_security",
                config=remote_cfg,
            )
            self.assertTrue(inter_max["requires_approval"])
            self.assertIn("LOCAL-ONLY VAULT", inter_max["proposed_remote_prompt"])
            self.assertIn("cortical_local_offload", inter_max["proposed_remote_prompt"])


class TestDashboardSnapshotOrchestration(unittest.TestCase):
    def test_snapshot_exposes_orchestration_matrix_without_secrets(self) -> None:
        snap = build_dashboard_snapshot(public_docs=True)
        self.assertIn("orchestration", snap)
        orch = snap["orchestration"]
        self.assertEqual(len(orch["harness_matrix"]), len(ALL_HARNESSES))
        self.assertEqual(orch["context_profile"]["auto_max_num_ctx"], 65536)
        self.assertIn("gemini", orch["presets"])
        serialized = json.dumps(snap)
        self.assertNotIn("sk-", serialized)


if __name__ == "__main__":
    unittest.main()
