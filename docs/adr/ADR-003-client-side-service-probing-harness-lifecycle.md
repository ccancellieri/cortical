# ADR-003: Client-Side Service Probing & 8-Harness Lifecycle Management

- **Status:** Accepted
- **Date:** 2026-11-23
- **GitHub Issue:** #22

## Context & Problem
Users run heterogeneous local services (Ollama on `:11434`, LiteLLM/OmniRoute on `:4000`, Unsloth Studio on `:8888`, LM Studio on `:1234`) and up to 8 coding harnesses across macOS, Linux, and Windows. Without a persistent Cortical daemon, the static dashboard still needs live visibility into installed runtimes and harness sync drift.

## Decision
1. **Direct Browser-Side Local Service Probes:** Provide a one-click **"Probe Local Services"** action that issues lightweight client-side `fetch()` requests (`GET /api/tags` for Ollama, `GET /v1/models` for OpenAI-compatible routers) with tight timeouts (`2500 ms`), clear CORS/offline diagnostics, and automatic fallback to the hydrated `cortical doctor` snapshot.
2. **Dual-Encoded 8-Harness & OSS Tool Lifecycle Matrix:** Compute per-harness drift at export time using `sync_harnesses(..., dry_run=True)` and render explicit icon+text badges (`✓ Linked & In-Sync`, `⚡ Config Drift`, `○ Installed (Unlinked)`, `— Not Detected`) plus an interactive **Install & Link Drawer** with OS-specific recipes (`macOS`/`Linux`/`Windows`), target config path preview, and idempotent diff.

## Alternatives Considered
- **Local proxy server to avoid CORS:** Violates the zero-server constraint.

## Consequences & Trade-offs
- **Pros:** Live runtime visibility when services allow localhost CORS (e.g., `OLLAMA_ORIGINS=*`), graceful zero-error fallback to `cortical doctor` snapshot when CORS is restricted or offline.
- **Cons:** Browser CORS policies on third-party local servers may block direct `fetch`, which the UI explains clearly with a 1-line `cortical doctor` / `OLLAMA_ORIGINS` hint.
