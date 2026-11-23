# ADR-001: Zero-Server Dashboard State Hydration & Client-Machine Bridge

- **Status:** Accepted
- **Date:** 2026-11-23
- **GitHub Issue:** #20

## Context & Problem
Cortical is intentionally **zero-server by default** (`stdio` MCP + declarative file sync + Python 3.10+ stdlib only, `dependencies = []`). Users need a rich, trustworthy control plane (`docs/settings.html` and `cortical dashboard`) to inspect hardware tiers, 8 harnesses, models, Privacy Vault aliases, and ROI metrics—both locally (`file://`) and cold on GitHub Pages (`https://ccancellieri.github.io/cortical/settings.html`)—without spinning up any new background daemon or persistent HTTP server.

## Decision
1. **Embedded JSON State Hydration (`window.__CORTICAL_SNAPSHOT__`):** `cortical dashboard` builds a structured, sanitized snapshot (`hardware`, `models`, `harnesses`, `composers`, `vault`, `roi`, `bench`, `adrs`, `backups`, `config`) and embeds it directly into the generated `settings.html`. When exported with `--public-docs` (for GitHub Pages), personal paths and vault entries are stripped and the UI boots cleanly in **Demo / Unlinked Mode** with a 1-click **Load Snapshot / Link Folder** action.
2. **Dual-Path Client-Machine Bridge:**
   - **Browser File System Access API (`window.showDirectoryPicker` / `showOpenFilePicker`):** Optional direct read/write of `cortical.config.json`, `vault/*.json`, and `vault_inbox/` in Chromium browsers.
   - **Universal Cross-Platform CLI Fallback:** Every configuration mutation generates exact, idempotent, copyable `macOS` / `Linux` / `Windows` PowerShell scripts (`cortical sync`, `cortical models add`, `cortical ingest`, `cortical watch`, `cortical tune`) and downloadable config JSON diffs.

## Alternatives Considered
- **Persistent FastAPI / Flask / Node backend daemon:** Violates Cortical's zero-server, zero-dependency architecture and adds port/lifecycle friction.
- **Static read-only HTML report:** Cannot edit declarative settings, compose CLI apply scripts, or attach local folders.

## Consequences & Trade-offs
- **Pros:** Zero open ports, zero background processes, works 100% offline, identical UX on local disk and GitHub Pages.
- **Cons:** Direct filesystem writes require Chromium's File System Access API; Firefox/Safari users seamlessly use the copyable CLI Apply Script & JSON export fallback.
