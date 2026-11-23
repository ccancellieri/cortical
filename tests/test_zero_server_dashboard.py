"""Zero-server static dashboard hydration, public-docs PII stripping, and docs/settings.html tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cortical.analytics.dashboard import export_static_dashboard
from cortical.analytics.snapshot import build_dashboard_snapshot, scan_repo_adrs
from cortical.config import DEFAULT_CONFIG


class TestZeroServerDashboard(unittest.TestCase):
    def test_snapshot_hydration_public_vs_local_and_adrs(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        adrs = scan_repo_adrs(repo_root)
        self.assertGreaterEqual(len(adrs), 7)
        ids = {a["id"] for a in adrs}
        self.assertTrue({"ADR-001", "ADR-002", "ADR-003", "ADR-004", "ADR-005", "ADR-006", "ADR-007"}.issubset(ids))

        pub = build_dashboard_snapshot(config=DEFAULT_CONFIG, repo_root=repo_root, public_docs=True)
        self.assertEqual(pub["meta"]["mode"], "demo")
        self.assertEqual(len(pub["harnesses"]), 8)
        self.assertTrue(all(h["planned_changes"] == [] for h in pub["harnesses"]))
        self.assertEqual(pub["vault"]["max_context_share_pct"], 15.0)
        self.assertNotIn("/Users/", pub["meta"]["repo_display"])
        self.assertGreaterEqual(len(pub["adrs"]), 7)

        loc = build_dashboard_snapshot(config=DEFAULT_CONFIG, repo_root=repo_root, public_docs=False)
        self.assertTrue(any(len(h["planned_changes"]) > 0 for h in loc["harnesses"]))

        with tempfile.TemporaryDirectory() as tmp:
            s_path, h_path = export_static_dashboard(Path(tmp), config=DEFAULT_CONFIG, public_docs=True)
            html = s_path.read_text(encoding="utf-8")
            self.assertTrue(h_path.is_file())
            self.assertIn("window.__CORTICAL_SNAPSHOT__", html)
            self.assertIn("Overview &amp; Quick Setup", html)
            self.assertIn("Services &amp; Harnesses", html)
            self.assertIn("Models &amp; Hardware Tuner", html)
            self.assertIn("Memory &amp; Privacy Vault", html)
            self.assertIn("Settings &amp; Config Composer", html)
            self.assertIn("Usage, ROI &amp; Reports", html)
            self.assertIn("Probe Local Services", html)
            self.assertIn("Command Palette", html)
            self.assertIn("webkitdirectory", html)
            self.assertIn("Task Tags", html)
            self.assertIn("ADR-007", html)
            self.assertIn("routing.enforce_cloud_budget", html)
            self.assertIn("routing.prefer_local_offload", html)

    def test_optional_cloud_budget_enforcement_and_default_high_budget(self) -> None:
        import json
        from cortical.analytics.roi import evaluate_routing_state

        with tempfile.TemporaryDirectory() as tmp:
            bdir = Path(tmp) / "brain"
            log = bdir / "chat1" / ".system_generated" / "logs" / "transcript.jsonl"
            log.parent.mkdir(parents=True)
            log.write_text(
                json.dumps({"type": "USER_INPUT"}) + "\n"
                + json.dumps({"type": "PLANNER_RESPONSE", "input_tokens": 990000, "output_tokens": 5000, "tool_calls": []}) + "\n",
                encoding="utf-8",
            )
            # Disabled by default in DEFAULT_CONFIG -> mixed, handoff_recommended False
            rs_off = evaluate_routing_state(config=DEFAULT_CONFIG, db_path=Path(tmp) / "empty.db", brain_dir=bdir)
            self.assertFalse(rs_off["enforce_cloud_budget"])
            self.assertFalse(rs_off["handoff_recommended"])
            self.assertEqual(rs_off["effective_mode"], "mixed")
            self.assertEqual(rs_off["cloud_budget_tokens"], 1000000)

            # Explicitly enabled -> full_local, handoff_recommended True
            cfg_on = json.loads(json.dumps(DEFAULT_CONFIG))
            cfg_on["routing"]["enforce_cloud_budget"] = True
            rs_on = evaluate_routing_state(config=cfg_on, db_path=Path(tmp) / "empty.db", brain_dir=bdir)
            self.assertTrue(rs_on["enforce_cloud_budget"])
            self.assertTrue(rs_on["handoff_recommended"])
            self.assertEqual(rs_on["effective_mode"], "full_local")

    def test_roi_top_level_transcript_tokens_and_most_recent_chat(self) -> None:
        import json
        import os
        from cortical.analytics.roi import build_roi_report

        with tempfile.TemporaryDirectory() as tmp:
            bdir = Path(tmp) / "brain"
            old_log = bdir / "0000_old" / ".system_generated" / "logs" / "transcript.jsonl"
            new_log = bdir / "zzzz_active" / ".system_generated" / "logs" / "transcript.jsonl"
            old_log.parent.mkdir(parents=True)
            new_log.parent.mkdir(parents=True)
            old_log.write_text(
                json.dumps({"type": "USER_INPUT"}) + "\n"
                + json.dumps({"type": "PLANNER_RESPONSE", "input_tokens": 100, "output_tokens": 20, "tool_calls": []}) + "\n",
                encoding="utf-8",
            )
            new_log.write_text(
                json.dumps({"type": "USER_INPUT"}) + "\n"
                + json.dumps({"type": "PLANNER_RESPONSE", "input_tokens": 12000, "cache_read_tokens": 4000, "output_tokens": 850, "tool_calls": [{"name": "a"}]}) + "\n",
                encoding="utf-8",
            )
            os.utime(old_log, (1700000000, 1700000000))
            os.utime(new_log, (1800000000, 1800000000))

            rep = build_roi_report(db_path=Path(tmp) / "empty.db", brain_dir=bdir)
            self.assertEqual(rep["remote"]["chats"][0]["conversation_id"], "zzzz_active")
            rem_turn = rep["current_turn"]["remote"]
            self.assertEqual(rem_turn["input_tokens"], 12000)
            self.assertEqual(rem_turn["cache_read_tokens"], 4000)
            self.assertEqual(rem_turn["output_tokens"], 850)
            self.assertEqual(rem_turn["active_tokens"], 12850)


if __name__ == "__main__":
    unittest.main()
