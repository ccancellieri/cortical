"""Zero-Server Static Dashboard State Hydration Builder (Python 3.10+ stdlib only).

Collects a structured, sanitized JSON snapshot (Hardware Tier, 8 Harnesses + Drift + Backups,
Composed OSS Tools, Model Catalog, Privacy Vault Metadata & 15% num_ctx Gauge, ROI, Benchmark,
and in-repo ADRs) for embedding directly into `settings.html`.
When `public_docs=True`, strips all personal paths, vault items, and local host metadata so
`docs/settings.html` boots cleanly on GitHub Pages in Demo / Unlinked mode.
"""

from __future__ import annotations

import copy
import platform
import re
import time
from pathlib import Path
from typing import Any, Optional

from ..composers.tools import inspect_composed_tools
from ..config import DEFAULT_CONFIG, ORCHESTRATOR_PRESETS, default_data_dir, load_cortical_config, resolve_orchestrator_spec
from ..hardware.context_window import compute_dynamic_num_ctx
from ..hardware.models import list_all_models, recommend_models_for_hardware
from ..hardware.probe import classify_hardware_tier
from ..harnesses.adapters import ALL_HARNESSES, get_harness_presend_matrix, plan_sync, resolve_user_paths

HARNESS_INSTALL_RECIPES: dict[str, dict[str, str]] = {
    "antigravity": {
        "macos": "Download Google Antigravity IDE; then run: cortical sync --harness antigravity",
        "linux": "Install Antigravity IDE; then run: cortical sync --harness antigravity",
        "windows": "Install Antigravity IDE; then run: cortical sync --harness antigravity",
    },
    "pi": {
        "macos": "npm i -g @earendil-works/pi-coding-agent && cortical sync --harness pi",
        "linux": "npm i -g @earendil-works/pi-coding-agent && cortical sync --harness pi",
        "windows": "npm i -g @earendil-works/pi-coding-agent; cortical sync --harness pi",
    },
    "opencode": {
        "macos": "brew install opencode-ai/tap/opencode && cortical sync --harness opencode",
        "linux": "curl -fsSL https://opencode.ai/install | bash && cortical sync --harness opencode",
        "windows": "winget install OpenCode.OpenCode; cortical sync --harness opencode",
    },
    "openclaw": {
        "macos": "npm i -g openclaw && cortical sync --harness openclaw",
        "linux": "npm i -g openclaw && cortical sync --harness openclaw",
        "windows": "npm i -g openclaw; cortical sync --harness openclaw",
    },
    "codex": {
        "macos": "npm i -g @openai/codex && cortical sync --harness codex",
        "linux": "npm i -g @openai/codex && cortical sync --harness codex",
        "windows": "npm i -g @openai/codex; cortical sync --harness codex",
    },
    "claude-code": {
        "macos": "npm i -g @anthropic-ai/claude-code && cortical sync --harness claude-code",
        "linux": "npm i -g @anthropic-ai/claude-code && cortical sync --harness claude-code",
        "windows": "npm i -g @anthropic-ai/claude-code; cortical sync --harness claude-code",
    },
    "dsh": {
        "macos": "npm i -g @deepseek-ai/dsh && cortical sync --harness dsh",
        "linux": "npm i -g @deepseek-ai/dsh && cortical sync --harness dsh",
        "windows": "npm i -g @deepseek-ai/dsh; cortical sync --harness dsh",
    },
    "unsloth-studio": {
        "macos": "pipx install unsloth && cortical sync --harness unsloth-studio",
        "linux": "pipx install unsloth && cortical sync --harness unsloth-studio",
        "windows": "pipx install unsloth; cortical sync --harness unsloth-studio",
    },
}

COMPOSER_META: list[dict[str, Any]] = [
    {
        "id": "serena",
        "name": "Serena LSP",
        "role": "AST / Symbol-level code navigation & targeted edits (saves 60–80% read tokens)",
        "recipes": {
            "macos": "uvx --from git+https://github.com/oraios/serena serena start-mcp-server",
            "linux": "uvx --from git+https://github.com/oraios/serena serena start-mcp-server",
            "windows": "uvx --from git+https://github.com/oraios/serena serena start-mcp-server",
        },
    },
    {
        "id": "rtk",
        "name": "RTK (Rust Token Killer)",
        "role": "CLI output token compression proxy (60–90% savings on git/test/build output)",
        "recipes": {
            "macos": "brew install rtk && rtk init --global --auto-patch",
            "linux": "cargo install rtk && rtk init --global --auto-patch",
            "windows": "cargo install rtk; rtk init --global --auto-patch",
        },
    },
    {
        "id": "pinchtab",
        "name": "PinchTab / Playwright MCP",
        "role": "Compact accessibility-tree browser automation without heavy DOM dumps",
        "recipes": {
            "macos": "npx -y @playwright/mcp@latest --help",
            "linux": "npx -y @playwright/mcp@latest --help",
            "windows": "npx -y @playwright/mcp@latest --help",
        },
    },
    {
        "id": "context_mode",
        "name": "context-mode",
        "role": "Deterministic context pruning & structured output filtering",
        "recipes": {
            "macos": "npx -y context-mode --version",
            "linux": "npx -y context-mode --version",
            "windows": "npx -y context-mode --version",
        },
    },
    {
        "id": "router",
        "name": "Local Router (LiteLLM / OmniRoute)",
        "role": "Unified OpenAI-compatible localhost:4000 router with semantic aliases",
        "recipes": {
            "macos": "pipx install 'litellm[proxy]' && litellm --config ~/.cortical/litellm_config.yaml --port 4000",
            "linux": "pipx install 'litellm[proxy]' && litellm --config ~/.cortical/litellm_config.yaml --port 4000",
            "windows": "pipx install \"litellm[proxy]\"; litellm --config $HOME\\.cortical\\litellm_config.yaml --port 4000",
        },
    },
]


def _tilde(p: Path) -> str:
    raw, home = str(p), str(Path.home())
    return "~" + raw[len(home):] if raw.startswith(home) else raw


def scan_repo_adrs(repo_root: Optional[Path] = None) -> list[dict[str, str]]:
    """Reads `docs/adr/ADR-*.md` so ADRs are searchable in the static dashboard Command Palette."""
    root = Path(repo_root or Path.cwd()).resolve()
    adr_dir = root / "docs" / "adr"
    if not adr_dir.is_dir():
        return []
    out: list[dict[str, str]] = []
    for fp in sorted(adr_dir.glob("ADR-*.md")):
        try:
            txt = fp.read_text(encoding="utf-8", errors="ignore")
            m_title = re.search(r"^#\s+(.+)$", txt, re.M)
            m_status = re.search(r"\*\*Status:\*\*\s*(.+)$", txt, re.M)
            m_issue = re.search(r"\*\*GitHub Issue:\*\*\s*(.+)$", txt, re.M)
            m_dec = re.search(r"##\s+Decision\s*\n+([^\n]+)", txt)
            adr_id = fp.stem.split("-")[0] + "-" + fp.stem.split("-")[1] if len(fp.stem.split("-")) >= 2 else fp.stem
            out.append({
                "id": adr_id,
                "filename": fp.name,
                "title": m_title.group(1).strip() if m_title else fp.stem,
                "status": m_status.group(1).strip() if m_status else "Accepted",
                "issue": m_issue.group(1).strip() if m_issue else "",
                "summary": (m_dec.group(1).strip()[:180] if m_dec else ""),
            })
        except OSError:
            continue
    return out


def _demo_hardware() -> dict[str, Any]:
    hw = {
        "os": "macos",
        "total_ram_gb": 16.0,
        "free_ram_gb": 10.5,
        "unified_memory": True,
        "vram_gb": 11.2,
        "memory_pressure_level": 1,
        "gpu_name": "Apple Silicon (Demo Profile)",
        "disk_free_gb": 120.0,
        "installed_ollama_models": [],
    }
    hw["classification"] = classify_hardware_tier(hw)
    return hw


def _build_orchestration_matrix(orch: dict[str, Any], harnesses_out: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Builds a per-harness orchestration & zero-leakage binding summary across all 8 harnesses."""
    is_remote = bool(orch.get("is_remote"))
    mode_label = f"Remote ({orch.get('provider')})" if is_remote else f"Local ({orch.get('provider')})"
    workers = orch.get("local_workers") or {}
    worker_str = f"fast={workers.get('fast', 'qwen3.5:9b-q3_k_xl')} · router={workers.get('router', 'qwen2.5:1.5b')}"
    targets_hint = {
        "antigravity": "GEMINI.md + cortical-mcp (local offload)",
        "pi": "models.json + settings.json + AGENTS.md",
        "opencode": "opencode.json + config.json + AGENTS.md",
        "openclaw": "openclaw.json + AGENTS.md",
        "codex": "config.toml [profiles.cortical_*] + AGENTS.md",
        "claude-code": "~/.claude.json + CLAUDE.md + Serena/Cortical",
        "dsh": "settings.yaml + Cordis MCP plugins",
        "unsloth-studio": "unsloth-studio-mcp.json + HTTP wrappers",
    }
    rows: list[dict[str, Any]] = []
    for h in harnesses_out:
        hid = str(h.get("id") or "")
        presend = bool(h.get("presend_verified"))
        if not is_remote:
            guard = "Air-Gapped Local Only (zero cloud egress)"
        elif presend:
            guard = "fail_closed + verified pre-send hook + MCP vault block"
        else:
            guard = "fail_closed MCP & sync guard (no native attachment hook)"
        rows.append({
            "harness": hid,
            "lifecycle": h.get("lifecycle", "not_detected"),
            "orchestrator_binding": mode_label,
            "orchestrator_model": orch.get("model", "cortical-deep"),
            "local_workers": worker_str,
            "num_ctx": int(orch.get("effective_num_ctx") or 65536),
            "timeout_sec": int(orch.get("timeout_sec") or 600),
            "delegation": "local_first_offload" if orch.get("local_first_delegation", True) else "direct",
            "privacy_guard": guard,
            "target_files": targets_hint.get(hid, ""),
        })
    return rows


def build_dashboard_snapshot(
    *,
    config: Optional[dict[str, Any]] = None,
    hw: Optional[dict[str, Any]] = None,
    repo_root: Optional[Path] = None,
    os_name: Optional[str] = None,
    public_docs: bool = False,
) -> dict[str, Any]:
    """Builds the full zero-server hydration JSON payload for `settings.html`."""
    from .benchmark import run_comparative_benchmark
    from .roi import build_roi_report, evaluate_routing_state

    root = Path(repo_root or Path.cwd()).resolve()
    cfg = copy.deepcopy(DEFAULT_CONFIG if public_docs else (config or load_cortical_config()))
    if public_docs:
        cfg["privacy"]["custom_terms"] = []

    hw_data = _demo_hardware() if public_docs else copy.deepcopy(hw or _demo_hardware())
    if "classification" not in hw_data:
        hw_data["classification"] = classify_hardware_tier(hw_data)

    rec = recommend_models_for_hardware(hw_data, custom_models=cfg.get("custom_models"))
    catalog = list_all_models(custom_models=cfg.get("custom_models"))
    orch = resolve_orchestrator_spec(cfg, hw=hw_data, rec_models=rec)
    active_model = str(cfg.get("active_model") or (cfg.get("models_by_role") or {}).get("daily_coder") or "qwen3.5:9b-q3_k_xl")
    active_meta = next((m for m in catalog if m["model_id"] == active_model), {"memory_gb": 5.1, "native_ctx": 65536})
    dyn_ctx = compute_dynamic_num_ctx(
        int(active_meta.get("native_ctx") or 65536),
        active_model,
        ram_available_gb=float(hw_data.get("free_ram_gb") or 8.0),
        vram_gb=float(hw_data.get("vram_gb") or 0.0),
        unified_memory=bool(hw_data.get("unified_memory")),
        model_ram_gb=float(active_meta.get("memory_gb") or 5.1),
        total_ram_gb=float(hw_data.get("total_ram_gb") or 16.0),
        memory_pressure_level=int(hw_data.get("memory_pressure_level") or 1),
    )

    # Harnesses + drift + backups
    presend = get_harness_presend_matrix()
    paths = resolve_user_paths(os_name=os_name)
    primary_key = {
        "antigravity": "mcp", "pi": "mcp", "opencode": "opencode", "openclaw": "config",
        "codex": "config", "claude-code": "mcp", "dsh": "settings", "unsloth-studio": "manifest",
    }
    home = Path.home()
    harnesses_out: list[dict[str, Any]] = []
    backups: list[str] = []

    if not public_docs:
        bdir = Path.home() / ".cortical" / "backups"
        if bdir.is_dir():
            backups = sorted([p.name for p in bdir.iterdir() if p.is_dir()], reverse=True)[:10]

    planned_by_harness: dict[str, list[dict[str, Any]]] = {h: [] for h in ALL_HARNESSES}
    if not public_docs:
        try:
            for ch in plan_sync(cfg, hw_data, rec, repo_root=root, user_paths=paths):
                planned_by_harness.setdefault(ch.harness, []).append({
                    "path": _tilde(ch.path),
                    "action": ch.action,
                    "kind": ch.kind,
                    "detail": ch.detail,
                    "preview": (ch.content or "")[:650],
                })
        except Exception:  # noqa: BLE001
            pass

    for h in ALL_HARNESSES:
        cfg_p = paths[h][primary_key[h]]
        h_changes = planned_by_harness.get(h, [])
        pending_updates = [c for c in h_changes if c["action"] in {"create", "update"}]
        if public_docs:
            detected, linked, drift = False, False, False
            cfg_disp = "~/" + str(cfg_p.relative_to(home)) if str(cfg_p).startswith(str(home)) else str(cfg_p)
            lifecycle = "not_detected"
        else:
            exists = cfg_p.is_file()
            linked = False
            if exists:
                try:
                    linked = "cortical" in cfg_p.read_text(encoding="utf-8", errors="ignore").lower()
                except OSError:
                    linked = False
            detected = exists or (cfg_p.parent != home and cfg_p.parent.is_dir())
            enabled = bool((cfg.get("harnesses") or {}).get(h, True))
            drift = bool(detected and enabled and (not linked or len(pending_updates) > 0))
            lifecycle = (
                "linked_in_sync" if (linked and not drift)
                else ("config_drift" if drift else ("installed_unlinked" if detected else "not_detected"))
            )
            cfg_disp = _tilde(cfg_p)
        harnesses_out.append({
            "id": h,
            "detected": detected,
            "linked": linked,
            "drift": drift,
            "pending_changes": len(pending_updates),
            "planned_changes": [] if public_docs else h_changes,
            "lifecycle": lifecycle,
            "presend_verified": bool(presend.get(h, False)),
            "config_path": cfg_disp,
            "enabled": bool((cfg.get("harnesses") or {}).get(h, True)),
            "recipes": HARNESS_INSTALL_RECIPES.get(h, {}),
        })

    # Composed OSS tools
    tool_status = {} if public_docs else inspect_composed_tools()
    composers_out: list[dict[str, Any]] = []
    for cm in COMPOSER_META:
        tid = cm["id"]
        st = tool_status.get(tid) or {}
        installed = bool(st.get("installed", False)) if not public_docs else False
        composers_out.append({
            "id": tid,
            "name": cm["name"],
            "role": cm["role"],
            "installed": installed,
            "enabled": bool((cfg.get("composers") or {}).get(tid, True)),
            "binary": str(st.get("binary") or ""),
            "recipes": cm["recipes"],
        })

    # Privacy Vault metadata (NEVER raw unmasked secrets!)
    max_share = float((cfg.get("compression") or {}).get("max_context_share", 0.15))
    budget_tok = max(256, int(dyn_ctx * max_share))
    vault_aliases: list[dict[str, Any]] = []
    watch_queue = 0
    audit_ledger: dict[str, Any] = {
        "ok": True,
        "total_entries": 0,
        "blocked_egress_count": 0,
        "head_hash": "0" * 64,
        "broken_at_seq": None,
        "recent": [],
    }
    if not public_docs:
        try:
            from ..privacy.vault import PrivacyVault
            dd = default_data_dir()
            vdb = dd / "vault.db"
            if vdb.is_file():
                v = PrivacyVault(vdb)
                watch_queue = len(v.pending_inbox())
                ver = v.verify_audit_ledger()
                audit_ledger = {**ver, "recent": v.get_audit_ledger(limit=5)}
                for it in v.list_items(include_local_only=True):
                    vault_aliases.append({
                        "alias": it.get("alias", ""),
                        "uri": it.get("uri", ""),
                        "source_name": it.get("source_name", ""),
                        "profile": it.get("profile", "medium"),
                        "resolved_policy": it.get("resolved_policy", "auto"),
                        "local_only": bool(it.get("local_only", False)),
                        "entity_count": int(it.get("entity_count") or 0),
                        "tokens_est": int(it.get("tokens_est") or 0),
                        "format_used": it.get("format_used", "text"),
                        "task_tags": list(it.get("task_tags") or []),
                        "sanitized_preview": str(it.get("sanitized_content") or "")[:320] if not it.get("local_only") else "[LOCAL-ONLY max_security — masked from cloud & static preview]",
                    })
        except Exception:  # noqa: BLE001
            pass
    else:
        audit_ledger = {
            "ok": True,
            "total_entries": 14,
            "blocked_egress_count": 3,
            "head_hash": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
            "broken_at_seq": None,
            "recent": [
                {"seq": 14, "event_type": "vault_read_blocked", "harness": "remote_mcp", "alias": "demo_tax_statement", "policy": "fail_closed", "blocked_egress": True, "entity_count": 14},
            ],
        }
        vault_aliases = [
            {
                "alias": "demo_architecture_brief",
                "uri": "cortical://private/demo_architecture_brief",
                "source_name": "architecture_notes.md",
                "profile": "medium",
                "resolved_policy": "fail_closed",
                "local_only": False,
                "entity_count": 3,
                "tokens_est": 240,
                "format_used": "toon",
                "task_tags": ["architecture"],
                "sanitized_preview": "Cortical Control Plane uses Dynamic Context Scaling. Contact: [EMAIL_1], Account: [IBAN_1].",
            },
            {
                "alias": "demo_tax_statement",
                "uri": "cortical://private/demo_tax_statement",
                "source_name": "tax_2026.pdf",
                "profile": "max_security",
                "resolved_policy": "fail_closed",
                "local_only": True,
                "entity_count": 14,
                "tokens_est": 610,
                "format_used": "text",
                "task_tags": ["finance"],
                "sanitized_preview": "[LOCAL-ONLY max_security — strictly offline; blocked from remote cloud MCP]",
            },
        ]

    used_tok = sum(int(a["tokens_est"]) for a in vault_aliases if not a["local_only"])
    budget_pct = round(min(100.0, (used_tok / max(1, budget_tok)) * 100.0), 1)

    # ROI & Comparative Benchmark
    try:
        bench = run_comparative_benchmark()
    except Exception:  # noqa: BLE001
        bench = {}
    if public_docs:
        roi_data = {
            "mode": "demo",
            "local_runs": 18,
            "local_tokens": 142000,
            "estimated_usd_saved": 1.85,
            "offload_pct": 68.4,
            "cloud_remaining_tokens": 165000,
            "cloud_token_threshold": 50000,
        }
    else:
        try:
            from .roi import _estimate_cost
            dd = default_data_dir()
            rep = build_roi_report(db_path=dd / "telemetry.db")
            rstate = evaluate_routing_state(db_path=dd / "telemetry.db", config=cfg)
            glob = (rep.get("local") or {}).get("global") or {}
            ct = rep.get("current_turn") or {}
            g_in = int(glob.get("input_tokens") or 0)
            g_out = int(glob.get("output_tokens") or 0)
            g_tot = int(glob.get("total_tokens") or 0)
            roi_data = {
                "mode": "live",
                "local_runs": int(glob.get("run_count") or 0),
                "local_tokens": g_tot,
                "estimated_usd_saved": float(_estimate_cost(g_in or g_tot, 0, g_out)),
                "offload_pct": float(ct.get("offload_share_pct") or 0.0),
                "cloud_remaining_tokens": int(rstate.get("cloud_remaining_tokens") or 200000),
                "cloud_token_threshold": int(rstate.get("cloud_token_threshold") or 50000),
            }
        except Exception:  # noqa: BLE001
            roi_data = {"mode": "live", "local_runs": 0, "local_tokens": 0, "estimated_usd_saved": 0.0, "offload_pct": 0.0}

    cur_os = "macos" if platform.system() == "Darwin" else ("windows" if platform.system() == "Windows" else "linux")
    return {
        "meta": {
            "version": "0.3.0",
            "mode": "demo" if public_docs else "hydrated",
            "generated_at": time.time(),
            "os": os_name or cur_os,
            "repo_display": "<cortical-repo>" if public_docs else _tilde(root),
            "data_display": "~/Documents/Cortical",
        },
        "config": cfg,
        "hardware": {
            "total_ram_gb": float(hw_data.get("total_ram_gb") or 16.0),
            "free_ram_gb": float(hw_data.get("free_ram_gb") or 8.0),
            "unified_memory": bool(hw_data.get("unified_memory", False)),
            "vram_gb": float(hw_data.get("vram_gb") or 0.0),
            "memory_pressure_level": int(hw_data.get("memory_pressure_level") or 1),
            "gpu_name": str(hw_data.get("gpu_name") or "CPU"),
            "classification": hw_data.get("classification") or {},
            "dynamic_num_ctx": dyn_ctx,
            "active_model": active_model,
        },
        "orchestration": {
            "active": {k: v for k, v in orch.items() if k != "context_profile"},
            "presets": copy.deepcopy(ORCHESTRATOR_PRESETS),
            "context_profile": orch.get("context_profile") or {},
            "harness_matrix": _build_orchestration_matrix(orch, harnesses_out),
        },
        "models": {
            "catalog": catalog,
            "recommended_by_role": rec.get("recommended_by_role") or {},
            "installed": list(hw_data.get("installed_ollama_models") or []),
        },
        "harnesses": harnesses_out,
        "backups": backups,
        "composers": composers_out,
        "vault": {
            "default_policy": (cfg.get("privacy") or {}).get("default_policy", "auto"),
            "default_profile": (cfg.get("privacy") or {}).get("default_profile", "medium"),
            "watch_queue_count": watch_queue,
            "memory_budget_tokens": budget_tok,
            "memory_used_tokens": used_tok,
            "memory_budget_pct": budget_pct,
            "max_context_share_pct": round(max_share * 100.0, 1),
            "aliases": vault_aliases,
            "audit_ledger": audit_ledger,
            "channels": [
                {"id": 1, "name": "Channel 1 — MCP Resource Egress", "status": "enforced", "detail": "cortical://private/<alias> blocks max_security from remote cloud MCP."},
                {"id": 2, "name": "Channel 2 — Harness Sync Memory Block", "status": "enforced", "detail": f"Sanitized memory capped at <= {round(max_share*100)}% num_ctx ({budget_tok} tok)."},
                {"id": 3, "name": "Channel 3 — Pre-Send Attachment Interception", "status": "verified", "detail": f"{sum(1 for h in harnesses_out if h['presend_verified'])}/8 harnesses verified for pre-send interception."},
            ],
        },
        "roi": roi_data,
        "bench": bench,
        "adrs": scan_repo_adrs(root),
    }
