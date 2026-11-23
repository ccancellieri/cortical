# ADR-007: Zero-Friction Workspace Auto-Discovery, IDE Integration & Control Plane SSOT

- **Status:** Accepted (SSOT reconciliation #7 & default model fix #17 implemented and closed)
- **Date:** 2026-11-23
- **GitHub Issue:** #29

## Context & Problem
Developers adopting Cortical across heterogeneous IDEs (`Cursor`, `Claude Code`, `VS Code`, `OpenCode`, `Windsurf`, `Cline`, `Zed`, `Antigravity`, `pi`) previously had to pass `PYTHONPATH=src`, specify `--db` manually, hand-edit MCP JSON configs, and manually reconcile stale model IDs (e.g., `qwen3.8:27b-q4_xxs` vs `qwen3.8:27b-iq2_xxs` across Ollama, LiteLLM, and `pi`) or Chrome remote debugging sessions.

## Decision
1. **Native Entry-Point & Git-Style Workspace Discovery (`src/cortical/workspace.py`, `install.sh`, `Makefile` — #8):** Install `.venv/bin/cortical` and `.venv/bin/cortical-mcp` with zero external deps; auto-discover `<project_root>/.cortical/` stopping at `.git` (ignoring global `~/.cortical`); provide `cortical init` with idempotent `.gitignore` and `.corticalignore` sync (`.claudeignore`, `.cursorignore`, `.geminiignore`).
2. **Idempotent IDE Integration & Diagnostics (`src/cortical/integrations.py` — #9):** Provide `cortical integrate <target> [--global|--project] [--dry-run]` with `.bak` backups, preserved user keys, and enhanced `cortical doctor` performing live stdio JSON-RPC `initialize` pings.
3. **Non-Destructive Browser & Autonomous Loop Resilience (`src/cortical/harnesses/chrome.py`, `scripts/cortical_overnight.py`):** Never kill the user's personal Chrome; use `DevToolsActivePort` / `--autoConnect` + Tab Groups and `1 Loop = 1 fresh pi -p --no-session` with mandatory `unittest` gates.
4. **Single Source of Truth Reconciliation (#7, #17):** Centralize validated model tags and semantic router aliases (`cortical-fast`, `cortical-deep`, `cortical-vision`) so LiteLLM, Ollama, and all 8 harnesses stay in sync automatically.

## Consequences & Trade-offs
- **Pros:** One-command onboarding (`./install.sh && cortical init && cortical integrate`), zero destructive Chrome kills, and deterministic overnight loops.
- **Cons:** Requires completing the automated SSOT reconciliation command tracked in #7 and fixing stale default model tags in #17.
