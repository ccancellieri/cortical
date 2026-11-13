---
name: learned-esegui-loop-continuo-audit
description: Skill appresa dal task pi-372901 (Esegui un loop continuo di audit e miglioramento di src/cortical/ui/js/workspace). Usa quando affronti compiti simili su esegui, loop, continuo, audit.
---

# Skill Appresa: Esegui un loop continuo di audit e miglioramento di src/cortical/ui/js

## Contesto & Origine
- **Task Sorgente:** `pi-372901`
- **Obiettivo Originario:** Esegui un loop continuo di audit e miglioramento di src/cortical/ui/js/workspace.js e src/cortical/dashboard.html (report agenti e gestione chat/task stile Codex), verificando con node --check e unittest senza chiamare host esterni.

## Lezione Chiave Consolidata
### Iterazione 1 (CONTINUE) - **Analyst** (1 tool, 7232 tok): Prego, l'obiettivo è di seguire i requisiti della procedura. Ecco le informazioni che mi sono state fornite: - Archiviazione per il proget

## Procedura Riutilizzabile
1. **read (ERR)** — ENOENT: no such file or directory, access '/attached/chat/README.md'
2. **bash (ERR)** — /Users/ccancellieri/work/code/cortical/src/cortical/ui/js/: total 240 drwxr-xr-x@ 9 ccancellieri staff 288 Nov 11 19:19 . drwxr-xr-x@ 4 ccancellieri staff 128 Nov 11 19:16 .. -rw-r
3. **bash (OK)** — find: /Users/ccancellieri/work/code/cortial: No such file or directory ls: /Users/ccancellieri/work/code/cortial/src/cortial/ui/: No such file or directory
4. **read (OK)** — <!DOCTYPE html> <html lang="it"> <head> <meta charset="utf-8" /> <meta name="viewport" content="width=device-width, initial-scale=1" /> <title>Cortical Mission Control — Second Bra
5. **read (OK)** — /** * Unified Chat & Multi-Agent Task workspace controller: * sidebar list/filters/infinite-scroll, clean message bubbles & task step timeline, * action confirmation modal, compose
6. **bash (OK)** — src/cortical/ui/: total 0 drwxr-xr-x@ 4 ccancellieri staff 128 Nov 11 19:16 . drwxr-xr-x@ 15 ccancellieri staff 480 Nov 11 19:16 .. drwxr-xr-x@ 9 ccancellieri staff 288 Nov 11 19:1
7. **bash (OK)** — total 240 drwxr-xr-x@ 9 ccancellieri staff 288 Nov 11 19:19 . drwxr-xr-x@ 4 ccancellieri staff 128 Nov 11 19:16 .. -rw-r--r--@ 1 ccancellieri staff 788 Nov 11 19:16 api.js -rw-r--r
8. **read (OK)** — /** * Unified Chat & Multi-Agent Task workspace controller: * sidebar list/filters/infinite-scroll, clean message bubbles & task step timeline, * action confirmation modal, compose

## File & Moduli Coinvolti
- `/attached/chat/README.md`
- `/Users/ccancellieri/work/code/cortical/src/cortical/dashboard.html`
- `/Users/ccancellieri/work/code/cortical/src/cortical/ui/js/workspace.js`

## Verifica
- Esegui: `find /Users/ccancellieri/work/code/cortial -maxdepth 4 -name dashboard.html 2>&1 | head; ls -la /Users/ccancellieri/work/code/cortial/src/cortial/ui/ 2>&1 | head -30`
- Esegui: `cd /Users/ccancellieri/work/code/cortical && ls -la src/cortical/ui/ src/cortial/ 2>/dev/null; echo '---'; find src/cortical -name '*.test.*' -o -name '*.js' | head -40`
- Esegui: `ls -la /Users/ccancellieri/work/code/cortical/src/cortical/ui/js/ | head -20 && echo '---' && wc -l /Users/ccancellieri/work/code/cortical/src/cortical/ui/js/*.js`
