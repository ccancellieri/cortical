# Cortical

[![Live Demo & Brand Site](https://img.shields.io/badge/Demo_&_Docs-ccancellieri.github.io%2Fcortical-38bdf8)](https://ccancellieri.github.io/cortical/)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-34d399)](LICENSE)
[![Python 3.10+ Stdlib Only](https://img.shields.io/badge/Dependencies-0_External_(Stdlib_Only)-fbbf24)](pyproject.toml)

**Zero-Server 4-Tier Merkle Second Brain MCP, Multi-Model Local Offload Engine, Local Privacy Sanitizer (`@private:` Egress Gate), Pluggable 200k Dynamic Context Auto-Scaler, and Cortical Skill Engine**

- **Live Brand Site & Interactive Demo:** [`https://ccancellieri.github.io/cortical/`](https://ccancellieri.github.io/cortical/)
- **Interactive Browser Configurator:** [`https://ccancellieri.github.io/cortical/settings.html`](https://ccancellieri.github.io/cortical/settings.html)
- **Platforms:** macOS (Apple Silicon Metal) & Linux (NVIDIA CUDA / Vulkan / CPU) · **Pure Python 3.10+ stdlib (`dependencies = []`)**
- **License:** `Apache-2.0` · **Author:** Carlo Cancellieri ([GitHub](https://github.com/ccancellieri) · ORCID `0009-0006-4092-4234`)

---

## Core Architecture (Zero-Server, Zero Vector-DB Bloat)

Cortical runs with **no background daemon, no Docker, no external vector DB, and no mandatory pip packages**. State stays in local SQLite (`WAL + FTS5`) and static HTML exports, plugging cleanly into **`pi`, `OpenCode`, `Claude Code`, `Codex CLI`, `Cursor`, `Windsurf`, `Cline`, `Zed`, `Continue.dev`, and `Antigravity`**.

1. **4-Tier Merkle + Macro-Graph Second Brain MCP (`src/cortical/wiki/`):**
   - Progressive retrieval tiers: `light` (~50 tok), `medium` (~250 tok), `high` (~1,000 tok), `max` (raw file).
   - Bottom-up `sha256` Merkle delta crawler ($O(1)$ skip for unchanged files), SQLite FTS5 search, relational RBAC/ACL, and native MCP `resources` (`cortical://private/...`, `cortical://node/...`, `cortical://concept/...`) & `prompts`.
2. **Multi-Model Local Offload Loops (`cortical local-loop` / `cortical_local_loop`):**
   - Chains pluggable local runners (`ollama`, `llama_cpp`, `mlx_lm`, `openai_compatible`) across router, analyst, and reviewer models (e.g. `qwen2.5:1.5b` &rarr; `qwen3.5:9b-q3_k_xl` &rarr; `qwen3:8b`) to resolve tasks offline and distill durable insights at **$0 cloud cost**.
3. **Local Privacy Sanitizer & `@private:` Egress Gate (`src/cortical/privacy_sanitizer.py`):**
   - Strips OOXML/PDF binary metadata, pseudonymizes emails/IDs/names/custom terms locally, protects private vaults via `.geminiignore`/`.cursorignore`/`.claudeignore`, and gates `@private:<alias>` / `cortical://private/...` egress across configurable profiles (`max_security`, `low`, `medium`, `max_context`).
4. **Pluggable 200k Dynamic Context Auto-Scaler (`src/cortical/context_window.py`):**
   - Auto-discovers loaded models (`/api/ps`, `/api/show`, or custom `register_model_context_provider()`) and scales `num_ctx` to live RAM headroom (`vm_stat` / `/proc/meminfo`) up to configurable `max_context_window` (default `200,000`), avoiding silent `4096`-token clipping and swap thrashing.
5. **Cortical Skill Engine (`src/cortical/skills_hub.py` + `.agents/skills/`):**
   - Ships portable `SKILL.md` playbooks (`cortical-token-saver`, `second-brain-3plus1-workflow`) alongside local skill consolidation and knowledge-graph linking.
6. **Zero-Token ROI Analytics & Adaptive Permission Gate (`src/cortical/token_analytics.py`, `src/cortical/permissions/gate.py`):**
   - Evaluates bash/tool risk deterministically in `<1 ms` and computes local offload + compression savings offline into static local dashboards.

---

## Reproducible Benchmarks (Apple M2 Pro · 16 GB Unified Memory)

Run the included benchmark scripts to measure directly on your own hardware:

| Benchmark | Measured Result | Scope | Script |
| --- | --- | --- | --- |
| **Root `light` Merkle Reduction** | **99.27%** (`1,860` vs `255,360` raw tok) | 43 Python modules | [`scripts/benchmark.py`](scripts/benchmark.py) |
| **Merkle Crawl / Delta Skip** | **283.35 ms** cold / **89.56 ms** $O(1)$ skip | 43 Python modules | [`scripts/benchmark.py`](scripts/benchmark.py) |
| **Single-File Reduction (`server.py`)** | **460** (`medium`) / **2,007** (`high`) vs `57,725` raw | `99.20%` / `96.52%` saved | [`scripts/benchmark.py`](scripts/benchmark.py) |
| **Adaptive Permission Gate** | **951.7 µs** per bash evaluation | Deterministic scorer | [`scripts/benchmark.py`](scripts/benchmark.py) |
| **3-Model Local Offload Loop** | **7,700 tok in 44.39s** (`14.51` out tok/s, `$0` cloud) | `1.5b -> 9b -> 8b` | [`scripts/benchmark_local_offload.py`](scripts/benchmark_local_offload.py) |

---

## How to Install

### 1. Local Environment (`.venv`)
```bash
git clone https://github.com/ccancellieri/cortical.git
cd cortical
python3 -m venv .venv
.venv/bin/pip install --no-deps -e .
```

### 2. Connect to Your Coding Agent (MCP `stdio`)
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
See [`docs/INTEGRATIONS.md`](docs/INTEGRATIONS.md) for Claude Code, Codex CLI, Cursor, Windsurf, Cline, `pi`, OpenCode, Zed, Continue.dev, and Antigravity examples.

---

## How to Use, Reproduce & Test

```bash
# 1. Run full offline test suite (39 unit tests, zero external deps)
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q

# 2. Reproduce core Merkle, token reduction & Permission Gate benchmarks
PYTHONPATH=src .venv/bin/python scripts/benchmark.py

# 3. Reproduce 3-model local offload loop benchmark (requires local Ollama)
PYTHONPATH=src .venv/bin/python scripts/benchmark_local_offload.py --tmp

# 4. Crawl a repo & execute a local multi-model reasoning loop
PYTHONPATH=src .venv/bin/python -m cortical.cli --db .cortical_data/wiki.db crawl .
PYTHONPATH=src .venv/bin/python -m cortical.cli --db .cortical_data/wiki.db local-loop \
  "Summarize @wiki:/src/cortical/context_window.py /tier:l1" --loops 3

# 5. Sanitize a sensitive document offline
PYTHONPATH=src .venv/bin/python -m cortical.cli sanitize ./document.docx --profile medium

# 6. Export private static dashboards locally (kept on disk, ignored by git)
PYTHONPATH=src .venv/bin/python -m cortical.cli --db .cortical_data/wiki.db wiki-dashboard --output html/wiki.html
PYTHONPATH=src .venv/bin/python -m cortical.cli --db .cortical_data/wiki.db token-report --html html/token_report.html
PYTHONPATH=src .venv/bin/python -m cortical.cli settings-dashboard --output html/settings.html
```

---

## Documentation

- **Brand Page, Interactive Demo & Configurator:** [`https://ccancellieri.github.io/cortical/`](https://ccancellieri.github.io/cortical/)
- **Agent & IDE Integrations:** [`docs/INTEGRATIONS.md`](docs/INTEGRATIONS.md)
- **Vibe-Coding Examples:** [`docs/USE_CASES_VIBE_CODING.md`](docs/USE_CASES_VIBE_CODING.md)
