# ADR-009: Strata Runtime, Inkling-2-Mini Quantization Fit & Local-Agent Guardrails

- **Status:** Proposed
- **Date:** 2026-11-23
- **GitHub Issue:** #31

## Context & Problem
Cortical currently discovers and configures `ollama`, `unsloth`, `llama_cpp`, `mlx_lm`, and `openai_compatible` in `src/cortical/config.py`, probes Apple Silicon VRAM heuristically as `0.70 * total_ram_gb` in `src/cortical/hardware/probe.py`, and computes `num_ctx` linearly in `src/cortical/hardware/context_window.py`.

Evaluating `Niko1221/Strata` (`v0.2.20`) and Thinking Machines Lab's `Inkling-2-Mini` (`26.4B` MoE, `3.4B` active / `5.4B` looped-active across 24 physical -> 48 virtual layers, via `strata-engine/Inkling-2-Mini-Strata` and `unsloth/Inkling-2-Mini-GGUF`) on an Apple M2 Pro (`16 GB` unified memory, macOS `27.0.1`) revealed four concrete gaps:
1. **No first-class `strata` runner detection:** `_TRACKED_BINARIES` in `probe.py`, `DEFAULT_CONFIG["runners"]` in `config.py`, and `render_litellm_config_yaml()` in `composers/router.py` do not detect `strata`, probe its `/health` or `/v1/models` endpoints (`http://127.0.0.1:8080/v1`), or ingest telemetry from `strata status --json`.
2. **Naive unified-memory & KV sizing:** Linear headroom ignores Metal `recommendedMaxWorkingSetSize` (`~11.84 GiB` on a 16 GB M2 Pro) and active OS/desktop memory contention:
   - `Inkling-2-Mini-SQ-10.strata` (`10.47 GB` + `0.64 GB` Vision) allocates `10.94 GiB` at `8192` ctx (`8.05 tok/s` cold decode, `86.4 tok/s` warm prefill, `4.53 tok/s` warm decode once system RAM reached `16.72 / 17.18 GB` = `97.3%`), whereas auto-clamped `12288` ctx (`11.08 GiB`) dropped to `1.8 tok/s` in standalone `--bench` under desktop load.
   - `UD-IQ2_XXS` (`8.49 GB` GGUF + `0.40 GB` DSpark drafter) fits with `~2 GB` additional unified RAM headroom for macOS/IDE/browser coexistence.
3. **Upstream Apple7/8 Metal compiler defect in `0.1.66`:** Prebuilt `strata-inkling 0.1.66-macos-arm64-metal` crashes `MTLCompilerService` on `ink_moe_gu_situ` (`XPC_ERROR_CONNECTION_INTERRUPTED`, upstream Strata `#6608`/`#6720`, fixed in `Niko1221/Strata` `main` commit `759ccf6c`). Compiling `engine/src/inkling2` from `main` resolved the crash completely (`--selfcheck PASS backend=metal`).
4. **Un-cancellable looped reasoning:** Inkling-2-Mini cannot turn reasoning fully off; without explicit `max_tokens` and agent turn ceilings, local agent loops can burn wall time and thermal budget.

## Decision
1. **Register `strata` runner & `Inkling-2-Mini` catalog entries:** Add `strata` to `_TRACKED_BINARIES`, `DEFAULT_CONFIG["runners"]`, and `BUILTIN_MODEL_CATALOG` (`SQ-10` `10.47 GB`, `UD-IQ2_XXS` `8.49 GB`, `UD-Q2_K_XL` `9.14 GB`, `SQ-15` `14.35 GB`, `SQ-20` `19.35 GB`), and expose running Strata endpoints inside `render_litellm_config_yaml()`.
2. **Dual unified-memory fit & hybrid KV sizing:** Enforce both `alloc <= Metal workSet` and `TotalAlloc + OS_reserve <= total_ram_gb`, model sliding-window (SWA) vs global KV layers + drafter overhead, and warn clearly (`may page under desktop load`) when remaining OS margin is tight at `16 GB`.
3. **Looped-model & engine-version guardrails:** Set explicit default `max_tokens` and turn caps on looped local offload requests (`temperature: 1.0`), and flag buggy `strata-inkling 0.1.66` binaries on Apple M1/M2 in `cortical doctor` until upstream `0.1.67` ships commit `759ccf6c`.
4. **Strata-inspired resilience & config layering:** Adopt 4-layer override preservation (`args_derived` + `user_args`) from `arg_layers.py`, cross-run refusal suppression (`netpolicy.py`) for offline localhost probes, `--plan --output json` dry-run symmetry across CLI commands, and optimistic instance-ID checks on runtime lifecycle controls.

## Consequences & Trade-offs
- **Pros:** Preserves Cortical's `dependencies = []` (Python 3.10+ stdlib only) and zero-server default while preventing 16 GB swap collapse and runaway local-agent loops.
- **Cons:** Adds per-family KV/drafter metadata fields to `BUILTIN_MODEL_CATALOG` and requires version-aware compatibility checks in `probe.py`.
