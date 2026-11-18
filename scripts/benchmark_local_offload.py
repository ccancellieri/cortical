"""Reproducible multi-model local LLM offload benchmark & telemetry runner for Cortical.

Executes a real 3-stage local reasoning loop (`router -> analyst -> reviewer`) using
Wiki `@concept:` / `@wiki:` references, Privacy Sanitizer, and dynamic `num_ctx` scaling,
recording zero-cloud-token telemetry into `agent_runs`.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from cortical.skills_hub import CorticalSkillHub  # noqa: E402
from cortical.wiki.db import CorticalWikiDB  # noqa: E402


DEFAULT_PROMPT = (
    "Analyze @concept:merkle-context-compression and @concept:zero-token-roi-analytics. "
    "Summarize in 4 concise bullets why Cortical's Zero-Server 4-Tier Merkle Wiki + Multi-Model Local Loop "
    "reduces cloud token spend and keeps sensitive files private offline. /tier:l1"
)


def run_local_offload_benchmark(
    db_path: Path,
    skills_dir: Path,
    models: list[str],
    loops: int = 3,
    max_tokens: int = 800,
    timeout: float = 90.0,
) -> dict:
    """Runs a real multi-model local offload loop and computes throughput metrics."""
    db = CorticalWikiDB(db_path)
    hub = CorticalSkillHub(db, skills_dir)
    ep_id = f"bench-local-{int(time.time())}"
    t0 = time.perf_counter()
    res = hub.run_multi_model_local_loop(
        DEFAULT_PROMPT,
        models=models,
        max_loops=loops,
        privacy_profile="medium",
        attached_files=[str(ROOT / "README.md")],
        episode_id=ep_id,
        max_tokens=max_tokens,
        timeout=timeout,
    )
    wall_sec = round(time.perf_counter() - t0, 2)
    out_tok_sum = sum(int(p.get("out_tokens_est") or 0) for p in res.get("passes", []))
    tot_tok = int(res.get("total_local_tokens") or 0)
    tok_per_sec = round(out_tok_sum / max(0.1, wall_sec), 2)
    return {
        "episode_id": ep_id,
        "models_used": res.get("models_used", []),
        "loops_executed": len(res.get("passes", [])),
        "total_local_tokens": tot_tok,
        "output_tokens_est": out_tok_sum,
        "wall_elapsed_sec": wall_sec,
        "effective_output_tok_per_sec": tok_per_sec,
        "fallback_used": res.get("fallback_used", False),
        "completed_locally": res.get("completed_locally", True),
        "distilled_insight": res.get("distilled_insight", ""),
        "passes": [
            {
                "pass": p.get("pass"),
                "model": p.get("model"),
                "role": p.get("role"),
                "elapsed_sec": p.get("elapsed_sec"),
                "in_tokens_est": p.get("in_tokens_est"),
                "out_tokens_est": p.get("out_tokens_est"),
            }
            for p in res.get("passes", [])
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark Cortical multi-model local LLM offload")
    parser.add_argument("--db", default=str(ROOT / ".cortical_data" / "wiki.db"), help="Target Wiki SQLite DB")
    parser.add_argument("--skills-dir", default=str(ROOT / ".agents" / "skills"), help="Skills directory path")
    parser.add_argument("--tmp", action="store_true", help="Run against an ephemeral temp DB instead of .cortical_data/wiki.db")
    parser.add_argument("--models", default="qwen2.5:1.5b,qwen3.5:9b-q3_k_xl,qwen3:8b", help="Comma-separated Ollama model chain")
    parser.add_argument("--loops", type=int, default=3, help="Number of local passes (default: 3)")
    parser.add_argument("--max-tokens", type=int, default=800, help="Max output tokens per pass")
    parser.add_argument("--timeout", type=float, default=90.0, help="Per-pass timeout in seconds")
    parser.add_argument("--json", action="store_true", help="Print JSON payload instead of Markdown table")
    args = parser.parse_args(argv)

    models = [m.strip() for m in str(args.models).split(",") if m.strip()]
    if args.tmp:
        with tempfile.TemporaryDirectory() as tmp:
            summary = run_local_offload_benchmark(Path(tmp) / "wiki.db", Path(args.skills_dir), models, args.loops, args.max_tokens, args.timeout)
    else:
        summary = run_local_offload_benchmark(Path(args.db), Path(args.skills_dir), models, args.loops, args.max_tokens, args.timeout)

    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0

    print(f"### Cortical Local Multi-Model Offload Benchmark (`{summary['episode_id']}`)")
    print(
        f"- **Models:** {' -> '.join(summary['models_used'])} | **Total Local Tokens:** `{summary['total_local_tokens']:,}` "
        f"| **Wall Time:** `{summary['wall_elapsed_sec']}s` | **Completed Locally:** `{summary['completed_locally']}` "
        f"| **Fallback:** `{summary['fallback_used']}`"
    )
    print("\n| Pass | Model | Role | In (est) | Out (est) | Elapsed |")
    print("| ---: | --- | --- | ---: | ---: | ---: |")
    for p in summary["passes"]:
        print(f"| {p['pass']} | `{p['model']}` | `{p['role']}` | {p['in_tokens_est']:,} | {p['out_tokens_est']:,} | {p['elapsed_sec']}s |")
    print(f"\n- **Distilled Insight:** {summary['distilled_insight']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
