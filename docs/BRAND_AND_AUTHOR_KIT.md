# Cortical Brand Guide & Author Personal Branding Kit

Prepared for **Carlo Cancellieri** (`@ccancellieri`) to align the positioning of **Cortical** across GitHub, Glama.ai, LinkedIn, X (Twitter), and Reddit (`r/mcp`, `r/LocalLLaMA`).

---

## Part 1: Cortical Brand Identity

### 1. Three Tagline Proposals

- **Technical (Recommended for GitHub / Glama):**
  `Zero-dependency MCP control plane for private, local-first AI agents.`
- **Visionary (For Keynotes / Landing Hero):**
  `The cognitive firewall between your private knowledge and cloud AI.`
- **Performance-Driven (For Benchmarks / X / Reddit):**
  `Cut agent token burn by 78% and keep sensitive files offline with zero dependencies.`

### 2. Tone of Voice & Core Vocabulary

- **Voice:** Principal engineer speaking to peers. Direct, verifiable, calm, zero hype. Lead with concrete architecture (`dependencies = []`, `127.0.0.1:0`, `fail_closed`, `-78.12%` measured via `cortical bench --compare`) instead of vague adjectives.
- **Neural / Cortical Metaphor (Restrained & Functional):**
  - **Prefrontal Gate / Cortical Layer:** The deterministic local boundary that decides what stays private (`fail_closed`) and what can safely leave the machine.
  - **Working Memory vs. Long-Term Vault:** Ephemeral cross-harness handoffs (`cortical_handoff`) vs. factorized `3+1` Second Brain storage (`cortical://brain`).
  - **Synaptic Routing (`@role:*`):** Semantic model roles decoupled from vendor tags, letting the same workflow route across 7 local runners or cloud fallback.
  - **Avoid:** generic AI hype, unverified superlatives, and vague buzzwords without numbers.

### 3. Logo & GitHub OpenGraph (`1280x640`) Generation Prompts

#### Minimalist Dev-Tool Logo Prompt (Vercel / Linear / Raycast Aesthetic)
```text
Minimalist geometric developer-tool logomark for "Cortical", inspired by Linear, Raycast, and Vercel. A crisp isometric hexagonal cortex shield formed by three interlocking parallel ribbon lines representing a local privacy boundary and token compression layer. Monochromatic silver-white (#F8FAFC) stroke with a single subtle electric cyan (#38BDF8) node accent on a deep obsidian matte background (#09090B). Ultra-clean vector geometry, uniform stroke weight, generous negative space, flat Swiss grid precision, no gradients clutter, no text, no 3D brain clichés, SVG-ready icon.
```

#### Ready-to-Use Minimalist SVG Logo (`docs/assets/cortical-mark.svg`)
```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64" fill="none">
  <rect width="64" height="64" rx="14" fill="#09090B"/>
  <path d="M32 12L50 22.5V41.5L32 52L14 41.5V22.5L32 12Z" stroke="#E2E8F0" stroke-width="2.5" stroke-linejoin="round"/>
  <path d="M32 20L43 26.5V37.5L32 44L21 37.5V26.5L32 20Z" stroke="#94A3B8" stroke-width="2" stroke-linejoin="round"/>
  <circle cx="32" cy="32" r="4.5" fill="#38BDF8"/>
  <path d="M32 12V20M32 44V52M14 22.5L21 26.5M43 37.5L50 41.5" stroke="#38BDF8" stroke-width="1.75" stroke-linecap="round"/>
</svg>
```

#### GitHub Social Preview / OpenGraph (`1280x640`) Prompt
```text
Clean dark-mode developer product OpenGraph card (1280x640) in the visual style of Linear and Vercel. Background: deep charcoal #09090B with a faint 24px technical dot grid (#18181B). Left side: crisp geometric hexagon-and-node icon in white and cyan (#38BDF8), bold sans-serif title "Cortical" (Inter/Geist, #F8FAFC), subtitle "Zero-dependency MCP control plane for private, local-first AI agents." (#94A3B8), and three clean monospace pill badges: "Python Stdlib Only (0 Deps)", "Fail-Closed Privacy Vault", "-78% Lossless TOON". Right side: clean minimal terminal card showing "$ cortical bench --compare" with green OK checks and a compact architecture flow (Local Vault -> TOON -> MCP). Crisp typography, zero clutter, high contrast.
```

---

## Part 2: Author Personal Branding (`Carlo Cancellieri` / `@ccancellieri`)

### 1. GitHub Profile Bio (160 chars max)
```text
Software Architect & creator of Cortical (zero-dependency MCP control plane for local-first, privacy-safe AI agents). Python, distributed systems & OSS.
```

### 2. X (Twitter) Bio (160 chars max)
```text
Software Architect building @Cortical (open-source, zero-dep MCP control plane for private local-first AI agents). Privacy, token economics & OSS.
```

### 3. LinkedIn Headline & About Snippet

**Headline:**
```text
Software Architect | Creator of Cortical (Open-Source MCP Control Plane) | Local-First AI Infrastructure, Privacy Engineering & Distributed Systems
```

**About (Opening Block):**
```text
I design privacy-first AI infrastructure and open-source developer tools.

I am the creator of Cortical, a zero-dependency Python MCP server and declarative agent control plane that lets teams and professionals use frontier AI without leaking private files or burning cloud token budgets. Cortical combines a fail-closed local Privacy Vault, lossless TOON payload compression (-78% vs pretty JSON), and multi-runner local LLM offload across Ollama, Unsloth, LM Studio, MLX, llama.cpp, and vLLM.

My focus is pragmatic engineering: auditable codebases, deterministic guardrails, reproducible benchmarks, and tools that respect both developer time and data sovereignty.
```

---

## Part 3: Release Launch Copy (`Cortical v0.3.0`)

### 1. X (Twitter) Post (280 chars / 2-post thread)

**Tweet 1:**
```text
Every time you attach a PDF or JSON dump to a coding agent, you leak private data and pay for redundant tokens.

I built Cortical v0.3.0: a zero-dependency Python MCP control plane.
- Fail-closed Privacy Vault (0 LLM needed)
- -78% lossless TOON compression
- Local offload across 7 runners

Repo: https://github.com/ccancellieri/cortical
```

**Tweet 2:**
```text
One command syncs MCP config across Claude Code, Cursor, Windsurf, OpenCode, Codex, and pi with --dry-run and --rollback.

Zero external pip packages (`dependencies = []`), zero background daemons, 64/64 tests green.

Live zero-install demo: https://ccancellieri.github.io/cortical/
```

### 2. LinkedIn Release Post (3-Second Readable, Human Voice)

```text
Most AI agent setups have two silent leaks: private documents sent straight to cloud prompts, and thousands of wasted tokens on raw JSON and repetitive file reads.

I just shipped Cortical v0.3.0 (Apache-2.0, Python 3.10+ stdlib only, zero external dependencies) to fix both at the MCP layer.

What happens in 30 seconds when you connect Cortical to Claude Desktop, Cursor, Windsurf, OpenCode, Codex, or pi:

1. Private files stay protected locally. Cortical strips Office/PDF metadata and masks PII/secrets in pure Python stdlib before anything touches a remote model. Items marked max_security are blocked fail-closed from cloud egress.
2. Structured payloads shrink automatically. Built-in lossless TOON compression cuts JSON token size by 78.12% vs pretty JSON (62.09% vs compact) with exact round-trip fidelity.
3. Routine file reads run locally at $0. Cortical routes summarization and reviews to your local runner (Ollama, Unsloth Studio, LM Studio, llama.cpp, MLX, or vLLM) through semantic @role slots.

No background daemon, no third-party dependency tree, and a full Docker image for clean MCP inspection.

Try the zero-install browser configurator or clone the repo:
GitHub: https://github.com/ccancellieri/cortical
Live Demo: https://ccancellieri.github.io/cortical/
Glama MCP Directory: https://glama.ai/mcp/servers/ccancellieri/cortical

#OpenSource #MCP #AI #Python #LocalLLM #Privacy
```

### 3. Reddit Post (`r/mcp` & `r/LocalLLaMA`)

**Title:**
```text
Cortical v0.3.0: Zero-dependency Python MCP server for fail-closed PII masking, -78% lossless TOON compression, and local LLM offload across 7 runners
```

**Body:**
```text
I built Cortical because I got tired of maintaining separate MCP configs across Claude Code, Cursor, OpenCode, Codex, and pi while accidentally leaking client names/IBANs in attachments and burning cloud tokens on raw JSON dumps.

What it does (and how it differs from typical wrappers):
- Zero external runtime dependencies: `dependencies = []` in `pyproject.toml` (Python 3.10+ stdlib only) and zero background daemons (`stdio` MCP by default, Dockerfile included).
- Tier-1 Zero-LLM Privacy Vault: deterministic PII/secret redaction + `.docx`/`.xlsx`/`.pptx`/`.pdf` metadata stripping + SHA-256 audit ledger. Works with no local model installed. Anything tagged `max_security` is blocked fail-closed from remote cloud egress.
- Deterministic lossless TOON compression: measured `-78.12%` vs pretty JSON (`-62.09%` vs compact JSON) via `cortical bench --compare`, with automatic fallback if savings drop under 10%.
- Local LLM offload (`cortical_local_offload`): reads local `file_paths` directly from disk via your local runner (Ollama, Unsloth Studio, LM Studio, llama.cpp, Apple MLX, vLLM, or any OpenAI-compatible endpoint) so raw files cost 0 cloud input tokens.
- Lean 8-tool MCP surface with full `annotations`, `outputSchema`, native `resources` (`cortical://private/<alias>`, `cortical://brain`), and `prompts`.

Quick verification in 60 seconds:
```bash
git clone https://github.com/ccancellieri/cortical.git && cd cortical
python3 -m venv .venv && .venv/bin/pip install --no-deps -e .
PYTHONPATH=src .venv/bin/python -m cortical.cli bench --compare
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q
```

Repo: https://github.com/ccancellieri/cortical
Live static demo (zero install, zero CDNs): https://ccancellieri.github.io/cortical/

Feedback on the MCP tool schemas and multi-runner setup is very welcome.
```
