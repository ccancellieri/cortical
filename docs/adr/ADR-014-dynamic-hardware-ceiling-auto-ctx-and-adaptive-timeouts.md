# ADR-014: Dynamic Hardware-Ceiling Context Window (`auto_ctx`) & Adaptive Timeout Sizing

- **Status:** Accepted
- **Date:** 2026-11-23
- **GitHub Issue:** #55 (Related Bug: #53, EPIC: #57)

## Context & Problem
Empirical debugging of `pi` + `router/cortical-deep` (`qwen3.8:27b-iq2_xxs`) uncovered three compounding defects:
1. **Static `32,768` Cap (`adapters.py:280`, `DEFAULT_MODEL_CONTEXT_WINDOWS`):** Ignored that `qwen3.8:27b-iq2_xxs` has `262,144` native context (`64` layers, `4` GQA KV heads -> `~1.22 GiB` per `32K` tokens) and fits `65,536` (`64K`) in `9.08 GiB` Metal VRAM on a 16 GB M2 Pro without swap. Once a `pi` session hit `~28.7K–30.5K` tokens, `pi-ai`'s `clampMaxTokensToContext` (`CONTEXT_SAFETY_TOKENS=4096`) clamped `max_tokens` to `1`, stopping output after a single token (`stopReason: "length"`).
2. **Unbounded `<think>` Loops & Premature 300s Timeouts:** Neither `litellm_config.yaml` nor `pi`'s `models.json` passed `reasoning_effort: "none"`, `keep_alive: "30m"`, or `timeout: 600`.
3. **Extension Shrink & Missing Semantic Aliases:** `~/.pi/agent/extensions/cortical-global.ts` forced `27b` requests down to `num_ctx: 16384`, and `plan_sync` omitted `cortical-deep` and `cortical-fast` from `pi`'s `models.json`.

## Decision
1. **Hardware-Aware KV & Ceiling Formula (`src/cortical/hardware/context_window.py`):**
   - Model `kv_tokens_per_gb` per architecture (`24576` for GQA-4 `qwen3.8:27b-iq2_xxs`, `28672` for `qwen3.5:9b`, `10240` fallback) and `compute_hardware_context_profile(...)` honoring Metal working-set / discrete VRAM headroom and OS reserves.
   - On 16 GB Unified Apple Silicon (`free_ram_gb >= 9.0`), `qwen3.8:27b-iq2_xxs` (`7.2 GB` weights) expands cleanly to **`65,536`** tokens while `qwen3.8:27b-q4_xxs` (`8.1 GB`) remains safely bounded (`32,768` unless `free_ram_gb >= 12.5`), and `qwen3.5:9b-q3_k_xl` (`5.1 GB`) scales to `98,304`–`131,072`.
2. **Adaptive Timeouts & Thinking Guardrails:**
   - Add `compute_adaptive_timeout(model_id, num_ctx, is_remote)` returning `600s` for `27b`/`32b`/`70b`/`cortical-deep`, `300s` for `8b`/`9b`/`cortical-fast`, and `180s` for lightweight/remote models.
   - Emit `reasoning_effort: none`, `keep_alive: 30m`, and `timeout` in `render_litellm_config_yaml()`, plus `samplingParams: {"reasoning_effort": "none"}` and `samplingParamsByThinkingLevel` in `pi`'s `models.json`.
   - Fix `plan_sync` to register semantic aliases (`cortical-fast`, `cortical-deep`, `local-default`) with computed `contextWindow` and update `cortical-global.ts` so `27b`/`cortical-deep` keeps `num_ctx: 65536`.

## Consequences & Trade-offs
- **Pros:** Eliminates `pi` + `cortical-deep` 300s timeouts and `max_tokens=1` length truncations while doubling usable context (`32K -> 64K`) swap-free on 16 GB Macs.
- **Cons:** When heavy background apps consume >7 GB RAM, dynamic headroom automatically steps `num_ctx` down (`49,152` / `32,768`) to avoid swap thrashing.
