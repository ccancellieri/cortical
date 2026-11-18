---
name: cortical-token-saver
description: Local-first multi-model offload, privacy sanitization, and universal @wiki:/@concept:/@skill: MCP context addressing across all coding harnesses (ChatGPT, Claude Code, Codex, OpenCode, Cursor, pi, Antigravity).
---

# Cortical Token-Saver, Multi-Model Local Loops & Universal `@` / `/` MCP Addressing

Use this skill to maximize **local LLM execution** (`0` cloud tokens, full GDPR/privacy isolation) and minimize remote cloud spend across **any harness or agent**. Remote cloud LLMs are reserved strictly for genuine architectural blockers after Cortical's local multi-model loop has distilled skills, Wiki nodes, and anonymized briefs.

## 1. Local-First Multi-Model Loop (Default Before Any Remote Escalation)

Run Cortical's iterative multi-model chain (`qwen2.5:1.5b` fast router/grounding → `qwen3.5:9b-q3_k_xl` analyst/synthesizer) locally first, automatically logging token telemetry to `agent_runs`:

* **Via MCP Tool (`cortical_local_loop`)** or **MCP Slash Prompt (`/mcp:cortical-wiki:cortical-local`):**
  ```json
  {
    "prompt": "Explain @concept:merkle-context-compression with @skill:learned-cortical-architecture /privacy:medium",
    "max_loops": 2
  }
  ```
* **Via Zero-Server CLI (`local-loop`):**
  ```bash
  PYTHONPATH=src .venv/bin/python -m cortical.cli --db .cortical_data/wiki.db local-loop \
    "Analyze @wiki:/src/cortical/privacy_sanitizer.py @concept:local-privacy-gdpr-sanitizer /privacy:low" \
    --models qwen2.5:1.5b,qwen3.5:9b-q3_k_xl --loops 2
  ```

**Decision Rule:**
1. If `completed_locally == true` (default for privacy-sensitive, single-repo, synthesis, test, or doc tasks), **return `local_answer` directly** (`$0.00` remote cost).
2. Forward `sanitized_remote_prompt` to the remote LLM **only** when `needs_remote_escalation == true` (never send raw files containing PII/secrets).

---

## 2. Universal Wiki & Knowledge Addressing (`@` and `/`) Across All Harnesses

Cortical exposes Wiki knowledge uniformly in two portable ways so every agent/harness resolves the same targets:

1. **Inline Universal Syntax (works in any prompt, CLI, HTTP, `wiki_enhance_prompt`, `wiki_resolve_references`, `cortical_local_loop`):**
   - `@wiki:<path>` or `@node:<path>` (e.g. `@wiki:/src/cortical/cli.py`) → loads L2 structured summary (override with `/tier:l1`, `/tier:l2`, `/tier:l3`, `/tier:max`)
   - `@concept:<slug>` (e.g. `@concept:merkle-context-compression`, `@concept:local-privacy-gdpr-sanitizer`, `@concept:zero-token-roi-analytics`) → loads canonical concept + matching L1 nodes + distilled insights
   - `@skill:<skill_id>` (e.g. `@skill:learned-cortical-architecture`) → loads procedural capability playbook
   - `@insight:<id_or_keyword>` → loads distilled memory rule
   - `@task:<episode_id>` → loads task 3+1 synthesis
   - `@root:workspace` / `@root:private_notes` → lists reconciled context files
   - **Slash Directives:** `/local` (block remote escalation), `/privacy:max_security` | `/privacy:low` | `/privacy:medium`, `/tier:l1` | `/tier:l2` | `/tier:l3` | `/tier:max`
2. **Standard MCP Native Protocol (`cortical-wiki-mcp` over stdio JSON-RPC 2.0):**
   - **MCP Resources (`@` picker in Claude Code, Cursor, Zed, Windsurf, OpenCode):** `resources/list` + `resources/read` exposing `cortical://node/{path}`, `cortical://concept/{slug}`, `cortical://skill/{skill_id}`, `cortical://insight/{insight_id}`, `cortical://root/workspace`, `cortical://root/private_notes`.
   - **MCP Prompts (`/` slash commands in compliant harnesses):** `cortical-local`, `cortical-wiki`, `cortical-sanitize`.

---

## 3. Compact Per-Response Token Report (Turn-Only Default)

Never burn remote cloud tokens to count usage. Execute locally:

```bash
PYTHONPATH=src .venv/bin/python -m cortical.cli --db .cortical_data/wiki.db token-report
```

- By default `token-report` prints **only the current response / active turn** (`turn_only=True`), keeping chat clutter minimal while linking directly to `html/token_report.html` and `html/wiki.html` (use `--full` only when lifetime history is explicitly requested in CLI).
