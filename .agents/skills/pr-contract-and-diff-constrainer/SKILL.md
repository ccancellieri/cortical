---
name: pr-contract-and-diff-constrainer
description: Vincoli di dimensione delle PR, contratti di review e Golden Rule della contribuzione. Impone diff microscopici per codice AI, convenzioni di titolo/descrizione e scomposizione ("questo potrebbe essere 3 PR").
---

# Contratti di Pull Request & Vincoli della Dimensione di Review

## 1. La Regola Aurea del Progetto (Golden Rule)
> **"Una contribuzione deve valere più del tempo che serve per revisionarla."**

Se una Pull Request generata o assistita dall'AI richiede 3 ore di review estenuante per verificare 800 righe di diff eterogeneo, il valore netto per il team è negativo.

---

## 2. Costringere l'Unità di Revisione (Constrain the Unit of Review)
Quando è coinvolta l'intelligenza artificiale, **la PR deve essere il più piccola possibile**:

- **Diff Size Cap:** Massimo 150–250 righe di diff effettivo per PR (esclusi file di fixture o lock).
- **Files Touched Cap:** Massimo 3–5 file modificati per PR.
- **Zero Modifiche Non Correlate:** Nessun refactoring cosmetico, formattazione di altri moduli o cambio dipendenze inserito di nascosto nella stessa PR.
- **Cap PR Concorrenti degli Agenti:** Non eseguire più agenti che aprono PR contemporanee sullo stesso modulo.

### Lo Scopo: Forzare la Conversazione
Il punto non è applicare un rigore burocratico cieco:
> **È forzare una discussione attiva ogni volta che una PR supera una dimensione ragionevole.**
A volte la discussione conclude: *"Sì, in questo caso eccezionale va bene."*
Molto spesso conclude: ***"Questa PR potrebbe e dovrebbe essere divisa in tre PR separate."***

---

## 3. Standard di Contratto della PR (Ispirazione CodeRabbit & Top Tech Teams)

### A. Titolo della PR
- Inizia con un **verbo all'imperativo** in forma convenzionale (es. `feat: implement...`, `fix: isolate...`, `refactor: extract...`).
- Lunghezza contenuta entro **65 caratteri**.
- Descrive esattamente l'azione prodotta, non il processo (`add weather grounding`, non `work on weather`).

### B. Descrizione della PR (Sezioni Obbligatorie)
1. **Summary / Scopo:** 2-3 frasi sull'obiettivo di business o tecnico.
2. **Linked Issue Assessment:** Valutazione esplicita: *Questa PR fa esattamente e unicamente ciò che il ticket ha chiesto?* (Né più, né meno).
3. **Punti di Rischio & Edge Cases:** Comportamenti limite considerati.
4. **Piano di Verifica / Test Eseguiti:** Comandi esatti eseguiti per validare il diff in single-shot.

---

## 4. Pair Programming: La Prima Linea di Difesa
Pratica il **Pair Programming** (tra sviluppatori o tra sviluppatore e agente con supervisione continua) ogniqualvolta possibile:
- Valida il design **prima** di generare 500 righe di codice.
- Interrompi l'agente al primo segno di allontanamento dall'architettura (`barge-in`).
- Mantieni la comprensione umana al 100% durante l'intero ciclo di sviluppo.
