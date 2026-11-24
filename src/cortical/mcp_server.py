"""Lean 7-tool MCP Server (`stdio` default, optional `--transport streamable-http`) for Cortical Control Plane."""

from __future__ import annotations

import argparse
import http.server
import json
import os
import sys
import threading
from pathlib import Path
from typing import Any, Optional

from .compression.engine import compress_structured
from .composers.tools import inspect_composed_tools
from .config import DEFAULT_VAULT_DB, invoke_configured_runner, load_cortical_config, remote_orchestrator_active
from .hardware.models import recommend_models_for_hardware
from .hardware.probe import probe_hardware
from .privacy.vault import PrivacyVault


TOOLS_SCHEMA: list[dict[str, Any]] = [
    {
        "name": "cortical_vault_read",
        "description": "Read a Vault item by `alias` OR all items matching a `task_tag` at 3+1 depth (`light`, `medium`, `high`, `max`; blocks max_security from cloud).",
        "annotations": {
            "title": "Read Sanitized Privacy Vault Context",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
        "inputSchema": {
            "type": "object",
            "properties": {
                "alias": {"type": "string", "description": "Vault alias or cortical://private/<alias> URI"},
                "task_tag": {"type": "string", "description": "Optional task tag to fetch compact context for all tagged documents"},
                "tier": {"type": "string", "enum": ["light", "medium", "high", "max"], "default": "max"},
            },
            "required": [],
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "uri": {"type": "string"},
                "alias": {"type": "string"},
                "tier": {"type": "string"},
                "resolved_policy": {"type": "string"},
                "profile": {"type": "string"},
                "format_used": {"type": "string"},
                "tokens_est": {"type": "integer"},
                "text": {"type": "string"},
                "task_tag": {"type": "string"},
                "count": {"type": "integer"},
                "documents": {"type": "array", "items": {"type": "object"}},
            },
            "additionalProperties": True,
        },
    },
    {
        "name": "cortical_ingest_private",
        "description": "Ingest a local file or text into Privacy Vault with dynamic `auto` | `fail_closed` | `fail_open` classification.",
        "annotations": {
            "title": "Ingest & Sanitize Private Context",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
        "inputSchema": {
            "type": "object",
            "properties": {
                "path_or_text": {"type": "string"},
                "alias": {"type": "string"},
                "policy": {"type": "string", "enum": ["auto", "fail_closed", "fail_open"], "default": "auto"},
                "profile": {"type": "string", "enum": ["max_security", "low", "medium", "max_context"], "default": "medium"},
                "task_tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["path_or_text"],
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "alias": {"type": "string"},
                "uri": {"type": "string"},
                "resolved_policy": {"type": "string"},
                "profile": {"type": "string"},
                "local_only": {"type": "boolean"},
                "entity_count": {"type": "integer"},
                "tokens_est": {"type": "integer"},
                "saving_pct": {"type": "number"},
            },
            "required": ["alias", "uri", "resolved_policy", "local_only"],
            "additionalProperties": True,
        },
    },
    {
        "name": "cortical_compress",
        "description": "Deterministically compress JSON (to lossless TOON with compact fallback), XML, or verbose logs.",
        "annotations": {
            "title": "Deterministic Lossless TOON Compression",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "format": {"type": "string", "enum": ["auto", "json", "xml", "yaml", "log"], "default": "auto"},
            },
            "required": ["text"],
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "compressed": {"type": "string"},
                "format_used": {"type": "string"},
                "raw_tokens_est": {"type": "integer"},
                "compressed_tokens_est": {"type": "integer"},
                "saving_pct": {"type": "number"},
            },
            "required": ["compressed", "format_used"],
            "additionalProperties": True,
        },
    },
    {
        "name": "cortical_doctor_status",
        "description": "Inspect machine hardware tier (incl. 4GB VRAM Hybrid & 16GB Unified 27B), installed local models, and composed OSS tools.",
        "annotations": {
            "title": "Hardware Preflight & Tool Diagnostics",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
        "inputSchema": {"type": "object", "properties": {}},
        "outputSchema": {
            "type": "object",
            "properties": {
                "hardware": {"type": "object"},
                "models": {"type": "object"},
                "composers": {"type": "object"},
                "routing": {"type": "object"},
            },
            "required": ["hardware", "models", "composers", "routing"],
            "additionalProperties": True,
        },
    },
    {
        "name": "cortical_local_offload",
        "description": "Delegate summarization/analysis/review to configured local Ollama/Unsloth model (0 cloud tokens).",
        "annotations": {
            "title": "Zero-Cloud-Token Local LLM Offload",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
        },
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "role": {
                    "type": "string",
                    "description": "Semantic model role (router, ner, fast_coder, daily_coder, reviewer, summarizer, deep_reasoner, orchestrator, vision)",
                },
                "model": {"type": "string", "description": "Optional explicit model ID or @role:<name> alias"},
                "vault_alias": {"type": "string", "description": "Optional vault alias (including max_security) processed strictly offline"},
            },
            "required": ["prompt"],
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "completed_locally": {"type": "boolean"},
                "model_used": {"type": "string"},
                "elapsed_sec": {"type": "number"},
                "response": {"type": "string"},
            },
            "required": ["completed_locally", "model_used", "response"],
            "additionalProperties": True,
        },
    },
    {
        "name": "cortical_roi_report",
        "description": "Compute local vs cloud token usage, USD savings, and remaining cloud budget (0 cloud tokens).",
        "annotations": {
            "title": "Zero-Token ROI & Cloud Budget Report",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
        "inputSchema": {
            "type": "object",
            "properties": {
                "conversation_id": {"type": "string"},
                "include_local_summary": {"type": "boolean", "default": False},
            },
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "markdown": {"type": "string"},
                "local_note": {"type": "string"},
                "effective_mode": {"type": "string"},
                "enforce_cloud_budget": {"type": "boolean"},
                "cloud_remaining_tokens": {"type": "integer"},
                "cloud_token_threshold": {"type": "integer"},
                "handoff_recommended": {"type": "boolean"},
            },
            "required": ["markdown", "effective_mode", "cloud_remaining_tokens"],
            "additionalProperties": True,
        },
    },
    {
        "name": "cortical_handoff",
        "description": "Save or load shared working context (goal, modified files, decisions, next_step) across Antigravity, pi, OpenCode, Claude Code & Codex.",
        "annotations": {
            "title": "Cross-Harness Working Context Handoff",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["save", "load"], "default": "load"},
                "goal": {"type": "string"},
                "summary": {"type": "string"},
                "modified_files": {"type": "array", "items": {"type": "string"}},
                "next_step": {"type": "string"},
                "source_harness": {"type": "string"},
            },
            "required": ["action"],
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "saved": {"type": "boolean"},
                "found": {"type": "boolean"},
                "path": {"type": "string"},
                "handoff": {"type": ["object", "null"]},
            },
            "additionalProperties": True,
        },
    },
]


class CorticalMCPServer:
    """Lean 7-tool JSON-RPC 2.0 MCP server + native `resources`, `prompts` & `completions`."""

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

    def _remote_egress_ctx(self) -> tuple[bool, list[str]]:
        cfg = load_cortical_config()
        is_remote = remote_orchestrator_active(cfg) and bool((cfg.get("orchestrator") or {}).get("strict_remote_privacy", True))
        terms = list((cfg.get("privacy") or {}).get("custom_terms") or [])
        return is_remote, terms

    def _dispatch_tool(self, name: str, args: dict[str, Any]) -> Any:
        if name == "cortical_vault_read":
            tier = str(args.get("tier") or "max")
            is_remote, terms = self._remote_egress_ctx()
            if args.get("task_tag") and not args.get("alias"):
                return self.vault.read_task_context(
                    str(args["task_tag"]),
                    allow_local_only=False,
                    tier=tier if tier != "max" else "medium",
                    remote_egress=is_remote,
                    custom_terms=terms or None,
                )
            return self.vault.read_resource(
                str(args.get("alias") or ""),
                allow_local_only=False,
                tier=tier,
                remote_egress=is_remote,
                custom_terms=terms or None,
            )
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
                task_tags=args.get("task_tags"),
            )
        if name == "cortical_compress":
            return compress_structured(str(args.get("text") or ""), fmt=str(args.get("format") or "auto"))
        if name == "cortical_doctor_status":
            from .analytics.roi import evaluate_routing_state, export_roi_json

            cfg = load_cortical_config()
            hw = probe_hardware(runners_probe=False)
            rec = recommend_models_for_hardware(hw, custom_models=cfg.get("custom_models"))
            routing_state = evaluate_routing_state(config=cfg)
            export_roi_json(self.vault.db_path.parent, config=cfg)
            return {"hardware": hw, "models": rec, "composers": inspect_composed_tools(), "routing": routing_state}
        if name == "cortical_local_offload":
            import time as _t
            from .analytics.roi import export_roi_json

            from .roles import normalize_role_or_model

            cfg = load_cortical_config()
            prompt = str(args.get("prompt") or "")
            if args.get("vault_alias"):
                item = self.vault.read_resource(str(args["vault_alias"]), allow_local_only=True)
                prompt = f"Sanitized local context (@private:{item['alias']}):\n{item['text']}\n\nTask:\n{prompt}"
            role_or_model = str(args.get("model") or args.get("role") or "").strip()
            used_model = normalize_role_or_model(role_or_model, cfg, default_role="daily_coder")
            t0 = _t.perf_counter()
            out = invoke_configured_runner(
                prompt,
                system_prompt="Reply concisely offline using only provided context.",
                config=cfg,
                model_override=used_model,
                role=str(args.get("role") or "mcp_local_offload"),
            )
            elapsed = round(_t.perf_counter() - t0, 2)
            export_roi_json(self.vault.db_path.parent, config=cfg)
            return {"completed_locally": True, "model_used": used_model, "elapsed_sec": elapsed, "response": out}
        if name == "cortical_roi_report":
            from .analytics.roi import evaluate_routing_state, export_roi_json, format_roi_markdown

            cfg = load_cortical_config()
            state = evaluate_routing_state(config=cfg, conversation_id=args.get("conversation_id"))
            export_roi_json(self.vault.db_path.parent, config=cfg)
            md = format_roi_markdown(state["roi"])
            local_note = ""
            if args.get("include_local_summary"):
                router_m = str((cfg.get("models_by_role") or {}).get("router") or "qwen2.5:1.5b")
                local_note = invoke_configured_runner(
                    f"Summarize in 1 short sentence the token optimization from this table:\n{md}",
                    system_prompt="Be concise (max 25 words).",
                    config=cfg,
                    model_override=router_m,
                    role="roi_recap",
                )
            return {
                "markdown": md,
                "local_note": local_note,
                "effective_mode": state["effective_mode"],
                "enforce_cloud_budget": bool(state.get("enforce_cloud_budget", False)),
                "cloud_remaining_tokens": state["cloud_remaining_tokens"],
                "cloud_token_threshold": state["cloud_token_threshold"],
                "handoff_recommended": bool(state.get("handoff_recommended", False)),
            }
        if name == "cortical_handoff":
            import time as _t

            action = str(args.get("action") or "load").lower().strip()
            h_path = self.vault.db_path.parent / "brain" / "handoff.json"
            h_path.parent.mkdir(parents=True, exist_ok=True)
            if action == "save":
                payload = {
                    "goal": str(args.get("goal") or ""),
                    "summary": str(args.get("summary") or ""),
                    "modified_files": list(args.get("modified_files") or []),
                    "next_step": str(args.get("next_step") or ""),
                    "source_harness": str(args.get("source_harness") or "unknown"),
                    "updated_at": int(_t.time()),
                }
                h_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                if payload["goal"] or payload["summary"]:
                    self.vault.brain.distill_and_factorize(
                        alias="active_handoff",
                        text=f"Goal: {payload['goal']}\nSummary: {payload['summary']}\nFiles: {', '.join(payload['modified_files'])}\nNext: {payload['next_step']}",
                        is_public=True,
                    )
                return {"saved": True, "path": str(h_path), "handoff": payload}
            if h_path.is_file():
                return {"found": True, "handoff": json.loads(h_path.read_text(encoding="utf-8"))}
            return {"found": False, "handoff": None, "brain_snapshot": self.vault.brain.get_snapshot(include_local_only=False)}
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
                    "protocolVersion": "2025-06-18",
                    "capabilities": {"tools": {}, "resources": {}, "prompts": {}, "completions": {}},
                    "serverInfo": {"name": "cortical-mcp", "version": "0.3.0"},
                }
            elif method == "tools/list":
                result = {"tools": TOOLS_SCHEMA}
            elif method == "tools/call":
                tname = str(params.get("name") or "")
                targs = params.get("arguments") or {}
                out = self._dispatch_tool(tname, targs)
                structured = out if isinstance(out, dict) else {"result": out}
                result = {
                    "content": [{"type": "text", "text": json.dumps(out, ensure_ascii=False, indent=2)}],
                    "structuredContent": structured,
                    "isError": False,
                }
            elif method == "resources/list":
                is_remote, terms = self._remote_egress_ctx()
                res = self.vault.list_resources(include_local_only=False, remote_egress=is_remote, custom_terms=terms or None)
                res.append({"uri": "cortical://brain", "name": "cortical-brain", "description": "Factorized 3+1 Local Brain (concepts, tasks, skills)", "mimeType": "application/json"})
                result = {"resources": res}
            elif method == "resources/read":
                uri = str(params.get("uri") or "")
                if uri == "cortical://brain":
                    snap = self.vault.brain.get_snapshot(include_local_only=False)
                    result = {"contents": [{"uri": "cortical://brain", "mimeType": "application/json", "text": json.dumps(snap, ensure_ascii=False, indent=2)}]}
                else:
                    is_remote, terms = self._remote_egress_ctx()
                    item = self.vault.read_resource(uri, allow_local_only=False, remote_egress=is_remote, custom_terms=terms or None)
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


def create_streamable_http_server(
    mcp_server: CorticalMCPServer,
    *,
    host: str = "127.0.0.1",
    port: int = 9122,
) -> http.server.ThreadingHTTPServer:
    """Creates an opt-in stdlib Streamable HTTP JSON-RPC server (`/mcp`, `/health`)."""

    class _MCPHttpHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return

        def _send_json(self, status: int, payload: Any) -> None:
            raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:
            if self.path.split("?", 1)[0] in {"/health", "/mcp", "/"}:
                self._send_json(200, {"ok": True, "name": "cortical-mcp", "version": "0.3.0", "transport": "streamable-http"})
                return
            self._send_json(404, {"error": "Not found"})

        def do_POST(self) -> None:
            if self.path.split("?", 1)[0] not in {"/mcp", "/"}:
                self._send_json(404, {"error": "Not found"})
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length).decode("utf-8")
                req = json.loads(body) if body.strip() else {}
            except Exception:  # noqa: BLE001
                self._send_json(400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
                return

            if isinstance(req, list):
                resps = [r for r in (mcp_server.handle_request(item) for item in req if isinstance(item, dict)) if r is not None]
                if not resps:
                    self.send_response(202)
                    self.end_headers()
                    return
                self._send_json(200, resps)
                return

            if not isinstance(req, dict):
                self._send_json(400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}})
                return
            resp = mcp_server.handle_request(req)
            if resp is None:
                self.send_response(202)
                self.end_headers()
                return
            self._send_json(200, resp)

    return http.server.ThreadingHTTPServer((host, port), _MCPHttpHandler)


def serve_streamable_http(mcp_server: CorticalMCPServer, host: str = "127.0.0.1", port: int = 9122) -> None:
    """Runs the opt-in foreground Streamable HTTP MCP server until interrupted."""
    httpd = create_streamable_http_server(mcp_server, host=host, port=port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cortical Lean 7-Tool MCP Server (stdio or streamable-http)")
    parser.add_argument("--vault-db", default=None, help="Path to Cortical Privacy Vault SQLite DB")
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9122)
    args, _ = parser.parse_known_args(argv)
    server = CorticalMCPServer(vault_db=args.vault_db)
    if args.transport == "streamable-http":
        serve_streamable_http(server, host=args.host, port=args.port)
        return 0
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
