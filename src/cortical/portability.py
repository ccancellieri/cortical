"""Portable USB / Cross-Machine Export & Import for Cortical Second Brain, Tasks & Skills.

Packages:
- SQLite knowledge/memory/task DB (`wiki.db`) via consistent hot backup (`sqlite3.Connection.backup`)
- Adaptive permissions DB (`permissions.db`) if present
- Chrome session preference (`~/.cortical_data/chrome_profile.json`)
- Custom & learned skills (`.agents/skills/`)
- Local `.memory/` notes (`decisions.md`, `scratchpad.md`) when present
"""

from __future__ import annotations

import datetime
import hashlib
import io
import json
import os
import platform
import shutil
import sqlite3
import tarfile
import tempfile
from pathlib import Path
from typing import Any, Optional


BUNDLE_SCHEMA_VERSION = "1.0"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sqlite_hot_backup_bytes(db_path: Path) -> Optional[bytes]:
    if not db_path.exists() or db_path.stat().st_size == 0:
        return None
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        src = sqlite3.connect(str(db_path))
        dst = sqlite3.connect(str(tmp_path))
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        return tmp_path.read_bytes()
    finally:
        tmp_path.unlink(missing_ok=True)


def list_usb_volumes() -> list[dict[str, str]]:
    """Lists mounted removable/external volumes suitable for USB export/import."""
    volumes: list[dict[str, str]] = []
    candidates: list[Path] = []
    sys_name = platform.system()
    if sys_name == "Darwin":
        vol_root = Path("/Volumes")
        if vol_root.exists():
            candidates = sorted(p for p in vol_root.iterdir() if p.is_dir() and p.name != "Macintosh HD")
    elif sys_name == "Linux":
        for root in (Path("/media"), Path("/mnt"), Path("/run/media")):
            if root.exists():
                for child in sorted(root.iterdir()):
                    if child.is_dir():
                        candidates.append(child)
    for vol in candidates:
        try:
            if os.access(vol, os.W_OK | os.R_OK):
                volumes.append({"name": vol.name, "path": str(vol)})
        except OSError:
            continue
    return volumes


def _collect_wiki_counts(db_path: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    if not db_path.exists() or db_path.stat().st_size == 0:
        return counts
    conn = sqlite3.connect(str(db_path))
    try:
        for table in ("task_episodes", "merkle_nodes", "macro_edges", "chat_threads", "chat_buffer", "learned_skills_registry", "agent_runs"):
            try:
                row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()  # noqa: S608
                counts[table] = int(row[0]) if row else 0
            except sqlite3.OperationalError:
                continue
    finally:
        conn.close()
    return counts


def _add_bytes_to_tar(tf: tarfile.TarFile, arcname: str, payload: bytes, checksums: dict[str, str]) -> None:
    info = tarfile.TarInfo(name=arcname)
    info.size = len(payload)
    info.mtime = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
    info.mode = 0o644
    tf.addfile(info, io.BytesIO(payload))
    checksums[arcname] = _sha256_bytes(payload)


def export_cortical_bundle(
    output_path: Optional[str | Path] = None,
    *,
    wiki_db_path: Optional[str | Path] = None,
    permissions_db_path: Optional[str | Path] = None,
    skills_dir: Optional[str | Path] = None,
    memory_dir: Optional[str | Path] = None,
    chrome_profile_path: Optional[str | Path] = None,
) -> dict[str, Any]:
    """Exports Cortical memory, tasks, chats, skills, and config into a portable .tar.gz bundle."""
    wiki_path = Path(wiki_db_path or os.environ.get("CORTICAL_WIKI_DB") or ".cortical_data/wiki.db").expanduser().resolve()
    data_dir = wiki_path.parent
    perm_path = Path(permissions_db_path or (data_dir / "permissions.db")).expanduser().resolve()
    skills_root = Path(skills_dir or ".agents/skills").expanduser().resolve()
    mem_root = Path(memory_dir or ".memory").expanduser().resolve()
    chrome_cfg = Path(chrome_profile_path or (Path.home() / ".cortical_data" / "chrome_profile.json")).expanduser().resolve()

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    default_name = f"cortical-backup-{stamp}.tar.gz"
    if output_path:
        target = Path(output_path).expanduser().resolve()
        if target.is_dir():
            target = target / default_name
    else:
        target = (data_dir / "backups" / default_name).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    checksums: dict[str, str] = {}
    counts = _collect_wiki_counts(wiki_path)
    skill_count = 0

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        wiki_bytes = _sqlite_hot_backup_bytes(wiki_path)
        if wiki_bytes is not None:
            _add_bytes_to_tar(tf, "data/wiki.db", wiki_bytes, checksums)

        perm_bytes = _sqlite_hot_backup_bytes(perm_path)
        if perm_bytes is not None:
            _add_bytes_to_tar(tf, "data/permissions.db", perm_bytes, checksums)

        if chrome_cfg.exists() and chrome_cfg.is_file():
            _add_bytes_to_tar(tf, "data/chrome_profile.json", chrome_cfg.read_bytes(), checksums)

        if skills_root.exists() and skills_root.is_dir():
            for file_path in sorted(skills_root.rglob("*")):
                if file_path.is_file() and "__pycache__" not in file_path.parts:
                    rel = file_path.relative_to(skills_root).as_posix()
                    _add_bytes_to_tar(tf, f"skills/{rel}", file_path.read_bytes(), checksums)
                    if file_path.name == "SKILL.md":
                        skill_count += 1

        if mem_root.exists() and mem_root.is_dir():
            for fname in ("decisions.md", "scratchpad.md"):
                fpath = mem_root / fname
                if fpath.exists() and fpath.is_file():
                    _add_bytes_to_tar(tf, f"memory/{fname}", fpath.read_bytes(), checksums)

        manifest = {
            "schema_version": BUNDLE_SCHEMA_VERSION,
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "source_host": platform.node(),
            "source_os": platform.system(),
            "counts": {**counts, "skills_files": skill_count},
            "checksums": checksums,
        }
        manifest_bytes = (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
        info = tarfile.TarInfo(name="manifest.json")
        info.size = len(manifest_bytes)
        info.mode = 0o644
        tf.addfile(info, io.BytesIO(manifest_bytes))

    archive_bytes = buf.getvalue()
    target.write_bytes(archive_bytes)
    return {
        "ok": True,
        "archive_path": str(target),
        "size_bytes": len(archive_bytes),
        "counts": {**counts, "skills": skill_count},
        "files_archived": len(checksums),
    }


def _merge_sqlite_dbs(src_db: Path, dst_db: Path) -> dict[str, int]:
    """Merges rows from imported SQLite DB into existing destination DB without dropping local rows."""
    if not dst_db.exists() or dst_db.stat().st_size == 0:
        dst_db.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_db, dst_db)
        return {"copied_fresh": 1}

    merged_tables: dict[str, int] = {}
    dst = sqlite3.connect(str(dst_db))
    src = sqlite3.connect(str(src_db))
    try:
        src_tables = {
            row[0]
            for row in src.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '%_fts%'").fetchall()
        }
        dst_tables = {
            row[0]
            for row in dst.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '%_fts%'").fetchall()
        }
        dst.execute("ATTACH DATABASE ? AS import_src", (str(src_db),))
        for table in sorted(src_tables & dst_tables):
            dst_cols = [r[1] for r in dst.execute(f"PRAGMA table_info({table})").fetchall()]
            src_cols = [r[1] for r in src.execute(f"PRAGMA table_info({table})").fetchall()]
            common_cols = [c for c in dst_cols if c in src_cols]
            if not common_cols:
                continue
            cols_sql = ", ".join(f'"{c}"' for c in common_cols)
            before = dst.total_changes
            dst.execute(f'INSERT OR IGNORE INTO "{table}" ({cols_sql}) SELECT {cols_sql} FROM import_src."{table}"')  # noqa: S608
            merged_tables[table] = dst.total_changes - before
        dst.commit()
    finally:
        try:
            dst.execute("DETACH DATABASE import_src")
        except sqlite3.Error:
            pass
        src.close()
        dst.close()
    return merged_tables


def import_cortical_bundle(
    archive_path: str | Path,
    *,
    mode: str = "merge",
    wiki_db_path: Optional[str | Path] = None,
    permissions_db_path: Optional[str | Path] = None,
    skills_dir: Optional[str | Path] = None,
    memory_dir: Optional[str | Path] = None,
    chrome_profile_path: Optional[str | Path] = None,
) -> dict[str, Any]:
    """Imports a portable Cortical .tar.gz bundle onto the current machine."""
    src_archive = Path(archive_path).expanduser().resolve()
    if not src_archive.exists():
        return {"ok": False, "error": f"archive_not_found:{src_archive}"}

    norm_mode = "replace" if str(mode).strip().lower() == "replace" else "merge"
    wiki_path = Path(wiki_db_path or os.environ.get("CORTICAL_WIKI_DB") or ".cortical_data/wiki.db").expanduser().resolve()
    data_dir = wiki_path.parent
    perm_path = Path(permissions_db_path or (data_dir / "permissions.db")).expanduser().resolve()
    skills_root = Path(skills_dir or ".agents/skills").expanduser().resolve()
    mem_root = Path(memory_dir or ".memory").expanduser().resolve()
    chrome_cfg = Path(chrome_profile_path or (Path.home() / ".cortical_data" / "chrome_profile.json")).expanduser().resolve()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_root = Path(tmpdir)
        with tarfile.open(src_archive, mode="r:gz") as tf:
            members = tf.getmembers()
            for member in members:
                if member.name.startswith("/") or ".." in Path(member.name).parts:
                    return {"ok": False, "error": f"unsafe_archive_entry:{member.name}"}
            tf.extractall(tmp_root, filter="data")

        manifest_file = tmp_root / "manifest.json"
        if not manifest_file.exists():
            return {"ok": False, "error": "invalid_bundle_missing_manifest"}
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        checksums = manifest.get("checksums") or {}
        for rel_name, expected_hash in checksums.items():
            extracted = tmp_root / rel_name
            if not extracted.exists() or _sha256_bytes(extracted.read_bytes()) != expected_hash:
                return {"ok": False, "error": f"checksum_mismatch:{rel_name}"}

        restored: dict[str, Any] = {"skills_restored": 0, "memory_files": 0, "db_mode": norm_mode}

        # 1. Restore SQLite wiki.db
        imp_wiki = tmp_root / "data" / "wiki.db"
        if imp_wiki.exists():
            if norm_mode == "replace":
                wiki_path.parent.mkdir(parents=True, exist_ok=True)
                if wiki_path.exists():
                    shutil.copy2(wiki_path, wiki_path.with_suffix(".db.bak"))
                shutil.copy2(imp_wiki, wiki_path)
                restored["wiki_db"] = "replaced"
            else:
                restored["wiki_merged_rows"] = _merge_sqlite_dbs(imp_wiki, wiki_path)

        # 2. Restore permissions.db
        imp_perm = tmp_root / "data" / "permissions.db"
        if imp_perm.exists():
            if norm_mode == "replace":
                perm_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(imp_perm, perm_path)
                restored["permissions_db"] = "replaced"
            else:
                restored["permissions_merged_rows"] = _merge_sqlite_dbs(imp_perm, perm_path)

        # 3. Restore skills
        imp_skills = tmp_root / "skills"
        if imp_skills.exists():
            skills_root.mkdir(parents=True, exist_ok=True)
            for fpath in sorted(imp_skills.rglob("*")):
                if fpath.is_file():
                    rel = fpath.relative_to(imp_skills)
                    dest = skills_root / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    if norm_mode == "replace" or not dest.exists():
                        shutil.copy2(fpath, dest)
                        if fpath.name == "SKILL.md":
                            restored["skills_restored"] += 1

        # 4. Restore .memory files
        imp_mem = tmp_root / "memory"
        if imp_mem.exists():
            mem_root.mkdir(parents=True, exist_ok=True)
            for fpath in sorted(imp_mem.iterdir()):
                if fpath.is_file():
                    dest = mem_root / fpath.name
                    if norm_mode == "replace" or not dest.exists():
                        shutil.copy2(fpath, dest)
                        restored["memory_files"] += 1

        # 5. Restore chrome_profile.json if missing or replace mode
        imp_chrome = tmp_root / "data" / "chrome_profile.json"
        if imp_chrome.exists() and (norm_mode == "replace" or not chrome_cfg.exists()):
            chrome_cfg.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(imp_chrome, chrome_cfg)
            restored["chrome_profile_restored"] = True

        return {
            "ok": True,
            "mode": norm_mode,
            "source_host": manifest.get("source_host", ""),
            "created_at": manifest.get("created_at", ""),
            "restored": restored,
        }
