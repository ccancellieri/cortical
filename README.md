# Cortical

[![Live Demo & Docs](https://img.shields.io/badge/Demo_&_Docs-ccancellieri.github.io%2Fcortical-38bdf8)](https://ccancellieri.github.io/cortical/)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-34d399)](LICENSE)
[![Python 3.10+ Stdlib Only](https://img.shields.io/badge/Dependencies-0_External_(Stdlib_Only)-fbbf24)](pyproject.toml)

**Cross-Platform Zero-Server Agent Control Plane & Declarative Composer** · **Dynamic Privacy Vault (`auto` | `fail_closed` | `fail_open`)** · **Deterministic Lossless `TOON` Compression** · **Hardware/Variable-Quant Model Manager & Auto-Tuner**

- **Live Documentation & Browser Configurator:** [`https://ccancellieri.github.io/cortical/`](https://ccancellieri.github.io/cortical/) · [`settings.html`](https://ccancellieri.github.io/cortical/settings.html)
- **Platforms:** `macOS` (Apple Silicon Metal), `Linux` (CUDA / Vulkan / CPU), `Windows` (MSVC / NVIDIA / WMIC-PowerShell)
- **Zero External Runtime Dependencies:** `dependencies = []` in `pyproject.toml` (Python 3.10+ stdlib only)
- **Zero-Server by Default:** `stdio` MCP + file sync across **8 harnesses**, with optional on-demand foreground `serve-mcp` or HTTP router integration
- **Legacy Archive:** Pre-redesign monolith (`~31.8K` LOC) preserved in git branch `legacy-v0.2` and tag `v0.2.0-legacy`; redesigned architecture (`~4.2K` Python LOC across 6 packages) reduces codebase surface by **~86.9%** while composing best-of-breed OSS tools.

---

## Core Architecture (6 Packages + Lean 5-Tool MCP)

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
5. **Lean 5-Tool MCP Server (`src/cortical/mcp_server.py`):**
   - Minimal surface (`cortical_vault_read`, `cortical_ingest_private`, `cortical_compress`, `cortical_doctor_status`, `cortical_local_offload`) + native MCP `resources` & `prompts`.
6. **Zero-Token Analytics, Auto-Tuner & Comparative Benchmark (`src/cortical/analytics/`):**
   - Offline ROI reporting (`cortical roi`), local Auto-Tuner (`cortical tune`), static zero-server dashboard (`cortical dashboard`), and reproducible comparative benchmarks (`cortical bench --compare`).

---

## Reproducible Comparative Benchmarks (`before vs after`)

Measured offline with `PYTHONPATH=src .venv/bin/python -m cortical.cli bench --compare` and `scripts/benchmark.py`:

| Capability | Baseline / Before | Cortical / After | Measured Result |
| --- | --- | --- | --- |
| **Lossless Payload Compression** | `745` pretty / `430` compact JSON tok | `163` tok (`toon`) | **`-78.12%` vs pretty · `-62.09%` vs compact JSON** |
| **Privacy Sanitizer Precision** | Naive Title-Case false positives | `100.0%` technical prose preserved | **`100%` PII masked · `policy=fail_closed`** |
| **Tier 1A Hybrid (`16 GB + 4 GB VRAM`)** | Static defaults / OOM risk | `qwen2.5:3b` (VRAM) + `qwen3.5:9b-q3_k_xl` | **Swap-free hybrid fit** |
| **Tier 1B Unified (`16 GB` + `27B 4-bit XXS`)** | `4096` silent Ollama clipping | `qwen3.8:27b-q4_xxs` (`8.1 GB`) @ `32,768` ctx | **Variable quant deep reasoner** |
| **Lean MCP Tool Surface** | Heavy server + 12+ tools | `5` tools + native Resources & Prompts | **`~1.1–1.9 ms` ingest+read handshake** |

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

## Daily CLI Commands & Verification

```bash
# Privacy Vault ingestion (dynamic auto | fail_closed | fail_open)
PYTHONPATH=src .venv/bin/python -m cortical.cli ingest ./brief.docx --alias client_brief --policy auto --profile medium

# Lossless TOON / XML / YAML / log compression
PYTHONPATH=src .venv/bin/python -m cortical.cli compress ./payload.json

# Run local Auto-Tuner, ROI report, and static browser dashboard
PYTHONPATH=src .venv/bin/python -m cortical.cli tune --apply
PYTHONPATH=src .venv/bin/python -m cortical.cli roi
PYTHONPATH=src .venv/bin/python -m cortical.cli dashboard --out-dir html --open

# Run offline benchmark & full unit test suite
PYTHONPATH=src .venv/bin/python -m cortical.cli bench --compare
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q
```
