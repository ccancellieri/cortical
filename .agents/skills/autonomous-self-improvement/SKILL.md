---
name: autonomous-self-improvement
description: >
  Disciplined local autonomous loop for Analyst, Implementer, and Reviewer agents:
  locate with grep/read, apply minimal surgical edits, verify with node --check or unittest,
  and emit exact VERDICT: CONTINUE or VERDICT: DONE.
---

# Autonomous Self-Improvement (`autonomous-self-improvement`)

## 1. Role Contract
- **Analyst (`qwen2.5:1.5b`)**: Use `grep` and `read` (short slices) to identify exact file paths, line numbers, and concrete bugs/gaps. Output a 5-bullet actionable brief.
- **Implementer (`qwen3.8:27b-iq2_xs`)**: Apply at least one concrete `edit` (or `write` for new tests/skills) and run the exact verification command (`node --check ...` or `PYTHONPATH=src .venv/bin/python -m unittest ...`). Report only observed tool outputs.
- **Reviewer (`qwen2.5:1.5b`)**: Verify that an actual edit and check succeeded. If no real edit or check ran yet, end with `VERDICT: CONTINUE` naming the exact file and next step. Otherwise end with `VERDICT: DONE`.

## 2. Guardrails
- Keep changes minimal, reversible, and compatible with Pi, OpenCode, and standard MCP.
- Never run `curl`/`wget`/network calls to external hosts (blocked by Cortical Egress Guard).
