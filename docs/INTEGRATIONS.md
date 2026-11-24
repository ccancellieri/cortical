# Cortical Integrations Guide (8 Coding Harnesses, MCP & OSS Composition)

> **Live Site:** `https://ccancellieri.github.io/cortical/`

Cortical runs **Zero-Server by default** (`python3 -m cortical.mcp_server` over `stdio`) across **macOS, Linux, and Windows** (`dependencies = []`), composing best-of-breed OSS tools (`Serena`, `RTK`, `PinchTab` / `Playwright`, `context-mode`) alongside Cortical's 3-Channel Privacy Vault and lossless `TOON` compression.

---

## 1. Safe 4-Step Cross-Platform Harness Sync (`cortical sync`)

```bash
# 1. Benchmark lossless TOON, Zero-LLM Privacy Vault & 7-tool MCP
PYTHONPATH=src .venv/bin/python -m cortical.cli bench --compare

# 2. Inspect OS/RAM/VRAM tier, Tier-1 Zero-LLM Stdlib & active local runner
PYTHONPATH=src .venv/bin/python -m cortical.cli doctor

# 3. Preview exact diffs across all 8 harnesses FIRST (modifies 0 files)
PYTHONPATH=src .venv/bin/python -m cortical.cli sync --dry-run

# 4. Apply idempotently (prints timestamped backup ID for instant rollback)
PYTHONPATH=src .venv/bin/python -m cortical.cli sync
PYTHONPATH=src .venv/bin/python -m cortical.cli sync --rollback <backup_id>
```

### Pluggable Local Runners (`active_runner` in `cortical.config.json` / `settings.html`)
Cortical is **runner-neutral**—Tier-1 features (Privacy Vault MD/DOCX/XLSX/PPTX/PDF + SHA-256 audit ledger, `TOON` compression, `doctor`, `sync`) require **no local LLM runner at all**, while Tier-2 features (`cortical_local_offload`, `cortical watch` image OCR, `--ner`, LiteLLM router generation) work across **7 local backends**:
- `ollama` (`http://127.0.0.1:11434`)
- `unsloth` (`http://127.0.0.1:8888/v1` — Unsloth Studio)
- `lm_studio` (`http://127.0.0.1:1234/v1` — LM Studio)
- `llama_cpp` (`http://127.0.0.1:8080/v1` — `llama-server`)
- `mlx_lm` (`http://127.0.0.1:8080/v1` — Apple Silicon `mlx_lm.server`)
- `vllm` (`http://127.0.0.1:8000/v1`)
- `openai_compatible` (`http://127.0.0.1:4000/v1` or any custom local endpoint)

| Harness | Pre-Send Attachment Interception | Config Synced (`macOS` / `Linux` / `Windows`) |
| --- | --- | --- |
| `pi` | **100% Verified** (Channel 3 extension) | `~/.pi/agent/{mcp,settings,models}.json` + `AGENTS.md` |
| `claude-code` | **100% Verified** (`PreToolUse` / hook) | `~/.claude.json` + `~/.claude/CLAUDE.md` |
| `opencode` | **100% Verified** (plugin/MCP) | `$XDG_CONFIG_HOME/opencode/config.json` + `AGENTS.md` |
| `openclaw` | **100% Verified** (hook) | `~/.openclaw/openclaw.json` + `~/.openclaw/AGENTS.md` |
| `codex` | **100% Verified** (hook/MCP) | `~/.codex/config.toml` + `~/.codex/AGENTS.md` |
| `dsh` (`deepseek-harness`) | **100% Verified** (hook) | `~/.dsh/settings.yaml` (`@deepseek-ai/dsh-mcp-client`) |
| `antigravity` | Not guaranteed (use Channels 1 & 2) | `~/.gemini/config/mcp_config.json` + `~/.gemini/GEMINI.md` |
| `unsloth-studio` | Runner integration | `~/.cortical/unsloth-studio-mcp.json` |

---

## 2. Standard 8-Tool MCP Server Setup (`stdio` JSON-RPC 2.0)

Use `python3 -m cortical.mcp_server` (or installed `cortical-mcp` script).

### Antigravity / Gemini CLI (`~/.gemini/config/mcp_config.json`)
```json
{
  "mcpServers": {
    "cortical": {
      "command": "python3",
      "args": ["-m", "cortical.mcp_server"],
      "env": {
        "PYTHONPATH": "/path/to/cortical/src",
        "CORTICAL_VAULT_DB": "/path/to/cortical/.cortical_data/vault.db"
      }
    }
  }
}
```

### Claude Code
```bash
claude mcp add cortical \
  -e PYTHONPATH=/path/to/cortical/src \
  -e CORTICAL_VAULT_DB=/path/to/cortical/.cortical_data/vault.db \
  -- python3 -m cortical.mcp_server
```

### OpenAI Codex CLI (`~/.codex/config.toml`)
```toml
[mcp_servers.cortical]
command = "python3"
args = ["-m", "cortical.mcp_server"]

[mcp_servers.cortical.env]
PYTHONPATH = "/path/to/cortical/src"
CORTICAL_VAULT_DB = "/path/to/cortical/.cortical_data/vault.db"
```

### DeepSeek Harness (`dsh`) & OpenCode & `pi`
- **DeepSeek Harness (`dsh`):** managed via `cortical sync --harness dsh` (`~/.dsh/settings.yaml`).
- **OpenCode (`opencode.json`):** included in repo root pointing to `python3 -m cortical.mcp_server`.
- **`pi` (`@earendil-works/pi-coding-agent`):** `pi --package /path/to/cortical` registers `.pi/extensions/cortical-harness.ts` (Channel 3 pre-send interception) and `.agents/skills/`.

---

## 3. Lean 8-Tool MCP Surface + Native Resources & Prompts (Plus Opt-In 5-Tool `cortical-wiki`)

| MCP Tool / Surface | Purpose |
| --- | --- |
| `cortical_vault_read` | Read sanitized, compressed `@private:<alias>` / `task_tag` item (`blocks max_security`) |
| `cortical_ingest_private` | Ingest file/text with `auto` \| `fail_closed` \| `fail_open` classification & metadata stripping |
| `cortical_compress` | Deterministic lossless TOON / XML / YAML / log compression (`>= 10%` guard vs compact JSON) |
| `cortical_doctor_status` | Hardware tier, GPU/VRAM, composed OSS tools & model recommendations |
| `cortical_local_offload` | Delegate prompt/task offline to local LLM runner (records SQLite telemetry at `$0` cloud cost) |
| `cortical_roi_report` | Zero-cloud-token local vs cloud token usage, USD savings & remaining cloud budget |
| `cortical_handoff` | Save/load shared working context across `antigravity`, `pi`, `opencode`, `claude-code`, `codex` |
| `cortical_next_prompt` | Harvest repo/issue/ADR state + `loop_memory`, run 5-Trigger gate or one-shot `127.0.0.1:0` browser elicitor (`cortical next`), and synthesize continuation prompt |
| Native `resources` & `prompts` | `@`-autocomplete `cortical://private/<alias>`, `cortical://brain`, `/cortical-private`, `/cortical-local` & `/cortical-next-prompt` |
| Opt-in `cortical-wiki` (`--wiki`) | `wiki_search`, `wiki_navigate`, `wiki_crawl_delta`, `wiki_record_episode`, `wiki_verify_citation` |

---

## 4. On-Demand Streamable HTTP Bridge (`serve-mcp`)

Cortical keeps zero open ports by default. When connecting a browser or remote harness over Streamable HTTP:

```bash
PYTHONPATH=src .venv/bin/python -m cortical.cli serve-mcp serena --project . --port 9121 --dry-run
PYTHONPATH=src .venv/bin/python -m cortical.cli serve-mcp cortical --project . --port 9122
```
