# Ready-to-Submit Open-Source PR & Showcase Proposals

> **Live Site:** `https://ccancellieri.github.io/cortical/`  
> **Repository:** `https://github.com/ccancellieri/cortical`  
> All metrics below were measured directly on Apple M2 Pro (16 GB unified memory) using `scripts/benchmark.py`, `scripts/benchmark_local_offload.py`, and `unittest discover -s tests`.

---

## 1. `punkpeye/awesome-mcp-servers` — `cortical-wiki-mcp`

- **Target:** `punkpeye/awesome-mcp-servers` (*Knowledge & Memory* section)
- **Contribution Rules (`CONTRIBUTING.md`):** Strict alphabetical order, concise description, exact legend icons (`🐍` Python, `🏠` Local), public GitHub repo; optional `🤖🤖🤖` in PR title for fast-track review.
- **PR Entry:**
  `- [cortical](https://github.com/ccancellieri/cortical) 🐍 🏠 - Zero-dependency Python 3.10+ stdlib + SQLite FTS5 4-tier Merkle Tree (`light`/`medium`/`high`/`max`), Privacy Sanitizer (`@private:`), local multi-model offload & Episode Macro-Graph MCP server with relational RBAC.`
- **Measured Value:** `283.35 ms` cold crawl (43 Python modules), `89.56 ms` $O(1)$ unchanged delta skip, `99.27%` root context token reduction (`1,860` `light` root tokens vs `255,360` raw).

---

## 2. `pi-coding-agent` (`@earendil-works/pi-coding-agent`) — `cortical-pi-harness` Package

- **Target:** `pi` Packages / Community Extensions Showcase
- **Contribution Rules (`CONTRIBUTING.md`):** Keep `pi` core minimal (external `pi-package` via `package.json` `"pi"` field), strict TypeScript (`import type`, `node:` built-in imports), resilient error handling so extensions never crash the TUI.
- **Measured Value:** `951.7 µs` deterministic permission gate evaluation, dynamic `num_ctx` auto-scaler (`32,768` @ 4 GB free -> `139,264` @ 16 GB free for `qwen3.5:9b-q3_k_xl`), `7,700` local tokens across a 3-model chain in `44.39s` (`0` cloud tokens).
- **Summary:**
  - Exposes `cortical-wiki-mcp` (`wiki_search`, `wiki_navigate`, `wiki_record_episode`, `wiki_resolve_references`, `cortical_local_loop`, native MCP `resources` & `prompts`) and `.agents/skills/` (`cortical-token-saver`, `second-brain-3plus1-workflow`) as a standard `pi-package`.
  - Pre-send hook in `.pi/extensions/cortical-harness.ts` intercepts `@private:` / `/private` / `@wiki:` / `@concept:` / `@skill:` and applies the Privacy Egress Gate before remote transmission.
  - Adds `compute_dynamic_num_ctx` (`src/cortical/context_window.py`) + `cortical token-report --turn-only` at `0` cloud tokens.

---

## 3. `unsloth` / `unsloth-studio` — Apple Silicon 16 GB GGUF Benchmark & Auto-Tuner

- **Target:** Unsloth Discussions / Community Benchmarks
- **Title:** `Apple M2 Pro (16 GB) Benchmark: Unsloth Qwen3.8-27B UD-IQ2_XXS vs Qwen3.5-9B UD-Q3_K_XL + Multi-Model Local Offload & Dynamic num_ctx`
- **Observed Benchmarks (Ollama on 16 GB Apple M2 Pro):**
  | Model / Loop | Disk / Footprint | Throughput / Time | Context | Role |
  | --- | ---: | ---: | ---: | --- |
  | `qwen3:8b` | 5.2 GB | 28.6 tok/s (load 5.19s) | 32K | Fast local reviewer / coder |
  | `qwen3.5:9b-q3_k_xl` (`UD-Q3_K_XL`) | 5.1 GB | 25.0 tok/s (load 6.57s) | 131K | Daily local LLM & 131K context |
  | `qwen3.8:27b-iq2_xxs` (`UD-IQ2_XXS`) | 7.2 GB | 9.9 tok/s (load 15.73s) | 32K | Heavy reasoning / complex tasks |
  | `1.5b -> 9b -> 8b` 3-Pass Loop | 0 Cloud Tok | 7,700 tok in 44.39s (14.51 out tok/s) | Dynamic | Grounded offline synthesis |
- **Key Takeaway:** Pairing Unsloth's `UD-Q3_K_XL` (`5.1 GB`, `25.0 tok/s`) with fast `qwen2.5:1.5b` routing and `qwen3:8b` review under `compute_dynamic_num_ctx` lets 16 GB Apple Silicon machines offload multi-step agent loops swap-free with zero cloud token spend.

---

## 4. `opencode` — Pluggable `cortical-token-saver` + `second-brain-3plus1` + Cortical Skill Engine Pack

- **Target:** OpenCode Community Integrations
- **Summary:** Drop-in `opencode.json` + `.agents/skills/` bundle integrating `cortical-wiki-mcp`, universal `@private:` / `@wiki:` references, Privacy Sanitizer profiles, and Cortical Skill Engine consolidation so codebase navigation, privacy filtering, and test analysis run locally while reserving cloud models for high-level architecture and final review.
