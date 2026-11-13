---
name: research-to-document
description: >
  Synthesize multi-page Chrome or local codebase research into structured Markdown
  documents saved in docs/research/ and indexed across all 4 Second Brain tiers
  (L1, L2, L3, +1 Max) via wiki_create_research_doc.
---

# Research to Document (`research-to-document`)

## 1. Workflow
1. Gather verified facts from Chrome (`chrome_read_active_page` / `take_snapshot`) or local files (`grep` / `read`).
2. Organize findings into:
   - `summary_l1` (1–2 sentence executive takeaway, <=200 chars)
   - `summary_l2` (structured overview, <=600 chars)
   - `sections`: list of `{heading, body}` with concrete evidence, tables, or recommendations
   - `sources`: list of `{title, url, snippet}`
3. Call `wiki_create_research_doc(title=..., slug=..., summary_l1=..., summary_l2=..., sections=..., sources=...)`.
4. Optionally call `wiki_record_episode(...)` to link the research document in the Macro-Graph.

## 2. Quality Rules
- Cite only URLs and facts actually observed during the session.
- Never invent statistics, prices, or quotes.
