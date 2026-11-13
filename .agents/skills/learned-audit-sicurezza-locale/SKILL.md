---
name: learned-audit-sicurezza-locale
description: Skill appresa dal task pi-578464 (Audit sicurezza locale). Usa quando affronti compiti simili su audit, sicurezza, locale.
---

# Skill Appresa: Audit sicurezza locale

## Contesto & Origine
- **Task Sorgente:** `pi-578464`
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
