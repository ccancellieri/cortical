# AGENTS.md — Cortical Architectural Rules, Code Standards & Zero-Drift Review Contract

> **Golden Rule:** A contribution must be worth more than the time required to review it.

---

## 1. Reviewer Mandate & Zero-Drift Contract
- **Reviewer Mandate:** Never rubber-stamp code because it looks clean. Verify correctness for Cortical's zero-server, stdlib-only architecture (`dependencies = []`), target hardware tiers, and fail-closed privacy guarantees.
- **Zero-Drift:** This file defines both **how agents write code** (in Antigravity, `pi`, OpenCode, Codex, Claude Code, and `dsh`) and **how reviewers verify PRs**. Detailed local-loop guardrails also live in [docs/LOCAL_AGENT_HANDOFF.md](./docs/LOCAL_AGENT_HANDOFF.md) and [docs/adr/README.md](./docs/adr/README.md).

## 2. Mandatory Function Complexity Thresholds
1. **Cyclomatic Complexity < 10:** Avoid nested `if`/`elif` chains and deep loops.
2. **Cognitive Complexity < 15:** Keep control flow immediately clear to human and local-LLM reviewers.
3. **Function Size 20–50 LOC:** Respect Single Responsibility; extract pure helpers when functions grow past 50 lines.

## 3. Pull Request Contract & Diff Cap
- **Compact Diff:** `<= 150–250` lines of effective diff and `<= 3–5` files per atomic PR.
- **Single Intent:** Never mix bug fixes, aesthetic refactors, and unrelated features; start PR titles with an imperative verb (`feat:`, `fix:`, `docs:`).
- **Issue Alignment:** Explicitly verify the change resolves the linked GitHub Issue (`docs/adr/` + `gh issue view`).

## 4. Tech Stack & Invariants (Cortical v0.3.0)
- **Runtime:** Python 3.10+ stdlib ONLY (`dependencies = []` in `pyproject.toml`), SQLite WAL thread-safe storage, Zero-Server default (`stdio` MCP + static `docs/settings.html`; `--transport streamable-http` and `--serve` strictly opt-in).
- **7 Subpackages (`src/cortical/`):** `hardware`, `harnesses`, `composers`, `privacy`, `compression`, `analytics`, `wiki` (+ `cli.py`, `mcp_server.py`, `apply.py`, `reconcile.py`, `integrations.py`, `workspace.py`, `config.py`).
- **MCP Surface:** Lean 7-tool `cortical-mcp` (`annotations` + `outputSchema` + `structuredContent`, native `resources`/`prompts`/`completions`) + opt-in 5-tool `cortical-wiki` (`--wiki`).
- **Privacy Vault:** Always enforce `fail_closed` on `max_security` items; never read raw `.cortical_data/` or `~/Documents/Cortical/vault/`.
- **Single-Shot Verification:** Always run `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q` and `PYTHONPATH=src .venv/bin/python -m cortical.cli reconcile --dry-run --json`.

## 5. Cross-Harness Collaboration, Shared Skills & Chrome (`:9222`)
- **Shared Skills (`.agents/skills/`):** Discovered natively by `pi`, `OpenCode`, `Codex`, `Claude Code`, and `Antigravity`. Read relevant `SKILL.md` files before editing.
- **Local Offload & Cross-Harness Handoff:** Prefer `cortical_local_offload` (`qwen3.5:9b-q3_k_xl` / `qwen3.8:27b-iq2_xxs`) for boilerplate/drafting/reviews (`$0` cloud cost) and `cortical_handoff(action='save'|'load')` when switching between Antigravity, `pi`, OpenCode, Claude Code, and Codex.
- **Chrome Remote Debugging (`:9222`):** Non-destructive `--autoConnect` + Task Tab Groups via `cortical browser status` / `chrome-devtools` MCP; never kill personal browser sessions.
