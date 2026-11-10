# AGENTS.md — Regole Architetturali, Standard di Codice & Criteri di Review di Cortical

> **Golden Rule del Progetto:** Una contribuzione deve valere più del tempo che serve per revisionarla.

---

## 1. Principi Guida & Mandato di Revisione (Reviewer Mandate)
- **Mandato del Reviewer:** Non limitarsi a catturare bug ovvi di sintassi. Verificare che il codice sia corretto per questa specifica codebase, a questa scala operativa e per gli obiettivi del business.
- **Falsa Sicurezza:** Mai saltare o sbrigare una review solo perché il codice generato dall'AI "sembra pulito e ben formattato".
- **Zero-Drift:** Questo file definisce contemporaneamente **come l'agente scrive il codice** e **come il reviewer verifica la PR**. Nessuna divergenza tra istruzioni di authoring e criteri di review.
- **Pair Programming:** Favorire sempre il pair programming supervisionato tra sviluppatore e agente.

---

## 2. Metriche di Complessità Obbligatorie per le Funzioni
Ogni funzione aggiunta o modificata deve rispettare le seguenti soglie:
1. **Cyclomatic Complexity < 10:** Massimo 10 percorsi di esecuzione lineare (evitare cascate di `if`/`elif`, loop nidificati e operatori logici sovrapposti).
2. **Cognitive Complexity < 15:** Il codice deve essere immediatamente comprensibile per una mente umana. Nessun trucco sintattico opaco.
3. **Lines of Code (LOC) < 20–50 righe:** Rispettare il *Single Responsibility Principle* (SRP). Se una funzione supera 50 righe, estrarre sotto-funzioni pure e testabili.

---

## 3. Contratti di Pull Request & Vincoli del Diff (Diff Cap)
- **Diff Compatto:** Massimo 150–250 righe di diff effettivo per PR.
- **File Toccati:** Massimo 3–5 file per PR.
- **Nessuna Modifica Non Correlata:** Un solo intento logico per PR. Mai mescolare fix, refactoring estetici e nuove feature.
- **Regola della Decomposizione:** Se una PR supera la soglia ragionevole, forzare la discussione per suddividerla in 2 o 3 PR indipendenti.
- **Titolo PR:** Iniziare sempre con un verbo all'imperativo (es. `feat: add...`, `fix: isolate...`), lunghezza massima 65 caratteri.
- **Linked Issue Assessment:** Verificare esplicitamente che la modifica soddisfi esattamente ciò che il ticket o l'utente ha richiesto, senza generare debito di manutenzione per domini non familiari.

---

## 4. Stack Tecnologico & Vincoli di Sistema
- **Backend:** Python 3.10+, standard library dove possibile, architettura SQLite WAL thread-safe (`CorticalWikiDB`).
- **Sintesi Memoria:** 3+1 Livelli (L1 Light ~50t, L2 Medium ~250t, L3 High ~1000t, +1 Max integrale).
- **Voce & Audio:** Isolamento Half-Duplex acustico (`is_tts_speaking_or_cooling_down`), audio ducking immediato e barge-in con wake-word. I caratteri accentati devono sempre essere formattati in UTF-8 nativo senza escaping numerico (`\u00...`).
- **Test:** Esecuzione single-shot da ambiente virtuale locale `.venv`.
