# ADR-006: Dirty-State Settings Validation, Embedding Compatibility Guardrail & Async Crawl Progress

- **Status:** Accepted (Applies to Opt-In `--serve` Control Plane & Shared UX Standards)
- **Date:** 2026-11-23
- **GitHub Issue:** #11 (renumbered from duplicate ADR-002)

## Context & Problem
Editing paths, numeric bounds, embedding models, or launching large directory crawls without guardrails causes silent config corruption, incompatible vector indices, or frozen UIs.

## Decision
1. **Transactional Dirty-State Settings:** Hold an isolated draft clone validated inline (filesystem paths, URLs, numeric bounds) with a sticky bottom **Unsaved Changes** bar (`Discard` / `Save & Apply`) and confirmation-protected section resets.
2. **Blocking Embedding Compatibility Guardrail:** Detect vector dimension or tokenizer family changes (`HTTP 409 embedding_incompatible`) and require explicit user acknowledgement with a one-click `Save & Trigger Full Re-index` workflow.
3. **Background `CrawlJobManager`:** Run `wiki_crawl_delta` / full re-index in a daemon worker thread with live progress counters and log tails queried via `/api/crawl/status`.

## Consequences & Trade-offs
- **Pros:** Eliminates silent vector/index corruption and keeps the UI responsive during large crawls.
- **Cons:** In-memory job logs reset on server restart (persistent Merkle hashes and timestamps remain in SQLite).
