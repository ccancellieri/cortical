# Cortical Upstream OSS Contribution Drafts & Strategic Priority Matrix

> **Status:** `DRAFT — HUMAN REVIEW & CONFIRMATION REQUIRED BEFORE OPENING ANY EXTERNAL PR OR ISSUE`
> Follows **ADR-012** (Value-First Contract) & **ADR-018** (Anonymized Second Brain + AI Colleague): every proposal solves a concrete maintainer/user pain point with zero forced dependencies on Cortical.

---

## Executive Priority Ranking (Updated Post-ADR-017 & ADR-018)

| Rank | Target Repository / Registry | Effort | Acceptance Likelihood | Strategic Impact | Recommendation |
| --- | --- | --- | --- | --- | --- |
| **#1 (Must-Do First)** | **Official MCP Registry (`modelcontextprotocol/registry`) + `punkpeye/awesome-mcp-servers` + Glama** | Very Low (30m) | **Very High (~95%)** | Canonical discovery for anyone searching *"privacy vault MCP"*, *"second brain MCP"*, *"token compression"*, or *"local LLM offload"*. | **Execute immediately upon your GO** (`server.json` & `glama.json` are already schema-validated). |
| **#2 (Highest Viral Local-LLM Reach)** | **`unslothai/unsloth` (Docs / Discussions Recipe)** | Low (45m) | **High (~85%)** | Reaches tens of thousands of 16–24 GB laptop users struggling with silent `num_ctx=4096` truncation & 300s `<think>` timeouts on `27B`/`9B` Dynamic GGUFs. | **Top technical backlink** — pure empirical Metal VRAM math (`9.08 GiB` @ `65,536` ctx) + natural link to Cortical's stdlib tuner & Second Brain. |
| **#3 (Best Fit for Privacy + Hybrid Escalation)** | **`BerriAI/litellm` (Cookbook / Custom Guardrail PR)** | Low–Med (1h) | **High (~80%)** | Directly showcases Cortical's **ADR-018** killer flow: `$0` local runner first -> `fail_closed` zero-PII + `TOON` escalation to remote frontier APIs. | **High enterprise/professional appeal** (lawyers, finance, healthcare, consultants using hybrid proxies). |
| **#4 (Fastest-Growing Agent Audience)** | **`anomalyco/opencode` (Community Plugin + `/next` & `/private` Commands)** | Low (45m) | **High (~80%)** | Drop-in 20-line `.mjs` `TOON` hook (`-62%` to `-78%` JSON savings) + `/next` Colleague Browser Elicitor & `@private:<alias>` Second Brain. | **Great UX showcase** for interactive `127.0.0.1:0` Colleague Mode. |
| **#5 (Core Dogfooding Community)** | **`earendil-works/pi` (Community Extension Listing)** | Low (30m) | **High (~85%)** | Solves `max_tokens=1` clamp + adds Channel 3 pre-send attachment privatization (`3.48M` local tokens verified). | **High conversion** among local-first CLI power users. |
| **#6 (Cross-Project Goodwill)** | **`oraios/serena` / `rtk-ai/rtk` (Discussion: 4-Layer Composable Benchmark)** | Very Low (20m) | **High (~90% as Discussion)** | Positions Cortical as an amplifier of Serena (`-95.79%`) & RTK (`-51.35%`) rather than a competitor. | Post as constructive Show & Tell Discussion (zero maintainer review burden). |
| **#7 (Opportunistic / Later)** | **`deepseek-ai/deepseek-harness` (`dsh`)** | Low (30m) | **Medium (~60%)** | Early ecosystem foothold via Cordis `onBeforeDispatch` hook, smaller current audience than #1–#5. | Defer to Wave 2 after #1–#4 land. |

---

## 1. `unslothai/unsloth` (Local Quantization & Ollama Deployment Docs / Discussions)
- **URL:** `https://github.com/unslothai/unsloth`
- **Strategic Value:** Massive visibility among local-LLM practitioners running `UD-IQ2_XXS`, `Q4_XXS`, and `UD-Q3_K_XL` GGUFs on 16–24 GB consumer hardware.
- **Proposed Contribution Type:** Documentation / Discussion Recipe PR ("Preventing silent `num_ctx=4096` clipping and 300s `<think>` timeouts for `Qwen3.8-27B-UD-IQ2_XXS` & `Qwen3.5-9B-UD-Q3_K_XL` on 16 GB Apple Silicon").
- **Why Maintainers Value It:** Solves the #1 user complaint when running Unsloth Dynamic 2.0 GGUFs via Ollama/LiteLLM: models load fine, then silently truncate context at 4096 or stall on long prompts. Gives exact verified VRAM + GQA-4 KV math (`9.08 GiB` Metal VRAM @ `65,536` ctx).
- **Draft Text (Ready to Review):**
  > **Recipe: Swap-Free `65K` Context for `Qwen3.8-27B-UD-IQ2_XXS` on 16 GB Unified Memory (Ollama + OpenAI-Compatible Clients)**
  >
  > When deploying `unsloth/Qwen3.8-27B-GGUF:UD-IQ2_XXS` (`7.2 GB` weights, `262K` native GQA-4 context) on 16 GB Apple Silicon (~`11.2 GB` Metal working-set limit), Ollama defaults `num_ctx` to `4096` and enables thinking by default, causing silent truncation or `300s` HTTP timeouts in coding agents.
  >
  > Verified parameters from live `/api/ps` testing on M2 Pro (16 GB):
  > - `num_ctx: 65536` (`98304` for `UD-Q3_K_XL` 9B) -> `size == size_vram == 9,751,316,397` bytes (**9.08 GiB 100% Metal VRAM, 0 CPU swap**)
  > - `reasoning_effort: "none"` (maps to `think: false` in LiteLLM `ollama_chat`) + `keep_alive: "30m"` + `timeout: 600`
  >
  > Implementation reference (pure Python stdlib KV-budget calculator): `compute_hardware_context_profile` in `ccancellieri/cortical`. Happy to contribute a concise troubleshooting section to the Unsloth Ollama guide if helpful!

---

## 2. `BerriAI/litellm` (Custom Guardrail / Router Documentation Example)
- **URL:** `https://github.com/BerriAI/litellm`
- **Strategic Value:** De facto open-source LLM proxy/router; directly showcases Cortical's `fail_closed` privacy boundary and per-model Ollama `ollama_chat` tuning.
- **Proposed Contribution Type:** Example Guardrail / Cookbook PR (`litellm_cortical_guard.py` — zero external deps pre-call hook blocking unmasked secrets/private paths from remote endpoints while passing local Ollama routes).
- **Why Maintainers Value It:** Lightweight `< 30`-line custom callback requiring zero third-party NLP/Presidio installs, immediately usable in hybrid local+cloud LiteLLM configs.
- **Draft Text (Ready to Review):**
  > **Proposal: Zero-Dependency `fail_closed` Pre-Call Privacy Guardrail Example for Hybrid Local+Cloud LiteLLM Proxies**
  >
  > Teams routing both local Ollama models (`ollama_chat/*`) and remote frontier APIs through LiteLLM often want a lightweight guardrail ensuring raw API secrets or private local vault markers are never forwarded upstream, without installing heavy DLP frameworks.
  >
  > We wrote a minimal, stdlib-only `CustomLogger` pre-call hook (`async_pre_call_hook`) that allows local targets through at `$0` while failing closed on unmasked secret patterns before any remote dispatch. Happy to open a small docs/cookbook PR if maintainers find this useful.

---

## 3. `earendil-works/pi` (`@earendil-works/pi-coding-agent` Community Extension)
- **URL:** `https://github.com/earendil-works/pi`
- **Strategic Value:** Direct audience of local-first `pi` CLI power users (and Cortical's primary dogfooding harness).
- **Proposed Contribution Type:** Community `pi-package` / Extension listing (`@private:<alias>` pre-send Channel 3 attachment interception + `models.json` `clampMaxTokensToContext` protection for local Ollama/LiteLLM `27B` models).
- **Why Maintainers Value It:** Prevents `max_tokens=1` (`stopReason: "length"`) truncation when local `num_ctx` isn't matched in `models.json`, and gives `pi` users zero-server PII sanitization before attachments leave the machine.
- **Draft Text (Ready to Review):**
  > **Community Extension: Pre-Send PII Interception + Hardware-Safe `models.json` Context Sizing for Local `pi` Runs**
  >
  > While running multi-million-token local coding sessions in `pi` (`3.48M` tokens on local Qwen 9B/27B quants), we hit two sharp edges: hardcoded `32K` `contextWindow` entries clamping `max_tokens` to `1` via `CONTEXT_SAFETY_TOKENS=4096`, and raw sensitive file attachments reaching remote providers.
  >
  > We packaged a tiny zero-dependency `pi` extension (`before_provider_request` hook + `cortical_mcp` resource autocomplete) plus an automated `models.json` `num_ctx`/`reasoning_effort: "none"` sync. Would love feedback on listing it in `pi`'s community packages/extensions docs.

---

## 4. `anomalyco/opencode` (ex `sst/opencode`)
- **URL:** `https://github.com/anomalyco/opencode`
- **Strategic Value:** One of the fastest-growing open-source coding agents with native MCP and plugin/slash-command support.
- **Proposed Contribution Type:** Integration Recipe / Plugin Example (`.config/opencode/plugins/cortical-hook.mjs` for automatic lossless `TOON` compaction on >2 KB payloads + `/cortical-private` & `/cortical-local` commands).
- **Why Maintainers Value It:** Standalone 20-line `.mjs` plugin + 2 Markdown commands giving OpenCode users immediate token savings (`-62%` to `-78%` on structured JSON) and local offload with zero core code changes.
- **Draft Text (Ready to Review):**
  > **Plugin & Custom Commands Recipe: Lossless `TOON` Payload Compaction + Zero-PII `/cortical-private` for OpenCode**
  >
  > Sharing a lightweight, non-invasive integration for OpenCode users looking to cut structured JSON token usage (`-62.09%` vs compact / `-78.12%` vs pretty JSON) and keep sensitive files offline:
  > - One `experimental.chat.messages.transform` hook (`cortical-hook.mjs`) that compresses oversized JSON tool/message payloads when savings exceed `10%`.
  > - Two slash commands (`/cortical-private` for fail-closed `@private:<alias>` MCP reads and `/cortical-local` for zero-cloud-token local offload).
  > Happy to submit this under community integration guides if welcomed!

---

## 5. `deepseek-ai/deepseek-harness` (`dsh`)
- **URL:** `https://github.com/deepseek-ai/deepseek-harness`
- **Strategic Value:** Emerging Cordis-based plugin harness with first-party `@deepseek-ai/dsh-mcp-client`; early ecosystem guides earn strong visibility.
- **Proposed Contribution Type:** Community Cordis Plugin Recipe (`@deepseek-ai/dsh-mcp-client` YAML snippet + `onBeforeDispatch` pre-send sanitizer hook `cortical-cordis-hook.mjs`).
- **Why Maintainers Value It:** Ready-to-use security & token-efficiency recipe built directly on Cordis's native plugin model.
- **Draft Text (Ready to Review):**
  > **Community Plugin Recipe: Pre-Send PII Redaction Hook + `@deepseek-ai/dsh-mcp-client` Config for `dsh`**
  >
  > We built a Cordis `onBeforeDispatch` hook (`cortical-cordis-hook.mjs`) plus `@deepseek-ai/dsh-mcp-client` config snippet so `dsh` users can intercept raw attachments locally (`fail_closed`, stripping PDF/OOXML metadata and masking PII) before any prompt reaches remote APIs, while enabling `TOON` compression (`-62%` vs compact JSON). Available cleanly as an optional recipe.

---

## 6. `oraios/serena` / `rtk-ai/rtk` / `mksglu/context-mode` (Shared Benchmark & Interop)
- **URLs:** `https://github.com/oraios/serena` · `https://github.com/rtk-ai/rtk` · `https://github.com/mksglu/context-mode`
- **Strategic Value:** Cortical already composes all three tools; publishing an unbiased 4-layer reproducible benchmark shows maintainers Cortical amplifies *their* tools rather than competing with them.
- **Proposed Contribution Type:** Discussion / Benchmark Reference citing `scripts/stack_benchmark.py` with exact measured savings on a real Python codebase.
- **Draft Text (Ready to Review):**
  > **Reproducible 4-Layer Token Efficiency Benchmark: `Serena` + `RTK` + `TOON` + Local File Offload**
  >
  > We built a zero-dependency benchmark (`scripts/stack_benchmark.py`, MIT/Apache-2.0 stdlib Python) measuring how non-overlapping efficiency layers stack in real coding workflows:
  > 1. **AST Symbol Navigation (`Serena`-style read):** `11,020 -> 464` tok (**`-95.79%`**)
  > 2. **Shell Output Compaction (`RTK` on `git log -n 30`):** `1,854 -> 902` tok (**`-51.35%`**, while transparently noting `--stat` passes through)
  > 3. **Structured JSON Compaction (`TOON` lossless):** `745` pretty / `430` compact -> `163` tok (**`-78.12%` / `-62.09%`**)
  > 4. **Local File Offload (`file_paths` -> local model):** `4,352 -> 183` cloud tok (**`-95.80%`** cloud input)
  > Sharing in case it helps illustrate how symbol navigation + CLI proxies + payload compression compose cleanly without overlap.

---

## 7. Official MCP Registry (`modelcontextprotocol/registry`) & `punkpeye/awesome-mcp-servers`
- **URLs:** `https://github.com/modelcontextprotocol/registry` · `https://github.com/punkpeye/awesome-mcp-servers` · `https://glama.ai/mcp/servers`
- **Strategic Value:** Canonical discovery channels for developers searching MCP tools.
- **Proposed Contribution Type:**
  - Run `mcp-publisher` using [`server.json`](../../server.json) (`io.github.ccancellieri/cortical`, schema `2025-12-11`, full `2025-06-18` `annotations` + `outputSchema`).
  - Open 1 concise PR on `punkpeye/awesome-mcp-servers` adding Cortical under Privacy/Security & DevTools, plus refresh `glama.json`.
- **Draft PR Line (`awesome-mcp-servers`):**
  > `- [ccancellieri/cortical](https://github.com/ccancellieri/cortical) - Zero-dependency Python 3.10+ stdlib control plane & 7-tool MCP server with Zero-LLM fail-closed Privacy Vault (SHA-256 audit ledger), lossless TOON compression (-62.09% vs compact JSON), and multi-runner @role:* local LLM offload (Ollama, Unsloth, LM Studio, llama.cpp, MLX, vLLM).`
