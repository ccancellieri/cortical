"""Stdlib-only tests for Cortical Multi-Tenant Knowledge Store, Wiki MCP Server & Redesigned Dashboard Control Plane."""

from __future__ import annotations

import base64
import json
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path

from cortical.analytics.dashboard import create_dashboard_server
from cortical.dashboard_api import DashboardController
from cortical.wiki.mcp_server import WikiMCPServer
from cortical.wiki.store import KnowledgeStore


class TestKnowledgeAndDashboardControlPlane(unittest.TestCase):
    def test_01_merkle_delta_crawler_rbac_search_episodes_and_citations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tpath = Path(tmp)
            dir_a = tpath / "alpha_docs"
            dir_b = tpath / "beta_docs"
            dir_a.mkdir()
            dir_b.mkdir()
            (dir_a / "arch.md").write_text("# Alpha Architecture\nCortical uses deterministic Merkle trees and SQLite FTS5.", encoding="utf-8")
            (dir_a / "secret.pyc").write_bytes(b"\x00\x01binary")
            (dir_b / "roadmap.md").write_text("# Beta Roadmap\nConfidential tenant beta planning document.", encoding="utf-8")

            store = KnowledgeStore(tpath / "wiki.db")
            ra = store.add_root(dir_a, principal_id="tenant_alpha")
            rb = store.add_root(dir_b, principal_id="tenant_beta")

            # Crawl all as local_owner
            c1 = store.crawl_delta(principal_id="local_owner")
            self.assertEqual(c1["roots_crawled"], 2)
            self.assertEqual(c1["added"], 2)
            self.assertEqual(c1["ignored"], 1)  # secret.pyc
            h1 = c1["merkle_roots"][ra["root_id"]]
            self.assertTrue(len(h1) == 64)

            # Second delta crawl skips unchanged files
            c2 = store.crawl_delta(root_id=ra["root_id"], principal_id="tenant_alpha")
            self.assertEqual(c2["added"], 0)
            self.assertEqual(c2["unchanged"], 1)
            self.assertEqual(c2["merkle_roots"][ra["root_id"]], h1)

            # Modify file -> delta crawl updates Merkle hash
            time.sleep(0.02)
            (dir_a / "arch.md").write_text("# Alpha Architecture v2\nUpdated deterministic Merkle tree crawler with RBAC.", encoding="utf-8")
            c3 = store.crawl_delta(root_id=ra["root_id"], principal_id="tenant_alpha")
            self.assertEqual(c3["modified"], 1)
            self.assertNotEqual(c3["merkle_roots"][ra["root_id"]], h1)

            # RBAC isolation on search & navigation
            alpha_search = store.search("Confidential", principal_id="tenant_alpha")
            self.assertEqual(len(alpha_search), 0)
            beta_search = store.search("Confidential", principal_id="tenant_beta")
            self.assertEqual(len(beta_search), 1)
            owner_search = store.search("Confidential", principal_id="local_owner")
            self.assertEqual(len(owner_search), 1)

            # Citation verification + RBAC
            v_ok = store.verify_citation("Updated deterministic Merkle tree crawler", principal_id="tenant_alpha")
            self.assertEqual(v_ok["status"], "verified")
            self.assertEqual(len(v_ok["matches"]), 1)
            v_blocked = store.verify_citation("Confidential tenant beta planning", principal_id="tenant_alpha")
            self.assertEqual(v_blocked["status"], "not_found")

            # Episodic memory + RBAC
            store.record_episode(title="Alpha Milestone", summary="Indexed arch.md", principal_id="tenant_alpha", tags=["merkle"])
            store.record_episode(title="Beta Milestone", summary="Indexed roadmap.md", principal_id="tenant_beta", tags=["beta"])
            self.assertEqual(len(store.list_episodes(principal_id="tenant_alpha")), 1)
            self.assertEqual(len(store.list_episodes(principal_id="local_owner")), 2)

            # Remove root
            self.assertFalse(store.remove_root(rb["root_id"], principal_id="tenant_alpha"))
            self.assertTrue(store.remove_root(rb["root_id"], principal_id="tenant_beta"))

    def test_02_wiki_mcp_server_protocol(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tpath = Path(tmp)
            docs = tpath / "docs"
            docs.mkdir()
            (docs / "guide.md").write_text("# Guide\nCortical MCP supports FTS5 search and citation verification.", encoding="utf-8")

            srv = WikiMCPServer(db_path=tpath / "wiki.db")
            srv.store.add_root(docs, principal_id="local_owner")

            init_r = srv.handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
            self.assertEqual(init_r["result"]["serverInfo"]["name"], "cortical-wiki")

            tools_r = srv.handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
            names = {t["name"] for t in tools_r["result"]["tools"]}
            self.assertEqual(names, {"wiki_search", "wiki_navigate", "wiki_crawl_delta", "wiki_record_episode", "wiki_verify_citation"})

            crawl_r = srv.handle_request({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "wiki_crawl_delta", "arguments": {}}})
            crawl_out = json.loads(crawl_r["result"]["content"][0]["text"])
            self.assertEqual(crawl_out["added"], 1)

            search_r = srv.handle_request({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "wiki_search", "arguments": {"query": "FTS5"}}})
            search_out = json.loads(search_r["result"]["content"][0]["text"])
            self.assertEqual(len(search_out["results"]), 1)

    def test_03_dashboard_controller_settings_guardrail_probes_and_http(self) -> None:
        def _fake_http(url: str, payload, timeout: float):
            if url.endswith("/api/tags"):
                return 200, {"models": [{"name": "nomic-embed-text"}, {"name": "qwen3.5:9b-q3_k_xl"}]}
            if url.endswith("/api/embeddings"):
                return 200, {"embedding": [0.1] * 768}
            return 200, {"choices": [{"message": {"content": "OK"}}]}

        with tempfile.TemporaryDirectory() as tmp:
            tpath = Path(tmp)
            docs = tpath / "kb"
            docs.mkdir()
            (docs / "hello.md").write_text("# Hello\nWelcome to Cortical Control Plane.", encoding="utf-8")

            ctrl = DashboardController(
                db_path=tpath / "wiki.db",
                settings_path=tpath / "dashboard_settings.json",
                http_probe_fn=_fake_http,
            )

            # Onboarding initially visible
            code, ctx0 = ctrl.handle_request("GET", "/api/context?principal_id=local_owner")
            self.assertEqual(code, 200)
            self.assertTrue(ctx0["onboarding"]["show_onboarding"])

            # Settings inline validation rejects invalid bounds
            code, bad = ctrl.handle_request("POST", "/api/settings", {"search_rag": {"default_depth": 9, "default_limit": 0}})
            self.assertEqual(code, 400)
            self.assertIn("search_rag.default_depth", bad["errors"])
            self.assertIn("search_rag.default_limit", bad["errors"])

            # Valid settings save + reset
            code, ok = ctrl.handle_request("POST", "/api/settings", {"search_rag": {"default_depth": 2, "default_limit": 25}})
            self.assertEqual(code, 200)
            self.assertEqual(ok["settings"]["search_rag"]["default_limit"], 25)
            code, rst = ctrl.handle_request("POST", "/api/settings/reset", {"section": "search_rag"})
            self.assertEqual(code, 200)
            self.assertEqual(rst["settings"]["search_rag"]["default_limit"], 10)

            # Path validation
            code, pv_ok = ctrl.handle_request("POST", "/api/validate/path", {"path": str(docs)})
            self.assertTrue(pv_ok["valid"])
            code, pv_bad = ctrl.handle_request("POST", "/api/validate/path", {"path": str(tpath / "does_not_exist")})
            self.assertFalse(pv_bad["valid"])

            # Model health probes
            code, ep = ctrl.handle_request("POST", "/api/models/probe", {"role": "embedding"})
            self.assertEqual(code, 200)
            self.assertTrue(ep["ok"])
            self.assertEqual(ep["vector_dim"], 768)

            code, lp = ctrl.handle_request("POST", "/api/models/probe", {"role": "llm"})
            self.assertEqual(code, 200)
            self.assertTrue(lp["ok"])

            # Embedding Compatibility Guardrail (409 unless acknowledged)
            code, blocked = ctrl.handle_request(
                "POST",
                "/api/models/config",
                {"models": {"embedding": {"model_id": "bge-m3", "dimensions": 1024, "tokenizer_family": "xlm-roberta"}}},
            )
            self.assertEqual(code, 409)
            self.assertEqual(blocked["error"], "embedding_incompatible")
            self.assertTrue(blocked["compatibility"]["dim_mismatch"])

            # Register root, upload file, and run async crawl
            code, rres = ctrl.handle_request("POST", "/api/roots", {"path": str(docs), "principal_id": "local_owner"})
            self.assertEqual(code, 200)
            rid = rres["root"]["root_id"]

            b64 = base64.b64encode(b"# Uploaded\nUploaded via drag and drop.").decode("ascii")
            code, ures = ctrl.handle_request(
                "POST",
                "/api/files/upload",
                {"root_id": rid, "principal_id": "local_owner", "filename": "uploaded.md", "content_base64": b64, "auto_crawl": True},
            )
            self.assertEqual(code, 200)
            job_id = ures["job"]["job_id"]
            for _ in range(40):
                _, st = ctrl.handle_request("GET", f"/api/crawl/status?job_id={job_id}")
                if st["job"]["status"] != "running":
                    break
                time.sleep(0.05)
            self.assertEqual(st["job"]["status"], "completed")
            self.assertEqual(st["job"]["summary"]["added"], 2)

            # Acknowledge embedding change + trigger reindex
            code, ack = ctrl.handle_request(
                "POST",
                "/api/models/config",
                {
                    "models": {"embedding": {"model_id": "bge-m3", "dimensions": 1024, "tokenizer_family": "xlm-roberta"}},
                    "confirm_reindex_ack": True,
                    "trigger_reindex": True,
                },
            )
            self.assertEqual(code, 200)
            self.assertIsNotNone(ack["job"])

            # Real HTTP server smoke check
            httpd, _ = create_dashboard_server(
                tpath / "web",
                port=0,
                db_path=tpath / "wiki.db",
                settings_path=tpath / "dashboard_settings.json",
                http_probe_fn=_fake_http,
            )
            port = httpd.server_address[1]
            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            try:
                html = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5).read().decode("utf-8")
                self.assertIn("Knowledge &amp; Files", html)
                self.assertIn("Models &amp; Runtime", html)
                self.assertIn("Memory &amp; Inspector", html)
                self.assertIn("Command Palette", html)
                ctx_raw = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/context", timeout=5).read().decode("utf-8")
                self.assertTrue(json.loads(ctx_raw)["ok"])
            finally:
                httpd.shutdown()
                httpd.server_close()


if __name__ == "__main__":
    unittest.main()
