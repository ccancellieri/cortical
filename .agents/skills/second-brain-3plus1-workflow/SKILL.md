---
name: second-brain-3plus1-workflow
description: >
  Cortical 3+1 Second Brain rule: always elaborate and persist all 4 tiers (L1 Light,
  L2 Medium, L3 High, +1 Max Raw), and retrieve at the requested depth (light, medium,
  high, max). Includes MCP tools for concept/episode updates.
---

# Second Brain 3+1 Workflow (`second-brain-3plus1-workflow`)

## 1. Dual Invariant: Full 4-Tier Write, Selective Depth Read
- **Write / Elaborate / Record**: Whenever summarizing a task, file, or concept (`wiki_synthesize_discussion_3plus1`, `wiki_upsert_concept`, Merkle crawl), **always** generate and store all 4 tiers (`L1`, `L2`, `L3`, `+1 Max`).
- **Read / Retrieve**: Match the user's selected retrieval depth (`light` -> L1, `medium` -> L2, `high` -> L3, `max` -> +1 Max) via `wiki_search` or `wiki_navigate`.

## 2. Updating Concepts & Graph
- Use `wiki_upsert_concept` to register or update framework/domain concepts and persist 4-tier summaries.
- Use `wiki_record_episode` after verified changes so the Macro-Graph links episodes to touched files and skills.
- Use `wiki_get_egress_audit` to review blocked outbound calls during security audits.
