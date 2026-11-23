"""Tests for recursive sanitized Merkle crawl, zero-PII SQLite persistence, CLI & Wiki Dashboard UX."""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import sqlite3
import subprocess
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path

from cortical.analytics.wiki_dashboard import export_wiki_dashboard
from cortical.cli import main as cli_main
from cortical.wiki.store import KnowledgeStore


def _make_minimal_pdf(body_text: str, author: str = "Hidden PDF Author") -> bytes:
    """Builds a minimal valid single-page PDF with FlateDecode stream & /Author metadata."""
    stream_src = f"BT /F1 12 Tf 72 720 Td ({body_text}) Tj ET".encode("latin-1")
    compressed = zlib.compress(stream_src)
    parts = [
        b"%PDF-1.4\n",
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
        b"3 0 obj << /Type /Page /Parent 2 0 R /Contents 4 0 R >> endobj\n",
        b"4 0 obj << /Length " + str(len(compressed)).encode("ascii") + b" /Filter /FlateDecode >>\nstream\n"
        + compressed
        + b"\nendstream\nendobj\n",
        f"5 0 obj << /Author ({author}) /Title (Confidential Invoice) >> endobj\n".encode("latin-1"),
        b"xref\n0 6\ntrailer << /Root 1 0 R /Info 5 0 R >>\n%%EOF\n",
    ]
    return b"".join(parts)


class SanitizedCrawlTests(unittest.TestCase):
    def _build_fixture_tree(self, root: Path) -> None:
        (root / "notes").mkdir(parents=True, exist_ok=True)
        (root / "contracts").mkdir(parents=True, exist_ok=True)
        (root / "invoices").mkdir(parents=True, exist_ok=True)
        (root / "ignored").mkdir(parents=True, exist_ok=True)
        (root / "media").mkdir(parents=True, exist_ok=True)

        (root / ".geminiignore").write_text("ignored/\n*.secret\n", encoding="utf-8")
        (root / "notes" / "client_brief.md").write_text(
            "# Brief for alice@example.org\n"
            "Primary contact: alice@example.org\n"
            "Budget approved for Project Orion.\n",
            encoding="utf-8",
        )
        (root / "src_snippet.py").write_text(
            "# Cortical Service Handler\n"
            "OWNER_EMAIL = 'alice@example.org'\n"
            "API_KEY = 'sk-proj-1234567890abcdef1234567890'\n",
            encoding="utf-8",
        )
        with zipfile.ZipFile(root / "contracts" / "nda.docx", "w") as zf:
            zf.writestr("docProps/core.xml", "<cp:coreProperties><dc:creator>Secret Author</dc:creator></cp:coreProperties>")
            zf.writestr(
                "word/document.xml",
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                "<w:body><w:p><w:r><w:t>NDA with alice@example.org for Project Orion.</w:t></w:r></w:p></w:body>"
                "</w:document>",
            )

        (root / "invoices" / "bill.pdf").write_bytes(
            _make_minimal_pdf("Bill for alice@example.org IBAN IT60X0542811101000000123456", author="Hidden PDF Author")
        )
        (root / "ignored" / "keys.secret").write_text("RAW_SECRET_LEAK=top-secret-key-9999\n", encoding="utf-8")
        (root / "media" / "archive.bin").write_bytes(b"\x00\x01\x02BINARYDATA")

    def _run_cli_json(self, argv: list[str]) -> dict:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = cli_main(argv)
        self.assertEqual(rc, 0, msg=f"CLI failed for {argv}: {buf.getvalue()}")
        return json.loads(buf.getvalue())

    def test_recursive_sanitized_crawl_zero_pii_and_merkle_invalidation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tpath = Path(tmp)
            folder = tpath / "dropbox_export"
            db_path = tpath / "wiki.db"
            self._build_fixture_tree(folder)

            # 1. --dry-run preview must NOT persist anything into wiki.db
            preview = self._run_cli_json([
                "crawl", str(folder), "--sanitize", "--privacy-profile", "low",
                "--custom-terms", "Project Orion", "--db", str(db_path), "--dry-run", "--json",
            ])
            self.assertTrue(preview["dry_run"])
            self.assertEqual(preview["files_sanitized"], 5)  # 4 sample docs + .geminiignore
            self.assertGreater(preview["entities_masked_total"], 0)
            store = KnowledgeStore(db_path)
            self.assertEqual(store.list_roots(), [])

            # 2. Live sanitized recursive crawl (profile='low')
            res1 = self._run_cli_json([
                "crawl", str(folder), "--sanitize", "--privacy-profile", "low",
                "--custom-terms", "Project Orion", "--db", str(db_path), "--json",
            ])
            self.assertEqual(res1["files_sanitized"], 5)
            self.assertEqual(res1["files_skipped"], 0)
            self.assertEqual(res1["unsupported_binary"], 1)
            self.assertGreaterEqual(res1["ignored"], 1)
            self.assertGreaterEqual(res1["metadata_stripped_count"], 2)

            # Raw SQLite inspection across ALL tables including FTS5
            raw_secrets = [
                "alice@example.org",
                "IT60X0542811101000000123456",
                "Project Orion",
                "Secret Author",
                "Hidden PDF Author",
                "top-secret-key-9999",
                "sk-proj-1234567890abcdef1234567890",
            ]
            with sqlite3.connect(db_path) as conn:
                all_dump: list[str] = []
                for sql in (
                    "SELECT title, content, warnings_json, stripped_meta_json, summaries_json FROM documents",
                    "SELECT text FROM chunks",
                    "SELECT title, content, rel_path FROM documents_fts",
                    "SELECT token, category, value_hmac, encrypted_blob FROM pseudonym_vault",
                    "SELECT path, status, error_message FROM roots",
                ):
                    for row in conn.execute(sql).fetchall():
                        all_dump.append(" ".join(str(x) for x in row))
                blob = "\n".join(all_dump)
                for secret in raw_secrets:
                    self.assertNotIn(secret, blob, msg=f"Raw PII leaked into SQLite: {secret}")

                # Deterministic cross-file pseudonym consistency across md, py, docx, pdf
                doc_contents = {
                    r[0]: r[1]
                    for r in conn.execute("SELECT rel_path, content FROM documents WHERE status = 'indexed'").fetchall()
                }
                email_tokens_seen: set[str] = set()
                for rel in ("notes/client_brief.md", "src_snippet.py", "contracts/nda.docx", "invoices/bill.pdf"):
                    self.assertIn(rel, doc_contents)
                    toks = re.findall(r"\[EMAIL_\d+\]", doc_contents[rel])
                    self.assertTrue(toks, msg=f"Expected EMAIL token in {rel}: {doc_contents[rel]}")
                    email_tokens_seen.update(toks)
                self.assertEqual(len(email_tokens_seen), 1, msg=f"Inconsistent cross-file email tokens: {email_tokens_seen}")

            # 3. O(1) Merkle delta skip on unchanged re-crawl with same profile
            res2 = self._run_cli_json([
                "crawl", str(folder), "--sanitize", "--privacy-profile", "low",
                "--custom-terms", "Project Orion", "--db", str(db_path), "--json",
            ])
            self.assertEqual(res2["files_sanitized"], 0)
            self.assertGreaterEqual(res2["files_skipped"], 4)
            self.assertGreaterEqual(res2["unchanged"], 4)

            # 4. Adding a new file referencing same email keeps consistent token across runs
            (folder / "notes" / "followup.md").write_text(
                "Follow-up with alice@example.org and bob@example.org.\n", encoding="utf-8"
            )
            self._run_cli_json([
                "crawl", str(folder), "--sanitize", "--privacy-profile", "low",
                "--custom-terms", "Project Orion", "--db", str(db_path), "--json",
            ])
            with sqlite3.connect(db_path) as conn:
                fup = conn.execute(
                    "SELECT content FROM documents WHERE rel_path = 'notes/followup.md'"
                ).fetchone()[0]
                self.assertIn(next(iter(email_tokens_seen)), fup)
                self.assertIn("[EMAIL_2]", fup)
                self.assertNotIn("bob@example.org", fup)

            # 5. Escalating --privacy-profile from low -> max_security invalidates policy_sig & re-sanitizes all files
            res3 = self._run_cli_json([
                "crawl", str(folder), "--sanitize", "--privacy-profile", "max_security",
                "--custom-terms", "Project Orion", "--db", str(db_path), "--json",
            ])
            self.assertEqual(res3["files_skipped"], 0)
            self.assertGreaterEqual(res3["files_sanitized"], 5)

            nav_gated = store.navigate(privacy_filter="private_gated")
            self.assertGreaterEqual(nav_gated["privacy_summary"]["private_gated"], 5)

            # 6. Batch `cortical sanitize --recursive --output-dir`
            san_out = tpath / "sanitized_mirror"
            s_res = self._run_cli_json([
                "sanitize", str(folder), "--recursive", "--output-dir", str(san_out),
                "--privacy-profile", "medium", "--custom-terms", "Project Orion", "--json",
            ])
            self.assertEqual(s_res["files_sanitized"], 6)
            mirrored = (san_out / "contracts" / "nda.sanitized.md").read_text(encoding="utf-8")
            self.assertNotIn("alice@example.org", mirrored)
            self.assertNotIn("Project Orion", mirrored)
            self.assertIn("[EMAIL_1]", mirrored)

            # 7. Wiki Dashboard static HTML generation (zero external CDNs, valid JS, zero raw PII)
            html_dir = tpath / "html_out"
            wiki_html = export_wiki_dashboard(html_dir, db_path=db_path)
            self.assertTrue(wiki_html.is_file())
            txt = wiki_html.read_text(encoding="utf-8")
            for marker in ("PRIVATE-GATED", "Sanitization Audit Panel", "4-Tier Sanitized Summary Inspector", "Command Builder"):
                self.assertIn(marker, txt)
            for secret in raw_secrets:
                self.assertNotIn(secret, txt)
            self.assertIsNone(re.search(r"<(script|link)[^>]+src=['\"]https?://", txt, flags=re.I))

            scripts = re.findall(r"<script[^>]*>(.*?)</script>", txt, flags=re.S)
            self.assertTrue(scripts)
            js_file = tpath / "wiki_check.js"
            js_file.write_text(scripts[0], encoding="utf-8")
            node_chk = subprocess.run(["node", "--check", str(js_file)], capture_output=True, text=True)
            self.assertEqual(node_chk.returncode, 0, msg=node_chk.stderr)

    def test_settings_html_contains_folder_privacy_policy_and_zero_cdns(self) -> None:
        settings_path = Path(__file__).resolve().parents[1] / "docs" / "settings.html"
        txt = settings_path.read_text(encoding="utf-8")
        self.assertIn("Folder Ingestion &amp; Privacy Policy", txt)
        self.assertIn("Cloud Drive / Dropbox Vault", txt)
        self.assertIsNone(re.search(r"<(script|link)[^>]+(src|href)=['\"]https?://", txt, flags=re.I))


if __name__ == "__main__":
    unittest.main()
