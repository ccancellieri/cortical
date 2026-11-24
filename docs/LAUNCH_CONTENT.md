# Cortical Launch Content & Visual Proof Kit

Every metric below is directly verified from `ccancellieri/cortical` (`2026-11-24`, commit `fddde77`, `51/51` `unittest` passing, `dependencies = []`). See [`docs/METRICS_LEDGER.md`](./METRICS_LEDGER.md) for the exact verification commands.

- **Repository:** `https://github.com/ccancellieri/cortical`
- **10-Second Zero-Install Browser Demo:** `https://ccancellieri.github.io/cortical/settings.html`

---

## Post 1 — The Engineering Craft Angle (Zero Dependencies, Zero Daemons, 8 Harnesses)

### English Version
Most AI agent tools ship a Node server, a Docker compose stack, and 40 dependencies just to sync config files.
We took the opposite route with **Cortical**: `dependencies = []` (Python 3.10+ stdlib only), zero background servers, and **51/51** passing tests.

Instead of reinventing LSPs (`Serena`), shell compressors (`RTK`), or local inference (`Ollama`/`Unsloth`), Cortical acts as a declarative control plane across **8 coding harnesses** (`Antigravity`, `pi`, `OpenCode`, `OpenClaw`, `Codex`, `Claude Code`, `dsh`, `Unsloth Studio`):
- Idempotent config sync with timestamped `--rollback <id>` (never overwrites your existing credentials)
- Lean 7-tool `stdio` MCP server (`4.09 ms` ingest+read handshake) with 2026 tool `annotations` & `outputSchema`
- Self-contained static browser configurator with **0 external CDNs** and **3 one-click interactive presets**
- Compact modular architecture (`18,224` LOC including embedded HTML/CSS/JS UI & wiki store, down from `~31.8K` LOC in `legacy-v0.2`)

Try it in 10 seconds in your browser (zero install):
https://ccancellieri.github.io/cortical/settings.html

Or reproduce locally in 60 seconds:
```bash
git clone https://github.com/ccancellieri/cortical.git && cd cortical
python3 -m venv .venv && .venv/bin/pip install --no-deps -e .
PYTHONPATH=src .venv/bin/python -m cortical.cli bench --compare
```

### Variante Italiana
Molti tool per coding agent richiedono un server Node, Docker e decine di dipendenze solo per sincronizzare configurazioni.
Con **Cortical** abbiamo scelto l'opposto: `dependencies = []` (solo stdlib Python 3.10+), zero server in background e **51/51** test verdi.

Cortical compone `Serena`, `RTK`, `Ollama` e `Unsloth` su **8 harness** (`Antigravity`, `pi`, `OpenCode`, `OpenClaw`, `Codex`, `Claude Code`, `dsh`, `Unsloth Studio`) con rollback atomico, MCP `stdio` da `4.09 ms` e una dashboard HTML statica senza CDN esterni.
Demo live in 10 secondi: https://ccancellieri.github.io/cortical/settings.html

### Suggested Visual Asset
- Side-by-side screenshot of `docs/settings.html` showing the **3 One-Click Demo Presets** card + terminal output of `unittest` (`51 tests OK`) and `pyproject.toml` (`dependencies = []`).

---

## Post 2 — Token Economics & Verifiable `fail_closed` Privacy

### English Version
Every time an AI agent dumps pretty-printed JSON or unredacted project attachments into a cloud LLM, you pay twice: once in wasted context tokens, and again in data-leakage risk.

We built two deterministic guardrails into **Cortical** (`0` external Python dependencies):
1. **Lossless `TOON` Compression:** Verified offline via `cortical bench --compare`: `745` pretty JSON tokens (`430` compact) drop to **`163` tokens** — **`-78.12%` vs pretty JSON** and **`-62.09%` vs compact JSON**, with lossless round-trip verification and an automatic `>= 10%` saving guard.
2. **Dynamic `fail_closed` Privacy Vault + Cryptographic Audit Ledger:** Strips OOXML/PDF metadata, masks PII/secrets while preserving **`100.0%` of technical prose**, blocks `max_security` items from remote orchestrators across MCP, sync rules, and pre-send hooks (`cortical hooks install`), and chains every event with **SHA-256** (`cortical vault audit --verify`) without ever storing raw PII.

Test live in your browser (click **Preset C: Hybrid Remote Guard**):
https://ccancellieri.github.io/cortical/settings.html

Reproduce the exact numbers locally:
```bash
PYTHONPATH=src .venv/bin/python -m cortical.cli bench --compare
PYTHONPATH=src .venv/bin/python -m cortical.cli vault audit --verify
```

### Variante Italiana
Inviare JSON verboso o allegati non filtrati a un LLM remoto costa doppio: token sprecati e rischio privacy.
In **Cortical** (`0` dipendenze esterne) abbiamo unito:
- Compressione lossless **`TOON`**: da `745` token JSON pretty (`430` compact) a **`163` token** (`-78.12%` / `-62.09%`).
- **Privacy Vault `fail_closed`** con precisione `100.0%` sui termini tecnici e **audit ledger SHA-256** (`cortical vault audit --verify`) che prova ogni blocco di egress verso modelli remoti senza salvare mai PII in chiaro.
Prova Preset C nel browser: https://ccancellieri.github.io/cortical/settings.html

### Suggested Visual Asset
- Clean dark-mode benchmark card showing:
  `Pretty JSON: 745 tok -> Compact JSON: 430 tok -> Cortical TOON: 163 tok (-78.12% / -62.09%) | PII Masked: 100% | Audit Chain: SHA-256 VERIFIED`.

---

## Post 3 — Running 27B Reasoning Models on a 16 GB Laptop Without Silent `4096` Clipping

### English Version
Running local `27B` coding/reasoning models on a 16 GB laptop usually fails in one of two silent ways:
1. Ollama quietly clips your context window to `4096` tokens.
2. Static `32K` harness configs or missing `reasoning_effort: none` trigger `max_tokens=1` truncations and `300s` stream timeouts.

We diagnosed both failure modes in a real `pi` coding session (**`3.48M` local tokens processed at `$0` cloud cost**) and built hardware-ceiling `auto_ctx` + adaptive timeouts directly into **Cortical**:
- **Tier 1A Hybrid (`16 GB RAM + 4 GB VRAM`):** places `qwen2.5:3b` in VRAM + `qwen3.5:9b-q3_k_xl` in swap-free hybrid offload.
- **Tier 1B Unified (`16 GB` Apple Silicon):** expands `qwen3.8:27b-iq2_xxs` (`7.2 GB` Unsloth Dynamic `UD-IQ2_XXS`) cleanly to **`65,536` context** in **`9.08 GiB` Metal VRAM** (`size == size_vram`, zero CPU spillover) with `keep_alive: 30m`, `reasoning_effort: none`, and `600s` adaptive timeout—and `qwen3.5:9b-q3_k_xl` to **`98,304` context**.

Explore Preset A (4 GB Hybrid) & Preset B (16 GB Unified 27B) in 10 seconds:
https://ccancellieri.github.io/cortical/settings.html

Inspect your own machine in one command:
```bash
PYTHONPATH=src .venv/bin/python -m cortical.cli doctor
PYTHONPATH=src .venv/bin/python -m cortical.cli sync --dry-run
```

### Variante Italiana
Far girare modelli `27B` su un portatile da 16 GB spesso si rompe in silenzio: `num_ctx` tagliato a `4096` oppure timeout a `300s`.
Dopo aver analizzato una sessione reale su `pi` da **`3.48M` token locali a `$0`**, abbiamo aggiunto in **Cortical** il sizing automatico `auto_ctx`: su Apple Silicon 16 GB, `qwen3.8:27b-iq2_xxs` gira a **`65,536` token di contesto** in **`9.08 GiB` di VRAM Metal** (zero swap, timeout adattivo `600s`) e `qwen3.5:9b-q3_k_xl` arriva a **`98,304` token**.
Prova Preset A e Preset B online: https://ccancellieri.github.io/cortical/settings.html

### Suggested Visual Asset
- Screenshot of `docs/settings.html` Models & Hardware Auto-Tuner with **Preset B** active (`65,536` ctx, Metal/KV budget bar) paired with live `ollama /api/ps` JSON (`"context_length": 65536`, `"size_vram": 9751316397`).
