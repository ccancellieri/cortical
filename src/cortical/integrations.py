"""Zero-dependency IDE/Agent MCP auto-detection, idempotent `cortical integrate`, and `cortical doctor` diagnostics."""

from __future__ import annotations

import copy
import difflib
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any, Optional

from .workspace import (
    SYNC_IGNORE_TARGETS,
    discover_workspace_root,
    find_initialized_cortical_dir,
    resolve_default_db,
)

SUPPORTED_TARGETS: tuple[str, ...] = (
    "cursor",
    "claude",
    "vscode",
    "opencode",
    "windsurf",
    "cline",
    "zed",
    "antigravity",
    "pi",
)


def _vscode_global_mcp_path(home: Path) -> Path:
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "Code" / "User" / "mcp.json"
    if sys.platform.startswith("win"):
        appdata = Path(os.environ.get("APPDATA") or (home / "AppData" / "Roaming"))
        return appdata / "Code" / "User" / "mcp.json"
    return home / ".config" / "Code" / "User" / "mcp.json"


def resolve_target_paths(
    target: str,
    *,
    project_root: Optional[Path] = None,
    home_dir: Optional[Path] = None,
) -> dict[str, Optional[Path]]:
    """Returns `{'project': Path|None, 'global': Path|None}` config file paths for an IDE/agent."""
    proj = (project_root or discover_workspace_root() or Path.cwd()).resolve()
    home = (home_dir or Path.home()).resolve()
    t = target.strip().lower()
    mapping: dict[str, dict[str, Optional[Path]]] = {
        "cursor": {"project": proj / ".cursor" / "mcp.json", "global": home / ".cursor" / "mcp.json"},
        "claude": {"project": proj / ".mcp.json", "global": home / ".claude.json"},
        "vscode": {"project": proj / ".vscode" / "mcp.json", "global": _vscode_global_mcp_path(home)},
        "opencode": {"project": proj / "opencode.json", "global": home / ".config" / "opencode" / "config.json"},
        "windsurf": {"project": proj / ".windsurf" / "mcp.json", "global": home / ".codeium" / "windsurf" / "mcp_config.json"},
        "cline": {"project": proj / ".cline" / "mcp.json", "global": home / ".cline" / "data" / "settings" / "cline_mcp_settings.json"},
        "zed": {"project": proj / ".zed" / "settings.json", "global": home / ".config" / "zed" / "settings.json"},
        "antigravity": {"project": None, "global": home / ".gemini" / "config" / "mcp_config.json"},
        "pi": {"project": None, "global": home / ".pi" / "agent" / "mcp.json"},
    }
    if t not in mapping:
        raise ValueError(f"Unsupported integration target '{target}'. Supported: {', '.join(SUPPORTED_TARGETS)}")
    return mapping[t]


def detect_integrations(
    *,
    project_root: Optional[Path] = None,
    home_dir: Optional[Path] = None,
) -> list[dict[str, Any]]:
    """Auto-detects installed/configured IDEs and coding agents in the project and user home."""
    proj = (project_root or discover_workspace_root() or Path.cwd()).resolve()
    home = (home_dir or Path.home()).resolve()
    results: list[dict[str, Any]] = []
    for target in SUPPORTED_TARGETS:
        paths = resolve_target_paths(target, project_root=proj, home_dir=home)
        p_path, g_path = paths["project"], paths["global"]
        p_exists = bool(p_path and (p_path.is_file() or p_path.parent.is_dir() and p_path.parent != proj))
        g_exists = bool(g_path and (g_path.is_file() or (g_path.parent.is_dir() and g_path.parent != home)))
        detected = p_exists or g_exists or bool(shutil.which(target))
        results.append({
            "target": target,
            "detected": detected,
            "project_path": str(p_path) if p_path else None,
            "project_exists": bool(p_path and p_path.is_file()),
            "global_path": str(g_path) if g_path else None,
            "global_exists": bool(g_path and g_path.is_file()),
        })
    return results


def resolve_python_executable(repo_root: Optional[Path] = None) -> str:
    """Resolves absolute `.venv/bin/python` (preserving venv symlink) if present, else `sys.executable`."""
    root = (repo_root or Path(__file__).resolve().parents[2]).resolve()
    for rel in (".venv/bin/python", ".venv/Scripts/python.exe"):
        cand = root / rel
        if cand.is_file():
            return os.path.abspath(cand)
    return os.path.abspath(sys.executable)


def _build_mcp_entry(
    target: str,
    *,
    python_exe: str,
    src_dir: Path,
    db_path: Path,
    module_name: str = "cortical.mcp_server",
) -> dict[str, Any]:
    env = {
        "PYTHONPATH": str(src_dir.resolve()),
        "CORTICAL_VAULT_DB": str(db_path.resolve()),
    }
    args = ["-m", module_name] + (["--db", str(db_path.resolve())] if module_name == "cortical.wiki.mcp_server" else [])
    t = target.strip().lower()
    if t == "opencode":
        return {
            "type": "local",
            "command": [python_exe, *args],
            "environment": env,
            "enabled": True,
        }
    if t == "zed":
        return {
            "command": {
                "path": python_exe,
                "args": args,
                "env": env,
            }
        }
    entry: dict[str, Any] = {
        "command": python_exe,
        "args": args,
        "env": env,
    }
    if t == "vscode":
        entry["type"] = "stdio"
    elif t == "pi":
        entry["exposure"] = "deferred"
    return entry


def _container_key_for_target(target: str) -> str:
    t = target.strip().lower()
    if t == "vscode":
        return "servers"
    if t == "opencode":
        return "mcp"
    if t == "zed":
        return "context_servers"
    return "mcpServers"


def integrate_target(
    target: str,
    *,
    scope: str = "project",
    server_name: str = "cortical-mcp",
    wiki_server: bool = False,
    project_root: Optional[Path] = None,
    home_dir: Optional[Path] = None,
    repo_root: Optional[Path] = None,
    db_path: Optional[Path | str] = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Safely injects or updates `server_name` in the target IDE/agent JSON config with `.bak` backup."""
    proj = (project_root or discover_workspace_root() or Path.cwd()).resolve()
    home = (home_dir or Path.home()).resolve()
    code_root = (repo_root or Path(__file__).resolve().parents[2]).resolve()
    paths = resolve_target_paths(target, project_root=proj, home_dir=home)

    eff_scope = scope.strip().lower()
    if eff_scope not in {"project", "global"}:
        raise ValueError("scope must be 'project' or 'global'")
    cfg_path = paths[eff_scope]
    if cfg_path is None:
        eff_scope = "global" if paths["global"] is not None else "project"
        cfg_path = paths[eff_scope]
    assert cfg_path is not None

    eff_db = Path(db_path).expanduser().resolve() if db_path else resolve_default_db(None, start_dir=proj).resolve()
    py_exe = resolve_python_executable(code_root)
    src_dir = code_root / "src"
    module_name = "cortical.wiki.mcp_server" if wiki_server else "cortical.mcp_server"
    eff_server = "cortical-wiki" if (wiki_server and server_name == "cortical-mcp") else server_name

    old_text = cfg_path.read_text(encoding="utf-8") if cfg_path.is_file() else ""
    if old_text.strip():
        try:
            existing = json.loads(old_text)
            if not isinstance(existing, dict):
                raise ValueError(f"Expected JSON object in {cfg_path}")
        except json.JSONDecodeError as exc:
            return {"ok": False, "target": target, "path": str(cfg_path), "error": f"Invalid JSON in {cfg_path}: {exc}"}
    else:
        existing = {}

    updated = copy.deepcopy(existing)
    container_key = _container_key_for_target(target)
    container = dict(updated.get(container_key) or {})
    if not wiki_server and eff_server == "cortical-mcp":
        legacy = container.get("cortical-wiki")
        if isinstance(legacy, dict) and "cortical.mcp_server" in json.dumps(legacy):
            container.pop("cortical-wiki", None)
    container[eff_server] = _build_mcp_entry(target, python_exe=py_exe, src_dir=src_dir, db_path=eff_db, module_name=module_name)
    updated[container_key] = container
    new_text = json.dumps(updated, indent=2, ensure_ascii=False) + "\n"

    changed = old_text != new_text
    diff = "".join(
        difflib.unified_diff(
            old_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile=f"{cfg_path} (before)",
            tofile=f"{cfg_path} (after)",
        )
    )

    backup_path = ""
    if not dry_run and changed:
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        if cfg_path.is_file():
            bak = cfg_path.with_name(cfg_path.name + ".bak")
            shutil.copy2(cfg_path, bak)
            backup_path = str(bak)
        cfg_path.write_text(new_text, encoding="utf-8")

    return {
        "ok": True,
        "target": target.lower(),
        "scope": eff_scope,
        "server_name": eff_server,
        "path": str(cfg_path),
        "backup_path": backup_path,
        "changed": changed,
        "dry_run": dry_run,
        "python": py_exe,
        "db_path": str(eff_db),
        "diff": diff,
    }


def ping_mcp_stdio(
    *,
    python_exe: Optional[str] = None,
    src_dir: Optional[Path] = None,
    db_path: Optional[Path] = None,
    timeout_sec: float = 5.0,
) -> dict[str, Any]:
    """Sends a JSON-RPC 2.0 `initialize` request to `cortical.mcp_server` over stdio and validates response."""
    code_root = Path(__file__).resolve().parents[2]
    py = python_exe or resolve_python_executable(code_root)
    src = (src_dir or (code_root / "src")).resolve()
    env = {**os.environ, "PYTHONPATH": str(src)}
    if db_path is not None:
        env["CORTICAL_VAULT_DB"] = str(Path(db_path).resolve())

    req = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "cortical-doctor", "version": "0.3.0"}},
    }) + "\n"
    try:
        proc = subprocess.run(
            [py, "-m", "cortical.mcp_server"],
            input=req,
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout_sec,
            check=False,
        )
        for line in (proc.stdout or "").splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            payload = json.loads(line)
            if payload.get("id") == 1 and isinstance(payload.get("result"), dict):
                srv = (payload["result"].get("serverInfo") or {})
                return {"ok": True, "server_name": srv.get("name", "cortical-mcp"), "version": srv.get("version", "")}
        return {"ok": False, "error": (proc.stderr or proc.stdout or f"exit={proc.returncode}").strip()[:220]}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def _probe_http_ok(url: str, timeout: float = 0.8) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310
            return 200 <= int(getattr(resp, "status", 200)) < 400
    except Exception:
        return False


def run_doctor_diagnostics(
    *,
    project_root: Optional[Path] = None,
    home_dir: Optional[Path] = None,
    ping_mcp: bool = True,
) -> dict[str, Any]:
    """Runs zero-dependency health checks: Python, `.cortical/` writability, MCP stdio ping, ignores & runners."""
    proj = (project_root or discover_workspace_root() or Path.cwd()).resolve()
    c_dir = find_initialized_cortical_dir(proj)

    writable = False
    if c_dir is not None and c_dir.is_dir():
        probe_f = c_dir / ".write_probe"
        try:
            probe_f.write_text("ok", encoding="utf-8")
            probe_f.unlink(missing_ok=True)
            writable = True
        except OSError:
            writable = False

    ignore_files = {
        name: (proj / name).is_file()
        for name in (".corticalignore", *SYNC_IGNORE_TARGETS)
    }

    local_runners = {
        "ollama_api": _probe_http_ok("http://127.0.0.1:11434/api/tags", timeout=0.4),
        "litellm_router": _probe_http_ok("http://127.0.0.1:4000/v1/models", timeout=0.4),
        "unsloth_api": _probe_http_ok("http://127.0.0.1:8888/v1/models", timeout=0.35),
        "lm_studio_api": _probe_http_ok("http://127.0.0.1:1234/v1/models", timeout=0.35),
        "llama_cpp_mlx_api": _probe_http_ok("http://127.0.0.1:8080/v1/models", timeout=0.35),
        "vllm_api": _probe_http_ok("http://127.0.0.1:8000/v1/models", timeout=0.35),
        "rtk_bin": bool(shutil.which("rtk")),
        "serena_bin": bool(shutil.which("serena")),
    }

    detected = detect_integrations(project_root=proj, home_dir=home_dir)
    mcp_ping = ping_mcp_stdio() if ping_mcp else {"ok": True, "skipped": True}

    return {
        "tier1_zero_llm_stdlib": True,
        "python": {
            "version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "supported": sys.version_info >= (3, 10),
            "executable": sys.executable,
        },
        "workspace": {
            "project_root": str(proj),
            "cortical_dir": str(c_dir) if c_dir else None,
            "initialized": c_dir is not None,
            "writable": writable,
        },
        "mcp_stdio": mcp_ping,
        "ignore_files": ignore_files,
        "local_runners": local_runners,
        "detected_integrations": [d["target"] for d in detected if d["detected"]],
    }
