#!/usr/bin/env python3
"""Reproducible 4-Layer Empirical Token-Efficiency Stack Benchmark (#48).

Measures real token savings on this repository (Python 3.10+ stdlib only):
  1. Symbol-level navigation (Serena-style AST symbol read vs full file read)
  2. Shell output compaction (RTK vs raw git log --stat)
  3. Structured JSON lossless compression (Cortical TOON vs pretty/compact JSON)
  4. Direct local-file offload (`cortical_local_offload(file_paths=...)` vs cloud file reads)
"""

from __future__ import annotations

import ast
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from cortical.analytics.benchmark import run_comparative_benchmark  # noqa: E402
from cortical.hardware.context_window import estimate_tokens  # noqa: E402
from cortical.mcp_server import CorticalMCPServer  # noqa: E402


def bench_symbol_vs_full_file() -> dict:
    target = ROOT / "src" / "cortical" / "privacy" / "vault.py"
    raw = target.read_text(encoding="utf-8")
    tree = ast.parse(raw)
    lines = raw.splitlines()
    sym_text = ""
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "verify_audit_ledger":
            sym_text = "\n".join(lines[node.lineno - 1 : node.end_lineno])
            break
    raw_tok = estimate_tokens(raw)
    sym_tok = estimate_tokens(sym_text)
    saving = round((1.0 - sym_tok / max(1, raw_tok)) * 100.0, 2)
    return {"file": "src/cortical/privacy/vault.py", "symbol": "verify_audit_ledger", "raw_tokens": raw_tok, "symbol_tokens": sym_tok, "saving_pct": saving}


def bench_rtk_vs_raw_shell() -> dict:
    raw_proc = subprocess.run(["git", "log", "-n", "30"], cwd=ROOT, capture_output=True, text=True, check=False)
    raw_tok = estimate_tokens(raw_proc.stdout)
    rtk_bin = shutil.which("rtk")
    if not rtk_bin:
        return {"available": False, "raw_tokens": raw_tok, "rtk_tokens": raw_tok, "saving_pct": 0.0}
    rtk_proc = subprocess.run([rtk_bin, "git", "log", "-n", "30"], cwd=ROOT, capture_output=True, text=True, check=False)
    rtk_tok = estimate_tokens(rtk_proc.stdout)
    saving = round((1.0 - rtk_tok / max(1, raw_tok)) * 100.0, 2)
    return {"available": True, "command": "git log -n 30", "raw_tokens": raw_tok, "rtk_tokens": rtk_tok, "saving_pct": saving}


def bench_toon_compression() -> dict:
    return dict(run_comparative_benchmark()["compression_before_vs_after"])


def bench_local_file_offload() -> dict:
    files = [
        str(ROOT / "src" / "cortical" / "roles.py"),
        str(ROOT / "src" / "cortical" / "privacy" / "curation.py"),
    ]
    raw_tok = sum(estimate_tokens(Path(f).read_text(encoding="utf-8")) for f in files)
    mcp = CorticalMCPServer()
    t0 = time.perf_counter()
    try:
        res = mcp._dispatch_tool(
            "cortical_local_offload",
            {
                "role": "fast_coder",
                "file_paths": files,
                "prompt": "Return 3 ultra-concise bullet points summarizing the public APIs of these 2 modules.",
            },
        )
        out_tok = estimate_tokens(str(res.get("response") or ""))
        saving = round((1.0 - out_tok / max(1, raw_tok)) * 100.0, 2)
        return {
            "available": True,
            "model_used": res.get("model_used"),
            "elapsed_sec": round(time.perf_counter() - t0, 2),
            "raw_file_tokens": raw_tok,
            "cloud_returned_tokens": out_tok,
            "cloud_input_saving_pct": saving,
        }
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "error": str(exc), "raw_file_tokens": raw_tok}


def main() -> int:
    report = {
        "layer_1_serena_symbol": bench_symbol_vs_full_file(),
        "layer_2_rtk_shell": bench_rtk_vs_raw_shell(),
        "layer_3_cortical_toon": bench_toon_compression(),
        "layer_4_local_file_offload": bench_local_file_offload(),
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
