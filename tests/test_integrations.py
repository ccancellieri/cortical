"""Stdlib-only unit tests for `cortical.integrations` (`cortical integrate` & `cortical doctor` diagnostics)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from cortical.integrations import (
    detect_integrations,
    integrate_target,
    ping_mcp_stdio,
    run_doctor_diagnostics,
)
from cortical.workspace import init_workspace


class TestCorticalIntegrations(unittest.TestCase):
    def test_auto_detection_project_and_global(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "repo"
            home = Path(tmp) / "home"
            (proj / ".cursor").mkdir(parents=True)
            (proj / ".cursor" / "mcp.json").write_text("{}", encoding="utf-8")
            (proj / "opencode.json").write_text("{}", encoding="utf-8")
            (home / ".claude.json").parent.mkdir(parents=True, exist_ok=True)
            (home / ".claude.json").write_text("{}", encoding="utf-8")

            found = {d["target"]: d for d in detect_integrations(project_root=proj, home_dir=home)}
            self.assertTrue(found["cursor"]["detected"])
            self.assertTrue(found["cursor"]["project_exists"])
            self.assertTrue(found["opencode"]["detected"])
            self.assertTrue(found["claude"]["global_exists"])

    def test_integrate_preserves_existing_keys_creates_bak_and_supports_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "repo"
            home = Path(tmp) / "home"
            proj.mkdir()
            home.mkdir()
            init_workspace(proj, update_gitignore=True, sync_ignores=True)

            cursor_cfg = proj / ".cursor" / "mcp.json"
            cursor_cfg.parent.mkdir(parents=True)
            original = {"mcpServers": {"other-tool": {"command": "echo", "args": ["hi"]}}, "customKey": 42}
            cursor_cfg.write_text(json.dumps(original, indent=2) + "\n", encoding="utf-8")

            # 1. Dry-run shows diff without touching disk
            dry = integrate_target("cursor", scope="project", project_root=proj, home_dir=home, dry_run=True)
            self.assertTrue(dry["ok"])
            self.assertTrue(dry["changed"])
            self.assertIn("cortical-wiki", dry["diff"])
            self.assertFalse(cursor_cfg.with_name("mcp.json.bak").exists())

            # 2. Apply creates .bak and preserves existing keys
            applied = integrate_target("cursor", scope="project", project_root=proj, home_dir=home, dry_run=False)
            self.assertTrue(applied["ok"])
            self.assertTrue(applied["changed"])
            bak = Path(applied["backup_path"])
            self.assertTrue(bak.is_file())
            self.assertEqual(json.loads(bak.read_text(encoding="utf-8")), original)

            merged = json.loads(cursor_cfg.read_text(encoding="utf-8"))
            self.assertEqual(merged["customKey"], 42)
            self.assertIn("other-tool", merged["mcpServers"])
            self.assertIn("cortical-wiki", merged["mcpServers"])
            cw = merged["mcpServers"]["cortical-wiki"]
            self.assertEqual(cw["args"], ["-m", "cortical.mcp_server"])
            self.assertTrue(cw["env"]["CORTICAL_VAULT_DB"].endswith(".cortical/wiki.db"))

            # 3. Idempotent re-run reports changed=False
            again = integrate_target("cursor", scope="project", project_root=proj, home_dir=home, dry_run=False)
            self.assertTrue(again["ok"])
            self.assertFalse(again["changed"])

    def test_ide_specific_schemas_vscode_opencode_zed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "repo"
            home = Path(tmp) / "home"
            proj.mkdir()
            home.mkdir()

            r_vs = integrate_target("vscode", scope="project", project_root=proj, home_dir=home)
            vs_data = json.loads(Path(r_vs["path"]).read_text(encoding="utf-8"))
            self.assertEqual(vs_data["servers"]["cortical-wiki"]["type"], "stdio")

            r_oc = integrate_target("opencode", scope="project", project_root=proj, home_dir=home)
            oc_data = json.loads(Path(r_oc["path"]).read_text(encoding="utf-8"))
            self.assertEqual(oc_data["mcp"]["cortical-wiki"]["type"], "local")

            r_zed = integrate_target("zed", scope="project", project_root=proj, home_dir=home)
            zed_data = json.loads(Path(r_zed["path"]).read_text(encoding="utf-8"))
            self.assertIn("path", zed_data["context_servers"]["cortical-wiki"]["command"])

    def test_mcp_stdio_initialize_ping_and_doctor_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "repo"
            home = Path(tmp) / "home"
            proj.mkdir()
            home.mkdir()
            init_workspace(proj, update_gitignore=True, sync_ignores=True)

            ping = ping_mcp_stdio(db_path=proj / ".cortical" / "wiki.db")
            self.assertTrue(ping["ok"], f"MCP stdio ping failed: {ping}")

            diag = run_doctor_diagnostics(project_root=proj, home_dir=home, ping_mcp=True)
            self.assertTrue(diag["python"]["supported"])
            self.assertTrue(diag["workspace"]["initialized"])
            self.assertTrue(diag["workspace"]["writable"])
            self.assertTrue(diag["mcp_stdio"]["ok"])
            self.assertTrue(diag["ignore_files"][".corticalignore"])


if __name__ == "__main__":
    unittest.main()
