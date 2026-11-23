# ADR-004: Unified In-Repo ADR & GitHub Issues Project Memory Sync

- **Status:** Accepted
- **Date:** 2026-11-23
- **GitHub Issue:** #23

## Context & Problem
Architectural decisions, discovered bugs, and UX roadmap ideas are easily lost across sessions or split between local markdown notes and GitHub Issues.

## Decision
1. **Dual-Anchored ADR Convention:** Maintain concise Markdown ADRs in `docs/adr/ADR-NNN-<slug>.md` (indexed in `docs/adr/README.md`) mirrored 1:1 with GitHub Issues titled `[ADR-NNN] <Title>` (`label: adr`).
2. **Dashboard Visibility:** `cortical dashboard` reads `docs/adr/` during static snapshot generation so recent ADRs and project decisions are searchable inside the dashboard's Command Palette (`Cmd/Ctrl + K`) and exportable from the Reports view.

## Alternatives Considered
- **GitHub Issues only:** Offline clones and air-gapped contributors lose architectural rationale.
- **Repo Markdown only:** Loses issue-level traceability, labels, and PR/commit linking.

## Consequences & Trade-offs
- **Pros:** Decisions survive across sessions, contributors, and offline environments; searchable from the static dashboard.
- **Cons:** Requires keeping `docs/adr/README.md` and GitHub ADR issue numbers aligned when adding new ADRs.
