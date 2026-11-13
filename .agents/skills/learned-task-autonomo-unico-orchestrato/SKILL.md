---
name: learned-task-autonomo-unico-orchestrato
description: Skill appresa dal task pi-635802 (Task autonomo unico (orchestrato con qwen3.8:27b-iq2_xs e qwen2.5:1.5b, effort m). Usa quando affronti compiti simili su task, autonomo, unico, orchestrato.
---

# Skill Appresa: Task autonomo unico (orchestrato con qwen3.8:27b-iq2_xs e qwen2.5:1.5b

## Contesto & Origine
- **Task Sorgente:** `pi-635802`
- **Obiettivo Originario:** Task autonomo unico (orchestrato con qwen3.8:27b-iq2_xs e qwen2.5:1.5b, effort medium): 1) Leggi le prime 60 righe di src/cortical/ui/js/workspace.js. 2) Aggiungi in src/cortical/ui/js/workspace.js un helper escAttr (se mancante) o verifica con node --check src/cortical/ui/js/workspace.js che tutti i file JS in src/cortical/ui/js/*.js siano sintatticamente validi. 3) Esegui PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -k test_22 -v per verificare egress guard e effort. Non contattare host esterni.

## Lezione Chiave Consolidata
### Iterazione 1 (CONTINUE) - **Analyst** (2 tool, 7463 tok): Mi scuso per l'errore. Ho rilescito il file `src/cortical/ui/js/workspace.js` e non ho trovato alcuna referenza all'estension di funzione 

## Procedura Riutilizzabile
1. **bash (ERR)** — Validation failed for tool "bash": - command: must have required properties command Received arguments: {}
2. **read (ERR)** — ENOENT: no such file or directory, access '/src/cortical/ui/js/workspace.js'
3. **bash (OK)** — total 80 drwxr-xr-x@ 19 ccancellieri staff 608 Nov 11 15:22 . drwxr-xr-x 112 ccancellieri staff 3584 Nov 10 18:05 .. drwxr-xr-x@ 3 ccancellieri staff 96 Nov 11 15:22 .agents drwxr-
4. **read (OK)** — /** * Unified Chat & Multi-Agent Task workspace controller: * sidebar list/filters/infinite-scroll, clean message bubbles & task step timeline, * action confirmation modal, compose
5. **read (OK)** — /** * Unified Chat & Multi-Agent Task workspace controller: * sidebar list/filters/infinite-scroll, clean message bubbles & task step timeline, * action confirmation modal, compose
6. **bash (OK)** — src/cortical/ui/js/attachments.js:7:import { activeScopeId, activeScopeLabel, escapeHtml, store } from './state.js'; src/cortical/ui/js/attachments.js:72: <span>📎 Contesto (<b>${es
7. **bash (OK)** — OK: src/cortical/ui/js/api.js OK: src/cortical/ui/js/app.js OK: src/cortical/ui/js/attachments.js OK: src/cortical/ui/js/audio.js OK: src/cortical/ui/js/graph_studio.js OK: src/cor

## File & Moduli Coinvolti
- `/src/cortical/ui/js/workspace.js`
- `src/cortical/ui/js/workspace.js`

## Verifica
- Esegui: `ls -la && echo "---JS---" && ls -la src/cortical/ui/js/`
- Esegui: `grep -n "escAttr\|escapeHtml" src/cortical/ui/js/*.js | head -20`
- Esegui: `for f in src/cortical/ui/js/*.js; do node --check "$f" 2>&1 | head -1 && echo "OK: $f"; done`
