---
name: learned-verifica-parallelo-versione-cortical
description: Skill appresa dal task pi-356466 (Verifica in parallelo la versione di cortical in pyproject.toml e i moduli in sr). Usa quando affronti compiti simili su verifica, parallelo, versione, cortical.
---

# Skill Appresa: Verifica in parallelo la versione di cortical in pyproject.toml e i mo

## Contesto & Origine
- **Task Sorgente:** `pi-356466`
- **Obiettivo Originario:** Verifica in parallelo la versione di cortical in pyproject.toml e i moduli in src/cortical/ui/js, poi riassumi in italiano.

## Lezione Chiave Consolidata
### Iterazione 1 (STOPPED) - **Implementer** (4 tool, 15877 tok): - **Analyst** (4 tool, 14354 tok):

## Procedura Riutilizzabile
1. **bash (ERR)** — /bin/bash: poetry: command not found Command exited with code 127
2. **bash (ERR)** — (no output) Command exited with code 1
3. **bash (ERR)** — (no output) Command exited with code 1
4. **bash (ERR)** — /bin/bash: poetry: command not found Command exited with code 127
5. **bash (ERR)** — grep: src/cortical/ui/js/: Is a directory Command exited with code 2
6. **bash (OK)** — api.js app.js attachments.js audio.js graph_studio.js state.js workspace.js
7. **bash (ERR)** — grep: ./: Is a directory Command exited with code 2
8. **bash (OK)** — AGENTS.md LICENSE NOTICE README.md opencode.json package.json pyproject.toml scripts src tests ./scripts: enable-service.sh setup.sh ./src: cortical cortical_agent.egg-info ./src/c

## Verifica
- Esegui: `ls -R src/cortical/ui/js/`
- Esegui: `ls -R`
