---
name: cortical-self-curated
description: Auto-curated zero-PII workflows and role-abstracted guardrails distilled from Cortical LocalBrain and verified sessions.
---

# Cortical Self-Curated Workflows

## Core Role-Abstracted Operating Rules
- Never hardcode concrete model tags in prompts or scripts; use semantic roles (`@role:router`, `@role:ner`, `@role:fast_coder`, `@role:daily_coder`, `@role:reviewer`, `@role:summarizer`, `@role:deep_reasoner`, `@role:orchestrator`, `@role:vision`).
- Offload bulk summaries, diff reviews, and private vault analysis locally via `cortical_local_offload(role=...)`.
- Compress large structured JSON/logs via `cortical_compress` (`TOON`) before passing state to a remote supervisor.
- Protect official `server.json` & `glama.json` manifests and run `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q` before committing.

## Recent Verified Session Pattern
- **Latest Verified Goal:** 10-role model abstraction, UI English alignment & Neon QA P0/P1 fixes pushed to main
- **Distilled Outcome:** Added canonical 10-role model registry (src/cortical/roles.py), wired @role: abstractions across MCP/router/harnesses/UI, aligned help.html/settings.html to English, fixed watch OCR fallback and Neon P0/P1 UI bugs; 53/53 tests OK and pushed to origin/main.

## Distilled LocalBrain Procedures

### Workflow: AGENTS.md — Cortical Architectural Rules, Code S
---
- **Reviewer Mandate:** Never rubber-stamp code because it looks clean. Verify correctness for Cortical's zero-server, stdlib-only architecture (`dependencies = []`), target hardware tiers, and fail-closed privacy guarantees.
- **Zero-Drift:** This file defines both **how agents write code** (in Antigravity, `pi`, OpenCode, Codex, Claude Code, and `dsh`) and **how reviewers verify PRs**. Detailed local-loop guardrails also live in [docs/LOCAL_AGENT_HANDOFF.md](./docs/LOCAL_AGENT_HANDOFF.md) and [docs/adr/README.md](./docs/adr/README.md).
1. **Cyclomatic Complexity < 10:** Avoid nested `if`

### Workflow: Cortical v0.3 Estado & Decisioni (2026-11-23):
1. Modelli configurabili per macchina (router :4000/v1): cortical-fast -> qwen3.5:9b-q3_k_xl, cortical-deep -> qwen3.8:27b-iq2_xxs, cortical-vision -> minicpm-ocr:latest.
2. ROI unificato in roi.py: aggrega telemetry.db + ~/.pi/agent/sessions/**/*.jsonl (>4.39M token locali, ~$13.54+ risparmiati). Badge live in ~/.pi/agent/extensions/cortical-global.ts.
3. Chrome autonomous session: chrome-devtools-mcp usa --autoConnect + chrome_tab_group per sessione; chrome.py supporta DevToolsActivePort fallback.
4. Golden Value Private Vault: upload multi-file/directory (webkitdirectory) e task_tags in das
