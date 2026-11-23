# Cortical Local-Agent Handoff & Anti-Regression Guide (`pi` / `unsloth` / `opencode`)

**Updated:** 2026-11-23 | **Hard Constraints:** Python 3.10+ stdlib ONLY (`dependencies = []` in `pyproject.toml`), Zero-Server by default, Cross-platform (`macOS` / `Linux` / `Windows`).

---

## 1. Current Verified State
- **Tests:** `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q` passes (`39/39` tests before committing; always keep green).
- **Implemented & Closed Issues:** `#7` (`cortical reconcile` SSOT), `#8` (`cortical init` / `.corticalignore`), `#9` (`cortical integrate` IDE setup + live `doctor`), `#12–#16, #19` (opt-in `--serve` wiki & control plane), `#17` (updated stale `qwen3.8:27b-q4_xxs` default -> `qwen3.8:27b-iq2_xxs`), `#24, #26–#28` (zero-server 6-domain dashboard & `cortical apply`), `#31` (`ADR-009` Strata retired after M2 16 GB OOM verdict).
- **ADRs (`docs/adr/`):** `ADR-001` (`#20`) through `ADR-008` (`#30`) Accepted; `ADR-010` (`#36`), `ADR-011` (`#37`), `ADR-012` (`#38`) Proposed.
- **Prioritized Open Backlog (Execute 1 atomic issue at a time on a branch):**
  1. **`#39` (`ADR-011`) + Bugs `#32`–`#35`**: MCP 2026 `annotations` & `outputSchema`, `serve-mcp cortical` Streamable HTTP, `cortical-mcp` naming sync, `README.md`/`AGENTS.md` alignment, `server.json`/`glama.json` (`#44`).
  2. **`#40`–`#43` (`ADR-010`)**: Cryptographic `fail_closed` audit ledger (`#40`), native harness hooks (`#41`), portable profiles (`#42`), dual Metal/VRAM working-set preflight & unified telemetry (`#43`).
  3. **`#44`–`#51` (`ADR-012`)**: Wave 1–3 Upstream Ecosystem Hooks (`#52` umbrella).
  4. **`#6` & `#5`**: remaining Loop #4/#7 items + `PiAgentManager` real `pi --mode json` loop.
  5. **`#1`, `#2`, `#3`, `#4`, `#18`, `#25`**: skill self-curation, persistent autonomous loop jobs, optional bidirectional Wiki export, Fase 2 LOC reduction, dashboard ideas.

---

## 2. Local Runtimes on This Machine (Apple M2 Pro, 16 GB Unified RAM)
- **Ollama (`:11434`) / LiteLLM Router (`:4000/v1`):**
  - `cortical-fast` -> `qwen3.5:9b-q3_k_xl` (`5.1 GB`, `131K` native ctx, `25.0 tok/s`) — **best daily workhorse for `pi` / `unsloth` / `opencode` multi-edit loops on 16 GB RAM**.
  - `cortical-deep` -> `qwen3.8:27b-iq2_xxs` (`7.2 GB`, `32K` ctx, `9.70 tok/s`) — deep reasoning & architectural review without swap/OOM pressure.
  - `qwen2.5:1.5b` (`1.0 GB`) / `minicpm-ocr:latest` (`2.0 GB`) — router/NER & vision OCR.

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
   - Keep `max_tokens` bounded for quick local edits and verify every edit via `unittest`.
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
