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
        "tools": ["meteo_forecast", "chrome-devtools", "bash"],
        "mission": "Esegue azioni reali sul browser / API esterne (Open-Meteo, Chrome DevTools) senza allucinare dati.",
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

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["recommended_depth"] = self.recommended_wiki_depth
        d["context_injection"] = self.enhanced_system_instructions
        return d

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.to_dict().get(key, default)


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
                "modern-web-guidance": ["meteo_forecast", "chrome-devtools"],
                "browser-use-playwright": ["meteo_forecast", "chrome-devtools", "bash"],
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
    ) -> PromptEnhancementResult:
        """Enhances a user prompt with right-sized 3+1 Wiki Memory + matched Procedural Skills + Tools."""
        access_ctx = ctx or AccessContext()
        depth = self.choose_wiki_depth(prompt)
        matched = self.rank_skills_for_prompt(prompt, limit=3)

        # Always include the matching 3+1 Memory Tier skill in parallel with domain skills
        tier_skill_map = {
            DepthTier.LIGHT: "cortical-memory-l1-light",
            DepthTier.MEDIUM: "cortical-memory-l2-medium",
            DepthTier.HIGH: "cortical-memory-l3-high",
            DepthTier.MAX: "cortical-memory-l3-high",
        }
        target_tier_skill = tier_skill_map[depth]
        selected_skills = [sk for sk, _ in matched]
        if not any(s.skill_id == target_tier_skill for s in selected_skills):
            for s in self.list_skills():
                if s.skill_id == target_tier_skill:
                    selected_skills.append(s)
                    break

        tools: list[str] = []
        for s in selected_skills:
            for t in s.recommended_tools:
                if t not in tools:
                    tools.append(t)

        # Fetch non-lossy 3+1 Wiki context at the chosen tier
        hits = self.wiki_db.search(access_ctx, query=prompt, depth=depth, limit=3)
        if hits:
            wiki_block = "\n\n".join(
                f"### [Wiki {h['depth_tier'].upper()}] {h['path']}\n{h['content']}"
                for h in hits
            )
        else:
            try:
                root_nav = self.wiki_db.navigate(access_ctx, path="/", depth=DepthTier.LIGHT)
                wiki_block = f"### [Wiki LIGHT Root Index]\n{root_nav.get('content', '')}"
            except Exception:  # noqa: BLE001
                wiki_block = "Nessun nodo Wiki ancora indicizzato."

        team_roster = self.resolve_team_roster(prompt)
        skills_playbook = "\n\n".join(
            f"#### Skill Attiva: `{s.name}` ({s.kind})\n{s.full_body[:900]}"
            for s in selected_skills[:3]
        )
        roster_text = "\n".join(
            f"- **{r['name']}** (Wiki `{r['wiki_depth']}`, Tools: `{', '.join(r['tools'])}`): {r['mission']}"
            for r in team_roster
        )

        enhanced_instructions = (
            f"=== CORTICAL HARNESS — Orchestratore Multi-Agent & 3+1 Second Brain ===\n"
            f"Rispondi sempre in italiano chiaro e tecnicamente rigoroso.\n\n"
            f"=== 1. CONTESTO MEMORIA WIKI (Livello 3+1 selezionato: {depth.value.upper()}) ===\n"
            f"{wiki_block}\n\n"
            f"=== 2. SKILL PROCEDURALI ATTIVATE IN PARALLELO ===\n"
            f"{skills_playbook}\n\n"
            f"=== 3. TOOL CONSIGLIATI & RUOLI MULTI-AGENTE ===\n"
            f"Tool prioritari: {', '.join(tools)}\n"
            f"{roster_text}\n"
        )

        proc_names = [s.name for s in selected_skills if s.kind != "memory_tier"]
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
    ) -> dict[str, str]:
        """Synthesizes a task's discussion at 3+1 levels (L1 Light, L2 Medium, L3 High, +1 Max) in parallel."""
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

        # L1 Light (~50 tokens): 1-2 sentence executive trace
        lessons = user_closing_notes.strip() or (
            resolved_steps[-1].get("detail", "")[:180] if resolved_steps else resolved_goal
        )
        lessons_clean = re.sub(r"\s+", " ", lessons).strip()[:200]
        tier_l1 = f"[L1 LIGHT] Task '{resolved_goal[:70]}' completato. Lezione chiave: {lessons_clean}"

        # L2 Medium (~250 tokens): Goal + Key Steps + Outcome
        step_titles = [f"• {st.get('title', '')}" for st in resolved_steps[:6] if st.get("title")]
        tier_l2 = (
            f"[L2 MEDIUM] Task {episode_id} — Obiettivo: {resolved_goal}\n"
            f"Passaggi eseguiti ({len(resolved_steps)} totali):\n"
            + ("\n".join(step_titles) if step_titles else "• Esecuzione diretta")
            + f"\nLezione consolidata: {lessons_clean}"
        )

        # L3 High (~1000 tokens): Detailed technical synthesis
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
    ) -> SkillEvaluationResult:
        """Evaluates whether a completed task warrants creating a reusable Skill (`SKILL.md`) for the future."""
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

        # Heuristic + LLM check: create a skill if force_create is True OR if the task encodes a reusable
        # engineering pattern/procedure (at least 5 meaningful terms and actionable keywords).
        reusable_signals = (
            "pattern", "procedura", "regola", "standard", "workflow", "architettura",
            "sempre", "quando", "skill", "pipeline", "test", "verifica", "mcp", "wiki",
            "analizza", "ottimizza", "integra", "configura",
        )
        norm = combined.lower()
        is_worthy = force_create or (
            len(terms) >= 4 and any(sig in norm for sig in reusable_signals)
        )

        if not is_worthy:
            return SkillEvaluationResult(
                episode_id=episode_id,
                should_create_skill=False,
                reason="Il task riguarda un'operazione puntuale e non richiede una nuova Skill procedurale permanente.",
            )

        slug_words = [w for w in re.findall(r"[a-z0-9]+", normalize_text(goal)) if w not in STOP_WORDS and len(w) > 2][:4]
        slug_base = "-".join(slug_words) if slug_words else f"task-{episode_id.lower()}"
        skill_id = f"learned-{slug_base}"
        skill_dir = self.skills_root / skill_id
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_path = skill_dir / "SKILL.md"

        steps_summary = "\n".join(
            f"{i+1}. {st.get('title', 'Step')}"
            for i, st in enumerate((discussion_steps or [])[:5])
            if st.get("title")
        ) or "1. Consulta la Wiki MCP a livello `medium`.\n2. Applica il pattern verificato.\n3. Verifica con test single-shot."

        skill_md = (
            f"---\n"
            f"name: {skill_id}\n"
            f"description: Skill appresa dal task {episode_id} ({goal[:80]}). Usa quando affronti compiti simili su {', '.join(slug_words)}.\n"
            f"---\n\n"
            f"# Skill Appresa: {goal[:70]}\n\n"
            f"## Contesto & Origine\n"
            f"- **Task Sorgente:** `{episode_id}`\n"
            f"- **Obiettivo Originario:** {goal}\n\n"
            f"## Lezione Chiave Consolidata\n"
            f"{lessons_learned or goal}\n\n"
            f"## Procedura Riutilizzabile\n"
            f"{steps_summary}\n\n"
            f"## Verifica\n"
            f"- Controlla la coerenza con la Wiki 3+1 (`wiki_navigate` / `wiki_search`) ed esegui i test in un unico colpo.\n"
        )
        skill_path.write_text(skill_md, encoding="utf-8")

        with self.wiki_db._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO learned_skills_registry(
                       skill_id, tenant_id, workspace_id, name, description,
                       skill_path, source_episode_id, use_count, helpful_count, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, ?)""",
                (
                    skill_id,
                    access_ctx.tenant_id,
                    access_ctx.workspace_id,
                    skill_id,
                    f"Skill appresa dal task {episode_id}: {goal[:80]}",
                    str(skill_path),
                    episode_id,
                    time.time(),
                ),
            )

        return SkillEvaluationResult(
            episode_id=episode_id,
            should_create_skill=True,
            reason=f"Creata nuova Skill riutilizzabile '{skill_id}' dalle lezioni apprese nel task {episode_id}.",
            skill_id=skill_id,
            skill_path=str(skill_path),
            skill_markdown=skill_md,
        )
