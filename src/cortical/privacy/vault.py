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
from ..config import load_cortical_config, remote_orchestrator_active
from .brain import LocalBrain
from .sanitizer import FailClosedError, classify_and_sanitize, pseudonymize_structured
from ._auto_tagger import get_default_tags_for_path


def _verify_zero_residual_pii(text: str, custom_terms: Optional[list[str]] = None) -> list[str]:
    """Scans sanitized text to ensure zero unmasked PII/secrets remain before remote egress."""
    if not text:
        return []
    _, residual = pseudonymize_structured(text, redact=False, custom_terms=custom_terms)
    return list(residual.values())

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
                       updated_at REAL NOT NULL,
                       task_tags_json TEXT NOT NULL DEFAULT '[]',
                       auto_detected_tags_json TEXT NOT NULL DEFAULT '[]'
                   )"""
            )
            cols = {r[1] for r in conn.execute("PRAGMA table_info(vault_items)").fetchall()}
            if "task_tags_json" not in cols:
                conn.execute("ALTER TABLE vault_items ADD COLUMN task_tags_json TEXT NOT NULL DEFAULT '[]'")
            if "auto_detected_tags_json" not in cols:
                conn.execute("ALTER TABLE vault_items ADD COLUMN auto_detected_tags_json TEXT NOT NULL DEFAULT '[]'")
        self.brain = LocalBrain(self._connect)

    @staticmethod
    def _normalize_tags(raw: Any) -> list[str]:
        """Normalizes raw tags input to deduplicated lowercase list."""
        if isinstance(raw, str):
            raw = [s.strip() for s in raw.split(",")]
        if not isinstance(raw, (list, tuple, set)):
            return []
        return list(dict.fromkeys(str(t).strip().lower().lstrip("#") for t in raw if str(t).strip()))

    def _write_brain_json(self) -> Path:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        out = self.db_path.parent / "brain.json"
        snap = self.brain.get_snapshot(include_local_only=True)
        out.write_text(json.dumps(snap, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return out

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
                            task_tags=self._normalize_tags(meta.get("task_tags")) or None,
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

            imported_for_brain: list[tuple[str, str, bool]] = []
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
                                   format_used, sanitized_content, entity_count, tokens_est, sha256_hash, updated_at, task_tags_json
                               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                                json.dumps(self._normalize_tags(data.get("task_tags"))),
                            ),
                        )
                        imported_for_brain.append((eff_alias, content, prof == "max_context"))
                        imported += 1
            for b_alias, b_content, b_pub in imported_for_brain:
                self.brain.distill_and_factorize(b_alias, b_content, is_public=b_pub)
            if imported or deleted or inbox_processed:
                self._write_brain_json()
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
        task_tags: Optional[list[str]] = None,
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
        # Auto-detect document tags when no explicit non-empty task_tags provided
        explicit_tags = self._normalize_tags(task_tags)
        auto_tags = self._normalize_tags(get_default_tags_for_path(path_or_text, content_hint=res["sanitized_text"]))
        norm_tags = explicit_tags or auto_tags

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
                       format_used, sanitized_content, entity_count, tokens_est, sha256_hash, updated_at,
                       task_tags_json, auto_detected_tags_json
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                    json.dumps(norm_tags),
                    json.dumps(auto_tags),
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
            "task_tags": norm_tags,
            "auto_detected_tags": auto_tags,
        })
        brain_cfg = (config or {}).get("brain") or {}
        if brain_cfg.get("auto_distill", True):
            self.brain.distill_and_factorize(
                eff_alias,
                res["sanitized_text"],
                is_public=(res["profile"] == "max_context"),
                jaccard_threshold=float(brain_cfg.get("factorize_jaccard_threshold") or 0.35),
                use_local_llm=bool(use_local_ner and llm_fn is not None),
                llm_fn=llm_fn,
                model=model,
                config=config,
            )
            self._write_brain_json()
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
            "task_tags": norm_tags,
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
        task_tags: Optional[list[str]] = None,
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

    def list_items(self, include_local_only: bool = True, task_tag: Optional[str] = None) -> list[dict[str, Any]]:
        """Lists all local Vault entries with management metadata (optionally filtered by `task_tag`)."""
        self.sync_from_disk()
        needle = str(task_tag or "").strip().lower().lstrip("#")
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM vault_items ORDER BY updated_at DESC").fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            if r["local_only"] and not include_local_only:
                continue
            try:
                tags = self._normalize_tags(json.loads(r["task_tags_json"] or "[]"))
            except Exception:  # noqa: BLE001
                tags = []
            if needle and needle not in tags:
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
                "task_tags": tags,
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
        self.brain.delete_alias(eff_alias)
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM vault_items WHERE alias = ?", (eff_alias,))
            deleted = cur.rowcount > 0 or had_disk
        if deleted:
            self._write_brain_json()
        return deleted

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
        task_tags: Optional[list[str]] = None,
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
        self.brain.distill_and_factorize(
            eff_alias,
            res["sanitized_text"],
            is_public=(res["profile"] == "max_context"),
            use_local_llm=bool(use_local_ner and llm_fn is not None),
            llm_fn=llm_fn,
            model=model,
            config=config,
        )
        self._write_brain_json()
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

    def list_resources(
        self,
        include_local_only: bool = False,
        *,
        remote_egress: bool = False,
        custom_terms: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        """Channel 1: Lists native MCP resource descriptors without exposing local filesystem paths."""
        self.sync_from_disk()
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM vault_items ORDER BY updated_at DESC").fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            if r["local_only"] and not include_local_only:
                continue
            if remote_egress and not include_local_only and _verify_zero_residual_pii(str(r["sanitized_content"] or ""), custom_terms):
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

    def read_resource(
        self,
        alias_or_uri: str,
        allow_local_only: bool = False,
        tier: str = "max",
        *,
        remote_egress: bool = False,
        custom_terms: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Channel 1: Reads sanitized/public content at `light|medium|high|max`; blocks `max_security` & unmasked PII from cloud."""
        self.sync_from_disk()
        alias = str(alias_or_uri).replace("cortical://private/", "").lstrip("@").strip()
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM vault_items WHERE alias = ?", (alias,)).fetchone()
        if not row:
            raise KeyError(f"Vault item not found: {alias}")
        if row["local_only"] and not allow_local_only:
            raise FailClosedError(
                f"Vault item '{alias}' is marked max_security (local-only); cloud egress blocked. "
                f"Process locally via cortical_local_offload(vault_alias='{alias}')."
            )
        eff_tier = str(tier or "max").lower().strip()
        tier_text = self.brain.read_tier(row["alias"], eff_tier) if eff_tier not in {"max", "l4"} else None
        text_out = tier_text if tier_text is not None else row["sanitized_content"]
        if remote_egress and not allow_local_only:
            if _verify_zero_residual_pii(str(text_out or ""), custom_terms):
                raise FailClosedError(
                    f"Remote orchestrator active: unmasked PII detected in '{alias}'; fail-closed remote egress blocked. "
                    f"Delegate locally via cortical_local_offload(vault_alias='{alias}')."
                )
        return {
            "uri": f"cortical://private/{row['alias']}",
            "alias": row["alias"],
            "tier": eff_tier,
            "resolved_policy": row["resolved_policy"],
            "profile": row["profile"],
            "format_used": row["format_used"],
            "tokens_est": int(row["tokens_est"]) if tier_text is None else max(1, len(text_out) // 4),
            "remote_egress_verified": bool(remote_egress),
            "text": text_out,
        }

    def read_task_context(
        self,
        task_tag: str,
        *,
        allow_local_only: bool = False,
        tier: str = "medium",
        remote_egress: bool = False,
        custom_terms: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Reads sanitized context across all Vault documents tagged with `task_tag`."""
        needle = str(task_tag or "").strip().lower().lstrip("#")
        matches = self.list_items(include_local_only=True, task_tag=needle)
        docs: list[dict[str, Any]] = []
        blocked_local: list[str] = []
        for m in matches:
            if m["local_only"] and not allow_local_only:
                blocked_local.append(m["alias"])
                continue
            try:
                docs.append(
                    self.read_resource(
                        m["alias"],
                        allow_local_only=allow_local_only,
                        tier=tier,
                        remote_egress=remote_egress,
                        custom_terms=custom_terms,
                    )
                )
            except FailClosedError:
                blocked_local.append(m["alias"])
        return {
            "task_tag": needle,
            "tier": tier,
            "count": len(docs),
            "documents": docs,
            "blocked_max_security_aliases": blocked_local,
        }

    def export_sanitized_memory_markdown(
        self,
        num_ctx: int = 16384,
        max_share: float = 0.15,
        *,
        remote_egress: bool = False,
        custom_terms: Optional[list[str]] = None,
    ) -> str:
        """Channel 2: Exports auto-sized sanitized memory blocks safe for harness rule/skill injection."""
        self.sync_from_disk()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM vault_items WHERE local_only = 0 ORDER BY updated_at DESC LIMIT 25"
            ).fetchall()
        safe_rows = [
            r for r in rows
            if not (remote_egress and _verify_zero_residual_pii(str(r["sanitized_content"] or ""), custom_terms))
        ]
        if not safe_rows:
            return ""
        blocks = [
            {
                "alias": r["alias"],
                "title": f"@private:{r['alias']} (`{r['profile']}` · {r['format_used']})",
                "content": r["sanitized_content"],
                "priority": 100 - idx,
            }
            for idx, r in enumerate(safe_rows)
        ]
        sized = fit_to_token_budget(blocks, num_ctx=num_ctx, max_share=max_share)
        guard_note = (
            "_Zero-Leakage Remote Guard: only verified PII-free summaries exported; process private items offline via `cortical_local_offload`._\n"
            if remote_egress
            else ""
        )
        return (
            "## Cortical Sanitized Context (Zero Cloud PII)\n"
            f"_Budget: {sized['used_tokens']}/{sized['budget_tokens']} tok_\n"
            + guard_note
            + "\n"
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
        config: Optional[dict[str, Any]] = None,
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

        cfg = config if config is not None else load_cortical_config()
        is_remote = remote_orchestrator_active(cfg)
        eff_terms = list(custom_terms or (cfg.get("privacy") or {}).get("custom_terms") or []) or None
        eff_policy = "fail_closed" if (is_remote and policy == "auto") else policy

        clean_prompt = prompt.strip()
        prompt_pii_masked = False
        if is_remote and clean_prompt:
            masked_p, p_map = pseudonymize_structured(clean_prompt, redact=False, custom_terms=eff_terms)
            if p_map:
                clean_prompt = masked_p
                prompt_pii_masked = True

        ingested: list[dict[str, Any]] = []
        refs_text: list[str] = []
        for f in files:
            item = self.ingest(
                f,
                policy=eff_policy,
                profile=profile,
                custom_terms=eff_terms,
                use_local_ner=use_local_ner,
                llm_fn=llm_fn,
                config=cfg,
            )
            ingested.append(item)
            if item["local_only"] or (is_remote and _verify_zero_residual_pii(item["sanitized_preview"], eff_terms)):
                refs_text.append(
                    f"[LOCAL-ONLY VAULT: @private:{item['alias']}] Blocked from remote orchestrator; "
                    f"delegate analysis locally via cortical_local_offload(vault_alias='{item['alias']}')."
                )
            else:
                tag = "ZERO-PII SANITIZED CONTEXT" if is_remote else "SANITIZED CONTEXT"
                refs_text.append(f"[{tag}: @private:{item['alias']}]\n{item['sanitized_preview']}")

        return {
            "supported": True,
            "harness_id": hid,
            "blocked_raw_upload": True,
            "remote_egress_guarded": is_remote,
            "prompt_pii_masked": prompt_pii_masked,
            "requires_approval": any(i["requires_confirmation"] or i["local_only"] for i in ingested) or prompt_pii_masked,
            "vault_aliases": [i["alias"] for i in ingested],
            "ingested": ingested,
            "proposed_remote_prompt": clean_prompt + ("\n\n" + "\n\n".join(refs_text) if refs_text else ""),
        }
