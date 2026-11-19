"""Lean 5-tool MCP Server (`stdio`) exposing Cortical Privacy Vault, TOON Compressor, Doctor & Local Offload."""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from pathlib import Path
from typing import Any, Optional

from .compression.engine import compress_structured
from .composers.tools import inspect_composed_tools
from .config import DEFAULT_VAULT_DB, invoke_configured_runner, load_cortical_config
from .hardware.models import recommend_models_for_hardware
from .hardware.probe import probe_hardware
from .privacy.vault import PrivacyVault


TOOLS_SCHEMA: list[dict[str, Any]] = [
    {
        "name": "cortical_vault_read",
        "description": "Read a locally sanitized, TOON-compressed item by alias or `cortical://private/<alias>` URI without touching raw files (blocks max_security).",
        "inputSchema": {
            "type": "object",
            "properties": {"alias": {"type": "string", "description": "Vault alias or cortical://private/<alias> URI"}},
            "required": ["alias"],
        },
    },
    {
        "name": "cortical_ingest_private",
        "description": "Ingest a local file or text into Privacy Vault with dynamic `auto` | `fail_closed` | `fail_open` classification.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path_or_text": {"type": "string"},
                "alias": {"type": "string"},
                "policy": {"type": "string", "enum": ["auto", "fail_closed", "fail_open"], "default": "auto"},
                "profile": {"type": "string", "enum": ["max_security", "low", "medium", "max_context"], "default": "medium"},
            },
            "required": ["path_or_text"],
        },
    },
    {
        "name": "cortical_compress",
        "description": "Deterministically compress JSON (to lossless TOON with compact fallback), XML, or verbose logs.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "format": {"type": "string", "enum": ["auto", "json", "xml", "yaml", "log"], "default": "auto"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "cortical_doctor_status",
        "description": "Inspect machine hardware tier (incl. 4GB VRAM Hybrid & 16GB Unified 27B), installed local models, and composed OSS tools.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "cortical_local_offload",
        "description": "Delegate summarization/analysis/review to configured local Ollama/Unsloth model (0 cloud tokens).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "model": {"type": "string"},
                "vault_alias": {"type": "string", "description": "Optional vault alias (including max_security) processed strictly offline"},
            },
            "required": ["prompt"],
        },
    },
]


class CorticalMCPServer:
    """Thin 5-tool JSON-RPC 2.0 MCP server + native `resources` & `prompts`."""

    def __init__(self, vault_db: Path | str | None = None) -> None:
        self.vault = PrivacyVault(vault_db or os.environ.get("CORTICAL_VAULT_DB") or DEFAULT_VAULT_DB)
        self.vault.process_inbox_inline = False  # slow local-model jobs never block an MCP call
        self._inbox_thread: Optional[threading.Thread] = None

    def _kick_inbox(self) -> None:
        """Processes queued uploads (local NER/vision) in a background thread."""
        if self._inbox_thread is not None and self._inbox_thread.is_alive():
            return
        if self.vault.pending_inbox():
            self._inbox_thread = threading.Thread(target=lambda: self.vault.sync_from_disk(process_inbox=True), daemon=True)
            self._inbox_thread.start()

    def _dispatch_tool(self, name: str, args: dict[str, Any]) -> Any:
        if name == "cortical_vault_read":
            return self.vault.read_resource(str(args.get("alias") or ""), allow_local_only=False)
        if name == "cortical_ingest_private":
            cfg = load_cortical_config()
            priv = cfg.get("privacy") or {}
            return self.vault.ingest(
                str(args.get("path_or_text") or ""),
                alias=args.get("alias"),
                policy=str(args.get("policy") or priv.get("default_policy") or "auto"),
                profile=str(args.get("profile") or priv.get("default_profile") or "medium"),
                custom_terms=list(priv.get("custom_terms") or []),
                config=cfg,
            )
        if name == "cortical_compress":
            return compress_structured(str(args.get("text") or ""), fmt=str(args.get("format") or "auto"))
        if name == "cortical_doctor_status":
            cfg = load_cortical_config()
            hw = probe_hardware(runners_probe=False)
            rec = recommend_models_for_hardware(hw, custom_models=cfg.get("custom_models"))
            return {"hardware": hw, "models": rec, "composers": inspect_composed_tools()}
        if name == "cortical_local_offload":
            cfg = load_cortical_config()
            prompt = str(args.get("prompt") or "")
            if args.get("vault_alias"):
                item = self.vault.read_resource(str(args["vault_alias"]), allow_local_only=True)
                prompt = f"Sanitized local context (@private:{item['alias']}):\n{item['text']}\n\nTask:\n{prompt}"
            out = invoke_configured_runner(
                prompt,
                system_prompt="Reply concisely offline using only provided context.",
                config=cfg,
                model_override=args.get("model") or None,
                role="mcp_local_offload",
            )
            return {"completed_locally": True, "response": out}
        raise ValueError(f"Unknown tool: {name}")

    def _private_prompt_text(self, alias: str) -> str:
        """Never raises: empty/unknown/local-only alias yields a helpful listing instead of an MCP error."""
        alias = alias.replace("cortical://private/", "").lstrip("@").strip()
        safe = self.vault.list_resources(include_local_only=False)
        names = [r["name"] for r in safe]
        listing = ", ".join(f"@private:{n}" for n in names) or "(none)"
        if not alias:
            if not names:
                return "Cortical Vault has no chat-safe items. Add files via settings.html (profile 'medium') or `cortical ingest`."
            return "Available sanitized Cortical items: " + listing + ". Re-run with alias=<name> to inject one."
        try:
            item = self.vault.read_resource(alias, allow_local_only=False)
            return f"Sanitized reference `{item['uri']}` ({item['format_used']}):\n{item['text']}"
        except KeyError:
            m = [n for n in names if alias.lower() in n.lower()]
            if len(m) == 1:
                item = self.vault.read_resource(m[0], allow_local_only=False)
                return f"Sanitized reference `{item['uri']}` ({item['format_used']}):\n{item['text']}"
            return f"No chat-safe item '{alias}'. Available: {listing}"
        except Exception as exc:  # noqa: BLE001
            return f"Item '{alias}' is not available for cloud chat ({exc}). Available: {listing}"

    def handle_request(self, req: dict[str, Any]) -> Optional[dict[str, Any]]:
        rid = req.get("id")
        method = str(req.get("method") or "")
        params = req.get("params") or {}

        if method.startswith("notifications/"):
            return None
        if method in {"initialize", "resources/list", "prompts/get", "tools/call"}:
            self._kick_inbox()
        try:
            if method == "initialize":
                result: Any = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}, "resources": {}, "prompts": {}, "completions": {}},
                    "serverInfo": {"name": "cortical-mcp", "version": "0.3.0"},
                }
            elif method == "tools/list":
                result = {"tools": TOOLS_SCHEMA}
            elif method == "tools/call":
                tname = str(params.get("name") or "")
                targs = params.get("arguments") or {}
                out = self._dispatch_tool(tname, targs)
                result = {"content": [{"type": "text", "text": json.dumps(out, ensure_ascii=False, indent=2)}], "isError": False}
            elif method == "resources/list":
                result = {"resources": self.vault.list_resources(include_local_only=False)}
            elif method == "resources/read":
                uri = str(params.get("uri") or "")
                item = self.vault.read_resource(uri, allow_local_only=False)
                result = {"contents": [{"uri": item["uri"], "mimeType": "text/plain", "text": item["text"]}]}
            elif method == "completion/complete":
                prefix = str((params.get("argument") or {}).get("value") or "").lower()
                vals = [r["name"] for r in self.vault.list_resources(include_local_only=False) if r["name"].lower().startswith(prefix)]
                result = {"completion": {"values": vals[:100], "total": len(vals), "hasMore": False}}
            elif method == "prompts/list":
                result = {
                    "prompts": [
                        {"name": "cortical-private", "description": "Inject sanitized @private:<alias> context (omit alias to list available items)", "arguments": [{"name": "alias", "description": "Vault alias (autocompleted)", "required": False}]},
                        {"name": "cortical-local", "description": "Run task offline on local Ollama/Unsloth model", "arguments": [{"name": "prompt", "required": True}]},
                    ]
                }
            elif method == "prompts/get":
                pname = str(params.get("name") or "")
                pargs = params.get("arguments") or {}
                if pname == "cortical-private":
                    txt = self._private_prompt_text(str(pargs.get("alias") or ""))
                elif pname == "cortical-local":
                    txt = f"Delegate to `cortical_local_offload` locally: {pargs.get('prompt', '')}"
                else:
                    raise ValueError(f"Unknown prompt: {pname}")
                result = {"messages": [{"role": "user", "content": {"type": "text", "text": txt}}]}
            else:
                raise ValueError(f"Unsupported MCP method: {method}")
            return {"jsonrpc": "2.0", "id": rid, "result": result}
        except Exception as exc:  # noqa: BLE001
            if rid is None:
                return None
            return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32000, "message": str(exc)}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cortical Lean MCP Server (stdio)")
    parser.add_argument("--vault-db", default=None, help="Path to Cortical Privacy Vault SQLite DB")
    args, _ = parser.parse_known_args(argv)
    server = CorticalMCPServer(vault_db=args.vault_db)
    for raw_line in sys.stdin:
        ln = raw_line.strip()
        if not ln:
            continue
        resp = server.handle_request(json.loads(ln))
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
