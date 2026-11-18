# Cortical Integrations Guide (Coding Agents, MCP Resources & Local Offload)

> **Live Site:** `https://ccancellieri.github.io/cortical/`

Cortical exposes standard **MCP (JSON-RPC 2.0 over stdio)** (Tools + `resources` + `prompts`), **Agent Skills (`SKILL.md`)**, and **Zero-Dependency CLI** interfaces so it integrates cleanly across modern coding agents and IDE harnesses without background servers.

---

## 1. MCP Server Setup Across 10+ Coding Agents & Harnesses

Use `python3 -m cortical.wiki.mcp_server` (or the installed `cortical-wiki-mcp` binary).

### Claude Code
```bash
claude mcp add cortical-wiki \
  -e PYTHONPATH=/path/to/cortical/src \
  -e CORTICAL_WIKI_DB=/path/to/cortical/.cortical_data/wiki.db \
  -- python3 -m cortical.wiki.mcp_server
```
Skills: symlink `.agents/skills/cortical-*` and `.agents/skills/second-brain-3plus1-workflow` into `~/.claude/skills/` or `.claude/skills/`.

### Antigravity / Gemini CLI (`~/.gemini/config/mcp_config.json`)
```json
{
  "mcpServers": {
    "cortical-wiki": {
      "command": "python3",
      "args": ["-m", "cortical.wiki.mcp_server"],
      "env": {
        "PYTHONPATH": "/path/to/cortical/src",
        "CORTICAL_WIKI_DB": "/path/to/cortical/.cortical_data/wiki.db"
      }
    }
  }
}
```

### OpenAI Codex CLI (`~/.codex/config.toml`)
```toml
[mcp_servers.cortical-wiki]
command = "python3"
args = ["-m", "cortical.wiki.mcp_server"]

[mcp_servers.cortical-wiki.env]
PYTHONPATH = "/path/to/cortical/src"
CORTICAL_WIKI_DB = "/path/to/cortical/.cortical_data/wiki.db"
```
Codex automatically discovers `.agents/skills/*/SKILL.md`.

### `pi` (`@earendil-works/pi-coding-agent`)
Included `package.json` (`pi-package`) auto-registers `.pi/extensions` and `.agents/skills`:
```bash
pi --package /path/to/cortical
```

### OpenCode (`opencode.json`), Cursor, Windsurf, Cline, Continue.dev & Zed
- **OpenCode:** copy `opencode.json` and Cortical skills into your workspace.
- **Cursor / Windsurf / Cline / Roo Code:** add `mcpServers.cortical-wiki` (same JSON block as above).
- **Continue.dev:** add `- name: cortical-wiki` under `mcpServers` in `~/.continue/config.yaml`.
- **Zed:** add `context_servers.cortical-wiki` in `~/.config/zed/settings.json`.

---

## 2. MCP Tools, Universal `@` / `/` Addressing & Native Resources

| Surface | Identifier / Command | Purpose |
| --- | --- | --- |
| Progressive Navigation | `wiki_navigate` (`light`/`medium`/`high`/`max`) | Traverse 4-tier Merkle tree (~50 to raw tok) |
| Full-Text Search | `wiki_search` | SQLite FTS5 search across codebase, episodes & concepts |
| Incremental Crawl | `wiki_crawl_delta` | Bottom-up `sha256` Merkle delta indexing ($O(1)$ unchanged skip) |
| Citation Check | `wiki_verify_citation` | Deterministic span + file hash verification |
| Universal Ref Resolver | `wiki_resolve_references` / `@wiki:`, `@private:`, `@concept:`, `@skill:` | Zero-path resolution & Privacy Egress Gate |
| Multi-Model Local Loop | `cortical_local_loop` / `/local` | Runs 2–3 local Ollama passes (`router -> analyst -> reviewer`) offline |
| Privacy Sanitizer | `privacy_read_sanitized` / `@private:<alias>:max_security` | OOXML/PDF metadata strip + offline pseudonymization |
| Native MCP Resources | `cortical://private/<alias>`, `cortical://node/...`, `cortical://concept/...`, `cortical://skill/...` | Standard MCP resource autocomplete without exposing raw paths |
| Native MCP Prompts | `/cortical-local`, `/cortical-wiki`, `/cortical-sanitize` | One-click harness slash prompts |
| Memory & Graph | `wiki_record_episode`, `wiki_get_knowledge_graph` | Persist episodes, insights, and Macro-Graph links |

---

## 3. Reproducible Benchmarks

```bash
# Core Merkle tree, token reduction & permission gate benchmarks
PYTHONPATH=src .venv/bin/python scripts/benchmark.py

# Multi-model local offload loop benchmark (requires local Ollama)
PYTHONPATH=src .venv/bin/python scripts/benchmark_local_offload.py
```
