---
name: pi-core-tools-mastery
description: >
  Use Pi's native coding and discovery tools (grep, find, ls, read, edit, write, bash)
  and deferred MCP extensions (tool-search, mcp) cleanly with minimal token waste.
  Compatible with Pi, Codex, OpenClaw, and AgentSkills-compliant harnesses.
---

# Pi Core Tools Mastery (`pi-core-tools-mastery`)

## 1. Prefer Structured Native Tools Over Shell Loops
- **`find` / `ls`**: Discover file paths instead of running `find` or `ls -R` inside `bash`.
- **`grep`**: Search for exact symbols, routes, or CSS/JS IDs across `src/` and `tests/` instead of `cat` or `rg` in `bash`.
- **`read`**: Always pass `offset` / `limit` (under ~120 lines) around the matched line; never read whole large files into an 8K context.
- **`edit`**: Make targeted, surgical replacements. Verify the exact target lines first with `read`.
- **`write`**: Use only for new files; use `edit` for existing files.
- **`bash`**: Reserve for running checks (`node --check`, `.venv/bin/python -m unittest ...`), git status/diff, or local service checks. Never contact external hosts.

## 2. Deferred MCP & Tool Search
- Use `tool-search` to discover deferred tools on `cortical-wiki` (16 tools) or `chrome` (30 tools) only when needed.
- Never load all MCP schemas upfront when working on a local code edit.
