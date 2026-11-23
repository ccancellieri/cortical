# ADR-013: Hybrid Local-First + Remote Orchestrator Architecture & 8-Harness Mapping

- **Status:** Accepted
- **Date:** 2026-11-23
- **GitHub Issue:** #54 (Related Bug: #53, EPIC: #57)

## Context & Problem
Developers using Cortical across **8 harnesses** (`antigravity`, `pi`, `opencode`, `openclaw`, `codex`, `claude-code`, `dsh`, `unsloth-studio`) need to choose whether their primary **Orchestrator** runs **100% locally** (`cortical-deep`, Ollama, `llama.cpp`, Unsloth Studio) or on a **Remote Cloud Provider** (Gemini, Claude, ChatGPT/OpenAI, DeepSeek, OpenRouter, or custom OpenAI-compatible endpoints) without leaking raw API keys into tracked files or burning cloud tokens on bulk repo scanning, file summaries, OCR/NER, and compression.

## Decision
1. **Declarative Orchestrator Schema (`src/cortical/config.py`):** Add `orchestrator` (`mode`: `local` | `remote`, `provider`, `model`, `api_key_env`, `endpoint`, `context_strategy`: `auto_max` | `fixed`, `fixed_num_ctx`, `timeout_sec`, `local_first_delegation`, `strict_remote_privacy`) plus `ORCHESTRATOR_PRESETS` and `resolve_orchestrator_spec(...)`.
2. **Environment-Variable Key Discipline:** Store only `api_key_env` names (e.g., `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, `OPENROUTER_API_KEY`), never raw credentials; `validate_plan` (`src/cortical/apply.py`) rejects plaintext secret literals in `api_key_env`.
3. **Local-First Delegation Topology & 8-Harness Sync:**
   - Map `orchestrator` + local worker tiers (`router`, `daily_coder`, `deep_reasoner`) consistently across all 8 adapters in `src/cortical/harnesses/adapters.py` (`plan_sync`) and optional LiteLLM routing (`cortical-orchestrator`, `cortical-fast`, `cortical-deep`, `cortical-vision` in `src/cortical/composers/router.py`).
   - Embed explicit local-first delegation instructions in shared harness rule files (`_build_shared_rules_md`) so bulk file reads, symbol navigation (`Serena`), shell compaction (`RTK`), `TOON` compression, OCR/NER, and `@private:` inspections execute locally via `cortical_local_offload`.

## Alternatives Considered
- **Hardcoding per-harness model overrides only in UI templates:** Causes config drift across `pi`, `opencode`, `codex`, `dsh`, and `litellm_config.yaml`.

## Consequences & Trade-offs
- **Pros:** Single declarative SSOT for both local air-gapped and hybrid remote topologies; preserves existing user credentials during `cortical sync`.
- **Cons:** Remote mode requires the target `ENV_VAR` to be exported in the shell or harness runtime environment.
