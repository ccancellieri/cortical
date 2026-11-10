# Cortical

**Autonomous Agentic Harness for `pi`, 4-Tier Deterministic Merkle/Macro-Graph Second Brain MCP, Adaptive Permission Gate & Dual-Path Voice Engine**

**Author:** Carlo Cancellieri ([GitHub](https://github.com/ccancellieri) · ORCID: `0009-0006-4092-4234`)  
**License:** Apache License 2.0 (`Apache-2.0`)  
**Platforms:** macOS (Apple Silicon Metal) & Linux (NVIDIA CUDA / Vulkan / CPU)

---

## System Architecture

```
+-----------------------------------------------------------------------------------+
|                        USER INTERACTION LAYER (CLI & VOICE)                       |
|  • Dual-Path Voice Engine (`cortical.voice`): Wake-word + Resilient Barge-in      |
|    - System 1 Reflex (<900ms): Fast Q&A, Status Checks, Voice Permission Approval |
|    - System 2 Agentic: Async background delegation to `pi` Orchestrator           |
+-----------------------------------------+-----------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                   `pi` AGENTIC HARNESS (`.pi/extensions/cortical-harness.ts`)     |
|  • Orchestrator (`delegate_subagent` / `submit_report` with bounded `maxTurns`)   |
|  • Adaptive Permission Gate (`cortical.permissions`):                             |
|    - Hard Guardrails (blocks `rm -rf /`, credential leaks, focus-stealing UI)     |
|    - Progressive Risk Learning (auto-approves recurring patterns after feedback)  |
+-------------------+-------------------------------------------+-------------------+
                    |                                           |
                    v (JSON-RPC 2.0 MCP)                        v (Deferred Skills & MCP)
+---------------------------------------+   +---------------------------------------+
|  CORTICAL SECOND BRAIN (`wiki.mcp`)   |   |   WEB & CODE AUTOMATION SUITE         |
|  • 4-Tier Deterministic Merkle Tree:  |   |  • `chrome-devtools-mcp` (Deferred)   |
|    1. `light`  (~50 tok index)        |   |  • Skill: `modern-web-guidance`       |
|    2. `medium` (~250 tok digest)      |   |    (3-Strategy SPA/React Resilience,  |
|    3. `high`   (~1000 tok synthesis)  |   |     Strict Zero Focus-Stealing)       |
|    4. `max`    (Full raw file)        |   |  • Skill: `browser-use-playwright`    |
|  • High-Level Episode Macro-Graph     |   |  • Skill: `cortical-second-brain`     |
|  • 2-Stage NLI Citation Fact-Checker  |   +---------------------------------------+
|  • Multi-Tenant Relational RBAC/ACL   |
+---------------------------------------+
```

---

## The 5 Second Brain Pillars + Hybrid Tree/Macro-Graph

1. **Parallel Deterministic Indexing (`crawler.py`):** Uses `ThreadPoolExecutor` and bottom-up `sha256` Merkle subtree hashing. Unchanged files and directories are skipped in $O(1)$.
2. **2-Stage Citation Fact-Checking (`fact_check.py`):** Verifies verbatim span containment against the raw document hash + evaluates semantic entailment (`verified` / `refuted` / `unverified`) via an NLI decision model.
3. **Multi-Tenancy (`db.py`):** Native `tenant_id` and `workspace_id` isolation in SQLite WAL (with a schema 1:1 portable to PostgreSQL).
4. **Scalability via Hybrid Merkle Tree + Macro-Graph:** Avoids $O(N^2)$ chunk graphs on thousands of documents by keeping documents in a 4-tier Merkle tree (`light`, `medium`, `high`, `max`) while maintaining a lightweight **High-Level Macro-Graph (`task_episodes` + `macro_edges`)** for cross-task episodic memory.
5. **Relational Permissions (RBAC/ACL):** Path-prefix read/write permissions (`acl_permissions`) enforced directly at SQL query time.

---

## 3-Step Quickstart

### Step 1 — Run the One-Shot Setup & Hardware Auto-Profiler
```bash
bash ./scripts/setup.sh
```
`setup.sh` creates `.venv`, runs `cortical doctor` to inspect your CPU/RAM/GPU/VRAM and auto-discover any running local inference servers (`:8080` `llama-server`, `:11434` `Ollama`, `:8081` `whisper-server`) so small laptops incur **zero extra VRAM overhead**, generates `.pi/mcp.json`, and crawls the workspace into the Second Brain.

### Step 2 — Navigate the 4-Tier Second Brain & Verify Citations
```bash
# Navigate root at 'light' depth (~50 tokens)
.venv/bin/cortical --db .cortical_data/wiki.db navigate --path / --depth light

# Escalate to 'high' or 'max' on a specific file
.venv/bin/cortical --db .cortical_data/wiki.db navigate --path /README.md --depth high

# Test the Dual-Path Voice router
.venv/bin/cortical voice-eval "Ehi Cortical, orchestra un sottoagente per analizzare il progetto"
```

### Step 3 — Run the Complete Test Suite
```bash
.venv/bin/python -m unittest discover -s tests -v
```
