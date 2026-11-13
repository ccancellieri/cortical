---
name: learned-issue-export-second-brain
description: Skill appresa dal task pi-546653 (Issue #3 — Export Second Brain -> MEMORY.md: 1) Usa `grep` su src/cortical/wiki/). Usa quando affronti compiti simili su issue, export, second, brain.
---

# Skill Appresa: Issue #3 — Export Second Brain -> MEMORY.md: 1) Usa `grep` su src/cort

## Contesto & Origine
- **Task Sorgente:** `pi-546653`
- **Obiettivo Originario:** Issue #3 — Export Second Brain -> MEMORY.md: 1) Usa `grep` su src/cortical/wiki/db.py per trovare `def get_knowledge_graph`. 2) Leggi le ultime 40 righe di src/cortical/wiki/db.py e aggiungi `export_memory_markdown(self, ctx, output_path)` che esporta concetti L1/L2 ed episodi in Markdown. 3) Esegui `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -k test_25 -v` e riporta il risultato reale. Non contattare host esterni.

## Lezione Chiave Consolidata
### Iterazione 1 (DONE) - **Analyst** (1 tool, 7719 tok): L'elenco dei files e le directory è attualmente in fase di installazione. Attendi l'isolarizzazione del sistema per aprire questo link. Se sei

## Procedura Riutilizzabile
1. **read (ERR)** — ENOENT: no such file or directory, access '/attached/chat/README.md'
2. **grep (OK)** — db.py:1189: def get_knowledge_graph(
3. **read (OK)** — def get_knowledge_graph( self, ctx: AccessContext, max_nodes: int = 60, ) -> dict[str, Any]: """Builds a Semantic Concept Knowledge Graph with protected configurable Framework Conc
4. **read (OK)** — for cid, cnode in concept_by_slug.items(): if cnode.get("category") == cat and cid != hub_id: edges.append( { "source": nid, "target": cid, "relation": "alimenta",
5. **read (OK)** — "summary": ins["insight_text"], "sources": ["conversazione"], } ) target_cid = next( (cid for cid, cn in concept_by_slug.items() if cn.get("category") == cat and cid != hub_id), hu
6. **read (OK)** — role: str, model: str, provider: str, status: str, goal: str, input_tokens: int = 0, output_tokens: int = 0, total_tokens: int = 0, elapsed_sec: float = 0.0, started_at: Optional[f
7. **bash (OK)** — 1201: def _slugify(text: str) -> str: 1205: def _infer_category(label: str, body: str) -> str: 1544: def upsert_agent_run(
8. **read (OK)** — src = f"{ed['source_type']}:{ed['source_id']}" dst = ( path_to_primary_concept.get(ed["target_id"], hub_id) if ed["target_type"] == "subtree" else f"{ed['target_type']}:{ed['target

## File & Moduli Coinvolti
- `/attached/chat/README.md`
- `src/cortical/wiki/db.py`

## Verifica
- Esegui: `grep -n "def get_knowledge_graph\|def " src/cortical/wiki/db.py | awk -F: '$1 > 1189 && $1 < 1555' | head -5`
