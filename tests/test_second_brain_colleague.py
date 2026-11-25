"""Unit & integration tests for ADR-018: Anonymized Second Brain, Bulk Folder Privatizer, Colleague Mode & Escalation."""

from __future__ import annotations

import json
import tempfile
import threading
import urllib.request
import unittest
from pathlib import Path

from cortical.cli import main as cli_main
from cortical.composers.prompt_studio import (
    detect_persona_and_language,
    generate_colleague_questions,
    run_next_prompt_flow,
)
from cortical.mcp_server import CorticalMCPServer
from cortical.privacy.sanitizer import FailClosedError
from cortical.privacy.second_brain import (
    build_anonymized_escalation_packet,
    curate_colleague_skill,
    evaluate_local_sufficiency,
    privatize_second_brain,
    reconcile_second_brain,
)


class TestSecondBrainAndColleagueMode(unittest.TestCase):
    def test_bulk_folder_privatizer_tiers_and_discrepancy_reconciliation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dossier = root / "ClientDossier"
            dossier.mkdir()
            (dossier / "contract_v1.md").write_text(
                "# Consulting Renewal Contract\n"
                "Client Contact: mario.rossi@acme.it — IBAN IT60X0542811101000000123456\n"
                "Annual consulting retainer renewal fee is €12,500 due on 2026-06-01.\n",
                encoding="utf-8",
            )
            (dossier / "contract_v2.md").write_text(
                "# Consulting Renewal Contract Addendum\n"
                "Client Contact: mario.rossi@acme.it\n"
                "Annual consulting retainer renewal fee is €15,000 due on 2026-09-01.\n",
                encoding="utf-8",
            )
            vault_db = root / "vault.db"
            skills_dir = root / "skills"

            res = privatize_second_brain(
                dossier,
                vault_db=vault_db,
                detail_tier="medium",
                reconcile=True,
                curate_skill=True,
                skill_name="Client Consulting Review",
                skills_dir=skills_dir,
            )
            self.assertTrue(res["ok"])
            self.assertTrue(res["is_directory"])
            self.assertEqual(res["files_privatized"], 2)
            self.assertGreaterEqual(res["entities_masked_total"], 2)
            self.assertEqual(len(res["aliases"]), 2)
            econ = res["token_economics"]
            self.assertGreater(econ["raw_tokens_est"], 0)
            self.assertIn("light", econ["tier_tokens_est"])
            self.assertIn("max_security", econ["tier_tokens_est"])

            rec = res["reconciliation"]
            self.assertIsNotNone(rec)
            self.assertGreaterEqual(len(rec["discrepancies"]), 1)

            sk = res["curated_skill"]
            self.assertIsNotNone(sk)
            skill_txt = Path(sk["path"]).read_text(encoding="utf-8")
            self.assertNotIn("mario.rossi@acme.it", skill_txt)
            self.assertNotIn("IT60X0542811101000000123456", skill_txt)

    def test_bilingual_colleague_persona_and_auto_discrepancy_question(self) -> None:
        persona, lang = detect_persona_and_language(
            "Vorrei riassumere i contratti del cliente nella cartella documenti",
            repo_root=Path("/tmp"),
        )
        self.assertEqual(persona, "colleague")
        self.assertEqual(lang, "it")

        qs_it = generate_colleague_questions(
            {"loop_memory": {}},
            lang="it",
            detail_tier="medium",
            discrepancies=[{"summary": "@private:doc1 (€12,500) vs @private:doc2 (€15,000)"}],
        )
        self.assertEqual(len(qs_it), 5)
        self.assertEqual(qs_it[-1]["id"], "discrepancy_resolution")
        self.assertIn("risultato concreto", qs_it[0]["title"])

    def test_local_sufficiency_vs_safe_toon_remote_escalation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            doc = root / "financial_notes.txt"
            doc.write_text(
                "Advisor: Giulia Bianchi (giulia.bianchi@studio.it), Tel +39 333 1234567.\n"
                "Portfolio allocation target: 60% BTP Italia 2028-05-15, 40% Global Equity ETF.\n",
                encoding="utf-8",
            )
            secret_doc = root / "vault_keys.txt"
            secret_doc.write_text("Master password and private recovery note", encoding="utf-8")
            vault_db = root / "vault.db"

            privatize_second_brain(doc, vault_db=vault_db, detail_tier="medium")
            privatize_second_brain(secret_doc, vault_db=vault_db, detail_tier="max_security")

            cfg = {
                "active_runner": "ollama",
                "models_by_role": {"daily_coder": "qwen3.5:9b-q3_k_xl", "deep_reasoner": "qwen3.8:27b-iq2_xxs"},
            }
            # 1) Local runner online -> local_sufficient ($0 cloud)
            suff_ok = evaluate_local_sufficiency(
                "Summarize my portfolio notes",
                doc_count=1,
                detail_tier="medium",
                config=cfg,
                runner_probe_fn=lambda _url: True,
            )
            self.assertEqual(suff_ok["verdict"], "local_sufficient")
            self.assertTrue(suff_ok["local_sufficient"])

            # 2) Local runner offline -> escalate_anonymized_remote with zero residual PII & max_security blocked
            suff_esc = evaluate_local_sufficiency(
                "Compare portfolio allocations and tax implications",
                doc_count=2,
                detail_tier="medium",
                config=cfg,
                runner_probe_fn=lambda _url: False,
            )
            self.assertEqual(suff_esc["verdict"], "escalate_anonymized_remote")

            pkt = build_anonymized_escalation_packet(
                "Compare portfolio for giulia.bianchi@studio.it",
                vault_db=vault_db,
                detail_tier="medium",
            )
            self.assertTrue(pkt["zero_residual_pii_verified"])
            self.assertEqual(pkt["blocked_max_security"], 1)
            self.assertNotIn("giulia.bianchi@studio.it", pkt["packet"])
            self.assertNotIn("Master password", pkt["packet"])

            # 3) max_security strictly blocks remote escalation packet construction
            with self.assertRaises(FailClosedError):
                build_anonymized_escalation_packet("Analyze secret", vault_db=vault_db, detail_tier="max_security")

    def test_colleague_browser_file_upload_and_mcp_directory_ingest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "Invoices"
            folder.mkdir()
            (folder / "inv_01.txt").write_text("Cliente: Luca Verdi (luca@verdi.it) — Fattura €3,200", encoding="utf-8")
            vault_db = root / "vault.db"
            skills_dir = root / "skills"

            # Verify MCP cortical_ingest_private accepts a directory seamlessly
            mcp = CorticalMCPServer(vault_db=vault_db)
            ing_res = mcp._dispatch_tool("cortical_ingest_private", {"path_or_text": str(folder), "profile": "medium"})
            self.assertIn("second_brain", ing_res)
            self.assertEqual(ing_res["second_brain"]["files_privatized"], 1)

            # Verify ephemeral browser Colleague session with uploadedFiles + auto_skill + offline escalation
            def _client_submit(url: str, port: int, tok: str) -> None:
                def _post() -> None:
                    payload = json.dumps({
                        "token": tok,
                        "seed": "Aiutami a controllare queste fatture e crea una skill",
                        "target": "hybrid",
                        "answers": {
                            "colleague_goal": "deep_comparison",
                            "detail_tier": "medium",
                            "ai_routing_mode": "smart_local_first",
                            "second_brain_learning": ["reconcile_knowledge", "auto_skill"],
                        },
                        "comments": {"colleague_goal": "Controlla anche IVA"},
                        "uploadedFiles": [
                            {"name": "inv_02.txt", "content": "Cliente: Luca Verdi (luca@verdi.it) — Fattura €4,800"}
                        ],
                    }).encode("utf-8")
                    req = urllib.request.Request(
                        f"http://127.0.0.1:{port}/submit?token={tok}",
                        data=payload,
                        headers={
                            "Host": f"127.0.0.1:{port}",
                            "Origin": f"http://127.0.0.1:{port}",
                            "Content-Type": "application/json",
                        },
                        method="POST",
                    )
                    urllib.request.urlopen(req, timeout=5).read()

                threading.Thread(target=_post, daemon=True).start()

            flow = run_next_prompt_flow(
                "Aiutami a controllare queste fatture",
                mode="browser",
                persona="colleague",
                open_browser=False,
                repo_root=root,
                vault_db=vault_db,
                data_dir=root / ".cortical_data",
                skills_dir=skills_dir,
                runner_probe_fn=lambda _u: False,
                on_browser_ready=_client_submit,
            )
            self.assertTrue(flow["ok"])
            self.assertEqual(flow["persona"], "colleague")
            self.assertEqual(flow["lang"], "it")
            self.assertTrue(flow["browser"]["port_closed"])
            self.assertEqual(flow["sufficiency"]["verdict"], "escalate_anonymized_remote")
            self.assertIsNotNone(flow["escalation_packet"])
            self.assertNotIn("luca@verdi.it", flow["prompt"])
            self.assertIsNotNone(flow["curated_skill"])
            self.assertTrue(Path(flow["curated_skill"]["path"]).is_file())

            # Verify CLI `cortical privatize --dry-run --json`
            rc = cli_main(["privatize", str(folder), "--tier", "light", "--dry-run", "--db", str(vault_db), "--json"])
            self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
