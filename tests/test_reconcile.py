"""Stdlib unit tests for Cortical Control Plane SSOT Drift Detection & Reconciliation (`src/cortical/reconcile.py`)."""

from __future__ import annotations

import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from cortical.cli import main as cli_main
from cortical.config import DEFAULT_CONFIG
from cortical.harnesses.adapters import resolve_user_paths
from cortical.reconcile import detect_all_drift, detect_router_drift, reconcile_all, resolve_validated_models


class TestControlPlaneReconcile(unittest.TestCase):
    def test_01_resolve_validated_models_detects_stale_tags_and_noops_when_empty(self) -> None:
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["models_by_role"]["deep_reasoner"] = "qwen3.8:27b-q4_xxs"
        cfg["privacy"]["vision_model"] = "qwen2.5vl:7b"

        # Empty installed_models must be a safe no-op
        noop = resolve_validated_models(cfg, [])
        self.assertFalse(noop["checked"])
        self.assertEqual(noop["drifted"], [])
        self.assertEqual(noop["resolved_by_role"]["deep_reasoner"], "qwen3.8:27b-q4_xxs")

        # Installed models contain qwen3.8:27b-iq2_xxs and minicpm-ocr:latest instead
        installed = ["qwen3.5:9b-q3_k_xl", "qwen3.8:27b-iq2_xxs", "qwen2.5:1.5b", "minicpm-ocr:latest"]
        res = resolve_validated_models(cfg, installed)
        self.assertTrue(res["checked"])
        by_role_drift = {d["role"]: d for d in res["drifted"]}
        self.assertIn("deep_reasoner", by_role_drift)
        self.assertEqual(by_role_drift["deep_reasoner"]["replacement"], "qwen3.8:27b-iq2_xxs")
        self.assertIn("privacy.vision_model", by_role_drift)
        self.assertEqual(by_role_drift["privacy.vision_model"]["replacement"], "minicpm-ocr:latest")
        # Dict-shaped Ollama tag items (matching live probe_hardware output)
        dict_res = resolve_validated_models(cfg, [{"name": m} for m in installed])
        self.assertEqual(len(dict_res["drifted"]), len(res["drifted"]))

    def test_02_detect_router_drift_sha256_and_missing_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            yaml_p = Path(tmp) / "litellm_config.yaml"
            yaml_p.write_text("model_list: []\n", encoding="utf-8")

            res = detect_router_drift(
                DEFAULT_CONFIG,
                router_config_path=yaml_p,
                served_models=["qwen3.5:9b-q3_k_xl", "local-default"],
            )
            self.assertTrue(res["config_drift"])
            self.assertTrue(res["runtime_drift"])
            self.assertEqual(sorted(res["missing_aliases"]), ["cortical-deep", "cortical-fast", "cortical-vision"])
            self.assertNotEqual(res["disk_sha256"], res["expected_sha256"])

    def test_03_reconcile_all_dry_run_vs_apply_and_converges_to_in_sync(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tpath = Path(tmp)
            cfg_p = tpath / "cortical.config.json"
            yaml_p = tpath / "litellm_config.yaml"
            backup_root = tpath / "backups"
            home_dir = tpath / "home"
            home_dir.mkdir()
            user_paths = resolve_user_paths(
                os_name="macos",
                home=home_dir,
                appdata=home_dir / "AppData",
                xdg_config=home_dir / ".config",
            )

            stale_cfg = copy.deepcopy(DEFAULT_CONFIG)
            stale_cfg["models_by_role"]["deep_reasoner"] = "qwen3.8:27b-q4_xxs"
            cfg_p.write_text(json.dumps(stale_cfg, indent=2) + "\n", encoding="utf-8")
            yaml_p.write_text("stale: true\n", encoding="utf-8")

            fake_hw = {
                "os": "macos",
                "total_ram_gb": 16.0,
                "free_ram_gb": 10.5,
                "unified_memory": True,
                "vram_gb": 11.2,
                "installed_ollama_models": ["qwen3.5:9b-q3_k_xl", "qwen3.8:27b-iq2_xxs", "qwen2.5:1.5b"],
                "binaries": {},
            }

            dry = reconcile_all(
                config=stale_cfg,
                dry_run=True,
                config_path=cfg_p,
                router_config_path=yaml_p,
                hw=fake_hw,
                served_models=["local-default", "cortical-fast", "cortical-deep", "cortical-vision"],
                user_paths=user_paths,
                backup_root=backup_root,
                repo_root=tpath,
            )
            self.assertTrue(dry["dry_run"])
            self.assertFalse(dry["in_sync"])
            self.assertEqual(yaml_p.read_text(encoding="utf-8"), "stale: true\n")

            applied = reconcile_all(
                config=stale_cfg,
                dry_run=False,
                config_path=cfg_p,
                router_config_path=yaml_p,
                hw=fake_hw,
                served_models=["local-default", "cortical-fast", "cortical-deep", "cortical-vision"],
                user_paths=user_paths,
                backup_root=backup_root,
                repo_root=tpath,
            )
            self.assertTrue(applied["applied"])
            self.assertIsNotNone(applied["backup_id"])

            new_cfg = json.loads(cfg_p.read_text(encoding="utf-8"))
            self.assertEqual(new_cfg["models_by_role"]["deep_reasoner"], "qwen3.8:27b-iq2_xxs")

            after = detect_all_drift(
                config=new_cfg,
                hw=fake_hw,
                served_models=["local-default", "cortical-fast", "cortical-deep", "cortical-vision"],
                router_config_path=yaml_p,
                user_paths=user_paths,
                repo_root=tpath,
            )
            self.assertTrue(after["in_sync"])
            self.assertEqual(after["drift_count"], 0)

    def test_04_cli_reconcile_dry_run_smoke(self) -> None:
        buf = io.StringIO()
        fake_hw = {
            "os": "macos",
            "total_ram_gb": 16.0,
            "free_ram_gb": 10.0,
            "unified_memory": True,
            "vram_gb": 11.2,
            "installed_ollama_models": ["qwen3.5:9b-q3_k_xl", "qwen3.8:27b-iq2_xxs", "qwen2.5:1.5b"],
            "binaries": {},
        }
        with patch("cortical.reconcile.probe_hardware", return_value=fake_hw):
            with redirect_stdout(buf):
                rc = cli_main(["reconcile", "--dry-run", "--json"])
        self.assertEqual(rc, 0)
        parsed = json.loads(buf.getvalue())
        self.assertIn("in_sync", parsed)
        self.assertTrue(parsed["dry_run"])


if __name__ == "__main__":
    unittest.main()
