"""Registry, cross-platform status detection & HTTP launcher for composed OSS tools."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional


COMPOSED_TOOLS: dict[str, dict[str, Any]] = {
    "serena": {
        "role": "Semantic LSP code navigation & symbol-level editing (-60%..-85% code reads)",
        "binary": "serena",
        "install_cmd": {
            "macos": "uv tool install -p 3.13 --from git+https://github.com/oraios/serena serena-agent",
            "linux": "uv tool install -p 3.13 --from git+https://github.com/oraios/serena serena-agent",
            "windows": "uv tool install -p 3.13 --from git+https://github.com/oraios/serena serena-agent",
        },
        "replaces": "Duplicate source-code AST/grep file reads",
    },
    "rtk": {
        "role": "Sub-10 ms shell & test output compression (-60%..-90% terminal bloat)",
        "binary": "rtk",
        "install_cmd": {
            "macos": "brew install rtk",
            "linux": "cargo install rtk",
            "windows": "cargo install rtk",
        },
        "replaces": "Raw verbose git/pytest/unittest/ls/find dumps",
    },
    "pinchtab": {
        "role": "Lightweight accessibility-tree browser control (~800 tok/page vs 12k DOM)",
        "binary": "pinchtab",
        "install_cmd": {
            "macos": "brew install pinchtab/tap/pinchtab || npm i -g pinchtab",
            "linux": "npm i -g pinchtab",
            "windows": "npm i -g pinchtab",
        },
        "replaces": "Token-heavy screenshot & raw HTML browsing",
    },
    "playwright_mcp": {
        "role": "Fallback accessibility-snapshot browser MCP via npx",
        "binary": "npx",
        "install_cmd": {
            "macos": "npx -y @playwright/mcp@latest --help",
            "linux": "npx -y @playwright/mcp@latest --help",
            "windows": "npx -y @playwright/mcp@latest --help",
        },
        "replaces": "Visual pixel coordinate clicking",
    },
    "context_mode": {
        "role": "FTS5 sandboxing & compaction for oversized tool/CLI outputs",
        "binary": "npx",
        "install_cmd": {
            "macos": "npx -y context-mode --help",
            "linux": "npx -y context-mode --help",
            "windows": "npx -y context-mode --help",
        },
        "replaces": "Multi-megabyte gh/curl JSON outputs flooding context",
    },
    "http_router": {
        "role": "Optional OpenAI+Anthropic local HTTP router (LiteLLM / OmniRoute / CCR) for 70-90% API offload",
        "binary": "litellm",
        "install_cmd": {
            "macos": "pipx install 'litellm[proxy]' || npm i -g @musistudio/claude-code-router",
            "linux": "pipx install 'litellm[proxy]' || npm i -g @musistudio/claude-code-router",
            "windows": "pipx install litellm[proxy] || npm i -g @musistudio/claude-code-router",
        },
        "replaces": "Unconditional frontier cloud routing on easy turns",
    },
}


def inspect_composed_tools(os_name: Optional[str] = None) -> dict[str, dict[str, Any]]:
    """Checks which composed best-of-breed OSS binaries are installed across macOS/Linux/Windows."""
    target_os = (os_name or sys.platform).lower()
    norm_os = "macos" if ("darwin" in target_os or "mac" in target_os) else ("windows" if "win" in target_os else "linux")
    out: dict[str, dict[str, Any]] = {}
    for key, spec in COMPOSED_TOOLS.items():
        bname = spec["binary"]
        found = shutil.which(bname) or ""
        out[key] = {
            "name": key,
            "role": spec["role"],
            "binary": bname,
            "installed": bool(found),
            "path": found,
            "install_cmd": spec["install_cmd"][norm_os],
        }
    return out


def build_serve_mcp_command(
    tool: str,
    project_dir: Path | str,
    *,
    port: int = 9121,
    host: str = "127.0.0.1",
) -> list[str]:
    """Builds a cross-platform Streamable-HTTP MCP command for desktop GUIs like Unsloth Studio or DSH."""
    t = tool.strip().lower()
    proj = str(Path(project_dir).resolve())
    if t == "serena":
        exe = shutil.which("serena") or "serena"
        return [
            exe,
            "start-mcp-server",
            "--context",
            "oaicompat-agent",
            "--agent-interface",
            "tools",
            "--transport",
            "streamable-http",
            "--host",
            host,
            "--port",
            str(port),
            "--project",
            proj,
            "--enable-web-dashboard",
            "false",
            "--open-web-dashboard",
            "false",
        ]
    if t == "cortical":
        return [
            sys.executable,
            "-m",
            "cortical.mcp_server",
            "--transport",
            "streamable-http",
            "--host",
            host,
            "--port",
            str(port),
        ]
    raise ValueError(f"Unsupported HTTP MCP target tool: {tool}")


def serve_mcp_http(
    tool: str,
    project_dir: Path | str,
    *,
    port: int = 9121,
    host: str = "127.0.0.1",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Starts the cross-platform Streamable-HTTP MCP bridge in the foreground (Zero-Server by default)."""
    cmd = build_serve_mcp_command(tool, project_dir, port=port, host=host)
    url = f"http://{host}:{port}/mcp"
    if dry_run:
        return {"ok": True, "dry_run": True, "tool": tool, "url": url, "command": cmd}
    proc = subprocess.run(cmd, check=False)
    return {"ok": proc.returncode == 0, "dry_run": False, "tool": tool, "url": url, "returncode": proc.returncode}


def _norm_os_name(os_name: Optional[str] = None) -> str:
    target_os = (os_name or sys.platform).lower()
    if "darwin" in target_os or "mac" in target_os:
        return "macos"
    if "win" in target_os:
        return "windows"
    return "linux"


def test_composed_tool(name: str, os_name: Optional[str] = None) -> dict[str, Any]:
    """Tests whether a composed OSS tool/service is installed and responds cleanly."""
    key = "http_router" if name in {"router", "litellm"} else name
    if key not in COMPOSED_TOOLS:
        return {"ok": False, "name": name, "installed": False, "error": f"Unknown tool: {name}"}

    if key == "http_router":
        from .router import resolve_router_bin, router_status

        st = router_status()
        rbin = st.get("bin") or resolve_router_bin() or ""
        return {
            "ok": bool(rbin),
            "name": key,
            "installed": bool(rbin),
            "healthy": bool(st.get("healthy")),
            "url": st.get("url"),
            "path": rbin,
            "output": f"litellm={rbin or 'missing'} healthy={st.get('healthy')}",
            "error": "" if rbin else "LiteLLM router not installed",
        }

    spec = COMPOSED_TOOLS[key]
    bname = spec["binary"]
    found = shutil.which(bname) or ""
    if not found:
        norm = _norm_os_name(os_name)
        return {
            "ok": False,
            "name": key,
            "installed": False,
            "path": "",
            "install_cmd": spec["install_cmd"][norm],
            "output": "",
            "error": f"Binary '{bname}' not found on PATH",
        }

    check_args = [found, "--version"] if key in {"rtk", "pinchtab", "playwright_mcp", "context_mode"} else [found, "--help"]
    try:
        res = subprocess.run(check_args, capture_output=True, text=True, timeout=8, check=False)
        out = (res.stdout or res.stderr or "").strip().splitlines()
        summary = " | ".join(out[:2])[:220]
        return {
            "ok": res.returncode == 0,
            "name": key,
            "installed": True,
            "path": found,
            "output": summary or "ready",
            "error": "" if res.returncode == 0 else f"exit={res.returncode}",
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "name": key, "installed": True, "path": found, "output": "", "error": str(exc)}


def install_composed_tool(name: str, os_name: Optional[str] = None) -> dict[str, Any]:
    """Installs a composed OSS tool/service using the host OS package manager."""
    key = "http_router" if name in {"router", "litellm"} else name
    if key not in COMPOSED_TOOLS:
        return {"ok": False, "name": name, "installed": False, "error": f"Unknown tool: {name}"}

    if key == "http_router":
        from .router import ensure_litellm_installed

        res = ensure_litellm_installed()
        st = test_composed_tool(key, os_name=os_name)
        return {**st, "ok": bool(res.get("ok")), "output": str(res.get("bin") or st.get("output") or ""), "error": str(res.get("error") or "")}

    norm = _norm_os_name(os_name)
    cmd = COMPOSED_TOOLS[key]["install_cmd"][norm]
    if key == "rtk":
        cmd = f"{cmd} && (rtk telemetry disable || true) && (rtk init -g --auto-patch || true) && (rtk init -g --agent pi --auto-patch || true)"
    try:
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=180, check=False)  # noqa: S602
        st = test_composed_tool(key, os_name=os_name)
        tail = "\n".join(((proc.stdout or "") + "\n" + (proc.stderr or "")).strip().splitlines()[-8:])
        return {
            "ok": proc.returncode == 0 and bool(st.get("installed")),
            "name": key,
            "command": cmd,
            "installed": bool(st.get("installed")),
            "path": st.get("path", ""),
            "output": st.get("output") or tail[:300],
            "error": "" if proc.returncode == 0 else (tail[-300:] or f"exit={proc.returncode}"),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "name": key, "command": cmd, "installed": False, "error": str(exc)}
