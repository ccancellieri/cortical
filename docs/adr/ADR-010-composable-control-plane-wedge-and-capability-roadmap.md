# ADR-010: Composable Control Plane Wedge & Top 5 Capability Roadmap

- **Status:** Proposed
- **Date:** 2026-11-23
- **GitHub Issue:** #36

## Context & Problem
The 2026 open-source AI coding agent landscape has matured into five specialized verticals:
1. **Coding Harnesses & Plugin Ecosystems:** `deepseek-ai/deepseek-harness` (`dsh` / `@deepseek-ai/cordis`), `anomalyco/opencode` (formerly `sst/opencode`), `earendil-works/pi`, `claude-code`, `codex`, `openclaw`, `unsloth-studio`, `antigravity`.
2. **Meta-Harness Wrappers & Multi-Agent Orchestrators:** `drmikecrowe/harnessed` (TUI agent containerization/sandboxing), `wanshuiyin/SuperARIS` (persistent multi-agent research teams), CLI routers.
3. **Context & Token Efficiency Layer:** `rtk-ai/rtk` (sub-10 ms shell output compression), `oraios/serena` (semantic LSP symbol navigation/editing), `mksglu/context-mode` (FTS5 subprocess output sandboxing), `LLMLingua`.
4. **Local LLM Runners & Variable Quantization:** `Ollama`, `llama.cpp`, `unslothai/unsloth` Dynamic 2.0 (`UD-IQ2_XXS`, `Q4_XXS`, `UD-Q3_K_XL`), `LM Studio`.
5. **Agent Privacy, DLP & Memory Vaults:** Microsoft `Presidio`, `Mem0`, `Zep`, `Letta`.

Each category addresses a single layer well, yet developers running mixed local + frontier coding workflows across IDEs and CLIs still lack an open, zero-daemon control plane that unifies **cross-harness declarative sync (`--rollback`) + hardware-aware variable-quant sizing + fail-closed DLP gateway + deterministic lossless `TOON` compression** with zero external Python runtime dependencies (`dependencies = []`).

## Decision
1. **Lock Cortical's Defensible Wedge:** Position Cortical strictly as the **Zero-Server, Stdlib-Only (`dependencies = []`) Cross-Harness Control Plane, Fail-Closed Privacy Gateway & Variable-Quant Composer**. Cortical does not reinvent LSPs (`Serena`), shell compressors (`RTK`), subprocess FTS5 sandboxes (`context-mode`), or inference runtimes (`Ollama`/`llama.cpp`/`Unsloth`)—it composes them uniformly across 8 harnesses while owning the four integration gaps OSS leaves open.
2. **Prioritize the Top 5 Capability Gaps:**
   - **Gap 1 — MCP 2025/2026 Schema Compliance & Streamable HTTP (`ADR-011`):** Tool `annotations`, `outputSchema` / `structuredContent`, 7-tool doc/code alignment, working `serve-mcp cortical --transport streamable-http`, and v0.3.0 registry manifests (`server.json`, `glama.json`).
   - **Gap 2 — Tamper-Evident Cryptographic Privacy & Egress Audit Ledger (`cortical vault audit`):** Append-only SHA-256 hash-chained audit trail of `fail_closed` egress blocks, stripped OOXML/PDF metadata, and PII pseudonymization counts (zero plaintext PII persisted).
   - **Gap 3 — First-Class Native Lifecycle Hooks (`dsh`, `opencode`, `pi`, `claude-code`):** Installable hook/plugin templates automating Channel 3 `cortical intercept` and `TOON` compaction on `PreToolUse` / `UserPromptSubmit` / Cordis event boundaries.
   - **Gap 4 — Portable Zero-Secret Team & Multi-Machine Profile Bundles:** Extend `cortical-plan/v1` (`ADR-008`) with `cortical profile export/import/diff` for reproducible team/dotfile sharing without credential leakage (connecting `#25`).
   - **Gap 5 — Dual Metal/VRAM Working-Set Preflight & Multi-Harness Telemetry Unification:** Enforce Metal `recommendedMaxWorkingSetSize` + discrete VRAM headroom bounds (`#43`) and normalize session token telemetry uniformly across `pi`, `claude-code`, `codex`, `opencode`, and `dsh`.

## Alternatives Considered
- **Expanding into a full agent IDE/runtime or heavyweight FastAPI platform:** Reintroduces legacy `v0.2` maintenance bloat (`#4`) and directly competes with well-funded harnesses instead of composing them.
- **Staying a thin dotfiles-only script:** Forfeits hardware-aware `num_ctx`/variable-quant fitting, deterministic `TOON`, and `fail_closed` 3-channel DLP guarantees.

## Consequences & Trade-offs
- **Pros:** Clear differentiation against every single-vertical competitor; reinforces `dependencies = []` and zero-server invariants; creates an actionable roadmap aligned with upstream ecosystem hooks (`ADR-012`).
- **Cons:** Requires strict discipline on PR scope (`<= 5` files, `AGENTS.md` / `docs/LOCAL_AGENT_HANDOFF.md`) and ongoing schema tracking across fast-moving harnesses.
