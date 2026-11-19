"""Cortical Unified Control Plane CLI (Zero-Dependency, Cross-Platform)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import webbrowser
from pathlib import Path
from typing import Any, Optional

from .analytics.benchmark import run_comparative_benchmark
from .analytics.dashboard import export_static_dashboard
from .analytics.roi import build_roi_report, format_roi_markdown
from .analytics.tuner import analyze_and_tune
from .compression.engine import compress_structured
from .composers.tools import inspect_composed_tools, serve_mcp_http
from .config import (
    DEFAULT_VAULT_DB,
    load_cortical_config,
    save_cortical_config,
)
from .harnesses.adapters import (
    ALL_HARNESSES,
    apply_sync,
    get_harness_presend_matrix,
    plan_sync,
    rollback_sync,
)
from .hardware.models import (
    add_custom_model,
    list_all_models,
    pull_model,
    recommend_models_for_hardware,
    remove_custom_model,
)
from .hardware.probe import probe_hardware
from .privacy.sanitizer import FailClosedError
from .privacy.vault import PrivacyVault


def _print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def _cmd_doctor(args: argparse.Namespace) -> int:
    cfg = load_cortical_config()
    hw = probe_hardware(os_name=args.os)
    rec = recommend_models_for_hardware(
        hw,
        custom_models=cfg.get("custom_models"),
        installed_models=hw.get("installed_ollama_models"),
    )
    composed = inspect_composed_tools(os_name=args.os)
    presend = get_harness_presend_matrix()
    report = {
        "hardware": hw,
        "recommended_models": rec,
        "composed_tools": composed,
        "presend_interception_harnesses": presend,
    }
    if args.out_dir:
        out = Path(args.out_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "hardware_profile.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    if args.json:
        _print_json(report)
        return 0

    cls = hw.get("classification", {})
    print(f"Cortical Doctor · OS={hw.get('os')} · Tier={cls.get('tier')} ({cls.get('label')})")
    print(
        f"  RAM: {hw.get('total_ram_gb')} GB total / {hw.get('free_ram_gb')} GB free | "
        f"Unified={hw.get('unified_memory')} | GPU={hw.get('gpu_name')} ({hw.get('vram_gb')} GB VRAM) | "
        f"Disk free={hw.get('disk_free_gb')} GB"
    )
    print(f"  Recommendation: {cls.get('recommendation')}")
    print("  Recommended Models:")
    for role, info in (rec.get("recommended_by_role") or {}).items():
        quant = info.get("quantization") or ""
        inst = "installed" if info.get("installed") else "pull needed"
        print(
            f"    - {role:14s}: {info['model_id']} ({info['memory_gb']} GB, {quant}, "
            f"num_ctx={info['recommended_num_ctx']}, {info['fit']}, {inst})"
        )
    print("  Composed OSS Tools:")
    for name, info in composed.items():
        mark = "OK" if info.get("installed") else f"missing -> {info.get('install_cmd')}"
        print(f"    - {name:12s} ({info.get('role')}): {mark}")
    return 0


def _cmd_models(args: argparse.Namespace) -> int:
    cfg = load_cortical_config()
    action = args.models_action

    if action == "list":
        models = list_all_models(cfg.get("custom_models"))
        if args.json:
            _print_json({"models": models})
            return 0
        for m in models:
            tag = " [variable-quant]" if m.get("is_variable_quant") else ""
            cust = " (custom)" if m.get("custom") else ""
            print(f"- {m['model_id']}: {m['memory_gb']} GB RAM, native_ctx={m['native_ctx']}, {m['quantization']}{tag}{cust}")
        return 0

    if action == "recommend":
        hw = probe_hardware(os_name=args.os)
        rec = recommend_models_for_hardware(
            hw,
            custom_models=cfg.get("custom_models"),
            installed_models=hw.get("installed_ollama_models"),
        )
        if args.json:
            _print_json(rec)
            return 0
        print(f"Hardware Tier: {rec['tier']} (local_llm_viable={rec['local_llm_viable']})")
        for role, info in rec["recommended_by_role"].items():
            quant = info.get("quantization") or ""
            print(f"  * {role:14s}: {info['model_id']} ({info['memory_gb']} GB, {quant}, {info['fit']}, num_ctx={info['recommended_num_ctx']})")
        if rec["to_download"]:
            print("  Pending downloads:")
            for item in rec["to_download"]:
                print(f"    {item['pull_ref']}  ({item['model_id']})")
        return 0

    if action == "add":
        roles = [r.strip() for r in (args.roles or "daily_coder").split(",") if r.strip()]
        spec = {
            "model_id": args.model_id,
            "runner": args.runner,
            "memory_gb": args.mem,
            "native_ctx": args.ctx,
            "quantization": args.quant,
            "is_variable_quant": bool(args.variable),
            "roles": roles,
            "pull_ref": args.pull_ref or args.model_id,
            "notes": args.notes or "",
        }
        entry = add_custom_model(cfg, spec)
        cfg_path = save_cortical_config(cfg)
        if args.json:
            _print_json({"saved": str(cfg_path), "model": entry})
            return 0
        print(f"Saved custom model '{entry['model_id']}' ({entry['memory_gb']} GB, {entry['quantization']}) to {cfg_path}")
        return 0

    if action == "remove":
        removed = remove_custom_model(cfg, args.model_id)
        if removed:
            save_cortical_config(cfg)
        if args.json:
            _print_json({"removed": removed, "model_id": args.model_id})
            return 0 if removed else 1
        print(f"Removed custom model '{args.model_id}': {removed}")
        return 0 if removed else 1

    if action == "pull":
        res = pull_model(args.model_id, runner=args.runner, dry_run=args.dry_run)
        if args.json:
            _print_json(res)
            return 0 if res.get("ok") else 1
        raw_cmd = res.get("command")
        cmd_str = raw_cmd if isinstance(raw_cmd, str) else " ".join(raw_cmd or [])
        print(f"Pull [{res.get('runner')}] ok={res.get('ok')} dry_run={res.get('dry_run')}: {cmd_str}")
        return 0 if res.get("ok") else 1

    return 1


def _cmd_sync(args: argparse.Namespace) -> int:
    if args.rollback:
        res = rollback_sync(args.rollback)
        if args.json:
            _print_json(res)
            return 0
        print(f"Rollback '{args.rollback}': restored={res.get('restored')} removed={res.get('removed')}")
        return 0

    cfg = load_cortical_config()
    if args.with_router:
        cfg.setdefault("router", {})
        cfg["router"]["enabled"] = True

    hw = probe_hardware(os_name=args.os, runners_probe=False)
    rec = recommend_models_for_hardware(
        hw,
        custom_models=cfg.get("custom_models"),
        installed_models=hw.get("installed_ollama_models"),
    )
    vault_db = Path(args.db or os.environ.get("CORTICAL_VAULT_DB") or DEFAULT_VAULT_DB)
    vault_md = ""
    if vault_db.is_file():
        vault = PrivacyVault(vault_db)
        eff_ctx = int(((rec.get("recommended_by_role") or {}).get("daily_coder") or {}).get("recommended_num_ctx") or 16384)
        share = float((cfg.get("compression") or {}).get("max_context_share") or 0.15)
        vault_md = vault.export_sanitized_memory_markdown(num_ctx=eff_ctx, max_share=share)

    selected = [h.strip().lower() for h in args.harness.split(",") if h.strip()] if args.harness else None
    if selected:
        unknown = [h for h in selected if h not in ALL_HARNESSES]
        if unknown:
            print(f"Unknown harnesses: {', '.join(unknown)}. Valid: {', '.join(ALL_HARNESSES)}", file=sys.stderr)
            return 2

    changes = plan_sync(
        cfg,
        hw,
        rec,
        vault_markdown=vault_md,
        harnesses=selected,
        repo_root=Path(args.repo_root).resolve(),
        vault_db_path=vault_db,
    )
    res = apply_sync(changes, dry_run=args.dry_run)
    if args.json:
        _print_json(res)
        return 0
    mode = "DRY-RUN" if res["dry_run"] else f"APPLIED (backup={res['backup_id']})"
    print(f"Cortical Sync [{mode}]: changed={res['changed_count']} unchanged={res['unchanged_count']}")
    for ch in res["changes"]:
        print(f"  - [{ch['action']:9s}] {ch['harness']:14s} -> {ch['path']} ({ch['detail']})")
    return 0


def _cmd_ingest(args: argparse.Namespace) -> int:
    vault = PrivacyVault(args.db or os.environ.get("CORTICAL_VAULT_DB") or DEFAULT_VAULT_DB)
    cfg = load_cortical_config()
    terms: list[str] = []
    for raw in args.custom_term or []:
        terms.extend([t.strip() for t in raw.split(",") if t.strip()])
    try:
        res = vault.ingest(
            args.target,
            alias=args.alias,
            policy=args.policy,
            profile=args.profile,
            custom_terms=terms or None,
            use_local_ner=bool(args.ner),
            model=args.model,
            config=cfg,
        )
    except FailClosedError as exc:
        if args.json:
            _print_json({"ok": False, "error": str(exc), "fail_closed": True})
        else:
            print(f"[FAIL-CLOSED BLOCKED] {exc}", file=sys.stderr)
        return 2

    if args.json:
        _print_json(res)
        return 0
    print(f"Ingested {res['uri']} (policy={res['resolved_policy']}, profile={res['profile']}, format={res['format_used']}, tokens={res['tokens_est']})")
    if res["requires_confirmation"]:
        print(f"  NOTE: confirmation requested ({', '.join(res.get('reasons') or [])})")
    return 0


def _cmd_intercept(args: argparse.Namespace) -> int:
    vault = PrivacyVault(args.db or os.environ.get("CORTICAL_VAULT_DB") or DEFAULT_VAULT_DB)
    try:
        res = vault.intercept_pre_send(
            args.harness,
            args.prompt,
            args.file or [],
            policy=args.policy,
            profile=args.profile,
            use_local_ner=bool(args.ner),
        )
    except FailClosedError as exc:
        _print_json({"supported": True, "blocked_raw_upload": True, "fail_closed": True, "error": str(exc)})
        return 2
    _print_json(res)
    return 0


def _cmd_compress(args: argparse.Namespace) -> int:
    raw = sys.stdin.read() if args.source == "-" else Path(args.source).read_text(encoding="utf-8", errors="ignore")
    res = compress_structured(raw, fmt=args.format, min_saving_pct=args.min_saving)
    if args.json:
        _print_json(res)
        return 0
    print(res["compressed"])
    return 0


def _cmd_serve_mcp(args: argparse.Namespace) -> int:
    try:
        res = serve_mcp_http(
            args.tool,
            Path(args.project).resolve(),
            port=args.port,
            host=args.host,
            dry_run=args.dry_run,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.json or args.dry_run:
        _print_json(res)
    return 0 if res.get("ok") else 1


def _cmd_dashboard(args: argparse.Namespace) -> int:
    cfg = load_cortical_config()
    hw = probe_hardware(runners_probe=False)
    settings_path, help_path = export_static_dashboard(
        Path(args.out_dir),
        config=cfg,
        hw=hw,
        public_docs=bool(args.public_docs),
    )
    if args.open:
        webbrowser.open(settings_path.resolve().as_uri())
    if args.json:
        _print_json({"settings": str(settings_path), "help": str(help_path)})
        return 0
    print(f"Exported zero-server dashboard -> {settings_path} & {help_path}")
    return 0


def _cmd_tune(args: argparse.Namespace) -> int:
    cfg = load_cortical_config()
    hw = probe_hardware(os_name=args.os, runners_probe=False)
    res = analyze_and_tune(config=cfg, hw=hw, apply_changes=bool(args.apply))
    if args.json:
        _print_json(res)
        return 0
    print(f"Cortical Auto-Tuner · tier={res['tier']} · applied={res['applied']} · budget={res['recommended_context_budget_tokens']} tok")
    for s in res["suggestions"]:
        print(f"  - {s}")
    return 0


def _cmd_bench(args: argparse.Namespace) -> int:
    res = run_comparative_benchmark()
    if args.json:
        _print_json(res)
        return 0
    c = res["compression_before_vs_after"]
    p = res["privacy_before_vs_after"]
    h = res["hardware_variable_quant_sizing"]
    m = res["lean_mcp"]
    print("Cortical Comparative Benchmark (Before vs After)")
    print(
        f"  - TOON Compression   : {c['raw_pretty_tokens_est']} pretty / {c['raw_compact_tokens_est']} compact -> "
        f"{c['compressed_tokens_est']} tok ({c['format_used']}, {c['saving_vs_pretty_pct']}% vs pretty, {c['saving_vs_compact_pct']}% vs compact)"
    )
    print(
        f"  - Privacy Sanitizer  : policy={p['resolved_policy']} · pii_masked={p['pii_masked']} · "
        f"tech_terms_preserved={p['technical_terms_preserved_pct']}%"
    )
    print(
        f"  - Tier 1A (4GB VRAM) : router={h['tier_1a_hybrid_4gb_vram']['router_ner']} · "
        f"daily={h['tier_1a_hybrid_4gb_vram']['daily_coder']}"
    )
    print(
        f"  - Tier 1B (16GB Unif): deep_reasoner={h['tier_1b_unified_16gb_27b']['deep_reasoner']} · "
        f"num_ctx={h['tier_1b_unified_16gb_27b']['num_ctx_27b_4bit_xxs']}"
    )
    print(f"  - Lean 5-Tool MCP    : {m['tool_count']} tools · ingest+read handshake={m['handshake_ingest_read_ms']} ms")
    return 0


def _cmd_roi(args: argparse.Namespace) -> int:
    report = build_roi_report(
        brain_dir=Path(args.brain_dir) if args.brain_dir else None,
        conversation_id=args.conversation_id,
        preset=args.preset,
    )
    if args.json:
        _print_json(report)
        return 0
    print(format_roi_markdown(report))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cortical", description="Cortical — Cross-Platform Zero-Server Agent Control Plane")
    sub = p.add_subparsers(dest="command", required=True)

    doc = sub.add_parser("doctor", help="Inspect OS, RAM/VRAM, GPUs, OSS tools, runners & recommended models")
    doc.add_argument("--os", choices=["macos", "linux", "windows"], default=None)
    doc.add_argument("--out-dir", default=None)
    doc.add_argument("--repo-root", default=".")
    doc.add_argument("--json", action="store_true")
    doc.set_defaults(func=_cmd_doctor)

    mod = sub.add_parser("models", help="Inspect, recommend, configure custom/variable-quant models & pull")
    mod_sub = mod.add_subparsers(dest="models_action", required=True)
    m_list = mod_sub.add_parser("list", help="List built-in and custom models")
    m_list.add_argument("--json", action="store_true")
    m_rec = mod_sub.add_parser("recommend", help="Recommend role-based models for detected hardware")
    m_rec.add_argument("--os", choices=["macos", "linux", "windows"], default=None)
    m_rec.add_argument("--json", action="store_true")
    m_add = mod_sub.add_parser("add", help="Add or update a custom/variable-quant model")
    m_add.add_argument("model_id")
    m_add.add_argument("--mem", type=float, required=True, help="Actual memory footprint in GB")
    m_add.add_argument("--ctx", type=int, default=32768)
    m_add.add_argument("--quant", default="custom")
    m_add.add_argument("--variable", action="store_true", help="Mark as Unsloth variable quantization")
    m_add.add_argument("--roles", default="daily_coder,deep_reasoner")
    m_add.add_argument("--runner", default="ollama")
    m_add.add_argument("--pull-ref", default=None)
    m_add.add_argument("--notes", default="")
    m_add.add_argument("--json", action="store_true")
    m_rm = mod_sub.add_parser("remove", help="Remove a custom model")
    m_rm.add_argument("model_id")
    m_rm.add_argument("--json", action="store_true")
    m_pull = mod_sub.add_parser("pull", help="Pull a local model via Ollama")
    m_pull.add_argument("model_id")
    m_pull.add_argument("--runner", default="ollama")
    m_pull.add_argument("--dry-run", action="store_true")
    m_pull.add_argument("--json", action="store_true")
    mod.set_defaults(func=_cmd_models)

    syn = sub.add_parser("sync", help="Idempotently compose and sync config/rules/skills across 8 harnesses")
    syn.add_argument("--harness", default=None, help=f"Comma-separated harnesses ({','.join(ALL_HARNESSES)})")
    syn.add_argument("--dry-run", action="store_true")
    syn.add_argument("--rollback", default=None, help="Restore exact files from a backup ID")
    syn.add_argument("--os", choices=["macos", "linux", "windows"], default=None)
    syn.add_argument("--repo-root", default=".")
    syn.add_argument("--db", default=None)
    syn.add_argument("--with-router", action="store_true")
    syn.add_argument("--json", action="store_true")
    syn.set_defaults(func=_cmd_sync)

    ing = sub.add_parser("ingest", help="Ingest a file or text into the encrypted-metadata-stripped Privacy Vault")
    ing.add_argument("target")
    ing.add_argument("--alias", default=None)
    ing.add_argument("--policy", choices=["auto", "fail_closed", "fail_open"], default="auto")
    ing.add_argument("--profile", choices=["max_security", "low", "medium", "max_context"], default="medium")
    ing.add_argument("--custom-term", action="append", default=[])
    ing.add_argument("--ner", action="store_true", help="Enable offline local LLM JSON NER")
    ing.add_argument("--model", default=None)
    ing.add_argument("--db", default=None)
    ing.add_argument("--json", action="store_true")
    ing.set_defaults(func=_cmd_ingest)

    ic = sub.add_parser("intercept", help="Channel 3 pre-send attachment interceptor for verified harnesses")
    ic.add_argument("--harness", required=True)
    ic.add_argument("--prompt", default="")
    ic.add_argument("--file", action="append", default=[])
    ic.add_argument("--policy", choices=["auto", "fail_closed", "fail_open"], default="auto")
    ic.add_argument("--profile", choices=["max_security", "low", "medium", "max_context"], default="medium")
    ic.add_argument("--ner", action="store_true")
    ic.add_argument("--db", default=None)
    ic.set_defaults(func=_cmd_intercept)

    comp = sub.add_parser("compress", help="Deterministic lossless TOON/JSON/XML/YAML/Log compression")
    comp.add_argument("source", help="Input file path or '-' for stdin")
    comp.add_argument("--format", choices=["auto", "json", "xml", "yaml", "log"], default="auto")
    comp.add_argument("--min-saving", type=float, default=10.0)
    comp.add_argument("--json", action="store_true")
    comp.set_defaults(func=_cmd_compress)

    srv = sub.add_parser("serve-mcp", help="On-demand foreground Streamable HTTP bridge for Serena or Cortical MCP")
    srv.add_argument("tool", choices=["serena", "cortical"])
    srv.add_argument("--project", default=".")
    srv.add_argument("--port", type=int, default=9121)
    srv.add_argument("--host", default="127.0.0.1")
    srv.add_argument("--dry-run", action="store_true")
    srv.add_argument("--json", action="store_true")
    srv.set_defaults(func=_cmd_serve_mcp)

    dash = sub.add_parser("dashboard", help="Export self-contained zero-server static HTML settings & help UI")
    dash.add_argument("--out-dir", default="html")
    dash.add_argument("--public-docs", action="store_true")
    dash.add_argument("--open", action="store_true")
    dash.add_argument("--json", action="store_true")
    dash.set_defaults(func=_cmd_dashboard)

    tun = sub.add_parser("tune", help="Local zero-cloud-token Auto-Tuner for models, num_ctx & context budget")
    tun.add_argument("--apply", action="store_true")
    tun.add_argument("--os", choices=["macos", "linux", "windows"], default=None)
    tun.add_argument("--json", action="store_true")
    tun.set_defaults(func=_cmd_tune)

    bnc = sub.add_parser("bench", help="Run before-vs-after comparative TOON, Privacy & Context benchmarks")
    bnc.add_argument("--compare", action="store_true")
    bnc.add_argument("--json", action="store_true")
    bnc.set_defaults(func=_cmd_bench)

    ro = sub.add_parser("roi", help="Zero-cloud-token ROI & token consumption report")
    ro.add_argument("--conversation-id", default=None)
    ro.add_argument("--brain-dir", default=None)
    ro.add_argument("--preset", default="cloud_standard")
    ro.add_argument("--json", action="store_true")
    ro.set_defaults(func=_cmd_roi)

    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
