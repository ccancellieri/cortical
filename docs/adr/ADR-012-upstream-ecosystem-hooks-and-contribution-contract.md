# ADR-012: Upstream Ecosystem Hooks & High-Leverage OSS Contribution Contract

- **Status:** Proposed
- **Date:** 2026-11-23
- **GitHub Issue:** #38

## Context & Problem
Cortical composes best-of-breed OSS tools (`Serena`, `RTK`, `context-mode`, `PinchTab`, `LiteLLM` / `OmniRoute` / `claude-code-router`, `Ollama` / `Unsloth`) across 8 coding harnesses (`antigravity`, `pi`, `opencode`, `openclaw`, `codex`, `claude-code`, `dsh`, `unsloth-studio`) and meta-harness orchestrators (`drmikecrowe/harnessed`). Connecting Cortical to these upstream communities organically requires strict contribution hygiene so PRs and ecosystem plugins are welcomed by maintainers rather than treated as promotional noise.

## Decision
1. **Upstream Value-First Contract:** Every upstream contribution MUST deliver standalone value to the host project's users first:
   - Solve a concrete host problem (e.g., preventing `4096` silent Ollama `num_ctx` clipping or 16 GB OOMs on `UD-IQ2_XXS`/`Q4_XXS`; adding pre-send PII/secret redaction hooks before cloud dispatch; providing reproducible multi-layer token benchmarks combining `Serena + RTK + context-mode + TOON`).
   - Never inject intrusive marketing copy or mandatory dependencies on Cortical into upstream core binaries; integrate via documented plugin registries, MCP config recipes, optional callbacks, or benchmarks/docs PRs.
2. **Thin Non-Invasive Hook Packaging:** Keep harness-specific extension code (`pi` `.pi/extensions/`, `dsh` Cordis config, `opencode` command/plugin recipes, `claude-code` `PreToolUse` hook scripts) decoupled from Cortical's zero-dependency Python core (`pyproject.toml` `dependencies = []`).
3. **Three-Wave Execution Strategy:**
   - **Wave 1 (Discovery & Native Harness Ecosystem):** Refresh MCP Registry & Glama (`server.json`, `glama.json`, `modelcontextprotocol/servers`, `awesome-mcp-servers`), polish `earendil-works/pi` package (`cortical://private/<alias>` autocompletion + Channel 3 extension), contribute `deepseek-ai/deepseek-harness` (`dsh`) Cordis MCP + pre-send hook recipe, and contribute `anomalyco/opencode` (formerly `sst/opencode`) MCP + privacy interceptor command/plugin guide.
   - **Wave 2 (Composable Token Stack & Meta-Harnesses):** Publish reproducible `Serena + RTK + context-mode + Cortical TOON` stack benchmarks & interop PRs, and propose Cortical as the optional declarative DLP + hardware quant auto-tuner layer for `drmikecrowe/harnessed`.
   - **Wave 3 (Local Quant Sizing & Privacy Routing):** Contribute hardware preflight + dynamic `num_ctx` sizing recipes for `unslothai/unsloth` Dynamic 2.0 / Ollama users, and optional `fail_closed` privacy pre-call hooks for `LiteLLM` / `OmniRoute` / `claude-code-router`.

## Alternatives Considered
- **Publishing uncoordinated wrapper forks or spammy "Awesome list" only links:** Low engineering credibility and high rejection rate without working hooks or reproducible benchmarks.
- **Tightly coupling Cortical Python code to Node/Rust plugin SDKs:** Violates cross-platform `dependencies = []` portability.

## Consequences & Trade-offs
- **Pros:** Drives organic adoption via real utility in 8+ thriving communities; validates Cortical's schemas against real upstream maintainers.
- **Cons:** Requires maintaining compatibility examples/hooks as upstream plugin APIs evolve (`dsh`, `opencode`, `pi`).
