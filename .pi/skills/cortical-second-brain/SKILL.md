---
name: cortical-second-brain
description: >
  Navigate, search, fact-check, and update Cortical's 4-Tier Deterministic Merkle Second Brain
  (light, medium, high, max) and High-Level Episode Macro-Graph. Use at the start of any task
  to fetch compact context and at the end of a task to consolidate learned knowledge.
---

# Cortical Second Brain Skill (`cortical-second-brain`)

## 1. Progressive Context Depth Strategy (Token Optimization)
Never load raw files (`max`) upfront when exploring a domain or codebase. Always escalate progressively:
1. **`light` (~50 tokens/node):** Use `wiki_navigate(path="/", depth="light")` first to inspect the subtree map and Macro-Graph links.
2. **`medium` (~250 tokens/node):** Drill into relevant subtrees with `depth="medium"` or `wiki_search(query="...", depth="medium")`.
3. **`high` (~1000 tokens/node):** Request `depth="high"` when designing architecture, comparing APIs, or synthesizing reports.
4. **`max` (Full Raw Source):** Request `depth="max"` ONLY on the exact leaf node where surgical code edits or verbatim quote extractions are needed.

## 2. Mandatory Citation Verification (Fact-Checking Gate)
Before presenting any factual claim derived from the knowledge base:
- Call `wiki_verify_citation(claim_text, source_path, quoted_span)`.
- Only include claims whose verdict is `"verified"` (`entailment >= 0.65` and `span_verified == true`).

## 3. Post-Task Memory Consolidation
At the end of every task:
1. Run `wiki_crawl_delta(root_dir=".")` if any files were created or modified.
2. Call `wiki_record_episode(...)` linking the completed episode (`relates_to`, `modifies`, `derived_from`) to the touched Merkle subtree roots so future agents inherit the lesson immediately.
