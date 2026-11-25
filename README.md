# Cortical

[![Live Demo & Docs](https://img.shields.io/badge/Demo_&_Docs-ccancellieri.github.io%2Fcortical-38bdf8)](https://ccancellieri.github.io/cortical/)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-34d399)](LICENSE)
[![Python 3.10+ Stdlib Only](https://img.shields.io/badge/Dependencies-0_External_(Stdlib_Only)-fbbf24)](pyproject.toml)
[![ccancellieri/cortical MCP server](https://glama.ai/mcp/servers/ccancellieri/cortical/badges/score.svg)](https://glama.ai/mcp/servers/ccancellieri/cortical)

**Cross-Platform Zero-Server Agent Control Plane & Declarative Composer** · **Dynamic Privacy Vault (`auto` | `fail_closed` | `fail_open`)** · **Deterministic Lossless `TOON` Compression** · **Hardware/Variable-Quant Model Manager & Auto-Tuner**

- **Live Documentation & 10-Second Browser Demo:** [`https://ccancellieri.github.io/cortical/`](https://ccancellieri.github.io/cortical/) · [`settings.html`](https://ccancellieri.github.io/cortical/settings.html) *(0 install, 3x 1-click presets, 0 CDNs)*
- **Platforms:** `macOS` (Apple Silicon Metal), `Linux` (CUDA / Vulkan / CPU), `Windows` (MSVC / NVIDIA / WMIC-PowerShell)
- **Zero External Runtime Dependencies:** `dependencies = []` in `pyproject.toml` (Python 3.10+ stdlib only)
- **Zero-Server by Default:** `stdio` MCP + file sync across **8 harnesses**, with optional on-demand foreground `serve-mcp` (`--transport streamable-http`), opt-in `--serve` dashboard, or HTTP router integration
- **Zero-LLM Privacy Vault (Works Without Any Local Model):** Deterministic PII + secret + custom-term masking, `.docx`/`.xlsx`/`.pptx`/selectable `.pdf` XML metadata stripping, `fail_closed` cloud egress guard, and cryptographic **SHA-256** audit ledger run **100% in Python stdlib**—no Ollama or local LLM required.
- **Multi-Runner Local & Hybrid Orchestration (7 Runners + 10 `@role:*` Slots):** Supports **`Ollama` (`:11434`)**, **`Unsloth Studio` (`:8888/v1`)**, **`LM Studio` (`:1234/v1`)**, **`llama.cpp` (`:8080/v1`)**, **`Apple MLX` (`:8080/v1`)**, **`vLLM` (`:8000/v1`)**, and custom **`openai_compatible`** endpoints through 10 semantic `@role:*` model abstractions (never hardcode model tags).
- **Codebase Breakdown (`wc -l` Verifiable):** Pre-redesign monolith (`~31.8K` LOC) archived in `legacy-v0.2` / `v0.2.0-legacy`; modular `v0.3.0` spans **7 Python subpackages** totaling **`22,230` LOC** (**`18,139` LOC Core Python + CLI + Second Brain + Colleague Studio + Merkle Wiki** and **`4,091` LOC embedded zero-CDN HTML/CSS/JS SPA modules**), verified by **`64/64` passing `unittest` tests** (`3,224` test LOC).

---

## Safe 60-Second Onboarding (Zero Dependencies, `--dry-run` First)

```bash
git clone https://github.com/ccancellieri/cortical.git && cd cortical
python3 -m venv .venv && .venv/bin/pip install --no-deps -e .

# 1. Benchmark lossless TOON (-78.12%), Zero-LLM Privacy Vault & 8-tool MCP
PYTHONPATH=src .venv/bin/python -m cortical.cli bench --compare

# 2. Inspect hardware tier, Tier-1 Zero-LLM Stdlib & detected local runners
PYTHONPATH=src .venv/bin/python -m cortical.cli doctor

# 3. Preview exact harness diffs FIRST (modifies 0 files)
PYTHONPATH=src .venv/bin/python -m cortical.cli sync --dry-run

# 4. Apply idempotently with timestamped backup (undo anytime via --rollback)
PYTHONPATH=src .venv/bin/python -m cortical.cli sync
# Undo anytime: PYTHONPATH=src .venv/bin/python -m cortical.cli sync --rollback <backup_id>
```

Prefer zero install? Open **[`https://ccancellieri.github.io/cortical/`](https://ccancellieri.github.io/cortical/)** or jump straight into the **[10-Second Interactive Control Plane (`settings.html`)](https://ccancellieri.github.io/cortical/settings.html)** and click **Preset A (4 GB VRAM Hybrid)**, **Preset B (16 GB Unified 27B @ 65K ctx)**, or **Preset C (Hybrid Remote + `fail_closed` Privacy Vault)**.

---

## Transparent 2-Tier Capability Matrix (`ADR-016`)

| Capability | Execution Tier | Local Model Runner Needed? | Supported Formats / Runners |
| --- | --- | --- | --- |
| **Privacy Vault, Metadata Strip & SHA-256 Audit Ledger** | **⚡ Tier 1 · Zero-LLM Stdlib** | **No** | `.md`, `.txt`, `.json`, `.docx`, `.xlsx`, `.pptx`, selectable `.pdf` (`auto` \| `fail_closed` \| `fail_open`) |
| **Lossless `TOON` Compression, `doctor` & 8-Harness `sync`** | **⚡ Tier 1 · Zero-LLM Stdlib** | **No** | `-78.12%` vs pretty / `-62.09%` vs compact JSON, `--dry-run` preview & `--rollback <id>` |
| **Static 6-Domain Browser Control Plane (`settings.html`)** | **⚡ Tier 1 · Zero-LLM Stdlib** | **No** | Zero external CDNs, zero open ports, client-side PII masking preview & 1-click Presets A/B/C |
| **Image / Scanned-PDF OCR (`cortical watch`) & `--ner`** | **🧠 Tier 2 · Local Runner** | Yes (`@role:vision` / `@role:ner`) | `Ollama`, `Unsloth Studio`, `LM Studio`, `llama.cpp`, `MLX`, `vLLM`, `openai_compatible` |
| **Zero-Cloud-Token Code Offload (`cortical_local_offload`)** | **🧠 Tier 2 · Local Runner** | Yes (`@role:daily_coder` / `@role:reviewer`) | Direct `file_paths` local read (`-95.80%` cloud input tokens at `$0` cloud cost) |

---

## Core Architecture (7 Subpackages + Lean 8-Tool MCP)

Cortical composes best-of-breed OSS tools (`Serena` LSP, `RTK` shell compressor, `PinchTab` / `Playwright` accessibility browser, `context-mode` output sandbox, optional `LiteLLM` / `OmniRoute` / `claude-code-router`) and handles the four gaps OSS leaves open:

1. **Hardware Preflight, Model Manager & Dynamic Variable Quantization (`src/cortical/hardware/`):**
   - Evaluates CPU RAM, discrete VRAM, unified memory, disk headroom, and active Ollama/CLI runners across 5 tiers (`tier_0_lean` through `tier_3_studio`).
   - Explicitly supports **Tier 1A Hybrid Laptops (`16 GB RAM + 4–6 GB VRAM`)** (`qwen2.5:1.5b`/`3b` in VRAM + `7B–9B` hybrid offload) and **Tier 1B Unified (`16–24 GB`)** running `qwen3.5:9b-q3_k_xl` (`5.1 GB`) alongside **Unsloth variable-quantized `27B` models** such as `qwen3.8:27b-q4_xxs` (`8.1 GB` 4-bit XXS) and `qwen3.8:27b-iq2_xxs` (`7.2 GB` `UD-IQ2_XXS`) for deep reasoning and orchestration without swap thrashing.
   - Manage built-in or user-configured custom/variable-quant models via `cortical models` (`list`, `recommend`, `add`, `remove`, `pull`) or the static configurator (`docs/settings.html`).
2. **Declarative Cross-Platform Harness Sync (`src/cortical/harnesses/`, `src/cortical/composers/`):**
   - Synchronizes MCP configs, router settings, and auto-sized rule files idempotently across **8 harnesses**: `antigravity`, `pi`, `opencode`, `openclaw`, `codex`, `claude-code`, `dsh` ([`deepseek-harness`](https://github.com/deepseek-ai/deepseek-harness)), and `unsloth-studio`.
   - Every `cortical sync` creates timestamped backups enabling exact `cortical sync --rollback <id>` without overwriting existing user credentials or unrelated config keys.
3. **Dynamic Privacy Vault & 3-Channel Zero-Attachment Exposure (`src/cortical/privacy/`):**
   - Strips OOXML/PDF metadata, runs structured PII + custom-term pseudonymization, optionally runs offline local LLM JSON NER (eliminating legacy Title-Case regex false positives on technical terms), and classifies items dynamically as **`auto`**, **`fail_closed`**, or **`fail_open`**.
   - **Channel 1 (`cortical://private/<alias>`):** Native MCP resource + `@private:<alias>` read (`blocks max_security` cloud egress).
   - **Channel 2 (`cortical sync`):** Injects sanitized memory blocks auto-capped at `<= 15% num_ctx`.
   - **Channel 3 (`cortical intercept`):** Deterministic pre-send attachment interception strictly on 100%-verified harnesses (`pi`, `claude-code`, `opencode`, `openclaw`, `codex`, `dsh`).
4. **Deterministic Lossless Compression (`src/cortical/compression/`):**
   - Native pure-Python lossless `TOON` encoder/decoder with deterministic round-trip fidelity, ANSI/log compaction, XML/YAML whitespace normalization, and an automatic `>= 10%` saving guard vs compact JSON.
5. **Lean 8-Tool MCP Server (`src/cortical/mcp_server.py`) & Prompt Studio (`src/cortical/composers/prompt_studio.py`):**
   - Minimal surface (`cortical_vault_read`, `cortical_ingest_private`, `cortical_compress`, `cortical_doctor_status`, `cortical_local_offload`, `cortical_roi_report`, `cortical_handoff`, `cortical_next_prompt`) with MCP `annotations`, `outputSchema`, `structuredContent`, native `resources`, `prompts` (`cortical-private`, `cortical-local`, `cortical-next-prompt`) & `completions`, plus opt-in 5-tool `cortical-wiki` RAG MCP (`src/cortical/wiki/mcp_server.py`).
   - **AI Colleague, Second-Brain Disk Privatizer & Prompt Studio (`cortical colleague` / `cortical privatize` / `cortical next` — `ADR-017` & `ADR-018`):** Recursively privatizes entire folders or drives into a **3+1 Tier Anonymized Second Brain** (`light`, `medium`, `high`, `max_security`), reconciles cross-document concepts & numeric/date discrepancies, asks plain-language bilingual (`IT`/`EN`) Colleague questions via a one-shot `127.0.0.1:0` loopback browser UI, auto-generates zero-PII `SKILL.md` workflows, and evaluates **Local LLM Sufficiency** first—escalating an anonymized + `TOON`-compressed packet to a remote LLM only when local capacity is insufficient.
6. **Zero-Token Analytics, Auto-Tuner & Comparative Benchmark (`src/cortical/analytics/`):**
   - Offline ROI reporting (`cortical roi`), local Auto-Tuner (`cortical tune`), static zero-server dashboard (`cortical dashboard`), Wiki audit explorer (`cortical wiki-dashboard`), and reproducible comparative benchmarks (`cortical bench --compare`).

---

## Reproducible Comparative Benchmarks (`before vs after`)

Measured offline with `PYTHONPATH=src .venv/bin/python -m cortical.cli bench --compare` and `scripts/benchmark.py`:

| Capability | Baseline / Before | Cortical / After | Measured Result |
| --- | --- | --- | --- |
| **Lossless Payload Compression** | `745` pretty / `430` compact JSON tok | `163` tok (`toon`) | **`-78.12%` vs pretty · `-62.09%` vs compact JSON** |
| **Privacy Sanitizer Precision** | Naive Title-Case false positives | `100.0%` technical prose preserved | **`100%` PII masked · `policy=fail_closed`** |
| **Tier 1A Hybrid (`16 GB + 4 GB VRAM`)** | Static defaults / OOM risk | `qwen2.5:3b` (VRAM) + `qwen3.5:9b-q3_k_xl` | **Swap-free hybrid fit** |
| **Tier 1B Unified (`16 GB` + `27B 4-bit XXS`)** | `4096` silent Ollama clipping | `qwen3.8:27b-q4_xxs` (`8.1 GB`) @ `32,768` ctx | **Variable quant deep reasoner** |
| **Lean MCP Tool Surface** | Heavy server + 12+ tools | `8` tools + native Resources & Prompts | **`~1–4 ms` ingest+read handshake** |

---

## Quickstart & Installation

### 1. Clone & Create Zero-Dependency `.venv`
```bash
git clone https://github.com/ccancellieri/cortical.git
cd cortical
python3 -m venv .venv
.venv/bin/pip install --no-deps -e .
```

### 2. Preflight Hardware, Select / Add Models & Sync Harnesses
```bash
# Inspect OS, GPU/VRAM, RAM headroom, composed OSS tools & model recommendations
PYTHONPATH=src .venv/bin/python -m cortical.cli doctor

# Inspect role-based recommendations or register custom variable-quant models
PYTHONPATH=src .venv/bin/python -m cortical.cli models recommend
PYTHONPATH=src .venv/bin/python -m cortical.cli models add qwen3.8:27b-q4_xxs --mem 8.1 --ctx 32768 --quant "Unsloth 4-bit XXS" --variable

# Preview and apply cross-platform config sync across 8 harnesses
PYTHONPATH=src .venv/bin/python -m cortical.cli sync --dry-run
PYTHONPATH=src .venv/bin/python -m cortical.cli sync
```

### 3. Connect Your MCP Client (`stdio` JSON-RPC 2.0)
```json
{
  "mcpServers": {
    "cortical": {
      "command": "python3",
      "args": ["-m", "cortical.mcp_server"],
      "env": {
        "PYTHONPATH": "/path/to/cortical/src",
        "CORTICAL_VAULT_DB": "/path/to/cortical/.cortical_data/vault.db"
      }
    }
  }
}
```
See [`docs/INTEGRATIONS.md`](docs/INTEGRATIONS.md) for all 8 harnesses (`antigravity`, `pi`, `opencode`, `openclaw`, `codex`, `claude-code`, `dsh`, `unsloth-studio`).

---

## Daily CLI Commands & Verification (25 Subcommands)

```bash
# Zero-friction workspace init, IDE MCP integration & one-shot setup
PYTHONPATH=src .venv/bin/python -m cortical.cli init -y
PYTHONPATH=src .venv/bin/python -m cortical.cli integrate --list
PYTHONPATH=src .venv/bin/python -m cortical.cli integrate cursor --dry-run
PYTHONPATH=src .venv/bin/python -m cortical.cli setup

# Drift reconciliation, dashboard apply bundles, composed tools & optional HTTP router
PYTHONPATH=src .venv/bin/python -m cortical.cli reconcile --dry-run --json
PYTHONPATH=src .venv/bin/python -m cortical.cli apply --from-clipboard --dry-run
PYTHONPATH=src .venv/bin/python -m cortical.cli tools status
PYTHONPATH=src .venv/bin/python -m cortical.cli router status

# Process queued local NER / vision (e.g. qwen2.5vl:3b) anonymization jobs (zero open ports)
PYTHONPATH=src .venv/bin/python -m cortical.cli watch

# Static dashboards (settings, help, wiki-dashboard) & Privacy Vault / Sanitized Crawl
PYTHONPATH=src .venv/bin/python -m cortical.cli dashboard --out-dir html --open
PYTHONPATH=src .venv/bin/python -m cortical.cli cortical --open
PYTHONPATH=src .venv/bin/python -m cortical.cli wiki-dashboard --open
PYTHONPATH=src .venv/bin/python -m cortical.cli ingest ./brief.pdf --alias client_brief --policy auto --profile medium
PYTHONPATH=src .venv/bin/python -m cortical.cli crawl ./docs --sanitize --dry-run
PYTHONPATH=src .venv/bin/python -m cortical.cli sanitize ./docs --recursive --output-dir ./docs_sanitized
PYTHONPATH=src .venv/bin/python -m cortical.cli vault list
PYTHONPATH=src .venv/bin/python -m cortical.cli vault show client_brief --local-ok
PYTHONPATH=src .venv/bin/python -m cortical.cli vault update client_brief --custom-term "Client Name" --profile medium
PYTHONPATH=src .venv/bin/python -m cortical.cli intercept --harness pi --prompt "Check @brief.pdf" --file ./brief.pdf

# Lossless TOON / XML / YAML / log compression, Streamable HTTP MCP & Chrome helper
PYTHONPATH=src .venv/bin/python -m cortical.cli compress ./payload.json
PYTHONPATH=src .venv/bin/python -m cortical.cli serve-mcp cortical --port 9122 --dry-run
PYTHONPATH=src .venv/bin/python -m cortical.cli browser status

# Interactive Prompt Studio & Autonomous Next-Prompt Elicitor (127.0.0.1:0 one-shot loopback, 0 persistent ports)
PYTHONPATH=src .venv/bin/python -m cortical.cli next "Add multi-runner health metrics" --target pi
PYTHONPATH=src .venv/bin/python -m cortical.cli next --resume --mode auto

# Run local Auto-Tuner, ROI report, offline benchmark & full unit test suite
PYTHONPATH=src .venv/bin/python -m cortical.cli tune --apply
PYTHONPATH=src .venv/bin/python -m cortical.cli roi
PYTHONPATH=src .venv/bin/python -m cortical.cli bench --compare
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q
```
