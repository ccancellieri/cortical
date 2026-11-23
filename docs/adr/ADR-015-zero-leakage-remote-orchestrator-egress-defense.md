# ADR-015: Zero-Leakage Remote Orchestrator Egress Defense (`fail_closed` Vault + 3-Channel Isolation)

- **Status:** Accepted
- **Date:** 2026-11-23
- **GitHub Issue:** #56 (EPIC: #57)

## Context & Problem
Selecting a Remote Cloud Orchestrator (`Gemini`, `Claude`, `OpenAI`, `DeepSeek`, `OpenRouter`, or external endpoints) introduces the risk that private Vault entries, unmasked PII/secrets, or workspace attachments might accidentally traverse MCP reads, synced rule blocks, or chat prompts to remote APIs.

## Decision
Enforce strict defense-in-depth `fail_closed` egress protection whenever `remote_orchestrator_active(config)` is True (`orchestrator.mode == "remote"`):
1. **Channel 1 (`cortical://private/<alias>` & `cortical_vault_read`):** Propagate `remote_egress=True` into `PrivacyVault.read_resource` and `read_task_context`. Block all `max_security` (`local_only`) items AND re-verify `fail_closed` items for zero unmasked PII residuals before permitting remote MCP reads—raising `FailClosedError` with explicit guidance to process locally via `cortical_local_offload(vault_alias=...)`.
2. **Channel 2 (`cortical sync` Memory Injection):** When `remote_egress=True`, emit only verified zero-residual-PII sanitized summaries (`<= 15% num_ctx`) and inject `[ZERO-LEAKAGE REMOTE ORCHESTRATOR GUARD]` + Local-First Delegation directives across all 8 harness instruction files (`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`).
3. **Channel 3 (`cortical intercept` Pre-Send Gate):** Automatically detect `remote_orchestrator_active(cfg)`, upgrade policy to `fail_closed` if PII/secrets are detected in the prompt or attached files, strip raw payload text from `proposed_remote_prompt` when `local_only` or `fail_closed` triggers, and emit local-only `@private:<alias>` offload stubs with `"remote_egress_guarded": True`.

## Consequences & Trade-offs
- **Pros:** Guarantees that raw private information never leaves the workstation even when developers orchestrate tasks with frontier remote models.
- **Cons:** In remote mode, `fail_closed` items with residual PII require re-sanitization or local-only processing via `cortical_local_offload`.
