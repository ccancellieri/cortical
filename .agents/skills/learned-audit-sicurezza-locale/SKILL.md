---
name: learned-audit-sicurezza-locale
description: Capability skill su Cortical Modular Architecture collegata a /src/cortical/cli.py.
---

# Capability Skill: Cortical Modular Architecture

## Conoscenze, Concetti & Nodi Wiki Collegati
- `concept:cortical-modular-architecture`
- `/src/cortical/cli.py`

## Regole & Insight Distillati
Pattern verificato: estrarre handler da src/cortical/cli.py sotto 40 LOC per funzione e rieseguire unittest (17/17 OK).
- Pattern verificato: estrarre handler da src/cortical/cli.py sotto 40 LOC per funzione e rieseguire unittest (17/17 OK).

## Procedura Riutilizzabile
1. **read (OK)** — def main(argv=None) exceeds 50 LOC due to inline subcommand branches.
2. **bash (OK)** — Ran 17 tests in 1.10s - OK

## Verifica
- Esegui: `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests`

## Provenienza & Evoluzione
- Origine iniziale: `pi-490216`

### Esperienza & Conoscenza Consolidata (`pi-76722`)
- **Concetti:** `concept:cortical-modular-architecture`
- **Regola Distillata:** Pattern verificato: estrarre handler da src/cortical/cli.py sotto 40 LOC per funzione e rieseguire unittest (17/17 OK).

### Esperienza & Conoscenza Consolidata (`pi-125376`)
- **Concetti:** `concept:cortical-modular-architecture`
- **Regola Distillata:** Pattern verificato: estrarre handler da src/cortical/cli.py sotto 40 LOC per funzione e rieseguire unittest (17/17 OK).

### Esperienza & Conoscenza Consolidata (`pi-50093`)
- **Concetti:** `concept:cortical-modular-architecture`
- **Regola Distillata:** Pattern verificato: estrarre handler da src/cortical/cli.py sotto 40 LOC per funzione e rieseguire unittest (17/17 OK).

### Esperienza & Conoscenza Consolidata (`pi-605370`)
- **Concetti:** `concept:cortical-modular-architecture`
- **Regola Distillata:** Pattern verificato: estrarre handler da src/cortical/cli.py sotto 40 LOC per funzione e rieseguire unittest (17/17 OK).

### Esperienza & Conoscenza Consolidata (`pi-693626`)
- **Concetti:** `concept:cortical-modular-architecture`
- **Regola Distillata:** Pattern verificato: estrarre handler da src/cortical/cli.py sotto 40 LOC per funzione e rieseguire unittest (17/17 OK).
