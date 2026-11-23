"""Zero-dependency Workspace Auto-Discovery (`.cortical/`) and `cortical init` engine (Python 3.10+ stdlib)."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Optional

from .config import DEFAULT_CONFIG, DEFAULT_VAULT_DB

CORTICAL_DIRNAME = ".cortical"
IGNORE_START = "# CORTICAL:START"
IGNORE_END = "# CORTICAL:END"
SYNC_IGNORE_TARGETS: tuple[str, ...] = (".claudeignore", ".cursorignore", ".geminiignore")

DEFAULT_CORTICALIGNORE_RULES: tuple[str, ...] = (
    "# Cortical local workspace, private vault, secrets & heavy artifacts",
    ".cortical/",
    ".cortical_data/",
    ".venv/",
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*secret*",
    "*credentials*",
)


def _walk_up(start_dir: Optional[Path | str] = None) -> list[Path]:
    base = Path(start_dir).expanduser().resolve() if start_dir is not None else Path.cwd().resolve()
    if base.is_file():
        base = base.parent
    return [base, *base.parents]


def find_initialized_cortical_dir(start_dir: Optional[Path | str] = None) -> Optional[Path]:
    """Walks upward (Git-style) looking for `.cortical/`, stopping at a `.git` boundary or `$HOME`."""
    home = Path.home().resolve()
    for d in _walk_up(start_dir):
        cand = d / CORTICAL_DIRNAME
        if cand.is_dir() and d != home:
            return cand
        if (d / ".git").exists():
            return cand if cand.is_dir() else None
    return None


def discover_workspace_root(start_dir: Optional[Path | str] = None) -> Optional[Path]:
    """Walks upward looking for the nearest `.cortical/` or `.git` boundary (ignoring global `~/.cortical`)."""
    home = Path.home().resolve()
    for d in _walk_up(start_dir):
        if (d / CORTICAL_DIRNAME).is_dir() and d != home:
            return d
        if (d / ".git").exists():
            return d
    return None


def resolve_workspace_paths(root: Path | str) -> dict[str, Path]:
    """Returns canonical paths under `<project_root>/.cortical/`."""
    proj = Path(root).expanduser().resolve()
    cdir = proj / CORTICAL_DIRNAME
    return {
        "root": proj,
        "cortical_dir": cdir,
        "db_path": cdir / "wiki.db",
        "config_json": cdir / "config.json",
        "config_toml": cdir / "config.toml",
        "exports_dir": cdir / "exports",
        "logs_dir": cdir / "logs",
        "ignore_file": proj / ".corticalignore",
        "gitignore": proj / ".gitignore",
    }


def resolve_default_db(
    explicit_db: Optional[str | Path] = None,
    *,
    start_dir: Optional[Path | str] = None,
) -> Path:
    """Resolves SQLite DB path: `--db` > `$CORTICAL_VAULT_DB` > `<workspace>/.cortical/wiki.db` > `DEFAULT_VAULT_DB`."""
    if explicit_db:
        return Path(explicit_db).expanduser()
    env_db = os.environ.get("CORTICAL_VAULT_DB")
    if env_db:
        return Path(env_db).expanduser()
    c_dir = find_initialized_cortical_dir(start_dir)
    if c_dir is not None:
        return c_dir / "wiki.db"
    return Path(DEFAULT_VAULT_DB)


def resolve_default_export_dir(
    explicit_out: Optional[str | Path] = None,
    *,
    start_dir: Optional[Path | str] = None,
) -> Path:
    """Resolves dashboard/report export dir: `--out-dir` > `<workspace>/.cortical/exports` > `html`."""
    if explicit_out:
        return Path(explicit_out).expanduser()
    c_dir = find_initialized_cortical_dir(start_dir)
    if c_dir is not None:
        return c_dir / "exports"
    return Path("html")


def read_workspace_config(cortical_dir: Path) -> dict[str, Any]:
    """Reads `.cortical/config.toml` (Python 3.11+ `tomllib`) or `.cortical/config.json`."""
    toml_p = cortical_dir / "config.toml"
    if toml_p.is_file() and sys.version_info >= (3, 11):
        import tomllib

        try:
            data = tomllib.loads(toml_p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:  # noqa: BLE001
            pass
    json_p = cortical_dir / "config.json"
    if json_p.is_file():
        try:
            data = json.loads(json_p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:  # noqa: BLE001
            pass
    return {}


def _ensure_gitignore_entry(gitignore_path: Path, entry: str = ".cortical/") -> bool:
    """Idempotently appends `entry` to `.gitignore`. Returns True if modified."""
    existing = gitignore_path.read_text(encoding="utf-8") if gitignore_path.is_file() else ""
    lines = [ln.strip() for ln in existing.splitlines()]
    if entry in lines or entry.rstrip("/") in lines:
        return False
    sep = "" if (not existing or existing.endswith("\n")) else "\n"
    block = f"{sep}# Cortical local workspace (auto-added by `cortical init`)\n{entry}\n"
    gitignore_path.write_text(existing + block, encoding="utf-8")
    return True


def _upsert_ignore_block(existing: str, rules_text: str) -> str:
    block = f"{IGNORE_START}\n{rules_text.strip()}\n{IGNORE_END}\n"
    if IGNORE_START in existing and IGNORE_END in existing:
        pre, rest = existing.split(IGNORE_START, 1)
        _, post = rest.split(IGNORE_END, 1)
        return pre + block + post.lstrip("\n")
    sep = "" if (not existing or existing.endswith("\n")) else "\n"
    return existing + sep + ("\n" if existing.strip() else "") + block


def _init_wiki_db(db_path: Path) -> None:
    """Initializes `<root>/.cortical/wiki.db` with WAL mode and FTS5-ready metadata table."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path), timeout=5.0) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS workspace_meta (
                   key TEXT PRIMARY KEY,
                   value TEXT NOT NULL
               )"""
        )
        conn.execute("INSERT OR IGNORE INTO workspace_meta(key, value) VALUES ('schema_version', '1')")
        try:
            conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS wiki_fts USING fts5(doc_id, title, body)")
        except sqlite3.OperationalError:
            pass


def init_workspace(
    target_dir: Optional[Path | str] = None,
    *,
    update_gitignore: bool = True,
    sync_ignores: bool = True,
) -> dict[str, Any]:
    """Initializes `.cortical/` workspace, `wiki.db`, `config.json`, `.gitignore` and ignore-file sync."""
    if target_dir is not None:
        root = Path(target_dir).expanduser().resolve()
    else:
        root = discover_workspace_root() or Path.cwd().resolve()

    paths = resolve_workspace_paths(root)
    paths["cortical_dir"].mkdir(parents=True, exist_ok=True)
    paths["exports_dir"].mkdir(parents=True, exist_ok=True)
    paths["logs_dir"].mkdir(parents=True, exist_ok=True)

    _init_wiki_db(paths["db_path"])

    config_created = False
    if not paths["config_json"].exists() and not paths["config_toml"].exists():
        ws_cfg = {
            "workspace_root": str(root),
            "db_path": ".cortical/wiki.db",
            "exports_dir": ".cortical/exports",
            "logs_dir": ".cortical/logs",
            "active_runner": DEFAULT_CONFIG["active_runner"],
            "models_by_role": DEFAULT_CONFIG["models_by_role"],
            "router": DEFAULT_CONFIG["router"],
        }
        paths["config_json"].write_text(json.dumps(ws_cfg, indent=2) + "\n", encoding="utf-8")
        config_created = True

    gitignore_updated = False
    if update_gitignore:
        gitignore_updated = _ensure_gitignore_entry(paths["gitignore"], ".cortical/")

    ignore_file = paths["ignore_file"]
    ignore_created = False
    if not ignore_file.exists():
        ignore_file.write_text("\n".join(DEFAULT_CORTICALIGNORE_RULES) + "\n", encoding="utf-8")
        ignore_created = True

    synced_ignores: list[str] = []
    if sync_ignores:
        rules_body = "\n".join(
            ln for ln in ignore_file.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        )
        for fname in SYNC_IGNORE_TARGETS:
            tp = root / fname
            old = tp.read_text(encoding="utf-8") if tp.is_file() else ""
            new = _upsert_ignore_block(old, rules_body)
            if new != old:
                tp.write_text(new, encoding="utf-8")
                synced_ignores.append(fname)

    return {
        "ok": True,
        "root": str(root),
        "cortical_dir": str(paths["cortical_dir"]),
        "db_path": str(paths["db_path"]),
        "config_path": str(paths["config_toml"] if paths["config_toml"].exists() else paths["config_json"]),
        "config_created": config_created,
        "exports_dir": str(paths["exports_dir"]),
        "logs_dir": str(paths["logs_dir"]),
        "gitignore_updated": gitignore_updated,
        "corticalignore_created": ignore_created,
        "synced_ignores": synced_ignores,
    }
