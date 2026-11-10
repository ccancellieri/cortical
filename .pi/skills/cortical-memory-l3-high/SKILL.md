---
name: cortical-memory-l3-high
description: Sintesi Memoria Livello 3+1 (HIGH ~1000 token + MAX verbatim) tramite MCP Wiki. Usa per debugging profondo, verifica citazioni NLI e lezioni tecniche complete.
---

# Cortical Memory L3 (+1 Max) — Deep Technical Synthesis (~1000 token)

## Quando usarla
- Quando serve il dettaglio implementativo completo, la root-cause di un bug o la verifica esatta del codice (`depth='high'` o `depth='max'`).

## Procedura Operativa (Tramite MCP `cortical-wiki`)
1. Invoca `wiki_navigate(path='<file>', depth='high')` (o `depth='max'` per il sorgente integrale senza tagli lossy).
2. Verifica sempre i claim critici con `wiki_verify_citation` prima di modificare contratti core.
3. A fine task, consolida i 3+1 livelli con `wiki_record_episode` e valuta se estrarre una nuova Skill procedurale.
