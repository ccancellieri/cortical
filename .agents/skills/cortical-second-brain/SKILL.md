---
name: cortical-second-brain
description: >
  Navigate codebases via composed OSS tools (Serena LSP, RTK, PinchTab/Playwright), compress
  structured payloads with lossless TOON, and manage Cortical's zero-cloud-PII Privacy Vault.
---

# Cortical Composed Architecture & Privacy Memory

## 1. Code Navigation & Shell Compression (OSS Composition)
Prefer composed best-of-breed tools synced by `cortical sync`:
1. **Serena MCP:** Semantic symbol navigation (`find_symbol`, `get_symbols_overview`, `find_referencing_symbols`) instead of loading whole files.
2. **RTK (`rtk`):** Compresses CLI test/git/build output by 60–90% before reaching the model context.
3. **Cortical MCP (`cortical.mcp_server`):** Exposes only 5 lean tools (`cortical_vault_read`, `cortical_ingest_private`, `cortical_compress`, `cortical_doctor_status`, `cortical_local_offload`) + native `resources` (`cortical://private/<alias>`) & `prompts`.

## 2. Zero-Cloud-PII Memory Sync & Budget Scaling
All synced sanitized memory (`export_sanitized_memory_markdown`) is strictly compressed (`TOON` w/ `>=10%` guard vs compact JSON) and auto-budgeted to `<= 15%` of `num_ctx` computed dynamically for the machine's RAM/VRAM headroom.
