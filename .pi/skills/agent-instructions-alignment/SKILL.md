---
name: agent-instructions-alignment
description: Allineamento Zero-Drift tra istruzioni per agenti AI e standard di review. Mantiene file esterni condivisi (AGENTS.md) per standardizzare le norme del team, eliminando prompt ripetitivi e allineando generazione e verifica.
---

# Allineamento Istruzioni Agenti & Standard di Review (Single Artifact Zero-Drift)

## 1. Il Principio del Singolo Artefatto (One Artifact, No Drift)
> **"Le istruzioni date all'agente sono il tuo standard di review."**

Il file che spiega all'AI come scrivere il codice (`AGENTS.md` o le regole di sistema) **deve essere lo stesso identico file** che definisce come il codice viene revisionato dagli umani o dagli agenti di review.
- **Zero Drift:** Se la regola non è scritta nel file di istruzioni condiviso, non puoi contestarla in review.
- **Evoluzione Continua:** Se una review scopre un antipattern ricorrente, aggiorna l'istruzione condivisa immediatamente (`/learn`), così nessun agente lo ripeterà mai più.

---

## 2. File Esterni Condivisi (`AGENTS.md`)
Mantenere file condivisi versionati nella radice del repository standardizza ciò che l'AI "conosce" sulle norme del team attraverso chat session diverse:
- **Nessun Prompt Ripetitivo:** Lo sviluppatore non deve rispiegare ogni volta le preferenze di framework, formattazione, naming e guardrail.
- **Coerenza tra i Membri del Team:** Tutti gli sviluppatori (junior, senior, consulenti esterni) invocano agenti alimentati dallo stesso set di regole condivise.
- **Isolamento e Compattezza:** Regole architetturali scoped caricate solo nei percorsi rilevanti.

---

## 3. Protocollo di Revisione Automatizzata & Umana

1. **Prima della scrittura:** L'agente legge `AGENTS.md` e le skill attive (`cortical-multiagent-orchestrator`, `ai-reviewer-mandate-and-complexity`, `pr-contract-and-diff-constrainer`).
2. **Durante la scrittura:** L'agente applica vincoli di Cyclomatic (< 10), Cognitive (< 15) e LOC (20–50).
3. **Durante la review:** Il reviewer (umano o subagente Reviewer) usa `AGENTS.md` come checklist deterministica di conformità.
4. **Esito:** Se la conformità è totale, il tempo di review scende a pochi minuti, soddisfacendo la **Golden Rule**: il valore della contribuzione supera ampiamente il tempo speso per esaminarla.
