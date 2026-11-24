# Cortical YouTube Mini-Series — Draft Scripts (`antigravity`, `pi`, `unsloth-studio`)

> **Status:** `DRAFT — DO NOT PUBLISH WITHOUT EXPLICIT USER APPROVAL`
> **Target Format:** 3 practical, terminal + browser (`docs/settings.html`) walkthroughs, 4–5 minutes each, zero theory slides.
> **Channel Workflow Note:** Export screen captures locally, attach YouTube chapters & verification commands below, review before uploading on YouTube, and cross-link the published video URL in the matching LinkedIn post (deleting temporary local covers/captures afterwards).

---

## Video 1 — Cortical + `pi`: Zero-Server `fail_closed` Privacy Vault, `TOON` (`-78%`) & Local-First Offload

- **SEO Title:** `Stop Leaking Client Data to Cloud LLMs: fail_closed Privacy Vault + TOON (-78% Tokens) in pi CLI`
- **Thumbnail Concept:** Split dark screen (`#09101f`): Left = red blurred `"IBAN / API KEY -> CLOUD"` blocked by cyan shield (`fail_closed · SHA-256`); Right = green pill **`-78.12% TOKENS · @role:fast_coder`**. Big top text: **`ZERO LEAKS · 0 DEPS`**.
- **Target Duration:** `4m 40s`

### Chapters (Timestamps)
- `00:00` — The Problem: Attaching raw PDFs/JSON dumps burns tokens and leaks secrets
- `00:45` — Interactive Preset C in `docs/settings.html` (Zero Install)
- `01:35` — Ingesting Markdown/PDF/PNG with `fail_closed` & verifying SHA-256 Audit Ledger
- `02:45` — Channel 1–3 isolation live inside `pi` (`@private:` + `cortical intercept`)
- `03:50` — Reproducible benchmark (`-78.12%` TOON & `-95.80%` `file_paths` local offload) + CTA

### Full Script (Voiceover + Screen Actions + Exact CLI)

1. **`[00:00 - 00:45]` Hook (Screen: Split terminal + clean repository):**
   - **Voiceover:** *"Every time you attach a client PDF or big JSON log to a cloud coding agent, two bad things happen: you pay 3x–4x in JSON token overhead, and you risk pushing PII or API keys outside your laptop. Today I'll show how Cortical solves both in pure Python stdlib—zero dependencies, zero background servers—wired directly into `pi`."*
2. **`[00:45 - 01:35]` Browser Walkthrough (Screen: Open `https://ccancellieri.github.io/cortical/settings.html` -> click **Preset C · Hybrid Remote Guard** -> open **Memory & Privacy Vault**):**
   - **Voiceover:** *"You don't even have to install anything to inspect the architecture. On GitHub Pages, click Preset C: notice the Hybrid Orchestrator locks into `fail_closed` remote mode using only an env var name like `GEMINI_API_KEY`, never a raw key, and the Vault enforces the `<= 15% num_ctx` budget across Channels 1, 2, and 3."*
3. **`[01:35 - 02:45]` Terminal Action (Screen: Live terminal):**
   - **Run:**
     ```bash
     PYTHONPATH=src .venv/bin/python -m cortical.cli ingest /tmp/demo_brief.md --alias demo_secret --policy fail_closed --profile max_security --custom-term "Acme FinTech S.r.l."
     PYTHONPATH=src .venv/bin/python -m cortical.cli vault audit --verify
     ```
   - **Voiceover:** *"Watch what happens when we ingest a technical Markdown brief, `.docx`, or selectable `.pdf` mixed with an IBAN, phone number, email, and custom client name under `max_security`—even with zero local LLM runner installed! Pure Python stdlib strips XML/PDF metadata, keeps `FastAPI`, `PostgreSQL`, and `Merkle Tree` 100% readable, masks every secret, and chains a SHA-256 audit proof via `cortical vault audit --verify`. Only image OCR (`@role:vision`) needs a local runner—and you can plug in Ollama, Unsloth Studio, LM Studio, llama.cpp, MLX, or vLLM."*
4. **`[02:45 - 03:50]` `pi` + Channel 3 Interception & `file_paths` Offload (Screen: Terminal running `intercept` & `stack_benchmark.py`):**
   - **Run:**
     ```bash
     PYTHONPATH=src .venv/bin/python -m cortical.cli intercept --harness pi --prompt "Review contract for Acme FinTech" --file /tmp/demo_brief.md --profile max_security
     ```
   - **Voiceover:** *"In `pi`, Channel 3 intercepts raw attachments before network dispatch, substituting a local-only stub directing the worker to `cortical_local_offload`. And for non-secret source files, passing `file_paths` directly into `cortical_local_offload` lets your local `@role:fast_coder` read 4,352 file tokens locally and return a 183-token summary—95.8% fewer cloud input tokens."*
5. **`[03:50 - 04:40]` Proof & CTA (Screen: `cortical bench --compare` output):**
   - **Run:**
     ```bash
     PYTHONPATH=src .venv/bin/python -m cortical.cli bench --compare
     ```
   - **Voiceover:** *"745 pretty JSON tokens drop to 163 via lossless TOON—minus 78.12%. Try the browser configurator or run `bench --compare` in 60 seconds. Links in the description."*

### YouTube Description (Draft)
```text
Zero-dependency, zero-server Privacy Vault (fail_closed), SHA-256 egress audit ledger, lossless TOON compression (-78.12% vs pretty / -62.09% vs compact JSON), and pi CLI Channel 1-3 interception.

Interactive 10-Second Browser Demo (no install):
https://ccancellieri.github.io/cortical/settings.html

GitHub Repository (Apache-2.0, Python 3.10+ stdlib only):
https://github.com/ccancellieri/cortical

Try locally in 60 seconds (safe --dry-run first):
git clone https://github.com/ccancellieri/cortical.git && cd cortical
python3 -m venv .venv && .venv/bin/pip install --no-deps -e .
PYTHONPATH=src .venv/bin/python -m cortical.cli bench --compare
PYTHONPATH=src .venv/bin/python -m cortical.cli doctor
PYTHONPATH=src .venv/bin/python -m cortical.cli sync --dry-run
# Apply with timestamped backup (undo anytime via: cortical sync --rollback <backup_id>):
PYTHONPATH=src .venv/bin/python -m cortical.cli sync
```

---

## Video 2 — Cortical + `antigravity`: Idempotent Config Sync, `--rollback` & Zero-Server Vault Dashboard

- **SEO Title:** `Sync 8 AI Coding Harnesses (Antigravity, Claude, Codex, pi) with 1 Command + Clean Rollback`
- **Thumbnail Concept:** Central `"CORTICAL SYNC"` button with cyan lines feeding `Antigravity`, `pi`, `Claude`, `Codex`, `dsh`, and a bright green **`--rollback` SAFE** badge.
- **Target Duration:** `4m 15s`

### Chapters (Timestamps)
- `00:00` — Why managing MCP configs & rules across 8 coding tools breaks every week
- `00:50` — Inspecting drift in `docs/settings.html` -> `Services & Harnesses`
- `01:50` — Previewing exact diffs with `cortical sync --dry-run` (credentials preserved!)
- `02:55` — Role abstraction (`@role:*`) + bidirectional `MEMORY.md` & `cortical curate`
- `03:45` — Applying & rolling back cleanly (`cortical sync --rollback <id>`)

### Full Script (Voiceover + Screen Actions + Exact CLI)

1. **`[00:00 - 00:50]` Hook (Screen: `Services & Harnesses` view in `docs/settings.html`):**
   - **Voiceover:** *"If you switch between Antigravity IDE, `pi`, Claude Code, Codex, and OpenCode, you know the pain: every tool expects a slightly different JSON, TOML, or YAML file—and one sloppy script wipes your existing keys. Cortical fixes config drift idempotently with zero daemons."*
2. **`[00:50 - 01:50]` Interactive Drawer & Guided Repair (Screen: Click `Inspect & Link →` on `antigravity` in `docs/settings.html`):**
   - **Voiceover:** *"Inside Cortical's static HTML dashboard, every harness shows live planned diffs before touching disk, OS-specific install recipes across macOS, Linux, and Windows, and a copy-ready Repair Playbook."*
3. **`[01:50 - 02:55]` Safe `--dry-run` Across `antigravity` + All 8 Harnesses (Screen: Terminal):**
   - **Run:**
     ```bash
     PYTHONPATH=src .venv/bin/python -m cortical.cli sync --harness antigravity,pi,unsloth-studio --dry-run
     ```
   - **Voiceover:** *"Notice `mcp_config.json` preserves unrelated servers while wiring `serena` and `cortical-mcp`, and `GEMINI.md` injects role-abstracted rules (`@role:orchestrator`, `@role:summarizer`) instead of hardcoding concrete model tags."*
4. **`[02:55 - 03:45]` Self-Curating Skills & `MEMORY.md` Sync (Screen: Terminal):**
   - **Run:**
     ```bash
     PYTHONPATH=src .venv/bin/python -m cortical.cli curate --dry-run
     PYTHONPATH=src .venv/bin/python -m cortical.cli memory-sync --direction export --dry-run
     ```
   - **Voiceover:** *"Cortical also exports distilled zero-PII concepts into human-readable `MEMORY.md` (`cortical memory-sync`) and compiles verified procedures into `.agents/skills/cortical-self-curated/SKILL.md` (`cortical curate`)."*
5. **`[03:45 - 04:15]` Timestamped Backup & Exact Rollback (Screen: Terminal):**
   - **Run:**
     ```bash
     PYTHONPATH=src .venv/bin/python -m cortical.cli sync --harness antigravity
     # Undo anytime with exact backup ID:
     # PYTHONPATH=src .venv/bin/python -m cortical.cli sync --rollback <backup_id>
     ```
   - **Voiceover:** *"Every sync creates a timestamped snapshot so `--rollback <id>` restores exact prior bytes—or deletes newly created files—in one second. Test it via `--dry-run` today."*

### YouTube Description (Draft)
```text
Declarative cross-platform MCP + rule sync across 8 harnesses (Antigravity, pi, OpenCode, OpenClaw, Codex, Claude Code, DeepSeek dsh, Unsloth Studio) with timestamped --rollback and 10 reusable model roles (@role:*).

10-Second Interactive Dashboard:
https://ccancellieri.github.io/cortical/settings.html

Repository & Docs:
https://github.com/ccancellieri/cortical
```

---

## Video 3 — Cortical + `unsloth-studio`: Running `27B` Variable-Quant Models @ `65K` Context on a 16 GB Laptop

- **SEO Title:** `Run 27B Models at 65,536 Context on a 16GB Laptop (No Silent 4096 Clipping or Swap Stalls)`
- **Thumbnail Concept:** Hardware memory bar (`9.08 GiB Metal VRAM · 0 Swap`), red strikethrough **`4096 Clip / 300s Timeout`** vs glowing green **`65,536 num_ctx · Unsloth 27B XXS`**.
- **Target Duration:** `4m 30s`

### Chapters (Timestamps)
- `00:00` — Why `27B` models silently clip to `4096` tokens or time out at `300s`
- `00:55` — Hardware Preflight in Browser (`Preset A` 4 GB Hybrid vs `Preset B` 16 GB Unified)
- `01:55` — Checking real hardware ceiling & Metal/VRAM math via `cortical doctor`
- `03:00` — Generating `unsloth-studio` & LiteLLM router configs (`reasoning_effort=none`, `600s`)
- `03:50` — Live `pi` verification + `ollama /api/ps` proving `context_length: 65536` in `9.08 GiB`

### Full Script (Voiceover + Screen Actions + Exact CLI)

1. **`[00:00 - 00:55]` Hook (Screen: `Models & Hardware Auto-Tuner` + terminal):**
   - **Voiceover:** *"You pull an Unsloth Dynamic 27B GGUF on a 16 GB laptop, expecting deep architectural reasoning—and either Ollama quietly clips your context to `4096`, or your harness times out after 300 seconds in hidden `<think>` loops. Here is how Cortical calculates the exact hardware KV ceiling so 27B models stay 100% inside VRAM."*
2. **`[00:55 - 01:55]` Interactive Presets A & B (Screen: `docs/settings.html` Overview -> **Load Tier 1A Preset** -> **Load Tier 1B 27B Preset** -> **Models & Hardware**):**
   - **Voiceover:** *"In `settings.html`, Preset A tunes a 4 GB VRAM hybrid Windows/Linux laptop (`@role:router` in VRAM + `9B` hybrid), while Preset B tunes 16 GB Unified Apple Silicon: `27B` `UD-IQ2_XXS` expands to `65,536` tokens (`600s` adaptive timeout), and `9B` `UD-Q3_K_XL` reaches `98,304` tokens—all customizable through Cortical's 10 semantic roles."*
3. **`[01:55 - 03:00]` Hardware Preflight CLI (Screen: Terminal):**
   - **Run:**
     ```bash
     PYTHONPATH=src .venv/bin/python -m cortical.cli doctor
     PYTHONPATH=src .venv/bin/python -m cortical.cli models recommend
     ```
   - **Voiceover:** *"Look at `cortical doctor`: on a 16 GB M2 Pro (`11.2 GB` Metal limit), Cortical assigns `qwen3.8:27b-iq2_xxs` to `@role:deep_reasoner` at `num_ctx=65,536` (`timeout=600s`) and `qwen3.5:9b-q3_k_xl` to `@role:daily_coder` at `num_ctx=98,304`."*
4. **`[03:00 - 03:50]` `unsloth-studio` & Router Integration (Screen: Open `~/.cortical/unsloth-studio-mcp.json` or terminal preview):**
   - **Run:**
     ```bash
     PYTHONPATH=src .venv/bin/python -m cortical.cli sync --harness unsloth-studio --dry-run
     ```
   - **Voiceover:** *"For Unsloth Studio workflows (`unsloth start pi`, `claude`, `opencode`, `dsh`), Cortical writes the hardware context profile (`weights_gb`, `gguf_arena_overhead_gb`, `kv_budget_gb`), sets `keep_alive: 30m`, and disables blocking `<think>` via `reasoning_effort: none` by default."*
5. **`[03:50 - 04:30]` Live Metal VRAM Proof (Screen: `ollama /api/ps` output):**
   - **Run:**
     ```bash
     curl -s http://127.0.0.1:11434/api/ps | python3 -m json.tool
     ```
   - **Voiceover:** *"Result verified live: `qwen3.8:27b-iq2_xxs` loaded with `context_length: 65536` and `size == size_vram == 9,751,316,397` bytes—9.08 GiB 100% in Metal VRAM, zero CPU swap."*

### YouTube Description (Draft)
```text
How Cortical auto-tunes Unsloth Dynamic variable-quant models (UD-IQ2_XXS, Q4_XXS, UD-Q3_K_XL) and connects unsloth-studio wrappers cleanly: 65,536 context in 9.08 GiB Metal VRAM on a 16 GB laptop without 4096 clipping or 300s timeouts.

Try Preset A & Preset B Online:
https://ccancellieri.github.io/cortical/settings.html

GitHub:
https://github.com/ccancellieri/cortical
```
