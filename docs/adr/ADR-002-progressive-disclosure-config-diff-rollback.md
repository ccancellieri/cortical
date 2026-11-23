# ADR-002: Progressive Disclosure & Safe Config Diff/Rollback UX

- **Status:** Accepted
- **Date:** 2026-11-23
- **GitHub Issue:** #21

## Context & Problem
Flat configuration dumps overwhelm developers and increase the risk of breaking active agent harnesses (`antigravity`, `pi`, `opencode`, `openclaw`, `codex`, `claude-code`, `dsh`, `unsloth-studio`) or silently clipping Ollama context windows (`4096` default) and exceeding the `<= 15% num_ctx` sanitized memory budget.

## Decision
1. **6-Domain Spatial Navigation + 5-Tab Settings Composer:** Separate operational concerns into 6 domains (*Overview & Quick Setup*, *Services & Harnesses*, *Models & Hardware Tuner*, *Memory & Privacy Vault*, *Settings & Config Composer*, *Usage, ROI & Reports*) and group declarative settings into 5 progressive tabs (*General & Workspace*, *Harnesses & Routing*, *Privacy & Context Budgets*, *Compression & TOON*, *Advanced / Raw JSON*).
2. **Transactional Dirty-State Dock & Inline Validation:** Keep an isolated draft state (`DRAFT_CFG`) diffed against `SAVED_CFG`. Validate paths, numeric context/budget bounds, and thresholds inline. Display a sticky bottom **"Unsaved Changes"** dock offering `Discard`, `View Diff`, `Copy CLI Apply Script`, and `Save to Linked Folder`.
3. **First-Class Dry-Run & Rollback Recipes:** Surface timestamped backup IDs from `cortical sync` and generate `cortical sync --dry-run` and `cortical sync --rollback <id>` commands directly in the Harness Inspector drawer.

## Alternatives Considered
- **Auto-writing config on every input change:** Unsafe for multi-harness setups and impossible to preview diffs before applying.

## Consequences & Trade-offs
- **Pros:** High trust, transparent config diffs, zero accidental overwrites, clear operational impact hints on every control.
- **Cons:** Requires an explicit apply step (via CLI script or Linked Folder write), which is desirable for infrastructure safety.
