"""Cortical Adaptive Skills & Prompt Intelligence Router.

Architectural Principles:
1. No Lossy Character Truncation:
   Cortical never injects arbitrary character cuts. It uses the deterministic
   3+1 Tier Wiki Memory (`light` L1, `medium` L2, `high` L3, `max` Full) in parallel with
   complete procedural Skill playbooks.
2. Full Playbook & Tool Binding:
   Matches bilingual (IT/EN) user intent, loads the full actionable steps of the top matching
   skills, binds the exact MCP/CLI tools to call, and resolves a Multi-Agent Team Roster
   (`arch_analyst`, `code_implementer`, `reviewer`, `web_researcher`).
3. Parallel Lanes (3+1 Memory vs Learned Procedural Skills):
   - Lane A: 3+1 Tier Discussion & Knowledge Memory in `CorticalWikiDB` + 3+1 Memory Synthesis Skills.
   - Lane B: Learned Procedural Skills in `.pi/skills/` + Task-Close Skill Compiler that evaluates
     completed tasks and generates reusable `SKILL.md` files when a durable pattern is learned.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from .grounding import detect_language
from .wiki.db import AccessContext, CorticalWikiDB, DepthTier

STOP_WORDS = frozenset(
    {
        "a", "about", "an", "and", "are", "can", "could", "do", "for", "from", "help",
        "how", "i", "in", "is", "me", "my", "of", "on", "or", "please", "should", "the",
        "this", "to", "use", "using", "what", "which", "with", "would", "you", "your",
        "ad", "ai", "al", "alla", "anche", "che", "come", "con", "da", "dei", "del",
        "della", "delle", "dello", "di", "e", "ed", "fa", "fare", "gli", "ha", "ho",
        "il", "in", "io", "la", "le", "lo", "ma", "mi", "nel", "nella", "non", "per",
        "piu", "più", "poi", "posso", "puoi", "quale", "quali", "questo", "questa",
        "se", "sei", "si", "sono", "su", "sul", "sulla", "ti", "tra", "un", "una",
        "uno", "vorrei", "voglio",
    }
)

# Bilingual IT -> EN concept bridge for deterministic skill & tool matching
ITALIAN_CONCEPT_BRIDGE = {
    "architettura": "architecture",
    "architetturale": "architecture",
    "browser": "browser",
    "navigazione": "browser",
    "chrome": "chrome",
    "wikipedia": "wikipedia",
    "cerca": "search",
    "ricerca": "search",
    "apri": "open",
    "form": "form",
    "compila": "fill",
    "invia": "submit",
    "focus": "focus",
    "leggi": "read",
    "leggimi": "read",
    "concetti": "concepts",
    "articolo": "article",
    "scheda": "tab",
    "pagina": "web",
    "sito": "web",
    "siti": "web",
    "meteo": "weather",
    "previsioni": "weather",
    "temperatura": "weather",
    "memoria": "memory",
    "ricorda": "memory",
    "wiki": "wiki",
    "grafo": "graph",
    "conoscenza": "knowledge",
    "sintesi": "synthesis",
    "riassunto": "synthesis",
    "riassumi": "synthesis",
    "codice": "code",
    "implementa": "implement",
    "implementare": "implement",
    "sviluppa": "implement",
    "test": "test",
    "verifica": "verify",
    "debug": "debug",
    "errore": "debug",
    "bug": "debug",
    "sicurezza": "security",
    "permessi": "permissions",
    "multiagent": "multiagent",
    "multiagente": "multiagent",
    "orchestratore": "orchestrator",
    "sottoagente": "subagent",
    "sottoagenti": "subagent",
    "agenti": "multiagent",
    "voce": "voice",
    "vocale": "voice",
}

# Specialized Multi-Agent Team Policy
MULTIAGENT_ROLES: dict[str, dict[str, Any]] = {
    "arch_analyst": {
        "name": "Architecture & Memory Analyst",
        "wiki_depth": "medium",
        "tools": ["wiki_navigate", "wiki_search", "wiki_get_knowledge_graph", "read", "grep"],
        "mission": "Mappa i moduli coinvolti usando la Wiki 3+1 (L1/L2) prima di toccare i file e identifica i vincoli architetturali.",
    },
    "code_implementer": {
        "name": "Surgical Code Implementer",
        "wiki_depth": "high",
        "tools": ["read", "edit", "write", "bash", "wiki_search"],
        "mission": "Applica modifiche chirurgiche (Karpathy Simplicity & Surgical Changes) rispettando i contratti esistenti.",
    },
    "reviewer": {
        "name": "Verification & Fact-Check Reviewer",
        "wiki_depth": "high",
        "tools": ["bash", "wiki_verify_citation", "wiki_record_episode"],
        "mission": "Esegue i test in single-shot, verifica le citazioni sulla Wiki e sintetizza le lezioni apprese.",
    },
    "web_researcher": {
        "name": "Web & Browser Grounding Specialist",
        "wiki_depth": "light",
        "tools": ["chrome_search", "chrome_read_page", "meteo_forecast", "chrome-devtools", "bash"],
        "mission": "Esegue navigazione visiva su Chrome in focus (apertura siti, compilazione form, invio ricerche), lettura/riassunto delle schede aperte e query Open-Meteo reali.",
    },
}


def normalize_text(text: str) -> str:
    norm = "".join(
        ch
        for ch in unicodedata.normalize("NFKD", text.casefold())
        if not unicodedata.combining(ch)
    )
    return re.sub(r"[^a-z0-9\s_-]", " ", norm)


def extract_terms(text: str) -> set[str]:
    out: set[str] = set()
    for word in re.findall(r"[a-z0-9_]+", normalize_text(text)):
        if word in STOP_WORDS or len(word) < 3:
            continue
        mapped = ITALIAN_CONCEPT_BRIDGE.get(word, word)
        if len(mapped) > 4 and mapped.endswith("s") and not mapped.endswith("ss"):
            mapped = mapped[:-1]
        out.add(mapped)
        out.add(word)
    return out


@dataclass
class SkillDescriptor:
    skill_id: str
    name: str
    description: str
    path: str
    kind: str  # 'core' | 'memory_tier' | 'learned'
    triggers: list[str] = field(default_factory=list)
    recommended_tools: list[str] = field(default_factory=list)
    body_excerpt: str = ""
    full_body: str = ""

    @property
    def category(self) -> str:
        return self.kind


@dataclass
class PromptEnhancementResult:
    original_prompt: str
    recommended_wiki_depth: str  # 'light' | 'medium' | 'high' | 'max'
    selected_skills: list[dict[str, Any]]
    recommended_tools: list[str]
    team_roster: list[dict[str, Any]]
    wiki_context_injected: str
    enhanced_system_instructions: str
    mode: str = "enhanced"
    memory_tier_skill: str = "cortical-memory-l2-medium"
    selected_procedural_skills: list[str] = field(default_factory=list)
    attached_context: list[dict[str, Any]] = field(default_factory=list)
    orchestrator_config: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["recommended_depth"] = self.recommended_wiki_depth
        d["context_injection"] = self.enhanced_system_instructions
        return d

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.to_dict().get(key, default)


def _extract_skill_procedure_blocks(
    discussion_steps: Optional[list[dict[str, Any]]],
) -> tuple[str, list[str], list[str]]:
    """Extracts structured procedure lines, touched paths, and verified commands from execution steps."""
    steps = list(discussion_steps or [])
    proc_lines: list[str] = []
    touched_files: list[str] = []
    verified_cmds: list[str] = []

    for idx, st in enumerate(steps[:8], start=1):
        title = str(st.get("title") or st.get("tool") or "Step").strip()
        detail = re.sub(r"\s+", " ", str(st.get("detail") or "")).strip()
        meta = st.get("meta") if isinstance(st.get("meta"), dict) else {}
        cmd = str(meta.get("command") or st.get("command") or "").strip()
        fpath = str(meta.get("path") or st.get("path") or "").strip()

        if fpath and fpath not in touched_files:
            touched_files.append(fpath)
        if cmd and cmd not in verified_cmds and not meta.get("is_error"):
            verified_cmds.append(cmd)

        if detail and detail.lower() != title.lower():
            proc_lines.append(f"{idx}. **{title}** — {detail[:180]}")
        elif fpath:
            proc_lines.append(f"{idx}. **{title}** — `{fpath}`")
        elif cmd:
            proc_lines.append(f"{idx}. **{title}** — `{cmd}`")
        else:
            proc_lines.append(f"{idx}. {title}")

    proc_text = (
        "\n".join(proc_lines)
        if proc_lines
        else "1. Consulta la Wiki MCP a livello `medium`.\n2. Applica il pattern verificato.\n3. Verifica con test single-shot."
    )
    return (proc_text, touched_files[:8], verified_cmds[:5])


_KNOWLEDGE_DOMAIN_MAP: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("concept:merkle-context-compression", ("merkle", "wiki", "fts5", "subtree", "tier", "crawl", "readme", "contesto")),
    ("concept:local-privacy-gdpr-sanitizer", ("privacy", "gdpr", "sanitizer", "anonym", "pseudonym", "metadata", "redact")),
    ("concept:zero-token-roi-analytics", ("token", "analytics", "roi", "transcript", "cost", "cache", "report", "savings")),
    ("concept:local-llm-runner-autoscaler", ("ollama", "runner", "llama", "mlx", "context_window", "num_ctx", "vram", "model")),
    ("concept:adaptive-permission-gate", ("permission", "rbac", "acl", "gate", "security", "bash", "sandbox")),
    ("concept:cortical-modular-architecture", ("cortical", "config", "unittest", "architecture", "architettura", "settings", "module")),
)


def _infer_knowledge_concepts(
    text: str,
    touched_files: list[str],
    wiki_db: CorticalWikiDB,
    ctx: AccessContext,
) -> dict[str, Any]:
    """Maps skill text & touched files to canonical Knowledge Concepts, Wiki Nodes & Memory Insights."""
    hay = f"{text} {' '.join(touched_files)}".lower()
    concepts: list[str] = []
    for cid, kws in _KNOWLEDGE_DOMAIN_MAP:
        if any(k in hay for k in kws):
            concepts.append(cid)
    if not concepts:
        concepts.append("concept:cortical-modular-architecture")

    terms = extract_terms(hay)
    wiki_paths: list[str] = []
    insight_refs: list[tuple[str, str]] = []
    with wiki_db._connect() as conn:
        for fp in touched_files:
            norm_p = "/" + fp.lstrip("/")
            row = conn.execute(
                "SELECT path FROM merkle_nodes WHERE tenant_id = ? AND workspace_id = ? AND (path = ? OR path LIKE ?)",
                (ctx.tenant_id, ctx.workspace_id, norm_p, f"%{fp.lstrip('/')}"),
            ).fetchone()
            wp = str(row["path"]) if row else norm_p
            if wp not in wiki_paths:
                wiki_paths.append(wp)

        if len(wiki_paths) < 5 and terms:
            try:
                rows = conn.execute(
                    """SELECT path, summary_light FROM merkle_nodes
                       WHERE tenant_id = ? AND workspace_id = ? AND node_type = 'file' LIMIT 120""",
                    (ctx.tenant_id, ctx.workspace_id),
                ).fetchall()
                scored_nodes: list[tuple[int, str]] = []
                for r in rows:
                    p = str(r["path"])
                    nt = extract_terms(f"{p} {r['summary_light']}")
                    ov = len(terms & nt)
                    if ov >= 2:
                        scored_nodes.append((ov, p))
                scored_nodes.sort(key=lambda x: x[0], reverse=True)
                for _, p in scored_nodes[:5]:
                    if p not in wiki_paths:
                        wiki_paths.append(p)
            except Exception:  # noqa: BLE001
                pass

        try:
            irows = conn.execute(
                """SELECT insight_id, insight_text FROM memory_insights
                   WHERE tenant_id = ? AND workspace_id = ? ORDER BY created_at DESC LIMIT 80""",
                (ctx.tenant_id, ctx.workspace_id),
            ).fetchall()
            scored_ins: list[tuple[int, str, str]] = []
            for r in irows:
                itxt = str(r["insight_text"] or "")
                ov = len(terms & extract_terms(itxt))
                if ov >= 2:
                    scored_ins.append((ov, str(r["insight_id"]), itxt[:160]))
            scored_ins.sort(key=lambda x: x[0], reverse=True)
            insight_refs = [(iid, txt) for _, iid, txt in scored_ins[:4]]
        except Exception:  # noqa: BLE001
            pass

    return {
        "concepts": concepts[:4],
        "wiki_paths": wiki_paths[:6],
        "insights": insight_refs,
    }


@dataclass
class SkillEvaluationResult:
    episode_id: str
    should_create_skill: bool
    reason: str
    skill_id: Optional[str] = None
    skill_path: Optional[str] = None
    skill_markdown: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["created"] = self.should_create_skill
        return d

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.to_dict().get(key, default)


class CorticalSkillHub:
    """Manages parallel 3+1 Memory Synthesis Skills, Learned Skills, and Prompt Enhancement."""

    def __init__(
        self,
        wiki_db: CorticalWikiDB,
        skills_root: str | Path,
        llm_fn: Optional[Callable[[str], str]] = None,
    ) -> None:
        self.wiki_db = wiki_db
        self.skills_root = Path(skills_root)
        self.skills_root.mkdir(parents=True, exist_ok=True)
        self.llm_fn = llm_fn
        self._ensure_builtin_memory_and_orchestrator_skills()
        self._ensure_db_tables()

    def _ensure_db_tables(self) -> None:
        with self.wiki_db._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS learned_skills_registry (
                    skill_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    skill_path TEXT NOT NULL,
                    source_episode_id TEXT NOT NULL,
                    use_count INTEGER NOT NULL DEFAULT 0,
                    helpful_count INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS task_discussion_synthesis (
                    episode_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    tier_l1_light TEXT NOT NULL,
                    tier_l2_medium TEXT NOT NULL,
                    tier_l3_high TEXT NOT NULL,
                    tier_max_raw TEXT NOT NULL,
                    lessons_learned TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );
                """
            )

    def _ensure_builtin_memory_and_orchestrator_skills(self) -> None:
        """Creates the 3+1 Memory Synthesis Skills & Multi-Agent Orchestrator Skill in `.pi/skills/`."""
        builtin_skills = {
            "cortical-memory-l1-light": (
                "--- \n"
                "name: cortical-memory-l1-light\n"
                "description: Sintesi Memoria Livello 1 (LIGHT ~50 token) tramite MCP Wiki. Usa per orientamento rapido sull'albero del progetto e indice delle discussioni senza appesantire il contesto.\n"
                "---\n\n"
                "# Cortical Memory L1 — Light Synthesis (~50 token)\n\n"
                "## Quando usarla\n"
                "- All'inizio di una richiesta esplorativa o per orientarsi rapidamente tra i moduli.\n\n"
                "## Procedura Operativa (Tramite MCP `cortical-wiki`)\n"
                "1. Invoca `wiki_navigate(path='/', depth='light')` per ottenere l'indice compatto.\n"
                "2. Per sintetizzare una discussione a Livello 1, produci **1 sola frase esecutiva** con: *Obiettivo + Esito + File principale toccato*.\n"
            ),
            "cortical-memory-l2-medium": (
                "---\n"
                "name: cortical-memory-l2-medium\n"
                "description: Sintesi Memoria Livello 2 (MEDIUM ~250 token) tramite MCP Wiki. Usa per comprendere architettura, firme delle funzioni, decisioni chiave e relazioni tra task.\n"
                "---\n\n"
                "# Cortical Memory L2 — Medium Structural Synthesis (~250 token)\n\n"
                "## Quando usarla\n"
                "- Default per task di sviluppo, refactoring e coordinamento multi-agente.\n\n"
                "## Procedura Operativa (Tramite MCP `cortical-wiki`)\n"
                "1. Invoca `wiki_search(query='<tema>', depth='medium')` e `wiki_navigate(path='<modulo>', depth='medium')`.\n"
                "2. Per sintetizzare una discussione a Livello 2, struttura:\n"
                "   - **Intento & Decisioni Architetturali**\n"
                "   - **Moduli & API Coinvolte**\n"
                "   - **Stato Attuale & Prossimi Passi**\n"
            ),
            "cortical-memory-l3-high": (
                "---\n"
                "name: cortical-memory-l3-high\n"
                "description: Sintesi Memoria Livello 3+1 (HIGH ~1000 token + MAX verbatim) tramite MCP Wiki. Usa per debugging profondo, verifica citazioni NLI e lezioni tecniche complete.\n"
                "---\n\n"
                "# Cortical Memory L3 (+1 Max) — Deep Technical Synthesis (~1000 token)\n\n"
                "## Quando usarla\n"
                "- Quando serve il dettaglio implementativo completo, la root-cause di un bug o la verifica esatta del codice (`depth='high'` o `depth='max'`).\n\n"
                "## Procedura Operativa (Tramite MCP `cortical-wiki`)\n"
                "1. Invoca `wiki_navigate(path='<file>', depth='high')` (o `depth='max'` per il sorgente integrale senza tagli lossy).\n"
                "2. Verifica sempre i claim critici con `wiki_verify_citation` prima di modificare contratti core.\n"
                "3. A fine task, consolida i 3+1 livelli con `wiki_record_episode` e valuta se estrarre una nuova Skill procedurale.\n"
            ),
            "cortical-multiagent-orchestrator": (
                "---\n"
                "name: cortical-multiagent-orchestrator\n"
                "description: Orchestratore Multi-Agente locale per pi e Cortical. Coordina Analyst, Implementer e Reviewer solo quando l'utente apre un task esplicito, salvando la discussione nei 3+1 livelli della Wiki e generando nuove skill.\n"
                "---\n\n"
                "# Cortical Multi-Agent Orchestrator\n\n"
                "## Regole Fondamentali (Karpathy Guidelines & Cortical 3+1)\n"
                "1. **Zero Task Automatici:** Non aprire un task per domande conversazionali o rapide. Apri un task solo su richiesta esplicita (`/task <obiettivo>` o `'crea un task...'`).\n"
                "2. **Niente Tagli Lossy:** Usa i livelli `light` -> `medium` -> `high` -> `max` della Wiki MCP invece di troncare i file a metà.\n"
                "3. **Flusso Multi-Agente in 3 Fasi:**\n"
                "   - **Fase 1 (`arch_analyst`):** Legge la Wiki MCP a livello `light`/`medium` e identifica i file esatti.\n"
                "   - **Fase 2 (`code_implementer`):** Legge i file target a livello `high`/`max` ed esegue modifiche chirurgiche.\n"
                "   - **Fase 3 (`reviewer`):** Esegue i test in single-shot, salva la sintesi a 3+1 livelli della discussione e valuta se creare una nuova Skill per il futuro.\n"
            ),
            "ai-reviewer-mandate-and-complexity": (
                "---\n"
                "name: ai-reviewer-mandate-and-complexity\n"
                "description: Mandato del revisore di codice AI e metriche di complessità oggettive (Cicli < 10, Complessità Cognitiva < 15, LOC 20-50). Previene debito tecnico, over-generation e falsa sicurezza da codice superficialmente pulito.\n"
                "---\n\n"
                "# Mandato del Revisore di Codice AI & Metriche di Complessità\n\n"
                "## 1. Il Nuovo Mandato del Revisore (Reviewer Mandate Shift)\n"
                "Il ruolo del revisore non è catturare bug ovvi di sintassi, ma verificare che il codice sia corretto per questa specifica codebase, a questa scala e per il business.\n\n"
                "## 2. Metriche Standard di Complessità delle Funzioni\n"
                "- **Cyclomatic Complexity:** < 10 per funzione (percorsi lineari esecuzione).\n"
                "- **Cognitive Complexity:** < 15 per funzione (difficoltà di lettura per la mente umana).\n"
                "- **Lines of Code (LOC):** < 20-50 righe (Single Responsibility Principle).\n"
            ),
            "pr-contract-and-diff-constrainer": (
                "---\n"
                "name: pr-contract-and-diff-constrainer\n"
                "description: Vincoli di dimensione delle PR, contratti di review e Golden Rule della contribuzione. Impone diff microscopici per codice AI, convenzioni di titolo/descrizione e scomposizione (questo potrebbe essere 3 PR).\n"
                "---\n\n"
                "# Contratti di Pull Request & Vincoli della Dimensione di Review\n\n"
                "## 1. La Regola Aurea del Progetto (Golden Rule)\n"
                "Una contribuzione deve valere più del tempo che serve per revisionarla.\n\n"
                "## 2. Costringere l'Unità di Revisione (Constrain the Unit of Review)\n"
                "- Cap diff size: max 150-250 righe di diff effettivo.\n"
                "- Files touched: max 3-5 file per PR.\n"
                "- Zero modifiche non correlate: un solo intento per PR.\n"
                "- Forzare la conversazione: se supera la dimensione, valutare se sdoppiare in 3 PR.\n"
                "- Pair programming: prima linea di difesa.\n"
            ),
            "agent-instructions-alignment": (
                "---\n"
                "name: agent-instructions-alignment\n"
                "description: Allineamento Zero-Drift tra istruzioni per agenti AI e standard di review. Mantiene file esterni condivisi (AGENTS.md) per standardizzare le norme del team, eliminando prompt ripetitivi e allineando generazione e verifica.\n"
                "---\n\n"
                "# Allineamento Istruzioni Agenti & Standard di Review (Single Artifact Zero-Drift)\n\n"
                "## 1. Il Principio del Singolo Artefatto (One Artifact, No Drift)\n"
                "Le istruzioni date all'agente sono il tuo standard di review. Il file che dice come scrivere codice è lo stesso che definisce come viene revisionato.\n\n"
                "## 2. File Esterni Condivisi (AGENTS.md)\n"
                "Standardizza ciò che l'AI sa sulle norme del team tra diverse sessioni di chat, prevenendo prompt ripetitivi.\n"
            ),
            "visual-chrome-navigation": (
                "---\n"
                "name: visual-chrome-navigation\n"
                "description: Navigazione visiva interattiva su Google Chrome in primo piano (focus) con apertura siti (Wikipedia, Google, YouTube, GitHub), compilazione DOM dei form di ricerca, invio della query e lettura/riassunto concettuale della pagina aperta.\n"
                "---\n\n"
                "# Visual Chrome Navigation, Form Filling & Page Reader\n\n"
                "## Quando usarla\n"
                "- Quando l'utente chiede esplicitamente di aprire il browser/Chrome, andare su un sito (es. Wikipedia), compilare la ricerca e mostrare il risultato in primo piano (`focus`).\n"
                "- Quando in un turno successivo l'utente chiede di leggere o riassumere i concetti della pagina aperta.\n\n"
                "## Procedura Operativa\n"
                "1. Usa `chrome_search(site='wikipedia', query='<termine>', focus=True)` per portare Google Chrome in primo piano, aprire la scheda del sito, compilare il campo di ricerca nel DOM e inviare il form.\n"
                "2. In un turno successivo, se l'utente chiede 'leggi' o 'riassumi i concetti della pagina aperta', invoca `chrome_read_page(mode='summarize'|'read')` per estrarre titolo, sezioni e testo pulito dalla scheda attiva di Chrome e sintetizzarli in italiano.\n"
            ),
        }
        for slug, content in builtin_skills.items():
            sdir = self.skills_root / slug
            sdir.mkdir(parents=True, exist_ok=True)
            sfile = sdir / "SKILL.md"
            if not sfile.exists():
                sfile.write_text(content, encoding="utf-8")

    def list_skills(self) -> list[SkillDescriptor]:
        """Scans `.pi/skills/*/SKILL.md` and returns structured descriptors."""
        descriptors: list[SkillDescriptor] = []
        for skill_md in sorted(self.skills_root.glob("*/SKILL.md")):
            raw = skill_md.read_text(encoding="utf-8")
            slug = skill_md.parent.name
            name = slug
            desc = ""
            body = raw
            if raw.startswith("---"):
                end = raw.find("\n---", 3)
                if end != -1:
                    fm = raw[3:end]
                    body = raw[end + 4 :].strip()
                    fm_lines = fm.splitlines()
                    desc_lines: list[str] = []
                    in_desc = False
                    for line in fm_lines:
                        if line.startswith("name:"):
                            in_desc = False
                            name = line.split(":", 1)[1].strip()
                        elif line.startswith("description:"):
                            val = line.split(":", 1)[1].strip()
                            if val in {">", "|", ">-", "|-", ""}:
                                in_desc = True
                            else:
                                in_desc = False
                                desc = val
                        elif in_desc and (line.startswith(" ") or line.startswith("\t")):
                            desc_lines.append(line.strip())
                        else:
                            in_desc = False
                    if desc_lines and not desc:
                        desc = " ".join(desc_lines)
            kind = "core"
            if slug.startswith("cortical-memory-"):
                kind = "memory_tier"
            elif slug.startswith("learned-"):
                kind = "learned"

            tools_map = {
                "cortical-second-brain": ["wiki_navigate", "wiki_search", "wiki_record_episode"],
                "cortical-memory-l1-light": ["wiki_navigate"],
                "cortical-memory-l2-medium": ["wiki_navigate", "wiki_search"],
                "cortical-memory-l3-high": ["wiki_navigate", "wiki_verify_citation", "wiki_record_episode"],
                "cortical-multiagent-orchestrator": ["delegate_subagent", "submit_report", "wiki_navigate"],
                "ai-reviewer-mandate-and-complexity": ["wiki_search", "wiki_verify_citation", "bash"],
                "pr-contract-and-diff-constrainer": ["wiki_search", "bash", "delegate_subagent"],
                "agent-instructions-alignment": ["wiki_navigate", "wiki_search", "submit_report"],
                "modern-web-guidance": ["meteo_forecast", "chrome-devtools"],
                "browser-use-playwright": ["meteo_forecast", "chrome-devtools", "bash"],
                "visual-chrome-navigation": ["chrome_search", "chrome_read_page", "chrome-devtools", "bash"],
            }
            descriptors.append(
                SkillDescriptor(
                    skill_id=slug,
                    name=name,
                    description=desc or body.splitlines()[0] if body else slug,
                    path=str(skill_md),
                    kind=kind,
                    triggers=sorted(extract_terms(f"{name} {desc}")),
                    recommended_tools=tools_map.get(slug, ["wiki_search", "bash"]),
                    body_excerpt=body[:420],
                    full_body=body,
                )
            )
        return descriptors

    def rank_skills_for_prompt(self, prompt: str, limit: int = 3) -> list[tuple[SkillDescriptor, int]]:
        """Deterministic bilingual (IT/EN) skill matcher that abstains on unrelated prompts."""
        q_terms = extract_terms(prompt)
        norm_p = prompt.lower()
        all_skills = self.list_skills()
        ranked: list[tuple[SkillDescriptor, int]] = []

        # Explicit $skill_name mention
        explicit = {m.lower() for m in re.findall(r"\$([a-zA-Z0-9_-]+)", prompt)}

        for sk in all_skills:
            score = 0
            if sk.skill_id.lower() in explicit or sk.name.lower() in explicit:
                score += 10_000

            name_terms = extract_terms(sk.name)
            desc_terms = extract_terms(sk.description)
            body_terms = extract_terms(sk.body_excerpt)

            name_hits = q_terms & name_terms
            desc_hits = q_terms & desc_terms
            body_hits = q_terms & body_terms

            score += 1200 * len(name_hits) + 250 * len(desc_hits) + 40 * len(body_hits)

            # Domain intent boosts
            if any(
                w in norm_p
                for w in ("browser", "chrome", "wikipedia", "apri", "cerca", "ricerca", "pagina aperta", "scheda aperta", "leggi")
            ) and sk.skill_id == "visual-chrome-navigation":
                score += 2200
            if any(w in norm_p for w in ("meteo", "chrome", "browser", "web", "cerca")) and sk.skill_id in {
                "modern-web-guidance",
                "browser-use-playwright",
            }:
                score += 1500
            if any(w in norm_p for w in ("multiagent", "orchestra", "task", "sottoagente", "agenti")) and sk.skill_id in {
                "cortical-multiagent-orchestrator",
                "cortical-second-brain",
            }:
                score += 1600
            if any(w in norm_p for w in ("wiki", "memoria", "conoscenza", "grafo", "sintesi", "riassumi")) and (
                sk.kind == "memory_tier" or sk.skill_id == "cortical-second-brain"
            ):
                score += 1400

            if score >= 250:
                ranked.append((sk, score))

        ranked.sort(key=lambda item: (-item[1], item[0].skill_id))
        return ranked[:limit]

    def discover_skills(self) -> list[SkillDescriptor]:
        """Alias for `list_skills()`."""
        return self.list_skills()

    def list_learned_skills(self, ctx: Optional[AccessContext] = None) -> list[dict[str, Any]]:
        access_ctx = ctx or AccessContext()
        with self.wiki_db._connect() as conn:
            rows = conn.execute(
                """SELECT skill_id, name, description, skill_path, source_episode_id, use_count, helpful_count, created_at
                   FROM learned_skills_registry
                   WHERE tenant_id = ? AND workspace_id = ?
                   ORDER BY created_at DESC""",
                (access_ctx.tenant_id, access_ctx.workspace_id),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_task_syntheses(self, limit: int = 15, ctx: Optional[AccessContext] = None) -> list[dict[str, Any]]:
        access_ctx = ctx or AccessContext()
        with self.wiki_db._connect() as conn:
            rows = conn.execute(
                """SELECT episode_id, tier_l1_light, tier_l2_medium, tier_l3_high, lessons_learned, updated_at
                   FROM task_discussion_synthesis
                   WHERE tenant_id = ? AND workspace_id = ?
                   ORDER BY updated_at DESC LIMIT ?""",
                (access_ctx.tenant_id, access_ctx.workspace_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def choose_wiki_depth(self, prompt: str) -> DepthTier:
        """Selects the optimal 3+1 memory tier (L1 light, L2 medium, L3 high, +1 max) for the prompt."""
        norm = prompt.lower()
        if any(w in norm for w in ("codice completo", "raw", "intero file", "max", "verbatim", "linea per linea")):
            return DepthTier.MAX
        if any(
            w in norm
            for w in (
                "debug", "bug", "errore", "implementa", "modifica", "test", "dettaglio", "high",
                "rifattorizza", "refactor", "sicurezza", "rbac", "citazioni",
            )
        ):
            return DepthTier.HIGH
        if any(w in norm for w in ("panoramica", "indice", "veloce", "light", "elenco")):
            return DepthTier.LIGHT
        return DepthTier.MEDIUM

    def resolve_team_roster(self, prompt: str) -> list[dict[str, Any]]:
        """Returns the specialized multi-agent team roster for the given task."""
        norm = prompt.lower()
        if any(w in norm for w in ("meteo", "chrome", "browser", "web", "sito")):
            return [
                {"id": "web_researcher", **MULTIAGENT_ROLES["web_researcher"]},
                {"id": "reviewer", **MULTIAGENT_ROLES["reviewer"]},
            ]
        if any(w in norm for w in ("implementa", "codice", "aggiungi", "fix", "bug", "crea", "sviluppa", "rifattorizza", "refactor")):
            return [
                {"id": "arch_analyst", **MULTIAGENT_ROLES["arch_analyst"]},
                {"id": "code_implementer", **MULTIAGENT_ROLES["code_implementer"]},
                {"id": "reviewer", **MULTIAGENT_ROLES["reviewer"]},
            ]
        return [
            {"id": "arch_analyst", **MULTIAGENT_ROLES["arch_analyst"]},
            {"id": "reviewer", **MULTIAGENT_ROLES["reviewer"]},
        ]

    def enhance_prompt(
        self,
        prompt: str,
        ctx: Optional[AccessContext] = None,
        active_episode_id: Optional[str] = None,
        scope_id: str = "chat",
    ) -> PromptEnhancementResult:
        """Enhances a user prompt with Scoped Attached Context (Files/Folders/Skills/Plugins) + 3+1 Wiki Memory + matched Skills & Orchestrator Config."""
        access_ctx = ctx or AccessContext()
        effective_scope = active_episode_id or scope_id or "chat"
        depth = self.choose_wiki_depth(prompt)
        matched = self.rank_skills_for_prompt(prompt, limit=3)

        # Load live framework concept configurations
        orch_cfg = self.wiki_db.get_concept_config(access_ctx, "concept:orchestratore-multi-agente")
        brain_cfg = self.wiki_db.get_concept_config(access_ctx, "concept:cortical-second-brain")

        # Load scoped attachments for the current chat/task scope
        attachments = self.wiki_db.list_context_attachments(access_ctx, scope_id=effective_scope)
        if effective_scope != "chat":
            chat_atts = self.wiki_db.list_context_attachments(access_ctx, scope_id="chat")
            seen_att_ids = {a["attachment_id"] for a in attachments}
            for ca in chat_atts:
                if ca["attachment_id"] not in seen_att_ids:
                    attachments.append(ca)

        # Always include the matching 3+1 Memory Tier skill in parallel with domain skills
        tier_skill_map = {
            DepthTier.LIGHT: "cortical-memory-l1-light",
            DepthTier.MEDIUM: "cortical-memory-l2-medium",
            DepthTier.HIGH: "cortical-memory-l3-high",
            DepthTier.MAX: "cortical-memory-l3-high",
        }
        target_tier_skill = tier_skill_map[depth]
        all_available_skills = self.list_skills()
        selected_skills = [sk for sk, _ in matched]

        # Force-activate any skill explicitly attached by the user to this chat/task
        for att in attachments:
            if att.get("item_type") == "skill":
                ref_low = str(att.get("item_ref", "")).lower()
                lbl_low = str(att.get("label", "")).lower()
                for sk in all_available_skills:
                    if sk.skill_id.lower() in {ref_low, lbl_low} or sk.name.lower() in {ref_low, lbl_low}:
                        if not any(s.skill_id == sk.skill_id for s in selected_skills):
                            selected_skills.insert(0, sk)

        if not any(s.skill_id == target_tier_skill for s in selected_skills):
            for s in all_available_skills:
                if s.skill_id == target_tier_skill:
                    selected_skills.append(s)
                    break

        tools: list[str] = []
        for s in selected_skills:
            for t in s.recommended_tools:
                if t not in tools:
                    tools.append(t)

        # Include any explicitly attached plugin/MCP tool in recommended_tools
        for att in attachments:
            if att.get("item_type") == "plugin":
                plug_ref = str(att.get("item_ref") or att.get("label"))
                if plug_ref and plug_ref not in tools:
                    tools.append(plug_ref)

        # Build Attached Context Block (Files, Folders, Skills, Plugins explicitly added by the user)
        attached_blocks: list[str] = []
        if brain_cfg.get("auto_attach_chat_context", True) and attachments:
            for att in attachments:
                itype = att.get("item_type", "file")
                ilabel = att.get("label", att.get("item_ref", ""))
                itier = att.get("depth_tier", depth.value)
                wpaths = att.get("metadata", {}).get("wiki_paths", [])
                if itype in {"file", "folder"} and wpaths:
                    for wp in wpaths[:6]:
                        try:
                            nav = self.wiki_db.navigate(access_ctx, path=wp, depth=itier, include_children=False)
                            attached_blocks.append(
                                f"### [ALLEGATO {itype.upper()} ({itier.upper()})] {ilabel} (`{wp}`)\n{nav.get('content', att.get('summary_preview', ''))}"
                            )
                        except Exception:
                            attached_blocks.append(
                                f"### [ALLEGATO {itype.upper()}] {ilabel}\n{att.get('summary_preview', '')}"
                            )
                else:
                    attached_blocks.append(
                        f"### [ALLEGATO {itype.upper()}] {ilabel} (`{att.get('item_ref', '')}`)\n{att.get('summary_preview', '')}"
                    )

        # Resolve any explicit @wiki:/@concept:/@skill:/@insight:/@task:/@root: or cortical:// references
        resolved_refs = self.resolve_wiki_references(prompt, default_tier=depth.value, ctx=access_ctx)

        # Fetch non-lossy 3+1 Wiki context at the chosen tier
        hits = self.wiki_db.search(access_ctx, query=prompt, depth=depth, limit=3)
        wiki_sections: list[str] = []
        if resolved_refs.get("context_markdown"):
            wiki_sections.append(resolved_refs["context_markdown"])
        if attached_blocks:
            wiki_sections.extend(attached_blocks)
        if hits:
            wiki_sections.extend(
                f"### [Wiki {h['depth_tier'].upper()}] {h['path']}\n{h['content']}"
                for h in hits
            )
        if not wiki_sections:
            wiki_block = "Nessun file o cartella allegata a questa conversazione (usa '+ Aggiungi al Contesto' per allegare file, cartelle, skill o plugin)."
        else:
            wiki_block = "\n\n".join(wiki_sections)

        team_roster = self.resolve_team_roster(prompt)
        role_model_map = {
            "arch_analyst": orch_cfg.get("analyst_model", "qwen2.5:1.5b"),
            "web_researcher": orch_cfg.get("analyst_model", "qwen2.5:1.5b"),
            "code_implementer": orch_cfg.get("implementer_model", "qwen2.5:1.5b"),
            "reviewer": orch_cfg.get("reviewer_model", "qwen2.5:1.5b"),
        }
        max_loops = int(orch_cfg.get("max_agent_loops", 6))
        for r in team_roster:
            r["model"] = role_model_map.get(r["id"], orch_cfg.get("implementer_model", "qwen2.5:1.5b"))
            r["max_loops"] = max_loops

        skills_playbook = "\n\n".join(
            f"#### Skill Attiva: `{s.name}` ({s.kind})\n{s.full_body[:900]}"
            for s in selected_skills[:4]
        )
        roster_text = "\n".join(
            f"- **{r['name']}** [Modello: `{r['model']}`, Max Loop: `{r['max_loops']}`, Wiki: `{r['wiki_depth']}`, Tools: `{', '.join(r['tools'])}`]: {r['mission']}"
            for r in team_roster
        )

        req_lang = detect_language(prompt)
        lang_rule = (
            "Always reply in clear, technically rigorous English."
            if req_lang == "en"
            else "Always reply in the EXACT same language as the user's prompt (e.g. Italian, Spanish, etc.) with technical rigor. Keep core tool/framework identifiers in English; learned discussion skills may use the conversation's language."
        )
        enhanced_instructions = (
            f"=== CORTICAL HARNESS — Multi-Agent Orchestrator & 3+1 Second Brain ===\n"
            f"{lang_rule} (detected={req_lang})\n"
            f"Configurazione Orchestratore: Max Loop Agenti = {max_loops} | Modelli = Analyst({role_model_map['arch_analyst']}), Implementer({role_model_map['code_implementer']}), Reviewer({role_model_map['reviewer']}).\n\n"
            f"=== 1. CONTESTO SPECIFICO ALLEGATO & WIKI (Livello 3+1: {depth.value.upper()}) ===\n"
            f"{wiki_block}\n\n"
            f"=== 2. SKILL PROCEDURALI ATTIVATE IN PARALLELO ===\n"
            f"{skills_playbook}\n\n"
            f"=== 3. TOOL & RUOLI MULTI-AGENTE CONFIGURATI ===\n"
            f"Tool/Plugin attivi: {', '.join(tools)}\n"
            f"{roster_text}\n"
        )

        proc_names = [s.name for s in selected_skills if s.kind != "memory_tier"]
        learned_ids = [s.skill_id for s in selected_skills if s.skill_id.startswith("learned-")]
        if learned_ids:
            self.record_skill_usage(learned_ids, helpful=True, ctx=access_ctx)
        return PromptEnhancementResult(
            original_prompt=prompt,
            recommended_wiki_depth=depth.value,
            selected_skills=[
                {
                    "skill_id": s.skill_id,
                    "name": s.name,
                    "kind": s.kind,
                    "description": s.description,
                    "recommended_tools": s.recommended_tools,
                }
                for s in selected_skills
            ],
            recommended_tools=tools,
            team_roster=team_roster,
            wiki_context_injected=wiki_block,
            enhanced_system_instructions=enhanced_instructions,
            mode="enhanced",
            memory_tier_skill=target_tier_skill,
            selected_procedural_skills=proc_names,
            attached_context=attachments,
            orchestrator_config=orch_cfg,
        )

    def _load_episode_and_steps(
        self,
        episode_id: str,
        access_ctx: AccessContext,
        goal: str = "",
        discussion_steps: Optional[list[dict[str, Any]]] = None,
    ) -> tuple[str, list[dict[str, Any]]]:
        resolved_goal = goal
        resolved_steps = list(discussion_steps or [])
        with self.wiki_db._connect() as conn:
            if not resolved_goal:
                ep = conn.execute(
                    "SELECT title, goal, learned_summary FROM task_episodes WHERE episode_id = ? AND tenant_id = ? AND workspace_id = ?",
                    (episode_id, access_ctx.tenant_id, access_ctx.workspace_id),
                ).fetchone()
                if ep:
                    resolved_goal = str(ep["goal"] or ep["title"] or episode_id)
            if not resolved_steps:
                try:
                    notes = conn.execute(
                        "SELECT step_type, title, detail FROM task_isolated_notes WHERE episode_id = ? AND tenant_id = ? AND workspace_id = ? ORDER BY note_id ASC",
                        (episode_id, access_ctx.tenant_id, access_ctx.workspace_id),
                    ).fetchall()
                    resolved_steps = [
                        {
                            "type": str(r["step_type"] or "step"),
                            "title": str(r["title"] or r["detail"])[:80],
                            "detail": str(r["detail"]),
                        }
                        for r in notes
                    ]
                except Exception:  # noqa: BLE001
                    resolved_steps = []
        return (resolved_goal or episode_id, resolved_steps)

    def synthesize_task_discussion_3plus1(
        self,
        episode_id: str,
        goal: str = "",
        discussion_steps: Optional[list[dict[str, Any]]] = None,
        user_closing_notes: str = "",
        ctx: Optional[AccessContext] = None,
        use_local_llm: bool = False,
        llm_fn: Optional[Callable[[str], str]] = None,
    ) -> dict[str, str]:
        """Synthesizes a task's discussion at 3+1 levels (L1 Light, L2 Medium, L3 High, +1 Max), optionally refined by local LLM."""
        access_ctx = ctx or AccessContext()
        # Handle 2-arg call `synthesize_task_discussion_3plus1(ep_id, notes)`
        if goal and discussion_steps is None and not user_closing_notes:
            user_closing_notes = goal
            goal = ""
        resolved_goal, resolved_steps = self._load_episode_and_steps(
            episode_id, access_ctx, goal=goal, discussion_steps=discussion_steps
        )
        raw_lines = [f"# Task {episode_id}: {resolved_goal}"]
        for st in resolved_steps:
            raw_lines.append(f"- [{st.get('type', 'step').upper()}] {st.get('title', '')}: {st.get('detail', '')}")
        if user_closing_notes:
            raw_lines.append(f"\n## Note Finali & Lezioni Apprese\n{user_closing_notes}")
        tier_max = "\n".join(raw_lines)

        lessons = user_closing_notes.strip() or (
            resolved_steps[-1].get("detail", "")[:180] if resolved_steps else resolved_goal
        )
        lessons_clean = re.sub(r"\s+", " ", lessons).strip()[:200]
        tier_l1 = f"[L1 LIGHT] Task '{resolved_goal[:70]}' completato. Lezione chiave: {lessons_clean}"

        step_titles = [f"• {st.get('title', '')}" for st in resolved_steps[:6] if st.get("title")]
        tier_l2 = (
            f"[L2 MEDIUM] Task {episode_id} — Obiettivo: {resolved_goal}\n"
            f"Passaggi eseguiti ({len(resolved_steps)} totali):\n"
            + ("\n".join(step_titles) if step_titles else "• Esecuzione diretta")
            + f"\nLezione consolidata: {lessons_clean}"
        )

        detailed_steps = [
            f"### Step {i+1}: {st.get('title', '')}\n{str(st.get('detail', ''))[:300]}"
            for i, st in enumerate(resolved_steps[:8])
        ]
        tier_l3 = (
            f"[L3 HIGH] Sintesi Tecnica Completa — Task {episode_id}\n"
            f"Obiettivo: {resolved_goal}\n\n"
            + "\n\n".join(detailed_steps)
            + f"\n\n### Lezioni Apprese\n{lessons_clean}"
        )

        if use_local_llm or llm_fn is not None:
            try:
                from .config import invoke_configured_runner

                synth_prompt = (
                    "Synthesize this engineering discussion into strict JSON with keys `light` (<=35 words), "
                    "`medium` (<=140 words), and `high` (<=320 words), highlighting durable architectural lessons:\n\n"
                    + tier_max[:3200]
                )
                raw_resp = (
                    llm_fn(synth_prompt)
                    if llm_fn is not None
                    else invoke_configured_runner(synth_prompt, max_tokens=500, timeout=25.0)
                )
                m_json = re.search(r"\{.*\}", raw_resp or "", re.DOTALL)
                parsed = json.loads(m_json.group(0) if m_json else raw_resp)
                if isinstance(parsed, dict) and parsed.get("light") and parsed.get("medium"):
                    tier_l1 = f"[L1 LIGHT] {str(parsed['light']).strip()[:240]}"
                    tier_l2 = f"[L2 MEDIUM] {str(parsed['medium']).strip()[:1200]}"
                    if parsed.get("high"):
                        tier_l3 = f"[L3 HIGH] {str(parsed['high']).strip()[:3200]}"
            except Exception:  # noqa: BLE001
                pass

        with self.wiki_db._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO task_discussion_synthesis(
                       episode_id, tenant_id, workspace_id,
                       tier_l1_light, tier_l2_medium, tier_l3_high, tier_max_raw,
                       lessons_learned, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    episode_id,
                    access_ctx.tenant_id,
                    access_ctx.workspace_id,
                    tier_l1,
                    tier_l2,
                    tier_l3,
                    tier_max,
                    lessons_clean,
                    time.time(),
                ),
            )

        return {
            "status": "synthesized",
            "episode_id": episode_id,
            "light": tier_l1,
            "medium": tier_l2,
            "high": tier_l3,
            "max": tier_max,
            "l1_light": tier_l1,
            "l2_medium": tier_l2,
            "l3_high": tier_l3,
            "l4_max_raw": tier_max,
            "lessons_learned": lessons_clean,
        }

    def evaluate_and_compile_skill(
        self,
        episode_id: str,
        goal: str = "",
        lessons_learned: str = "",
        discussion_steps: Optional[list[dict[str, Any]]] = None,
        force_create: bool = False,
        ctx: Optional[AccessContext] = None,
        user_closing_notes: str = "",
        use_local_llm: bool = False,
        llm_fn: Optional[Callable[[str], str]] = None,
    ) -> SkillEvaluationResult:
        """Evaluates whether an episode yields durable knowledge & compiles/evolves a concept-linked Skill."""
        access_ctx = ctx or AccessContext()
        if user_closing_notes and not lessons_learned:
            lessons_learned = user_closing_notes
        if goal and not lessons_learned and discussion_steps is None:
            lessons_learned = goal
            goal = ""
        resolved_goal, resolved_steps = self._load_episode_and_steps(
            episode_id, access_ctx, goal=goal, discussion_steps=discussion_steps
        )
        goal = resolved_goal
        discussion_steps = resolved_steps
        combined = f"{goal} {lessons_learned}".strip()
        terms = extract_terms(combined)

        from .config import invoke_configured_runner, load_cortical_config

        sk_cfg = (load_cortical_config().get("skills") or {})
        if not force_create and not bool(sk_cfg.get("auto_compile", True)):
            return SkillEvaluationResult(
                episode_id=episode_id,
                should_create_skill=False,
                reason="Auto-compilazione skill disabilitata da configurazione (`skills.auto_compile = false`).",
            )
        min_terms = int(sk_cfg.get("min_terms", 4))
        consol_overlap = int(sk_cfg.get("consolidation_overlap", 3))
        consol_jacc = float(sk_cfg.get("consolidation_jaccard", 0.30))

        reusable_signals = (
            "pattern", "procedura", "regola", "standard", "workflow", "architettura",
            "sempre", "quando", "skill", "pipeline", "test", "verifica", "mcp", "wiki",
            "analizza", "ottimizza", "integra", "configura",
        )
        norm = combined.lower()
        is_worthy = force_create or (
            len(terms) >= min_terms and any(sig in norm for sig in reusable_signals)
        )

        if not is_worthy:
            return SkillEvaluationResult(
                episode_id=episode_id,
                should_create_skill=False,
                reason="Il task riguarda un'operazione puntuale e non richiede una nuova Skill procedurale permanente.",
            )

        slug_words = [w for w in re.findall(r"[a-z0-9]+", normalize_text(goal)) if w not in STOP_WORDS and len(w) > 2][:4]
        steps_summary, touched_files, verified_cmds = _extract_skill_procedure_blocks(discussion_steps)
        has_substance = bool(
            touched_files
            or verified_cmds
            or len(discussion_steps or []) >= 2
            or len(lessons_learned.strip()) >= 80
        )
        if not force_create and (not has_substance or (len(slug_words) < 2 and not touched_files and not verified_cmds)):
            return SkillEvaluationResult(
                episode_id=episode_id,
                should_create_skill=False,
                reason="Contenuto procedurale insufficiente per compilare una Skill permanente (nessun file/comando verificato o lezione sintetica).",
            )

        k_links = _infer_knowledge_concepts(combined, touched_files, self.wiki_db, access_ctx)
        slug_base = "-".join(slug_words) if slug_words else f"knowledge-{episode_id.lower()}"
        skill_id = f"learned-{slug_base}"

        matched_existing: Optional[SkillDescriptor] = None
        if not force_create and terms:
            best_score = 0.0
            for desc in self.list_skills():
                if not desc.skill_id.startswith("learned-"):
                    continue
                s_body = Path(desc.path).read_text(encoding="utf-8", errors="replace")[:500] if desc.path else ""
                s_terms = extract_terms(f"{desc.name} {desc.description} {s_body}")
                overlap = len(terms & s_terms)
                jacc = overlap / max(1, len(terms | s_terms))
                if overlap >= consol_overlap or jacc >= consol_jacc:
                    score = overlap + jacc
                    if score > best_score:
                        best_score = score
                        matched_existing = desc

        if matched_existing is not None:
            skill_id = matched_existing.skill_id
            skill_path = Path(matched_existing.path)
            existing_txt = skill_path.read_text(encoding="utf-8", errors="replace")
            if f"`{episode_id}`" not in existing_txt:
                extra_files = [f"- `{p}`" for p in k_links["wiki_paths"] if f"`{p}`" not in existing_txt]
                extra_cmds = [f"- Esegui: `{c}`" for c in verified_cmds if f"`{c}`" not in existing_txt]
                addition = (
                    f"\n\n### Esperienza & Conoscenza Consolidata (`{episode_id}`)\n"
                    f"- **Concetti:** {', '.join(f'`{c}`' for c in k_links['concepts'])}\n"
                    f"- **Regola Distillata:** {lessons_learned or goal}\n"
                    + (f"- **Nodi Wiki Collegati:**\n" + "\n".join(extra_files) + "\n" if extra_files else "")
                    + (f"- **Comandi Verificati:**\n" + "\n".join(extra_cmds) + "\n" if extra_cmds else "")
                )
                skill_path.write_text(existing_txt.rstrip() + addition, encoding="utf-8")
                self.record_skill_usage([skill_id], helpful=True, ctx=access_ctx)
            self._link_skill_knowledge_edges(skill_id, episode_id, k_links, access_ctx)
            return SkillEvaluationResult(
                episode_id=episode_id,
                should_create_skill=True,
                reason=f"Consolidata ed evoluta la Skill esistente '{skill_id}' con la conoscenza di {episode_id}.",
                skill_id=skill_id,
                skill_path=str(skill_path),
                skill_markdown=skill_path.read_text(encoding="utf-8", errors="replace"),
            )

        refined_rule = lessons_learned or goal
        if use_local_llm or llm_fn is not None:
            try:
                p_llm = (
                    f"Distilla una regola tecnica riutilizzabile (senza citare ID di task) per una Skill Cortical.\n"
                    f"Concetti: {', '.join(k_links['concepts'])}\n"
                    f"Nodi Wiki: {', '.join(k_links['wiki_paths'])}\n"
                    f"Nota: {refined_rule}\n"
                    f"Restituisci 2-3 frasi concise ed azionabili."
                )
                ans = llm_fn(p_llm) if llm_fn is not None else invoke_configured_runner(p_llm, max_tokens=240, timeout=20.0)
                if ans and len(ans.strip()) >= 20:
                    refined_rule = ans.strip()[:600]
            except Exception:  # noqa: BLE001
                pass

        skill_dir = self.skills_root / skill_id
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_path = skill_dir / "SKILL.md"
        concepts_block = "\n".join(f"- `{c}`" for c in k_links["concepts"])
        nodes_block = (
            "\n".join(f"- `{wp}`" for wp in k_links["wiki_paths"])
            if k_links["wiki_paths"]
            else "- (`/src/cortical`)"
        )
        insights_block = (
            "\n".join(f"- `{iid}`: {itxt}" for iid, itxt in k_links["insights"])
            if k_links["insights"]
            else f"- {refined_rule[:180]}"
        )
        verify_block = (
            "\n".join(f"- Esegui: `{c}`" for c in verified_cmds)
            if verified_cmds
            else "- Controlla la coerenza con la Wiki 3+1 (`wiki_navigate` / `wiki_search`) ed esegui i test in un unico colpo."
        )
        cap_title = ", ".join(c.split(":")[-1].replace("-", " ").title() for c in k_links["concepts"][:2])

        skill_md = (
            f"---\n"
            f"name: {skill_id}\n"
            f"description: Capability skill su {cap_title} collegata a {', '.join(k_links['wiki_paths'][:3] or slug_words)}.\n"
            f"---\n\n"
            f"# Capability Skill: {cap_title or goal[:70]}\n\n"
            f"## Conoscenze, Concetti & Nodi Wiki Collegati\n"
            f"{concepts_block}\n"
            f"{nodes_block}\n\n"
            f"## Regole & Insight Distillati\n"
            f"{refined_rule}\n"
            f"{insights_block}\n\n"
            f"## Procedura Riutilizzabile\n"
            f"{steps_summary}\n\n"
            f"## Verifica\n"
            f"{verify_block}\n\n"
            f"## Provenienza & Evoluzione\n"
            f"- Origine iniziale: `{episode_id}`\n"
        )
        skill_path.write_text(skill_md, encoding="utf-8")

        with self.wiki_db._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO learned_skills_registry(
                       skill_id, tenant_id, workspace_id, name, description,
                       skill_path, source_episode_id, use_count, helpful_count, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, 1, ?)""",
                (
                    skill_id,
                    access_ctx.tenant_id,
                    access_ctx.workspace_id,
                    skill_id,
                    f"Capability: {cap_title} · nodi: {', '.join(k_links['wiki_paths'][:2])}",
                    str(skill_path),
                    episode_id,
                    time.time(),
                ),
            )
        self._link_skill_knowledge_edges(skill_id, episode_id, k_links, access_ctx)

        return SkillEvaluationResult(
            episode_id=episode_id,
            should_create_skill=True,
            reason=f"Creata nuova Skill '{skill_id}' collegata a {', '.join(k_links['concepts'])}.",
            skill_id=skill_id,
            skill_path=str(skill_path),
            skill_markdown=skill_md,
        )

    def _link_skill_knowledge_edges(
        self,
        skill_id: str,
        episode_id: str,
        k_links: dict[str, Any],
        ctx: AccessContext,
    ) -> int:
        now = time.time()
        added = 0
        with self.wiki_db._connect() as conn:
            for cid in k_links.get("concepts") or []:
                conn.execute(
                    """INSERT OR IGNORE INTO macro_edges(
                           tenant_id, workspace_id, source_type, source_id, relation, target_type, target_id, weight, created_at
                       ) VALUES (?, ?, 'skill', ?, 'links_knowledge', 'concept', ?, 1.0, ?)""",
                    (ctx.tenant_id, ctx.workspace_id, skill_id, cid, now),
                )
                added += 1
            for wp in k_links.get("wiki_paths") or []:
                conn.execute(
                    """INSERT OR IGNORE INTO macro_edges(
                           tenant_id, workspace_id, source_type, source_id, relation, target_type, target_id, weight, created_at
                       ) VALUES (?, ?, 'skill', ?, 'links_knowledge', 'subtree', ?, 0.9, ?)""",
                    (ctx.tenant_id, ctx.workspace_id, skill_id, wp, now),
                )
                added += 1
            for iid, _ in k_links.get("insights") or []:
                conn.execute(
                    """INSERT OR IGNORE INTO macro_edges(
                           tenant_id, workspace_id, source_type, source_id, relation, target_type, target_id, weight, created_at
                       ) VALUES (?, ?, 'skill', ?, 'links_knowledge', 'insight', ?, 0.85, ?)""",
                    (ctx.tenant_id, ctx.workspace_id, skill_id, iid, now),
                )
                added += 1
            if episode_id and episode_id != "consolidated":
                conn.execute(
                    """INSERT OR IGNORE INTO macro_edges(
                           tenant_id, workspace_id, source_type, source_id, relation, target_type, target_id, weight, created_at
                       ) VALUES (?, ?, 'episode', ?, 'derived_from', 'skill', ?, 0.7, ?)""",
                    (ctx.tenant_id, ctx.workspace_id, episode_id, skill_id, now),
                )
                added += 1
        return added

    def record_skill_usage(
        self,
        skill_ids: list[str],
        helpful: bool = True,
        ctx: Optional[AccessContext] = None,
    ) -> int:
        """Increments `use_count` (and optionally `helpful_count`) for learned skills."""
        if not skill_ids:
            return 0
        access_ctx = ctx or AccessContext()
        updated = 0
        with self.wiki_db._connect() as conn:
            for sid in skill_ids:
                cur = conn.execute(
                    """UPDATE learned_skills_registry
                       SET use_count = use_count + 1,
                           helpful_count = helpful_count + ?
                       WHERE tenant_id = ? AND workspace_id = ? AND skill_id = ?""",
                    (1 if helpful else 0, access_ctx.tenant_id, access_ctx.workspace_id, sid),
                )
                updated += int(cur.rowcount or 0)
        return updated

    def prune_low_value_skills(
        self,
        dry_run: bool = True,
        ctx: Optional[AccessContext] = None,
    ) -> dict[str, Any]:
        """Finds (and optionally removes) `learned-*` stub skills with no real procedure/files/commands."""
        access_ctx = ctx or AccessContext()
        candidates: list[str] = []
        if self.skills_root.exists():
            for d in sorted(self.skills_root.glob("learned-*")):
                sfile = d / "SKILL.md"
                if not sfile.is_file():
                    continue
                txt = sfile.read_text(encoding="utf-8", errors="replace")
                slug_parts = d.name.removeprefix("learned-").split("-")
                has_files_or_cmds = ("## File & Moduli Coinvolti" in txt) or ("## Conoscenze, Concetti" in txt) or ("- Esegui: `" in txt)
                is_short_stub = len(slug_parts) < 2 and not has_files_or_cmds
                is_empty_proc = "Analisi ed esecuzione controllata sul workspace locale." in txt and not has_files_or_cmds
                if is_short_stub or is_empty_proc:
                    candidates.append(d.name)
                    if not dry_run:
                        sfile.unlink(missing_ok=True)
                        try:
                            d.rmdir()
                        except OSError:
                            pass
                        with self.wiki_db._connect() as conn:
                            conn.execute(
                                "DELETE FROM learned_skills_registry WHERE tenant_id = ? AND workspace_id = ? AND skill_id = ?",
                                (access_ctx.tenant_id, access_ctx.workspace_id, d.name),
                            )
        return {"dry_run": dry_run, "candidates": candidates, "count": len(candidates)}

    def consolidate_and_link_skills(
        self,
        ctx: Optional[AccessContext] = None,
        use_local_llm: bool = False,
        llm_fn: Optional[Callable[[str], str]] = None,
    ) -> dict[str, int]:
        """Prunes stubs, merges overlapping `learned-*` skills, generalizes them via local LLM, and links knowledge."""
        from .config import invoke_configured_runner

        access_ctx = ctx or AccessContext()
        pruned = self.prune_low_value_skills(dry_run=False, ctx=access_ctx)["count"]
        merged = 0
        edges_added = 0
        insights_added = 0
        generalized = 0

        learned = [s for s in self.list_skills() if s.skill_id.startswith("learned-")]
        removed_ids: set[str] = set()
        for i, base in enumerate(learned):
            if base.skill_id in removed_ids:
                continue
            b_path = Path(base.path)
            if not b_path.is_file():
                continue
            b_txt = b_path.read_text(encoding="utf-8", errors="replace")
            b_terms = extract_terms(f"{base.name} {base.description} {b_txt[:400]}")
            for other in learned[i + 1 :]:
                if other.skill_id in removed_ids:
                    continue
                o_path = Path(other.path)
                if not o_path.is_file():
                    continue
                o_txt = o_path.read_text(encoding="utf-8", errors="replace")
                o_terms = extract_terms(f"{other.name} {other.description} {o_txt[:400]}")
                overlap = len(b_terms & o_terms)
                jacc = overlap / max(1, len(b_terms | o_terms))
                if overlap >= 4 or jacc >= 0.35:
                    if other.skill_id not in b_txt:
                        b_txt += f"\n\n### Conoscenza Unificata da `{other.skill_id}`\n{o_txt[:900]}"
                        b_path.write_text(b_txt, encoding="utf-8")
                    o_path.unlink(missing_ok=True)
                    try:
                        o_path.parent.rmdir()
                    except OSError:
                        pass
                    with self.wiki_db._connect() as conn:
                        conn.execute(
                            "DELETE FROM learned_skills_registry WHERE tenant_id = ? AND workspace_id = ? AND skill_id = ?",
                            (access_ctx.tenant_id, access_ctx.workspace_id, other.skill_id),
                        )
                    removed_ids.add(other.skill_id)
                    merged += 1

            k_links = _infer_knowledge_concepts(f"{base.name} {b_txt}", [], self.wiki_db, access_ctx)
            if "## Conoscenze, Concetti" not in b_txt:
                concepts_block = "\n".join(f"- `{c}`" for c in k_links["concepts"])
                nodes_block = "\n".join(f"- `{wp}`" for wp in k_links["wiki_paths"]) or "- (`/src/cortical`)"
                cap_title = ", ".join(c.split(":")[-1].replace("-", " ").title() for c in k_links["concepts"][:2])
                extra_summary = f"Regole riutilizzabili su {cap_title} collegate ai moduli {', '.join(k_links['wiki_paths'][:3])}."
                if use_local_llm or llm_fn is not None:
                    try:
                        pr_gen = (
                            "Riscrivi questa skill di Cortical in italiano in formato professionale senza far dipendere il titolo "
                            "da un singolo ID task. Mantieni le informazioni reali e generalizza la conoscenza riusabile (max 120 parole).\n\n"
                            f"Concetti: {', '.join(k_links['concepts'])}\n"
                            f"Moduli Wiki: {', '.join(k_links['wiki_paths'])}\n"
                            f"Testo attuale:\n{b_txt[:1500]}"
                        )
                        ans = (
                            llm_fn(pr_gen)
                            if llm_fn is not None
                            else invoke_configured_runner(pr_gen, max_tokens=320, timeout=25.0)
                        )
                        if ans and len(ans.strip()) >= 30:
                            extra_summary = ans.strip()[:900]
                    except Exception:  # noqa: BLE001
                        pass

                new_md = (
                    f"---\nname: {base.skill_id}\n"
                    f"description: Capability skill su {cap_title} collegata a {', '.join(k_links['wiki_paths'][:3] or ['cortical'])}.\n"
                    f"---\n\n"
                    f"# Capability Skill: {cap_title}\n\n"
                    f"## Conoscenze, Concetti & Nodi Wiki Collegati\n"
                    f"{concepts_block}\n{nodes_block}\n\n"
                    f"## Regole & Sintesi Generale\n{extra_summary}\n\n"
                    f"## Provenienza & Dettagli Precedenti\n{b_txt}\n"
                )
                b_path.write_text(new_md, encoding="utf-8")
                with self.wiki_db._connect() as conn:
                    conn.execute(
                        """UPDATE learned_skills_registry
                           SET description = ?, use_count = MAX(1, use_count)
                           WHERE tenant_id = ? AND workspace_id = ? AND skill_id = ?""",
                        (f"Capability: {cap_title}", access_ctx.tenant_id, access_ctx.workspace_id, base.skill_id),
                    )
                generalized += 1

            with self.wiki_db._connect() as conn:
                conn.execute(
                    """INSERT OR IGNORE INTO learned_skills_registry(
                           skill_id, tenant_id, workspace_id, name, description,
                           skill_path, source_episode_id, use_count, helpful_count, created_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, 1, ?)""",
                    (base.skill_id, access_ctx.tenant_id, access_ctx.workspace_id, base.name, base.description, str(b_path), "knowledge_consolidated", time.time()),
                )
                conn.execute(
                    "UPDATE learned_skills_registry SET use_count = MAX(1, use_count) WHERE tenant_id = ? AND workspace_id = ? AND skill_id = ?",
                    (access_ctx.tenant_id, access_ctx.workspace_id, base.skill_id),
                )
            edges_added += self._link_skill_knowledge_edges(base.skill_id, "", k_links, access_ctx)

        now = time.time()
        with self.wiki_db._connect() as conn:
            for row in conn.execute(
                "SELECT skill_id, source_episode_id FROM learned_skills_registry WHERE tenant_id = ? AND workspace_id = ?",
                (access_ctx.tenant_id, access_ctx.workspace_id),
            ).fetchall():
                sid, eid = str(row["skill_id"]), str(row["source_episode_id"] or "")
                if eid and eid not in {"consolidated", "knowledge_consolidated"}:
                    conn.execute(
                        """INSERT OR IGNORE INTO macro_edges(
                               tenant_id, workspace_id, source_type, source_id, relation, target_type, target_id, weight, created_at
                           ) VALUES (?, ?, 'episode', ?, 'derived_from', 'skill', ?, 0.7, ?)""",
                        (access_ctx.tenant_id, access_ctx.workspace_id, eid, sid, now),
                    )
                    edges_added += 1

            for row in conn.execute(
                """SELECT e.episode_id, e.goal, COALESCE(s.tier_l2_medium, e.learned_summary, '') AS synth
                   FROM task_episodes e
                   LEFT JOIN task_discussion_synthesis s
                     ON e.tenant_id = s.tenant_id AND e.workspace_id = s.workspace_id AND e.episode_id = s.episode_id
                   WHERE e.tenant_id = ? AND e.workspace_id = ?""",
                (access_ctx.tenant_id, access_ctx.workspace_id),
            ).fetchall():
                txt = re.sub(r"\s+", " ", str(row["synth"] or row["goal"] or "")).strip()[:240]
                if len(txt) < 30:
                    continue
                iid = "ins-" + hashlib.sha256(txt.encode("utf-8")).hexdigest()[:10]
                cur = conn.execute(
                    """INSERT OR IGNORE INTO memory_insights(
                           insight_id, tenant_id, workspace_id, category, insight_text, related_path, created_at
                       ) VALUES (?, ?, ?, 'task_distillation', ?, ?, ?)""",
                    (iid, access_ctx.tenant_id, access_ctx.workspace_id, txt, f"/{row['episode_id']}", now),
                )
                insights_added += int(cur.rowcount or 0)

        return {
            "pruned_stubs": pruned,
            "merged_skills": merged,
            "generalized_skills": generalized,
            "edges_linked": edges_added,
            "insights_distilled": insights_added,
        }

    def distill_and_compact_knowledge(
        self,
        target_kind: str,
        target_id: str,
        keep_tier: str = "l2",
        use_local_llm: bool = True,
        llm_fn: Optional[Callable[[str], str]] = None,
        ctx: Optional[AccessContext] = None,
    ) -> dict[str, Any]:
        """Distills knowledge from a subtree/context/episode/topic into a durable insight and discards L4 Max raw blobs."""
        from .config import invoke_configured_runner

        access_ctx = ctx or AccessContext()
        kind = (target_kind or "subtree").lower().strip()
        tier = (keep_tier or "l2").lower().strip()
        snippets: list[str] = []
        bytes_freed = 0
        compacted_nodes = 0
        compacted_episodes = 0

        with self.wiki_db._connect() as conn:
            if kind in {"subtree", "node", "folder", "context_root"}:
                if kind == "context_root" and target_id == "root:private_notes":
                    where_sql = "tenant_id = ? AND workspace_id = ? AND (path = '/private_notes' OR path LIKE '/private_notes/%')"
                    params: tuple[Any, ...] = (access_ctx.tenant_id, access_ctx.workspace_id)
                elif kind == "context_root" or target_id == "/":
                    where_sql = "tenant_id = ? AND workspace_id = ? AND path NOT LIKE '/private_notes%'"
                    params = (access_ctx.tenant_id, access_ctx.workspace_id)
                else:
                    pref = "/" + target_id.strip("/")
                    where_sql = "tenant_id = ? AND workspace_id = ? AND (path = ? OR path LIKE ?)"
                    params = (access_ctx.tenant_id, access_ctx.workspace_id, pref, pref + "/%")

                rows = conn.execute(
                    f"SELECT path, summary_light, summary_medium, summary_high, raw_content FROM merkle_nodes WHERE {where_sql}",
                    params,
                ).fetchall()
                for r in rows:
                    raw_s = str(r["raw_content"] or "")
                    hi_s = str(r["summary_high"] or "")
                    snippets.append(f"{r['path']}: {str(r['summary_medium'] or r['summary_light'] or '')[:220]}")
                    bytes_freed += len(raw_s.encode("utf-8", errors="ignore"))
                    if raw_s:
                        compacted_nodes += 1
                    if tier == "l1":
                        bytes_freed += len(hi_s.encode("utf-8", errors="ignore"))
                        conn.execute(
                            "UPDATE merkle_nodes SET raw_content = '', summary_high = '' WHERE tenant_id = ? AND workspace_id = ? AND path = ?",
                            (access_ctx.tenant_id, access_ctx.workspace_id, r["path"]),
                        )
                    else:
                        conn.execute(
                            "UPDATE merkle_nodes SET raw_content = '' WHERE tenant_id = ? AND workspace_id = ? AND path = ?",
                            (access_ctx.tenant_id, access_ctx.workspace_id, r["path"]),
                        )
                    conn.execute(
                        "UPDATE merkle_fts SET raw_content = '' WHERE tenant_id = ? AND workspace_id = ? AND path = ?",
                        (access_ctx.tenant_id, access_ctx.workspace_id, r["path"]),
                    )

            if kind in {"episode", "topic", "context_root"}:
                ep_rows = conn.execute(
                    """SELECT e.episode_id, e.goal, COALESCE(s.tier_l2_medium, e.learned_summary, '') AS synth,
                              COALESCE(s.tier_l3_high, '') AS hi, COALESCE(s.tier_max_raw, '') AS raw_t
                       FROM task_episodes e
                       LEFT JOIN task_discussion_synthesis s
                         ON e.tenant_id = s.tenant_id AND e.workspace_id = s.workspace_id AND e.episode_id = s.episode_id
                       WHERE e.tenant_id = ? AND e.workspace_id = ?""",
                    (access_ctx.tenant_id, access_ctx.workspace_id),
                ).fetchall()
                for r in ep_rows:
                    eid = str(r["episode_id"])
                    if kind == "episode" and eid != target_id:
                        continue
                    raw_t = str(r["raw_t"] or "")
                    hi_t = str(r["hi"] or "")
                    snippets.append(f"Task {eid}: {str(r['synth'] or r['goal'] or '')[:220]}")
                    bytes_freed += len(raw_t.encode("utf-8", errors="ignore"))
                    if raw_t:
                        compacted_episodes += 1
                    if tier == "l1":
                        bytes_freed += len(hi_t.encode("utf-8", errors="ignore"))
                        conn.execute(
                            "UPDATE task_discussion_synthesis SET tier_max_raw = '', tier_l3_high = '' WHERE tenant_id = ? AND workspace_id = ? AND episode_id = ?",
                            (access_ctx.tenant_id, access_ctx.workspace_id, eid),
                        )
                    else:
                        conn.execute(
                            "UPDATE task_discussion_synthesis SET tier_max_raw = '' WHERE tenant_id = ? AND workspace_id = ? AND episode_id = ?",
                            (access_ctx.tenant_id, access_ctx.workspace_id, eid),
                        )

            digest_src = "\n".join(snippets[:16]) or f"Distilled knowledge for {kind}:{target_id}"
            insight_text = f"Conoscenza distillata ({kind} {target_id}, livello {tier.upper()}): " + re.sub(r"\s+", " ", digest_src)[:260]
            llm_refined = False
            if use_local_llm or llm_fn is not None:
                try:
                    p_dist = (
                        f"Distilla in una singola regola tecnica ad alta densità (max 60 parole, zero ID di task effimeri) "
                        f"l'essenza architetturale di questi elementi (`{kind}:{target_id}`):\n\n{digest_src[:2500]}"
                    )
                    ans = (
                        llm_fn(p_dist)
                        if llm_fn is not None
                        else invoke_configured_runner(p_dist, max_tokens=180, timeout=20.0)
                    )
                    if ans and len(ans.strip()) >= 20:
                        insight_text = ans.strip()[:420]
                        llm_refined = True
                except Exception:  # noqa: BLE001
                    pass

            now = time.time()
            iid = "ins-" + hashlib.sha256(f"{kind}:{target_id}:{insight_text}".encode("utf-8")).hexdigest()[:10]
            conn.execute(
                """INSERT OR REPLACE INTO memory_insights(
                       insight_id, tenant_id, workspace_id, category, insight_text, related_path, created_at
                   ) VALUES (?, ?, ?, 'knowledge_distillation', ?, ?, ?)""",
                (iid, access_ctx.tenant_id, access_ctx.workspace_id, insight_text, target_id, now),
            )
            conn.execute(
                """INSERT OR IGNORE INTO macro_edges(
                       tenant_id, workspace_id, source_type, source_id, relation, target_type, target_id, weight, created_at
                   ) VALUES (?, ?, 'insight', ?, 'distilled_from', ?, ?, 1.0, ?)""",
                (access_ctx.tenant_id, access_ctx.workspace_id, iid, "episode" if kind == "episode" else "subtree", target_id, now),
            )

        return {
            "status": "compacted",
            "target_kind": kind,
            "target_id": target_id,
            "keep_tier": tier,
            "compacted_nodes": compacted_nodes,
            "compacted_episodes": compacted_episodes,
            "bytes_freed": bytes_freed,
            "insight_id": iid,
            "insight_text": insight_text,
            "llm_refined": llm_refined,
        }

    def _gate_privacy_content(
        self,
        raw_text: str,
        ref_label: str,
        eff_privacy: str,
        default_tier: str,
    ) -> tuple[str, bool]:
        """Applies Cortical's Egress Decision Engine based on privacy profile (`max_security`, `low`, `medium`, etc.)."""
        if not eff_privacy or eff_privacy in {"workspace_code", "max_context"}:
            return (raw_text, False)
        from .config import load_cortical_config
        from .privacy_sanitizer import pseudonymize_text

        cfg = load_cortical_config()
        san_cfg = cfg.get("privacy_sanitizer") or {}
        custom_terms = list(san_cfg.get("custom_terms") or []) or None
        if eff_privacy == "max_security":
            red_l1, _ = pseudonymize_text(raw_text[:280], redact=True, custom_terms=custom_terms)
            gated = (
                f"[🔒 MAX_SECURITY VAULT: {ref_label}] Contenuto riservato elaborabile solo da LLM locale (`cortical_local_loop`). "
                f"Sintesi L1 anonimizzata: {red_l1}"
            )
            return (gated, True)
        if eff_privacy == "low":
            red_low, _ = pseudonymize_text(raw_text[:900], redact=True, custom_terms=custom_terms)
            return (f"[🛡️ PRIVACY: LOW EGRESS · {ref_label}]\n{red_low}", False)
        pseudo, _ = pseudonymize_text(raw_text, redact=False, custom_terms=custom_terms)
        return (pseudo, False)

    def resolve_wiki_references(
        self,
        prompt: str,
        default_tier: str = "l2",
        ctx: Optional[AccessContext] = None,
    ) -> dict[str, Any]:
        """Resolves universal `@kind:ref`, `@private:alias[:profile]`, `/private alias`, `cortical://`, and `/directive` mentions."""
        access_ctx = ctx or AccessContext()
        text = prompt or ""
        tier_map = {"light": "l1", "l1": "l1", "medium": "l2", "l2": "l2", "high": "l3", "l3": "l3", "max": "max", "l4": "max"}
        m_tier = re.search(r"/tier:(l1|l2|l3|l4|light|medium|high|max)\b", text, re.IGNORECASE)
        eff_tier = tier_map.get((m_tier.group(1) if m_tier else default_tier).lower(), "l2")
        m_priv = re.search(r"/privacy:([a-z0-9_]+)\b", text, re.IGNORECASE)
        priv_val = m_priv.group(1).lower() if m_priv else None
        directives = {
            "force_local": bool(re.search(r"/(?:local|offline)\b", text, re.IGNORECASE)) or priv_val == "max_security",
            "distill": bool(re.search(r"/distill\b", text, re.IGNORECASE)),
            "privacy_profile": priv_val,
            "tier": eff_tier,
        }

        raw_refs: list[tuple[str, str]] = []
        for kind, ref in re.findall(r"@(wiki|node|file|folder|private|vault|ctx|concept|topic|skill|insight|task|root):([A-Za-z0-9_./:-]+)", text, re.IGNORECASE):
            pair = (kind.lower(), ref.strip())
            if pair not in raw_refs:
                raw_refs.append(pair)
        for ref in re.findall(r"(?:^|\s)/private\s+([A-Za-z0-9_./:-]+)", text, re.IGNORECASE):
            pair = ("private", ref.strip())
            if pair not in raw_refs:
                raw_refs.append(pair)
        for kind, ref in re.findall(r"cortical://(node|private|concept|skill|insight|task|root)/([A-Za-z0-9_./:-]+)", text, re.IGNORECASE):
            pair = (kind.lower(), ref.strip())
            if pair not in raw_refs:
                raw_refs.append(pair)

        col_map = {"l1": "summary_light", "l2": "summary_medium", "l3": "summary_high", "max": "raw_content"}
        target_col = col_map.get(eff_tier, "summary_medium")
        resolved: list[dict[str, Any]] = []
        all_skills = self.list_skills()

        with self.wiki_db._connect() as conn:
            att_privacy: dict[str, str] = {}
            try:
                for arow in conn.execute(
                    "SELECT item_ref, label, depth_tier, metadata_json FROM scoped_context_attachments WHERE tenant_id = ? AND workspace_id = ?",
                    (access_ctx.tenant_id, access_ctx.workspace_id),
                ).fetchall():
                    m_json = {}
                    try:
                        m_json = json.loads(str(arow["metadata_json"] or "{}"))
                    except Exception:  # noqa: BLE001
                        pass
                    pr = str(m_json.get("privacy_profile") or arow["depth_tier"] or "").lower()
                    if pr in {"max_security", "low", "medium", "max_context"}:
                        att_privacy[str(arow["item_ref"] or "")] = pr
                        if arow["label"]:
                            att_privacy[str(arow["label"])] = pr
            except Exception:  # noqa: BLE001
                pass

            for kind, raw_ref in raw_refs[:16]:
                inline_priv = None
                ref = raw_ref
                for p_cand in ("max_security", "max_context", "medium", "low"):
                    if raw_ref.lower().endswith(f":{p_cand}"):
                        inline_priv = p_cand
                        ref = raw_ref[: -(len(p_cand) + 1)]
                        break

                if kind in {"wiki", "node", "file", "folder", "private", "vault", "ctx"}:
                    norm_p = "/" + ref.lstrip("/")
                    fuzzy_rows = conn.execute(
                        f"SELECT path, node_type, {target_col} AS body, summary_medium, summary_light FROM merkle_nodes "
                        "WHERE tenant_id = ? AND workspace_id = ? AND (path = ? OR LOWER(path) LIKE ? OR LOWER(path) LIKE ?) "
                        "ORDER BY (CASE WHEN path = ? THEN 0 WHEN LOWER(path) LIKE ? THEN 1 ELSE 2 END), LENGTH(path) ASC LIMIT 4",
                        (access_ctx.tenant_id, access_ctx.workspace_id, norm_p, f"%/{ref.lower().lstrip('/')}", f"%{ref.lower().lstrip('/')}%", norm_p, f"%/{ref.lower().lstrip('/')}"),
                    ).fetchall()
                    if fuzzy_rows:
                        top = fuzzy_rows[0]
                        tpath = str(top["path"])
                        body = str(top["body"] or top["summary_medium"] or top["summary_light"] or "")[:2400]
                        eff_p = inline_priv or priv_val or att_privacy.get(tpath) or att_privacy.get(Path(tpath).name) or ("low" if kind in {"private", "vault", "ctx"} else "")
                        gated_body, forced_loc = self._gate_privacy_content(body, tpath, eff_p, eff_tier)
                        if forced_loc:
                            directives["force_local"] = True
                            directives["privacy_profile"] = directives["privacy_profile"] or "max_security"
                        disamb = [str(r["path"]) for r in fuzzy_rows[1:]]
                        if disamb:
                            gated_body += f"\n(Altri match simili: {', '.join(disamb)})"
                        resolved.append({
                            "kind": "private" if eff_p in {"max_security", "low"} else "node",
                            "ref": tpath,
                            "alias": Path(tpath).name,
                            "privacy_profile": eff_p or "workspace_code",
                            "tier": eff_tier,
                            "title": f"{tpath} ({top['node_type']})",
                            "content": gated_body,
                            "tokens": max(1, len(gated_body) // 4),
                        })
                    else:
                        hits = self.wiki_db.search(access_ctx, query=ref, depth=DepthTier.MEDIUM, limit=2)
                        for h in hits:
                            hpath = str(h["path"])
                            body = str(h.get("content") or "")[:1600]
                            eff_p = inline_priv or priv_val or att_privacy.get(hpath) or ("low" if kind in {"private", "vault", "ctx"} else "")
                            gated_body, forced_loc = self._gate_privacy_content(body, hpath, eff_p, eff_tier)
                            if forced_loc:
                                directives["force_local"] = True
                            resolved.append({
                                "kind": "private" if eff_p in {"max_security", "low"} else "node",
                                "ref": hpath,
                                "alias": Path(hpath).name,
                                "privacy_profile": eff_p or "workspace_code",
                                "tier": eff_tier,
                                "title": hpath,
                                "content": gated_body,
                                "tokens": max(1, len(gated_body) // 4),
                            })
                elif kind in {"concept", "topic"}:
                    slug = ref.split(":")[-1].lower()
                    kws = []
                    matched_cid = f"concept:{slug}"
                    for cid, words in _KNOWLEDGE_DOMAIN_MAP:
                        if slug in cid or any(slug in w for w in words):
                            matched_cid = cid
                            kws = list(words)
                            break
                    if not kws:
                        kws = [t for t in re.split(r"[-_:]+", slug) if len(t) > 2]
                    lines = [f"Concetto Canonico: `{matched_cid}`"]
                    m_rows = conn.execute(
                        "SELECT path, summary_light FROM merkle_nodes WHERE tenant_id = ? AND workspace_id = ? LIMIT 150",
                        (access_ctx.tenant_id, access_ctx.workspace_id),
                    ).fetchall()
                    matched_paths = [
                        (str(r["path"]), str(r["summary_light"] or ""))
                        for r in m_rows
                        if any(k in (str(r["path"]) + " " + str(r["summary_light"])).lower() for k in kws)
                    ][:5]
                    if matched_paths:
                        lines.append("Nodi Wiki correlati:")
                        lines.extend(f"- `{p}`: {s[:140]}" for p, s in matched_paths)
                    i_rows = conn.execute(
                        "SELECT insight_id, insight_text FROM memory_insights WHERE tenant_id = ? AND workspace_id = ? ORDER BY created_at DESC LIMIT 80",
                        (access_ctx.tenant_id, access_ctx.workspace_id),
                    ).fetchall()
                    matched_ins = [
                        (str(r["insight_id"]), str(r["insight_text"] or ""))
                        for r in i_rows
                        if any(k in str(r["insight_text"] or "").lower() for k in kws)
                    ][:4]
                    if matched_ins:
                        lines.append("Regole/Insight Distillati:")
                        lines.extend(f"- `{iid}`: {txt[:160]}" for iid, txt in matched_ins)
                    body = "\n".join(lines)
                    resolved.append({
                        "kind": "concept",
                        "ref": matched_cid,
                        "tier": eff_tier,
                        "title": matched_cid,
                        "content": body,
                        "tokens": max(1, len(body) // 4),
                    })
                elif kind == "skill":
                    target_s = ref.lower()
                    matched_sk = next(
                        (s for s in all_skills if s.skill_id.lower() == target_s or target_s in s.skill_id.lower() or target_s in s.name.lower()),
                        None,
                    )
                    if matched_sk:
                        body = matched_sk.body_excerpt if eff_tier == "l1" else matched_sk.full_body[: (1000 if eff_tier == "l2" else 2800)]
                        resolved.append({
                            "kind": "skill",
                            "ref": matched_sk.skill_id,
                            "tier": eff_tier,
                            "title": matched_sk.name,
                            "content": body,
                            "tokens": max(1, len(body) // 4),
                        })
                elif kind == "insight":
                    irow = conn.execute(
                        "SELECT insight_id, category, insight_text, related_path FROM memory_insights "
                        "WHERE tenant_id = ? AND workspace_id = ? AND (insight_id = ? OR LOWER(insight_text) LIKE ? OR LOWER(category) LIKE ?) LIMIT 1",
                        (access_ctx.tenant_id, access_ctx.workspace_id, ref, f"%{ref.lower()}%", f"%{ref.lower()}%"),
                    ).fetchone()
                    if irow:
                        body = f"[{irow['category']}] {irow['insight_text']} (path: {irow['related_path'] or '/'})"
                        resolved.append({
                            "kind": "insight",
                            "ref": str(irow["insight_id"]),
                            "tier": eff_tier,
                            "title": str(irow["insight_id"]),
                            "content": body,
                            "tokens": max(1, len(body) // 4),
                        })
                elif kind == "task":
                    erow = conn.execute(
                        "SELECT e.episode_id, e.goal, e.learned_summary, s.tier_l1_light, s.tier_l2_medium, s.tier_l3_high "
                        "FROM task_episodes e LEFT JOIN task_discussion_synthesis s "
                        "ON e.tenant_id = s.tenant_id AND e.workspace_id = s.workspace_id AND e.episode_id = s.episode_id "
                        "WHERE e.tenant_id = ? AND e.workspace_id = ? AND (e.episode_id = ? OR LOWER(e.goal) LIKE ?) LIMIT 1",
                        (access_ctx.tenant_id, access_ctx.workspace_id, ref, f"%{ref.lower()}%"),
                    ).fetchone()
                    if erow:
                        t_key = {"l1": "tier_l1_light", "l3": "tier_l3_high"}.get(eff_tier, "tier_l2_medium")
                        body = str(erow[t_key] or erow["learned_summary"] or erow["goal"] or "")[:2000]
                        resolved.append({
                            "kind": "task",
                            "ref": str(erow["episode_id"]),
                            "tier": eff_tier,
                            "title": f"Task {erow['episode_id']}",
                            "content": body,
                            "tokens": max(1, len(body) // 4),
                        })
                elif kind == "root":
                    if "private" in ref.lower():
                        rrows = conn.execute(
                            "SELECT path, summary_light FROM merkle_nodes WHERE tenant_id = ? AND workspace_id = ? AND path LIKE '/private_notes/%' ORDER BY path ASC LIMIT 25",
                            (access_ctx.tenant_id, access_ctx.workspace_id),
                        ).fetchall()
                        r_title = "Contesto Privato Sanitizzato (private_notes)"
                    else:
                        rrows = conn.execute(
                            "SELECT path, summary_light FROM merkle_nodes WHERE tenant_id = ? AND workspace_id = ? AND path NOT LIKE '/private_notes%' AND node_type = 'file' ORDER BY path ASC LIMIT 25",
                            (access_ctx.tenant_id, access_ctx.workspace_id),
                        ).fetchall()
                        r_title = "Workspace Riconciliato"
                    if rrows:
                        body = "\n".join(f"- `{r['path']}`: {str(r['summary_light'] or '')[:120]}" for r in rrows)
                        resolved.append({
                            "kind": "root",
                            "ref": ref,
                            "tier": eff_tier,
                            "title": r_title,
                            "content": body,
                            "tokens": max(1, len(body) // 4),
                        })

        blocks = [f"#### [{r['kind'].upper()} · {r['tier'].upper()}] `{r['ref']}`\n{r['content']}" for r in resolved]
        return {
            "directives": directives,
            "resolved": resolved,
            "context_markdown": "\n\n".join(blocks),
            "total_tokens": sum(int(r.get("tokens") or 0) for r in resolved),
        }

    def run_multi_model_local_loop(
        self,
        prompt: str,
        *,
        models: Optional[list[str]] = None,
        max_loops: int = 3,
        privacy_profile: Optional[str] = None,
        attached_files: Optional[list[str]] = None,
        force_local_only: bool = False,
        episode_id: Optional[str] = None,
        max_tokens: int = 1200,
        context_budget_chars: int = 16000,
        timeout: float = 90.0,
        num_ctx: Optional[int] = None,
        llm_fn: Optional[Callable[[str, str], str]] = None,
        ctx: Optional[AccessContext] = None,
    ) -> dict[str, Any]:
        """Runs multi-model iterative local reasoning using Wiki references + Skills + Privacy Sanitizer."""
        from .config import _record_runner_telemetry, invoke_configured_runner, load_cortical_config
        from .privacy_sanitizer import pseudonymize_text, sanitize_with_profile

        access_ctx = ctx or AccessContext()
        cfg = load_cortical_config()
        loop_cfg = cfg.get("local_loop") or {}
        refs = self.resolve_wiki_references(prompt, ctx=access_ctx)

        eff_privacy = str(
            privacy_profile
            or refs["directives"].get("privacy_profile")
            or loop_cfg.get("default_privacy_profile")
            or "medium"
        )
        eff_force_local = bool(
            force_local_only
            or eff_privacy == "max_security"
            or refs["directives"].get("force_local")
        )

        # Sanitize user prompt & optional files before passing across models or remote prompt builder
        san_cfg = cfg.get("privacy_sanitizer") or {}
        profiles = cfg.get("privacy_profiles") or {}
        prof = dict(profiles.get(eff_privacy) or profiles.get("medium") or {})
        clean_goal, goal_map = pseudonymize_text(
            prompt,
            redact=bool(prof.get("redact", False)),
            strip_categories=list(prof.get("strip_categories") or []) or None,
            custom_terms=list(san_cfg.get("custom_terms") or []) or None,
        )

        eff_ctx_budget = max(5200, int(context_budget_chars or 16000))
        files_list = list(attached_files or [])[:8]
        per_file_chars = min(6000, max(1400, eff_ctx_budget // max(1, len(files_list))))
        sanitized_files_blocks: list[str] = []
        for fp in files_list:
            p = Path(fp)
            if p.is_file():
                try:
                    sres = sanitize_with_profile(p, profile_name=eff_privacy, config=cfg)
                    sanitized_files_blocks.append(f"### [FILE SANITIZED ({eff_privacy})] `{p.name}`\n{sres['sanitized_text'][:per_file_chars]}")
                except Exception:  # noqa: BLE001
                    pass

        matched_skills = self.rank_skills_for_prompt(prompt, limit=3)
        for sk_desc, _ in matched_skills:
            if sk_desc.skill_id.startswith("learned-"):
                self.record_skill_usage([sk_desc.skill_id], helpful=True, ctx=access_ctx)
        skills_md = "\n".join(f"- `{s.skill_id}`: {s.description[:140]}" for s, _ in matched_skills)

        depth = self.choose_wiki_depth(prompt)
        search_hits = self.wiki_db.search(access_ctx, query=prompt, depth=depth, limit=4)
        hits_md = "\n\n".join(f"### [Wiki {h['depth_tier'].upper()}] `{h['path']}`\n{h['content'][:1200]}" for h in search_hits)

        ctx_parts = [p for p in (refs.get("context_markdown"), "\n\n".join(sanitized_files_blocks), hits_md, f"### [Skills]\n{skills_md}" if skills_md else "") if p]
        context_bundle = "\n\n".join(ctx_parts)[:eff_ctx_budget]

        n_loops = max(1, min(5, int(max_loops or loop_cfg.get("max_iterations", 3))))
        router_m = str(loop_cfg.get("router_model") or "qwen2.5:1.5b")
        analyst_m = str(loop_cfg.get("analyst_model") or "qwen3.5:9b-q3_k_xl")
        reviewer_m = str(loop_cfg.get("reviewer_model") or loop_cfg.get("reasoner_model") or "qwen3:8b")
        default_chain = [router_m, analyst_m, reviewer_m] if n_loops >= 3 else [router_m, analyst_m]
        model_chain = [m.strip() for m in (models or default_chain) if str(m).strip()] or default_chain

        ep_id = episode_id or f"loop-{int(time.time())}"
        passes: list[dict[str, Any]] = []
        prior_findings = ""
        fallback_used = False
        prior_limit = max(2200, min(6000, eff_ctx_budget // 2))
        ref_limit = max(1800, min(5000, eff_ctx_budget // 2))

        for idx in range(n_loops):
            chosen_model = model_chain[min(idx, len(model_chain) - 1)]
            role = "local_router" if (n_loops >= 3 and idx == 0) else ("local_analyst" if idx == 0 or (n_loops >= 3 and idx == 1) else ("local_synthesizer" if idx == n_loops - 1 else f"local_loop_{idx + 1}"))
            sys_p = (
                "You are Cortical's offline multi-model reasoning agent (0 remote tokens). "
                "Reply thoroughly and concisely in the prompt language using ONLY grounded context. Do NOT re-introduce raw PII."
            )
            if idx == 0:
                usr_p = (
                    f"[PASS 1/{n_loops} · ARCHITECTURE & GROUNDING]\n"
                    f"Task (privacy={eff_privacy}): {clean_goal}\n\n"
                    f"Grounded Context (Wiki + Skills + Sanitized Files):\n{context_bundle}\n\n"
                    f"Produce: (1) Key findings & modules/sections involved, (2) Structured outline or full draft deliverable, "
                    f"(3) A 1-sentence INSIGHT candidate."
                )
            else:
                usr_p = (
                    f"[PASS {idx + 1}/{n_loops} · DISTILLATION & LOCAL COMPLETION GATE]\n"
                    f"Task (privacy={eff_privacy}): {clean_goal}\n\n"
                    f"Prior Local Pass Findings:\n{prior_findings[:prior_limit]}\n\n"
                    f"Grounded Reference Context:\n{context_bundle[:ref_limit]}\n\n"
                    f"Refine and produce the complete, verified deliverable, start the distilled rule with `INSIGHT:`, and end with "
                    f"`NEEDS_CLOUD: NO` if the task is resolved locally or `NEEDS_CLOUD: YES (<reason>)` only if impossible offline."
                )

            t0 = time.perf_counter()
            answer = ""
            if llm_fn is not None:
                answer = str(llm_fn(chosen_model, usr_p) or "").strip()
                elapsed = round(time.perf_counter() - t0, 2)
                in_tok = max(1, (len(sys_p) + len(usr_p)) // 4)
                out_tok = max(1, len(answer) // 4)
                _record_runner_telemetry(
                    model=chosen_model,
                    runner_name="local_loop",
                    role=role,
                    prompt=clean_goal,
                    in_tok=in_tok,
                    out_tok=out_tok,
                    elapsed_sec=elapsed,
                    episode_id=ep_id,
                    db_path=self.wiki_db.db_path,
                )
            else:
                try:
                    answer = invoke_configured_runner(
                        usr_p,
                        system_prompt=sys_p,
                        config=cfg,
                        model_override=chosen_model,
                        max_tokens=int(max_tokens),
                        timeout=float(timeout),
                        num_ctx=num_ctx,
                        role=role,
                        episode_id=ep_id,
                        db_path=self.wiki_db.db_path,
                    )
                    elapsed = round(time.perf_counter() - t0, 2)
                    in_tok = max(1, (len(sys_p) + len(usr_p)) // 4)
                    out_tok = max(1, len(answer) // 4)
                except Exception:  # noqa: BLE001
                    fallback_used = True
                    elapsed = round(time.perf_counter() - t0, 2)
                    answer = (
                        f"[Fallback Deterministico Locale ({chosen_model})] Contesto analizzato su {len(refs['resolved'])} riferimenti Wiki "
                        f"e {len(matched_skills)} skill.\nINSIGHT: Contesto localizzato offline su {clean_goal[:90]}.\nNEEDS_CLOUD: NO"
                    )
                    in_tok = max(1, (len(sys_p) + len(usr_p)) // 4)
                    out_tok = max(1, len(answer) // 4)
            prior_findings = answer
            passes.append({
                "pass": idx + 1,
                "model": chosen_model,
                "role": role,
                "elapsed_sec": elapsed,
                "in_tokens_est": in_tok,
                "out_tokens_est": out_tok,
                "output_chars": len(answer),
                "output": answer,
            })

        final_answer = passes[-1]["output"] if passes else ""
        m_ins = re.search(r"INSIGHT:\s*(.+)", final_answer, re.IGNORECASE)
        distilled_insight = (m_ins.group(1).strip() if m_ins else f"Local loop ({' -> '.join(p['model'] for p in passes)}): {clean_goal[:110]}")[:320]
        now = time.time()
        ins_id = "ins-" + hashlib.sha256(f"{ep_id}:{distilled_insight}".encode("utf-8")).hexdigest()[:10]
        with self.wiki_db._connect() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS memory_insights (
                       insight_id TEXT PRIMARY KEY,
                       tenant_id TEXT NOT NULL,
                       workspace_id TEXT NOT NULL,
                       category TEXT NOT NULL,
                       insight_text TEXT NOT NULL,
                       related_path TEXT NOT NULL DEFAULT '/',
                       created_at REAL NOT NULL
                   )"""
            )
            conn.execute(
                """INSERT OR REPLACE INTO memory_insights(
                       insight_id, tenant_id, workspace_id, category, insight_text, related_path, created_at
                   ) VALUES (?, ?, ?, 'local_loop_distillation', ?, ?, ?)""",
                (ins_id, access_ctx.tenant_id, access_ctx.workspace_id, distilled_insight, refs["resolved"][0]["ref"] if refs["resolved"] else "/", now),
            )

        cloud_flag = bool(re.search(r"NEEDS_CLOUD:\s*YES", final_answer, re.IGNORECASE))
        needs_remote = False if eff_force_local else cloud_flag

        ep_runs = self.wiki_db.list_agent_runs(access_ctx, episode_id=ep_id, limit=50)
        tot_loc_tok = sum(int(r.get("total_tokens") or 0) for r in ep_runs) or sum(p["in_tokens_est"] + p["out_tokens_est"] for p in passes)
        tot_elapsed = round(sum(float(p.get("elapsed_sec") or 0.0) for p in passes), 2)

        sanitized_remote_prompt = (
            f"=== CORTICAL PRIVACY-SAFE DISTILLED BRIEF ({eff_privacy}) ===\n"
            f"Sanitized Objective: {clean_goal}\n\n"
            f"Resolved Wiki & Skills Contracts ({len(refs['resolved'])} refs):\n{context_bundle[:1800]}\n\n"
            f"Distilled Local Conclusions ({len(passes)} local passes across {', '.join(p['model'] for p in passes)}):\n"
            f"{final_answer[:1800]}\n\n"
            f"Distilled Rule: {distilled_insight}\n"
        )
        if eff_force_local:
            sanitized_remote_prompt = (
                "[BLOCKED BY MAX_SECURITY / /local POLICY: Remote cloud forwarding disabled; "
                "use `local_answer` directly on-device.]"
            )

        return {
            "episode_id": ep_id,
            "privacy_profile": eff_privacy,
            "force_local_only": eff_force_local,
            "completed_locally": not needs_remote,
            "needs_remote_escalation": needs_remote,
            "recommended_action": "use_local_answer" if not needs_remote else "send_sanitized_remote_prompt",
            "fallback_used": fallback_used,
            "models_used": [p["model"] for p in passes],
            "total_local_tokens": tot_loc_tok,
            "total_elapsed_sec": tot_elapsed,
            "passes": passes,
            "resolved_references": refs["resolved"],
            "distilled_insight_id": ins_id,
            "distilled_insight": distilled_insight,
            "pseudonymized_entities": len(goal_map),
            "local_answer": final_answer,
            "sanitized_remote_prompt": sanitized_remote_prompt,
        }
