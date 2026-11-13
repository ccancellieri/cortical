---
name: visual-chrome-navigation
description: Navigazione visiva interattiva su Google Chrome in primo piano (focus) con apertura siti (Wikipedia, Google, YouTube, GitHub), compilazione DOM dei form di ricerca, invio della query e lettura/riassunto concettuale della pagina aperta.
---

# Visual Chrome Navigation, Form Filling & Page Reader

## Quando usarla
- Quando l'utente chiede esplicitamente di aprire il browser/Chrome, andare su un sito (es. Wikipedia), compilare la ricerca e mostrare il risultato in primo piano (`focus`).
- Quando in un turno successivo l'utente chiede di leggere o riassumere i concetti della pagina aperta.

## Procedura Operativa
1. Usa `chrome_search(site='wikipedia', query='<termine>', focus=True)` per portare Google Chrome in primo piano, aprire la scheda del sito, compilare il campo di ricerca nel DOM e inviare il form.
2. In un turno successivo, se l'utente chiede 'leggi' o 'riassumi i concetti della pagina aperta', invoca `chrome_read_page(mode='summarize'|'read')` per estrarre titolo, sezioni e testo pulito dalla scheda attiva di Chrome e sintetizzarli in italiano.
