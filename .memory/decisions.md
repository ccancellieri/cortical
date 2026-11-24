# Decisioni — CLI Command `/cortical` e Dashboard UX Improvements

**Data:** 2026-07-XX | **Sessione:** #6 Follow-up  
**Status:** Completato ✅

---

## Comando Nuovo: `cortical` (con slash pattern)

### Descrizione
Aggiunta un nuovo sottocomando `cortical` (da usare come `/cortical`) che apre l'UI Zero-Server statica direttamente dal CLI, senza dover ricordare il percorso esatto dell'HTML.

### Sintassi
```bash
# Apri dashboard nel browser
cortical --open

# Export con report JSON
cortical --json

# Export in una cartella personalizzata
cortical --out-dir /path/to/html --open

# Versione pubblica pulita (senza config locale)
cortical --public-docs
```

### Implementazione
- **Funzione:** `_cmd_cortical_dash()` in `src/cortical/cli.py`
- **Linee chiave:** 548-577
- **Args:** `--open`, `--out-dir`, `--public-docs`, `--json`
- **Behavior:**
  - Exporta `settings.html` + `help.html` nella cartella indicata (o `html/` come default)
  - Genera report JSON con percorsi dei file exportati
  - Opzionale: apre la dashboard nel browser predefinito con `--open`
  - Usa `probe_hardware()` per rilevare tier/hardware e passa i dati al renderer HTML

### Esempi
```bash
# Semplice: apre l'HTML nel browser
cortical --open

# JSON report (utile per CI/script)
cortical --json
# Output:
# {
#   "dashboard": "/path/to/html/settings.html",
#   "help": "/path/to/html/help.html",
#   "exported": true,
#   "public_docs": false
# }

# In una cartella specifica
cortical --out-dir ./ui --open
```

---

## Miglioramenti UX Dashboard HTML (Issue #6 Item 1)

### Cambiamenti Implementati

#### 1. Upload File con Pre-filling & Alias Sanitization
- **File:** `src/cortical/analytics/dashboard.py`
- **Funzione:** `pickFileObj()` e `modelCard()`
- **Cambiamenti:**
  - ✅ Saniore generazione alias: rimuove caratteri non consentiti (`< > : / \ | ?`)
  - ✅ Pre-filling dei termini custom quando si carica file testuale (`pdf`, `docx`, `xlsx` ecc.)
  - ✅ Mostra lista modelli visione disponibili sotto il selector

#### 2. Model Selector UX Improvements
- **Visual indicatori:** Badge `✓` per modelli già installati in Ollama
- **Alert informativi:**
  - Se nessun modello visione installato → mostra comando `ollama pull ...` con pulsante "📋 Copia comando"
  - Se il modello selezionato non è scaricato → mostra alert + pulsante "📥 Scarica"
- **Elenco modelli:** Mostra tutti i modelli vision disponibili se presenti

#### 3. Feedback Coda Job in Elaborazione
- **Badge verde** `⏳ Job in coda: X/Y` durante l'upload
- **Position:** Sotto il pulsante "Upload" nella scheda Privacy Vault

---

## Test & Validazione

### Test Passati
```bash
# Suite completa
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p "test_cortical.py"
# Risultato: 14/14 OK ✓

# Sintassi Python
PYTHONPATH=src .venv/bin/python -m py_compile src/cortical/cli.py
# Risultato: ✓ Syntax OK

# Export HTML
PYTHONPATH=src .venv/bin/python -c "from cortical.analytics.dashboard import export_static_dashboard; from pathlib import Path; s, h = export_static_dashboard(Path('/tmp/cortical_ui_test'), public_docs=True); print('✓', s.name, '(', s.stat().st_size, 'bytes)')"
# Risultato: settings.html (90KB) ✓

# Comando CLI
PYTHONPATH=src .venv/bin/python -m cortical.cli cortical --help
# Output: uso: cortical cortical [-h] [--open] [--out-dir OUT_DIR] [--public-docs] [--json] ✓
```

---

## Sessione Successiva
**Backlog Item 2:** Oscuramento file privati & Privacy Vault  
- Anteprima chiara del testo mascherato  
- Gestione profili (`max_security`, `low`, `medium`, `max_context`) e `custom_terms`  

Comando per riprendere in locale:
```bash
python -m unittest discover -s tests -p "test_cortical.py"
```

---

## Aggiornamento Cross-Harness, Golden Value, RTK 1.2.1 & Dashboard Live (`--serve`)

**Data:** 2026-11-23 | **Sessione:** #6 Loop #2 & #3 Infra  
**Status:** Verificato (`18/18` test OK)

- **Chrome Autonomous Session (`chrome.py`, `adapters.py`, `~/.pi/agent/mcp.json`, `cortical-global.ts`)**:
  - `chrome-devtools-mcp` migrato a `--autoConnect` cross-platform (Win/Lin/Mac), eliminando i riavvii del Chrome personale.
  - Aggiunto `probe_cdp()` fallback su `DevToolsActivePort` e **Task Tab Groups** per isolare le tab di ciascuna sessione/task (`chrome_tab_group` + `~/.cortical_data/chrome_tab_groups.json`).
- **ROI Reale Unificato (`roi.py`, `mcp_server.py`, `cortical-global.ts`)**:
  - Corretto il DB telemetrico in `cortical_roi_report` (`DEFAULT_TELEMETRY_DB` invece di `vault.db`).
  - Integrato `collect_pi_local_runs()` dalle sessioni locali `~/.pi/agent/sessions/**/*.jsonl` + riga cumulativa ROI + badge live `agent_end` in `pi`.
- **Routing per Macchina (`router.py`)**:
  - Aggiunti alias semantici `cortical-fast`, `cortical-deep`, `cortical-vision` in `litellm_config.yaml` (`:4000/v1`).
- **Golden Value & Dashboard UI/UX (`vault.py`, `mcp_server.py`, `dashboard.py`)**:
  - Upload multi-file + intere directory (`webkitdirectory`), `task_tags` persistenti in SQLite/Vault JSON e `cortical_vault_read(task_tag=..., tier=...)` (con blocco `max_security` dall'egress cloud).
  - Risolto `UnboundLocalError` su `res["auto_detected_tags"]` in `vault.py`.
  - Aggiunti selettore **Target Machine OS**, **Vision/OCR Model**, comando slash `/cortical-dashboard` su `pi`/Claude/Antigravity/Codex.
- **RTK 1.2.1 & Live Tool Management (`tools.py`, `cli.py`, `dashboard.py`)**:
  - Installato `/opt/homebrew/bin/rtk` (`1.2.1`) e configurati hook globali su Claude Code, `pi`, Antigravity e Codex.
  - Aggiunti `test_composed_tool()`, `install_composed_tool()`, CLI `cortical tools {status,test,install}`, server `--serve` (`http://127.0.0.1:8787/settings.html`) con pulsanti UI **`🧪 Test`** e **`⬇️ Install`**.


---

## Sessione 2026-11-23 — Zero-Friction DX, IDE Integrations, Zero-Server 6-Domain Dashboard & Synchronized ADRs

- **Issues #8 & #9 (Closed):** Added `install.sh`, `Makefile`, `src/cortical/workspace.py` (`cortical init`, Git-style `.cortical/` discovery, `.corticalignore` sync), and `src/cortical/integrations.py` (`cortical integrate` with `.bak` + `--dry-run`, enhanced `cortical doctor` stdio JSON-RPC ping).
- **Issues #12–#16, #19 (Closed) + ADRs #10–#11 (Renumbered ADR-005/ADR-006):** Added opt-in `--serve` multi-tenant Knowledge/Merkle/FTS5/RBAC engine (`src/cortical/wiki/{store,mcp_server}.py`, `src/cortical/dashboard_api.py`, `src/cortical/dashboard_ui.py`).
- **Issues #24, #26–#28 (Closed) + ADRs #20–#23, #29 (ADR-001..004, ADR-007):** Created `docs/adr/` synchronized 1:1 with GitHub Issues, built `src/cortical/analytics/snapshot.py` + `src/cortical/analytics/zero_server_ui.py`, and published zero-server `docs/settings.html` (with real `dry_run` harness diffs and client-side multi-file/`task_tags` Privacy Vault upload/masking).
- **Open Follow-ups:** Issue #7 (SSOT reconciliation), Issue #17 (stale default model ID `qwen3.8:27b-q4_xxs` in `config.py`), Issue #18 & #25 (roadmap ideas).

- **ROI Zero-Token Bug Fixed (`src/cortical/analytics/roi.py` & `snapshot.py`):**
  1. Antigravity `transcript.jsonl` stores `input_tokens`, `cache_read_tokens`, and `output_tokens` at top-level (not nested under `usage`); `roi.py` now reads both top-level and `usage` + bumped cache signature to v2 to auto-invalidate stale `0`-token caches.
  2. Sorted parsed remote transcripts by `mtime_ns` descending so `chats[0]` is always the active conversation (instead of alphabetically first UUID).
  3. Included `collect_pi_local_runs()` when `db_path == DEFAULT_TELEMETRY_DB` (not only `db_path is None`), and fixed `snapshot.py` to read `local.global.run_count` and `_estimate_cost(...)`.
  4. Note: Antigravity's long-running `cortical-mcp` stdio process must be reloaded to pick up on-disk `roi.py` / `mcp_server.py` updates.
- **Zero-Server `cortical apply` & Guided Repair Playbooks (`ADR-008`, #30) + Bug #17 Fixed:**
  - Fixed stale default model IDs in `src/cortical/config.py` (`qwen3.8:27b-q4_xxs` -> `qwen3.8:27b-iq2_xxs`) and closed GitHub Issue #17.
  - Added `src/cortical/apply.py` (`cortical-plan/v1` schema validation, `fail_closed` protection on `max_security` vault items, single atomic backup compatible with `cortical sync --rollback <id>`, auto-rollback on write error, OS clipboard reader) wired as `cortical apply` in `src/cortical/cli.py`.
  - Updated `src/cortical/analytics/zero_server_ui.py` with `cortical-plan.json` download & `apply --from-clipboard` copy in the sticky `#dirty-dock`, `Add to Apply Plan` for custom models & harnesses, batch `Plan Repair for All Drift`, OS-aware Guided Install/Link/Repair/Verify playbooks, `Verify & Refresh Snapshot`, and modal/drawer Tab focus trap + `restoreFocus()`.
  - Added `tests/test_apply_and_html_schema.py` and verified both Cold (`docs/settings.html`) and Hydrated (`html/settings.html`) modes in headless Chromium via Playwright (`1440x900`, `1280x800`, `768x1024`: 0 page errors, 0 overflows).
- **Issue #7 Closed — Single Source of Truth Drift Detection & Reconciliation (`src/cortical/reconcile.py`, `cortical reconcile`):**
  - Offloaded initial `reconcile.py` signature/edge-case draft to local `qwen3.5:9b-q3_k_xl` via `cortical_local_offload` (32.21s local run).
  - Extracted `render_litellm_config_yaml()` in `src/cortical/composers/router.py`, implemented `src/cortical/reconcile.py` (`resolve_validated_models`, `detect_router_drift`, `detect_all_drift`, `reconcile_all`), handled both string and dict-shaped `installed_ollama_models`, and wired `cortical reconcile [--apply|--dry-run|--json]` in `src/cortical/cli.py`.
  - Verified with `tests/test_reconcile.py` (`37/37` tests passing) and live `cortical reconcile --dry-run --json`.

---

## Session 2026-11-23 (Evening) — Strata & Inkling-2-Mini Evaluation, `ADR-009`, Cross-Harness Handoff

- **GitHub Issue & ADR Created:** Opened `#31` (`[ADR-009]`) + [docs/adr/ADR-009-strata-runtime-and-inkling2-quant-integration.md](../../docs/adr/ADR-009-strata-runtime-and-inkling2-quant-integration.md) + [docs/LOCAL_AGENT_HANDOFF.md](../../docs/LOCAL_AGENT_HANDOFF.md).
- **Strata CLI & `Inkling-2-Mini-SQ-10` on Apple M2 Pro (16 GB Unified, macOS 27.0.1):**
  - Installed `~/.local/bin/strata` (`0.2.20` / `0.1.66`), downloaded `Inkling-2-Mini-SQ-10.strata` (`10.47 GB`) + `Inkling-2-Mini-Vision.strata` (`0.64 GB`).
  - Diagnosed upstream M1/M2 `MTLCompilerService` crash on `ink_moe_gu_situ` (`#6608`/`#6720`) in prebuilt `0.1.66`; compiled `strata-inkling` from `Niko1221/Strata` `main` (includes `759ccf6c`), staged at `~/.local/bin/strata-inkling-main` with profile `~/.local/share/strata/sq10-m2-local.json`.
  - Measured `SQ-10` (`--context 8192`, `TotalAlloc=10.94 GiB`): cold coding `8.05 tok/s` decode; warm reasoning `86.4 tok/s` prefill / `4.53 tok/s` decode (`97.3%` RAM pressure); `--bench` at auto-clamped `12288` ctx (`11.08 GiB`) dropped to `1.8 tok/s` — confirming `16 GB` M2 Pro needs dual `workSet + OS headroom` bounds and benefits from lighter `UD-IQ2_XXS` (`8.49 GB`) GGUF testing.
- **Anti-Regression Local Handoff (`pi` / `unsloth`):** Documented copy-paste execution prompt, branch-isolation discipline, Serena symbol edits, `unittest` + `reconcile --dry-run` verification gate, and `max_tokens` ceiling in `docs/LOCAL_AGENT_HANDOFF.md`.
- **GGUF vs `.strata` Metal Test (`Inkling-2-Mini-UD-IQ2_XXS.gguf`):** Downloaded verified `8.09 GiB` GGUF (HF LFS SHA-256 `2f953a44...`), but Strata `0.2.20` failed hardcoded size (`-1,280` B drift) and `strata-inkling-main` (`native_gguf=0`) spent `140.3s` transcoding it into a `15.00 GiB` Metal arena (`TotalAlloc=15.80 GiB` @ `ctx=4096`), triggering `kIOGPUCommandBufferCallbackErrorOutOfMemory`. Removed non-viable GGUF (`8.5 GB` reclaimed); `SQ-10.strata` @ `<=8192` ctx is the sole viable Inkling-2-Mini quant on 16 GB Apple Silicon, while `qwen3.5:9b-q3_k_xl` (`5.1 GB`) & `qwen3.8:27b-iq2_xxs` (`7.2 GB`) on Ollama remain best for continuous background loops alongside IDE/browser.

---

## Session 2026-11-23 (Late) — Strata Cleanup, Ollama `Inkling-2-Mini` Verification & Recursive Sanitized Ingestion

- **Strata Cleanup & Ollama `Inkling-2-Mini` Verdict:**
  - Removed `~/.local/share/strata`, `~/.local/state/strata`, `~/.local/bin/strata*` cleanly.
  - Pulled `hf.co/unsloth/Inkling-2-Mini-GGUF:UD-IQ2_XXS` (`8.5 GB` + `641 MB` mmproj) into Ollama `0.40.16`; Ollama failed to load it (`unknown model architecture: 'inkling2_loop'`, HTTP 500), so removed the `9.1 GB` blob via `ollama rm` to keep disk clear.
  - Baseline `qwen3.8:27b-iq2_xxs` (`7.2 GB` in Ollama) measured `9.70 tok/s` decode (`40.13 tok/s` prefill, `load=6.91s`), outperforming earlier Strata `SQ-10` (`8.05 -> 4.53 tok/s`) on 16 GB M2 Pro without swap/OOM pressure; `qwen3.5:9b-q3_k_xl` (`5.1 GB`) + `qwen3.8:27b-iq2_xxs` (`7.2 GB`) remain optimal.
- **Recursive Sanitized Ingestion & Privacy UI/UX Implemented (`39/39` tests passing):**
  - `src/cortical/privacy/sanitizer.py`: folder-consistent `pseudonym_state`, `preserve_pseudonyms`, `entities_by_category`, `metadata_stripped_count`, and OOXML fragment fallback on `ET.ParseError`.
  - `src/cortical/wiki/store.py`: schema migration (`sanitized`, `privacy_profile`, `privacy_namespace`, `policy_sig`, `entities_masked`, `entities_by_cat_json`, `stripped_meta_json`, `summaries_json`, and `pseudonym_vault` HMAC + `.pseudonym.key` counter-mode encryption with zero plaintext PII in `wiki.db`), 4-tier summaries, `.corticalignore`/`.geminiignore`/`.cursorignore`/`.claudeignore`, O(1) Merkle skip keyed on `policy_sig`, `--dry-run`, and `navigate(privacy_filter=...)`.
  - `src/cortical/cli.py`: added `crawl --sanitize --dry-run` (with TTY progress bar & Privacy Audit table), `sanitize --recursive --output-dir`, and `wiki-dashboard`.
  - `src/cortical/analytics/wiki_dashboard.py`, `src/cortical/dashboard_api.py`, `src/cortical/dashboard_ui.py`, `src/cortical/analytics/zero_server_ui.py`, `docs/settings.html`, `docs/index.html`, and `tests/test_sanitized_crawl.py`.


---

## Session 2026-11-23 (Night) — State-of-the-Art Audit, Competitive Wedge, Upstream Hooks & ADR-010..012

- **GitHub Labels Synced:** Added `strategy`, `upstream`, `privacy`, `hardware`, `compression` (28 total labels on `ccancellieri/cortical`).
- **Track 1 Discrepancies Logged (`[Bug]` Issues `#32`–`#35`):**
  - `#32`: `cortical serve-mcp cortical` passes unsupported `--transport`/`--host`/`--port` flags to `cortical.mcp_server` (`stdio`-only `stdin` loop).
  - `#33`: `TOOLS_SCHEMA` exposes `7` tools (`bench --compare` confirms `7`) while docs/benchmark label still say `5`, missing MCP `annotations` & `outputSchema`, and no `server.json`/`glama.json` manifests (leaving Glama on legacy `v0.1.0`).
  - `#34`: Server key drift (`cortical integrate` defaults to `cortical-wiki` pointing at `cortical.mcp_server`, while `cortical sync` pops `cortical-wiki` and writes `cortical-mcp`) + root `opencode.json` schema mismatch.
  - `#35`: Doc/LOC drift (`README.md` / `docs/DESIGN.md` claim `~4.2K` LOC across `6` packages vs actual `16,083` LOC across `7` subpackages + top-level modules, legacy `v0.2` Italian `AGENTS.md`, and `11` of `25` CLI subcommands omitted in `README.md`).
- **Living ADR Sync (`docs/adr/README.md` + `#36`–`#38`):**
  - Created `ADR-010` (`#36`, Composable Control Plane Wedge & Top 5 Capability Roadmap), `ADR-011` (`#37`, MCP 2026 Tool Annotations, Output Schemas, 7-Tool Contract & Registry Standard), and `ADR-012` (`#38`, Upstream Ecosystem Hooks & Contribution Contract); updated `ADR-007` status note (`#7` and `#17` closed).
- **Strategic Backlog Created (`#39`–`#52`):**
  - Top 5 Product Gaps (`[Idea]` `#39`–`#43`), 8 High-Leverage Ecosystem Contributions (`[Upstream]` `#44`–`#51`), and `[Strategy]` Umbrella Issue `#52`.

---

## Session 2026-11-23 (Late Night) — Retire `ADR-009`, Land `ADR-011` / `#39` + `#32`–`#35` & Evolve Cross-Harness Knowledge/Skills

- **Retired `ADR-009` (`#31`):** Deleted `docs/adr/ADR-009-strata-runtime-and-inkling2-quant-integration.md`, updated `docs/adr/README.md`, `ADR-010`, and `docs/LOCAL_AGENT_HANDOFF.md`, and closed GitHub Issue `#31` (`not planned`).
- **Committed Baseline Checkpoints:**
  - `f8dbfff`: `feat(wiki,privacy,cli): recursive sanitized crawl, folder pseudonym vault & wiki-dashboard`
  - `06a6d9b`: `docs(adr): add ADR-010..012 strategic audit & retire ADR-009 strata proposal`
- **Implemented `ADR-011` (`#37`) / `#39` / `#32`–`#35` / `#44` Prep (drafted with `cortical_local_offload` `qwen3.5:9b-q3_k_xl`):**
  - `src/cortical/mcp_server.py`: added 2025/2026 MCP `annotations` (`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`) + JSON `outputSchema` + `structuredContent` across all 7 tools, upgraded `protocolVersion` to `"2025-06-18"`, and implemented stdlib `ThreadingHTTPServer` Streamable HTTP (`--transport streamable-http --host --port`, `GET /health`/`/mcp`, `POST /mcp` single/batch).
  - `src/cortical/wiki/mcp_server.py`: added `annotations`, `outputSchema`, and `structuredContent` across all 5 `WIKI_TOOLS_SCHEMA` tools.
  - `src/cortical/integrations.py`, `src/cortical/cli.py`, `opencode.json`: unified default `cortical integrate` key to `cortical-mcp` (adding `--wiki` for `cortical-wiki`), cleaned stale `"cortical-wiki"` keys pointing to `cortical.mcp_server`, and aligned root `opencode.json`.
  - Root `server.json` & `glama.json`: published `0.3.0` MCP Registry & Glama manifests.
  - Aligned `README.md`, `docs/INTEGRATIONS.md`, `docs/index.html`, `scripts/benchmark.py`, and `src/cortical/analytics/benchmark.py` to 7 core tools + 25 CLI subcommands.
- **Evolved Local Knowledge & Cross-Harness Skills:**
  - Updated `AGENTS.md`, `.agents/skills/learned-cortical-architecture/SKILL.md`, `.agents/skills/cortical-token-saver/SKILL.md`, `.agents/skills/pi-core-tools-mastery/SKILL.md`, and `.pi/extensions/cortical-harness.ts` (`/reconcile`, `/handoff`, safe `try/catch`).
  - Ingested `docs/adr/README.md` (`@private:cortical_adr_index`) and `AGENTS.md` (`@private:cortical_agents_contract`) into Privacy Vault & `LocalBrain`, and saved `cortical_handoff`.
- **Verified:** `40/40` tests PASS (`PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q`), `reconcile --dry-run --json`, and `bench --compare`.

---

## Session 2026-11-23 (Hybrid Orchestrator & `pi` + `cortical-deep` Fix)

- **Root Causes Diagnosed (`#53`):**
  1. `adapters.py` capped non-9B models to `contextWindow: 32768`; once `pi` prompts reached ~30.5K tokens, `pi-ai`'s `CONTEXT_SAFETY_TOKENS=4096` clamped `max_tokens` to `1` (`stopReason: "length"`, `"I"`).
  2. `litellm_config.yaml` and `pi` `models.json` lacked `reasoning_effort: none` (`think=False` in LiteLLM `ollama_chat`), `keep_alive: 30m`, and adaptive >300s timeouts, causing unbounded `<think>` generation and 300s request aborts.
  3. `cortical-global.ts` capped `27b` requests at `num_ctx: 16384`; macOS `vm_stat` low `free_ram_gb` caused `recommend_models_for_hardware` to clip to `4096`.
- **Architecture & ADRs Implemented (`ADR-013` `#54`, `ADR-014` `#55`, `ADR-015` `#56`, EPIC `#57`):**
  - `src/cortical/hardware/{probe,context_window,models}.py`: macOS `memory_pressure_level`, KV-density + Metal/VRAM ceiling math (`65536` for `qwen3.8:27b-iq2_xxs` and `98304` for `qwen3.5:9b-q3_k_xl` on 16 GB Unified), `compute_hardware_context_profile`, and `compute_adaptive_timeout` (`600s` for `cortical-deep`).
  - `src/cortical/config.py`, `apply.py`, `composers/router.py`, `harnesses/adapters.py`: added `ORCHESTRATOR_PRESETS` (local + `gemini`, `anthropic`, `openai`, `deepseek`, `openrouter`, `custom`) using env var names only, `api_key_env` secret rejection in `validate_plan`, LiteLLM `reasoning_effort: none` + `keep_alive: 30m` + fallback routing, and 8-harness orchestrator/worker/rules sync preserving user credentials.
  - `src/cortical/privacy/vault.py`, `mcp_server.py`, `cli.py`: enforced `remote_egress` zero-residual-PII `fail_closed` checks across Channels 1–3 (`cortical_vault_read`, `resources/read`, `export_sanitized_memory_markdown`, `intercept_pre_send`) while preserving local `cortical_local_offload(vault_alias=...)`.
  - `src/cortical/analytics/{snapshot,tuner,zero_server_ui}.py` + regenerated `docs/settings.html` & `html/settings.html`: added Orchestrator Topology UI card (`renderOrchestrationCard`), Metal/KV breakdown, and 8-harness binding matrix (`node --check` exit `0`).
  - `/Users/ccancellieri/.pi/agent/extensions/cortical-global.ts`: aligned `before_provider_request` (`num_ctx=65536` for `cortical-deep`/`27b`, `98304` for `9b`, `max_tokens` floor `4096` for local models).
- **Verified (`tests/test_hybrid_orchestration.py` + Live Dogfooding):**
  - `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q`: `47` tests PASS (`OK`).
  - Live `pi -p --no-session --model router/cortical-deep "Reply with CORTICAL_DEEP_OK only."` returned `CORTICAL_DEEP_OK` (`exit 0`, `244.69s` cold load), and `curl -s http://127.0.0.1:11434/api/ps` confirmed `context_length: 65536` with `size == size_vram == 9,751,316,397` (~9.08 GiB 100% Metal VRAM).

---

## Session 2026-11-24 (Asymmetric Local-First Roadmap Delivery: `#40`–`#43`, `#25`, `#36`, `#38`, `#45`–`#47`, `#51`)

- **Workspace & Memory Governance:** Restored stray manifest edits (`server.json`, `glama.json`), removed scratch comment files, updated `.gitignore` (`.memory/*` + `!.memory/decisions.md`) so `.memory/decisions.md` is version-controlled in git, and promoted `ADR-010` (`#36`) & `ADR-012` (`#38`) to `Accepted`.
- **Group A Issues Closed (`#6`, `#10`, `#11`, `#20`, `#21`, `#22`, `#23`, `#29`, `#30`, `#44`):** Closed 10 previously implemented & verified issues with exact commit/test evidence.
- **Feature 1 (`#40`) — Cryptographic Fail-Closed Egress Audit Ledger (`src/cortical/privacy/vault.py`, `cli.py`, `snapshot.py`, `zero_server_ui.py`):** Added `privacy_audit_ledger` SQLite table chaining SHA-256 hashes over every `vault_ingest`, `vault_read_*` (incl. `blocked_egress=True` on `FailClosedError`), and `intercept_pre_send` event without storing raw PII; added `cortical vault audit [--verify]` CLI and Vault UI verification status card.
- **Feature 2 (`#41`, `#45`, `#46`, `#47`, `#51`) — Native Lifecycle Hook Installers (`src/cortical/harnesses/hooks.py`, `cli.py`):** Implemented idempotent stdlib installer/inspector `cortical hooks <status|install>` shipping cross-platform hooks/plugins for `claude-code` (`cortical_pretool.py`), `pi` (`cortical-intercept.ts`), `opencode` (`cortical-hook.mjs` + `/cortical-private` & `/cortical-local`), `dsh` (`cortical-cordis-hook.mjs`), and `litellm` (`litellm_cortical_guard.py`).
- **Feature 3 (`#42`, `#25`) — Portable Zero-Secret Profile Bundles (`src/cortical/profile.py`, `cli.py`, `zero_server_ui.py`):** Added `cortical-profile/v1` (`cortical profile <export|diff|import>`) scrubbing raw secret patterns (`sk-`, `AIza`, `ghp_`, etc.) and raw/resolved `$HOME` prefixes -> `~`, routing imports safely through `cortical-plan/v1`, plus offline Profile Export & Diff UI in Settings.
- **Feature 4 (`#43`) — Dual Metal/VRAM Working-Set Preflight & Multi-Harness Telemetry (`src/cortical/hardware/context_window.py`, `src/cortical/analytics/roi.py`):** Exposed `gguf_arena_overhead_gb` & `zero_copy_safe` in `compute_hardware_context_profile` and added `collect_multi_harness_local_runs()` with `(mtime_ns, size)` caching aggregating local LLM usage across `claude-code`, `codex`, `opencode`, and `dsh` alongside `pi` and `agent_runs`.
- **Verified (`tests/test_roadmap_features.py`):** `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q` -> **`51/51` OK** (`14.665s`), `bench --compare` (`78.12%` vs pretty / `62.09%` vs compact TOON), `docs/settings.html` & `html/settings.html` `node --check` exit `0`.

---

## Session 2026-11-24 (Morning — Phase 0 `pi` Audit, 1-Click Browser Demo Presets, Metrics Ledger, Upstream Playbook & Verified Launch Kit)

- **Phase 0 (`pi --session 01a20890-2032-7222-9290-a615d597d1d0` Audit):** Verified `3,481,633` local tokens processed (`3,452,912` in + `28,721` out, `$0` cloud cost); confirmed the 4 `cortical-deep` / `27b` timeout & `stopReason=length` errors were resolved by `783449b`; added local harness hygiene guardrail in `AGENTS.md` to prevent manifest schema drift and `.github/` scratch clutter.
- **Phase 1–4 Deliverables Committed:**
  - `docs/METRICS_LEDGER.md`: Ground-truth KPI scorecard (`51/51` tests, `18,224` LOC, `dependencies = []`, `-78.12%` / `-62.09%` TOON, `4.09 ms` MCP handshake, `0` stars / `0` forks / `9` views / `218` clones / `47` closed / `10` open issues) + weekly automated CLI/API cadence.
  - `src/cortical/analytics/zero_server_ui.py` & `docs/settings.html`: Added **3 One-Click Interactive Browser Demo Presets** (Preset A: Tier 1A 4 GB VRAM Hybrid, Preset B: Tier 1B 16 GB Unified 27B @ `65,536` ctx, Preset C: Hybrid Remote Supervisor + `fail_closed` Privacy Vault), verified `node --check` exit `0` and `51/51` tests OK.
  - `README.md`: Added top-of-page **Try in 60 Seconds (Zero Dependencies)** and **10-Second Interactive Browser Demo** callouts with exact verified numbers.
  - `docs/UPSTREAM_PLAYBOOK.md` & `docs/LAUNCH_CONTENT.md`: Prepared 7 value-first upstream PR/issue contribution kits (zero auto-submission) and 3 verified-number LinkedIn launch posts (EN + IT variants) with visual proof specs.
- **LinkedIn Cover Image Rule:** Always attach a freshly generated cover image to every LinkedIn post, keep it out of git (never commit), and delete it once the post is published.

---

## Session 2026-11-24 (Role-Based Model Abstraction, UI English Alignment & Neon QA P0/P1 Fixes)

- **Canonical 10-Role Model Abstraction (`src/cortical/roles.py`):** Introduced `MODEL_ROLES` (`router`, `ner`, `fast_coder`, `daily_coder`, `reviewer`, `summarizer`, `deep_reasoner`, `orchestrator`, `vision`, `embedder`), semantic aliases (`cortical-*`, `@role:<name>`), deterministic fallback chains, `resolve_role_model`, `resolve_all_roles`, and `normalize_role_or_model`. Wired across `config.py`, `mcp_server.py` (`cortical_local_offload(role=...)`), `composers/router.py`, `harnesses/adapters.py` (`_build_shared_rules_md` now uses `@role:` abstractions instead of concrete model tags), `privacy/{vault,sanitizer,brain}.py`, `snapshot.py`, and `zero_server_ui.py` (Reusable Model Role Registry UI).
- **UI Language Alignment (`dashboard.py`, `docs/help.html`, `docs/settings.html`):** Aligned `help.html` and `settings.html` to default consistently to English (`'en'`) with zero mixed Italian strings in English views.
- **Neon QA P0/P1 Fixes:**
  - `privacy/vault.py` & `cli.py`: `sync_from_disk` now falls back to configured `privacy.vision_model` & `resolve_role_model("ner", cfg)` for `vault_inbox` items; `cortical watch` reports `.error.json` counts and details on stderr.
  - `analytics/zero_server_ui.py`: fixed broken `onclick` quoting in `renderServiceDrawer()` via `data-copy`; made 8-Harness Matrix and Vault Context Budget Gauge dynamically recompute from `ST.draftCfg`; added neutral empty-ledger badge (`0 entries`), US phone redaction regex (`+1-555-0199`), partial profile diff cleanup, bottom-right toast positioning, sticky sidebar, and `.main` bottom padding for the sticky dock.
- **Verified:** `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q` -> **`53/53` OK** (`15.786s`), `docs/settings.html` & `html/settings.html` `node --check` exit `0`.

---

## Session 2026-11-24 (Self-Curation `#1`, Bidirectional `MEMORY.md` Sync `#3`, Dashboard Polish & Ephemeral LinkedIn Cover Kit)

- **Implemented `#1` & `#3` (`src/cortical/privacy/curation.py`, `src/cortical/cli.py`, `tests/test_roadmap_features.py`):**
  - `cortical curate` compiles zero-PII verified workflows from `LocalBrain` (`by_skill`) and `handoff.json` into `.agents/skills/cortical-self-curated/SKILL.md` (with optional `--local-llm` refinement via `@role:summarizer`).
  - `cortical memory-sync` performs optional bidirectional zero-PII sync between `LocalBrain` L1/L2 (`by_concept`) and `MEMORY.md` (`<!-- CORTICAL-MEMORY:START/END -->`), excluding `max_security` items.
- **Dashboard UX/UI Polish (`src/cortical/analytics/zero_server_ui.py`):** Added inline Markdown rendering (`fmtInlineMd`) for the Overview ADR table and non-disorienting inline preset summary banners on Overview (zero `SyntaxWarning`, `node --check` exit `0`).
- **Upstream Playbook & Ephemeral LinkedIn Cover Images:** Refined `docs/UPSTREAM_PLAYBOOK.md` with verified Official MCP Registry (`mcp-publisher`) vs `punkpeye/awesome-mcp-servers` paths; generated 3 bespoke 16:9 dark-navy LinkedIn cover images strictly inside the external artifact directory (untracked, never committed, ready to attach & delete after posting).
- **Verified:** `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q` -> **`54/54` OK** (`13.943s`), `cortical bench --compare` (`-78.12%`/`-62.09%` TOON, `4.26 ms` MCP handshake), `18,838` LOC (`dependencies = []`).

---

## Session 2026-11-24 (Evening — P2 UI Micro-Refinements, `file_paths` Local Offload for 3rd-Party Harnesses & Empirical 4-Layer Stack Benchmark)

- **P2 UI Micro-Refinements (`zero_server_ui.py`):** Raised `.toasts` (`bottom: 132px`) above sticky dock, added `white-space: nowrap` on ADR ID column + italic `*...*` rendering in `fmtInlineMd`, and made Vault Channel 2 card dynamically display live `liveBudgetTok`.
- **Structural Local-Offload Fix for 3rd-Party Cloud Harnesses (`mcp_server.py`, `harnesses/adapters.py`):** Upgraded `cortical_local_offload` with `file_paths: list[str]` (reading raw files locally from disk at `$0` cloud tokens while blocking `.cortical_data/` & `Documents/Cortical/vault/`) and updated shared harness rules to mandate local-first file offload before reading >150 LOC files into cloud context.
- **Empirical 4-Layer Benchmark (`scripts/stack_benchmark.py`, `#48`):** Verified `-95.79%` symbol read (`11,020 -> 464` tok), `-51.35%` RTK `git log -n 30` (`1,854 -> 902` tok), `-78.12%`/`-62.09%` TOON (`745`/`430 -> 163` tok), and `-95.80%` cloud input via local `file_paths` offload (`4,352 -> 183` tok in `31.72s`).
- **Verified:** `55/55` `unittest` PASS (`15.246s`), `docs/settings.html` & `html/settings.html` `node --check` exit `0`.

## 2026-11-24 — ADR-016: Unconditional `GO` Release Standard (Zero-LLM Tier 1, 7-Runner Generalization & Safe `--dry-run` Onboarding)
- **Zero-LLM Stdlib Independence (`Tier 1`):** Proven via automated regression tests (`test_zero_runner_privacy_vault_and_toon_operate_100pct_offline`) against unreachable loopback port `:9` that Privacy Vault (`.md`, `.txt`, `.json`, `.docx`, `.xlsx`, `.pptx`, selectable `.pdf` metadata strip + PII/secret/custom-term masking + `fail_closed` remote block + SHA-256 tamper-evident audit ledger) and `TOON` compression run 100% in Python stdlib with zero local LLM runner.
- **7-Runner Multi-Runner Engine (`config.py`, `sanitizer.py`, `adapters.py`, `router.py`, `integrations.py`):** Added `lm_studio` (`:1234/v1`) and `vllm` (`:8000/v1`) alongside `ollama`, `unsloth`, `llama_cpp`, `mlx_lm`, and `openai_compatible` via `resolve_active_runner_endpoint()`, generalized `ocr_image_local` to OpenAI `/v1/chat/completions` `image_url` payloads, and added stack-trace-free offline diagnostics (`zero_llm_stdlib_active: True`).
- **UI, GitHub Pages & Ground-Truth Metrics:** Refreshed `docs/index.html` and `docs/settings.html` (`zero_server_ui.py`) with `⚡ Zero-LLM (Stdlib)` vs `🧠 Requires Local Runner (@role:...)` pills, 4-step `--dry-run` + `--rollback` onboarding, and exact reproducible `wc -l` breakdown (`19,086` total `src/cortical/` LOC = `15,048` Core Python/CLI/Wiki + `4,038` embedded zero-CDN SPA UI; `57/57` tests in `2,678` test LOC).
