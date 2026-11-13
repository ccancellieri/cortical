---
name: generic-autonomous-loop
description: >
  Domain-agnostic autonomous multi-step execution loop (Plan -> Act -> Verify -> Learn) for coding,
  browser automation, research, and local computer workflows. Guided by domain skill checks,
  AdaptivePermissionGate, max_agent_loops, and AGENTS.md complexity/PR constraints.
---

# Generic Autonomous Loop (`generic-autonomous-loop`)

A reusable, zero-dependency execution protocol compatible with **`pi`** and **`OpenCode`** (`agentskills.io`).
Never hardcode domain checks (e.g. `unittest` or browser automation) into the orchestrator: derive them dynamically from the active task context and matched domain skills.

## Cycle (`<= max_agent_loops`)

1. **Plan (Context & Scope)**
   - Select the right Wiki depth (`light` / `medium` / `high`) and inspect attached scoped context only.
   - Identify the explicit completion criteria and deterministic verification command(s) for the domain:
     - **Coding / Refactor:** targeted unit/integration test suite (`.venv` on Python projects), complexity check (`Cyclomatic < 10`, `Cognitive < 15`, `LOC < 50`), syntax verification (`node --check`).
     - **Browser / Web UI:** ensure Chrome Remote Debugging on `127.0.0.1:9222` (`cortical chrome-ensure` or `chrome_ensure_debug` MCP tool — reuse if already active, else spawn isolated debug instance), then verify DOM/title/URL/console state.
     - **Research / Knowledge:** verify every factual claim via `wiki_verify_citation` before final reporting.
     - **Local System / Computer Ops:** verify filesystem/exit-code postconditions cleanly.
2. **Act (Gated Execution)**
   - Apply minimal, targeted edits or commands permitted by `AdaptivePermissionGate`.
   - Respect zero-drift rules defined in `AGENTS.md`.
3. **Verify (Deterministic Check)**
   - Run the domain's verification check and observe real output.
   - If verification fails, inspect the exact error, form a single root-cause hypothesis, and iterate without repeating blind retries.
4. **Learn & Close**
   - Summarize outcome concisely in 3+1 levels (`L1` / `L2` / `L3` / `Max`).
   - If the solved workflow established a repeatable pattern, propose or compile a concise `.agents/skills/<slug>/SKILL.md` (compatible with both `pi` and `OpenCode`).
