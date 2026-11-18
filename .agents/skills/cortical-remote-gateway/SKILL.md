---
name: cortical-remote-gateway
description: Optional, modular Remote Gateway Key auth, User Account Cap (`max_users`), HTTPS Tunnel (`localhost.run` / `cloudflared` / DuckDNS), and cross-harness integration for `pi`, `OpenCode`, `OpenClaw`, `Claude Code`, `Codex`, and `DeepSeek`.
---

# Cortical Remote Gateway — Standard Cross-Harness Tool & Extension Pack

This capability is **100% optional and modular**: Cortical is NOT a proprietary closed harness. It exposes the exact same Remote Gateway, Authentication Key (`X-Cortical-Key`), User Cap (`max_users`), Tunnel, and Chat API through **open protocols**:
1. **Standard MCP (`stdio`)**: `wiki_gateway_status`, `wiki_gateway_configure`, `wiki_gateway_expose`, `wiki_gateway_invite_user` in `cortical.wiki.mcp_server`.
2. **Standard HTTP REST + Bearer/API Key**: `GET /api/gateway/status`, `POST /api/gateway/expose`, `POST /api/auth/login`, `POST /api/auth/setup-password`, `POST /api/voice` (`X-Cortical-Key: ctk_...` or `Authorization: Bearer ...`).
3. **Standard CLI (`SKILL.md` / Tool Use)**: `.venv/bin/python -m cortical.cli gateway <status|expose|config|invite|duckdns>` (or `scripts/gateway_cli.py`).

## Compatibility Across Harnesses

| Harness / Client | Integration Mechanism | Config / Entrypoint |
| --- | --- | --- |
| **`pi` (`@earendil-works/pi-coding-agent`)** | Native Extension + `/gateway` + `manage_remote_gateway` + MCP | `.pi/extensions/cortical-harness.ts`, `.pi/mcp.json` |
| **OpenCode** | Native `.agents/skills/` auto-discovery + MCP `servers.cortical-wiki` | `opencode.json`, `.agents/skills/cortical-remote-gateway/SKILL.md` |
| **OpenClaw** | AgentSkills standard (`SKILL.md` + `scripts/gateway_cli.py`) | `.agents/skills/cortical-remote-gateway/` |
| **Claude Code** | Standard `.mcp.json` + `.agents/skills/` + CLI | `.mcp.json` |
| **Codex CLI** | Standard MCP stdio (`cortical-wiki-mcp`) or HTTP `X-Cortical-Key` | `~/.codex/config.toml` -> `[mcp_servers.cortical-wiki]` |
| **DeepSeek Harness / OpenAI-compatible** | Tool calling (`wiki_gateway_*`) or HTTP `POST /api/voice` with header `X-Cortical-Key` | Any HTTP / MCP client |

## Common Commands

```bash
# Inspect gateway status, user cap (e.g. 1/1), and active public URL
PYTHONPATH=src .venv/bin/python -m cortical.cli --db .cortical_data/wiki.db gateway status --include-secret

# Expose local Cortical over HTTPS (free zero-config SSH tunnel or cloudflared)
PYTHONPATH=src .venv/bin/python -m cortical.cli --db .cortical_data/wiki.db gateway expose --provider auto

# Adjust max users or toggle optional localhost bypass
PYTHONPATH=src .venv/bin/python -m cortical.cli --db .cortical_data/wiki.db gateway config --max-users 1 --auth-enabled true

# Send/prepare password setup link email
PYTHONPATH=src .venv/bin/python -m cortical.cli --db .cortical_data/wiki.db gateway invite --email user@example.com
```
