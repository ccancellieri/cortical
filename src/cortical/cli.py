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
from .analytics.dashboard import build_dashboard_env, export_static_dashboard, serve_dashboard_http
from .analytics.roi import build_roi_report, format_roi_markdown
from .analytics.tuner import analyze_and_tune
from .compression.engine import compress_structured
from .composers.tools import inspect_composed_tools, install_composed_tool, serve_mcp_http, test_composed_tool
from .integrations import SUPPORTED_TARGETS, detect_integrations, integrate_target, run_doctor_diagnostics
from .workspace import init_workspace, resolve_default_db, resolve_default_export_dir
from .config import (
    DEFAULT_VAULT_DB,
    default_data_dir,
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
from .privacy.sanitizer import FailClosedError, classify_and_sanitize
from .privacy.vault import PrivacyVault
from .wiki.store import DEFAULT_IGNORE_PATTERNS, KnowledgeStore, SANITIZABLE_BINARY_EXTENSIONS, TEXT_EXTENSIONS, _matches_ignore


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
    diag = run_doctor_diagnostics(
        project_root=Path(args.repo_root).resolve() if getattr(args, "repo_root", None) else None,
        ping_mcp=not bool(getattr(args, "no_mcp_ping", False)),
    )
    report = {
        "hardware": hw,
        "recommended_models": rec,
        "composed_tools": composed,
        "presend_interception_harnesses": presend,
        "diagnostics": diag,
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
    py_d = diag["python"]
    ws_d = diag["workspace"]
    mcp_d = diag["mcp_stdio"]
    ign_ok = [k for k, v in (diag.get("ignore_files") or {}).items() if v]
    run_ok = [k for k, v in (diag.get("local_runners") or {}).items() if v]
    print("  Diagnostics:")
    print(f"    - Python:       {py_d['version']} ({'OK' if py_d['supported'] else 'UNSUPPORTED <3.10'})")
    print(f"    - Workspace:    {ws_d['cortical_dir'] or 'not initialized'} (writable={ws_d['writable']})")
    print(f"    - MCP stdio:    {'OK (' + str(mcp_d.get('server_name') or 'cortical-mcp') + ')' if mcp_d.get('ok') else 'FAIL: ' + str(mcp_d.get('error', ''))}")
    print(f"    - Ignore files: {', '.join(ign_ok) if ign_ok else 'none'}")
    print(f"    - Runners:      {', '.join(run_ok) if run_ok else 'none'}")
    print(f"    - IDEs/Agents:  {', '.join(diag.get('detected_integrations') or []) or 'none'}")
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
        from .composers.router import start_router

        r_res = start_router(cfg, enable_in_config=True)
        if not r_res.get("ok"):
            print(f"[warn] Router start failed: {r_res.get('error')}", file=sys.stderr)

    hw = probe_hardware(os_name=args.os, runners_probe=False)
    rec = recommend_models_for_hardware(
        hw,
        custom_models=cfg.get("custom_models"),
        installed_models=hw.get("installed_ollama_models"),
    )
    vault_db = resolve_default_db(args.db)
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
    vault = PrivacyVault(resolve_default_db(args.db))
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
    if res["local_only"]:
        print("  NOTE: max_security (LOCAL-ONLY) — stored in Privacy Vault & visible in 'cortical vault list' / static settings.html; blocked from remote cloud MCP.")
    if res["requires_confirmation"]:
        print(f"  NOTE: confirmation requested ({', '.join(res.get('reasons') or [])})")
    return 0


def _cmd_vault(args: argparse.Namespace) -> int:
    vault = PrivacyVault(resolve_default_db(args.db))
    action = args.vault_action

    if action == "list":
        items = vault.list_items(include_local_only=True)
        if args.json:
            _print_json({"items": items})
            return 0
        if not items:
            print("Privacy Vault is empty. Upload files via static 'html/settings.html' or 'cortical ingest <path>'.")
            return 0
        for it in items:
            tag = "[LOCAL-ONLY max_security]" if it["local_only"] else f"[CHAT-SAFE {it['profile']}]"
            print(f"  * @private:{it['alias']:20s} {tag:26s} {it['source_name']} ({it['entity_count']} masked, {it['tokens_est']} tok, {it['format_used']})")
        return 0

    if action == "show":
        try:
            item = vault.read_resource(args.alias, allow_local_only=bool(args.local_ok))
        except (KeyError, FailClosedError) as exc:
            if args.json:
                _print_json({"ok": False, "error": str(exc)})
            else:
                print(f"[BLOCKED/MISSING] {exc} (hint: pass --local-ok to inspect local-only items offline)", file=sys.stderr)
            return 2 if isinstance(exc, FailClosedError) else 1
        if args.json:
            _print_json(item)
            return 0
        print(f"=== {item['uri']} ({item['resolved_policy']}/{item['profile']}, {item['tokens_est']} tok, {item['format_used']}) ===")
        print(item["text"])
        return 0

    if action == "update":
        terms: list[str] = []
        for raw in args.custom_term or []:
            terms.extend([t.strip() for t in raw.split(",") if t.strip()])
        try:
            res = vault.re_sanitize(
                args.alias,
                profile=args.profile,
                policy=args.policy,
                custom_terms=terms or None,
                use_local_ner=bool(args.ner),
                config=load_cortical_config(),
            )
        except KeyError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        except FailClosedError as exc:
            print(f"[FAIL-CLOSED] {exc}", file=sys.stderr)
            return 2
        if args.json:
            _print_json(res)
            return 0
        print(f"Updated {res['uri']} (policy={res['resolved_policy']}, profile={res['profile']}, masked={res['entity_count']}, tokens={res['tokens_est']})")
        return 0

    if action == "delete":
        removed = vault.delete_item(args.alias)
        if args.json:
            _print_json({"deleted": removed, "alias": args.alias})
            return 0 if removed else 1
        print(f"Deleted '{args.alias}': {removed}")
        return 0 if removed else 1

    return 1


def _cmd_intercept(args: argparse.Namespace) -> int:
    vault = PrivacyVault(resolve_default_db(args.db))
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
    out_dir = resolve_default_export_dir(args.out_dir)
    settings_path, help_path = export_static_dashboard(
        out_dir,
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


def _cmd_setup(args: argparse.Namespace) -> int:
    """One-shot, OS-neutral setup: data folder, config, harness links, static page."""
    import shutil as _sh
    data = default_data_dir()
    for sub_d in ("", "vault", "vault_inbox"):
        (data / sub_d).mkdir(parents=True, exist_ok=True)
    legacy = Path(".cortical_data") / "vault.db"
    if legacy.is_file() and not (data / "vault.db").exists():
        _sh.copyfile(legacy, data / "vault.db")
    cfg = load_cortical_config()
    cfg_path = data / "cortical.config.json"
    if not cfg_path.exists():
        save_cortical_config(cfg, config_path=cfg_path)

    env = build_dashboard_env(repo_root=Path.cwd())
    chosen = [h for h, v in env["harness_status"].items() if v["detected"]]
    hw = probe_hardware(runners_probe=True)
    rec = recommend_models_for_hardware(hw, custom_models=cfg.get("custom_models"), installed_models=hw.get("installed_ollama_models"))
    changes = plan_sync(cfg, hw, rec, harnesses=chosen, repo_root=Path.cwd().resolve(), vault_db_path=data / "vault.db")
    preview = apply_sync(changes, dry_run=True)
    print(f"Cortical data folder: {data}")
    print(f"Detected harnesses: {', '.join(chosen) or '(none)'} -> {preview['changed_count']} file(s) to update")
    do_apply = bool(args.yes)
    if not do_apply and not args.dry_run and sys.stdin.isatty():
        do_apply = input("Link these harnesses now (backup created)? [Y/n] ").strip().lower() in {"", "y", "yes", "s", "si"}
    if do_apply and not args.dry_run:
        res = apply_sync(changes)
        print(f"Linked. Backup id: {res['backup_id']} (undo: cortical sync --rollback {res['backup_id']})")
    else:
        print("Skipped linking (use --yes to apply). Re-run anytime.")
    if not args.dry_run and bool((cfg.get("router") or {}).get("enabled")):
        from .composers.router import start_router

        r_res = start_router(cfg, data, enable_in_config=False)
        print(f"Router ({r_res.get('url', '127.0.0.1:4000')}): ok={r_res.get('ok')} healthy={r_res.get('healthy', False)}")

    from .analytics.roi import export_roi_json

    PrivacyVault(data / "vault.db")._write_brain_json()
    export_roi_json(data, config=cfg)
    s_path, _h = export_static_dashboard(data, config=cfg, hw=hw, public_docs=False)
    print(f"Open this page in Chrome/Edge/Arc and click 'Choose folder' -> Documents > Cortical:\n  {s_path}")
    if not args.no_open:
        webbrowser.open(s_path.resolve().as_uri())
    return 0


def _cmd_router(args: argparse.Namespace) -> int:
    from .composers.router import ensure_litellm_installed, router_status, start_router, stop_router, write_litellm_config

    cfg = load_cortical_config()
    act = args.router_action
    if act == "setup":
        inst = ensure_litellm_installed()
        cfg_yaml = write_litellm_config(cfg)
        res = {"ok": inst.get("ok"), "bin": inst.get("bin"), "config_yaml": str(cfg_yaml), "error": inst.get("error")}
    elif act == "start":
        res = start_router(cfg, enable_in_config=True)
    elif act == "stop":
        res = stop_router()
    else:
        res = router_status(cfg)
    if args.json:
        _print_json(res)
    else:
        print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0 if res.get("ok", True) else 1


def _cmd_watch(args: argparse.Namespace) -> int:
    """Processes queued uploads (local NER / vision models) from the data folder; no ports opened."""
    import time as _t
    vault = PrivacyVault(resolve_default_db(args.db))
    print(f"Watching {vault.inbox_dir} (Ctrl+C to stop)" if not args.once else f"Processing {vault.inbox_dir}")
    try:
        while True:
            res = vault.sync_from_disk(process_inbox=True)
            if res["inbox_processed"] or res["imported"] or res["deleted"]:
                from .analytics.roi import export_roi_json

                export_roi_json(vault.db_path.parent)
                print(f"  processed={res['inbox_processed']} imported={res['imported']} deleted={res['deleted']}")
            if args.once:
                return 0
            _t.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped.")
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
    print(f"  - Lean 7-Tool MCP    : {m['tool_count']} tools · ingest+read handshake={m['handshake_ingest_read_ms']} ms")
    return 0


def _cmd_browser(args: argparse.Namespace) -> int:
    from .harnesses.chrome import (
        click_in_chrome,
        discover_chrome_profiles,
        ensure_chrome_connected,
        extract_page_and_forms,
        fill_form_and_upload,
        list_open_tabs,
        read_active_or_url_tab,
        relaunch_chrome_with_profile,
    )

    act = args.action
    if act in {"status", "profiles"}:
        _print_json(discover_chrome_profiles())
        return 0
    if act == "ensure":
        res = ensure_chrome_connected(args.profile or "ccancellieri@gmail.com", port=args.port)
        _print_json(res)
        return 0 if res.get("ok") else 1
    if act == "tabs":
        tabs = list_open_tabs(port=args.port)
        _print_json({"ok": True, "tabs": tabs, "count": len(tabs)})
        return 0
    if act == "read":
        res = read_active_or_url_tab(args.url or "", port=args.port)
        _print_json(res)
        return 0 if res.get("ok") else 1
    if act == "click":
        res = click_in_chrome(args.selector or "", url=args.url or "", port=args.port)
        _print_json(res)
        return 0 if res.get("ok") else 1
    if act == "attach":
        res = relaunch_chrome_with_profile(args.profile or "ccancellieri@gmail.com", port=args.port, target_url=args.url or "")
        _print_json(res)
        return 0 if res.get("ok") else 1
    if act == "extract":
        res = extract_page_and_forms(args.url or "", port=args.port)
        _print_json(res)
        return 0 if res.get("ok") else 1
    if act == "fill":
        fields = json.loads(args.fields_json or "{}")
        res = fill_form_and_upload(
            args.url or "",
            fields if isinstance(fields, dict) else {},
            upload_file=args.upload or "",
            submit=bool(args.submit),
            port=args.port,
        )
        _print_json(res)
        return 0 if res.get("ok") else 1
    return 1


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


def _cmd_integrate(args: argparse.Namespace) -> int:
    """Auto-detects installed IDEs/agents or idempotently injects `cortical-mcp` (or `--wiki` `cortical-wiki`) config with `.bak` backup."""
    proj = Path(args.project).resolve() if args.project else None
    if args.list or not args.target:
        items = detect_integrations(project_root=proj)
        if args.json:
            _print_json({"ok": True, "integrations": items})
            return 0
        print("Detected IDE/Agent Integrations:")
        for it in items:
            mark = "DETECTED" if it["detected"] else "available"
            loc = it["project_path"] if it["project_exists"] else (it["global_path"] or it["project_path"] or "")
            print(f"  - {it['target']:12s} [{mark:9s}] {loc}")
        return 0

    scope = "global" if args.global_scope else "project"
    try:
        res = integrate_target(
            args.target,
            scope=scope,
            server_name=args.server_name,
            wiki_server=bool(getattr(args, "wiki", False)),
            project_root=proj,
            db_path=args.db,
            dry_run=bool(args.dry_run),
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.json:
        _print_json(res)
        return 0 if res.get("ok") else 1
    if not res.get("ok"):
        print(f"Integration failed: {res.get('error')}", file=sys.stderr)
        return 1
    mode = "DRY-RUN" if res["dry_run"] else ("UPDATED" if res["changed"] else "UNCHANGED")
    print(f"Cortical Integrate [{mode}] {res['target']} ({res['scope']}) -> {res['path']}")
    if res.get("backup_path"):
        print(f"  Backup: {res['backup_path']}")
    if res["dry_run"] and res.get("diff"):
        print(res["diff"], end="")
    return 0


def _cmd_init(args: argparse.Namespace) -> int:
    """Initializes `.cortical/` workspace, `wiki.db`, `config.json`, `.gitignore` and ignore-file sync."""
    update_gitignore = not bool(args.no_gitignore)
    if update_gitignore and not args.yes and sys.stdin.isatty():
        try:
            ans = input("Add '.cortical/' to .gitignore? [Y/n] ").strip().lower()
            if ans in {"n", "no"}:
                update_gitignore = False
        except EOFError:
            pass
    res = init_workspace(
        target_dir=args.path,
        update_gitignore=update_gitignore,
        sync_ignores=not bool(args.no_sync_ignores),
    )
    if args.json:
        _print_json(res)
        return 0
    print(f"Initialized Cortical workspace: {res['cortical_dir']}")
    print(f"  - Database: {res['db_path']}")
    print(f"  - Config:   {res['config_path']}")
    print(f"  - Exports:  {res['exports_dir']}")
    print(f"  - Logs:     {res['logs_dir']}")
    if res["gitignore_updated"]:
        print("  - Updated .gitignore with '.cortical/'")
    if res["synced_ignores"]:
        print(f"  - Synced .corticalignore -> {', '.join(res['synced_ignores'])}")
    return 0


def _cmd_tools(args: argparse.Namespace) -> int:
    action = getattr(args, "tools_action", "status") or "status"
    name = getattr(args, "name", "") or ""
    os_name = getattr(args, "os", None)
    if action == "status" or not name:
        data = inspect_composed_tools(os_name=os_name)
        _print_json({"ok": True, "tools": data})
        return 0
    if action == "test":
        res = test_composed_tool(name, os_name=os_name)
        _print_json(res)
        return 0 if res.get("ok") else 1
    if action == "install":
        res = install_composed_tool(name, os_name=os_name)
        _print_json(res)
        return 0 if res.get("ok") else 1
    return 1


def _cmd_cortical_dash(args: argparse.Namespace) -> int:
    """Opens the Zero-Server Static HTML Dashboard (or interactive `--serve` HTTP server) in browser."""
    from pathlib import Path

    out_dir = resolve_default_export_dir(args.out_dir)
    open_browser = args.open
    public = args.public_docs
    serve_live = getattr(args, "serve", False)
    port = int(getattr(args, "port", 8787) or 8787)
    cfg = load_cortical_config()
    hw = probe_hardware(os_name=args.os if hasattr(args, "os") else None, runners_probe=False)

    if serve_live:
        serve_dashboard_http(out_dir, port=port, open_browser=open_browser, config=cfg, hw=hw, public_docs=public)
        return 0

    s_path, h_path = export_static_dashboard(
        output_dir=Path(out_dir),
        config=cfg,
        hw=hw,
        public_docs=public,
    )
    
    json_report = {
        "dashboard": str(s_path.resolve()),
        "help": str(h_path.resolve()),
        "exported": True,
        "public_docs": public,
    }
    
    if args.json:
        _print_json(json_report)
        return 0
    
    if open_browser:
        webbrowser.open(f"file://{s_path.parent.absolute()}/{s_path.name}")
        print(f"Opened dashboard in browser: file://{s_path.parent.absolute()}/{s_path.name}")
    else:
        print(f"Dashboard ready at: file://{s_path.parent.absolute()}/{s_path.name}")
        print(f"  - Settings UI: {s_path}")
        print(f"  - Help page:   {h_path}")
    
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

    apl = sub.add_parser("apply", help="Atomically apply a dashboard cortical-plan.json bundle (validated, single rollback snapshot)")
    apl.add_argument("plan", nargs="?", default=None, help="Path to cortical-plan.json (or inline JSON)")
    apl.add_argument("--from-clipboard", action="store_true", help="Read plan JSON from OS clipboard")
    apl.add_argument("--dry-run", action="store_true")
    apl.add_argument("--regenerate-dashboard", default=None, metavar="OUT_DIR", help="Re-export settings.html after applying")
    apl.add_argument("--json", action="store_true")
    apl.set_defaults(func=_cmd_apply)

    rec = sub.add_parser("reconcile", help="Detect and reconcile drift across models, LiteLLM router, services, and harnesses")
    rec.add_argument("--apply", action="store_true", help="Apply fixes (default is dry-run unless --apply is passed)")
    rec.add_argument("--dry-run", action="store_true", help="Preview drift without writing files")
    rec.add_argument("--json", action="store_true")
    rec.set_defaults(func=_cmd_reconcile)

    rtr = sub.add_parser("router", help="Install, configure, start/stop or inspect local LiteLLM HTTP router")
    rtr.add_argument("router_action", choices=["setup", "start", "stop", "status"])
    rtr.add_argument("--json", action="store_true")
    rtr.set_defaults(func=_cmd_router)

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

    vlt = sub.add_parser("vault", help="List, inspect, re-sanitize, or delete Privacy Vault entries (including max_security)")
    vlt_sub = vlt.add_subparsers(dest="vault_action", required=True)
    v_list = vlt_sub.add_parser("list", help="List all Vault entries including local-only max_security")
    v_list.add_argument("--db", default=None)
    v_list.add_argument("--json", action="store_true")
    v_show = vlt_sub.add_parser("show", help="Show sanitized content for an alias")
    v_show.add_argument("alias")
    v_show.add_argument("--local-ok", action="store_true", help="Allow reading max_security local-only item")
    v_show.add_argument("--db", default=None)
    v_show.add_argument("--json", action="store_true")
    v_upd = vlt_sub.add_parser("update", help="Change privacy profile or mask additional custom terms")
    v_upd.add_argument("alias")
    v_upd.add_argument("--profile", choices=["max_security", "low", "medium", "max_context"], default=None)
    v_upd.add_argument("--policy", choices=["auto", "fail_closed", "fail_open"], default=None)
    v_upd.add_argument("--custom-term", action="append", default=[])
    v_upd.add_argument("--ner", action="store_true")
    v_upd.add_argument("--db", default=None)
    v_upd.add_argument("--json", action="store_true")
    v_del = vlt_sub.add_parser("delete", help="Delete a Vault item")
    v_del.add_argument("alias")
    v_del.add_argument("--db", default=None)
    v_del.add_argument("--json", action="store_true")
    vlt.set_defaults(func=_cmd_vault)

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
    dash.add_argument("--out-dir", default=None)
    dash.add_argument("--public-docs", action="store_true")
    dash.add_argument("--open", action="store_true")
    dash.add_argument("--json", action="store_true")
    dash.set_defaults(func=_cmd_dashboard)

    ini = sub.add_parser("init", help="Initialize `.cortical/` workspace, `wiki.db`, `.gitignore` and `.corticalignore` sync")
    ini.add_argument("--path", default=None, help="Target project root (defaults to Git root or cwd)")
    ini.add_argument("-y", "--yes", action="store_true", help="Non-interactive mode (auto-update .gitignore)")
    ini.add_argument("--no-gitignore", action="store_true", help="Do not modify .gitignore")
    ini.add_argument("--no-sync-ignores", action="store_true", help="Do not sync .corticalignore to .claudeignore/.cursorignore/.geminiignore")
    ini.add_argument("--json", action="store_true")
    ini.set_defaults(func=_cmd_init)

    itg = sub.add_parser("integrate", help="Auto-detect IDEs/agents and idempotently configure Cortical MCP (`--dry-run` supported)")
    itg.add_argument("target", nargs="?", choices=list(SUPPORTED_TARGETS), default=None, help="Target IDE/agent")
    scope_grp = itg.add_mutually_exclusive_group()
    scope_grp.add_argument("--project", action="store_true", help="Write project-local config (default)")
    scope_grp.add_argument("--global", dest="global_scope", action="store_true", help="Write global user config")
    itg.add_argument("--list", action="store_true", help="List auto-detected IDE/agent integrations")
    itg.add_argument("--server-name", default="cortical-mcp", help="MCP server key name (default: cortical-mcp)")
    itg.add_argument("--wiki", action="store_true", help="Register the 5-tool cortical-wiki RAG server instead of core cortical-mcp")
    itg.add_argument("--project-dir", dest="project", default=None, help="Override project root directory")
    itg.add_argument("--db", default=None, help="Override SQLite DB path")
    itg.add_argument("--dry-run", action="store_true", help="Preview unified JSON diff without writing")
    itg.add_argument("--json", action="store_true")
    itg.set_defaults(func=_cmd_integrate)

    stp = sub.add_parser("setup", help="One-shot setup: data folder (~/Documents/Cortical), harness links & static page")
    stp.add_argument("--yes", action="store_true")
    stp.add_argument("--dry-run", action="store_true")
    stp.add_argument("--no-open", action="store_true")
    stp.set_defaults(func=_cmd_setup)

    dash = sub.add_parser("cortical", help="Open Static or Live Interactive (`--serve`) Dashboard in browser (/cortical)")
    dash.add_argument("--open", action="store_true", help="Open dashboard in default browser after export")
    dash.add_argument("--serve", action="store_true", help="Serve dashboard via local HTTP (:8787) to test & install services from UI")
    dash.add_argument("--port", type=int, default=8787, help="Port for --serve (default: 8787)")
    dash.add_argument("--out-dir", default=None, help="Output folder (defaults to .cortical/exports or html)")
    dash.add_argument("--public-docs", action="store_true", help="Export clean public version (no local config)")
    dash.add_argument("--json", action="store_true", help="Print JSON report instead of opening browser")
    dash.set_defaults(func=_cmd_cortical_dash)

    tl = sub.add_parser("tools", help="Inspect, test or install composed OSS frameworks (rtk, serena, http_router, pinchtab, ...)")
    tl.add_argument("tools_action", choices=["status", "test", "install"], default="status", nargs="?")
    tl.add_argument("name", default="", nargs="?")
    tl.add_argument("--os", choices=["macos", "linux", "windows"], default=None)
    tl.set_defaults(func=_cmd_tools)

    wch = sub.add_parser("watch", help="Process queued uploads with local models (no ports)")
    wch.add_argument("--once", action="store_true")
    wch.add_argument("--interval", type=float, default=2.0)
    wch.add_argument("--db", default=None)
    wch.set_defaults(func=_cmd_watch)

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

    br = sub.add_parser("browser", help="Autonomous Chrome (:9222) session attachment, tabs, click, extraction & authenticated form filling")
    br.add_argument("action", choices=["status", "profiles", "ensure", "tabs", "read", "click", "attach", "extract", "fill"], default="status", nargs="?")
    br.add_argument("--profile", default="ccancellieri@gmail.com")
    br.add_argument("--port", type=int, default=9222)
    br.add_argument("--url", default="")
    br.add_argument("--selector", default="")
    br.add_argument("--fields-json", default="{}")
    br.add_argument("--upload", default="")
    br.add_argument("--submit", action="store_true")
    br.set_defaults(func=_cmd_browser)

    crw = sub.add_parser("crawl", help="Recursively index a folder into wiki.db (with optional --sanitize PII/metadata masking)")
    crw.add_argument("path", help="Folder path to crawl recursively")
    crw.add_argument("--sanitize", action="store_true", help="Strip OOXML/PDF metadata and mask PII in-memory before indexing")
    crw.add_argument("--privacy-profile", choices=["max_security", "low", "medium", "max_context"], default=None)
    crw.add_argument("--custom-terms", default="", help="Comma-separated custom terms to redact/pseudonymize")
    crw.add_argument("--custom-term", action="append", default=[])
    crw.add_argument("--principal", default="local_owner")
    crw.add_argument("--namespace", default="cortical://private")
    crw.add_argument("--db", default=None)
    crw.add_argument("--dry-run", action="store_true", help="Preview scan/ignore/sanitization counts without writing wiki.db")
    crw.add_argument("--full-reindex", action="store_true")
    crw.add_argument("--json", action="store_true")
    crw.set_defaults(func=_cmd_crawl)

    san = sub.add_parser("sanitize", help="Batch-sanitize files or recursive folders to an anonymized output directory")
    san.add_argument("path", help="Source file or directory")
    san.add_argument("--recursive", action="store_true", help="Walk subdirectories recursively")
    san.add_argument("--output-dir", required=True, help="Destination directory for sanitized text/markdown files")
    san.add_argument("--privacy-profile", choices=["max_security", "low", "medium", "max_context"], default=None)
    san.add_argument("--custom-terms", default="", help="Comma-separated custom terms to mask")
    san.add_argument("--dry-run", action="store_true")
    san.add_argument("--json", action="store_true")
    san.set_defaults(func=_cmd_sanitize)

    wdash = sub.add_parser("wiki-dashboard", help="Export static zero-CDN Wiki Explorer & Sanitization Audit HTML (wiki.html)")
    wdash.add_argument("--db", default=None)
    wdash.add_argument("--out-dir", default=None)
    wdash.add_argument("--principal", default="local_owner")
    wdash.add_argument("--open", action="store_true")
    wdash.add_argument("--json", action="store_true")
    wdash.set_defaults(func=_cmd_wiki_dashboard)

    return p


def _cmd_reconcile(args: argparse.Namespace) -> int:
    from .reconcile import reconcile_all

    dry_run = not bool(args.apply) or bool(args.dry_run)
    res = reconcile_all(dry_run=dry_run)
    if args.json:
        _print_json(res)
        return 0
    mode = "DRY-RUN" if res["dry_run"] else f"APPLIED (backup={res.get('backup_id')})"
    print(f"Cortical Reconcile [{mode}]: in_sync={res['in_sync']} drift_count={res['drift_count']}")
    for m in res["models"]["drifted"]:
        print(f"  - [model] {m['role']}: {m['configured']} -> {m['replacement']} ({m['reason']})")
    if res["router"]["config_drift"]:
        print(f"  - [router] litellm_config.yaml SHA mismatch ({res['router']['disk_sha256'] or 'missing'} != {res['router']['expected_sha256']})")
    if res["router"]["runtime_drift"]:
        print(f"  - [router] missing runtime aliases: {', '.join(res['router']['missing_aliases'])}")
    for ch in res["harnesses"]["pending"]:
        print(f"  - [harness] [{ch['action']}] {ch['harness']} -> {ch['path']}")
    return 0


def _cmd_apply(args: argparse.Namespace) -> int:
    from .apply import PlanError, apply_plan, read_clipboard_text

    try:
        if args.from_clipboard:
            source: Any = read_clipboard_text()
        elif args.plan:
            source = args.plan
        else:
            print("Provide a plan path or --from-clipboard.", file=sys.stderr)
            return 2
        res = apply_plan(source, dry_run=args.dry_run, regenerate_dashboard=args.regenerate_dashboard)
    except (PlanError, FileNotFoundError) as exc:
        if args.json:
            _print_json({"ok": False, "error": str(exc)})
        else:
            print(f"[cortical apply] {exc}", file=sys.stderr)
        return 2
    if args.json:
        _print_json({"ok": True, **res})
        return 0
    mode = "DRY-RUN" if res["dry_run"] else f"APPLIED (rollback: cortical sync --rollback {res['backup_id']})"
    print(f"Cortical Apply [{mode}]: {res['changed_count']} file change(s), {len(res['vault_updates'])} vault update(s), {len(res['custom_models'])} model(s)")
    for ch in res["changes"]:
        print(f"  - [{ch['action']:9s}] {ch['harness']:15s} -> {ch['path']}")
    if res.get("dashboard"):
        print(f"  Dashboard regenerated: {res['dashboard']}")
    return 0


def _parse_custom_terms(raw_str: str = "", raw_list: Optional[list[str]] = None) -> list[str]:
    out: list[str] = []
    if raw_str:
        out.extend([s.strip() for s in raw_str.split(",") if s.strip()])
    for raw in (raw_list or []):
        out.extend([s.strip() for s in str(raw).split(",") if s.strip()])
    return list(dict.fromkeys(out))


class _CrawlProgressPrinter:
    """Stdlib-only TTY-aware progress bar showing live files/s and O(1) Merkle skip rate."""

    def __init__(self, *, enabled: bool) -> None:
        import time as _time

        self.enabled = enabled
        self.is_tty = enabled and sys.stdout.isatty()
        self.t0 = _time.perf_counter()
        self.skipped = 0
        self.last_pct = -1
        self._time = _time

    def __call__(self, ev: dict[str, Any]) -> None:
        if ev.get("action") == "unchanged":
            self.skipped += 1
        if not self.enabled:
            return
        total = max(1, int(ev.get("total") or 1))
        done = int(ev.get("processed") or 0)
        elapsed = max(0.001, self._time.perf_counter() - self.t0)
        rate = done / elapsed
        hit_pct = int((self.skipped / max(1, done)) * 100)
        pct = int((done / total) * 100)
        if self.is_tty:
            fill = int((done / total) * 20)
            bar = "#" * fill + "-" * (20 - fill)
            sys.stdout.write(f"\r[{bar}] {done}/{total} ({pct}%) | {rate:.1f} files/s | O(1) hit {hit_pct}%")
            if done >= total:
                sys.stdout.write("\n")
            sys.stdout.flush()
        elif pct >= self.last_pct + 25 or done == total:
            self.last_pct = pct
            print(f"  progress: {done}/{total} ({pct}%) | {rate:.1f} files/s | O(1) hit {hit_pct}%")


def _cmd_crawl(args: argparse.Namespace) -> int:
    target = Path(args.path).expanduser().resolve()
    if not target.is_dir():
        print(f"Directory does not exist: {target}", file=sys.stderr)
        return 1
    cfg = load_cortical_config()
    profile = args.privacy_profile or str((cfg.get("privacy") or {}).get("default_profile") or "medium")
    custom_terms = _parse_custom_terms(args.custom_terms, args.custom_term)
    db_path = resolve_default_db(args.db, start_dir=target)
    store = KnowledgeStore(db_path)

    existing_roots = [r for r in store.list_roots(principal_id=args.principal) if Path(r["path"]).resolve() == target]
    printer = _CrawlProgressPrinter(enabled=not bool(args.json))

    if args.dry_run and not existing_roots:
        res = store._crawl_single_root(
            {
                "root_id": "dry_preview",
                "path": str(target),
                "principal_id": args.principal,
                "ignore_patterns": list(DEFAULT_IGNORE_PATTERNS),
            },
            full_reindex=bool(args.full_reindex),
            embedding_model="",
            embedding_dim=0,
            sanitize=bool(args.sanitize),
            privacy_profile=profile,
            custom_terms=custom_terms or None,
            privacy_namespace=args.namespace,
            dry_run=True,
            progress_cb=printer,
        )
        summary: dict[str, Any] = {
            "roots_crawled": 1,
            "sanitized": bool(args.sanitize),
            "privacy_profile": profile if args.sanitize else "raw",
            "dry_run": True,
            **res,
            "merkle_roots": {"dry_preview": res.get("merkle_root_hash", "")},
        }
    else:
        root_id = existing_roots[0]["root_id"] if existing_roots else store.add_root(target, principal_id=args.principal)["root_id"]
        summary = store.crawl_delta(
            root_id=root_id,
            principal_id=args.principal,
            full_reindex=bool(args.full_reindex),
            sanitize=bool(args.sanitize),
            privacy_profile=profile,
            custom_terms=custom_terms or None,
            privacy_namespace=args.namespace,
            dry_run=bool(args.dry_run),
            progress_cb=printer,
        )

    summary["db_path"] = str(db_path)
    if args.json:
        _print_json(summary)
        return 0

    mode = "DRY-RUN" if summary.get("dry_run") else "INDEXED"
    san_tag = f"sanitized:{summary['privacy_profile']}" if summary.get("sanitized") else "raw"
    print(
        f"Cortical Crawl [{mode} · {san_tag}]: "
        f"{summary['files_scanned']} files scanned | {summary['files_skipped']} skipped (O(1)) | "
        f"{summary['files_sanitized']} sanitized | {summary['entities_masked_total']} PII entities masked | "
        f"{summary['metadata_stripped_count']} meta stripped | {summary['unsupported_binary']} binary skipped"
    )
    by_cat = summary.get("entities_by_category") or {}
    if by_cat:
        print("  Privacy Audit:", " | ".join(f"{k}: {v}" for k, v in sorted(by_cat.items())))
    if summary.get("errors"):
        print(f"  Errors: {summary['errors']} (check wiki-dashboard for sanitized file warnings)")
    return 0


def _cmd_sanitize(args: argparse.Namespace) -> int:
    src = Path(args.path).expanduser().resolve()
    out_dir = Path(args.output_dir).expanduser().resolve()
    cfg = load_cortical_config()
    profile = args.privacy_profile or str((cfg.get("privacy") or {}).get("default_profile") or "medium")
    custom_terms = _parse_custom_terms(args.custom_terms)
    policy = "fail_closed" if profile == "max_security" else "auto"

    if not src.exists():
        print(f"Path not found: {src}", file=sys.stderr)
        return 1

    base_root = src.parent if src.is_file() else src
    store_helper = KnowledgeStore.__new__(KnowledgeStore)
    patterns = store_helper._collect_ignore_patterns(base_root, list(DEFAULT_IGNORE_PATTERNS)) if src.is_dir() else []

    candidates: list[tuple[str, Path]] = []
    if src.is_file():
        candidates.append((src.name, src))
    elif args.recursive:
        for dirpath, dirnames, filenames in os.walk(src):
            rel_dir = os.path.relpath(dirpath, src).replace("\\", "/")
            if rel_dir == ".":
                rel_dir = ""
            dirnames[:] = [d for d in sorted(dirnames) if not _matches_ignore(f"{rel_dir}/{d}" if rel_dir else d, patterns)]
            for fn in sorted(filenames):
                rel = f"{rel_dir}/{fn}" if rel_dir else fn
                if not _matches_ignore(rel, patterns):
                    candidates.append((rel, Path(dirpath) / fn))
    else:
        for f in sorted(src.iterdir()):
            if f.is_file() and not _matches_ignore(f.name, patterns):
                candidates.append((f.name, f))

    folder_state: dict[str, Any] = {"rev": {}, "counters": {}}
    results: list[dict[str, Any]] = []
    total_entities = 0
    by_cat_total: dict[str, int] = {}
    skipped_binary = 0
    errors = 0

    for rel, fpath in candidates:
        ext = fpath.suffix.lower()
        try:
            raw_head = fpath.read_bytes()[:1024]
        except OSError as exc:
            errors += 1
            results.append({"rel_path": rel, "status": "error", "error": type(exc).__name__})
            continue
        if ext and ext not in SANITIZABLE_BINARY_EXTENSIONS and ext not in TEXT_EXTENSIONS and b"\x00" in raw_head:
            skipped_binary += 1
            results.append({"rel_path": rel, "status": "skipped_binary"})
            continue
        try:
            san = classify_and_sanitize(
                fpath,
                policy=policy,
                profile=profile,
                custom_terms=custom_terms or None,
                pseudonym_state=folder_state,
                preserve_pseudonyms=True,
            )
        except Exception as exc:  # noqa: BLE001
            errors += 1
            results.append({"rel_path": rel, "status": "error", "error": type(exc).__name__})
            continue

        out_rel = Path(rel)
        if ext in SANITIZABLE_BINARY_EXTENSIONS:
            out_rel = out_rel.with_suffix(".sanitized.md")
        dest = out_dir / out_rel
        if not args.dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(san.get("sanitized_text") or "", encoding="utf-8")

        ent_cnt = int(san.get("entity_count") or 0)
        total_entities += ent_cnt
        for cat, cnt in (san.get("entities_by_category") or {}).items():
            by_cat_total[cat] = by_cat_total.get(cat, 0) + int(cnt)
        results.append({
            "rel_path": rel,
            "output_path": str(dest),
            "status": "sanitized",
            "entity_count": ent_cnt,
            "stripped_metadata": san.get("stripped_metadata") or [],
        })

    payload = {
        "source": str(src),
        "output_dir": str(out_dir),
        "privacy_profile": profile,
        "dry_run": bool(args.dry_run),
        "files_sanitized": sum(1 for r in results if r["status"] == "sanitized"),
        "skipped_binary": skipped_binary,
        "errors": errors,
        "entities_masked_total": total_entities,
        "entities_by_category": by_cat_total,
        "files": results,
    }
    if args.json:
        _print_json(payload)
        return 0
    mode = "DRY-RUN" if args.dry_run else "WRITTEN"
    print(f"Cortical Sanitize [{mode} · {profile}]: {payload['files_sanitized']} sanitized -> {out_dir} | {total_entities} PII entities masked | {skipped_binary} binary skipped")
    return 0


def _cmd_wiki_dashboard(args: argparse.Namespace) -> int:
    from .analytics.wiki_dashboard import export_wiki_dashboard

    out_dir = resolve_default_export_dir(args.out_dir)
    db_path = resolve_default_db(args.db)
    target = export_wiki_dashboard(out_dir, db_path=db_path, principal_id=args.principal)
    if args.open:
        webbrowser.open(target.resolve().as_uri())
    if args.json:
        _print_json({"wiki_dashboard": str(target), "db_path": str(db_path)})
        return 0
    print(f"Exported Wiki Explorer & Privacy Audit dashboard -> {target}")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
