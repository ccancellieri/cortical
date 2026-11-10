---
name: cortical-multiagent-orchestrator
description: Orchestratore Multi-Agente locale per pi e Cortical. Coordina Analyst, Implementer e Reviewer solo quando l'utente apre un task esplicito, salvando la discussione nei 3+1 livelli della Wiki e generando nuove skill.
---

# Cortical Multi-Agent Orchestrator

## Regole Fondamentali (Lezioni da `mcp-skill-hub` + Karpathy Guidelines)
1. **Zero Task Automatici:** Non aprire un task per domande conversazionali o rapide. Apri un task solo su richiesta esplicita (`/task <obiettivo>` o `'crea un task...'`).
2. **Niente Tagli Lossy:** Usa i livelli `light` -> `medium` -> `high` -> `max` della Wiki MCP invece di troncare i file a metà.
3. **Flusso Multi-Agente in 3 Fasi:**
   - **Fase 1 (`arch_analyst`):** Legge la Wiki MCP a livello `light`/`medium` e identifica i file esatti.
   - **Fase 2 (`code_implementer`):** Legge i file target a livello `high`/`max` ed esegue modifiche chirurgiche.
   - **Fase 3 (`reviewer`):** Esegue i test in single-shot, salva la sintesi a 3+1 livelli della discussione e valuta se creare una nuova Skill per il futuro.
