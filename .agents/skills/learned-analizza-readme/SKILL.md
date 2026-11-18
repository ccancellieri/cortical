---
name: learned-analizza-readme
description: Capability skill su Merkle Context Compression, Zero Token Roi Analytics collegata a /AGENTS.md, /tests/test_cortical_all.py, /README.md.
---

# Capability Skill: Merkle Context Compression, Zero Token Roi Analytics

## Conoscenze, Concetti & Nodi Wiki Collegati
- `concept:merkle-context-compression`
- `concept:zero-token-roi-analytics`
- `concept:local-llm-runner-autoscaler`
- `concept:adaptive-permission-gate`
- `/AGENTS.md`
- `/tests/test_cortical_all.py`
- `/README.md`
- `/docs/USE_CASES_VIBE_CODING.md`
- `/src/cortical/wiki/db.py`

## Regole & Sintesi Generale
Skill: Analisi Documentazione e Audit Architetturale Cortical

Questa competenza automatizza l'analisi di README, documentazione tecnica e audit di sicurezza per il framework Cortical. Integra concetti chiave come la compressione contestuale Merkle, l'ottimizzazione ROI a token zero e scaling adattivo per LLM locali. La procedura include: 1) Navigazione intelligente nella Wiki (AGENTS.md, USE_CASES_VIBE_CODING) tramite MCP; 2) Estrazione di handler critici mantenendo il codice sotto 40 LOC per funzione; 3) Verifica deterministica della coerenza architetturale e esecuzione unit test completa. Applica gate di permessi adattivi e motori vocali dual-path per garantire integrità operativa, riducendo l'errore umano nell'interpretazione di casi d'uso complessi come Vibe Coding.

## Provenienza & Dettagli Precedenti
---
name: learned-analizza-readme
description: Skill appresa dal task pi-89984 (Analizza README). Usa quando affronti compiti simili su analizza, readme.
---

# Skill Appresa: Analizza README

## Contesto & Origine
- **Task Sorgente:** `pi-89984`
- **Obiettivo Originario:** Analizza README

## Lezione Chiave Consolidata
Ho ricevuto la richiesta: 'Analizza README'. Se vuoi che diventi un task operativo, chiedimi 'crea un task per Analizza README'.

## Procedura Riutilizzabile
1. **read (OK)** — # Cortical **Autonomous Agentic Harness for `pi`, 4-Tier Deterministic Merkle/Macro-Graph Second Brain MCP, Adaptive Permission Gate & Dual-Path Voice Engine** **Author:** Carlo Ca

## File & Moduli Coinvolti
- `README.md`

## Verifica
- Controlla la coerenza con la Wiki 3+1 (`wiki_navigate` / `wiki_search`) ed esegui i test in un unico colpo.


### Unificata da `learned-audit-sicurezza-locale`
---
name: learned-audit-sicurezza-locale
description: Skill appresa dal task pi-691502 (Audit sicurezza locale). Usa quando affronti compiti simili su audit, sicurezza, locale.
---

# Skill Appresa: Audit sicurezza locale

## Contesto & Origine
- **Task Sorgente:** `pi-691502`
- **Obiettivo Originario:** Audit sicurezza locale

## Lezione Chiave Consolidata
Pattern verificato: estrarre handler da src/cortical/cli.py sotto 40 LOC per funzione e rieseguire unittest (17/17 OK).

## Procedura Riutilizzabile
1. **read (OK)** — def main(argv=None) exceeds 50 LOC due to inline subcommand branches.
2. **bash (OK)** — Ran 17 tests in 1.10s - OK

## File & Moduli Coinvolti
- `src/cortical/cli.py`

## Verifica
- Esegui: `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests`

### Esperienza Consolidata (`pi-788294`)
- **Obiettivo:** Audit sicurezza locale
- **Lezione:** Pattern verificato: 

### Unificata da `learned-audit-task`
---
name: learned-audit-task
description: Skill appresa dal task pi-590478 (Audit task uno). Usa quando affronti compiti simili su audit, task.
---

# Skill Appresa: Audit task uno

## Contesto & Origine
- **Task Sorgente:** `pi-590478`
- **Obiettivo Originario:** Audit task uno

## Lezione Chiave Consolidata
Sintesi verificata e salvata nei 3+1 livelli.

## Procedura Riutilizzabile
1. **Working Note** — Avvio run run-pi-590478-90482: Audit task uno | Allegati: file:package.json

## Verifica
- Controlla la coerenza con la Wiki 3+1 (`wiki_navigate` / `wiki_search`) ed esegui i test in un unico colpo.


### Unificata da `learned-check-git-issues`
---
name: learned-check-git-issues
description: Skill appresa dal task pi-403488 (1 and check git issues). Usa quando affronti compiti simili su check, git, issues.
---

# Skill Appresa: 1 and check git issues

## Contesto & Origine
- **Task Sorgente:** `pi-403488`
- **Obiettivo Originario:** 1 and check git issues

## Lezione Chiave Consolidata
### Iterazione 1 (DONE) - **Implementer** (1 tool, 9625 tok): The Git status shows a mix of staged renames, modified files, and untracked skill directories. Here's a breakdown of actionable steps: 1. 

## Procedura Riutilizzabile
1. **bash (ERR)** — On branch main Your branch is up to date with 'origin/main'. Changes to be committed: (use "git restore --staged <file>..." to unstage) renamed: .pi/skills/agent-instructions-align
2. **read (OK)** — # AGENTS.md — Regole Architetturali, Standard di Codice & Criteri di Review di Cortical > **Golden Rul

### Unificata da `learned-chrome-search-chrome-mcp`
---
name: learned-chrome-search-chrome-mcp
description: Skill appresa dal task pi-620116 (sa chrome_search o chrome MCP per cercare le posizioni GIS). Usa quando affronti compiti simili su chrome, search, chrome, mcp.
---

# Skill Appresa: sa chrome_search o chrome MCP per cercare le posizioni GIS

## Contesto & Origine
- **Task Sorgente:** `pi-620116`
- **Obiettivo Originario:** sa chrome_search o chrome MCP per cercare le posizioni GIS

## Lezione Chiave Consolidata
**Risultato del task: Cercare posizioni GIS utilizzando chrome_search o chrome MCP** **Sintesi:** Il task mirava a utilizzare gli strumenti `chrome_search` o `chrome MCP` per cercare posizioni GIS. Tu

## Procedura Riutilizzabile
1. **bash (OK)** — SKILL.md
2. **read (OK)** — --- name: chrome-complex-workflows description: > Execute complex multi-step browser workflows in Google Chrome (job applications, social post draftin

### Unificata da `learned-crea-mini-videogioco-tennis`
---
name: learned-crea-mini-videogioco-tennis
description: Skill appresa dal task pi-678582 (Crea un mini videogioco Tennis HTML5 giocabile in examples/vibe_games/tennis/ind). Usa quando affronti compiti simili su crea, mini, videogioco, tennis.
---

# Skill Appresa: Crea un mini videogioco Tennis HTML5 giocabile in examples/vibe_games/

## Contesto & Origine
- **Task Sorgente:** `pi-678582`
- **Obiettivo Originario:** Crea un mini videogioco Tennis HTML5 giocabile in examples/vibe_games/tennis/index.html con racchette, palla, punteggio e tasti W/S e Frecce Su/Giu, poi verifica la sintassi JS.

## Lezione Chiave Consolidata
The file `examples/vibe_games/tennis/index.html` has been successfully written to. Let me know if you need further assistance!

## Procedura Riutilizzabile
1. **write (OK)** — Successfully wrote to `./examples/vibe_games/tennis/index.html`

### Unificata da `learned-crea-task-migliora-prompt`
---
name: learned-crea-task-migliora-prompt
description: Skill appresa dal task pi-913699 (crea un task migliora il prompt carica le skill necessarie ed inizia a lavorarci). Usa quando affronti compiti simili su crea, task, migliora, prompt.
---

# Skill Appresa: crea un task migliora il prompt carica le skill necessarie ed inizia a

## Contesto & Origine
- **Task Sorgente:** `pi-913699`
- **Obiettivo Originario:** crea un task migliora il prompt carica le skill necessarie ed inizia a lavorarci

## Lezione Chiave Consolidata
Mvc

## Procedura Riutilizzabile
1. **bash (OK)** — AGENTS.md LICENSE NOTICE README.md docs examples html opencode.json package.json pyproject.toml scripts src tests
2. **read (OK)** — # AGENTS.md — Regole Architetturali, Standard di Codice & Criteri di Review di Cortical > **Golden Rule del Progetto:** Una contribuzione deve valere più del tempo che serve per re
3. 

### Unificata da `learned-crea-videogioco-breakout-arkanoid`
---
name: learned-crea-videogioco-breakout-arkanoid
description: Skill appresa dal task pi-754199 (Crea un videogioco Breakout (Arkanoid) HTML5 giocabile in examples/vibe_games/br). Usa quando affronti compiti simili su crea, videogioco, breakout, arkanoid.
---

# Skill Appresa: Crea un videogioco Breakout (Arkanoid) HTML5 giocabile in examples/vib

## Contesto & Origine
- **Task Sorgente:** `pi-754199`
- **Obiettivo Originario:** Crea un videogioco Breakout (Arkanoid) HTML5 giocabile in examples/vibe_games/breakout/index.html con mattoncini colorati, racchetta mobile (frecce/mouse), palla, vite, punteggio e pulsante Restart, poi verifica la sintassi.

## Lezione Chiave Consolidata
La directory esiste. Controllo se ci sono file esistenti in breakout e poi creo il gioco Breakout completo.

## Procedura Riutilizzabile
1. **bash (OK)** — total 16 drwxr-xr-x@ 9 ccancellieri staff 288 Nov 17 

### Unificata da `learned-esegui-bash-comando-curl`
---
name: learned-esegui-bash-comando-curl
description: Skill appresa dal task pi-701559 (Esegui con bash il comando curl -sI https://example.com per verificare se la ret). Usa quando affronti compiti simili su esegui, bash, comando, curl.
---

# Skill Appresa: Esegui con bash il comando curl -sI https://example.com per verificare

## Contesto & Origine
- **Task Sorgente:** `pi-701559`
- **Obiettivo Originario:** Esegui con bash il comando curl -sI https://example.com per verificare se la rete esterna è bloccata, poi riporta in italiano cosa è successo.

## Lezione Chiave Consolidata
Task pi-701559 completato (2 passi tool eseguiti). - bash (ERR): [Cortical Hard Guardrail] Blocked by non-bypassable security/focus guardrail. - bash (OK): PING 127.0.0.1 (127.0.0.1): 56 data bytes 64

## Procedura Riutilizzabile
1. **bash (ERR)** — [Cortical Hard Guardrail] Blocked by non-bypassable securit

### Unificata da `learned-esegui-loop-continuo-audit`
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

## Procedura 

### Unificata da `learned-esegui-loop-parallelo-audit`
---
name: learned-esegui-loop-parallelo-audit
description: Skill appresa dal task pi-926383 (Esegui in loop parallelo un audit di src/cortical/ui/js/workspace.js e src/corti). Usa quando affronti compiti simili su esegui, loop, parallelo, audit.
---

# Skill Appresa: Esegui in loop parallelo un audit di src/cortical/ui/js/workspace.js e

## Contesto & Origine
- **Task Sorgente:** `pi-926383`
- **Obiettivo Originario:** Esegui in loop parallelo un audit di src/cortical/ui/js/workspace.js e src/cortical/dashboard.html per migliorare la chiarezza dei report agenti e la gestione chat/task stile Codex/OpenClaw, verifica con node --check e unittest senza mai chiamare host esterni.

## Lezione Chiave Consolidata
### Iterazione 1 (DONE) - **Analyst** (2 tool, 8960 tok): Il codice che hai fornito è un **frontend di un'applicazione di chat avanzata**, molto probabilmente simile a un'intelligenza a

### Unificata da `learned-issue-export-bidirezionale-second`
---
name: learned-issue-export-bidirezionale-second
description: Skill appresa dal task pi-129417 (Issue #3 — Export bidirezionale Second Brain -> MEMORY.md: 1) Usa `grep` e `read). Usa quando affronti compiti simili su issue, export, bidirezionale, second.
---

# Skill Appresa: Issue #3 — Export bidirezionale Second Brain -> MEMORY.md: 1) Usa `gre

## Contesto & Origine
- **Task Sorgente:** `pi-129417`
- **Obiettivo Originario:** Issue #3 — Export bidirezionale Second Brain -> MEMORY.md: 1) Usa `grep` e `read` su src/cortical/wiki/db.py (get_knowledge_graph / export) e src/cortical/wiki/mcp_server.py. 2) Aggiungi un helper `export_memory_markdown(ctx, output_path)` in src/cortical/wiki/db.py (che esporti i concetti L1/L2 e gli episodi in Markdown pulito) e/o un tool MCP `wiki_export_memory_md` in src/cortical/wiki/mcp_server.py. 3) Aggiungi un test unitario in tests/test_cortical_all.py

### Unificata da `learned-issue-export-second-brain`
---
name: learned-issue-export-second-brain
description: Skill appresa dal task pi-546653 (Issue #3 — Export Second Brain -> MEMORY.md: 1) Usa `grep` su src/cortical/wiki/). Usa quando affronti compiti simili su issue, export, second, brain.
---

# Skill Appresa: Issue #3 — Export Second Brain -> MEMORY.md: 1) Usa `grep` su src/cort

## Contesto & Origine
- **Task Sorgente:** `pi-546653`
- **Obiettivo Originario:** Issue #3 — Export Second Brain -> MEMORY.md: 1) Usa `grep` su src/cortical/wiki/db.py per trovare `def get_knowledge_graph`. 2) Leggi le ultime 40 righe di src/cortical/wiki/db.py e aggiungi `export_memory_markdown(self, ctx, output_path)` che esporta concetti L1/L2 ed episodi in Markdown. 3) Esegui `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -k test_25 -v` e riporta il risultato reale. Non contattare host esterni.

## Lezione Chiave Consolidata
### Iterazio

### Unificata da `learned-leggi-pyproject-toml-verifica`
---
name: learned-leggi-pyproject-toml-verifica
description: Skill appresa dal task pi-403488 (Leggi pyproject.toml e verifica la versione corrente del progetto Cortical usand). Usa quando affronti compiti simili su leggi, pyproject, toml, verifica.
---

# Skill Appresa: Leggi pyproject.toml e verifica la versione corrente del progetto Cort

## Contesto & Origine
- **Task Sorgente:** `pi-403488`
- **Obiettivo Originario:** Leggi pyproject.toml e verifica la versione corrente del progetto Cortical usando il tool read.

## Lezione Chiave Consolidata
### Iterazione 1 (DONE) - **Implementer** (1 tool, 4997 tok): Let me read the pyproject.toml file and verify the current version of the Cortical project. - **Reviewer** (8576 tok): Visto: `pyproject.t

## Procedura Riutilizzabile
1. **read (OK)** — [build-system] requires = ["setuptools>=68.0"] build-backend = "setuptools.build_meta" [project] 

### Unificata da `learned-leggi-readme-frase`
---
name: learned-leggi-readme-frase
description: Skill appresa dal task pi-342754 (Leggi README.md in una frase). Usa quando affronti compiti simili su leggi, readme, frase.
---

# Skill Appresa: Leggi README.md in una frase

## Contesto & Origine
- **Task Sorgente:** `pi-342754`
- **Obiettivo Originario:** Leggi README.md in una frase

## Lezione Chiave Consolidata
Task pi-342754 completato (4 passi tool eseguiti). - read (OK): # Cortical **Autonomous Agentic Harness for `pi`, 4-Tier Deterministic Merkle/Macro-Graph Second Brain MCP, Adaptive Permission Gate & D

## Procedura Riutilizzabile
1. **read (OK)** — # Cortical **Autonomous Agentic Harness for `pi`, 4-Tier Deterministic Merkle/Macro-Graph Second Brain MCP, Adaptive Permission Gate & Dual-Path Voice Engine** **Author:** Carlo Ca
2. **submit_report (OK)** — { "subagent_report": { "summary": "Cortical is an autonomous agentic har

### Unificata da `learned-leggi-readme-riassumi-cos`
---
name: learned-leggi-readme-riassumi-cos
description: Skill appresa dal task pi-527621 (Leggi README.md e riassumi cos'e Cortical in una frase). Usa quando affronti compiti simili su leggi, readme, riassumi, cos.
---

# Skill Appresa: Leggi README.md e riassumi cos'e Cortical in una frase

## Contesto & Origine
- **Task Sorgente:** `pi-527621`
- **Obiettivo Originario:** Leggi README.md e riassumi cos'e Cortical in una frase

## Lezione Chiave Consolidata
== CORTICAL HARNESS — ORCHESTRATION INITIATED == === 1. CONTEXTUAL INJECTION & WIKI STATE === No files attached. Use `+ Aggiungi al Contesto` to add files, folders, skills, or plugins. === 2. PROTOCOL

## Procedura Riutilizzabile
1. **read (OK)** — # Cortical **Autonomous Agentic Harness for `pi`, 4-Tier Deterministic Merkle/Macro-Graph Second Brain MCP, Adaptive Permission Gate & Dual-Path Voice Engine** **Author:** Carlo Ca
2. **de

### Unificata da `learned-leggi-src-cortical-context`
---
name: learned-leggi-src-cortical-context
description: Skill appresa dal task pi-500804 (Leggi src/cortical/context_window.py (max 60 righe), aggiungi un commento/docstr). Usa quando affronti compiti simili su leggi, src, cortical, context.
---

# Skill Appresa: Leggi src/cortical/context_window.py (max 60 righe), aggiungi un comme

## Contesto & Origine
- **Task Sorgente:** `pi-500804`
- **Obiettivo Originario:** Leggi src/cortical/context_window.py (max 60 righe), aggiungi un commento/docstring o piccolo helper se utile, oppure verifica con bash .venv/bin/python -c "from cortical.context_window import get_system_memory_snapshot, compute_dynamic_num_ctx; print(get_system_memory_snapshot(), compute_dynamic_num_ctx())" e riporta il risultato esatto.

## Lezione Chiave Consolidata
The file `src/cortical/context_window.py` exists under `$CORTICAL_ROOT/src/cortical/`.

### Unificata da `learned-modificheremo-harness-raccogliere-statistiche`
---
name: learned-modificheremo-harness-raccogliere-statistiche
description: Skill appresa dal task pi-913699 (Modificheremo l'harness per raccogliere statistiche di contesto, token spesi e m). Usa quando affronti compiti simili su modificheremo, harness, raccogliere, statistiche.
---

# Skill Appresa: Modificheremo l'harness per raccogliere statistiche di contesto, token

## Contesto & Origine
- **Task Sorgente:** `pi-913699`
- **Obiettivo Originario:** Modificheremo l'harness per raccogliere statistiche di contesto, token spesi e metriche di sistema (RAM, CPU, VRAM) durante l'esecuzione di ogni task. Aggiungeremo un monitoraggio in tempo reale e un report finale dettagliato. Posso iniziare a implementare questa funzionalità.

## Lezione Chiave Consolidata
The file `CorticalWikiDB.py` was not found in the specified directory or any subdirectories. Please verify the file name and path, o

### Unificata da `learned-ora-usa-browser-cercare`
---
name: learned-ora-usa-browser-cercare
description: Skill appresa dal task pi-620116 (ora usa il browser per cercare le posizioni disponibili presso le fonti e applic). Usa quando affronti compiti simili su ora, usa, browser, cercare.
---

# Skill Appresa: ora usa il browser per cercare le posizioni disponibili presso le font

## Contesto & Origine
- **Task Sorgente:** `pi-620116`
- **Obiettivo Originario:** ora usa il browser per cercare le posizioni disponibili presso le fonti e applica

## Lezione Chiave Consolidata
Non è stato possibile trovare il file `/AGENTS.md` o `/tests/fixtures/api_fixtures.json` nel sistema, poiché il comando `bash` ha restituito un errore indicando che i file non esistono. Pertanto, non 

## Procedura Riutilizzabile
1. **bash (OK)** — File does not exist

## Verifica
- Esegui: `test -f .cortical_data/outbox/application_gis_expert.md && echo 'File exists' |

### Unificata da `learned-porre`
---
name: learned-porre
description: Skill appresa dal task pi-895807 (porre). Usa quando affronti compiti simili su porre.
---

# Skill Appresa: porre

## Contesto & Origine
- **Task Sorgente:** `pi-895807`
- **Obiettivo Originario:** porre

## Lezione Chiave Consolidata
Task pi-895807 completato (2 passi tool eseguiti). - bash (OK): AGENTS.md LICENSE NOTICE README.md docs examples opencode.json package.json pyproject.toml scripts src tests - bash (OK): /Users/ccancel

## Procedura Riutilizzabile
1. **bash (OK)** — AGENTS.md LICENSE NOTICE README.md docs examples opencode.json package.json pyproject.toml scripts src tests
2. **bash (OK)** — ./examples: vibe_games ./src: cortical tests

## Verifica
- Esegui: `ls .`
- 

### Unificata da `learned-procedi`
---
name: learned-procedi
description: Skill appresa dal task pi-546653 (procedi). Usa quando affronti compiti simili su procedi.
---

# Skill Appresa: procedi

## Contesto & Origine
- **Task Sorgente:** `pi-546653`
- **Obiettivo Originario:** procedi

## Lezione Chiave Consolidata
### Iterazione 1 (CONTINUE) - **Analyst** (2 tool, 7473 tok): Mi dispiace per il fallback nella non disponibilità del file allegate nel contesto. Posso procedere a esplorare altri files o directories?

## Procedura Riutilizzabile
1. **read (ERR)** — ENOENT: no such file or directory, access '/attached/chat/README.md'
2. **bash (ERR)** — (no output) Command exited with code 1
3. **read (OK)** — --- name: second-brain-3plus1-workflow description: > Cortical 3+1 Second Brain rule: always elaborate and persist all 4 tiers (L1 Light, L2 Medium, L3 High, +1 Max Raw), and retri
4. **read (OK)** — --- name: autonomous

### Unificata da `learned-procediamo-tasto`
---
name: learned-procediamo-tasto
description: Skill appresa dal task pi-403488 (procediamo su questo tasto). Usa quando affronti compiti simili su procediamo, tasto.
---

# Skill Appresa: procediamo su questo tasto

## Contesto & Origine
- **Task Sorgente:** `pi-403488`
- **Obiettivo Originario:** procediamo su questo tasto

## Lezione Chiave Consolidata
### Iterazione 1 (DONE) - **Implementer** (1 tool, 9304 tok): The "No matches found" result from `grep` suggests the search pattern didn't match any content in the specified files/directory. To troubl

## Procedura Riutilizzabile
1. **grep (OK)** — No matches found
2. **read (OK)** — --- name: pi-core-tools-mastery description: > Use Pi's native coding and discovery tools (grep, find, ls, read, edit, write, bash) and deferred MCP extensions (tool-search, mcp) c
3. **bash (OK)** — total 80 drwxr-xr-x@ 19 ccancellieri staff 608 Nov 11 15

### Unificata da `learned-task-autonomo-unico-orchestrato`
---
name: learned-task-autonomo-unico-orchestrato
description: Skill appresa dal task pi-635802 (Task autonomo unico (orchestrato con qwen3.8:27b-iq2_xs e qwen2.5:1.5b, effort m). Usa quando affronti compiti simili su task, autonomo, unico, orchestrato.
---

# Skill Appresa: Task autonomo unico (orchestrato con qwen3.8:27b-iq2_xs e qwen2.5:1.5b

## Contesto & Origine
- **Task Sorgente:** `pi-635802`
- **Obiettivo Originario:** Task autonomo unico (orchestrato con qwen3.8:27b-iq2_xs e qwen2.5:1.5b, effort medium): 1) Leggi le prime 60 righe di src/cortical/ui/js/workspace.js. 2) Aggiungi in src/cortical/ui/js/workspace.js un helper escAttr (se mancante) o verifica con node --check src/cortical/ui/js/workspace.js che tutti i file JS in src/cortical/ui/js/*.js siano sintatticamente validi. 3) Esegui PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -k test_22 -v per verificare e

### Unificata da `learned-task-notturno-autonomo-coding`
---
name: learned-task-notturno-autonomo-coding
description: Skill appresa dal task pi-406009 (Task Notturno Autonomo (Coding, Chrome & Second Brain 3+1): 1) Verifica con `rea). Usa quando affronti compiti simili su task, notturno, autonomo, coding.
---

# Skill Appresa: Task Notturno Autonomo (Coding, Chrome & Second Brain 3+1): 1) Verific

## Contesto & Origine
- **Task Sorgente:** `pi-406009`
- **Obiettivo Originario:** Task Notturno Autonomo (Coding, Chrome & Second Brain 3+1): 1) Verifica con `read`/`grep` le skill .agents/skills/chrome-complex-workflows/SKILL.md e .agents/skills/research-to-document/SKILL.md e il tool `wiki_create_research_doc` in src/cortical/wiki/mcp_server.py. 2) Esegui con `bash` la suite completa `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v` e verifica `pi mcp list --json`. 3) Produci un documento di sintesi tecnica in docs/research/ usand

### Unificata da `learned-task-seriale-autonomous-testing`
---
name: learned-task-seriale-autonomous-testing
description: Skill appresa dal task pi-766724 (Task Seriale 1 (Autonomous Testing & MCP Self-Improvement): 1) Usa `grep` e `rea). Usa quando affronti compiti simili su task, seriale, autonomous, testing.
---

# Skill Appresa: Task Seriale 1 (Autonomous Testing & MCP Self-Improvement): 1) Usa `gr

## Contesto & Origine
- **Task Sorgente:** `pi-766724`
- **Obiettivo Originario:** Task Seriale 1 (Autonomous Testing & MCP Self-Improvement): 1) Usa `grep` e `read` (max 80 righe) sulla fine di tests/test_cortical_all.py (intorno a test_23) e su src/cortical/wiki/mcp_server.py (wiki_upsert_concept, wiki_get_egress_audit). 2) Aggiungi in tests/test_cortical_all.py un nuovo test `test_24_mcp_concept_upsert_and_egress_audit` che verifichi via CorticalWikiMCPServer.handle_request: (a) `wiki_upsert_concept` con tutti e 4 i livelli (summary_light, sum

### Unificata da `learned-usa-read-leggere-src`
---
name: learned-usa-read-leggere-src
description: Skill appresa dal task pi-346442 (Usa read per leggere src/cortical/context_window.py, poi usa edit per aggiungere). Usa quando affronti compiti simili su usa, read, leggere, src.
---

# Skill Appresa: Usa read per leggere src/cortical/context_window.py, poi usa edit per 

## Contesto & Origine
- **Task Sorgente:** `pi-346442`
- **Obiettivo Originario:** Usa read per leggere src/cortical/context_window.py, poi usa edit per aggiungere la funzione format_context_telemetry(telemetry: dict) -> str alla fine del file (che restituisce f"{used}/{win} tok ({pct}%)"), e verifica con bash eseguendo `.venv/bin/python -c "from cortical.context_window import format_context_telemetry; print(format_context_telemetry({\"used_tokens\":100,\"context_window_tokens\":1000,\"occupancy_pct\":10.0}))"`.

## Lezione Chiave Consolidata
**Risultato del task:** -

### Unificata da `learned-usa-skill-career-campaign`
---
name: learned-usa-skill-career-campaign
description: Skill appresa dal task pi-620116 (Usa la skill career-campaign-unified (leggi .agents/skills/career-campaign-unifi). Usa quando affronti compiti simili su usa, skill, career, campaign.
---

# Skill Appresa: Usa la skill career-campaign-unified (leggi .agents/skills/career-camp

## Contesto & Origine
- **Task Sorgente:** `pi-620116`
- **Obiettivo Originario:** Usa la skill career-campaign-unified (leggi .agents/skills/career-campaign-unified/SKILL.md) per preparare in dettaglio una candidatura completa per la posizione GIS Expert (https://www.recruit4eu.com/job/ref-no-1052026-gis-expert/) adatta al profilo di Carlo Cancellieri (Geospatial / GeoSolutions / FAO / OGC / Python backend, preferenza telework/Europa e organizzazioni internazionali). Scrivi il pacchetto dettagliato di candidatura (fit analysis, risposte alle domande del for

### Unificata da `learned-verifica-parallelo-versione-cortical`
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
3. **bash (ERR)** — (no outpu

### Unificata da `learned-verifica-permessi`
---
name: learned-verifica-permessi
description: Skill appresa dal task pi-100075 (Verifica permessi). Usa quando affronti compiti simili su verifica, permessi.
---

# Skill Appresa: Verifica permessi

## Contesto & Origine
- **Task Sorgente:** `pi-100075`
- **Obiettivo Originario:** Verifica permessi

## Lezione Chiave Consolidata
Carlo, per favore conferma i tuoi permessi.

## Procedura Riutilizzabile
1. **bash (OK)** — ./scripts/setup.sh ./scripts/enable-service.sh ./opencode.json ./AGENTS.md ./.git/config ./.git/objects/0d/7c8042eb8bd62da0ce284d5cd626114ee49ac8 ./.git/objects/59/044968e21c47affe

## Verifica
- Esegui: `ls -l && find . -type f -perm -002 && find . -type d -perm -002 && find . -type f -perm -004 && find . -type d -perm -004 && find . -type f -perm -001 && find . -type d -perm -001`


### Unificata da `learned-vibe-code-gioco-snake`
---
name: learned-vibe-code-gioco-snake
description: Skill appresa dal task pi-629817 (Vibe code un gioco snake). Usa quando affronti compiti simili su vibe, code, gioco, snake.
---

# Skill Appresa: Vibe code un gioco snake

## Contesto & Origine
- **Task Sorgente:** `pi-629817`
- **Obiettivo Originario:** Vibe code un gioco snake

## Lezione Chiave Consolidata
Task pi-629817 completato (1 passi tool eseguiti). - bash (OK): AGENTS.md LICENSE NOTICE README.md docs examples opencode.json package.json pyproject.toml scripts src tests ./docs: USE_CASES_VIBE_CODI

## Procedura Riutilizzabile
1. **bash (OK)** — AGENTS.md LICENSE NOTICE README.md docs examples opencode.json package.json pyproject.toml scripts src tests ./docs: USE_CASES_VIBE_CODING.md ./examples: vibe_games ./examples/vibe

## Verifica
- Esegui: `ls -R`

