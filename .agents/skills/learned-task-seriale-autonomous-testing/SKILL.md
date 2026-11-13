---
name: learned-task-seriale-autonomous-testing
description: Skill appresa dal task pi-766724 (Task Seriale 1 (Autonomous Testing & MCP Self-Improvement): 1) Usa `grep` e `rea). Usa quando affronti compiti simili su task, seriale, autonomous, testing.
---

# Skill Appresa: Task Seriale 1 (Autonomous Testing & MCP Self-Improvement): 1) Usa `gr

## Contesto & Origine
- **Task Sorgente:** `pi-766724`
- **Obiettivo Originario:** Task Seriale 1 (Autonomous Testing & MCP Self-Improvement): 1) Usa `grep` e `read` (max 80 righe) sulla fine di tests/test_cortical_all.py (intorno a test_23) e su src/cortical/wiki/mcp_server.py (wiki_upsert_concept, wiki_get_egress_audit). 2) Aggiungi in tests/test_cortical_all.py un nuovo test `test_24_mcp_concept_upsert_and_egress_audit` che verifichi via CorticalWikiMCPServer.handle_request: (a) `wiki_upsert_concept` con tutti e 4 i livelli (summary_light, summary_medium, summary_high, raw_content) e recupero a depth light/max, (b) `wiki_get_egress_audit` che ritorni count e events. 3) Esegui con `bash`: PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -k test_24 -v e riporta il risultato reale. Non contattare host esterni.

## Lezione Chiave Consolidata
### Iterazione 1 (DONE) - **Analyst** (0 tool, 4808 tok): ### Utilizzo del software Crede di avere la capacità sufficiente per completare la seguente tesi? Se si presenta un problema, avvisi il testat

## Procedura Riutilizzabile
1. **bash (OK)** — 1492 tests/test_cortical_all.py 503 src/cortical/wiki/mcp_server.py 1995 total src/cortical/wiki/: __init__.py __pycache__ crawler.py db.py fact_check.py mcp_server.py tests/: __py
2. **grep (OK)** — test_cortical_all.py:71: def test_1_merkle_crawler_4_tiers_and_delta_skip(self) -> None: test_cortical_all.py:102: def test_2_multi_tenancy_and_relational_rbac(self) -> None: test_
3. **read (OK)** — def test_22_egress_isolation_and_effort_control(self) -> None: """Tests strict outbound egress blocking/logging, _EgressGuardProxy, and low/med/high effort controls.""" import urll
4. **read (ERR)** — ENOENT: no such file or directory, access '/Users/ccancellieri/work/code/cortical/tests/test_cortical_all.py#~!test_23'

## File & Moduli Coinvolti
- `tests/test_cortical_all.py`
- `/Users/ccancellieri/work/code/cortical/tests/test_cortical_all.py#~!test_23`

## Verifica
- Esegui: `wc -l tests/test_cortical_all.py src/cortical/wiki/mcp_server.py 2>/dev/null || echo "files not found at expected paths"; ls tests/ src/cortical/wiki/ 2>/dev/null`
