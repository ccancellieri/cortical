---
name: learned-verifica-permessi
description: Skill appresa dal task pi-100075 (Verifica permessi). Usa quando affronti compiti simili su verifica, permessi.
---

# Skill Appresa: Verifica permessi

## Contesto & Origine
- **Task Sorgente:** `pi-100075`
- **Obiettivo Originario:** Verifica permessi

## Lezione Chiave Consolidata
Carlo, per favore conferma i tuoi permessi.

## Procedura Riutilizzabile
1. **bash (OK)** — ./scripts/setup.sh ./scripts/enable-service.sh ./opencode.json ./AGENTS.md ./.git/config ./.git/objects/0d/7c8042eb8bd62da0ce284d5cd626114ee49ac8 ./.git/objects/59/044968e21c47affe

## Verifica
- Esegui: `ls -l && find . -type f -perm -002 && find . -type d -perm -002 && find . -type f -perm -004 && find . -type d -perm -004 && find . -type f -perm -001 && find . -type d -perm -001`
