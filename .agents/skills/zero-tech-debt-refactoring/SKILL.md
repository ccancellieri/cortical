---
name: zero-tech-debt-refactoring
description: >
  Clean-code, Red-Green TDD, and Zero-Technical-Debt agentic refactoring loop. Audits real callers,
  enforces function complexity limits (Cyclomatic < 10, Cognitive < 15, LOC < 50), removes dead
  wrappers and duplicate logic, and compiles reusable SKILL.md patterns upon verified completion.
---

# Zero Technical Debt & Clean Code Refactoring (`zero-tech-debt-refactoring`)

Combines the best practices from structured agentic TDD loops (`superpowers`), `zero-tech-debt`, and Cortical's `AGENTS.md` thresholds.

## Core Mandate
Never leave behind dead wrappers, unused fallback branches, copy-pasted logic, or bloated functions just for "safety" unless an active caller or test contract explicitly requires them.

## 4-Phase Execution Loop

### 1. Audit & Caller Discovery (Second Brain First)
- Query `wiki_navigate` / `wiki_search` (at `medium` or `high` depth) and `grep`/`rg` for all real callers of the target module or symbol.
- Mark unreferenced helpers, duplicated blocks, and functions exceeding **Cyclomatic < 10**, **Cognitive < 15**, or **50 LOC** for extraction or deletion.

### 2. Red-Line Baseline & TDD Guardrail
- Run the local verification command (e.g. `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v`) **before** editing.
- If the target path lacks test coverage, write a deterministic test with JSON fixtures first (Red) before refactoring.

### 3. End-State Clean Rework
- Extract shared helpers to eliminate duplication.
- Flatten deep nesting with early returns.
- Keep edits local, scoped, and reversible (`<= 3-5` files, compact diff).

### 4. Dead-Code Deletion, Verification & Skill Distillation
- Delete obsolete code/wrappers replaced during Phase 3.
- Re-run the full verification suite and syntax checks (`node --check` if JS is touched).
- Close the task via Cortical Second Brain 3+1 synthesis (`L1/L2/L3/Max`) and, if a new repeatable refactoring pattern emerged, write/update a reusable `SKILL.md` in `.agents/skills/`.
