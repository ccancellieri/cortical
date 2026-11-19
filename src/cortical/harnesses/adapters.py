"""8-Harness Declarative Config Sync (`Antigravity`, `pi`, `OpenCode`, `OpenClaw`, `Codex`, `Claude Code`, `dsh`, `Unsloth Studio`).

Cross-platform (`macOS`, `Linux`, `Windows`) with idempotent config merges, Schema Diet,
timestamped backups before write, `--dry-run`, and clean `--rollback`.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Optional

from ..privacy.vault import VERIFIED_PRESEND_HARNESSES

ALL_HARNESSES: tuple[str, ...] = (
    "antigravity",
    "pi",
    "opencode",
    "openclaw",
    "codex",
    "claude-code",
    "dsh",
    "unsloth-studio",
)


def get_harness_presend_matrix() -> dict[str, bool]:
    """Reports which harnesses guarantee 100% pre-send attachment interception."""
    return {h: (h in VERIFIED_PRESEND_HARNESSES) for h in ALL_HARNESSES}


@dataclasses.dataclass
class FileChange:
    """Represents a planned idempotent config or shared-rules update for one harness."""

    harness: str
    path: Path
    content: str
    kind: str  # json | toml | yaml | markdown
    action: str  # create | update | unchanged
    detail: str = ""


def resolve_user_paths(
    os_name: Optional[str] = None,
    home: Optional[Path] = None,
    appdata: Optional[Path] = None,
    xdg_config: Optional[Path] = None,
) -> dict[str, dict[str, Path]]:
    """Resolves canonical per-harness config paths across macOS, Linux, and Windows."""
    t_os = (os_name or sys.platform).lower()
    is_win = "win" in t_os and "darwin" not in t_os
    h = Path(home or Path.home())
    win_app = Path(appdata or os.environ.get("APPDATA") or (h / "AppData" / "Roaming"))
    xdg = Path(xdg_config or os.environ.get("XDG_CONFIG_HOME") or (h / ".config"))
    cfg_root = win_app if is_win else xdg

    return {
        "antigravity": {
            "mcp": h / ".gemini" / "config" / "mcp_config.json",
            "rules": h / ".gemini" / "GEMINI.md",
        },
        "pi": {
            "mcp": h / ".pi" / "agent" / "mcp.json",
            "settings": h / ".pi" / "agent" / "settings.json",
            "models": h / ".pi" / "agent" / "models.json",
            "rules": h / ".pi" / "agent" / "AGENTS.md",
        },
        "opencode": {
            "config": cfg_root / "opencode" / "config.json",
            "opencode": cfg_root / "opencode" / "opencode.json",
            "rules": cfg_root / "opencode" / "AGENTS.md",
        },
        "openclaw": {
            "config": h / ".openclaw" / "openclaw.json",
            "rules": h / ".openclaw" / "AGENTS.md",
        },
        "codex": {
            "config": h / ".codex" / "config.toml",
            "rules": h / ".codex" / "AGENTS.md",
        },
        "claude-code": {
            "mcp": h / ".claude.json",
            "rules": h / ".claude" / "CLAUDE.md",
        },
        "dsh": {
            "settings": h / ".dsh" / "settings.yaml",
            "mcp": h / ".dsh" / "cordis.patch.yml",
        },
        "unsloth-studio": {
            "manifest": h / ".cortical" / "unsloth-studio-mcp.json",
        },
    }


def _read_json_safe(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _upsert_marked_block(existing: str, block_body: str, start_marker: str, end_marker: str) -> str:
    body = f"{start_marker}\n{block_body.rstrip()}\n{end_marker}\n"
    if start_marker in existing and end_marker in existing:
        before, _, rest = existing.partition(start_marker)
        _, _, after = rest.partition(end_marker)
        clean_after = after.lstrip("\n")
        return before + body + (("\n" + clean_after) if clean_after else "")
    prefix = existing.rstrip() + "\n\n" if existing.strip() else ""
    return prefix + body


def _serena_args(context: str) -> list[str]:
    return [
        "start-mcp-server",
        "--context",
        context,
        "--agent-interface",
        "tools",
        "--project-from-cwd",
        "--enable-web-dashboard",
        "false",
        "--open-web-dashboard",
        "false",
    ]


def _cortical_mcp_entry(repo_root: Path, db_path: Path, python_exe: Optional[str] = None) -> dict[str, Any]:
    return {
        "command": python_exe or sys.executable or "python3",
        "args": ["-m", "cortical.mcp_server"],
        "env": {
            "PYTHONPATH": str((repo_root / "src").resolve()),
            "CORTICAL_VAULT_DB": str(db_path.resolve()),
        },
    }


def _build_shared_rules_md(vault_md: str, model_id: str, router_url: str, composed: dict[str, Any]) -> str:
    tools_active = [k for k, v in composed.items() if (v.get("installed") if isinstance(v, dict) else bool(v))]
    lines = [
        "# Cortical Unified Harness Contract",
        "",
        f"- **Default Local Model:** `{model_id}`" + (f" · **Optional HTTP Router:** `{router_url}`" if router_url else ""),
        f"- **Active Token-Savers:** {', '.join(f'`{t}`' for t in tools_active) if tools_active else '`serena`, `rtk`, `TOON`'}",
        "- **Code Navigation & Edits:** Prefer Serena LSP symbol tools (`get_symbols_overview`, `find_symbol`, `replace_symbol_body`) over reading full files.",
        "- **Shell & Test Hygiene:** Compress shell output via `rtk` (or `-q` / summary flags); run tests single-shot after edits.",
        "- **Privacy Vault:** Never read raw files inside `.cortical_data/private_vault/`; reference `@private:<alias>` or sanitized MCP resources.",
    ]
    if vault_md.strip():
        lines.extend(["", vault_md.strip()])
    return "\n".join(lines)


def plan_sync(
    config: dict[str, Any],
    hw: dict[str, Any],
    rec_models: dict[str, Any],
    *,
    vault_markdown: str = "",
    harnesses: Optional[list[str]] = None,
    repo_root: Optional[Path] = None,
    vault_db_path: Optional[Path] = None,
    user_paths: Optional[dict[str, dict[str, Path]]] = None,
) -> list[FileChange]:
    """Plans idempotent updates across selected harnesses without overwriting existing user credentials."""
    root = Path(repo_root or Path.cwd())
    v_db = Path(vault_db_path or (root / ".cortical_data" / "vault.db"))
    paths_map = user_paths or resolve_user_paths(os_name=hw.get("os"))
    targets = list(harnesses or ALL_HARNESSES)

    serena_bin = (hw.get("binaries") or {}).get("serena") or "serena"
    rec_by_role = rec_models.get("recommended_by_role") or {}
    daily_model = (rec_by_role.get("daily_coder") or {}).get("model_id") or config.get("active_model") or "qwen3.5:9b-q3_k_xl"
    reasoner_model = (rec_by_role.get("deep_reasoner") or {}).get("model_id") or daily_model
    router_model = (rec_by_role.get("router") or {}).get("model_id") or "qwen2.5:1.5b"

    router_cfg = config.get("router") or {}
    router_enabled = bool(router_cfg.get("enabled", False))
    router_url = str(router_cfg.get("base_url") or "http://127.0.0.1:4000/v1") if router_enabled else ""
    ollama_v1 = "http://127.0.0.1:11434/v1"
    eff_base_url = router_url or ollama_v1

    rules_body = _build_shared_rules_md(vault_markdown, daily_model, router_url, hw.get("binaries") or {})
    changes: list[FileChange] = []

    def _add(harness: str, path: Path, content: str, kind: str, detail: str) -> None:
        old = path.read_text(encoding="utf-8") if path.is_file() else None
        action = "create" if old is None else ("unchanged" if old == content else "update")
        changes.append(FileChange(harness=harness, path=path, content=content, kind=kind, action=action, detail=detail))

    if "antigravity" in targets:
        p = paths_map["antigravity"]["mcp"]
        cur = _read_json_safe(p)
        mcps = dict(cur.get("mcpServers") or {})
        mcps["serena"] = {"command": serena_bin, "args": _serena_args("antigravity"), "disabled": False}
        mcps["cortical-mcp"] = {**_cortical_mcp_entry(root, v_db), "disabled": False}
        cur["mcpServers"] = mcps
        _add("antigravity", p, json.dumps(cur, indent=2) + "\n", "json", "Add lean Serena + cortical-mcp (Dashboard Ingest Only)")
        rp = paths_map["antigravity"]["rules"]
        r_old = rp.read_text(encoding="utf-8") if rp.is_file() else ""
        _add("antigravity", rp, _upsert_marked_block(r_old, rules_body, "<!-- CORTICAL:START -->", "<!-- CORTICAL:END -->"), "markdown", "Sync shared token-saving rules")

    if "pi" in targets:
        mp = paths_map["pi"]["mcp"]
        cur_m = _read_json_safe(mp)
        ms = dict(cur_m.get("mcpServers") or {})
        ms["serena"] = {"command": serena_bin, "args": _serena_args("ide"), "exposure": "eager", "description": "Serena semantic LSP tools"}
        ms["cortical-mcp"] = {**_cortical_mcp_entry(root, v_db), "exposure": "deferred", "description": "Cortical Privacy Vault & TOON Compression"}
        cur_m["mcpServers"] = ms
        _add("pi", mp, json.dumps(cur_m, indent=2) + "\n", "json", "Configure Serena (eager) & cortical-mcp (deferred)")

        sp = paths_map["pi"]["settings"]
        cur_s = _read_json_safe(sp)
        cur_s["defaultProvider"] = "router" if router_enabled else "ollama"
        cur_s["defaultModel"] = daily_model
        enabled = [f"{cur_s['defaultProvider']}/{m}" for m in dict.fromkeys([daily_model, reasoner_model, router_model])]
        cur_s["enabledModels"] = enabled
        _add("pi", sp, json.dumps(cur_s, indent=2) + "\n", "json", f"Set defaultModel={daily_model} ({'HTTP router' if router_enabled else 'Ollama'})")

    if "opencode" in targets:
        op_p = paths_map["opencode"]["opencode"]
        cur_o = _read_json_safe(op_p)
        prov = dict(cur_o.get("provider") or {})
        prov["ollama"] = {
            "npm": "@ai-sdk/openai-compatible",
            "name": "Cortical Local / Router",
            "options": {"baseURL": eff_base_url},
            "models": {
                m: {"name": m, "num_ctx": int((rec_by_role.get("daily_coder") or {}).get("recommended_num_ctx") or 32768)}
                for m in dict.fromkeys([daily_model, reasoner_model, router_model])
            },
        }
        cur_o["provider"] = prov
        oc_mcp = dict(cur_o.get("mcp") or {})
        oc_mcp["serena"] = {"type": "local", "command": [serena_bin, *_serena_args("ide")], "enabled": True}
        oc_mcp["cortical-mcp"] = {"type": "local", "command": [_cortical_mcp_entry(root, v_db)["command"], "-m", "cortical.mcp_server"], "enabled": True}
        cur_o["mcp"] = oc_mcp
        _add("opencode", op_p, json.dumps(cur_o, indent=2) + "\n", "json", "Sync OpenCode Ollama/Router models + Serena + cortical-mcp")

    if "openclaw" in targets:
        ocp = paths_map["openclaw"]["config"]
        cur_c = _read_json_safe(ocp)
        provs = dict(cur_c.get("providers") or {})
        provs["cortical_local"] = {"baseURL": eff_base_url, "model": daily_model, "reasonerModel": reasoner_model}
        cur_c["providers"] = provs
        mcps = dict(cur_c.get("mcpServers") or {})
        mcps["serena"] = {"command": serena_bin, "args": _serena_args("oaicompat-agent")}
        mcps["cortical-mcp"] = _cortical_mcp_entry(root, v_db)
        cur_c["mcpServers"] = mcps
        _add("openclaw", ocp, json.dumps(cur_c, indent=2) + "\n", "json", "Configure OpenClaw local/router provider + MCPs")

    if "codex" in targets:
        cxp = paths_map["codex"]["config"]
        existing = cxp.read_text(encoding="utf-8") if cxp.is_file() else ""
        toml_block = (
            "[mcp_servers.serena]\n"
            f'command = {json.dumps(serena_bin)}\n'
            f'args = {json.dumps(_serena_args("codex"))}\n\n'
            "[mcp_servers.cortical_mcp]\n"
            f'command = {json.dumps(_cortical_mcp_entry(root, v_db)["command"])}\n'
            'args = ["-m", "cortical.mcp_server"]\n\n'
            "[mcp_servers.cortical_mcp.env]\n"
            f'PYTHONPATH = {json.dumps(str((root / "src").resolve()))}\n'
            f'CORTICAL_VAULT_DB = {json.dumps(str(v_db.resolve()))}'
        )
        _add("codex", cxp, _upsert_marked_block(existing, toml_block, "# >>> CORTICAL START >>>", "# <<< CORTICAL END <<<"), "toml", "Upsert Codex CLI MCP blocks")

    if "claude-code" in targets:
        clp = paths_map["claude-code"]["mcp"]
        cur_cl = _read_json_safe(clp)
        ms = dict(cur_cl.get("mcpServers") or {})
        ms["serena"] = {"command": serena_bin, "args": _serena_args("claude-code")}
        ms["cortical-mcp"] = _cortical_mcp_entry(root, v_db)
        cur_cl["mcpServers"] = ms
        _add("claude-code", clp, json.dumps(cur_cl, indent=2) + "\n", "json", "Merge Serena + cortical-mcp into ~/.claude.json preserving prefs")

    if "dsh" in targets:
        dsp = paths_map["dsh"]["settings"]
        existing = dsp.read_text(encoding="utf-8") if dsp.is_file() else ""
        yaml_block = (
            f"base_url: {eff_base_url}\n"
            f"default_model: {daily_model}\n"
            f"reasoner_model: {reasoner_model}\n"
            "plugins:\n"
            "  - id: mcp-serena\n"
            "    name: '@deepseek-ai/dsh-mcp-client'\n"
            "    config:\n"
            "      serverName: serena\n"
            "      transport: stdio\n"
            f"      command: {serena_bin}\n"
            f"      args: {json.dumps(_serena_args('oaicompat-agent'))}\n"
            "  - id: mcp-cortical\n"
            "    name: '@deepseek-ai/dsh-mcp-client'\n"
            "    config:\n"
            "      serverName: cortical-mcp\n"
            "      transport: stdio\n"
            f"      command: {_cortical_mcp_entry(root, v_db)['command']}\n"
            "      args: ['-m', 'cortical.mcp_server']"
        )
        _add("dsh", dsp, _upsert_marked_block(existing, yaml_block, "# >>> CORTICAL START >>>", "# <<< CORTICAL END <<<"), "yaml", "Configure DeepSeek Harness (dsh) model URL & @deepseek-ai/dsh-mcp-client")

    if "unsloth-studio" in targets:
        usp = paths_map["unsloth-studio"]["manifest"]
        manifest = {
            "serena_streamable_http": "http://127.0.0.1:9121/mcp",
            "cortical_streamable_http": "http://127.0.0.1:9122/mcp",
            "launch_serena_cmd": "cortical serve-mcp serena --port 9121",
            "launch_cortical_cmd": "cortical serve-mcp cortical --port 9122",
            "supported_cli_wrappers": ["unsloth start pi", "unsloth start opencode", "unsloth start claude", "unsloth start dsh"],
            "recommended_models": rec_by_role,
        }
        _add("unsloth-studio", usp, json.dumps(manifest, indent=2) + "\n", "json", "Write Unsloth Studio HTTP MCP manifest & wrapper reference")

    return changes


def apply_sync(
    changes: list[FileChange],
    *,
    dry_run: bool = False,
    backup_root: Optional[Path] = None,
) -> dict[str, Any]:
    """Applies planned harness changes with automatic timestamped backups for clean rollback."""
    b_root = Path(backup_root or (Path.home() / ".cortical" / "backups"))
    bid = time.strftime("%Y%m%d-%H%M%S")
    backup_dir = b_root / bid

    pending = [c for c in changes if c.action != "unchanged"]
    if dry_run or not pending:
        return {
            "dry_run": dry_run,
            "backup_id": None,
            "changed_count": len(pending),
            "unchanged_count": len(changes) - len(pending),
            "changes": [{"harness": c.harness, "path": str(c.path), "action": c.action, "detail": c.detail} for c in changes],
        }

    backup_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, Any]] = []
    for idx, ch in enumerate(pending):
        existed = ch.path.is_file()
        snap_name = f"{idx:03d}_{ch.path.name}.bak"
        if existed:
            (backup_dir / snap_name).write_bytes(ch.path.read_bytes())
        manifest.append({
            "target_path": str(ch.path),
            "existed": existed,
            "backup_file": snap_name if existed else None,
            "sha256_after": hashlib.sha256(ch.content.encode("utf-8")).hexdigest()[:16],
        })
        ch.path.parent.mkdir(parents=True, exist_ok=True)
        ch.path.write_text(ch.content, encoding="utf-8")

    (backup_dir / "manifest.json").write_text(json.dumps({"backup_id": bid, "entries": manifest}, indent=2), encoding="utf-8")
    return {
        "dry_run": False,
        "backup_id": bid,
        "backup_dir": str(backup_dir),
        "changed_count": len(pending),
        "unchanged_count": len(changes) - len(pending),
        "changes": [{"harness": c.harness, "path": str(c.path), "action": c.action, "detail": c.detail} for c in changes],
    }


def rollback_sync(backup_id: str, backup_root: Optional[Path] = None) -> dict[str, Any]:
    """Restores exact previous files (and deletes newly created files) for `backup_id`."""
    b_root = Path(backup_root or (Path.home() / ".cortical" / "backups"))
    backup_dir = b_root / backup_id
    mf = backup_dir / "manifest.json"
    if not mf.is_file():
        raise FileNotFoundError(f"Backup manifest not found: {mf}")
    data = json.loads(mf.read_text(encoding="utf-8"))
    restored = 0
    removed = 0
    for entry in data.get("entries", []):
        target = Path(entry["target_path"])
        if entry["existed"] and entry.get("backup_file"):
            snap = backup_dir / entry["backup_file"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(snap, target)
            restored += 1
        elif not entry["existed"] and target.is_file():
            target.unlink()
            removed += 1
    return {"backup_id": backup_id, "restored": restored, "removed_new": removed}
