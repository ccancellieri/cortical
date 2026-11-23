# Cortical Local-Agent Handoff & Anti-Regression Guide (`pi` / `unsloth` / `opencode`)

**Updated:** 2026-11-23 | **Hard Constraints:** Python 3.10+ stdlib ONLY (`dependencies = []` in `pyproject.toml`), Zero-Server by default, Cross-platform (`macOS` / `Linux` / `Windows`).

---

## 1. Current Verified State
- **Tests:** `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q` passes (`37/37` tests before committing; always keep green).
- **Implemented & Closed Issues:** `#7` (`cortical reconcile` SSOT), `#8` (`cortical init` / `.corticalignore`), `#9` (`cortical integrate` IDE setup + live `doctor`), `#12–#16, #19` (opt-in `--serve` wiki & control plane), `#17` (updated stale `qwen3.8:27b-q4_xxs` default -> `qwen3.8:27b-iq2_xxs`), `#24, #26–#28` (zero-server 6-domain dashboard & `cortical apply`).
- **ADRs (`docs/adr/`):** `ADR-001` (`#20`) through `ADR-008` (`#30`) Accepted; `ADR-009` (`#31`) Proposed for `Strata` + `Inkling-2-Mini` integration.
- **Open Backlog (Execute 1 atomic issue at a time on a branch):**
  1. **`#6`** (`feat(local-loop)`): remaining items — Loop #4 OCR/scanner diagnostics + Loop #7 Community `README.md` Quickstart.
  2. **`#31` (`ADR-009`)**: `strata` runner detection in `config.py` / `probe.py` / `models.py` / `router.py`, dual `workSet + RAM` fit check, `max_tokens` guardrail for looped models.
  3. **`#5`**: wire `PiAgentManager` to real `pi --mode json` loop.
  4. **`#1`, `#2`, `#3`, `#4`**: skill self-curation, persistent autonomous loop jobs, optional bidirectional Wiki export, Fase 2 LOC reduction.
  5. **`#18`, `#25`**: UI roadmap ideas (Visual Merkle Diff Graph, Offline Snapshot Diff).

---

## 2. Local Runtimes on This Machine (Apple M2 Pro, 16 GB Unified RAM)
- **Ollama (`:11434`) / LiteLLM Router (`:4000/v1`):**
  - `cortical-fast` -> `qwen3.5:9b-q3_k_xl` (`5.1 GB`, `131K` native ctx) — **best daily workhorse for `pi` / `unsloth` multi-edit loops on 16 GB RAM**.
  - `cortical-deep` -> `qwen3.8:27b-iq2_xxs` (`7.2 GB`, `32K` ctx) — slower deep reasoning.
  - `qwen2.5:1.5b` (`1.0 GB`) / `minicpm-ocr:latest` (`2.0 GB`) — router/NER & vision OCR.
- **Strata Metal Runtime (`:8080/v1`, compiled from `main` `759ccf6c` at `~/.local/bin/strata-inkling-main`):**
  - `Inkling-2-Mini SQ-10` (`10.47 GB` + `0.64 GB` Vision): `~/.local/bin/strata serve --profile ~/.local/share/strata/sq10-m2-local.json` (`8192` ctx, `10.94 GiB` alloc — keep other heavy apps closed to avoid 16 GB memory pressure; **best & only viable `Inkling-2-Mini` quant on 16 GB Apple Silicon**).
  - *Negative finding (`UD-IQ2_XXS` GGUF):* Tested `8.09 GiB` GGUF — `strata-inkling` (`native_gguf=0`) transcodes GGUFs on Metal (`140.3s`) into a `15.00 GiB` arena (`TotalAlloc=15.80 GiB`), immediately OOMing 16 GB Metal (`kIOGPUCommandBufferCallbackErrorOutOfMemory`). Removed GGUF; keep `.strata` `SQ-10` for isolated Strata sessions and `qwen3.5:9b-q3_k_xl` (`5.1 GB`) / `qwen3.8:27b-iq2_xxs` (`7.2 GB`) on Ollama for everyday `pi` / `unsloth` multi-app coding loops.
  - *Note:* Prebuilt `strata-inkling 0.1.66` crashes `MTLCompilerService` on Apple M1/M2 (`#6608`/`#6720`). Use `~/.local/bin/strata-inkling-main` until `0.1.67` releases.

---

## 3. Specialized Anti-Regression Prompt for `pi` / `unsloth`

Copy-paste the prompt below when starting a local agent session (`pi` or `unsloth start ...`), filling in `<ISSUE_NUMBER>`:

```markdown
You are working locally on Cortical (/Users/ccancellieri/work/code/cortical) via local LLM.
Target ONLY GitHub Issue #<ISSUE_NUMBER>.

### NON-NEGOTIABLE GUARDRAILS (NO REGRESSIONS)
1. Branch isolation first:
   - Before editing any file, verify clean baseline tests and create a task branch:
     `git checkout -b feat/issue-<ISSUE_NUMBER>`
   - NEVER work directly on detached history or skip baseline checks.
2. Strict architectural invariants:
   - Python 3.10+ stdlib ONLY (`pyproject.toml` MUST keep `dependencies = []`).
   - Zero persistent background daemons/servers by default.
   - `CorticalMCPServer` default tool count stays lean (`len(tools) == 7` invariant in `tests/test_cortical.py`).
   - Enforce `fail_closed` on `max_security` vault items; NEVER read raw `.cortical_data/` or `~/Documents/Cortical/vault/`.
   - Always run commands & tests with `.venv/bin/python`, never system Python.
3. Context & Edit Discipline (Avoid local-model bloat/hallucination):
   - Use Serena LSP tools (`get_symbols_overview`, `find_symbol`, `replace_symbol_body`) or read ONLY small 50-120 line slices. NEVER rewrite entire large files (`cli.py`, `dashboard.py`, `zero_server_ui.py`).
   - Load `docs/adr/README.md`, relevant `ADR-*.md`, and Issue #<ISSUE_NUMBER> (`gh issue view #<ISSUE_NUMBER>`) BEFORE coding.
   - Scope limit: touch <= 3 source files + 1 test file per iteration. If >3 files need changes, stop and report a mini-plan first.
   - If using `Inkling-2-Mini`, cap `max_tokens <= 1024` per turn and limit reasoning loops.
4. Mandatory Verification Gate (After EVERY Edit Batch):
   Run ALL of:
   - `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q` (100% pass required, 0 skipped/broken)
   - `PYTHONPATH=src .venv/bin/python -m cortical.cli reconcile --dry-run --json`
   - `git diff --stat` (inspect every changed line; revert accidental edits immediately with `git checkout -- <file>`)
5. Stop Conditions:
   - If a test fails twice on the same edit, STOP trying variations: revert the broken file (`git checkout -- <file>`), log exact traceback, and ask the coordinator / cloud model to review.
6. Final Sync:
   - When all checks pass, summarize touched files + test counts, update `.memory/decisions.md`, and leave changes committed cleanly on `feat/issue-<ISSUE_NUMBER>` (do NOT force-push or push to `main` unless asked).
```
