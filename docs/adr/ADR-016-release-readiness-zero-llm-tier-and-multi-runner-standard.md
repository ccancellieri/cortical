# ADR-016: Release Readiness Standard — 2-Tier Zero-LLM Stdlib Transparency, Multi-Runner Generalization & Safe `--dry-run` Onboarding

- **Status:** Accepted (Upgrades Pre-Launch Maturity Gate from `CONDITIONAL GO` to `GO`)
- **Date:** 2026-11-24
- **Scope:** Core Control Plane (`config.py`, `cli.py`, `mcp_server.py`), Privacy Vault (`sanitizer.py`), Harnesses & Router (`adapters.py`, `router.py`), Static SPA (`zero_server_ui.py` / `docs/settings.html` / `docs/index.html`)

## Context

During the pre-launch technical and UX audit (`docs/launch_drafts/MATURITY_AUDIT.md`), three adoption-critical clarity requirements emerged before public showcase:

1. **Zero-LLM Stdlib vs Local-Runner Transparency:** Users evaluating Cortical must immediately see that **Tier 1**—including the `fail_closed` Privacy Vault for `.md`/`.txt`/`.json`/`.docx`/`.xlsx`/`.pptx`/selectable `.pdf`, metadata stripping, custom-term masking, SHA-256 tamper-evident audit ledger, lossless `TOON` compression, `cortical doctor`, and 8-harness `cortical sync`—operates **100% in Python 3.10+ stdlib with zero local LLM runner**. Only **Tier 2** capabilities (multimodal image/scanned-PDF OCR via `cortical watch`, optional `--ner`, and `cortical_local_offload`) require a local model runner.
2. **Multi-Runner Neutrality Beyond Ollama:** Developers run local models across diverse engines (`Ollama`, `Unsloth Studio`, `LM Studio`, `llama.cpp`, `Apple MLX`, `vLLM`, and custom OpenAI-compatible servers). Hardcoding `http://127.0.0.1:11434` inside `ocr_image_local`, `plan_sync`, or `render_litellm_config_yaml` created avoidable lock-in.
3. **Safe Onboarding (`--dry-run` + `--rollback`) & Ground-Truth Metrics:** Mutating dotfile configs across 8 coding harnesses without leading with `--dry-run` and `--rollback <backup_id>`, or leaving historical issue metrics (`~4.2K` LOC, `5` tools) unclarified, risks eroding developer trust in the first 5 minutes.

## Decision

1. **Formalize the 2-Tier Capability Contract (`⚡ Tier 1: Zero-LLM Stdlib` vs `🧠 Tier 2: Local Runner`):**
   - `cortical doctor`, `docs/settings.html`, `docs/index.html`, and `README.md` explicitly surface Tier-1 Zero-LLM Stdlib status alongside optional Tier-2 runner status.
   - When no local runner is reachable, `invoke_configured_runner`, `ocr_image_local`, and `cortical_local_offload` return constructive, stack-trace-free guidance confirming Tier-1 Zero-LLM features remain 100% active (`zero_llm_stdlib_active: true`).
2. **Standardize 7 Pluggable Local Runners (`resolve_active_runner_endpoint`):**
   - Support `ollama` (`:11434`), `unsloth` (`:8888/v1`), `lm_studio` (`:1234/v1`), `llama_cpp` (`:8080/v1`), `mlx_lm` (`:8080/v1`), `vllm` (`:8000/v1`), and `openai_compatible` (`:4000/v1`) across `invoke_configured_runner`, multimodal `ocr_image_local` (`/api/chat` and OpenAI `/v1/chat/completions` `image_url`), `plan_sync`, `render_litellm_config_yaml`, and UI runtime probes.
3. **Enforce the Canonical 4-Step Safe Onboarding & Verifiable `wc -l` Breakdown:**
   - Lead every CLI quickstart, UI button bar, and launch draft with `bench --compare` -> `doctor` -> `sync --dry-run` -> `sync` (printing `Undo anytime: cortical sync --rollback <backup_id>`).
   - State exact, reproducible `wc -l` figures distinguishing Core Python logic from embedded zero-CDN HTML/CSS/JS SPA templates and `tests/`, alongside the **7-tool** `cortical-mcp` core surface (+ opt-in 5-tool `cortical-wiki`).

## Consequences

- **Positive:** Eliminates "Ollama required" misconceptions, unlocks first-class `Unsloth Studio` / `LM Studio` / `llama.cpp` / `MLX` / `vLLM` workflows, keeps `dependencies = []` intact, and upgrades Cortical's release gate to an unconditional **`GO`**.
- **Trade-offs:** Maintaining embedded zero-CDN HTML templates inside Python keeps `src/cortical/` total line count around `~19K` LOC (`~15.2K` Core Python + `~3.8K` embedded zero-CDN UI), which is documented transparently rather than hidden.
