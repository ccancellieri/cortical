---
name: pi-core-tools-mastery
description: >
  Use Pi's native coding and discovery tools (grep, find, ls, read, edit, write, bash),
  deferred MCP extensions (cortical-mcp, serena, chrome), and Cortical anti-regression checks
  cleanly with minimal token waste across Pi, OpenCode, Codex, and AgentSkills harnesses.
---

# Pi Core Tools Mastery (`pi-core-tools-mastery`)

## 1. Prefer Structured Native Tools Over Shell Loops
- **`find` / `ls`**: Discover file paths instead of running `find` or `ls -R` inside `bash`.
- **`grep`**: Search for exact symbols, routes, or CSS/JS IDs across `src/` and `tests/` instead of `cat` or `rg` in `bash`.
- **`read`**: Always pass `offset` / `limit` (under ~120 lines) around the matched line; never read whole large files into a local context window.
- **`edit`**: Make targeted, surgical replacements. Verify the exact target lines first with `read`.
- **`write`**: Use only for new files; use `edit` for existing files.
- **`bash`**: Reserve for running checks (`PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q`, `cortical reconcile --dry-run --json`, `git diff --stat`). Never contact external hosts.

## 2. Deferred MCP & Cross-Harness Continuity
- Prefer `tool-search` / deferred loading for `cortical-mcp` (7 core tools), `serena` (LSP symbol edits), and `chrome` (`--autoConnect`). Register `cortical-wiki` (5 RAG tools) only when `--wiki` search/Merkle crawling is needed.
- On session start or model switch, inspect `cortical_handoff(action="load")` and `docs/adr/README.md`, keep edits scoped (`<= 3` source files + `1` test file per loop), and call `cortical_handoff(action="save", ...)` when finishing a milestone.
