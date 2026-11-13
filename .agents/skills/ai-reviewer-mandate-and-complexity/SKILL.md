---
name: ai-reviewer-mandate-and-complexity
description: Mandato del revisore di codice AI e metriche di complessità oggettive (Cicli < 10, Complessità Cognitiva < 15, LOC 20-50). Previene debito tecnico, over-generation e falsa sicurezza da codice superficialmente pulito.
---

# Mandato del Revisore di Codice AI & Metriche di Complessità

## 1. Il Nuovo Mandato del Revisore (Reviewer Mandate Shift)
Il ruolo del revisore di codice non è più "catturare bug ovvi di sintassi" (compito già delegato a linter e compilatori).
Il mandato del revisore è oggi:
> **"Verificare che il codice sia corretto per questa specifica codebase, a questa scala operativa, e per le esigenze reali del business."**

### I 4 Rischi Critici dell'AI Coding da Neutralizzare:
1. **Output inconsistente tra membri del team:** stili, astrazioni e librerie divergenti generate da prompt isolati.
2. **Eccessiva dipendenza dall'AI per domini sconosciuti (Over-reliance):** accettare soluzioni AI in aree di cui non si conoscono i vincoli nascosti, edge-case o implicazioni di sicurezza.
3. **Over-generating code & Debito di Manutenzione:** l'AI tende a generare wrapper, boilerplate e complessità non necessaria, espandendo la superficie da mantenere.
4. **Skipping review perché il codice "sembra pulito":** il codice sintetico generato dall'AI ha un'apparenza ordinata, ma può nascondere falle logiche, corruzione di stato o mancata scalabilità.

---

## 2. Metriche Standard di Complessità delle Funzioni

Ogni funzione generata o modificata dall'AI deve rispettare rigorosamente queste tre soglie metriche:

| Metrica | Cosa Misura | Soglia Target | Perché è Cruciale per il Codice AI |
| :--- | :--- | :--- | :--- |
| **Cyclomatic Complexity** | Numero di percorsi di esecuzione lineare (loop, blocchi `if`/`elif`, `match`/`case`, operatori booleani). | **< 10 per funzione** | L'AI tende a nidificare controlli e loop multipli, creando codice quasi impossibile da testare esaustivamente con unit test. |
| **Cognitive Complexity** | Difficoltà di lettura e comprensione da parte della mente umana (penalizza annidamenti profondi e trucchi sintattici compressi). | **< 15 per funzione** | Il codice AI può essere logicamente corretto ma strutturalmente opaco, criptico e fonte di disorientamento per i colleghi. |
| **Lines of Code (LOC)** | Lunghezza effettiva del corpo della singola funzione. | **< 20–50 righe** | Funzioni lunghe violano il *Single Responsibility Principle* (SRP) e rallentano esponenzialmente il tempo di review. |

---

## 3. Checklist Operativa per la Revisione di Codice AI

Prima di approvare o integrare una modifica prodotta da agenti o sviluppatori assistiti:
- [ ] **Verifica Architetturale:** Il codice rispetta le convenzioni condivise e i contratti esistenti?
- [ ] **Controllo Metriche:** Nessuna funzione supera Cyclomatic 10, Cognitive 15, o 50 LOC.
- [ ] **Scomposizione Responsabilità:** Se una funzione fa più di una cosa, estraila in moduli puri o composizioni testabili singolarmente.
- [ ] **Scale & Business Check:** È verificato il comportamento sotto carico, concorrenza e fallimento di rete?
