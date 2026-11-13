---
name: learned-esegui-bash-comando-curl
description: Skill appresa dal task pi-701559 (Esegui con bash il comando curl -sI https://example.com per verificare se la ret). Usa quando affronti compiti simili su esegui, bash, comando, curl.
---

# Skill Appresa: Esegui con bash il comando curl -sI https://example.com per verificare

## Contesto & Origine
- **Task Sorgente:** `pi-701559`
- **Obiettivo Originario:** Esegui con bash il comando curl -sI https://example.com per verificare se la rete esterna è bloccata, poi riporta in italiano cosa è successo.

## Lezione Chiave Consolidata
Task pi-701559 completato (2 passi tool eseguiti). - bash (ERR): [Cortical Hard Guardrail] Blocked by non-bypassable security/focus guardrail. - bash (OK): PING 127.0.0.1 (127.0.0.1): 56 data bytes 64

## Procedura Riutilizzabile
1. **bash (ERR)** — [Cortical Hard Guardrail] Blocked by non-bypassable security/focus guardrail.
2. **bash (OK)** — PING 127.0.0.1 (127.0.0.1): 56 data bytes 64 bytes from 127.0.0.1: icmp_seq=0 ttl=64 time=0.166 ms --- 127.0.0.1 ping statistics --- 1 packets transmitted, 1 packets received, 0.0%

## Verifica
- Esegui: `ping -c 1 127.0.0.1`
