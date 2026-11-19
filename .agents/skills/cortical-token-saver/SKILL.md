---
name: cortical-token-saver
description: Local-first multi-model offload, variable-quantization model routing, dynamic Privacy Vault sanitization, and lossless TOON context compression across 8 coding harnesses.
---

# Cortical Control Plane & Token-Saver

Use this skill to maximize **local LLM execution** (`0` cloud tokens, full GDPR/privacy isolation), compress structured data deterministically (`TOON`), and choose the right local model for the machine's RAM/VRAM budget.

## 1. Preflight Hardware, Composed Tools & Models

```bash
PYTHONPATH=src .venv/bin/python -m cortical.cli doctor
PYTHONPATH=src .venv/bin/python -m cortical.cli models recommend
```

- **Tier 1A Hybrid Laptop (16 GB RAM + 4–6 GB VRAM):** `qwen2.5:1.5b` (fast sanitizer/router in VRAM) + `qwen3:8b` (`7B–8B` Q4 hybrid CPU+GPU).
- **Tier 1B Unified (16–24 GB Unified RAM):** `qwen3.5:9b-q3_k_xl` (`~4.9 GB` daily coder) + **Unsloth variable-quantized `27B` (`qwen3.8:27b-q4_xxs` `8.1 GB` or `qwen3.8:27b-iq2_xxs` `7.2 GB`)** for deep reasoning & multi-agent orchestration.
- **Add Custom Model:** `cortical models add <model_id> --mem <gb> --ctx <num_ctx> --quant <q> --variable`.

## 2. Dynamic Privacy Vault (`auto` | `fail_closed` | `fail_open`)

Never attach raw files containing PII/secrets to remote cloud prompts:

```bash
PYTHONPATH=src .venv/bin/python -m cortical.cli ingest ./notes.docx --alias client_brief --policy auto --profile medium
```

- **Channel 1 (MCP Resource):** read `@private:client_brief` or `cortical://private/client_brief` via `cortical.mcp_server` (`cortical_vault_read`).
- **Channel 2 (Auto-Sized Memory Sync):** `cortical sync` injects sanitized context capped at `<= 15% num_ctx` into all enabled harness rule files.
- **Channel 3 (Verified Pre-Send Interception):** automatically intercepts prompt attachments in `pi`, `claude-code`, `opencode`, `openclaw`, `codex`, `dsh`.

## 3. Lossless Compression & Comparative Telemetry

```bash
PYTHONPATH=src .venv/bin/python -m cortical.cli compress ./payload.json
PYTHONPATH=src .venv/bin/python -m cortical.cli bench --compare
PYTHONPATH=src .venv/bin/python -m cortical.cli tune --apply
PYTHONPATH=src .venv/bin/python -m cortical.cli roi
```
