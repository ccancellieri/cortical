# Cortical LinkedIn Articles & Launch Posts — Verified Draft Kit

> **Status:** `DRAFT — DO NOT PUBLISH WITHOUT EXPLICIT USER APPROVAL`
> **Verification Ground Truth (`2026-11-24`, Certified `GO` — `ADR-016`):**
> Every single number below was directly measured via `unittest` (`57/57` PASS, `2,678` test LOC), `wc -l` (`19,086` total `src/cortical/` LOC = `15,048` Core Python/CLI/Wiki + `4,038` embedded zero-CDN HTML/CSS/JS SPA templates, `-40.0%` vs `~31.8K` `legacy-v0.2`), `cortical bench --compare`, `scripts/stack_benchmark.py`, and live `pi` + local Metal VRAM telemetry.
> **Cover Image Rule:** Attach the matching temporary 16:9 cover image from the artifact folder when publishing, then delete the cover file after posting (never commit cover images to git).

---

## Article 1 — Architecture, Zero-LLM Privacy Vault & Multi-Runner Craft (Long-Form)

**Title:** Why We Replaced a 31.8K-LOC Monolith With a Zero-Dependency, Zero-Server Agent Control Plane (And a Privacy Vault That Needs Zero LLMs)

Most open-source AI agent tools today start with `npm install`, three Docker containers, a background FastAPI daemon, and 45 transitive packages—just to mask PII, configure MCP tools, and route prompts.

When we audited our own early v0.2 codebase (**~31.8K LOC**), we realized we were rebuilding things great open-source tools already do better: LSP code navigation (`Serena`), shell log compaction (`RTK`), subprocess sandboxing (`context-mode`), and local model serving (`Ollama`, `Unsloth Studio`, `LM Studio`, `llama.cpp`, `MLX`, `vLLM`).

So we stripped everything down to a single rule in `pyproject.toml`:

```toml
dependencies = []
requires-python = ">=3.10"
```

### The Result (`v0.3.0`, Verified Today)
Instead of running another daemon, **Cortical** is a **100% stdlib Python composable control plane** (**`19,086` total LOC** across 7 modular packages: **`15,048` Core Python/CLI/Wiki LOC** + **`4,038` embedded zero-CDN HTML/CSS/JS SPA LOC**, **`-40.0%`** smaller than `legacy-v0.2`) backed by **`57/57` passing tests** (`unittest`):

1. **Zero-LLM Fail-Closed Privacy Vault (Works Without Any Local Runner):** Before a single token reaches a cloud agent, Cortical strips hidden `.docx`/`.xlsx`/`.pptx`/selectable `.pdf` XML metadata, masks Email/IBAN/Tax ID/Phone/IP/API secrets + custom client terms (`100.0%` technical identifiers preserved), enforces `fail_closed` egress across 3 channels, and chains every event into a cryptographic **SHA-256 audit ledger**—**100% in Python stdlib with zero local LLM installed**.
2. **Runner-Neutral Multi-Runner Support + 10 `@role:*` Slots:** When you want local inference, OCR (`@role:vision`), or zero-cloud-token file offload (`@role:daily_coder`, `@role:reviewer`), Cortical connects cleanly to **Ollama, Unsloth Studio, LM Studio, llama.cpp, Apple MLX, vLLM, or any OpenAI-compatible server** without hardcoding model tags.
3. **Safe 4-Step Sync Across 8 Harnesses:** Preview exact diffs first via `cortical sync --dry-run`, then sync `Antigravity`, `pi`, `OpenCode`, `OpenClaw`, `Codex`, `Claude Code`, `DeepSeek Harness (dsh)`, and `Unsloth Studio` with automatic timestamped `cortical sync --rollback <backup_id>` snapshots.
4. **Lean 7-Tool `stdio` MCP (`~4.5 ms` handshake) + Zero-CDN Browser SPA:** Exposes 7 core MCP tools (+ opt-in 5-tool `cortical-wiki`), lossless `TOON` compression (`-78.12%` vs pretty / `-62.09%` vs compact JSON), and an interactive GitHub Pages control plane (`0` external CDNs).

**Explore the live landing page & 10-second browser control plane:**
https://ccancellieri.github.io/cortical/ · https://ccancellieri.github.io/cortical/settings.html
**Inspect the code & challenge our benchmarks:** https://github.com/ccancellieri/cortical

---

### Short Launch Post for Article 1 (`DRAFT` — Pair with Cover Image 1)
*(Attach temporary cover `linkedin_cover_post1_zero_deps_1795519693902.jpg`, publish, then delete the image file.)*

Most AI agent control planes ship with a background server, Docker, spaCy/Presidio, and 40+ dependencies—and lock you into a single local model runner.
We locked **Cortical** to `dependencies = []` (Python 3.10+ stdlib only) and **0 background daemons**.

What works **immediately with ZERO local LLM runner** (Tier 1 Stdlib):
- **Fail-Closed Privacy Vault + SHA-256 Audit Ledger:** Strips `.docx`/`.xlsx`/`.pptx`/`.pdf` metadata & masks PII/secrets (`100.0%` tech terms preserved)
- **Lossless `TOON` Compression:** **`-78.12%`** vs pretty JSON (**`-62.09%`** vs compact)
- **Safe 8-Harness Sync:** Preview first via `--dry-run`, undo anytime via `--rollback <id>` across `Antigravity`, `pi`, `Claude Code`, `Codex`, `OpenCode`, `OpenClaw`, `dsh` & `Unsloth Studio`

And when you add **any** local runner (**Ollama, Unsloth Studio, LM Studio, llama.cpp, MLX, or vLLM**), 10 reusable `@role:*` model slots unlock local OCR & `-95.80%` cloud-input file offload (`57/57` `unittest` passing; `15,048` Core Python LOC + `4,038` zero-CDN SPA LOC).

Test online in 10s (zero install): https://ccancellieri.github.io/cortical/settings.html
Or verify safely in 60s (`--dry-run` modifies 0 files):
```bash
git clone https://github.com/ccancellieri/cortical.git && cd cortical
python3 -m venv .venv && .venv/bin/pip install --no-deps -e .
PYTHONPATH=src .venv/bin/python -m cortical.cli bench --compare
PYTHONPATH=src .venv/bin/python -m cortical.cli doctor
PYTHONPATH=src .venv/bin/python -m cortical.cli sync --dry-run
```
Which local runner (or cloud + local mix) is powering your coding workflow right now?

---

## Article 2 — Privacy, Token Economics & 27B Local Hardware (Long-Form)

**Title:** Cutting JSON Tokens by 78%, Stopping Cloud Leaks (`fail_closed`), and Running 27B Models at 65K Context on a 16 GB Laptop

When mixing frontier cloud models with local coding assistants, three silent leaks hurt teams every day:
1. **The JSON & File-Read Tax:** Dumping raw files and pretty JSON into frontier prompts.
2. **Unmasked Egress:** Accidentally leaking customer names, IBANs, internal IPs, or `.pdf`/`.docx` author metadata through MCP reads or attachments.
3. **Silent Local Truncation:** Pulling a quantized `27B` reasoning model on a 16 GB laptop, only to have Ollama silently clip context to `4096` tokens or time out at `300s`.

We measured all three layers empirically in **Cortical** (0 external Python dependencies):

### 1. Stackable Token Savings (Reproducible via `bench --compare` & `scripts/stack_benchmark.py`)
- **Lossless `TOON` Compression:** `745` pretty JSON tokens (`430` compact) compress to **`163` tokens** (**`-78.12%` vs pretty / `-62.09%` vs compact JSON**), verified lossless on round-trip.
- **Direct Local `file_paths` Offload:** Calling `cortical_local_offload(role="fast_coder", file_paths=[...])` lets local models read **`4,352` raw file tokens** from disk and return **`183` summary tokens** to the remote orchestrator (**`-95.80%` cloud input**, `$0` cloud cost).
- Paired with **`Serena`** AST symbol reads (**`-95.79%`**, `11,020 -> 464` tok) and **`RTK`** shell compaction (**`-51.35%`** on `git log -n 30`), every layer compounds cleanly.

### 2. Zero-LLM `fail_closed` Privacy Vault + SHA-256 Audit Ledger (Works Without Any Local Runner!)
- **100% Python Stdlib (Zero Local LLM Needed):** Strips OOXML (`core.xml`, `app.xml`, `comments.xml`) and selectable PDF `/Author` metadata, and masks PII/secrets/custom terms while preserving **`100.0%` of technical terms** (`FastAPI`, `PostgreSQL`, `Merkle Tree`). For images and scanned PDFs, optional offline OCR (`@role:vision` via `cortical watch`) supports **Ollama, Unsloth Studio, LM Studio, llama.cpp, MLX, and vLLM**.
- Blocks `max_security` items from remote orchestrators across MCP (Channel 1), `sync` rules (Channel 2, `<= 15% num_ctx`), and pre-send interception (Channel 3), recording every blocked egress in a tamper-evident **SHA-256 hash chain** (`cortical vault audit --verify`) with **0 plaintext PII stored**.

### 3. Hardware-Ceiling `auto_ctx` for `27B` Models on `16 GB` RAM Across Local Runners
By modeling actual GQA KV-cache density and Apple Silicon Metal working-set ceilings (`~11.2 GB` on 16 GB M2 Pro), Cortical dynamically configures `@role:deep_reasoner` (`27B` `UD-IQ2_XXS`) at **`65,536` tokens** (`reasoning_effort=none`, `keep_alive=30m`, `600s` adaptive timeout)—verified live using **`9.08 GiB` Metal VRAM (`size == size_vram`, 0 CPU swap)**.

**Try Preset A (4 GB Hybrid), Preset B (16 GB 27B), or Preset C (Remote Guard) in 10s:**
https://ccancellieri.github.io/cortical/ · https://ccancellieri.github.io/cortical/settings.html

---

### Short Launch Post for Article 2 (`DRAFT` — Pair with Cover Image 2 or Cover Image 3)
*(Attach `linkedin_cover_post2_toon_privacy_1795519694366.jpg` or `linkedin_cover_post3_27b_laptop_1795519737079.jpg`, publish, then delete the temporary image file.)*

Sending raw client docs and verbose JSON to cloud LLMs costs you twice: token bloat and accidental data leaks.
And you shouldn't need a heavy NLP stack—or even a running local LLM—just to sanitize `.docx`, `.xlsx`, `.pdf`, and `.md` files safely.

What we verified empirically in **Cortical** (`dependencies = []`, Python 3.10+ stdlib, `57/57` tests passing):
- **Zero-LLM Privacy Vault (`Tier 1 Stdlib`):** Strips `.docx`/`.pdf` metadata, preserves **`100.0%`** technical prose, enforces `fail_closed`, and logs a **SHA-256 audit chain** (`cortical vault audit --verify`) with **zero local model required**
- **`-78.12%` / `-62.09%`** lossless `TOON` compression (`745` / `430` -> `163` tok)
- **7 Local Runners (`Tier 2`):** Connect **Ollama, Unsloth Studio, LM Studio, llama.cpp, MLX, or vLLM** via `@role:*` slots for **`-95.80%`** cloud-input file offload (`4,352` -> `183` tok) and **`65,536` context** on `27B` variable quants in **`9.08 GiB` Metal VRAM** (`0` swap)

Inspect live in browser: https://ccancellieri.github.io/cortical/settings.html
Reproduce safely (`--dry-run` touches 0 files):
```bash
PYTHONPATH=src .venv/bin/python -m cortical.cli bench --compare
PYTHONPATH=src .venv/bin/python -m cortical.cli doctor
PYTHONPATH=src .venv/bin/python -m cortical.cli sync --dry-run
```
Are you sanitizing client docs deterministically before cloud prompts, or still relying on `.gitignore` alone?
