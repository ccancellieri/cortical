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
            "macos": "brew install rtk-ai/tap/rtk",
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
