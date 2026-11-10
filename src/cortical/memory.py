"""Smart Conversational Memory, Local LLM Memory Curator & Task-Isolated Lifecycle.

Implements the user's memory architecture:
1. Bounded Generic Chat Buffer (`chat_buffer`, auto-pruned to max 20 turns):
   Everyday chitchat, clock checks ("che ore sono"), weather lookups ("meteo a Roma domani"),
   and quick searches are classified as `ephemeral` and NEVER bloat long-term memory.
2. Intelligent Local LLM Memory Curator (`MemoryCurator`):
   Evaluates whether a conversational turn contains a durable insight (architectural choice,
   user preference, project rule) before storing a compact `memory_insights` node.
3. Explicit-Only Tasks with Task-Isolated Working Memory (`task_isolated_notes`):
   - Tasks are created ONLY when explicitly requested by the user.
   - Working notes stay isolated inside the task until the user archives it.
   - At task closure (`prepare_task_closure`), Cortical generates 1-2 closing questions.
   - Upon archival (`archive_task`), working notes are purged and only a compact trace
     (`archived_trace`, ~50 tokens) + high-level Macro-Graph edges are kept.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from .wiki.db import AccessContext, CorticalWikiDB

EPHEMERAL_PATTERNS = [
    r"\bche\s+or[ae]\b",
    r"\bche\s+giorno\b",
    r"\bmeteo\b",
    r"\bche\s+tempo\s+fa\b",
    r"\bprevisioni\b",
    r"\btemperatura\b",
    r"\bcercami\b",
    r"\bcerca\s+su\s+chrome\b",
    r"\bcome\s+stai\b",
    r"\bciao\b",
    r"\bbuongiorno\b",
    r"\bbuonasera\b",
    r"\bgrazie\b",
    r"\bbasta\b",
    r"\bstop\b",
    r"\bfermati\b",
]

DURABLE_MEMORY_TRIGGERS = (
    "ricorda che",
    "ricordati che",
    "salva in memoria",
    "nota importante",
    "decisione architetturale",
    "standard di progetto",
    "preferisco",
    "usa sempre",
    "non usare mai",
)

EXPLICIT_TASK_TRIGGERS = (
    "crea un task",
    "crea task",
    "nuovo task",
    "avvia un task",
    "apri un task",
    "orchestra un sottoagente",
    "delega a un agente",
)


def is_ephemeral_utterance(text: str) -> bool:
    """Returns True for everyday transient queries (time, weather, greetings, quick lookups)."""
    norm = text.lower().strip()
    if len(norm.split()) <= 3 and not any(t in norm for t in DURABLE_MEMORY_TRIGGERS):
        return True
    for pat in EPHEMERAL_PATTERNS:
        if re.search(pat, norm):
            return True
    return False


def is_explicit_task_request(text: str) -> bool:
    """Returns True ONLY when the user explicitly requests creating/starting a task."""
    norm = text.lower().strip()
    return any(trigger in norm for trigger in EXPLICIT_TASK_TRIGGERS)


@dataclass
class CurationDecision:
    worth_saving: bool
    category: str  # 'ephemeral' | 'user_preference' | 'architecture_decision' | 'project_fact'
    distilled_insight: str
    related_path: str = "/"


class MemoryCurator:
    """Filters everyday chat and extracts only compact durable insights for the Second Brain."""

    def __init__(
        self,
        db: CorticalWikiDB,
        llm_curator_fn: Optional[Callable[[str, str], CurationDecision]] = None,
        llm_fn: Optional[Callable[[str], str]] = None,
        max_chat_turns: int = 20,
    ) -> None:
        self.db = db
        self.llm_curator_fn = llm_curator_fn
        self.llm_fn = llm_fn
        self.max_chat_turns = max_chat_turns
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        with self.db._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS chat_buffer (
                    turn_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    user_text TEXT NOT NULL,
                    assistant_text TEXT NOT NULL,
                    is_ephemeral INTEGER NOT NULL DEFAULT 1,
                    created_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS memory_insights (
                    insight_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    insight_text TEXT NOT NULL,
                    related_path TEXT NOT NULL DEFAULT '/',
                    created_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS task_isolated_notes (
                    note_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    episode_id TEXT NOT NULL,
                    step_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                """
            )
            cols = {
                r["name"]
                for r in conn.execute("PRAGMA table_info(task_episodes)").fetchall()
            }
            if "lifecycle_state" not in cols:
                conn.execute(
                    "ALTER TABLE task_episodes ADD COLUMN lifecycle_state TEXT NOT NULL DEFAULT 'active'"
                )
            if "archived_trace" not in cols:
                conn.execute(
                    "ALTER TABLE task_episodes ADD COLUMN archived_trace TEXT NOT NULL DEFAULT ''"
                )
            if "closing_questions_json" not in cols:
                conn.execute(
                    "ALTER TABLE task_episodes ADD COLUMN closing_questions_json TEXT NOT NULL DEFAULT '[]'"
                )

    def evaluate_turn(self, user_text: str, assistant_text: str) -> CurationDecision:
        if is_ephemeral_utterance(user_text):
            return CurationDecision(
                worth_saving=False,
                category="ephemeral",
                distilled_insight="",
            )

        if self.llm_curator_fn is not None:
            return self.llm_curator_fn(user_text, assistant_text)

        norm = user_text.lower()
        if any(t in norm for t in DURABLE_MEMORY_TRIGGERS):
            cat = "user_preference" if "preferisco" in norm or "usa sempre" in norm else "architecture_decision"
            distilled = re.sub(r"\s+", " ", user_text).strip()[:220]
            if self.llm_fn is not None:
                try:
                    raw = self.llm_fn(
                        f"Estrai in 1 frase la regola o preferenza da memorizzare: {user_text}"
                    )
                    if raw.strip().startswith("{"):
                        parsed = json.loads(raw.strip())
                        if parsed.get("insight"):
                            distilled = str(parsed["insight"])[:220]
                except Exception:  # noqa: BLE001
                    pass
            return CurationDecision(
                worth_saving=True,
                category=cat,
                distilled_insight=distilled,
                related_path="/",
            )

        return CurationDecision(
            worth_saving=False,
            category="ephemeral",
            distilled_insight="",
        )

    def record_chat_turn(
        self,
        ctx_or_user: AccessContext | str,
        user_or_assistant: str,
        assistant_optional: Optional[str] = None,
    ) -> dict[str, Any]:
        """Stores turn in bounded rolling buffer (`max_chat_turns`) and curates durable insights."""
        if isinstance(ctx_or_user, AccessContext):
            ctx = ctx_or_user
            user_text = user_or_assistant
            assistant_text = assistant_optional or ""
        else:
            ctx = AccessContext()
            user_text = ctx_or_user
            assistant_text = user_or_assistant

        decision = self.evaluate_turn(user_text, assistant_text)
        now = time.time()
        with self.db._connect() as conn:
            conn.execute(
                """INSERT INTO chat_buffer(
                       tenant_id, workspace_id, user_text, assistant_text, is_ephemeral, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    ctx.tenant_id,
                    ctx.workspace_id,
                    user_text[:600],
                    assistant_text[:800],
                    0 if decision.worth_saving else 1,
                    now,
                ),
            )
            conn.execute(
                """DELETE FROM chat_buffer
                   WHERE tenant_id = ? AND workspace_id = ?
                     AND turn_id NOT IN (
                         SELECT turn_id FROM chat_buffer
                         WHERE tenant_id = ? AND workspace_id = ?
                         ORDER BY turn_id DESC LIMIT ?
                     )""",
                (
                    ctx.tenant_id,
                    ctx.workspace_id,
                    ctx.tenant_id,
                    ctx.workspace_id,
                    self.max_chat_turns,
                ),
            )

            insight_id = None
            if decision.worth_saving and decision.distilled_insight:
                insight_id = "ins-" + hashlib.sha256(
                    decision.distilled_insight.encode("utf-8")
                ).hexdigest()[:10]
                conn.execute(
                    """INSERT OR REPLACE INTO memory_insights(
                           insight_id, tenant_id, workspace_id, category,
                           insight_text, related_path, created_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        insight_id,
                        ctx.tenant_id,
                        ctx.workspace_id,
                        decision.category,
                        decision.distilled_insight,
                        decision.related_path,
                        now,
                    ),
                )
                conn.execute(
                    """INSERT OR REPLACE INTO macro_edges(
                           tenant_id, workspace_id, source_type, source_id,
                           relation, target_type, target_id, weight, metadata_json, created_at
                       ) VALUES (?, ?, 'episode', ?, 'relates_to', 'subtree', ?, 1.0, ?, ?)""",
                    (
                        ctx.tenant_id,
                        ctx.workspace_id,
                        insight_id,
                        decision.related_path,
                        json.dumps({"kind": "curated_insight", "category": decision.category}),
                        now,
                    ),
                )

        return {
            "is_ephemeral": not decision.worth_saving,
            "curated_saved": decision.worth_saving,
            "worth_saving": decision.worth_saving,
            "category": decision.category,
            "insight_id": insight_id,
            "distilled_insight": decision.distilled_insight,
        }

    def get_recent_chat(self, limit: int = 20, ctx: Optional[AccessContext] = None) -> list[dict[str, Any]]:
        c = ctx or AccessContext()
        with self.db._connect() as conn:
            rows = conn.execute(
                """SELECT turn_id, user_text, assistant_text, is_ephemeral, created_at
                   FROM chat_buffer
                   WHERE tenant_id = ? AND workspace_id = ?
                   ORDER BY turn_id DESC LIMIT ?""",
                (c.tenant_id, c.workspace_id, limit),
            ).fetchall()
            return [dict(r) for r in reversed(rows)]

    def list_insights(self, limit: int = 25, ctx: Optional[AccessContext] = None) -> list[dict[str, Any]]:
        c = ctx or AccessContext()
        with self.db._connect() as conn:
            rows = conn.execute(
                """SELECT insight_id, category, insight_text, related_path, created_at
                   FROM memory_insights
                   WHERE tenant_id = ? AND workspace_id = ?
                   ORDER BY created_at DESC LIMIT ?""",
                (c.tenant_id, c.workspace_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def add_task_working_note(
        self,
        episode_id: str,
        detail: str,
        step_type: str = "note",
        title: str = "Working Note",
        ctx: Optional[AccessContext] = None,
    ) -> None:
        c = ctx or AccessContext()
        with self.db._connect() as conn:
            conn.execute(
                """INSERT INTO task_isolated_notes(
                       tenant_id, workspace_id, episode_id, step_type, title, detail, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (c.tenant_id, c.workspace_id, episode_id, step_type, title, detail, time.time()),
            )

    def get_task_working_notes(
        self,
        episode_id: str,
        ctx: Optional[AccessContext] = None,
    ) -> list[dict[str, Any]]:
        c = ctx or AccessContext()
        with self.db._connect() as conn:
            rows = conn.execute(
                """SELECT note_id, episode_id, step_type, title, detail, created_at
                   FROM task_isolated_notes
                   WHERE tenant_id = ? AND workspace_id = ? AND episode_id = ?
                   ORDER BY note_id ASC""",
                (c.tenant_id, c.workspace_id, episode_id),
            ).fetchall()
            return [dict(r) for r in rows]

    def prepare_task_closure(
        self,
        ctx_or_ep: AccessContext | str,
        episode_id_optional: Optional[str] = None,
    ) -> dict[str, Any]:
        """Generates 1-2 closing questions before archiving an active task."""
        if isinstance(ctx_or_ep, AccessContext):
            ctx = ctx_or_ep
            episode_id = episode_id_optional or ""
        else:
            ctx = AccessContext()
            episode_id = ctx_or_ep

        with self.db._connect() as conn:
            ep = conn.execute(
                """SELECT * FROM task_episodes
                   WHERE tenant_id = ? AND workspace_id = ? AND episode_id = ?""",
                (ctx.tenant_id, ctx.workspace_id, episode_id),
            ).fetchone()
            if not ep:
                raise KeyError(f"Task '{episode_id}' not found.")

            notes_cnt = conn.execute(
                """SELECT COUNT(*) AS cnt FROM task_isolated_notes
                   WHERE tenant_id = ? AND workspace_id = ? AND episode_id = ?""",
                (ctx.tenant_id, ctx.workspace_id, episode_id),
            ).fetchone()["cnt"]

            questions = [
                f"Quale lezione o decisione chiave del task '{ep['title']}' vuoi salvare nella traccia permanente?",
                "Vuoi collegare questo risultato a un nodo specifico della Wiki (es. / o /src) prima di eliminare i log intermedi?",
            ]
            conn.execute(
                """UPDATE task_episodes
                   SET lifecycle_state = 'closing_review',
                       closing_questions_json = ?
                   WHERE tenant_id = ? AND workspace_id = ? AND episode_id = ?""",
                (json.dumps(questions), ctx.tenant_id, ctx.workspace_id, episode_id),
            )
        return {
            "episode_id": episode_id,
            "lifecycle_state": "closing_review",
            "working_notes_count": int(notes_cnt),
            "closing_questions": questions,
        }

    def archive_task(
        self,
        ctx_or_ep: AccessContext | str,
        episode_id_optional: Optional[str] = None,
        user_closing_answer: str = "",
        user_closing_notes: str = "",
        target_subtree: str = "/",
    ) -> dict[str, Any]:
        """Purges isolated working notes of the task and stores only a compact trace + macro edge."""
        if isinstance(ctx_or_ep, AccessContext):
            ctx = ctx_or_ep
            episode_id = episode_id_optional or ""
        else:
            ctx = AccessContext()
            episode_id = ctx_or_ep

        closing_note = (user_closing_notes or user_closing_answer).strip()
        now = time.time()
        with self.db._connect() as conn:
            ep = conn.execute(
                """SELECT * FROM task_episodes
                   WHERE tenant_id = ? AND workspace_id = ? AND episode_id = ?""",
                (ctx.tenant_id, ctx.workspace_id, episode_id),
            ).fetchone()
            if not ep:
                raise KeyError(f"Task '{episode_id}' not found.")

            raw_trace = closing_note or ep["learned_summary"] or ep["goal"]
            compact_trace = re.sub(r"\s+", " ", raw_trace)[:180]

            deleted_notes = conn.execute(
                """DELETE FROM task_isolated_notes
                   WHERE tenant_id = ? AND workspace_id = ? AND episode_id = ?""",
                (ctx.tenant_id, ctx.workspace_id, episode_id),
            ).rowcount

            conn.execute(
                """UPDATE task_episodes
                   SET lifecycle_state = 'archived',
                       outcome_status = 'archived',
                       archived_trace = ?,
                       learned_summary = ?
                   WHERE tenant_id = ? AND workspace_id = ? AND episode_id = ?""",
                (
                    compact_trace,
                    compact_trace,
                    ctx.tenant_id,
                    ctx.workspace_id,
                    episode_id,
                ),
            )

            conn.execute(
                """INSERT OR REPLACE INTO macro_edges(
                       tenant_id, workspace_id, source_type, source_id,
                       relation, target_type, target_id, weight, metadata_json, created_at
                   ) VALUES (?, ?, 'episode', ?, 'relates_to', 'subtree', ?, 1.0, ?, ?)""",
                (
                    ctx.tenant_id,
                    ctx.workspace_id,
                    episode_id,
                    target_subtree or "/",
                    json.dumps({"archived_trace": compact_trace}),
                    now,
                ),
            )

        return {
            "status": "archived",
            "episode_id": episode_id,
            "lifecycle_state": "archived",
            "archived_trace": compact_trace,
            "purged_working_notes": deleted_notes,
            "isolated_notes_purged": deleted_notes,
            "linked_subtree": target_subtree or "/",
        }
