# ADR-018: Colleague Second Brain, Bulk Disk Privatization, Knowledge Reconciliation & Smart Local-to-Remote Escalation

- **Status:** Accepted
- **Date:** 2026-11-25
- **Extends:** ADR-005 (Wiki Store), ADR-013 (Hybrid Local-First Orchestrator), ADR-015 (Zero-Leakage Remote Egress), ADR-016 (Zero-LLM Tier & 7 Local Runners), ADR-017 (Interactive Prompt Elicitor & Autonomous Loop)

---

## 1. Context & Problem Statement

`ADR-017` introduced `cortical next` (`src/cortical/composers/prompt_studio.py`), giving developers an ephemeral `127.0.0.1:0` browser elicitor and a 5-Trigger autonomous confidence gate. However, re-evaluating `cortical next` and Cortical's broader value proposition revealed four usability and capability gaps for **non-developer professionals** (lawyers, financial advisors, consultants, doctors, researchers, managers) and **everyday users** who want to use AI safely on their own computers:

1. **Fragmented Disk/Folder Privatization:** `KnowledgeStore` (`src/cortical/wiki/store.py`) could crawl directories with HMAC pseudonymization, and `PrivacyVault` + `LocalBrain` (`src/cortical/privacy/`) stored 3+1 detail tiers (`light`, `medium`, `high`, `max_security`) with `SHA-256` audit chains, yet users lacked a **single one-command workflow (`cortical privatize <folder_or_drive>`)** that recursively privatizes whole folders/hard drives into an **Anonymized Second Brain** across all 4 detail tiers while calculating token savings.
2. **Developer Jargon in `cortical next`:** Adaptive questions defaulted to software-engineering terminology (`git`, `ADR`, `unittest`, `Serena`), alienating everyday users who want Cortical to act like a **plain-spoken colleague** asking 3–4 simple questions in their own language (`it` / `en`) and collecting documents/folders on the spot.
3. **Missing Cross-Document Knowledge Reconciliation & Domain Auto-Skills:** Ingesting dozens of files + Q&A clarifications requires **reconciling knowledge**—merging duplicate concepts, surfacing potential numerical/date/status discrepancies across documents, persisting user clarifications as structured Second-Brain episodes, and automatically synthesizing reusable `SKILL.md` & prompt recipes.
4. **Implicit Local-vs-Remote Escalation:** Users want to spend `$0` on local LLMs (`@role:daily_coder`, `@role:deep_reasoner`) whenever their local model is capable, and **only escalate to a remote frontier LLM** when local capability is insufficient—using an **anonymized (`_verify_zero_residual_pii`) + `TOON`-compressed packet** at the user's chosen detail tier (`light` / `medium` / `high`), while strictly blocking `max_security` items (`fail_closed`).

---

## 2. Architectural Decisions

### 2.1 Unified Second-Brain Privatizer & Reconciler (`src/cortical/privacy/second_brain.py`)
- **`privatize_second_brain(target_path, ...)`** bridges `KnowledgeStore.crawl_delta(sanitize=True)` (incremental Merkle-tracked directory/drive scan across text, `.pdf`, `.docx`, `.xlsx`, `.pptx`, and optional local vision OCR) directly into `PrivacyVault` & `LocalBrain` 3+1 detail tiers (`light`, `medium`, `high`, `max_security`):
  - **`light` (~85%+ token reduction):** 1–2 sentence executive takeaways & masked headline metrics.
  - **`medium` (~65–75% token reduction):** Structured anonymized headings, key clauses, and entities (`PERSON_01`, `ORG_01`).
  - **`high` (~25–45% token reduction):** High-fidelity pseudonymized text preserving full reasoning structure with zero raw PII.
  - **`max_security` (100% Air-Gapped):** Never included in remote packets (`fail_closed`); accessible exclusively to offline local runners.
- **`reconcile_second_brain(...)`** runs deterministic stdlib reconciliation across privatized documents and user Q&A answers:
  - **Concept Consolidation:** Merges overlapping topics via Jaccard keyword overlap into canonical Second-Brain concepts.
  - **Numeric/Date Discrepancy Detection:** Identifies shared concepts/entities where distinct documents report differing figures, percentages, or dates so the user or AI colleague can resolve them explicitly.
  - **Q&A Memory Integration:** Stores user answers/comments from Colleague Mode back into `LocalBrain` + `KnowledgeStore` episodes so the Second Brain grows smarter every session.
- **`curate_colleague_skill(...)`** compiles verified domain facts, Q&A preferences, and workflow steps into reusable zero-PII `.agents/skills/<slug>/SKILL.md` + `.cortical_data/templates/` recipes.

### 2.2 Bilingual Plain-Language "Colleague Mode" (`cortical colleague` & `cortical next --persona colleague|technical|auto`)
- **`detect_persona_and_language(seed, repo_root, persona, lang)`**:
  - Auto-detects Italian (`it`) vs English (`en`) from user text or `--lang`.
  - Selects `colleague` persona automatically when invoked via `cortical colleague`, when `--attach` points to documents/folders outside code tasks, when outside a git repo, or when `--persona colleague` is set; preserves `technical` persona for software-repo engineering loops.
- **Simple Colleague Elicitation (Zero Jargon):**
  - Asks 3–4 clear, human questions (*Concrete Goal*, *Second-Brain Detail Level (`light|medium|high|max_security`)*, *Local-First vs Anonymized Cloud Escalation*, *Save Learned Knowledge & Reusable Skill*).
  - Supports **direct file & folder collection** both via CLI (`--attach <file_or_dir>`) and inside the one-shot `127.0.0.1:0` Ephemeral Browser UI (client-side file upload sanitized immediately on loopback + local folder path privatization).

### 2.3 Local LLM Sufficiency & Safe Anonymized Remote Escalation (`evaluate_local_sufficiency`)
- Evaluates 4 deterministic factors before any remote LLM usage:
  1. **Privacy Boundary (`max_security` / `strict_local_only`):** If active, remote egress is **strictly forbidden** (`LOCAL_ONLY_REQUIRED`).
  2. **Runner & Model Availability:** Checks `resolve_active_runner_endpoint()` across all 7 supported local runners (`ollama`, `unsloth`, `lm_studio`, `llama_cpp`, `mlx_lm`, `vllm`, `openai_compatible`) and inspects configured `@role:daily_coder` / `@role:deep_reasoner` capacity.
  3. **Complexity & Token Fit:** Compares estimated context tokens + multi-document synthesis complexity against local model class (`<4B` router-only vs `7B–14B` daily vs `24B+` deep reasoner) and hardware KV budget.
  4. **Escalation Packet Construction:** When `verdict == "escalate_anonymized_remote"`, builds a `TOON`-compressed, tier-filtered (`light`/`medium`/`high`) prompt verified by `_verify_zero_residual_pii(...)` (`fail_closed`), reporting exact token savings (`%`) and estimated cloud cost saved.

---

## 3. Non-Negotiable Invariants Preserved
- **`dependencies = []`** in `pyproject.toml` (100% Python 3.10+ stdlib, zero external CDNs).
- **Zero Persistent Daemons:** Ephemeral browser sessions bind `127.0.0.1:0` with `secrets.token_urlsafe(32)`, enforce `421`/`403` `Host`/`Origin` validation, and call `server_close()` immediately in `finally`.
- **Lean 8-Tool MCP Surface:** Extends `cortical_ingest_private` (recursive directory support) and `cortical_next_prompt` (`persona`, `detail_tier`, `attach_paths`, `reconcile_brain`, `auto_curate_skill`) without adding MCP schema bloat.
