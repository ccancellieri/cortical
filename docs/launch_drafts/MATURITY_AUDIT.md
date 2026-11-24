# Cortical — Phase 1 Critical Market Audit & Certified Release Gate (`GO`)

**Audit Date:** `2026-11-24` · **Gate Status:** **`GO` (Unconditional — All 3 Pre-Launch Conditions Closed & Verified via `ADR-016`)** · **Scope:** Repository inspection, live CLI benchmarks, zero-runner Privacy Vault verification, 7-runner multi-runner generalization, `docs/index.html` + `docs/settings.html` GitHub Pages verification, and competitive ecosystem analysis.

---

## 1. Ground-Truth Technical Verification (Observed Outputs)

| Check / Command | Verified Live Output (`2026-11-24`) |
| --- | --- |
| `pyproject.toml` | `cortical-agent` `0.3.0`, Python `>=3.10`, **`dependencies = []`** (`0` external runtime deps) |
| `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q` | **`Ran 57 tests — OK`** (`0` failures, `0` skips, `2,678` test LOC) |
| `wc -l` Reproducible Breakdown (`src/cortical/`) | **`19,086` total LOC** = **`15,048` LOC Core Python + CLI + Merkle Wiki** + **`4,038` LOC embedded zero-CDN HTML/CSS/JS SPA templates** (`-40.0%` vs `~31.8K` LOC `legacy-v0.2`) |
| Zero-Runner Privacy Vault Proof (`:9` unreachable port) | **`100%` operational with zero local LLM runner**: `.md`, `.docx` (XML metadata stripped), selectable `.pdf` (`/Author` stripped), `max_security` remote egress blocked, SHA-256 ledger `ok=True`, `TOON` lossless roundtrip |
| Multi-Runner Support (`resolve_active_runner_endpoint`) | **7 pluggable local runners** (`ollama`, `unsloth`, `lm_studio`, `llama_cpp`, `mlx_lm`, `vllm`, `openai_compatible`) across `invoke_configured_runner`, multimodal `ocr_image_local`, `plan_sync`, and `render_litellm_config_yaml` |
| `PYTHONPATH=src .venv/bin/python -m cortical.cli bench --compare` | **TOON Compression:** `745` pretty / `430` compact -> `163` tok (**`-78.12%` vs pretty / `-62.09%` vs compact**) · **Privacy Sanitizer:** `fail_closed`, `100.0%` tech prose preserved · **MCP Handshake (`7` core tools):** `~4.5 ms` |
| `PYTHONPATH=src .venv/bin/python scripts/stack_benchmark.py` | **AST Symbol (`verify_audit_ledger`):** `11,020 -> 464` tok (**`-95.79%`**) · **RTK (`git log -n 30`):** `1,854 -> 902` tok (**`-51.35%`**) · **Local `file_paths` offload (`@role:fast_coder`):** `4,352 -> 183` tok (**`-95.80%`** cloud input, `$0` cloud) |
| `PYTHONPATH=src .venv/bin/python -m cortical.cli doctor` | Explicitly reports **`Tier-1 Stdlib: ACTIVE`** (Zero-LLM Vault, TOON, SHA-256 Ledger, Sync) + **`Tier-2 Runner`** status across 7 runners, `@role:deep_reasoner` @ **`num_ctx=65,536`** (`timeout=600s`) |
| `PYTHONPATH=src .venv/bin/python -m cortical.cli sync --dry-run` | Previews **8 harnesses** cleanly (`0` files modified) and `cortical sync` prints `Undo anytime: cortical sync --rollback <backup_id>` |
| GitHub Pages (`docs/index.html` + `docs/settings.html`) | Both refreshed to `v0.3.0`, `0` external CDNs, `node --check` `JS_SYNTAX_OK`, prominent 1-Click Presets A/B/C & Tier-1/Tier-2 badges |

---

## 2. Unbiased Competitive Market Benchmark

| Category | Leading Ecosystem Tools | How Cortical Compares (Honest Assessment) |
| --- | --- | --- |
| **Coding Harnesses** | `claude-code`, `codex`, `anomalyco/opencode`, `earendil-works/pi`, `deepseek-harness` (`dsh`), `openclaw` | Cortical is **not** a competing coding harness; it is the shared control plane keeping MCP servers, `@role:*` model slots, and privacy rules in sync across all 8. |
| **Meta-Harnesses & Routers** | `LiteLLM`, `OmniRoute`, `claude-code-router`, `drmikecrowe/harnessed` | `LiteLLM` routes HTTP calls; Cortical generates runner-neutral `litellm_config.yaml` (`ollama_chat/*` or `openai/*` across Unsloth/LM Studio/llama.cpp/MLX/vLLM) with `num_ctx`, `reasoning_effort=none`, and `fail_closed` guardrails. |
| **Context & Token Optimizers** | `Serena` (LSP), `rtk-ai/rtk` (CLI proxy), `mksglu/context-mode` (FTS5 sandbox) | Complementary layers. Cortical composes all three and adds structured payload `TOON` compression (`-62.09%` / `-78.12%`) plus `file_paths` local LLM summarization (`-95.80%`). |
| **Local Runners & Quants** | `Ollama`, `Unsloth Studio`, `LM Studio`, `llama.cpp`, `Apple MLX`, `vLLM` | Cortical works with **all 7 local runners** (plus zero-runner Tier-1 mode) and computes per-machine `num_ctx` ceilings so 27B variable quants don't clip to `4096` or stall swap. |
| **Agent Privacy / DLP** | Microsoft `Presidio`, cloud DLP proxies | `Presidio` requires heavy NLP/spaCy dependencies. Cortical's Tier-1 Privacy Vault runs **100% in Python stdlib** (OOXML/PDF metadata stripping + PII/secret/custom-term masking + SHA-256 ledger) with zero local LLM required. |

---

## 3. Resolution of All 3 Pre-Launch Conditions (`CONDITIONAL GO` -> `GO`)

1. **[x] Condition 1 — Verifiable Ground-Truth Metrics (`wc -l` & `7` Core MCP Tools):**
   - Exact breakdown documented across `README.md`, `docs/METRICS_LEDGER.md`, `ADR-016`, and all launch drafts: **`19,086` total `src/cortical/` LOC** (`15,048` Core Python/CLI/Wiki + `4,038` embedded zero-CDN HTML/CSS/JS SPA templates) + **`2,678` test LOC** (`57/57` passing), and **`7` core MCP tools** (+ opt-in `5`-tool `cortical-wiki`). Zero stale `~4.2K` or `86.9%` claims remain.
2. **[x] Condition 2 — Safe `--dry-run` + `--rollback` Onboarding First:**
   - Every CLI quickstart (`README.md`, `docs/INTEGRATIONS.md`, `docs/index.html`, `docs/settings.html`, YouTube scripts, LinkedIn drafts) leads with `bench --compare` -> `doctor` -> `sync --dry-run` -> `sync` + `cortical sync --rollback <backup_id>`, and `_cmd_sync` prints the exact rollback command on every apply.
3. **[x] Condition 3 — Zero-LLM Stdlib Independence & Multi-Runner Constructive Diagnostics:**
   - Tier-1 Zero-LLM Stdlib vs Tier-2 Local-Runner badges added across `docs/settings.html` and `docs/index.html`; `cortical doctor`, `invoke_configured_runner`, `ocr_image_local`, and `cortical_local_offload` emit stack-trace-free runner-neutral guidance across all 7 local runners.

---

## 4. Formal Maturity Verdict: **`GO` (Ready for Human-Approved Launch)**

All technical, UX, multi-runner, and documentation gates are **100% satisfied and verified**. Per the **Human-in-the-Loop Golden Rule**, all external assets in `docs/launch_drafts/` remain local **DRAFTs** awaiting explicit user approval before any LinkedIn post, YouTube upload, or external repository PR/issue is published.
