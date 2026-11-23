# ADR-005: Opt-In Local HTTP Control Plane API & Multi-Tenant Wiki Store

- **Status:** Accepted (Opt-In `--serve` Mode; Zero-Server `ADR-001` remains canonical default)
- **Date:** 2026-11-23
- **GitHub Issue:** #10 (renumbered from duplicate ADR-001)

## Context & Problem
While Cortical's canonical mode is strictly **zero-server** (`ADR-001`, `docs/settings.html`), users who explicitly invoke interactive local workflows (`cortical dashboard --serve --port 8787`) or multi-tenant Knowledge/RAG exploration (`wiki_search`, `wiki_navigate`, `wiki_crawl_delta`, `wiki_record_episode`, `wiki_verify_citation`) need an opt-in, stdlib-only local backend without breaking the lean 7-tool `CorticalMCPServer` contract or adding external Python dependencies.

## Decision
1. **Opt-In Only (`--serve`):** Never start a background daemon or open a localhost port by default. Only `create_dashboard_server` / `serve_dashboard_http` binds `127.0.0.1:<port>` when explicitly requested.
2. **Dedicated Stdlib Multi-Tenant Wiki Engine (`src/cortical/wiki/store.py` & `src/cortical/wiki/mcp_server.py`):** Implement SQLite WAL + FTS5 + SHA-256 Merkle-tree delta crawling, strict `principal_id` RBAC (`local_owner` vs isolated scoped tenants), episodic memory, and citation verification using pure stdlib. Keep `CorticalMCPServer` at its lean 7-tool contract by default.
3. **Modular Control Plane API (`src/cortical/dashboard_api.py` & `src/cortical/dashboard_ui.py`):** Serve `/api/*` and `dashboard.html` strictly inside `--serve` mode, keeping `export_static_dashboard()` focused on zero-server `settings.html` and `help.html`.

## Consequences & Trade-offs
- **Pros:** Zero regressions on zero-server defaults (`ADR-001`) and lean MCP benchmarks; clean opt-in local RAG/Merkle control plane when desired.
- **Cons:** Two distinct UI surfaces (`settings.html` zero-server vs `dashboard.html` opt-in `--serve`), clearly separated by purpose and documented here.
