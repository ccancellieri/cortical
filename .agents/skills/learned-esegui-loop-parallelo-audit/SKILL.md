---
name: learned-esegui-loop-parallelo-audit
description: Skill appresa dal task pi-926383 (Esegui in loop parallelo un audit di src/cortical/ui/js/workspace.js e src/corti). Usa quando affronti compiti simili su esegui, loop, parallelo, audit.
---

# Skill Appresa: Esegui in loop parallelo un audit di src/cortical/ui/js/workspace.js e

## Contesto & Origine
- **Task Sorgente:** `pi-926383`
- **Obiettivo Originario:** Esegui in loop parallelo un audit di src/cortical/ui/js/workspace.js e src/cortical/dashboard.html per migliorare la chiarezza dei report agenti e la gestione chat/task stile Codex/OpenClaw, verifica con node --check e unittest senza mai chiamare host esterni.

## Lezione Chiave Consolidata
### Iterazione 1 (DONE) - **Analyst** (2 tool, 8960 tok): Il codice che hai fornito è un **frontend di un'applicazione di chat avanzata**, molto probabilmente simile a un'intelligenza artificiale o a 

## Procedura Riutilizzabile
1. **read (OK)** — <!DOCTYPE html> <html lang="it"> <head> <meta charset="utf-8" /> <meta name="viewport" content="width=device-width, initial-scale=1" /> <title>Cortical Mission Control — Second Bra
2. **read (OK)** — /** * Unified Chat & Multi-Agent Task workspace controller: * sidebar list/filters/infinite-scroll, clean message bubbles & task step timeline, * action confirmation modal, compose
3. **bash (OK)** — src/cortical/ui/js/workspace.js src/cortical/ui/js/audio.js src/cortical/ui/js/graph_studio.js src/cortical/ui/js/attachments.js src/cortical/ui/js/app.js
4. **read (OK)** — /** * Unified Chat & Multi-Agent Task workspace controller: * sidebar list/filters/infinite-scroll, clean message bubbles & task step timeline, * action confirmation modal, compose

## File & Moduli Coinvolti
- `/Users/ccancellieri/work/code/cortical/src/cortical/dashboard.html`
- `/Users/ccancellieri/work/code/cortical/src/cortical/ui/js/workspace.js`
- `src/cortical/ui/js/workspace.js`

## Verifica
- Esegui: `find src/cortical -name "*.js" -o -name "*.html" | xargs grep -l "import" | grep -v "node_modules"`
