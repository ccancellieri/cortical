#!/usr/bin/env python3
"""Cortical Overnight Loop Runner (1 Loop = 1 Fresh `pi -p --no-session` Context).

Prevents local 9B/27B context bloat (>70k tok) and premature `stop` without tool calls
by giving each Issue #6 / #7 loop a clean session, mandatory `unittest` verification,
bounded retries with exact traceback, and safe rollback if a loop cannot turn green.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VENV_PYTHON = str(REPO_ROOT / ".venv" / "bin" / "python")


@dataclass(frozen=True)
class LoopSpec:
    id: str
    issue: int
    title: str
    goal: str
    target_files: tuple[str, ...]


DEFAULT_LOOPS: list[LoopSpec] = [
    LoopSpec(
        id="4",
        issue=6,
        title="OCR & Document Scanning Robustness",
        goal=(
            "Improve error handling and batch inbox scanning diagnostics in `src/cortical/privacy/vault.py` "
            "(`sync_from_disk`) and `src/cortical/privacy/sanitizer.py` so corrupted PDFs or missing OCR models "
            "write clear actionable `.error.json` messages. Add 1 unit test in `tests/test_cortical.py`."
        ),
        target_files=("src/cortical/privacy/vault.py", "src/cortical/privacy/sanitizer.py", "tests/test_cortical.py"),
    ),
    LoopSpec(
        id="5",
        issue=7,
        title="Validated Model Inventory & Zero-400 Sync",
        goal=(
            "Implement `resolve_validated_models` in `src/cortical/hardware/models.py` and wire `plan_sync` in "
            "`src/cortical/harnesses/adapters.py` so stale uninstalled model IDs (e.g. `q4_xxs` when only `iq2_xxs` "
            "is pulled) are never written to harness configs (`pi`, Codex, OpenCode, Claude). Add 1 regression test."
        ),
        target_files=("src/cortical/hardware/models.py", "src/cortical/harnesses/adapters.py", "tests/test_cortical.py"),
    ),
    LoopSpec(
        id="6",
        issue=7,
        title="Router Config SHA-256 Auto-Reload (`cortical router ensure`)",
        goal=(
            "In `src/cortical/composers/router.py` and `src/cortical/cli.py`, store SHA-256 hash of `litellm_config.yaml` "
            "and implement `ensure_router_synced()` / `cortical router ensure` so config changes trigger stop+start "
            "and `/v1/models` verification. Add 1 unit test."
        ),
        target_files=("src/cortical/composers/router.py", "src/cortical/cli.py", "tests/test_cortical.py"),
    ),
    LoopSpec(
        id="7",
        issue=6,
        title="Community Quickstart (`README.md`) & Measured Benchmarks",
        goal=(
            "Update `README.md` with a concise, verified 60s Quickstart for Unsloth + `pi`, `/cortical-dashboard --serve`, "
            "`rtk`, `cortical tools`, and Golden Value `@private:<alias>` + `task_tags`. Use ONLY numbers printed by "
            "`cortical.cli bench --json` and `cortical.cli roi`."
        ),
        target_files=("README.md",),
    ),
]


def _run_tests() -> tuple[bool, str]:
    env = {**os.environ, "PYTHONPATH": "src"}
    res = subprocess.run(
        [VENV_PYTHON, "-m", "unittest", "tests/test_cortical.py", "-q"],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    out = ((res.stdout or "") + "\n" + (res.stderr or "")).strip()
    return res.returncode == 0, out


def _git_dirty_paths() -> set[str]:
    res = subprocess.run(["git", "status", "--porcelain"], cwd=str(REPO_ROOT), capture_output=True, text=True)
    paths: set[str] = set()
    for ln in res.stdout.splitlines():
        if len(ln) > 3:
            paths.add(ln[3:].strip())
    return paths


def _run_pi_prompt(prompt: str, provider: str, model: str, timeout_sec: int) -> tuple[int, str]:
    cmd = ["pi", "-p", "--no-session", "--provider", provider, "--model", model, prompt]
    try:
        res = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=timeout_sec)
        return res.returncode, ((res.stdout or "") + "\n" + (res.stderr or "")).strip()[-1800:]
    except subprocess.TimeoutExpired:
        return 124, f"pi timed out after {timeout_sec}s"


def _post_github_comment(issue: int, body: str) -> None:
    subprocess.run(
        ["gh", "issue", "comment", str(issue), "--body", body],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run isolated 1-loop-per-session `pi` improvements with test gate.")
    ap.add_argument("--loops", default="4,5,6,7", help="Comma-separated loop IDs to run")
    ap.add_argument("--provider", default="router")
    ap.add_argument("--model", default="cortical-fast")
    ap.add_argument("--max-retries", type=int, default=2)
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--github", action="store_true", help="Post verified loop updates to GitHub Issues")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    want = {s.strip() for s in args.loops.split(",") if s.strip()}
    plan = [lp for lp in DEFAULT_LOOPS if lp.id in want]
    if not plan:
        print("No matching loops selected.", file=sys.stderr)
        return 2

    ok_base, out_base = _run_tests()
    print(f"[baseline unittest] ok={ok_base}")
    if not ok_base:
        print(out_base)
        return 1

    if args.dry_run:
        for lp in plan:
            print(f"[dry-run] Loop #{lp.id} (Issue #{lp.issue}): {lp.title} -> {list(lp.target_files)}")
        return 0

    for lp in plan:
        print(f"\n=== Starting Loop #{lp.id}: {lp.title} ===")
        before_dirty = _git_dirty_paths()
        base_prompt = (
            f"Loop #{lp.id} (Issue #{lp.issue}): {lp.title}\n"
            f"Repo: {REPO_ROOT}\n"
            f"Goal: {lp.goal}\n"
            f"Target files only: {', '.join(lp.target_files)}\n"
            "Rules:\n"
            "- Use `.venv/bin/python`, never system python.\n"
            "- Read only targeted slices (`sed -n`), make small `edit` tool calls (no /tmp rewrite scripts!).\n"
            "- Finish by running `PYTHONPATH=src .venv/bin/python -m unittest tests/test_cortical.py -q`.\n"
        )
        t0 = time.monotonic()
        rc, pi_out = _run_pi_prompt(base_prompt, args.provider, args.model, args.timeout)
        print(f"[pi rc={rc}] {pi_out[-400:]}")

        passed, test_out = _run_tests()
        attempt = 0
        while not passed and attempt < args.max_retries:
            attempt += 1
            print(f"[retry {attempt}/{args.max_retries}] Fixing test failure...")
            fix_prompt = (
                f"Fix the test failure from Loop #{lp.id} in {', '.join(lp.target_files)}.\n"
                f"Exact unittest output:\n{test_out[-1600:]}\n"
                "Make minimal targeted `edit` changes and run `PYTHONPATH=src .venv/bin/python -m unittest tests/test_cortical.py -q`."
            )
            _run_pi_prompt(fix_prompt, args.provider, args.model, args.timeout)
            passed, test_out = _run_tests()

        elapsed = round(time.monotonic() - t0, 1)
        if not passed:
            newly_dirty = _git_dirty_paths() - before_dirty
            for rel in newly_dirty:
                if (REPO_ROOT / rel).exists():
                    subprocess.run(["git", "checkout", "--", rel], cwd=str(REPO_ROOT), check=False)
            print(f"[FAILED Loop #{lp.id} in {elapsed}s] Rolled back newly dirtied files: {sorted(newly_dirty)}")
            print(test_out[-800:])
            continue

        print(f"[PASSED Loop #{lp.id} in {elapsed}s]")
        if args.github:
            last_line = [ln for ln in test_out.splitlines() if ln.strip()][-1:] or ["OK"]
            _post_github_comment(
                lp.issue,
                f"### Automated Loop #{lp.id} ({lp.title}) — VERIFIED\n- Elapsed: `{elapsed}s` via `{args.provider}/{args.model}`\n- Tests: `{last_line[0]}`",
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
