# Cortical Upstream Ecosystem Playbook (PRs & Issue Contributions)

Every upstream contribution below follows **ADR-012** (Value-First Contract): solve a real host problem with zero bloat, zero forced dependencies, and reproducible numbers—**never auto-submitted without human review**.

---

## Prioritized Upstream Action Queue (7 Prominent Repositories)

### 1. `modelcontextprotocol/servers` & Glama (`#44` — Ready to Submit)
- **Target:** `https://github.com/modelcontextprotocol/servers` (community registry PR) & `https://glama.ai/mcp/servers` (refresh `v0.3.0`)
- **Maintainer Value:** Accurate `2025-12-11` registry manifest ([`server.json`](../server.json)) + [`glama.json`](../glama.json) exposing full MCP `2025-06-18` `annotations`, `outputSchema`, `structuredContent`, `stdio` + `streamable-http`, and `dependencies = []`.
- **Ready-to-Use PR Summary:**
  > Adds/refreshes `io.github.ccancellieri/cortical` (`v0.3.0`): Python 3.10+ stdlib-only (`dependencies = []`) MCP server providing a `fail_closed` Privacy Vault with SHA-256 audit ledger, lossless `TOON` compression (`-62.09%` vs compact JSON), and hardware-aware local offload (`4.09 ms` handshake).

### 2. `earendil-works/pi` (`#47` — Hook Shipped in `src/cortical/harnesses/hooks.py`)
- **Target:** `https://github.com/earendil-works/pi` (extensions / community packages)
- **Pain Point Solved:** Prevents `max_tokens=1` length truncations when local `27B` models hit hardcoded `32K` context limits, prevents 300s stream aborts by setting `reasoning_effort: "none"`, and adds `@private:<alias>` Channel 3 pre-send protection.
- **Ready Artifact:** `cortical hooks install --target pi` (`~/.pi/agent/extensions/cortical-intercept.ts`) + `cortical sync --harness pi`.

### 3. `deepseek-ai/deepseek-harness` (`dsh`) (`#45` — Hook Shipped in `hooks.py`)
- **Target:** `https://github.com/deepseek-ai/deepseek-harness` (Cordis plugin recipes / docs)
- **Pain Point Solved:** Ready-to-drop `@deepseek-ai/dsh-mcp-client` YAML recipe + `onBeforeDispatch` Cordis pre-send attachment sanitizer (`~/.dsh/plugins/cortical-cordis-hook.mjs`) so private attachments never hit remote APIs unmasked.
- **Ready Artifact:** `cortical sync --harness dsh && cortical hooks install --target dsh`.

### 4. `anomalyco/opencode` (ex `sst/opencode`) (`#46` — Hook Shipped in `hooks.py`)
- **Target:** `https://github.com/anomalyco/opencode` (docs / plugins / custom slash commands)
- **Pain Point Solved:** One-file plugin (`~/.config/opencode/plugins/cortical-hook.mjs`) compacting oversized tool/message JSON via lossless `TOON` (`>= 10%` saving guard) plus `/cortical-private` and `/cortical-local` slash commands.
- **Ready Artifact:** `cortical sync --harness opencode && cortical hooks install --target opencode`.

### 5. Composable Token-Efficiency Stack (`Serena` + `RTK` + `context-mode` + `TOON`) (`#48`)
- **Target:** `https://github.com/oraios/serena`, `https://github.com/rtk-ai/rtk`, `https://github.com/mksglu/context-mode` (interop benchmark discussion / docs PR)
- **Pain Point Solved:** Developers ask how LSP navigation (`Serena`), shell compaction (`RTK`), subprocess sandboxing (`context-mode`), and structured JSON/YAML payload compression (`TOON`) compose without overlapping.
- **Draft Discussion / PR Body:**
  > We benchmarked the 4-layer zero-daemon stack across 8 coding harnesses: `Serena` trims file reads to symbol bodies, `RTK` compresses shell/test logs, `context-mode` sandboxes oversized tool outputs, and deterministic pure-Python `TOON` (`cortical compress`) reduces structured JSON payloads by **`78.12%` vs pretty JSON / `62.09%` vs compact JSON** (`745` / `430` -> `163` tokens, lossless roundtrip). Reproducible offline in 10 seconds via `python3 -m cortical.cli bench --compare` (0 external dependencies).

### 6. `unslothai/unsloth` & Ollama Ecosystem (`#50`)
- **Target:** `https://github.com/unslothai/unsloth` (Dynamic 2.0 GGUF / Ollama deployment docs & discussions)
- **Pain Point Solved:** Ollama silently defaults to `num_ctx=4096` even when `qwen3.8:27b-iq2_xxs` (`7.2 GB` weights, `262K` native GQA-4 context) fits **`65,536` context in `9.08 GiB` Metal VRAM** on a 16 GB Apple Silicon laptop with zero swap and `qwen3.5:9b-q3_k_xl` fits **`98,304` context**.
- **Draft Recipe Contribution:**
  > On 16 GB Unified Apple Silicon (`10.67–11.2 GB` Metal working set), pairing `num_ctx: 65536`, `keep_alive: "30m"`, `reasoning_effort: "none"` (`think: false` in `ollama_chat`), and `timeout: 600` eliminates both silent `4096` clipping and `300s` stream timeouts while keeping `size == size_vram == 9.08 GiB` (zero CPU spillover). Verified formula implemented in stdlib Python (`src/cortical/hardware/context_window.py`).

### 7. `drmikecrowe/harnessed` & `BerriAI/litellm` (`#49`, `#51`)
- **Target:** `https://github.com/drmikecrowe/harnessed` (discussions/PR) & `https://github.com/BerriAI/litellm` (custom guardrail callback example)
- **Pain Point Solved:** Containerized meta-harnesses and HTTP routers need a lightweight, zero-dependency `fail_closed` pre-call guardrail preventing raw secrets (`sk-`, `AIza`, `ghp_`, `AKIA`) and local-only vault files from reaching remote providers.
- **Ready Artifact:** `cortical hooks install --target litellm` (`~/.cortical/hooks/litellm_cortical_guard.py`) + `cortical profile export` (`cortical-profile/v1`).
