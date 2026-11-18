# Cortical Launch Kit — PRs, GitHub Discussions & Multi-Channel Publicity Copy

> **Author:** Carlo Cancellieri ([GitHub](https://github.com/ccancellieri) · [LinkedIn](https://linkedin.com/in/ccancellieri) · ORCID `0009-0006-4092-4234`)  
> **Live Docs & Configurator:** `https://ccancellieri.github.io/cortical/` (served from `/docs` on `main`)  
> **Repository:** `https://github.com/ccancellieri/cortical`  
> **Reproducible Local Benchmarks:** `scripts/benchmark.py` and `scripts/benchmark_local_offload.py`

---

## 1. LinkedIn Post (English — Ready to Publish)

Stop burning cloud tokens re-reading the same codebase. Meet **Cortical** — a zero-dependency, zero-server **4-Tier Merkle Second Brain MCP**, **Multi-Model Local Offload Loop**, **Privacy Sanitizer (`@private:`)**, **Cortical Skill Engine**, and **200k Dynamic Context Auto-Scaler**.

While profiling local coding agents and cloud transcripts on 16 GB Apple Silicon, two bottlenecks stood out:
1. Uncached codebase re-reading and boilerplate drafting burn massive cloud context when a lightweight 4-tier tree + local Ollama chain handles them cleanly offline.
2. Local LLMs on 16 GB laptops silently truncate at `4096` tokens or thrash into swap without RAM-aware `num_ctx` scaling.

So I open-sourced **Cortical** (Apache-2.0, pure Python 3.10+ stdlib, **0 external dependencies, 0 background servers**):
- **99.27% token reduction** on codebase orientation (`1,860` `light` root tokens vs `255,360` raw across `43` Python modules) and **99.20%** on large single files (`460` `medium` vs `57,725` raw for `server.py`)
- **283.35 ms** full Merkle crawl & **89.56 ms** $O(1)$ unchanged delta skip
- **7,700 local tokens in 44.39s (0 cloud tokens)** chaining `qwen2.5:1.5b` (router) -> `qwen3.5:9b-q3_k_xl` (analyst) -> `qwen3:8b` (reviewer) via `cortical local-loop`
- **`@private:` Zero-Path Egress Gate & Local Privacy Sanitizer:** strips OOXML/PDF metadata, pseudonymizes identities/custom terms offline, and exposes safe MCP `resources` & `prompts`
- **951.7 µs** deterministic permission gate evaluation

Works across Claude Code, Codex CLI, Cursor, Windsurf, Cline, `pi`, OpenCode, Zed, Continue.dev, and Antigravity.

Live interactive configurator & docs: https://ccancellieri.github.io/cortical/  
GitHub repo: https://github.com/ccancellieri/cortical

Reproduce locally: `PYTHONPATH=src python3 scripts/benchmark.py && PYTHONPATH=src python3 scripts/benchmark_local_offload.py`

#LocalLLMs #OpenSource #MCP #AICodingAgents #Ollama #PrivacyByDesign #Python #Cortical

---

## 2. LinkedIn Post (Italiano — Pronto per la Pubblicazione)

Smetti di sprecare token cloud facendo rileggere ogni volta lo stesso repository. Ecco **Cortical**: un toolkit Python a zero dipendenze e **Zero-Server** con **Second Brain Merkle a 4 livelli (MCP)**, **Loop Multi-Modello in Locale**, **Privacy Sanitizer (`@private:`)**, **Cortical Skill Engine** e **Auto-Scaler dinamico fino a 200k token**.

Analizzando sessioni reali di coding su MacBook Apple Silicon da 16 GB sono emersi due problemi ricorrenti:
1. Rileggere da zero file e cartelle o far generare bozze ripetitive agli LLM cloud consuma inutilmente contesto, quando una gerarchia Merkle a 4 livelli (`light` / `medium` / `high` / `max`) + modelli locali risolvono il lavoro offline.
2. Senza dimensionamento dinamico su RAM libera reale, i runner locali troncano a `4096` token o mandano il sistema in swap.

Ho rilasciato **Cortical** in open source (Apache-2.0, Python 3.10+ stdlib pura, **0 dipendenze esterne, 0 demoni attivi**):
- **99.27% di riduzione token** sull'orientamento del progetto (`1.860` token `light` contro `255.360` raw su `43` moduli) e **99.20%** sui singoli file grandi
- **283.35 ms** per il crawl Merkle completo e **89.56 ms** per lo skip $O(1)$ sui file invariati
- **7.700 token offloaded in locale in 44.39s ($0 cloud)** concatenando `qwen2.5:1.5b` -> `qwen3.5:9b-q3_k_xl` -> `qwen3:8b` con `cortical local-loop`
- **Privacy by Design:** pseudonimizzazione offline, stripping metadati OOXML/PDF, Vault privati `@private:` con egress gate verso il cloud e risorse MCP native
- **951.7 µs** per la valutazione deterministica del Permission Gate

Compatibile con Claude Code, Codex CLI, Cursor, Windsurf, Cline, `pi`, OpenCode, Zed, Continue.dev e Antigravity.

Sito e configuratore interattivo: https://ccancellieri.github.io/cortical/  
Repository GitHub: https://github.com/ccancellieri/cortical

#LocalLLMs #OpenSource #MCP #IntelligenzaArtificiale #Privacy #Ollama #Python #Cortical

---

## 3. X / Twitter 5-Post Thread

1/5 Stop burning cloud tokens re-reading the same repo. Meet **Cortical** — a **zero-dependency, zero-server** 4-Tier Merkle Second Brain MCP, Multi-Model Local Offload engine, Privacy Sanitizer (`@private:`), and 200k Context Auto-Scaler.
Repo: https://github.com/ccancellieri/cortical | Docs: https://ccancellieri.github.io/cortical/

2/5 Most coding agents burn cloud context just finding files, while local models on 16 GB laptops either silently clip at `4096` tokens or swap. Cortical indexes code/docs into `light` (~50 tok) -> `max` tiers AND auto-scales `num_ctx` to live free RAM (`vm_stat` / `/proc/meminfo`).

3/5 Measured benchmarks on Apple M2 Pro (16 GB):
- 99.27% repo token reduction (1,860 `light` vs 255,360 raw across 43 Python modules)
- 283.35 ms cold Merkle crawl | 89.56 ms $O(1)$ delta skip
- 951.7 µs Permission Gate
- 7,700 tok offline in 44.39s across 1.5B -> 9B -> 8B Ollama models (0 cloud tokens)

4/5 Privacy stays local-first: strip OOXML/PDF binary metadata, pseudonymize emails/IDs/custom terms, auto-guard private folders across `.geminiignore`/`.cursorignore`/`.claudeignore`, and resolve `@private:<alias>` + `cortical://private/...` MCP resources before anything touches cloud egress.

5/5 Built in pure Python 3.10+ stdlib (`dependencies = []`) + SQLite WAL/FTS5. Works cleanly with Claude Code, Codex CLI, `pi`, OpenCode, Cursor, Windsurf, Zed, Continue, and Antigravity.
Run benchmarks locally:
`PYTHONPATH=src python3 scripts/benchmark.py`

---

## 4. Hacker News (`Show HN`)

- **Title:** `Show HN: Cortical – Zero-dep 4-tier Merkle Second Brain MCP, local multi-model loops & privacy sanitizer`
- **URL:** `https://github.com/ccancellieri/cortical`
- **Body:**
  Hi HN, I built **Cortical** (Apache-2.0, Python 3.10+ stdlib only, zero external runtime dependencies, zero background daemons) to solve two pain points I kept hitting across coding agent harnesses (`pi`, Claude Code, Codex CLI, OpenCode, Cursor, Antigravity):

  1. **Context bloat & redundant cloud reads:** `cortical-wiki-mcp` builds a deterministic bottom-up `sha256` Merkle tree in SQLite FTS5 with 4 progressive retrieval tiers (`light`, `medium`, `high`, `max`) plus native MCP `resources` and `prompts`. Across Cortical's own 43 Python modules, navigating at `light` drops 255,360 raw tokens to 1,860 (`99.27%`, measured via `scripts/benchmark.py` in `283.35 ms` cold / `89.56 ms` unchanged delta).
  2. **Under-used local hardware & privacy exposure:** `cortical local-loop` chains local Ollama / `llama.cpp` / `mlx-lm` models (e.g., `qwen2.5:1.5b` router -> `qwen3.5:9b-q3_k_xl` analyst -> `qwen3:8b` reviewer, with live RAM-aware `num_ctx` scaling up to 200k) to finish tasks offline and distill insights—while a deterministic Privacy Sanitizer strips OOXML/PDF metadata and gates `@private:` / `cortical://private/...` references (`max_security` blocks cloud egress completely).

  You also get **Cortical Skill Engine** (knowledge-linked `SKILL.md` consolidation), an adaptive sub-millisecond bash Permission Gate (`951.7 µs`), and static zero-server HTML dashboards (`wiki.html`, `token_report.html`, `settings.html`) saved strictly on your local disk.

  Live docs & configurator: https://ccancellieri.github.io/cortical/

---

## 5. Reddit (`r/LocalLLaMA` & `r/ClaudeAI`)

- **Title:** `[Open Source] Cortical: Zero-Dep Python 4-Tier Merkle Second Brain MCP + Multi-Model Ollama Offload Loops + Dynamic 200k num_ctx on 16GB Laptops`
- **Body:**
  Hey everyone — wanted to share **Cortical** (Apache-2.0, Python 3.10+ stdlib only, zero dependencies, no Docker/vector-DB daemon).

  It gives Claude Code / Codex / `pi` / OpenCode / Cursor / Antigravity:
  - **Multi-Model Local Offload (`cortical local-loop` / `cortical_local_loop` MCP):** Chains `qwen2.5:1.5b` -> `qwen3.5:9b-q3_k_xl` -> `qwen3:8b` offline. In `scripts/benchmark_local_offload.py` on a 16 GB Apple M2 Pro, a 3-pass grounded loop offloaded **7,700 tokens in 44.39s** (0 cloud tokens).
  - **RAM-Aware Dynamic `num_ctx` (up to 200k):** Inspects live free RAM (`vm_stat` / `/proc/meminfo`) and `/api/ps` / `/api/show` so local models scale cleanly without silent 4096 clipping or swap thrashing (`32,768` at 4 GB free -> `139,264` at 16 GB free for `qwen3.5:9b-q3_k_xl`).
  - **4-Tier Merkle Wiki + `@private:` Egress Gate:** Retrieve `light`/`medium`/`high`/`max` context via SQLite FTS5 (`99.27%` reduction on repo root), reference sensitive local docs without pasting raw paths using `@private:<alias>`, and block or pseudonymize cloud egress via configurable privacy profiles.
  - **0-Cloud-Token ROI Analytics & Cortical Skill Engine:** Track per-turn local vs cloud offload directly from local transcripts + SQLite telemetry.

  Docs & interactive configurator: https://ccancellieri.github.io/cortical/  
  GitHub: https://github.com/ccancellieri/cortical

---

## 6. Launch & Publishing Checklist

1. **GitHub Pages Enabled:** Repository `ccancellieri/cortical` Settings -> Pages -> Branch `main` / Folder `/docs` -> Live at `https://ccancellieri.github.io/cortical/`.
2. **PR #1 (`punkpeye/awesome-mcp-servers`):** Submit concise alphabetical entry in *Knowledge & Memory* (`🐍 🏠`).
3. **Showcase / Discussion #2 (`pi-coding-agent`):** Share `cortical-pi-harness` (`package.json` `"pi"` extension + `.agents/skills` + RAM-aware `num_ctx`).
4. **Benchmark Discussion #3 (`unsloth`):** Post 16 GB Apple Silicon GGUF numbers (`UD-Q3_K_XL` + `UD-IQ2_XXS`) alongside `scripts/benchmark.py` and `scripts/benchmark_local_offload.py`.
5. **Social Posts:** Publish LinkedIn (EN/IT), X thread, Show HN, and Reddit `r/LocalLLaMA`.
