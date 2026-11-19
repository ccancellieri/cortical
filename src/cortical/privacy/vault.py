"""Local Privacy Vault (SQLite WAL) + 3-Channel Zero-Attachment Exposure for Harnesses."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

from ..compression.engine import compress_structured, fit_to_token_budget
from .sanitizer import FailClosedError, classify_and_sanitize

VERIFIED_PRESEND_HARNESSES: frozenset[str] = frozenset({
    "pi",
    "claude-code",
    "opencode",
    "openclaw",
    "codex",
    "dsh",
    "http-router",
})


_PROC_LOCK = threading.Lock()


class PrivacyVault:
    """Stores locally ingested, sanitized, compressed items and exposes them across Channels 1-3."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.vault_dir = self.db_path.parent / "vault"
        self.inbox_dir = self.db_path.parent / "vault_inbox"
        self.process_inbox_inline = True
        with self._connect() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS vault_items (
                       alias TEXT PRIMARY KEY,
                       source_name TEXT NOT NULL,
                       resolved_policy TEXT NOT NULL,
                       profile TEXT NOT NULL,
                       local_only INTEGER NOT NULL DEFAULT 0,
                       format_used TEXT NOT NULL DEFAULT 'text',
                       sanitized_content TEXT NOT NULL,
                       entity_count INTEGER NOT NULL DEFAULT 0,
                       tokens_est INTEGER NOT NULL DEFAULT 0,
                       sha256_hash TEXT NOT NULL,
                       updated_at REAL NOT NULL
                   )"""
            )

    def _write_item_json(self, record: dict[str, Any]) -> Path:
        """Persists sanitized vault record to `.cortical_data/vault/<alias>.json` for zero-server static UI sync."""
        self.vault_dir.mkdir(parents=True, exist_ok=True)
        out_p = self.vault_dir / f"{record['alias']}.json"
        payload = {
            "alias": record["alias"],
            "uri": f"cortical://private/{record['alias']}",
            "source_name": record["source_name"],
            "resolved_policy": record["resolved_policy"],
            "profile": record["profile"],
            "local_only": bool(record["local_only"]),
            "format_used": record["format_used"],
            "sanitized_content": record["sanitized_content"],
            "entity_count": int(record["entity_count"]),
            "tokens_est": int(record["tokens_est"]),
            "sha256_hash": record["sha256_hash"],
            "updated_at": float(record["updated_at"]),
        }
        out_p.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return out_p

    def pending_inbox(self) -> list[Path]:
        """Raw files waiting in `vault_inbox/` (not yet processed, no error marker)."""
        if not self.inbox_dir.is_dir():
            return []
        return [
            f for f in sorted(self.inbox_dir.iterdir())
            if f.is_file() and not f.name.startswith(".") and not f.name.endswith((".meta.json", ".error.json"))
            and not f.with_name(f.name + ".error.json").is_file()
        ]

    def sync_from_disk(self, process_inbox: Optional[bool] = None) -> dict[str, int]:
        """Auto-ingests files dropped in `vault_inbox/` and reconciles static-UI `vault/*.json` edits/tombstones."""
        do_inbox = self.process_inbox_inline if process_inbox is None else process_inbox
        if not _PROC_LOCK.acquire(blocking=False):
            return {"inbox_processed": 0, "imported": 0, "deleted": 0}
        inbox_processed = 0
        imported = 0
        deleted = 0
        try:
            if do_inbox and self.inbox_dir.is_dir():
                for f in sorted(self.inbox_dir.iterdir()):
                    if not f.is_file() or f.name.startswith(".") or f.name.endswith(".meta.json") or f.name.endswith(".error.json"):
                        continue
                    err_p = f.with_name(f.name + ".error.json")
                    if err_p.is_file():
                        continue
                    meta_p = f.with_name(f.name + ".meta.json")
                    meta: dict[str, Any] = {}
                    if meta_p.is_file():
                        try:
                            parsed_m = json.loads(meta_p.read_text(encoding="utf-8"))
                            if isinstance(parsed_m, dict):
                                meta = parsed_m
                        except Exception:  # noqa: BLE001
                            meta = {}
                    try:
                        terms = meta.get("custom_terms")
                        keep = meta.get("keep_terms")
                        cfg_m = {"privacy": {}}
                        try:
                            from ..config import load_cortical_config
                            cfg_m = load_cortical_config()
                        except Exception:  # noqa: BLE001
                            pass
                        ing_res = self.ingest(
                            f,
                            model=meta.get("ner_model") or None,
                            vision_model=meta.get("vision_model") or None,
                            keep_terms=list(keep) if isinstance(keep, list) else None,
                            config=cfg_m,
                            alias=meta.get("alias") or None,
                            policy=str(meta.get("policy") or "auto"),
                            profile=str(meta.get("profile") or "medium"),
                            custom_terms=list(terms) if isinstance(terms, list) else None,
                            use_local_ner=bool(meta.get("use_local_ner", False)),
                        )
                        f.unlink(missing_ok=True)
                        meta_p.unlink(missing_ok=True)
                        if meta.get("source_name"):
                            with self._connect() as c2:
                                c2.execute("UPDATE vault_items SET source_name = ? WHERE alias = ?", (str(meta["source_name"])[:200], ing_res["alias"]))
                                row2 = c2.execute("SELECT * FROM vault_items WHERE alias = ?", (ing_res["alias"],)).fetchone()
                            if row2:
                                self._write_item_json({k: row2[k] for k in row2.keys()} | {"sanitized_content": row2["sanitized_content"]})
                        inbox_processed += 1
                    except Exception as exc:  # noqa: BLE001
                        err_p.write_text(
                            json.dumps({"file": f.name, "error": str(exc), "updated_at": time.time()}, indent=2),
                            encoding="utf-8",
                        )

            if self.vault_dir.is_dir():
                with self._connect() as conn:
                    existing = {
                        r["alias"]: (str(r["sha256_hash"]), float(r["updated_at"]))
                        for r in conn.execute("SELECT alias, sha256_hash, updated_at FROM vault_items").fetchall()
                    }
                    for jp in sorted(self.vault_dir.glob("*.json")):
                        try:
                            data = json.loads(jp.read_text(encoding="utf-8"))
                        except Exception:  # noqa: BLE001
                            continue
                        if not isinstance(data, dict):
                            continue
                        eff_alias = self._normalize_alias(str(data.get("alias") or jp.stem))
                        if data.get("deleted") is True:
                            conn.execute("DELETE FROM vault_items WHERE alias = ?", (eff_alias,))
                            jp.unlink(missing_ok=True)
                            deleted += 1
                            continue
                        content = str(data.get("sanitized_content") if "sanitized_content" in data else (data.get("text") or ""))
                        digest = str(data.get("sha256_hash") or hashlib.sha256(content.encode("utf-8")).hexdigest()[:16])
                        disk_ts = float(data.get("updated_at") or jp.stat().st_mtime)
                        cur_row = existing.get(eff_alias)
                        if cur_row is not None and disk_ts <= (cur_row[1] + 1e-6) and digest == cur_row[0]:
                            continue
                        if cur_row is not None and disk_ts < (cur_row[1] - 1e-6):
                            continue
                        prof = str(data.get("profile") or "medium")
                        local_only = bool(data.get("local_only", prof == "max_security"))
                        conn.execute(
                            """INSERT OR REPLACE INTO vault_items(
                                   alias, source_name, resolved_policy, profile, local_only,
                                   format_used, sanitized_content, entity_count, tokens_est, sha256_hash, updated_at
                               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (
                                eff_alias,
                                str(data.get("source_name") or f"{eff_alias}.json"),
                                str(data.get("resolved_policy") or ("fail_closed" if prof == "max_security" else "auto")),
                                prof,
                                1 if local_only else 0,
                                str(data.get("format_used") or "text"),
                                content,
                                int(data.get("entity_count") or 0),
                                int(data.get("tokens_est") or max(1, len(content) // 4)),
                                digest,
                                disk_ts,
                            ),
                        )
                        imported += 1
            return {"inbox_processed": inbox_processed, "imported": imported, "deleted": deleted}
        finally:
            _PROC_LOCK.release()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _normalize_alias(self, alias_or_name: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9._-]+", "_", str(alias_or_name).strip()).strip("_").lower()
        return slug[:48] or f"item_{int(time.time())}"

    def ingest(
        self,
        path_or_text: str | Path,
        *,
        alias: Optional[str] = None,
        policy: str = "auto",
        profile: str = "medium",
        custom_terms: Optional[list[str]] = None,
        use_local_ner: bool = False,
        llm_fn: Optional[Callable[[str], str]] = None,
        model: Optional[str] = None,
        config: Optional[dict[str, Any]] = None,
        vision_model: Optional[str] = None,
        keep_terms: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Sanitizes, compresses, and stores content locally under `cortical://private/<alias>`."""
        res = classify_and_sanitize(
            path_or_text,
            policy=policy,
            profile=profile,
            custom_terms=custom_terms,
            use_local_ner=use_local_ner,
            llm_fn=llm_fn,
            model=model,
            config=config,
            vision_model=vision_model,
            keep_terms=keep_terms,
        )
        comp = compress_structured(res["sanitized_text"])
        is_path = isinstance(path_or_text, Path) or (
            isinstance(path_or_text, str) and "\n" not in path_or_text and len(path_or_text) < 260 and Path(path_or_text).exists()
        )
        src_name = Path(path_or_text).name if is_path else "inline_note"
        eff_alias = self._normalize_alias(alias or Path(src_name).stem)
        digest = hashlib.sha256(comp["compressed"].encode("utf-8")).hexdigest()[:16]
        now = time.time()

        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO vault_items(
                       alias, source_name, resolved_policy, profile, local_only,
                       format_used, sanitized_content, entity_count, tokens_est, sha256_hash, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    eff_alias,
                    src_name,
                    res["resolved_policy"],
                    res["profile"],
                    1 if res["local_only"] else 0,
                    comp["format_used"],
                    comp["compressed"],
                    int(res["entity_count"]),
                    int(comp["compressed_tokens_est"]),
                    digest,
                    now,
                ),
            )
        self._write_item_json({
            "alias": eff_alias,
            "source_name": src_name,
            "resolved_policy": res["resolved_policy"],
            "profile": res["profile"],
            "local_only": res["local_only"],
            "format_used": comp["format_used"],
            "sanitized_content": comp["compressed"],
            "entity_count": res["entity_count"],
            "tokens_est": comp["compressed_tokens_est"],
            "sha256_hash": digest,
            "updated_at": now,
        })
        return {
            "alias": eff_alias,
            "uri": f"cortical://private/{eff_alias}",
            "source_name": src_name,
            "resolved_policy": res["resolved_policy"],
            "profile": res["profile"],
            "local_only": res["local_only"],
            "requires_confirmation": res["requires_confirmation"],
            "entity_count": res["entity_count"],
            "format_used": comp["format_used"],
            "tokens_est": comp["compressed_tokens_est"],
            "saving_pct": comp["saving_pct"],
            "sanitized_preview": comp["compressed"][:320],
        }

    def ingest_bytes(
        self,
        filename: str,
        raw_bytes: bytes,
        *,
        alias: Optional[str] = None,
        policy: str = "auto",
        profile: str = "medium",
        custom_terms: Optional[list[str]] = None,
        use_local_ner: bool = False,
        llm_fn: Optional[Callable[[str], str]] = None,
        model: Optional[str] = None,
        config: Optional[dict[str, Any]] = None,
        vision_model: Optional[str] = None,
        keep_terms: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Sanitizes, compresses, and stores uploaded file bytes while stripping metadata via extension handlers."""
        safe_name = Path(filename or "upload.txt").name or "upload.txt"
        eff_alias = alias or Path(safe_name).stem
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / safe_name
            tmp_path.write_bytes(raw_bytes)
            return self.ingest(
                tmp_path,
                alias=eff_alias,
                policy=policy,
                profile=profile,
                custom_terms=custom_terms,
                use_local_ner=use_local_ner,
                llm_fn=llm_fn,
                model=model,
                config=config,
                vision_model=vision_model,
                keep_terms=keep_terms,
            )

    def list_items(self, include_local_only: bool = True) -> list[dict[str, Any]]:
        """Lists all local Vault entries with management metadata (including `max_security` items by default)."""
        self.sync_from_disk()
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM vault_items ORDER BY updated_at DESC").fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            if r["local_only"] and not include_local_only:
                continue
            out.append({
                "alias": r["alias"],
                "uri": f"cortical://private/{r['alias']}",
                "source_name": r["source_name"],
                "resolved_policy": r["resolved_policy"],
                "profile": r["profile"],
                "local_only": bool(r["local_only"]),
                "format_used": r["format_used"],
                "entity_count": int(r["entity_count"]),
                "tokens_est": int(r["tokens_est"]),
                "sha256_hash": r["sha256_hash"],
                "updated_at": float(r["updated_at"]),
                "preview": str(r["sanitized_content"] or "")[:280],
            })
        return out

    def delete_item(self, alias_or_uri: str) -> bool:
        """Removes an item from Privacy Vault by alias or `cortical://private/<alias>` URI."""
        raw = str(alias_or_uri or "").replace("cortical://private/", "").lstrip("@").strip()
        eff_alias = self._normalize_alias(raw)
        disk_p = self.vault_dir / f"{eff_alias}.json"
        had_disk = disk_p.is_file()
        disk_p.unlink(missing_ok=True)
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM vault_items WHERE alias = ?", (eff_alias,))
            return cur.rowcount > 0 or had_disk

    def re_sanitize(
        self,
        alias_or_uri: str,
        *,
        profile: Optional[str] = None,
        policy: Optional[str] = None,
        custom_terms: Optional[list[str]] = None,
        use_local_ner: bool = False,
        llm_fn: Optional[Callable[[str], str]] = None,
        model: Optional[str] = None,
        config: Optional[dict[str, Any]] = None,
        vision_model: Optional[str] = None,
        keep_terms: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Refines privacy policy/profile or masks additional custom terms on an existing Vault item."""
        raw = str(alias_or_uri or "").replace("cortical://private/", "").lstrip("@").strip()
        eff_alias = self._normalize_alias(raw)
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM vault_items WHERE alias = ?", (eff_alias,)).fetchone()
        if not row:
            raise KeyError(f"Vault item not found: {eff_alias}")

        eff_profile = str(profile or row["profile"] or "medium")
        eff_policy = str(policy or row["resolved_policy"] or "auto")
        res = classify_and_sanitize(
            str(row["sanitized_content"]),
            policy=eff_policy,
            profile=eff_profile,
            custom_terms=custom_terms,
            use_local_ner=use_local_ner,
            llm_fn=llm_fn,
            model=model,
            config=config,
        )
        comp = compress_structured(res["sanitized_text"])
        digest = hashlib.sha256(comp["compressed"].encode("utf-8")).hexdigest()[:16]
        total_entities = int(row["entity_count"]) + int(res["entity_count"])
        now = time.time()

        with self._connect() as conn:
            conn.execute(
                """UPDATE vault_items
                   SET resolved_policy = ?, profile = ?, local_only = ?, format_used = ?,
                       sanitized_content = ?, entity_count = ?, tokens_est = ?, sha256_hash = ?, updated_at = ?
                   WHERE alias = ?""",
                (
                    res["resolved_policy"],
                    res["profile"],
                    1 if res["local_only"] else 0,
                    comp["format_used"],
                    comp["compressed"],
                    total_entities,
                    int(comp["compressed_tokens_est"]),
                    digest,
                    now,
                    eff_alias,
                ),
            )
        self._write_item_json({
            "alias": eff_alias,
            "source_name": row["source_name"],
            "resolved_policy": res["resolved_policy"],
            "profile": res["profile"],
            "local_only": res["local_only"],
            "format_used": comp["format_used"],
            "sanitized_content": comp["compressed"],
            "entity_count": total_entities,
            "tokens_est": comp["compressed_tokens_est"],
            "sha256_hash": digest,
            "updated_at": now,
        })
        return {
            "alias": eff_alias,
            "uri": f"cortical://private/{eff_alias}",
            "source_name": row["source_name"],
            "resolved_policy": res["resolved_policy"],
            "profile": res["profile"],
            "local_only": res["local_only"],
            "requires_confirmation": res["requires_confirmation"],
            "entity_count": total_entities,
            "format_used": comp["format_used"],
            "tokens_est": comp["compressed_tokens_est"],
            "saving_pct": comp["saving_pct"],
            "sanitized_preview": comp["compressed"][:320],
        }

    def list_resources(self, include_local_only: bool = False) -> list[dict[str, Any]]:
        """Channel 1: Lists native MCP resource descriptors without exposing local filesystem paths."""
        self.sync_from_disk()
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM vault_items ORDER BY updated_at DESC").fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            if r["local_only"] and not include_local_only:
                continue
            out.append({
                "uri": f"cortical://private/{r['alias']}",
                "name": r["alias"],
                "description": f"Sanitized ({r['resolved_policy']}/{r['profile']}, {r['tokens_est']} tok, {r['format_used']})",
                "mimeType": "text/plain",
                "local_only": bool(r["local_only"]),
                "tokens_est": int(r["tokens_est"]),
            })
        return out

    def read_resource(self, alias_or_uri: str, allow_local_only: bool = False) -> dict[str, Any]:
        """Channel 1: Reads sanitized content; blocks `max_security` items from remote cloud egress."""
        self.sync_from_disk()
        alias = str(alias_or_uri).replace("cortical://private/", "").lstrip("@").strip()
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM vault_items WHERE alias = ?", (alias,)).fetchone()
        if not row:
            raise KeyError(f"Vault item not found: {alias}")
        if row["local_only"] and not allow_local_only:
            raise FailClosedError(f"Vault item '{alias}' is marked max_security (local-only); cloud egress blocked.")
        return {
            "uri": f"cortical://private/{row['alias']}",
            "alias": row["alias"],
            "resolved_policy": row["resolved_policy"],
            "profile": row["profile"],
            "format_used": row["format_used"],
            "tokens_est": int(row["tokens_est"]),
            "text": row["sanitized_content"],
        }

    def export_sanitized_memory_markdown(self, num_ctx: int = 16384, max_share: float = 0.15) -> str:
        """Channel 2: Exports auto-sized sanitized memory blocks safe for harness rule/skill injection."""
        self.sync_from_disk()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM vault_items WHERE local_only = 0 ORDER BY updated_at DESC LIMIT 25"
            ).fetchall()
        if not rows:
            return ""
        blocks = [
            {
                "alias": r["alias"],
                "title": f"@private:{r['alias']} (`{r['profile']}` · {r['format_used']})",
                "content": r["sanitized_content"],
                "priority": 100 - idx,
            }
            for idx, r in enumerate(rows)
        ]
        sized = fit_to_token_budget(blocks, num_ctx=num_ctx, max_share=max_share)
        return (
            "## Cortical Sanitized Context (Zero Cloud PII)\n"
            f"_Budget: {sized['used_tokens']}/{sized['budget_tokens']} tok_\n\n"
            + sized["markdown"]
        )

    def intercept_pre_send(
        self,
        harness_id: str,
        prompt: str,
        files: list[Path | str],
        *,
        policy: str = "auto",
        profile: str = "medium",
        custom_terms: Optional[list[str]] = None,
        use_local_ner: bool = False,
        llm_fn: Optional[Callable[[str], str]] = None,
    ) -> dict[str, Any]:
        """Channel 3: Intercepts prompt attachments strictly on verified pre-send harnesses before network dispatch."""
        hid = str(harness_id or "").strip().lower()
        if hid not in VERIFIED_PRESEND_HARNESSES:
            return {
                "supported": False,
                "harness_id": hid,
                "blocked_raw_upload": False,
                "message": (
                    f"Harness '{hid}' does not guarantee 100% network pre-send interception. "
                    "Use the Cortical Dashboard or CLI `cortical ingest` beforehand."
                ),
            }

        ingested: list[dict[str, Any]] = []
        refs_text: list[str] = []
        for f in files:
            item = self.ingest(
                f,
                policy=policy,
                profile=profile,
                custom_terms=custom_terms,
                use_local_ner=use_local_ner,
                llm_fn=llm_fn,
            )
            ingested.append(item)
            if item["local_only"]:
                refs_text.append(f"[LOCAL-ONLY VAULT: @private:{item['alias']}] Keep on local runner; do not upload.")
            else:
                refs_text.append(f"[SANITIZED CONTEXT: @private:{item['alias']}]\n{item['sanitized_preview']}")

        return {
            "supported": True,
            "harness_id": hid,
            "blocked_raw_upload": True,
            "requires_approval": any(i["requires_confirmation"] or i["local_only"] for i in ingested),
            "vault_aliases": [i["alias"] for i in ingested],
            "ingested": ingested,
            "proposed_remote_prompt": prompt.strip() + ("\n\n" + "\n\n".join(refs_text) if refs_text else ""),
        }
