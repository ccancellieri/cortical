"""Multi-tenant Knowledge Store: SQLite WAL + FTS5 + Deterministic SHA-256 Merkle-Tree Delta Crawler + RBAC."""

from __future__ import annotations

import base64
import fnmatch
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

from ..privacy.sanitizer import (
    FailClosedError,
    classify_and_sanitize,
    pseudonymize_structured,
)

DEFAULT_IGNORE_PATTERNS: list[str] = [
    ".git",
    ".git/*",
    ".cortical",
    ".cortical/*",
    ".cortical_data",
    ".cortical_data/*",
    ".venv",
    ".venv/*",
    "node_modules",
    "node_modules/*",
    "__pycache__",
    "__pycache__/*",
    "*.pyc",
    "*.pyo",
    "*.db",
    "*.db-wal",
    "*.db-shm",
    ".pseudonym.key",
    ".DS_Store",
]

SANITIZABLE_BINARY_EXTENSIONS: set[str] = {".pdf", ".docx", ".xlsx", ".pptx"}
IGNORE_FILENAMES: tuple[str, ...] = (".corticalignore", ".geminiignore", ".cursorignore", ".claudeignore")
_IMAGE_SUFFIXES: set[str] = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}

TEXT_EXTENSIONS: set[str] = {
    ".md", ".txt", ".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".yaml", ".yml",
    ".toml", ".ini", ".cfg", ".conf", ".csv", ".tsv", ".html", ".htm", ".css",
    ".xml", ".sql", ".sh", ".bash", ".zsh", ".go", ".rs", ".java", ".c", ".h",
    ".cpp", ".hpp", ".rb", ".php", ".swift", ".kt", ".r", ".env.example", ".rst",
}

MAX_FILE_BYTES = 2 * 1024 * 1024  # 2 MiB safe text cap


def _sha256_str(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_or_create_vault_key(db_path: Path) -> bytes:
    """Loads or initializes a local 256-bit key in `<db_dir>/.pseudonym.key` (never stored in SQLite)."""
    key_path = db_path.parent / ".pseudonym.key"
    if key_path.is_file():
        try:
            raw = bytes.fromhex(key_path.read_text(encoding="ascii").strip())
            if len(raw) == 32:
                return raw
        except Exception:  # noqa: BLE001
            pass
    key = secrets.token_bytes(32)
    key_path.write_text(key.hex() + "\n", encoding="ascii")
    try:
        os.chmod(key_path, 0o600)
    except OSError:
        pass
    return key


def _hmac_value(key: bytes, value: str) -> str:
    return hmac.new(key, value.encode("utf-8", errors="replace"), hashlib.sha256).hexdigest()


def _encrypt_token_value(key: bytes, value: str) -> str:
    plain = value.encode("utf-8", errors="replace")
    nonce = secrets.token_bytes(16)
    stream = bytearray()
    blk = 0
    while len(stream) < len(plain):
        stream.extend(hashlib.sha256(key + nonce + blk.to_bytes(4, "big")).digest())
        blk += 1
    cipher = bytes(b ^ s for b, s in zip(plain, stream))
    return "v1:" + base64.b64encode(nonce + cipher).decode("ascii")


class _HmacAwareRev(dict):
    """Maps raw entities to consistent tokens across crawls via HMAC without keeping plaintext in SQLite."""

    def __init__(self, key: bytes, hmac_to_tok: dict[str, str]) -> None:
        super().__init__()
        self._key = key
        self._hmac_to_tok = hmac_to_tok

    def __contains__(self, raw_val: object) -> bool:
        if super().__contains__(raw_val):
            return True
        if isinstance(raw_val, str) and _hmac_value(self._key, raw_val) in self._hmac_to_tok:
            return True
        return False

    def __getitem__(self, raw_val: str) -> str:
        if super().__contains__(raw_val):
            return super().__getitem__(raw_val)
        hv = _hmac_value(self._key, raw_val)
        if hv in self._hmac_to_tok:
            tok = self._hmac_to_tok[hv]
            super().__setitem__(raw_val, tok)
            return tok
        raise KeyError(raw_val)


def _build_four_tier_summaries(text: str, title: str) -> dict[str, str]:
    """Generates light/medium/high/max 4-tier summaries strictly from already-sanitized text."""
    clean_lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    joined = "\n".join(clean_lines)
    if not joined:
        base = title or "(empty)"
        return {"light": base, "medium": base, "high": base, "max": base}
    first_sent = re.split(r"(?<=[.!?])\s+", clean_lines[0], maxsplit=1)[0]
    light_raw = f"{title}: {first_sent}" if title and not first_sent.startswith(title) else first_sent
    light = (light_raw[:217] + "...") if len(light_raw) > 220 else light_raw
    headings_and_body = [ln for ln in clean_lines if ln.startswith("#") or len(ln) > 12]
    med_src = "\n".join(headings_and_body[:16]) or joined
    medium = (med_src[:697] + "...") if len(med_src) > 700 else med_src
    high = (joined[:1997] + "...") if len(joined) > 2000 else joined
    max_txt = (text[:11997] + "...") if len(text) > 12000 else text
    return {"light": light, "medium": medium, "high": high, "max": max_txt}


def _normalize_principal(principal_id: Optional[str]) -> str:
    val = re.sub(r"[^a-zA-Z0-9._-]+", "_", str(principal_id or "local_owner").strip())
    return val or "local_owner"


def _matches_ignore(rel_path: str, patterns: list[str]) -> bool:
    norm = rel_path.replace("\\", "/").lstrip("./")
    parts = norm.split("/")
    for raw in patterns:
        pat = str(raw or "").strip()
        if not pat or pat.startswith("#"):
            continue
        pat = pat.rstrip("/")
        if fnmatch.fnmatch(norm, pat) or fnmatch.fnmatch(parts[-1], pat):
            return True
        if any(fnmatch.fnmatch(p, pat) for p in parts):
            return True
    return False


def _chunk_text(text: str, chunk_size: int = 1200, overlap: int = 150) -> list[dict[str, Any]]:
    if not text.strip():
        return []
    chunks: list[dict[str, Any]] = []
    n = len(text)
    pos = 0
    idx = 0
    step = max(200, chunk_size - overlap)
    while pos < n:
        end = min(n, pos + chunk_size)
        seg = text[pos:end]
        chunks.append({
            "chunk_index": idx,
            "char_start": pos,
            "char_end": end,
            "token_est": max(1, len(seg) // 4),
            "text": seg,
        })
        if end >= n:
            break
        pos += step
        idx += 1
    return chunks


def _tokenize_for_citation(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9_]{3,}", text.lower())}


class KnowledgeStore:
    """SQLite WAL + FTS5 multi-tenant knowledge base with deterministic Merkle-tree delta crawling."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS principals (
                    principal_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'tenant',
                    isolation_policy TEXT NOT NULL DEFAULT 'strict',
                    created_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS roots (
                    root_id TEXT PRIMARY KEY,
                    path TEXT NOT NULL,
                    principal_id TEXT NOT NULL,
                    ignore_patterns_json TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL DEFAULT 'changes_detected',
                    last_crawl_at REAL,
                    merkle_root_hash TEXT NOT NULL DEFAULT '',
                    doc_count INTEGER NOT NULL DEFAULT 0,
                    chunk_count INTEGER NOT NULL DEFAULT 0,
                    error_message TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    UNIQUE(path, principal_id)
                );

                CREATE TABLE IF NOT EXISTS documents (
                    doc_id TEXT PRIMARY KEY,
                    root_id TEXT NOT NULL REFERENCES roots(root_id) ON DELETE CASCADE,
                    rel_path TEXT NOT NULL,
                    abs_path TEXT NOT NULL,
                    principal_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'indexed',
                    file_size INTEGER NOT NULL DEFAULT 0,
                    mtime REAL NOT NULL DEFAULT 0,
                    content_hash TEXT NOT NULL DEFAULT '',
                    merkle_hash TEXT NOT NULL DEFAULT '',
                    title TEXT NOT NULL DEFAULT '',
                    content TEXT NOT NULL DEFAULT '',
                    chunk_count INTEGER NOT NULL DEFAULT 0,
                    warnings_json TEXT NOT NULL DEFAULT '[]',
                    sanitized INTEGER NOT NULL DEFAULT 0,
                    privacy_profile TEXT NOT NULL DEFAULT 'raw',
                    privacy_namespace TEXT NOT NULL DEFAULT '',
                    policy_sig TEXT NOT NULL DEFAULT 'raw',
                    entities_masked INTEGER NOT NULL DEFAULT 0,
                    entities_by_cat_json TEXT NOT NULL DEFAULT '{}',
                    stripped_meta_json TEXT NOT NULL DEFAULT '[]',
                    summaries_json TEXT NOT NULL DEFAULT '{}',
                    indexed_at REAL NOT NULL,
                    UNIQUE(root_id, rel_path)
                );

                CREATE TABLE IF NOT EXISTS pseudonym_vault (
                    root_id TEXT NOT NULL,
                    token TEXT NOT NULL,
                    category TEXT NOT NULL,
                    value_hmac TEXT NOT NULL,
                    encrypted_blob TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY (root_id, token)
                );

                CREATE TABLE IF NOT EXISTS chunks (
                    chunk_id TEXT PRIMARY KEY,
                    doc_id TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
                    principal_id TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    char_start INTEGER NOT NULL,
                    char_end INTEGER NOT NULL,
                    token_est INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    embedding_model TEXT NOT NULL DEFAULT '',
                    embedding_dim INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS episodes (
                    episode_id TEXT PRIMARY KEY,
                    principal_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    source_refs_json TEXT NOT NULL DEFAULT '[]',
                    created_at REAL NOT NULL
                );

                CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
                    title,
                    content,
                    rel_path,
                    principal_id UNINDEXED,
                    doc_id UNINDEXED
                );
                """
            )
            now = time.time()
            # Migrate legacy schemas missing sanitization / summary columns
            doc_cols = {r[1] for r in conn.execute("PRAGMA table_info(documents)").fetchall()}
            migrations = (
                ("sanitized", "INTEGER NOT NULL DEFAULT 0"),
                ("privacy_profile", "TEXT NOT NULL DEFAULT 'raw'"),
                ("privacy_namespace", "TEXT NOT NULL DEFAULT ''"),
                ("policy_sig", "TEXT NOT NULL DEFAULT 'raw'"),
                ("entities_masked", "INTEGER NOT NULL DEFAULT 0"),
                ("entities_by_cat_json", "TEXT NOT NULL DEFAULT '{}'"),
                ("stripped_meta_json", "TEXT NOT NULL DEFAULT '[]'"),
                ("summaries_json", "TEXT NOT NULL DEFAULT '{}'"),
            )
            for col_name, col_def in migrations:
                if col_name not in doc_cols:
                    conn.execute(f"ALTER TABLE documents ADD COLUMN {col_name} {col_def}")
            conn.execute(
                """
                INSERT OR IGNORE INTO principals (principal_id, display_name, role, isolation_policy, created_at)
                VALUES ('local_owner', 'Local Owner (Full Access)', 'owner', 'strict', ?)
                """,
                (now,),
            )

    # ---- Principals / RBAC ----

    def list_principals(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT principal_id, display_name, role, isolation_policy, created_at FROM principals ORDER BY role ASC, principal_id ASC"
            ).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                cnt = conn.execute(
                    "SELECT COUNT(*) FROM documents WHERE principal_id = ? AND status = 'indexed'",
                    (d["principal_id"],),
                ).fetchone()[0]
                d["indexed_docs"] = int(cnt)
                out.append(d)
            return out

    def ensure_principal(
        self,
        principal_id: str,
        display_name: Optional[str] = None,
        role: str = "tenant",
        isolation_policy: str = "strict",
    ) -> dict[str, Any]:
        pid = _normalize_principal(principal_id)
        if pid == "local_owner":
            role = "owner"
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO principals (principal_id, display_name, role, isolation_policy, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(principal_id) DO UPDATE SET
                    display_name = COALESCE(NULLIF(excluded.display_name, ''), principals.display_name),
                    isolation_policy = excluded.isolation_policy
                """,
                (pid, display_name or pid, role, isolation_policy, time.time()),
            )
            row = conn.execute("SELECT * FROM principals WHERE principal_id = ?", (pid,)).fetchone()
            return dict(row)

    def _rbac_clause(self, principal_id: str, column: str = "principal_id") -> tuple[str, list[Any]]:
        pid = _normalize_principal(principal_id)
        if pid == "local_owner":
            return "1=1", []
        return f"{column} = ?", [pid]

    # ---- Roots Management ----

    def add_root(
        self,
        path: str | Path,
        principal_id: str = "local_owner",
        ignore_patterns: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        pid = _normalize_principal(principal_id)
        self.ensure_principal(pid)
        resolved = str(Path(path).expanduser().resolve())
        if not Path(resolved).is_dir():
            raise ValueError(f"Directory does not exist: {resolved}")
        patterns = list(ignore_patterns) if ignore_patterns is not None else list(DEFAULT_IGNORE_PATTERNS)
        root_id = "root_" + _sha256_str(f"{pid}:{resolved}")[:12]
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO roots (root_id, path, principal_id, ignore_patterns_json, status, created_at)
                VALUES (?, ?, ?, ?, 'changes_detected', ?)
                ON CONFLICT(path, principal_id) DO UPDATE SET
                    ignore_patterns_json = excluded.ignore_patterns_json
                """,
                (root_id, resolved, pid, json.dumps(patterns), now),
            )
            row = conn.execute("SELECT * FROM roots WHERE path = ? AND principal_id = ?", (resolved, pid)).fetchone()
            return self._root_row_to_dict(row)

    def list_roots(self, principal_id: str = "local_owner") -> list[dict[str, Any]]:
        clause, params = self._rbac_clause(principal_id)
        with self._connect() as conn:
            rows = conn.execute(f"SELECT * FROM roots WHERE {clause} ORDER BY created_at DESC", params).fetchall()
            return [self._root_row_to_dict(r) for r in rows]

    def remove_root(self, root_id: str, principal_id: str = "local_owner") -> bool:
        clause, params = self._rbac_clause(principal_id)
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT root_id FROM roots WHERE root_id = ? AND {clause}",
                [root_id, *params],
            ).fetchone()
            if not row:
                return False
            doc_ids = [r[0] for r in conn.execute("SELECT doc_id FROM documents WHERE root_id = ?", (root_id,)).fetchall()]
            for did in doc_ids:
                conn.execute("DELETE FROM documents_fts WHERE doc_id = ?", (did,))
            conn.execute("DELETE FROM roots WHERE root_id = ?", (root_id,))
            return True

    def _root_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        try:
            d["ignore_patterns"] = json.loads(d.pop("ignore_patterns_json", "[]") or "[]")
        except Exception:  # noqa: BLE001
            d["ignore_patterns"] = []
        return d

    # ---- Deterministic Merkle-Tree Delta Crawler ----

    def _collect_ignore_patterns(self, base: Path, configured: list[str]) -> list[str]:
        patterns = list(configured or DEFAULT_IGNORE_PATTERNS)
        for ign_name in IGNORE_FILENAMES:
            ign_file = base / ign_name
            if ign_file.is_file():
                try:
                    for line in ign_file.read_text(encoding="utf-8", errors="ignore").splitlines():
                        s = line.strip()
                        if s and not s.startswith("#") and s not in patterns:
                            patterns.append(s)
                except OSError:
                    pass
        if ".pseudonym.key" not in patterns:
            patterns.append(".pseudonym.key")
        return patterns

    def _load_folder_pseudonym_state(
        self, conn: sqlite3.Connection, root_id: str, vault_key: bytes,
    ) -> dict[str, Any]:
        hmac_to_tok: dict[str, str] = {}
        counters: dict[str, int] = {}
        rows = conn.execute(
            "SELECT token, category, value_hmac FROM pseudonym_vault WHERE root_id = ?",
            (root_id,),
        ).fetchall()
        for r in rows:
            tok = str(r["token"])
            hmac_to_tok[str(r["value_hmac"])] = tok
            m = re.match(r"^\[([A-Z0-9_]+)_(\d+)\]$", tok)
            if m:
                cat, num = m.group(1), int(m.group(2))
                if num > counters.get(cat, 0):
                    counters[cat] = num
        return {"rev": _HmacAwareRev(vault_key, hmac_to_tok), "counters": counters}

    def _persist_pseudonym_mappings(
        self, conn: sqlite3.Connection, root_id: str, vault_key: bytes, mapping: dict[str, str], now: float,
    ) -> None:
        for tok, raw_val in mapping.items():
            clean = tok.strip("[]")
            cat = clean.rsplit("_", 1)[0] if "_" in clean else clean
            conn.execute(
                """
                INSERT INTO pseudonym_vault (root_id, token, category, value_hmac, encrypted_blob, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(root_id, token) DO NOTHING
                """,
                (root_id, tok, cat, _hmac_value(vault_key, raw_val), _encrypt_token_value(vault_key, raw_val), now),
            )

    def _parse_and_sanitize(
        self,
        *,
        fpath: Path,
        rel: str,
        ext: str,
        raw_bytes: bytes,
        fsize: int,
        sanitize: bool,
        privacy_profile: str,
        custom_terms: Optional[list[str]],
        use_local_ner: bool,
        folder_state: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        warnings: list[str] = []
        if not sanitize:
            if fsize > MAX_FILE_BYTES:
                warnings.append(f"File truncated to {MAX_FILE_BYTES // 1024} KiB for indexing.")
            if ext and ext not in TEXT_EXTENSIONS and b"\x00" in raw_bytes[:1024]:
                warnings.append(f"Binary file ({ext}) indexed by metadata only.")
                text = f"[Binary file: {rel} ({fsize} bytes)]"
            else:
                text = raw_bytes.decode("utf-8", errors="replace")
            title = self._extract_title(text, fpath.name)
            return {
                "unsupported": False, "text": text, "title": title, "warnings": warnings,
                "summaries": _build_four_tier_summaries(text, title),
                "entities_masked": 0, "entities_by_cat": {}, "stripped_meta": [], "pseudonym_map": {},
            }

        is_extractable_doc = ext in SANITIZABLE_BINARY_EXTENSIONS
        is_unknown_binary = (ext in _IMAGE_SUFFIXES) or (
            ext and not is_extractable_doc and ext not in TEXT_EXTENSIONS and b"\x00" in raw_bytes[:1024]
        )
        if is_unknown_binary:
            return {
                "unsupported": True, "text": "", "title": fpath.name,
                "warnings": [f"Unsupported binary file skipped ({ext or 'binary'})"],
                "summaries": {}, "entities_masked": 0, "entities_by_cat": {}, "stripped_meta": [], "pseudonym_map": {},
            }

        eff_policy = "fail_closed" if privacy_profile == "max_security" else "auto"
        san_input: str | Path = fpath
        if not is_extractable_doc and fsize > MAX_FILE_BYTES:
            warnings.append(f"File truncated to {MAX_FILE_BYTES // 1024} KiB before sanitization.")
            san_input = raw_bytes.decode("utf-8", errors="replace")
        san = classify_and_sanitize(
            san_input,
            policy=eff_policy,
            profile=privacy_profile,
            custom_terms=custom_terms,
            use_local_ner=use_local_ner,
            pseudonym_state=folder_state,
            preserve_pseudonyms=True,
        )
        san_text = str(san.get("sanitized_text") or "")
        raw_title = self._extract_title(san_text, fpath.name)
        clean_title, title_map = pseudonymize_structured(
            raw_title, redact=False, custom_terms=custom_terms, pseudonym_state=folder_state,
        )
        combined_map = dict(san.get("pseudonym_map") or {})
        combined_map.update(title_map)
        by_cat = dict(san.get("entities_by_category") or {})
        stripped_meta = list(san.get("stripped_metadata") or [])
        return {
            "unsupported": False,
            "text": san_text,
            "title": clean_title,
            "warnings": warnings,
            "summaries": _build_four_tier_summaries(san_text, clean_title),
            "entities_masked": int(san.get("entity_count") or 0),
            "entities_by_cat": by_cat,
            "stripped_meta": stripped_meta,
            "pseudonym_map": combined_map,
        }

    def crawl_delta(
        self,
        *,
        root_id: Optional[str] = None,
        principal_id: str = "local_owner",
        full_reindex: bool = False,
        embedding_model: str = "",
        embedding_dim: int = 0,
        sanitize: bool = False,
        privacy_profile: str = "medium",
        custom_terms: Optional[list[str]] = None,
        privacy_namespace: str = "cortical://private",
        dry_run: bool = False,
        use_local_ner: bool = False,
        progress_cb: Optional[Callable[[dict[str, Any]], None]] = None,
    ) -> dict[str, Any]:
        clause, params = self._rbac_clause(principal_id)
        with self._connect() as conn:
            if root_id:
                roots = conn.execute(
                    f"SELECT * FROM roots WHERE root_id = ? AND {clause}",
                    [root_id, *params],
                ).fetchall()
            else:
                roots = conn.execute(f"SELECT * FROM roots WHERE {clause}", params).fetchall()

        summary: dict[str, Any] = {
            "roots_crawled": 0,
            "total_files": 0,
            "files_scanned": 0,
            "files_skipped": 0,
            "files_sanitized": 0,
            "unsupported_binary": 0,
            "added": 0,
            "modified": 0,
            "unchanged": 0,
            "ignored": 0,
            "removed": 0,
            "errors": 0,
            "entities_masked_total": 0,
            "metadata_stripped_count": 0,
            "entities_by_category": {},
            "sanitized": bool(sanitize),
            "privacy_profile": privacy_profile if sanitize else "raw",
            "dry_run": bool(dry_run),
            "merkle_roots": {},
        }
        for rrow in roots:
            rdict = self._root_row_to_dict(rrow)
            res = self._crawl_single_root(
                rdict,
                full_reindex=full_reindex,
                embedding_model=embedding_model,
                embedding_dim=embedding_dim,
                sanitize=sanitize,
                privacy_profile=privacy_profile,
                custom_terms=custom_terms,
                privacy_namespace=privacy_namespace,
                dry_run=dry_run,
                use_local_ner=use_local_ner,
                progress_cb=progress_cb,
            )
            summary["roots_crawled"] += 1
            for k in (
                "total_files", "files_scanned", "files_skipped", "files_sanitized",
                "unsupported_binary", "added", "modified", "unchanged", "ignored",
                "removed", "errors", "entities_masked_total", "metadata_stripped_count",
            ):
                summary[k] += int(res.get(k, 0))
            for cat, cnt in (res.get("entities_by_category") or {}).items():
                summary["entities_by_category"][cat] = summary["entities_by_category"].get(cat, 0) + int(cnt)
            summary["merkle_roots"][rdict["root_id"]] = res["merkle_root_hash"]
        return summary

    def _crawl_single_root(
        self,
        root: dict[str, Any],
        *,
        full_reindex: bool,
        embedding_model: str,
        embedding_dim: int,
        sanitize: bool = False,
        privacy_profile: str = "medium",
        custom_terms: Optional[list[str]] = None,
        privacy_namespace: str = "cortical://private",
        dry_run: bool = False,
        use_local_ner: bool = False,
        progress_cb: Optional[Callable[[dict[str, Any]], None]] = None,
    ) -> dict[str, Any]:
        rid = root["root_id"]
        pid = root["principal_id"]
        base = Path(root["path"])
        patterns = self._collect_ignore_patterns(base, list(root.get("ignore_patterns") or DEFAULT_IGNORE_PATTERNS))
        terms_clean = sorted({str(t).strip() for t in (custom_terms or []) if str(t).strip()})
        terms_hash = _sha256_str(json.dumps(terms_clean))[:16]
        policy_sig = f"san:{privacy_profile}:{terms_hash}" if sanitize else "raw"

        with self._connect() as conn:
            if not dry_run:
                conn.execute("UPDATE roots SET status = 'syncing', error_message = '' WHERE root_id = ?", (rid,))
            existing_rows = conn.execute(
                """
                SELECT doc_id, rel_path, content_hash, mtime, file_size, status,
                       policy_sig, sanitized, entities_masked, entities_by_cat_json, stripped_meta_json
                FROM documents WHERE root_id = ?
                """,
                (rid,),
            ).fetchall()
            vault_key: Optional[bytes] = None
            folder_state: Optional[dict[str, Any]] = None
            if sanitize:
                if dry_run and not (self.db_path.parent / ".pseudonym.key").is_file():
                    vault_key = secrets.token_bytes(32)
                else:
                    vault_key = _load_or_create_vault_key(self.db_path)
                folder_state = self._load_folder_pseudonym_state(conn, rid, vault_key)
        existing = {r["rel_path"]: dict(r) for r in existing_rows}

        if not base.is_dir():
            if not dry_run:
                with self._connect() as conn:
                    conn.execute(
                        "UPDATE roots SET status = 'error', error_message = ? WHERE root_id = ?",
                        (f"Directory missing: {base}", rid),
                    )
            return {
                "total_files": 0, "files_scanned": 0, "files_skipped": 0, "files_sanitized": 0,
                "unsupported_binary": 0, "added": 0, "modified": 0, "unchanged": 0,
                "ignored": 0, "removed": 0, "errors": 1, "entities_masked_total": 0,
                "metadata_stripped_count": 0, "entities_by_category": {}, "merkle_root_hash": "",
            }

        discovered: list[tuple[str, Path, bool]] = []
        for dirpath, dirnames, filenames in os.walk(base):
            rel_dir = os.path.relpath(dirpath, base).replace("\\", "/")
            if rel_dir == ".":
                rel_dir = ""
            pruned = []
            for d in sorted(dirnames):
                cand = f"{rel_dir}/{d}" if rel_dir else d
                if _matches_ignore(cand, patterns):
                    continue
                pruned.append(d)
            dirnames[:] = pruned
            for fname in sorted(filenames):
                rel = f"{rel_dir}/{fname}" if rel_dir else fname
                is_ignored = _matches_ignore(rel, patterns)
                discovered.append((rel, Path(dirpath) / fname, is_ignored))

        total = len(discovered)
        stats: dict[str, Any] = {
            "total_files": total, "files_scanned": total, "files_skipped": 0,
            "files_sanitized": 0, "unsupported_binary": 0,
            "added": 0, "modified": 0, "unchanged": 0, "ignored": 0, "removed": 0, "errors": 0,
            "entities_masked_total": 0, "metadata_stripped_count": 0,
            "entities_by_category": {}, "merkle_root_hash": "",
        }
        seen_paths: set[str] = set()
        merkle_entries: list[str] = []
        now = time.time()

        with self._connect() as conn:
            for idx, (rel, fpath, is_ignored) in enumerate(discovered, start=1):
                seen_paths.add(rel)
                doc_id = "doc_" + _sha256_str(f"{rid}:{rel}")[:16]
                try:
                    st = fpath.stat()
                    fsize = int(st.st_size)
                    mtime = float(st.st_mtime)
                except OSError as exc:
                    stats["errors"] += 1
                    err_msg = "[Sanitized I/O error]" if sanitize else str(exc)
                    if not dry_run:
                        self._upsert_doc(
                            conn, doc_id=doc_id, root_id=rid, rel_path=rel, abs_path=str(fpath),
                            principal_id=pid, status="error", file_size=0, mtime=0.0,
                            content_hash="", merkle_hash=_sha256_str(f"{rel}:error"),
                            title=fpath.name, content="", chunks=[], warnings=[err_msg],
                            embedding_model=embedding_model, embedding_dim=embedding_dim, now=now,
                            sanitized=sanitize, privacy_profile=privacy_profile if sanitize else "raw",
                            privacy_namespace=privacy_namespace if sanitize else "",
                            policy_sig=policy_sig,
                        )
                    if progress_cb:
                        progress_cb({"processed": idx, "total": total, "rel_path": rel, "action": "error", "message": err_msg})
                    continue

                if is_ignored:
                    stats["ignored"] += 1
                    mhash = _sha256_str(f"{rel}:ignored:{policy_sig}")
                    if not dry_run:
                        self._upsert_doc(
                            conn, doc_id=doc_id, root_id=rid, rel_path=rel, abs_path=str(fpath),
                            principal_id=pid, status="ignored", file_size=fsize, mtime=mtime,
                            content_hash="", merkle_hash=mhash, title=fpath.name, content="",
                            chunks=[], warnings=["Matched ignore pattern"],
                            embedding_model=embedding_model, embedding_dim=embedding_dim, now=now,
                            sanitized=sanitize, privacy_profile=privacy_profile if sanitize else "raw",
                            privacy_namespace=privacy_namespace if sanitize else "",
                            policy_sig=policy_sig,
                        )
                    if progress_cb:
                        progress_cb({"processed": idx, "total": total, "rel_path": rel, "action": "ignored"})
                    continue

                prev = existing.get(rel)
                prev_sig = str(prev.get("policy_sig") or "raw") if prev else "raw"
                if (
                    not full_reindex
                    and prev
                    and prev["status"] == "indexed"
                    and int(prev["file_size"]) == fsize
                    and abs(float(prev["mtime"]) - mtime) < 1e-3
                    and prev_sig == policy_sig
                ):
                    stats["unchanged"] += 1
                    stats["files_skipped"] += 1
                    mhash = _sha256_str(f"{rel}:{prev['content_hash']}")
                    merkle_entries.append(f"{rel}:{mhash}")
                    if progress_cb:
                        progress_cb({"processed": idx, "total": total, "rel_path": rel, "action": "unchanged"})
                    continue

                ext = fpath.suffix.lower()
                try:
                    raw_bytes = fpath.read_bytes() if (sanitize and ext in SANITIZABLE_BINARY_EXTENSIONS) else fpath.read_bytes()[:MAX_FILE_BYTES]
                    raw_digest = _sha256_bytes(raw_bytes)
                    chash = _sha256_str(f"{raw_digest}:{policy_sig}") if sanitize else raw_digest
                    if not full_reindex and prev and prev["status"] == "indexed" and prev["content_hash"] == chash:
                        if not dry_run:
                            conn.execute("UPDATE documents SET mtime = ?, indexed_at = ? WHERE doc_id = ?", (mtime, now, doc_id))
                        stats["unchanged"] += 1
                        stats["files_skipped"] += 1
                        mhash = _sha256_str(f"{rel}:{chash}")
                        merkle_entries.append(f"{rel}:{mhash}")
                        if progress_cb:
                            progress_cb({"processed": idx, "total": total, "rel_path": rel, "action": "unchanged"})
                        continue

                    parsed = self._parse_and_sanitize(
                        fpath=fpath, rel=rel, ext=ext, raw_bytes=raw_bytes, fsize=fsize,
                        sanitize=sanitize, privacy_profile=privacy_profile,
                        custom_terms=terms_clean, use_local_ner=use_local_ner,
                        folder_state=folder_state,
                    )
                except (OSError, FailClosedError, Exception) as exc:  # noqa: BLE001
                    stats["errors"] += 1
                    safe_err = f"{type(exc).__name__}" if sanitize else str(exc)
                    if not dry_run:
                        self._upsert_doc(
                            conn, doc_id=doc_id, root_id=rid, rel_path=rel, abs_path=str(fpath),
                            principal_id=pid, status="error", file_size=fsize, mtime=mtime,
                            content_hash="", merkle_hash=_sha256_str(f"{rel}:error"),
                            title=fpath.name, content="", chunks=[], warnings=[safe_err],
                            embedding_model=embedding_model, embedding_dim=embedding_dim, now=now,
                            sanitized=sanitize, privacy_profile=privacy_profile if sanitize else "raw",
                            privacy_namespace=privacy_namespace if sanitize else "",
                            policy_sig=policy_sig,
                        )
                    if progress_cb:
                        progress_cb({"processed": idx, "total": total, "rel_path": rel, "action": "error", "message": safe_err})
                    continue

                if parsed["unsupported"]:
                    stats["unsupported_binary"] += 1
                    stats["ignored"] += 1
                    mhash = _sha256_str(f"{rel}:unsupported:{chash}")
                    if not dry_run:
                        self._upsert_doc(
                            conn, doc_id=doc_id, root_id=rid, rel_path=rel, abs_path=str(fpath),
                            principal_id=pid, status="ignored", file_size=fsize, mtime=mtime,
                            content_hash=chash, merkle_hash=mhash, title=fpath.name, content="",
                            chunks=[], warnings=parsed["warnings"],
                            embedding_model=embedding_model, embedding_dim=embedding_dim, now=now,
                            sanitized=True, privacy_profile=privacy_profile,
                            privacy_namespace=privacy_namespace, policy_sig=policy_sig,
                        )
                    if progress_cb:
                        progress_cb({"processed": idx, "total": total, "rel_path": rel, "action": "ignored"})
                    continue

                text = parsed["text"]
                title = parsed["title"]
                mhash = _sha256_str(f"{rel}:{chash}")
                merkle_entries.append(f"{rel}:{mhash}")
                chunks = _chunk_text(text)

                if sanitize:
                    stats["files_sanitized"] += 1
                    stats["entities_masked_total"] += int(parsed["entities_masked"])
                    stats["metadata_stripped_count"] += len(parsed["stripped_meta"])
                    for cat, cnt in parsed["entities_by_cat"].items():
                        stats["entities_by_category"][cat] = stats["entities_by_category"].get(cat, 0) + int(cnt)
                    if not dry_run and vault_key is not None and parsed["pseudonym_map"]:
                        self._persist_pseudonym_mappings(conn, rid, vault_key, parsed["pseudonym_map"], now)

                if not dry_run:
                    self._upsert_doc(
                        conn, doc_id=doc_id, root_id=rid, rel_path=rel, abs_path=str(fpath),
                        principal_id=pid, status="indexed", file_size=fsize, mtime=mtime,
                        content_hash=chash, merkle_hash=mhash, title=title, content=text,
                        chunks=chunks, warnings=parsed["warnings"],
                        embedding_model=embedding_model, embedding_dim=embedding_dim, now=now,
                        sanitized=sanitize,
                        privacy_profile=privacy_profile if sanitize else "raw",
                        privacy_namespace=f"{privacy_namespace.rstrip('/')}/{rid}/{rel}" if sanitize else "",
                        policy_sig=policy_sig,
                        entities_masked=int(parsed["entities_masked"]),
                        entities_by_cat=parsed["entities_by_cat"],
                        stripped_meta=parsed["stripped_meta"],
                        summaries=parsed["summaries"],
                    )
                action = "modified" if prev else "added"
                stats[action] += 1
                if progress_cb:
                    progress_cb({
                        "processed": idx, "total": total, "rel_path": rel, "action": action,
                        "entities_masked": parsed["entities_masked"],
                    })

            if not dry_run:
                for rel, prev in existing.items():
                    if rel not in seen_paths:
                        conn.execute("DELETE FROM documents_fts WHERE doc_id = ?", (prev["doc_id"],))
                        conn.execute("DELETE FROM documents WHERE doc_id = ?", (prev["doc_id"],))
                        stats["removed"] += 1

                merkle_root = _sha256_str("\n".join(sorted(merkle_entries))) if merkle_entries else _sha256_str("empty")
                doc_cnt = conn.execute(
                    "SELECT COUNT(*) FROM documents WHERE root_id = ? AND status = 'indexed'", (rid,)
                ).fetchone()[0]
                chunk_cnt = conn.execute(
                    "SELECT COALESCE(SUM(chunk_count), 0) FROM documents WHERE root_id = ? AND status = 'indexed'", (rid,)
                ).fetchone()[0]
                final_status = "error" if (stats["errors"] > 0 and doc_cnt == 0) else "synced"
                conn.execute(
                    """
                    UPDATE roots
                    SET status = ?, last_crawl_at = ?, merkle_root_hash = ?, doc_count = ?, chunk_count = ?
                    WHERE root_id = ?
                    """,
                    (final_status, now, merkle_root, int(doc_cnt), int(chunk_cnt), rid),
                )
            else:
                merkle_root = _sha256_str("\n".join(sorted(merkle_entries))) if merkle_entries else _sha256_str("empty")
                stats["removed"] = sum(1 for rel in existing if rel not in seen_paths)
            stats["merkle_root_hash"] = merkle_root
        return stats

    def _extract_title(self, text: str, fallback: str) -> str:
        for line in text.splitlines()[:15]:
            s = line.strip()
            if s.startswith("# "):
                return s[2:].strip()[:120] or fallback
        return fallback

    def _upsert_doc(
        self,
        conn: sqlite3.Connection,
        *,
        doc_id: str,
        root_id: str,
        rel_path: str,
        abs_path: str,
        principal_id: str,
        status: str,
        file_size: int,
        mtime: float,
        content_hash: str,
        merkle_hash: str,
        title: str,
        content: str,
        chunks: list[dict[str, Any]],
        warnings: list[str],
        embedding_model: str,
        embedding_dim: int,
        now: float,
        sanitized: bool = False,
        privacy_profile: str = "raw",
        privacy_namespace: str = "",
        policy_sig: str = "raw",
        entities_masked: int = 0,
        entities_by_cat: Optional[dict[str, int]] = None,
        stripped_meta: Optional[list[str]] = None,
        summaries: Optional[dict[str, str]] = None,
    ) -> None:
        conn.execute(
            """
            INSERT INTO documents (
                doc_id, root_id, rel_path, abs_path, principal_id, status,
                file_size, mtime, content_hash, merkle_hash, title, content,
                chunk_count, warnings_json, sanitized, privacy_profile, privacy_namespace,
                policy_sig, entities_masked, entities_by_cat_json, stripped_meta_json,
                summaries_json, indexed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(doc_id) DO UPDATE SET
                status=excluded.status, file_size=excluded.file_size, mtime=excluded.mtime,
                content_hash=excluded.content_hash, merkle_hash=excluded.merkle_hash,
                title=excluded.title, content=excluded.content, chunk_count=excluded.chunk_count,
                warnings_json=excluded.warnings_json, sanitized=excluded.sanitized,
                privacy_profile=excluded.privacy_profile, privacy_namespace=excluded.privacy_namespace,
                policy_sig=excluded.policy_sig, entities_masked=excluded.entities_masked,
                entities_by_cat_json=excluded.entities_by_cat_json,
                stripped_meta_json=excluded.stripped_meta_json,
                summaries_json=excluded.summaries_json, indexed_at=excluded.indexed_at
            """,
            (
                doc_id, root_id, rel_path, abs_path, principal_id, status,
                file_size, mtime, content_hash, merkle_hash, title, content,
                len(chunks), json.dumps(warnings), 1 if sanitized else 0,
                privacy_profile, privacy_namespace, policy_sig, int(entities_masked),
                json.dumps(entities_by_cat or {}), json.dumps(stripped_meta or []),
                json.dumps(summaries or {}), now,
            ),
        )
        conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
        for ch in chunks:
            cid = f"{doc_id}_c{ch['chunk_index']}"
            conn.execute(
                """
                INSERT INTO chunks (chunk_id, doc_id, principal_id, chunk_index, char_start, char_end, token_est, text, embedding_model, embedding_dim)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (cid, doc_id, principal_id, ch["chunk_index"], ch["char_start"], ch["char_end"], ch["token_est"], ch["text"], embedding_model, embedding_dim),
            )
        conn.execute("DELETE FROM documents_fts WHERE doc_id = ?", (doc_id,))
        if status == "indexed":
            conn.execute(
                "INSERT INTO documents_fts (title, content, rel_path, principal_id, doc_id) VALUES (?, ?, ?, ?, ?)",
                (title, content, rel_path, principal_id, doc_id),
            )

    # ---- Navigation & File Inspection ----

    def navigate(
        self,
        *,
        principal_id: str = "local_owner",
        root_id: Optional[str] = None,
        status_filter: Optional[str] = None,
        privacy_filter: Optional[str] = None,
        search_path: str = "",
    ) -> dict[str, Any]:
        clause, params = self._rbac_clause(principal_id)
        where = [clause]
        qparams = list(params)
        if root_id:
            where.append("root_id = ?")
            qparams.append(root_id)
        if status_filter and status_filter != "all":
            where.append("status = ?")
            qparams.append(status_filter)
        if privacy_filter == "sanitized":
            where.append("sanitized = 1")
        elif privacy_filter == "raw":
            where.append("sanitized = 0")
        elif privacy_filter == "private_gated":
            where.append("(sanitized = 1 AND privacy_profile = 'max_security')")
        if search_path.strip():
            where.append("LOWER(rel_path) LIKE ?")
            qparams.append(f"%{search_path.strip().lower()}%")

        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT doc_id, root_id, rel_path, abs_path, principal_id, status,
                       file_size, mtime, content_hash, merkle_hash, title, chunk_count,
                       warnings_json, sanitized, privacy_profile, privacy_namespace,
                       entities_masked, entities_by_cat_json, stripped_meta_json, indexed_at
                FROM documents
                WHERE {' AND '.join(where)}
                ORDER BY rel_path ASC
                """,
                qparams,
            ).fetchall()

        files: list[dict[str, Any]] = []
        counts = {"indexed": 0, "modified": 0, "ignored": 0, "error": 0}
        priv_summary: dict[str, Any] = {
            "sanitized": 0,
            "raw": 0,
            "private_gated": 0,
            "entities_masked_total": 0,
            "entities_by_category": {},
        }
        for r in rows:
            d = dict(r)
            if d["status"] == "indexed" and d["abs_path"] and os.path.isfile(d["abs_path"]):
                try:
                    cur_m = os.path.getmtime(d["abs_path"])
                    if abs(cur_m - float(d["mtime"] or 0)) > 1.0:
                        d["status"] = "modified"
                except OSError:
                    pass
            for jkey, outkey, default in (
                ("warnings_json", "warnings", []),
                ("entities_by_cat_json", "entities_by_cat", {}),
                ("stripped_meta_json", "stripped_meta", []),
            ):
                try:
                    d[outkey] = json.loads(d.pop(jkey, "") or json.dumps(default))
                except Exception:  # noqa: BLE001
                    d[outkey] = default
            d["sanitized"] = bool(d.get("sanitized"))
            d["private_gated"] = d["sanitized"] and d.get("privacy_profile") == "max_security"
            counts[d["status"]] = counts.get(d["status"], 0) + 1
            if d["sanitized"]:
                priv_summary["sanitized"] += 1
            else:
                priv_summary["raw"] += 1
            if d["private_gated"]:
                priv_summary["private_gated"] += 1
            priv_summary["entities_masked_total"] += int(d.get("entities_masked") or 0)
            for cat, cnt in (d.get("entities_by_cat") or {}).items():
                priv_summary["entities_by_category"][cat] = priv_summary["entities_by_category"].get(cat, 0) + int(cnt)
            files.append(d)

        return {"files": files, "counts": counts, "privacy_summary": priv_summary, "total": len(files)}

    def inspect_file(self, doc_id: str, principal_id: str = "local_owner") -> Optional[dict[str, Any]]:
        clause, params = self._rbac_clause(principal_id)
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT * FROM documents WHERE doc_id = ? AND {clause}",
                [doc_id, *params],
            ).fetchone()
            if not row:
                return None
            d = dict(row)
            for jkey, outkey, default in (
                ("warnings_json", "warnings", []),
                ("entities_by_cat_json", "entities_by_cat", {}),
                ("stripped_meta_json", "stripped_meta", []),
                ("summaries_json", "summaries", {}),
            ):
                try:
                    d[outkey] = json.loads(d.pop(jkey, "") or json.dumps(default))
                except Exception:  # noqa: BLE001
                    d[outkey] = default
            d["sanitized"] = bool(d.get("sanitized"))
            d["private_gated"] = d["sanitized"] and d.get("privacy_profile") == "max_security"
            chunks = conn.execute(
                "SELECT chunk_id, chunk_index, char_start, char_end, token_est, embedding_model, embedding_dim, substr(text, 1, 240) AS preview FROM chunks WHERE doc_id = ? ORDER BY chunk_index ASC",
                (doc_id,),
            ).fetchall()
            d["chunks"] = [dict(c) for c in chunks]
            d["preview"] = (d.get("content") or "")[:6000]
            if not d["summaries"] and d["preview"]:
                d["summaries"] = _build_four_tier_summaries(d.get("content") or "", d.get("title") or "")
            return d

    # ---- FTS5 Search (`wiki_search`) ----

    def search(
        self,
        query: str,
        *,
        principal_id: str = "local_owner",
        limit: int = 10,
        depth: int = 1,
    ) -> list[dict[str, Any]]:
        q = str(query or "").strip()
        if not q:
            return []
        limit = max(1, min(100, int(limit)))
        clause, params = self._rbac_clause(principal_id, column="d.principal_id")
        results: list[dict[str, Any]] = []

        with self._connect() as conn:
            rows = []
            try:
                safe_q = " ".join(re.findall(r"[a-zA-Z0-9_]+", q))
                if safe_q:
                    rows = conn.execute(
                        f"""
                        SELECT d.doc_id, d.root_id, d.rel_path, d.principal_id, d.title, d.merkle_hash,
                               d.chunk_count, d.indexed_at, d.content,
                               snippet(documents_fts, 1, '[', ']', '...', 24) AS snip,
                               bm25(documents_fts) AS rank
                        FROM documents_fts
                        JOIN documents d ON d.doc_id = documents_fts.doc_id
                        WHERE documents_fts MATCH ? AND {clause}
                        ORDER BY rank ASC
                        LIMIT ?
                        """,
                        [safe_q, *params, limit],
                    ).fetchall()
            except sqlite3.OperationalError:
                rows = []

            if not rows:
                like_p = f"%{q.lower()}%"
                rows = conn.execute(
                    f"""
                    SELECT d.doc_id, d.root_id, d.rel_path, d.principal_id, d.title, d.merkle_hash,
                           d.chunk_count, d.indexed_at, d.content,
                           substr(d.content, 1, 260) AS snip,
                           0.0 AS rank
                    FROM documents d
                    WHERE d.status = 'indexed' AND (LOWER(d.content) LIKE ? OR LOWER(d.title) LIKE ? OR LOWER(d.rel_path) LIKE ?) AND {clause}
                    LIMIT ?
                    """,
                    [like_p, like_p, like_p, *params, limit],
                ).fetchall()

            for r in rows:
                item: dict[str, Any] = {
                    "doc_id": r["doc_id"],
                    "root_id": r["root_id"],
                    "rel_path": r["rel_path"],
                    "principal_id": r["principal_id"],
                    "title": r["title"],
                    "merkle_hash": r["merkle_hash"],
                    "chunk_count": r["chunk_count"],
                    "score": round(abs(float(r["rank"] or 0.0)), 4),
                }
                if depth >= 1:
                    item["snippet"] = r["snip"]
                if depth >= 2:
                    item["excerpt"] = (r["content"] or "")[:2000]
                results.append(item)
        return results

    # ---- Episodic Memory (`wiki_record_episode`) ----

    def record_episode(
        self,
        *,
        title: str,
        summary: str,
        principal_id: str = "local_owner",
        tags: Optional[list[str]] = None,
        source_refs: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        pid = _normalize_principal(principal_id)
        self.ensure_principal(pid)
        eid = "ep_" + uuid.uuid4().hex[:12]
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO episodes (episode_id, principal_id, title, summary, tags_json, source_refs_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (eid, pid, title.strip() or "Untitled Episode", summary.strip(), json.dumps(list(tags or [])), json.dumps(list(source_refs or [])), now),
            )
        return {
            "episode_id": eid,
            "principal_id": pid,
            "title": title.strip() or "Untitled Episode",
            "summary": summary.strip(),
            "tags": list(tags or []),
            "source_refs": list(source_refs or []),
            "created_at": now,
        }

    def list_episodes(
        self,
        *,
        principal_id: str = "local_owner",
        date_from: Optional[float] = None,
        date_to: Optional[float] = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        clause, params = self._rbac_clause(principal_id)
        where = [clause]
        qparams = list(params)
        if date_from is not None:
            where.append("created_at >= ?")
            qparams.append(float(date_from))
        if date_to is not None:
            where.append("created_at <= ?")
            qparams.append(float(date_to))
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM episodes WHERE {' AND '.join(where)} ORDER BY created_at DESC LIMIT ?",
                [*qparams, max(1, min(200, int(limit)))],
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["tags"] = json.loads(d.pop("tags_json", "[]") or "[]")
            d["source_refs"] = json.loads(d.pop("source_refs_json", "[]") or "[]")
            out.append(d)
        return out

    # ---- Citation Verifier (`wiki_verify_citation`) ----

    def verify_citation(
        self,
        claim: str,
        *,
        principal_id: str = "local_owner",
        doc_id: Optional[str] = None,
        threshold: float = 0.45,
    ) -> dict[str, Any]:
        text_claim = str(claim or "").strip()
        if not text_claim:
            return {"status": "not_found", "confidence": 0.0, "matches": [], "claim": text_claim}

        clause, params = self._rbac_clause(principal_id)
        where = ["status = 'indexed'", clause]
        qparams = list(params)
        if doc_id:
            where.append("doc_id = ?")
            qparams.append(doc_id)

        claim_lower = text_claim.lower()
        claim_tokens = _tokenize_for_citation(text_claim)
        matches: list[dict[str, Any]] = []

        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT doc_id, root_id, rel_path, principal_id, title, merkle_hash, content FROM documents WHERE {' AND '.join(where)}",
                qparams,
            ).fetchall()

        for r in rows:
            content = r["content"] or ""
            clower = content.lower()
            idx = clower.find(claim_lower)
            if idx != -1:
                start = max(0, idx - 80)
                end = min(len(content), idx + len(text_claim) + 120)
                matches.append({
                    "doc_id": r["doc_id"],
                    "root_id": r["root_id"],
                    "rel_path": r["rel_path"],
                    "principal_id": r["principal_id"],
                    "title": r["title"],
                    "merkle_hash": r["merkle_hash"],
                    "confidence": 1.0,
                    "match_type": "exact",
                    "char_offset": idx,
                    "snippet": content[start:end].strip(),
                })
                continue

            if not claim_tokens:
                continue
            doc_tokens = _tokenize_for_citation(content)
            overlap = claim_tokens & doc_tokens
            if not overlap:
                continue
            ratio = len(overlap) / max(1, len(claim_tokens))
            if ratio >= 0.25:
                # Find best window snippet around first matched token
                first_tok = sorted(overlap, key=len, reverse=True)[0]
                pos = clower.find(first_tok)
                start = max(0, pos - 80) if pos >= 0 else 0
                end = min(len(content), start + 260)
                matches.append({
                    "doc_id": r["doc_id"],
                    "root_id": r["root_id"],
                    "rel_path": r["rel_path"],
                    "principal_id": r["principal_id"],
                    "title": r["title"],
                    "merkle_hash": r["merkle_hash"],
                    "confidence": round(ratio, 3),
                    "match_type": "lexical_overlap",
                    "char_offset": max(0, pos),
                    "snippet": content[start:end].strip(),
                })

        matches.sort(key=lambda m: m["confidence"], reverse=True)
        best = matches[0]["confidence"] if matches else 0.0
        if best >= max(0.75, float(threshold)):
            status = "verified"
        elif best >= max(0.30, float(threshold) * 0.65):
            status = "partial"
        else:
            status = "not_found"

        return {
            "status": status,
            "confidence": round(best, 3),
            "threshold": float(threshold),
            "claim": text_claim,
            "matches": matches[:5],
        }

    # ---- Summary Stats ----

    def index_summary(self, principal_id: str = "local_owner") -> dict[str, Any]:
        roots = self.list_roots(principal_id=principal_id)
        nav = self.navigate(principal_id=principal_id)
        statuses = {r["status"] for r in roots}
        if not roots:
            overall = "empty"
        elif "syncing" in statuses:
            overall = "syncing"
        elif "error" in statuses:
            overall = "error"
        elif "changes_detected" in statuses or nav["counts"].get("modified", 0) > 0:
            overall = "changes_detected"
        else:
            overall = "synced"
        return {
            "status": overall,
            "root_count": len(roots),
            "doc_count": nav["counts"].get("indexed", 0),
            "modified_count": nav["counts"].get("modified", 0),
            "error_count": nav["counts"].get("error", 0),
            "chunk_count": sum(int(r.get("chunk_count") or 0) for r in roots),
        }
