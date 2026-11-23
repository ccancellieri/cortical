# ADR-008: Atomic Dashboard Plan Bundle (`cortical-plan/v1`), `cortical apply` & Guided Service Repair

- **Status:** Accepted
- **Date:** 2026-11-23
- **GitHub Issue:** #30

## Context & Problem
While `ADR-001` enabled zero-server dashboard editing with File System Access API and per-control CLI snippets, users applying coordinated changes (multi-section config updates, custom variable-quant models, privacy policy updates, and multi-harness syncs) still faced multi-command friction and risked partial application if an individual step failed. Additionally, unlinked or drifted harnesses and OSS tools needed concrete, OS-aware repair recipes paired with an immediate verification workflow.

## Decision
1. **Declarative Atomic Plan Schema (`cortical-plan/v1`):** The static dashboard sticky dock (`settings.html`) exports a single self-contained bundle (`cortical-plan.json` download or `--from-clipboard` JSON copy) aggregating `config_patch`, `custom_models`, `vault_updates`, `sync_harnesses`, and optional `regenerate_dashboard`.
2. **Safe Atomic Apply (`src/cortical/apply.py` → `cortical apply`):**
   - Validates schema version, numeric bounds, top-level config keys, harness IDs, and strictly rejects downgrades or `fail_open` overrides on `max_security` (`LOCAL-ONLY`) vault items before touching disk.
   - Supports `--dry-run` and `--from-clipboard` (stdlib subprocess wrappers for `pbpaste`, `wl-paste`, `xclip`/`xsel`, PowerShell `Get-Clipboard` with actionable fallback hints).
   - Creates ONE timestamped backup manifest compatible with `cortical sync --rollback <id>` across all modified files (`cortical.config.json`, harness configs, `vault.db`), and automatically rolls back every file if any write fails.
3. **Guided Service Repair & Verify Playbooks (`src/cortical/analytics/zero_server_ui.py`):** Each harness/OSS tool drawer adapts step-by-step commands to lifecycle state (`Install`, `Link`, `Repair`, `Verify`), adds `Add to Apply Plan`, provides batch `Plan Repair for All Drift`, and includes a 1-click `Verify & Refresh Snapshot` command (`cortical doctor && cortical sync --dry-run && cortical dashboard --out-dir html --open`).

## Alternatives Considered
- **Generating long imperative shell scripts:** Harder to validate safely before execution and impossible to undo atomically via `cortical sync --rollback <id>`.
- **Running a local background daemon to apply changes from the browser:** Violates Cortical's zero-server invariant (`ADR-001`).

## Consequences & Trade-offs
- **Pros:** Zero background servers, Python stdlib-only (`dependencies = []`), single-command reversible handoff from browser to terminal, fail-closed vault protection enforced centrally.
- **Cons:** Clipboard handoff relies on native OS clipboard utilities; where unavailable (e.g., headless containers), users cleanly download `cortical-plan.json` and pass the file path to `cortical apply`.
