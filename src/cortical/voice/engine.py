"""Cortical Dual-Path Voice Engine (System 1 Fast Reflex + System 2 Agentic Delegation).

Upgrades and generalizes Peppe's voice capabilities for cross-platform (macOS + Linux) operation:
1. Resilient Wake-Word & Stop/Barge-In Detection (`is_stop_command`):
   Handles Whisper/WebSpeech variations ("hei cortical", "ehi cortical", "hey cortical",
   "ba sta", "fer ma ti") and immediately stops active TTS/agents.
2. Instant Built-in Italian Reflexes (< 5ms):
   Answers clock/time ("che ore sono"), date ("che giorno è"), system status, and
   voice permission confirmations without waiting for an LLM roundtrip.
3. Dual-Path Routing:
   - System 1 (Fast Reflex < 1s): Direct voice queries, web grounding, and subagent status checks.
   - System 2 (Async Agentic Orchestrator): Multi-step coding, browser automation, or deep Wiki
     tasks are delegated in background to `pi` while immediately acknowledging by voice.
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass
from typing import Any, Callable, Optional

from ..permissions.gate import AdaptivePermissionGate
from ..wiki.db import AccessContext, CorticalWikiDB

WAKE_PREFIXES = (
    "ehi cortical",
    "hei cortical",
    "hey cortical",
    "ei cortical",
    "ai cortical",
    "ciao cortical",
    "ok cortical",
    "cortical",
    "ehi peppe",
    "hei peppe",
    "hey peppe",
    "peppe",
)

STOP_EXACT_WORDS = {
    "basta",
    "stop",
    "fermati",
    "ferma",
    "silenzio",
    "zitto",
    "annulla",
    "taci",
    "chiudi",
}

STOP_SYLLABLE_PATTERNS = [
    r"\bba\s*sta\b",
    r"\bfer\s*ma(?:\s*ti)?\b",
    r"\bsi\s*len\s*zio\b",
    r"\ban\s*nul\s*la\b",
    r"\bstop\b",
]

AGENTIC_INTENT_KEYWORDS = (
    "orchestra",
    "sottoagente",
    "subagent",
    "agente",
    "refactoring",
    "implementa",
    "scrivi codice",
    "modifica il file",
    "crea un file",
    "apri chrome",
    "compila il form",
    "candidatura",
    "indicizza",
    "crawla",
    "analizza il progetto",
    "analizza il codice",
    "esegui i test",
    "lancia pi",
    "usa pi",
)

GIORNI_SETTIMANA = (
    "lunedì",
    "martedì",
    "mercoledì",
    "giovedì",
    "venerdì",
    "sabato",
    "domenica",
)

MESI_ANNO = (
    "",
    "gennaio",
    "febbraio",
    "marzo",
    "aprile",
    "maggio",
    "giugno",
    "luglio",
    "agosto",
    "settembre",
    "ottobre",
    "novembre",
    "dicembre",
)


def _clean_transcript(text: str) -> str:
    cleaned = re.sub(r"[^\w\s]", " ", text.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def strip_wake_word(text: str) -> tuple[bool, str]:
    """Strips wake word if present (including 'hei/ehi/hey cortical'); returns (had_wake_word, remaining_command)."""
    norm = _clean_transcript(text)
    for prefix in WAKE_PREFIXES:
        if norm == prefix:
            return (True, "")
        if norm.startswith(prefix + " "):
            return (True, norm[len(prefix) :].strip())
    # Fuzzy match if wake word appears after a greeting word like "allora hei cortical ..."
    m = re.match(r"^(?:allora\s+| senti\s+)?(?:ehi|hei|hey|ei|ciao|ok)?\s*cortical\b\s*(.*)$", norm)
    if m:
        return (True, m.group(1).strip())
    return (False, norm)


def is_stop_command(text: str) -> bool:
    """Resilient barge-in / stop detector tolerant of Whisper syllable splits and filler prefixes."""
    _, remainder = strip_wake_word(text)
    tokens = [
        t
        for t in remainder.split()
        if t not in {"ehi", "hei", "hey", "ok", "per", "favore", "ora", "subito"}
    ]
    if not tokens:
        return False

    joined = " ".join(tokens)
    if len(tokens) <= 4:
        if any(t in STOP_EXACT_WORDS for t in tokens):
            return True
        for pat in STOP_SYLLABLE_PATTERNS:
            if re.search(pat, joined):
                return True
    return False


@dataclass
class VoiceRouteResult:
    route: str  # 'stop' | 'permission_feedback' | 'status_report' | 'system1_reflex' | 'system2_agentic'
    spoken_response: str
    dispatched_task_goal: Optional[str] = None
    permission_updated: Optional[str] = None


class CorticalVoiceEngine:
    """Dual-path voice coordinator connecting STT/TTS to System 1 Reflex and System 2 `pi` Orchestrator."""

    def __init__(
        self,
        wiki_db: Optional[CorticalWikiDB] = None,
        permission_gate: Optional[AdaptivePermissionGate] = None,
        reflex_llm_fn: Optional[Callable[[str], str]] = None,
        agentic_dispatch_fn: Optional[Callable[[str], str]] = None,
        stop_callback: Optional[Callable[[], None]] = None,
    ) -> None:
        self.wiki_db = wiki_db
        self.permission_gate = permission_gate
        self.reflex_llm_fn = reflex_llm_fn
        self.agentic_dispatch_fn = agentic_dispatch_fn or (
            lambda goal: f"task-{abs(hash(goal)) % 10000}"
        )
        self.stop_callback = stop_callback
        self.pending_permission: Optional[tuple[str, dict[str, Any]]] = None
        self.active_background_tasks: dict[str, str] = {}

    def register_pending_permission(self, tool_name: str, args: dict[str, Any]) -> None:
        self.pending_permission = (tool_name, args)

    def _instant_builtin_reflex(self, cmd: str) -> Optional[str]:
        """Handles clock, date, and identity questions deterministically in <5ms if not overridden."""
        now = datetime.datetime.now()
        if any(p in cmd for p in ("che ore sono", "che ora e", "che ora è", "dimmi l ora")):
            giorno = GIORNI_SETTIMANA[now.weekday()]
            mese = MESI_ANNO[now.month]
            return f"Sono le {now.strftime('%H:%M')} di {giorno} {now.day} {mese}."
        if any(p in cmd for p in ("che giorno e", "che giorno è", "data di oggi", "quanti ne abbiamo")):
            giorno = GIORNI_SETTIMANA[now.weekday()]
            mese = MESI_ANNO[now.month]
            return f"Oggi è {giorno} {now.day} {mese} {now.year}."
        return None

    def handle_utterance(self, transcript: str) -> VoiceRouteResult:
        """Routes a transcribed voice utterance through Stop -> Permission -> Status -> System 1/2."""
        if is_stop_command(transcript):
            if self.stop_callback:
                self.stop_callback()
            return VoiceRouteResult(
                route="stop",
                spoken_response="Ricevuto, mi fermo subito.",
            )

        _, cmd = strip_wake_word(transcript)
        if not cmd:
            return VoiceRouteResult(
                route="system1_reflex",
                spoken_response="Sono in ascolto, dimmi pure.",
            )

        # 1. Voice approval/rejection for Adaptive Permission Gate
        if self.pending_permission and any(
            w in cmd for w in ("approva", "consenti", "autorizza", "rifiuta", "blocca", "nega")
        ):
            tool_name, args = self.pending_permission
            approved = any(w in cmd for w in ("approva", "consenti", "autorizza"))
            remember = "ricorda" in cmd or "sempre" in cmd
            self.pending_permission = None
            if self.permission_gate:
                dec = self.permission_gate.record_user_feedback(
                    tool_name, args, approved=approved, remember_always=remember
                )
                spoken = (
                    f"Permesso accordato per {dec.normalized_pattern}."
                    if approved
                    else f"Operazione {dec.normalized_pattern} bloccata."
                )
                return VoiceRouteResult(
                    route="permission_feedback",
                    spoken_response=spoken,
                    permission_updated=dec.verdict,
                )

        # 2. Subagent / Episode status check
        if any(p in cmd for p in ("a che punto", "stato dei lavori", "stato agenti", "progressi")):
            if self.active_background_tasks:
                summary = ", ".join(f"{tid}: {st}" for tid, st in self.active_background_tasks.items())
                return VoiceRouteResult(
                    route="status_report",
                    spoken_response=f"Ho {len(self.active_background_tasks)} task attivi: {summary}.",
                )
            if self.wiki_db:
                macro = self.wiki_db.query_macro_graph(AccessContext(), limit=1)
                if macro["episodes"]:
                    last = macro["episodes"][0]
                    return VoiceRouteResult(
                        route="status_report",
                        spoken_response=f"Ultimo task completato: {last['title']} con esito {last['outcome_status']}.",
                    )
            return VoiceRouteResult(
                route="status_report",
                spoken_response="Non ci sono sottoagenti in esecuzione al momento.",
            )

        # 3. System 2: Complex multi-step Agentic Task -> Delegate in background to `pi`
        if any(kw in cmd for kw in AGENTIC_INTENT_KEYWORDS):
            task_id = self.agentic_dispatch_fn(cmd)
            self.active_background_tasks[task_id] = "in_progress"
            return VoiceRouteResult(
                route="system2_agentic",
                spoken_response=(
                    f"Avvio l'agente su pi per questo compito (ID {task_id}). "
                    "Puoi seguire i passaggi in tempo reale nella console."
                ),
                dispatched_task_goal=cmd,
            )

        # 4. System 1: Fast Reflex (<1s direct response)
        if self.reflex_llm_fn is not None:
            answer = self.reflex_llm_fn(cmd)
        else:
            builtin = self._instant_builtin_reflex(cmd)
            answer = builtin or f"Risposta rapida System 1: {cmd}"
        return VoiceRouteResult(
            route="system1_reflex",
            spoken_response=answer,
        )
