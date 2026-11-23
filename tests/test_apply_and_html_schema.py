"""Stdlib tests for `cortical apply` atomic bundles, rollback safety, and static HTML/JSON schema validation."""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from cortical.analytics.dashboard import export_static_dashboard
from cortical.apply import PLAN_SCHEMA, PlanError, apply_plan, validate_plan
from cortical.config import DEFAULT_CONFIG
from cortical.harnesses.adapters import FileChange, rollback_sync
from cortical.privacy.vault import PrivacyVault


def _extract_embedded_snapshot(html: str) -> dict:
    m = re.search(r"window\.__CORTICAL_SNAPSHOT__\s*=\s*(\{.*?\});\s*\n", html, re.S)
    assert m is not None, "window.__CORTICAL_SNAPSHOT__ not found in HTML"
    raw = m.group(1).replace("<\\/", "</")
    return json.loads(raw)


class TestCorticalApplyAndHtmlSchema(unittest.TestCase):
    def test_01_apply_plan_validation_dry_run_apply_and_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tpath = Path(tmp)
            cfg_path = tpath / "cortical.config.json"
            cfg_path.write_text(json.dumps(DEFAULT_CONFIG, indent=2) + "\n", encoding="utf-8")
            backup_root = tpath / "backups"
            harness_file = tpath / "pi_mcp.json"
            harness_file.write_text('{"existing": true}\n', encoding="utf-8")

            def _fake_plan_changes(_cfg, harnesses):
                return [
                    FileChange(
                        harness=harnesses[0],
                        path=harness_file,
                        content='{"existing": true, "cortical": true}\n',
                        kind="json",
                        action="update",
                        detail="mock harness sync",
                    )
                ]

            plan = {
                "schema": PLAN_SCHEMA,
                "config_patch": {
                    "routing": {"mode": "full_local", "cloud_token_threshold": 40000},
                    "compression": {"max_context_share": 0.12},
                },
                "custom_models": [
                    {
                        "model_id": "qwen3.8:27b-iq2_xxs",
                        "memory_gb": 7.2,
                        "native_ctx": 32768,
                        "quantization": "Unsloth Dynamic UD-IQ2_XXS",
                        "is_variable_quant": True,
                    }
                ],
                "sync_harnesses": ["pi"],
            }

            # Dry-run writes nothing
            dry = apply_plan(plan, dry_run=True, config_path=cfg_path, backup_root=backup_root, plan_changes_fn=_fake_plan_changes)
            self.assertTrue(dry["dry_run"])
            self.assertIsNone(dry["backup_id"])
            self.assertEqual(dry["changed_count"], 2)
            self.assertNotIn("cortical", harness_file.read_text(encoding="utf-8"))

            # Real apply writes config + harness + single rollback snapshot + regenerates dashboard
            dash_out = tpath / "html_out"
            res = apply_plan(
                plan,
                dry_run=False,
                config_path=cfg_path,
                backup_root=backup_root,
                plan_changes_fn=_fake_plan_changes,
                regenerate_dashboard=str(dash_out),
            )
            self.assertFalse(res["dry_run"])
            self.assertIsNotNone(res["backup_id"])
            self.assertTrue((dash_out / "settings.html").is_file())
            updated_cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            self.assertEqual(updated_cfg["routing"]["mode"], "full_local")
            self.assertEqual(updated_cfg["compression"]["max_context_share"], 0.12)
            self.assertIn("cortical", harness_file.read_text(encoding="utf-8"))

            # Exact rollback via cortical sync --rollback <id>
            rb = rollback_sync(res["backup_id"], backup_root=backup_root)
            self.assertEqual(rb["restored"], 2)
            restored_cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            self.assertEqual(restored_cfg["routing"]["mode"], "auto")
            self.assertEqual(harness_file.read_text(encoding="utf-8"), '{"existing": true}\n')

    def test_02_apply_plan_enforces_fail_closed_on_max_security_vault(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tpath = Path(tmp)
            vdb = tpath / "vault.db"
            vault = PrivacyVault(vdb)
            vault.ingest("IBAN IT60X0542811101000000123456", alias="bank_secret", policy="fail_closed", profile="max_security")

            bad_plan = {
                "schema": PLAN_SCHEMA,
                "config_patch": {},
                "vault_updates": [{"alias": "bank_secret", "profile": "medium", "policy": "fail_open"}],
            }
            with self.assertRaises(PlanError) as ctx:
                apply_plan(bad_plan, config_path=tpath / "cfg.json", vault_db=vdb)
            self.assertIn("LOCAL-ONLY", str(ctx.exception))

            # Unknown config keys rejected
            errs = validate_plan({"schema": PLAN_SCHEMA, "config_patch": {"unknown_key": 123}})
            self.assertTrue(any("unknown top-level keys" in e for e in errs))

    def test_03_generated_html_schema_offline_self_containment_and_accessibility(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tpath = Path(tmp)
            for public_mode in (True, False):
                out_dir = tpath / ("pub" if public_mode else "loc")
                s_path, h_path = export_static_dashboard(out_dir, config=DEFAULT_CONFIG, public_docs=public_mode)
                self.assertTrue(s_path.is_file())
                self.assertTrue(h_path.is_file())
                html = s_path.read_text(encoding="utf-8")

                # Zero external CDN stylesheets or scripts (strict offline self-containment)
                self.assertIsNone(re.search(r'<script[^>]+src=["\']https?://', html, re.I))
                self.assertIsNone(re.search(r'<link[^>]+href=["\']https?://', html, re.I))

                # Required landmarks, keyboard/HCI features, and zero-server apply bridge
                for marker in (
                    'role="banner"',
                    'aria-label="Primary Navigation"',
                    'id="dirty-dock"',
                    'downloadPlan()',
                    'copyPlanForClipboardApply()',
                    'VERIFY_REFRESH_CMD',
                    'repairSteps(',
                    'restoreFocus()',
                ):
                    self.assertIn(marker, html)

                # Validate embedded JSON snapshot schema
                snap = _extract_embedded_snapshot(html)
                for key in ("meta", "config", "hardware", "models", "harnesses", "composers", "vault", "roi", "bench", "adrs"):
                    self.assertIn(key, snap)
                self.assertEqual(len(snap["harnesses"]), 8)
                self.assertEqual(snap["meta"]["mode"], "demo" if public_mode else "hydrated")
                if public_mode:
                    self.assertNotIn("/Users/", json.dumps(snap))


if __name__ == "__main__":
    unittest.main()
