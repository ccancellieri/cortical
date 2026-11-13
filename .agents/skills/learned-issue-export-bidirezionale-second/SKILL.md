---
name: learned-issue-export-bidirezionale-second
description: Skill appresa dal task pi-129417 (Issue #3 — Export bidirezionale Second Brain -> MEMORY.md: 1) Usa `grep` e `read). Usa quando affronti compiti simili su issue, export, bidirezionale, second.
---

# Skill Appresa: Issue #3 — Export bidirezionale Second Brain -> MEMORY.md: 1) Usa `gre

## Contesto & Origine
- **Task Sorgente:** `pi-129417`
- **Obiettivo Originario:** Issue #3 — Export bidirezionale Second Brain -> MEMORY.md: 1) Usa `grep` e `read` su src/cortical/wiki/db.py (get_knowledge_graph / export) e src/cortical/wiki/mcp_server.py. 2) Aggiungi un helper `export_memory_markdown(ctx, output_path)` in src/cortical/wiki/db.py (che esporti i concetti L1/L2 e gli episodi in Markdown pulito) e/o un tool MCP `wiki_export_memory_md` in src/cortical/wiki/mcp_server.py. 3) Aggiungi un test unitario in tests/test_cortical_all.py ed esegui `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v`. Non contattare host esterni.

## Lezione Chiave Consolidata
### Iterazione 1 (DONE) - **Analyst** (1 tool, 8000 tok): Hai provato a controllare se `export_memory_markdown` è nella fine del file .py? Se si trova là, potrebbe servirsi di un secondo passo e poi v

## Procedura Riutilizzabile
1. **read (ERR)** — ENOENT: no such file or directory, access '/src/cortical/wiki/db.py#946'

## File & Moduli Coinvolti
- `/src/cortical/wiki/db.py#946`

## Verifica
- Controlla la coerenza con la Wiki 3+1 (`wiki_navigate` / `wiki_search`) ed esegui i test in un unico colpo.
