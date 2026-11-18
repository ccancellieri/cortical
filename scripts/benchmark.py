"""Reproducible, zero-cloud-token benchmark suite for Cortical core modules.

Measures:
  1. 4-Tier Merkle Second Brain crawl & O(1) delta skip latency
  2. Progressive token reduction (light/medium/high vs raw max)
  3. Adaptive Permission Gate deterministic evaluation latency
  4. Dynamic 200k context window scaling across RAM profiles
  5. Optional live Ollama throughput (--ollama)
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from cortical.context_window import compute_dynamic_num_ctx, estimate_tokens  # noqa: E402
from cortical.permissions.gate import AdaptivePermissionGate  # noqa: E402
from cortical.wiki.crawler import DeterministicMerkleCrawler  # noqa: E402
from cortical.wiki.db import AccessContext, CorticalWikiDB, DepthTier  # noqa: E402


def run_core_benchmarks(target_dir: Path) -> dict:
    """Runs deterministic, reproducible benchmarks on `target_dir`."""
    with tempfile.TemporaryDirectory() as tmp:
        tpath = Path(tmp)
        db = CorticalWikiDB(str(tpath / "bench.db"))
        ctx = AccessContext()
        crawler = DeterministicMerkleCrawler(db)

        t0 = time.perf_counter()
        s1 = crawler.crawl_directory(str(target_dir))
        crawl_ms = (time.perf_counter() - t0) * 1000.0

        t0 = time.perf_counter()
        crawler.crawl_directory(str(target_dir))
        delta_ms = (time.perf_counter() - t0) * 1000.0

        nav_light = db.navigate(ctx, "/", DepthTier.LIGHT)
        raw_files = list(target_dir.rglob("*.py"))
        raw_bytes = sum(p.stat().st_size for p in raw_files)
        raw_tok_est = raw_bytes // 4
        light_tok = estimate_tokens(json.dumps(nav_light))

        largest_py = max(raw_files, key=lambda p: p.stat().st_size) if raw_files else None
        single_file_stats = {}
        if largest_py is not None:
            rel_path = "/" + str(largest_py.relative_to(target_dir)).replace("\\", "/")
            med_tok = estimate_tokens(json.dumps(db.navigate(ctx, rel_path, DepthTier.MEDIUM)))
            high_tok = estimate_tokens(json.dumps(db.navigate(ctx, rel_path, DepthTier.HIGH)))
            max_tok = estimate_tokens(json.dumps(db.navigate(ctx, rel_path, DepthTier.MAX)))
            single_file_stats = {
                "file": rel_path,
                "medium_tokens": med_tok,
                "high_tokens": high_tok,
                "max_tokens": max_tok,
                "medium_reduction_pct": round((1.0 - med_tok / max(1, max_tok)) * 100.0, 2),
                "high_reduction_pct": round((1.0 - high_tok / max(1, max_tok)) * 100.0, 2),
            }

        gate = AdaptivePermissionGate(str(tpath / "perm.db"))
        cmds = ["ls -la", ".venv/bin/python -m unittest discover -s tests -q", "curl https://example.com", "rm -rf /"]
        t0 = time.perf_counter()
        iters = 100
        for _ in range(iters):
            for c in cmds:
                gate.evaluate("bash", {"command": c})
        gate_us = ((time.perf_counter() - t0) / (iters * len(cmds))) * 1e6

        return {
            "target_dir": str(target_dir),
            "files_scanned": s1.files_scanned,
            "cold_crawl_ms": round(crawl_ms, 2),
            "delta_unchanged_ms": round(delta_ms, 2),
            "raw_repo_tokens_est": raw_tok_est,
            "root_light_tokens": light_tok,
            "root_light_reduction_pct": round((1.0 - light_tok / max(1, raw_tok_est)) * 100.0, 2),
            "largest_file": single_file_stats,
            "permission_gate_eval_us": round(gate_us, 1),
            "dynamic_ctx_scaling": {
                "qwen3.5_9b_4gb_free": compute_dynamic_num_ctx(131072, "qwen3.5:9b-q3_k_xl", ram_available_gb=4.0),
                "qwen3.5_9b_16gb_free": compute_dynamic_num_ctx(131072, "qwen3.5:9b-q3_k_xl", ram_available_gb=16.0),
                "qwen3.8_27b_8gb_free": compute_dynamic_num_ctx(32768, "qwen3.8:27b-iq2_xxs", ram_available_gb=8.0),
            },
        }


def run_ollama_benchmark(models: list[str]) -> list[dict]:
    """Optional live local Ollama throughput check."""
    results = []
    for m in models:
        t0 = time.time()
        try:
            req = urllib.request.Request(
                "http://127.0.0.1:11434/api/chat",
                data=json.dumps({
                    "model": m,
                    "stream": False,
                    "think": False,
                    "messages": [{"role": "user", "content": "Explain a Merkle tree in one sentence."}],
                    "options": {"num_predict": 60, "temperature": 0.1},
                }).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            ec = int(data.get("eval_count") or 0)
            ed = float(data.get("eval_duration") or 1) / 1e9
            ld = float(data.get("load_duration") or 0) / 1e9
            results.append({
                "model": m,
                "load_sec": round(ld, 2),
                "eval_tokens": ec,
                "tokens_per_sec": round(ec / max(ed, 0.01), 1),
                "wall_sec": round(time.time() - t0, 2),
            })
        except Exception as exc:  # noqa: BLE001
            results.append({"model": m, "error": str(exc)})
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Reproducible Cortical Benchmark Suite")
    parser.add_argument("--dir", default=str(ROOT / "src" / "cortical"), help="Directory to crawl/benchmark")
    parser.add_argument("--ollama", nargs="*", default=None, help="Optional Ollama model IDs to benchmark")
    args = parser.parse_args()

    out = {"core": run_core_benchmarks(Path(args.dir))}
    if args.ollama is not None:
        models = args.ollama or ["qwen3.5:9b-q3_k_xl", "qwen3:8b", "qwen3.8:27b-iq2_xxs"]
        out["ollama"] = run_ollama_benchmark(models)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
