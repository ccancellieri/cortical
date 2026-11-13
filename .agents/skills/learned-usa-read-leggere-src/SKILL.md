---
name: learned-usa-read-leggere-src
description: Skill appresa dal task pi-346442 (Usa read per leggere src/cortical/context_window.py, poi usa edit per aggiungere). Usa quando affronti compiti simili su usa, read, leggere, src.
---

# Skill Appresa: Usa read per leggere src/cortical/context_window.py, poi usa edit per 

## Contesto & Origine
- **Task Sorgente:** `pi-346442`
- **Obiettivo Originario:** Usa read per leggere src/cortical/context_window.py, poi usa edit per aggiungere la funzione format_context_telemetry(telemetry: dict) -> str alla fine del file (che restituisce f"{used}/{win} tok ({pct}%)"), e verifica con bash eseguendo `.venv/bin/python -c "from cortical.context_window import format_context_telemetry; print(format_context_telemetry({\"used_tokens\":100,\"context_window_tokens\":1000,\"occupancy_pct\":10.0}))"`.

## Lezione Chiave Consolidata
**Risultato del task:** - **Lettura del file:** `src/cortical/context_window.py` è stato letto correttamente. - **Modifica del file:** La funzione `format_context_telemetry(telemetry: dict) -> str` è 

## Procedura Riutilizzabile
1. **read (OK)** — """Context window budgeting, multi-message chunking, and LLM paragraph summarization. Prevents brutal character truncation by splitting long context along paragraph boundaries, opt

## File & Moduli Coinvolti
- `src/cortical/context_window.py`

## Verifica
- Controlla la coerenza con la Wiki 3+1 (`wiki_navigate` / `wiki_search`) ed esegui i test in un unico colpo.
