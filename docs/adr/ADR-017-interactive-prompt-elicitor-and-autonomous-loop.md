# ADR-017: Cortical Prompt Studio, Ephemeral Loopback Browser Elicitor (`cortical next`) & 5-Trigger Autonomous Loop

- **Status:** Accepted
- **Date:** 2026-11-24
- **Scope:** Composers (`src/cortical/composers/prompt_studio.py`), CLI (`cortical next` / `cortical prompt`), MCP Server (`cortical_next_prompt` tool + `cortical-next-prompt` prompt), Cross-Harness Sync (`src/cortical/harnesses/`), Static Control Plane (`docs/settings.html`)

## Context

Developers and autonomous coordinators (`Argon`, `Neon`, `pi`, `antigravity`, `claude-code`, `codex`, `opencode`, `openclaw`, `dsh`, `unsloth-studio`) frequently need to synthesize high-precision next-step prompts grounded in live repository state (`git`, open GitHub Issues, `docs/adr/`, sanitized Privacy Vault context, and prior iteration lessons).

Three architectural tensions must be resolved without violating Cortical's core invariants (`dependencies = []`, zero persistent background servers, zero external CDNs, `fail_closed` privacy):

1. **Cross-Harness Interactive Elicitation:** Native MCP `elicitation/create` (`input_required`) is not uniformly supported across all 8 CLI/IDE coding harnesses, and terminal raw-stdin prompts block or garble inside stdio MCP servers and non-TTY subshells.
2. **Zero-Server Security Posture:** Opening an HTTP listener to serve a rich browser questionnaire must never leave a persistent daemon running or expose local state to cross-origin / DNS-rebinding attacks.
3. **Human-in-the-Loop vs Autonomous Chaining:** Autonomous coordinators (`--mode auto` / `auto_if_confident`) need a deterministic, auditable policy deciding when a next prompt can be synthesized autonomously vs when human steering is mandatory.

## Decision

### 1. Three-Mode Elicitation Transport (Ephemeral Loopback Browser + Headless TUI/JSON + Static SPA)
- **Mode A — Ephemeral One-Shot Browser Elicitor (`127.0.0.1:0`, Default Interactive Mode):**
  - Binds an OS-assigned ephemeral loopback port (`http.server.HTTPServer(("127.0.0.1", 0), ...)`), generates a cryptographic 256-bit single-use token (`secrets.token_urlsafe(32)`), and opens `http://127.0.0.1:<port>/elicit?token=<token>` in Chrome (when requested/available) or the system default browser (`webbrowser`).
  - **Strict Anti-DNS-Rebinding & Token Guard:** Every request validates `Host` against exact `127.0.0.1:<port>` or `localhost:<port>` (returning HTTP `421 Misdirected Request` / `403 Forbidden` otherwise), checks the single-use token via `secrets.compare_digest`, sets `Cache-Control: no-store`, and rejects cross-origin `Origin` headers.
  - **Guaranteed Zero-Port Teardown:** The instant `/submit` or `/cancel` completes—or `timeout_sec` expires—the server signals completion and calls `server_close()` in a `finally` block, leaving **zero open ports** and **zero background daemons**.
- **Mode B — Headless TUI / JSON Fallback (`--mode tui` or SSH/non-GUI environments):**
  - Falls back cleanly to interactive terminal prompts when a TTY is attached, or deterministic recommended defaults when non-interactive.
- **Mode C — Zero-Server Browser Tab (`Prompt Studio` in `docs/settings.html`):**
  - Embeds a 100% client-side **Prompt Studio** domain inside `settings.html` so users can compose role-targeted continuation prompts offline or directly on GitHub Pages (`https://ccancellieri.github.io/cortical/settings.html`).

### 2. Context Harvesting, Loop Learning (`loop_memory.json`) & `fail_closed` Privacy Boundary
- **Harvester (`harvest_prompt_context`):** Collects active git branch, dirty file summary, recent commits, open GitHub Issues (`gh issue list` with graceful offline fallback to local ADRs/issues), `docs/adr/` index, and `.cortical_data/loop_memory.json` (recording preferred target profile, recurring constraints, rejected approaches, last issue/commit, and saved prompt templates).
- **Privacy Firewall & `TOON` Compaction:**
  - When the target profile involves remote egress (`hybrid`, `antigravity`, `claude-code`, `codex`, or `remote_orchestrator_active(cfg)`), context packets pass through `classify_and_sanitize` (`fail_closed` on `max_security` vault items—never injecting raw `.cortical_data/` or `max_security` aliases) and structured issue/commit metadata is compressed via `compress_structured` (`TOON`).
- **Adaptive Question Generator:** Generates 2–5 high-leverage multiple-choice (`radio` / `checkbox`) questions with `(Recommended)` first-choice trade-offs, per-question comment boxes, global directives, and target profile selection (`pi` Local Worker, `argon` Coordinator, `neon` UX/QA Persona, `hybrid` Remote+Local, `general` Harness)—100% in Python stdlib by default, with optional local enrichment via `@role:daily_coder`.

### 3. Deterministic 5-Trigger Confidence Gate (`--mode auto` / `auto_if_confident`)
Evaluate five normalized risk triggers (`0.0` safe -> `1.0` high risk) before autonomous prompt synthesis:
1. **Irreversibility:** Destructive/public keywords (`delete`, `drop`, `force-push`, `publish`, `production`, `rm -rf`, external PR/post).
2. **Scope / Scale:** Multi-subsystem blast radius (`> 8` dirty files, repo-wide refactor/migration, or broad cross-package rewrite).
3. **Ambiguity:** Very terse/underspecified seed (`< 4` meaningful words without `--resume` or `--issue`) or conflicting directives.
4. **Privacy / Compliance:** References to sensitive files, PII, credentials, or `max_security` vault aliases while targeting a remote/hybrid profile.
5. **Novelty:** Cold-start `loop_memory` with an unfamiliar architectural domain not covered by existing ADRs or prior loop history.

- **Decision Rule:** Compute `confidence_score = round(1.0 - max_trigger_weight, 2)` (penalized by multi-trigger accumulation). If `confidence_score >= threshold` (default `0.72`) and zero hard triggers fire, synthesize autonomously and log an audit record under `.cortical_data/prompts/`. Otherwise, escalate automatically to the Ephemeral Browser UI pre-populated with recommended answers (falling back to structured `escalation_required` metadata in non-GUI headless calls).

### 4. Universal 8-Harness Exposure
- **CLI:** `cortical next` (alias `cortical prompt`) with `--resume`, `--mode browser|tui|auto`, `--browser chrome|default`, `--target`, `--issue`, `--out`, `--json`.
- **MCP (`cortical-mcp`):** Expose `cortical_next_prompt` (8th core MCP tool with full `annotations` & `outputSchema`) + native MCP prompt `cortical-next-prompt`.
- **8-Harness Sync (`cortical sync`):** Inject `/next` (`cortical next`) workflow rules and slash-command/skill files across `pi`, `antigravity`, `opencode`, `openclaw`, `codex`, `claude-code`, `dsh`, and `unsloth-studio`.

## Consequences

- **Positive:** Gives every CLI and IDE agent an ergonomic, zero-CDN browser elicitation UI + autonomous loop synthesizer with cryptographic loopback safety, `fail_closed` privacy, and zero third-party dependencies.
- **Trade-offs:** Core `cortical-mcp` tool surface grows from `7` to `8` tools (`cortical_next_prompt`), documented transparently across `README.md`, `docs/INTEGRATIONS.md`, `docs/METRICS_LEDGER.md`, and `tests/`.
