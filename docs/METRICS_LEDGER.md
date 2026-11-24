# Cortical Metrics Ledger & KPI Scorecard

Single source of truth for **Cortical** (`https://github.com/ccancellieri/cortical`) product quality, demo friction, upstream ecosystem hooks, and organic adoption metrics. Every number below is captured directly from live command executions (zero fabricated metrics).

---

## 1. Verified Baseline (`2026-11-24`, Updated Post-Sprint)

### A. Product, Stability & Token Economics KPIs

| Metric | Verified Baseline (`2026-11-24`) | Target (30-Day) | Verification Command |
| --- | --- | --- | --- |
| **External Runtime Dependencies** | **`0`** (`dependencies = []`) | `0` (invariant) | `grep dependencies pyproject.toml` |
| **Unit & Integration Tests** | **`57 / 57` PASS** (`0` failures, `0` skips, `2,678` test LOC) | `>= 60` (`100%` pass) | `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q` |
| **Codebase Size (`src/cortical/`)** | **`19,086` total LOC** (**`15,048` Core Python/CLI/Wiki** + **`4,038` embedded zero-CDN HTML/CSS/JS SPA templates**; `-40.0%` vs `~31.8K` LOC `legacy-v0.2`) | Modular 7-package core | `wc -l src/cortical/*.py src/cortical/*/*.py` |
| **Zero-LLM Privacy Vault Independence** | **`100%` offline stdlib** (MD/DOCX/XLSX/PPTX/PDF + SHA-256 ledger verified on unreachable runner port `:9`) + **7 local runners** (`ollama`, `unsloth`, `lm_studio`, `llama_cpp`, `mlx_lm`, `vllm`, `openai_compatible`) | `100%` Tier-1 zero-LLM | `unittest` `test_zero_runner_privacy_vault_and_toon_operate_100pct_offline` |
| **TOON Lossless Compression** | **`-78.12%` vs pretty JSON** · **`-62.09%` vs compact JSON** (`745`/`430` -> `163` tok) | `>= 60%` vs compact | `PYTHONPATH=src .venv/bin/python -m cortical.cli bench --compare` |
| **Privacy Sanitizer Precision** | **`100.0%` tech prose preserved** · `policy=fail_closed` · `pii_masked=True` | `100.0%` | `cortical bench --compare` |
| **Lean 7-Tool MCP Handshake** | **`4.26–4.74 ms`** (`ingest+read`, `7` core tools + opt-in `5`-tool `cortical-wiki` + 10 semantic `@role:*` slots) | `< 10 ms` | `cortical bench --compare` |
| **Tier 1B 27B Auto-Context (`pi`)** | **`65,536` ctx** (`@role:deep_reasoner`, `9.08 GiB` Metal VRAM, `timeout=600s`, `reasoning_effort=none`) | `0` timeouts / `0` truncations | `pi -p --no-session --model router/cortical-deep` + `ollama /api/ps` |
| **Real-World `pi` Local Offload (`01a20890`)** | **`3,481,633` local tokens** (`3,452,912` in + `28,721` out, `$0` cloud cost) | `>= 80%` local offload | `~/.pi/agent/sessions/...01a20890...jsonl` |
| **GitHub Issues Resolved** | **`49` closed / `10` open** (`59` total) | `>= 90%` core issues closed | `gh issue list --state all --limit 100` |

### B. Demo Friction KPIs

| Metric | Baseline (`2026-11-24`) | Target |
| --- | --- | --- |
| **Online Time-to-First-Value** | `10s` via [`https://ccancellieri.github.io/cortical/settings.html`](https://ccancellieri.github.io/cortical/settings.html) (0 install, 3x 1-Click Interactive Presets, 0 external CDNs) | `< 10s` |
| **Local Time-to-First-Value** | `< 60s` (`git clone` -> `python3 -m venv .venv` -> `cortical bench --compare` / `doctor`) | `<= 3` copy-paste commands |

### C. Upstream Ecosystem KPIs

| Target Repo | Category | Cortical Issue | Status |
| --- | --- | --- | --- |
| `modelcontextprotocol/servers` & Glama | MCP Registry | `#44` (Closed) | `server.json` & `glama.json` `0.3.0` ready |
| `deepseek-ai/deepseek-harness` (`dsh`) | Coding Harness | `#45` (Closed) | `cortical-cordis-hook.mjs` shipped in `hooks.py` |
| `anomalyco/opencode` | Coding Harness | `#46` (Closed) | `cortical-hook.mjs` + slash cmds shipped in `hooks.py` |
| `earendil-works/pi` | Coding Harness | `#47` (Closed) | `cortical-intercept.ts` + `cortical-global.ts` shipped |
| `LiteLLM` / `OmniRoute` / `CCR` | Local Router | `#51` (Closed) | `litellm_cortical_guard.py` shipped in `hooks.py` |
| `Serena` + `RTK` + `context-mode` + `TOON` | Token Stack | `#48` (Open) | Composable benchmark & interop guide drafted |
| `drmikecrowe/harnessed` | Meta-Harness | `#49` (Open) | Declarative DLP & quant preflight proposal drafted |
| `unslothai/unsloth` / Ollama docs | Local Quant | `#50` (Open) | Variable-quant `auto_ctx` (`65K`/`98K`) recipe drafted |

### D. Distribution & Adoption KPIs (`gh api`)

| Metric | Baseline (`2026-11-24`) | 30-Day Target |
| --- | --- | --- |
| **GitHub Stars** | `0` | `>= 50` |
| **GitHub Forks** | `0` | `>= 10` |
| **14-Day Repo Views** | `9` views (`7` unique) | `>= 500` views |
| **14-Day Repo Clones** | `218` clones (`106` unique) | `>= 300` clones |
| **Verified LinkedIn Posts Ready / Published** | `3` ready (`EN` + `IT`) / `0` published | `3` published |

---

## 2. Weekly Automated Measurement Cadence

Run every Monday (or via `/schedule`) to refresh this ledger with zero manual guesswork:

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q
PYTHONPATH=src .venv/bin/python -m cortical.cli bench --compare
PYTHONPATH=src .venv/bin/python -m cortical.cli roi
gh api repos/ccancellieri/cortical --jq '{stars:.stargazers_count,forks:.forks_count,open_issues:.open_issues_count}'
gh api repos/ccancellieri/cortical/traffic/views --jq '{views:.count,uniques:.uniques}'
gh api repos/ccancellieri/cortical/traffic/clones --jq '{clones:.count,uniques:.uniques}'
```

---

## 3. Empirical 4-Layer Composable Stack Benchmark (`scripts/stack_benchmark.py`, `#48`)

Measured directly on `ccancellieri/cortical` (`2026-11-24`):

| Layer | Baseline (Raw) | Optimized | Measured Saving |
| --- | --- | --- | --- |
| **1. Symbol Navigation (`Serena` AST read: `vault.py` -> `verify_audit_ledger`)** | `11,020` tok | `464` tok | **`-95.79%`** |
| **2. Shell Compaction (`RTK` on `git log -n 30`)** | `1,854` tok | `902` tok | **`-51.35%`** *(note: `--stat` passes through)* |
| **3. Structured Payload (`Cortical TOON` lossless)** | `745` pretty / `430` compact tok | `163` tok | **`-78.12%` / `-62.09%`** |
| **4. Local File Offload (`cortical_local_offload(file_paths=...)`, `@role:fast_coder`)** | `4,352` raw file tok | `183` returned tok | **`-95.80%` cloud input** (`31.72s`, `$0` cloud) |
