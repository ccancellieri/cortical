---
name: learned-task-notturno-autonomo-coding
description: Skill appresa dal task pi-406009 (Task Notturno Autonomo (Coding, Chrome & Second Brain 3+1): 1) Verifica con `rea). Usa quando affronti compiti simili su task, notturno, autonomo, coding.
---

# Skill Appresa: Task Notturno Autonomo (Coding, Chrome & Second Brain 3+1): 1) Verific

## Contesto & Origine
- **Task Sorgente:** `pi-406009`
- **Obiettivo Originario:** Task Notturno Autonomo (Coding, Chrome & Second Brain 3+1): 1) Verifica con `read`/`grep` le skill .agents/skills/chrome-complex-workflows/SKILL.md e .agents/skills/research-to-document/SKILL.md e il tool `wiki_create_research_doc` in src/cortical/wiki/mcp_server.py. 2) Esegui con `bash` la suite completa `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v` e verifica `pi mcp list --json`. 3) Produci un documento di sintesi tecnica in docs/research/ usando `wiki_create_research_doc` (o `write`) che riepiloghi lo stato di Cortical pronto per coding, Chrome e Second Brain a 4 livelli. Non contattare host esterni.

## Lezione Chiave Consolidata
### Iterazione 1 (CONTINUE) - **Analyst** (0 tool, 4277 tok): ```json {"name": "ls", "arguments": {"path": "/Users/ccancellieri/work/code/cortical"}} ``` ```json {"name": "read", "arguments": {"path":

## Procedura Riutilizzabile
1. **read (ERR)** — ENOENT: no such file or directory, access '/Users/ccannels/work/code/cortical/.agents/skills/chrome-complex-workflows/SKILL.md'
2. **read (OK)** — --- name: chrome-complex-workflows description: > Execute complex multi-step browser workflows in Google Chrome (job applications, social post drafting, multi-tab research, form fi
3. **read (ERR)** — ENOENT: no such file or directory, access '/Users/cc/ancel/ieri/work/code/cortical/.agents/skills/chrome-complex-workflows/SKILL.md'
4. **read (ERR)** — ENOENT: no such file or directory, access '/Users/cc/ancel/ieri/work/code/cortical/.Agents/SKills/chrome-complex-workflows/SKILL.md'
5. **grep (ERR)** — Validation failed for tool "grep": - pattern: missing - context: expected number, got string Received arguments: { "what": "wiki_create_research_doc", "context": "Second Brain 3+1 
6. **grep (OK)** — cortical/wiki/mcp_server.py-258- }, cortical/wiki/mcp_server.py-259- { cortical/wiki/mcp_server.py:260: "name": "wiki_create_research_doc", cortical/wiki/mcp_server.py-261- "descri
7. **read (OK)** — """Standard Model Context Protocol (MCP) Server for Cortical Second Brain (`cortical-wiki-mcp`). Implements JSON-RPC 2.0 over stdio so `pi` (via `.pi/agent/mcp.json`) or any MCP ho
8. **read (ERR)** — Validation failed for tool "read": - path: missing Received arguments: { "function": "read", "arguments": { "limit": 300, "path": "src/cortical/wiki/mcp_server.py" } }

## File & Moduli Coinvolti
- `/Users/ccannels/work/code/cortical/.agents/skills/chrome-complex-workflows/SKILL.md`
- `/Users/ccancellieri/work/code/cortical/.agents/skills/chrome-complex-workflows/SKILL.md`
- `/Users/cc/ancel/ieri/work/code/cortical/.agents/skills/chrome-complex-workflows/SKILL.md`
- `/Users/cc/ancel/ieri/work/code/cortical/.Agents/SKills/chrome-complex-workflows/SKILL.md`
- `/Users/ccancellieri/work/code/cortical/src`
- `/Users/ccancellieri/work/code/cortical/src/cortical/wiki/mcp_server.py`

## Verifica
- Controlla la coerenza con la Wiki 3+1 (`wiki_navigate` / `wiki_search`) ed esegui i test in un unico colpo.
