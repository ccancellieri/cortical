---
name: cortical-token-saver
description: Local-first multi-model offload, variable-quantization model routing, dynamic Privacy Vault sanitization, lossless TOON compression, and cross-harness handoff across 8 coding harnesses.
---

# Cortical Control Plane & Token-Saver

Maximize **local LLM execution** (`$0` cloud tokens, `fail_closed` GDPR/privacy isolation), compress structured data deterministically (`TOON`), and synchronize configurations across 8 coding harnesses (`antigravity`, `pi`, `opencode`, `openclaw`, `codex`, `claude-code`, `dsh`, `unsloth-studio`).

## 1. Preflight Hardware, Composed Tools & SSOT Reconciliation

```bash
PYTHONPATH=src .venv/bin/python -m cortical.cli doctor
PYTHONPATH=src .venv/bin/python -m cortical.cli models recommend
PYTHONPATH=src .venv/bin/python -m cortical.cli reconcile --dry-run --json
```

- **Tier 1A Hybrid Laptop (16 GB RAM + 4–6 GB VRAM):** `qwen2.5:1.5b` / `qwen2.5:3b` (VRAM router/NER) + `qwen3:8b` (hybrid offload).
- **Tier 1B Unified (16–24 GB Unified RAM):** `qwen3.5:9b-q3_k_xl` (`5.1 GB`, `131K` ctx daily coder) + `qwen3.8:27b-iq2_xxs` (`7.2 GB`, `32K` ctx deep reasoner/orchestrator).
- **Add Custom Model / Apply Dashboard Bundle:** `cortical models add <id> --mem <gb> --ctx <num_ctx> --quant <q> --variable` or `cortical apply --from-clipboard`.

## 2. Dynamic Privacy Vault (`auto` | `fail_closed` | `fail_open`) & Sanitized Crawl

Never attach raw files containing PII/secrets to remote cloud prompts:

```bash
PYTHONPATH=src .venv/bin/python -m cortical.cli ingest ./notes.docx --alias client_brief --policy auto --profile medium
PYTHONPATH=src .venv/bin/python -m cortical.cli crawl ./docs --sanitize --dry-run
PYTHONPATH=src .venv/bin/python -m cortical.cli sanitize ./docs --recursive --output-dir ./docs_sanitized
```

- **Channel 1 (MCP Resource):** read `@private:client_brief`, `cortical://private/client_brief`, or `task_tag` via `cortical_vault_read(tier='light'|'medium'|'high'|'max')` (`blocks max_security`).
- **Channel 2 (Auto-Sized Memory Sync):** `cortical sync` injects sanitized context capped at `<= 15% num_ctx`.
- **Channel 3 (Verified Pre-Send Interception):** automatically intercepts prompt attachments in `pi`, `claude-code`, `opencode`, `openclaw`, `codex`, `dsh`.

## 3. Lean 7-Tool `cortical-mcp` & Zero-Token Telemetry

- **`cortical_local_offload`:** Delegate summaries, code reviews, or boilerplate drafts locally (`0` cloud tokens; pass `vault_alias` for offline `max_security` docs).
- **`cortical_compress`:** Deterministic lossless `TOON` / XML / YAML / log compaction (`>= 10%` guard vs compact JSON).
- **`cortical_handoff`:** Save or load `{goal, summary, modified_files, next_step}` across Antigravity, `pi`, OpenCode, Claude Code & Codex.
- **`cortical_roi_report`:** Compute turn + cumulative local vs cloud token savings (`0` cloud tokens).

```bash
PYTHONPATH=src .venv/bin/python -m cortical.cli compress ./payload.json
PYTHONPATH=src .venv/bin/python -m cortical.cli bench --compare
PYTHONPATH=src .venv/bin/python -m cortical.cli tune --apply
PYTHONPATH=src .venv/bin/python -m cortical.cli roi
```
