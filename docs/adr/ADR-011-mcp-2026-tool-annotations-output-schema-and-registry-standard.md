# ADR-011: MCP 2026 Tool Annotations, Output Schemas, 7-Tool Contract & Registry Metadata Standard

- **Status:** Proposed
- **Date:** 2026-11-23
- **GitHub Issue:** #37

## Context & Problem
Track 1 repository auditing surfaced four concrete MCP specification, runtime, and registry discrepancies (`#32`, `#33`, `#34`):
1. **Tool Count Drift (`7` vs `5`):** `src/cortical/mcp_server.py` (`TOOLS_SCHEMA`) exposes **7 tools** (`cortical_vault_read`, `cortical_ingest_private`, `cortical_compress`, `cortical_doctor_status`, `cortical_local_offload`, `cortical_roi_report`, `cortical_handoff`) and `cortical bench --compare` reports `tool_count: 7`, yet module docstrings, `README.md`, `docs/INTEGRATIONS.md`, and `scripts/benchmark.py` still describe "5 tools".
2. **Missing 2025/2026 MCP Annotations & `outputSchema`:** Neither `TOOLS_SCHEMA` nor `WIKI_TOOLS_SCHEMA` (`src/cortical/wiki/mcp_server.py`) declares `annotations` (`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`) or `outputSchema` + `structuredContent`.
3. **Broken `serve-mcp cortical` Streamable HTTP Bridge:** `src/cortical/composers/tools.py` invokes `python -m cortical.mcp_server --transport streamable-http --host ... --port ...`, but `src/cortical/mcp_server.py` ignores those flags and blocks on `sys.stdin`.
4. **Server Key & Registry Drift:** `cortical integrate` defaults to key `"cortical-wiki"` pointing to `cortical.mcp_server`, whereas `cortical sync` deletes `"cortical-wiki"` and writes `"cortical-mcp"`; root `opencode.json` uses a nested `"mcp": { "servers": ... }` shape incompatible with current OpenCode adapters; and external registries (Glama) still index stale `v0.1.0` `wiki.mcp` metadata because no `server.json` or `glama.json` manifest exists.

## Decision
1. **Standardize the Lean 7-Tool Core MCP Surface (`cortical-mcp`)** alongside the optional **5-Tool Wiki MCP (`cortical-wiki`)**, updating all docs, docstrings, and benchmark tables to report `7` core tools cleanly.
2. **Implement MCP 2025/2026 `annotations` & `outputSchema`:**
   - Attach accurate `annotations` (`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`) and JSON `outputSchema` to every entry in `TOOLS_SCHEMA` and `WIKI_TOOLS_SCHEMA`.
   - Return `structuredContent` alongside backward-compatible JSON `content` blocks in `tools/call` responses.
3. **Add Stdlib Streamable HTTP Transport to `cortical.mcp_server`:** Implement `--transport streamable-http --host --port` using Python stdlib `http.server.ThreadingHTTPServer` on `/mcp`, preserving `stdio` as the default zero-server mode.
4. **Unify Server Keys & Ship Registry Manifests (`0.3.0`):**
   - Default `cortical integrate` to `"cortical-mcp"` for `cortical.mcp_server` (and add `--wiki` targeting `cortical.wiki.mcp_server` as `"cortical-wiki"`).
   - Align root `opencode.json` to current OpenCode adapter output (`"mcp": { "cortical-mcp": { "type": "local", ... } }`).
   - Add `server.json` (official MCP Registry format) and `glama.json` at repo root (`0.3.0`).

## Alternatives Considered
- **Dropping `cortical_roi_report` and `cortical_handoff` to force 5 tools:** Breaks `tests/test_cortical.py` (`len(tools) == 7`) and removes zero-token ROI/handoff workflows already integrated into harness rules.
- **Adding `fastmcp` / `mcp` PyPI SDKs:** Violates Cortical's foundational `dependencies = []` (Python 3.10+ stdlib only) invariant.

## Consequences & Trade-offs
- **Pros:** Achieves full 2025/2026 MCP protocol compliance and 5/5 registry metadata readiness without adding a single external dependency; fixes `serve-mcp cortical` for `unsloth-studio` and HTTP-only clients.
- **Cons:** Increases JSON schema metadata slightly in `TOOLS_SCHEMA` (handled lazily by harnesses with deferred tool loading).
