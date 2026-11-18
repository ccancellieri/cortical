# Cortical

[![Live Docs & Configurator](https://img.shields.io/badge/Docs_&_Site-ccancellieri.github.io%2Fcortical-38bdf8)](https://ccancellieri.github.io/cortical/)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-34d399)](LICENSE)
[![Python 3.10+ Stdlib Only](https://img.shields.io/badge/Dependencies-0_External_(Stdlib_Only)-fbbf24)](pyproject.toml)

**Zero-Server 4-Tier Merkle Second Brain MCP, Multi-Model Local Offload Engine, Local Privacy Sanitizer (`@private:` Egress Gate), Pluggable 200k Dynamic Context Auto-Scaler, Cortical Skill Engine & Zero-Token ROI Analytics**

**Live Site & Configurator:** https://ccancellieri.github.io/cortical/  
**Author:** Carlo Cancellieri ([GitHub](https://github.com/ccancellieri) · [LinkedIn](https://linkedin.com/in/ccancellieri) · ORCID: `0009-0006-4092-4234`)  
**Platforms:** macOS (Apple Silicon Metal) & Linux (NVIDIA CUDA / Vulkan / CPU) · **Python 3.10+ stdlib only (`dependencies = []`)**

---

## Why Cortical? (Zero-Server, Privacy-First, Plug-and-Play)

Cortical runs with **zero background servers, zero open ports, zero Docker, and zero vector-DB bloat**. Everything persists in local SQLite (`WAL + FTS5`) and static HTML files (`docs/` / `html/`), plugging directly into **`pi`, `OpenCode`, `Claude Code`, `Codex CLI`, `Cursor`, `Windsurf`, `Cline`, `Zed`, `Continue.dev`, and `Antigravity`**.

1. **4-Tier Merkle + Macro-Graph Second Brain MCP (`src/cortical/wiki/`):**
   - Progressive retrieval tiers: `light` (~50 tok), `medium` (~250 tok), `high` (~1000 tok), `max` (raw file).
   - Bottom-up `sha256` Merkle delta crawler ($O(1)$ skip for unchanged files), SQLite FTS5 search, relational RBAC/ACL, and native MCP `resources` (`cortical://private/...`, `cortical://node/...`, `cortical://concept/...`) & `prompts`.
2. **Multi-Model Local Offload Loops (`cortical local-loop` / `cortical_local_loop`):**
   - Chains pluggable local runners (`ollama`, `llama_cpp`, `mlx_lm`, `openai_compatible`) across multiple specialized local models — e.g. `qwen2.5:1.5b` (router) &rarr; `qwen3.5:9b-q3_k_xl` (analyst) &rarr; `qwen3:8b` (reviewer) — to execute analysis, drafting, and insight distillation completely offline at **$0 cloud cost**.
3. **Local Privacy Sanitizer & `@private:` Zero-Path Egress Gate (`src/cortical/privacy_sanitizer.py`):**
   - Strips OOXML/PDF binary metadata, pseudonymizes IDs, person names, and user `custom_terms` (`[EMAIL_1]`, `[CUSTOM_1]`, `[PERSON_NAME_1]`), generates `.geminiignore`/`.cursorignore`/`.claudeignore` vault protections, and enforces configurable egress profiles (`max_security` local-only, `low`, `medium`, `max_context`).
   - Users reference private documents safely without typing filesystem paths via `@private:<alias>` or `/private <alias>`.
4. **Pluggable 200k Dynamic Context Auto-Scaler (`src/cortical/context_window.py`):**
   - Auto-discovers loaded models (`/api/ps`, `/api/show`, or custom `register_model_context_provider()`) and scales `num_ctx` to live RAM headroom (`vm_stat` / `/proc/meminfo`) up to configurable `max_context_window` (default `200,000`) — preventing silent 4096-token truncation and swap thrashing on 16 GB laptops.
5. **Cortical Skill Engine (`src/cortical/skills_hub.py` + `.agents/skills/`):**
   - Consolidates overlapping lessons via local LLM into knowledge-linked `learned-*` skills alongside standard playbooks (`cortical-token-saver`, `second-brain-3plus1-workflow`) with compilation gating and usage tracking.
6. **Zero-Remote-Token ROI Analytics & Adaptive Permission Gate (`src/cortical/token_analytics.py`, `src/cortical/permissions/gate.py`):**
   - Measures turn-level & historical remote transcript usage (disk-cached via `mtime+size` in ~99 ms), active-window local offload share (`offload_share_pct` + `effective_offload_share_pct`), and 3+1 memory savings at **0 cloud tokens**, paired with sub-millisecond (`<1 ms`) bash risk scoring.

---

## Verified Benchmarks (Apple M2 Pro · 16 GB Unified Memory)

Measured directly with [`scripts/benchmark.py`](scripts/benchmark.py) and [`scripts/benchmark_local_offload.py`](scripts/benchmark_local_offload.py):

| Metric / Workflow | Measured Value | Details |
| --- | --- | --- |
| **Root `light` Merkle Reduction** | **99.27%** | `1,860` `light` tokens vs `255,360` raw tokens across `43` Python modules |
| **Merkle Crawl / Delta Skip** | **283.35 ms / 89.56 ms** | Full bottom-up `sha256` crawl vs $O(1)$ unchanged skip |
| **Single-File Reduction (`server.py`)** | **99.20% / 96.52%** | `460` (`medium`) / `2,007` (`high`) vs `57,725` raw tokens |
| **3-Model Local Offload Loop** | **7,700 tok in 44.39s** | `qwen2.5:1.5b` &rarr; `qwen3.5:9b-q3_k_xl` &rarr; `qwen3:8b` (`14.51` out tok/s, **0 cloud tokens**) |
| **Permission Gate Latency** | **951.7 µs** | Deterministic bash risk evaluation per command |

---

## Quick Integration & CLI

### 1. MCP Server (`pi`, `OpenCode`, `Claude Code`, `Codex`, `Antigravity`, `Cursor`)
```json
{
  "mcpServers": {
    "cortical-wiki": {
      "command": "python3",
      "args": ["-m", "cortical.wiki.mcp_server"],
      "env": {
        "PYTHONPATH": "/path/to/cortical/src",
        "CORTICAL_WIKI_DB": "/path/to/cortical/.cortical_data/wiki.db"
      }
    }
  }
}
```
See [`docs/INTEGRATIONS.md`](docs/INTEGRATIONS.md) for all 10+ coding agent setups and native `@private:` / MCP Resource workflows.

### 2. CLI Quickstart, Local Offload Loops & Static Dashboards
```bash
# Index workspace into 4-tier Merkle Second Brain
PYTHONPATH=src .venv/bin/python -m cortical.cli --db .cortical_data/wiki.db crawl .

# Run a 3-model local offload reasoning loop (0 cloud tokens)
PYTHONPATH=src .venv/bin/python -m cortical.cli --db .cortical_data/wiki.db local-loop \
  "Summarize @wiki:/src/cortical/context_window.py /tier:l1" --loops 3

# Sanitize a private document offline
PYTHONPATH=src .venv/bin/python -m cortical.cli sanitize ./private_doc.docx --profile medium

# Generate private static local dashboards (open directly in browser, zero servers)
PYTHONPATH=src .venv/bin/python -m cortical.cli --db .cortical_data/wiki.db wiki-dashboard --output html/wiki.html
PYTHONPATH=src .venv/bin/python -m cortical.cli --db .cortical_data/wiki.db token-report --html html/token_report.html
PYTHONPATH=src .venv/bin/python -m cortical.cli settings-dashboard --output html/settings.html

# Reproduce benchmarks & run complete test suite (zero external deps)
PYTHONPATH=src .venv/bin/python scripts/benchmark.py
PYTHONPATH=src .venv/bin/python scripts/benchmark_local_offload.py
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q
```

---

## Repository Guides

- **Live Landing Page & Configurator:** [`https://ccancellieri.github.io/cortical/`](https://ccancellieri.github.io/cortical/)
- **Agent & IDE Integrations:** [`docs/INTEGRATIONS.md`](docs/INTEGRATIONS.md)
- **Publicity & Launch Kit (LinkedIn IT/EN, X, HN, Reddit):** [`docs/LAUNCH_KIT.md`](docs/LAUNCH_KIT.md)
- **OSS PR & Showcase Proposals:** [`docs/PR_PROPOSALS.md`](docs/PR_PROPOSALS.md)
- **Vibe-Coding Examples:** [`docs/USE_CASES_VIBE_CODING.md`](docs/USE_CASES_VIBE_CODING.md)
