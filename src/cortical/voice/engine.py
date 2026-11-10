"""Cortical Dual-Path Voice Engine with Self-Echo Rejection, Ducking & Explicit-Only Tasks.

Key Capabilities:
1. Self-Echo Isolation (`is_self_echo`):
   Remembers the last spoken assistant response (`last_spoken_text`, `last_spoken_at`).
   Any microphone transcript that overlaps >=45% with what Cortical just said (or is a substring
   of its own speech within the echo window) is ignored (`route='ignored_echo'`), preventing
   self-listening feedback loops.
2. Audio Ducking & Barge-In Recalculation:
   When the user starts speaking a real new question while Cortical is talking, active TTS
   is ducked/aborted and the new question is recalculated immediately.
3. Explicit-Only Task Creation:
   Everyday questions (time, weather, searches, conversation) do NOT create tasks automatically.
   Tasks are spawned ONLY when explicitly requested ("crea un task", "nuovo task", "orchestra un sottoagente").
"""

from __future__ import annotations

import datetime
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from ..grounding import extract_weather_intent, fetch_weather_forecast
from ..memory import MemoryCurator, is_explicit_task_request
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
    m = re.match(
        r"^(?:allora\s+|senti\s+)?(?:ehi|hei|hey|ei|ciao|ok)?\s*cortical\b\s*(.*)$",
        norm,
    )
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


def is_self_echo(
    incoming_text: str,
    last_spoken_text: str,
    elapsed_sec: float,
    echo_window_sec: float = 14.0,
) -> bool:
    """Deterministically detects if incoming microphone audio is Cortical's own spoken output."""
    if not last_spoken_text or elapsed_sec > echo_window_sec:
        return False
    norm_in = _clean_transcript(incoming_text)
    norm_out = _clean_transcript(last_spoken_text)
    if not norm_in or not norm_out:
        return False

    # Never treat an explicit stop command as echo
    if is_stop_command(norm_in):
        return False

    if len(norm_in) >= 6 and (norm_in in norm_out or norm_out in norm_in):
        return True

    in_words = [w for w in norm_in.split() if len(w) > 2]
    out_words = set(w for w in norm_out.split() if len(w) > 2)
    if len(in_words) >= 2 and out_words:
        overlap = sum(1 for w in in_words if w in out_words) / len(in_words)
        if overlap >= 0.55:
            return True
    return False


@dataclass
class VoiceRouteResult:
    route: str  # 'ignored_echo' | 'stop' | 'permission_feedback' | 'status_report' | 'system1_reflex' | 'system2_agentic'
    spoken_response: str
    dispatched_task_goal: Optional[str] = None
    permission_updated: Optional[str] = None
    memory_curation: Optional[dict[str, Any]] = None


class CorticalVoiceEngine:
    """Dual-path voice coordinator with Self-Echo Guard, Ducking, and Smart Memory Curation."""

    def __init__(
        self,
        wiki_db: Optional[CorticalWikiDB] = None,
        permission_gate: Optional[AdaptivePermissionGate] = None,
        reflex_llm_fn: Optional[Callable[[str], str]] = None,
        agentic_dispatch_fn: Optional[Callable[[str], str]] = None,
        stop_callback: Optional[Callable[[], None]] = None,
        duck_callback: Optional[Callable[[], None]] = None,
        memory_curator: Optional[MemoryCurator] = None,
    ) -> None:
        self.wiki_db = wiki_db
        self.curator = memory_curator or (MemoryCurator(wiki_db) if wiki_db else None)
        self.permission_gate = permission_gate
        self.reflex_llm_fn = reflex_llm_fn
        self.agentic_dispatch_fn = agentic_dispatch_fn or (
            lambda goal: f"task-{abs(hash(goal)) % 10000}"
        )
        self.stop_callback = stop_callback
        self.duck_callback = duck_callback
        self.pending_permission: Optional[tuple[str, dict[str, Any]]] = None
        self.active_background_tasks: dict[str, str] = {}
        self.last_spoken_text: str = ""
        self.last_spoken_at: float = 0.0

    def register_pending_permission(self, tool_name: str, args: dict[str, Any]) -> None:
        self.pending_permission = (tool_name, args)

    def record_spoken_output(self, spoken_text: str) -> None:
        """Records assistant speech so subsequent microphone pickups of the same phrase are ignored."""
        if spoken_text and spoken_text.strip():
            self.last_spoken_text = spoken_text.strip()
            self.last_spoken_at = time.time()

    def _instant_builtin_reflex(self, cmd: str) -> Optional[str]:
        now = datetime.datetime.now()
        if any(p in cmd for p in ("che ore sono", "che ora e", "che ora è", "dimmi l ora")):
            giorno = GIORNI_SETTIMANA[now.weekday()]
            mese = MESI_ANNO[now.month]
            return f"Sono le {now.strftime('%H:%M')} di {giorno} {now.day} {mese}."
        if any(p in cmd for p in ("che giorno e", "che giorno è", "data di oggi", "quanti ne abbiamo")):
            giorno = GIORNI_SETTIMANA[now.weekday()]
            mese = MESI_ANNO[now.month]
            return f"Oggi è {giorno} {now.day} {mese} {now.year}."

        weather_intent = extract_weather_intent(cmd)
        if weather_intent:
            open_chrome = any(w in cmd for w in ("chrome", "browser", "apri", "cerca"))
            w = fetch_weather_forecast(
                city=weather_intent["city"],
                day_offset=weather_intent["day_offset"],
                open_chrome=open_chrome,
            )
            return str(w["summary_it"])
        return None

    def handle_utterance(
        self,
        transcript: str,
        force_task: bool = False,
    ) -> VoiceRouteResult:
        """Routes a transcribed voice utterance: Echo Guard -> Stop -> Permission -> Status -> System 1/2."""
        elapsed = time.time() - self.last_spoken_at
        if is_self_echo(transcript, self.last_spoken_text, elapsed):
            return VoiceRouteResult(
                route="ignored_echo",
                spoken_response="",
            )

        if is_stop_command(transcript):
            if self.stop_callback:
                self.stop_callback()
            resp = "Ricevuto, mi fermo subito."
            self.record_spoken_output(resp)
            return VoiceRouteResult(
                route="stop",
                spoken_response=resp,
            )

        # User is asking a new question: interrupt/duck any previous ongoing speech
        if self.duck_callback:
            self.duck_callback()

        _, cmd = strip_wake_word(transcript)
        if not cmd:
            resp = "Sono in ascolto, dimmi pure."
            self.record_spoken_output(resp)
            return VoiceRouteResult(
                route="system1_reflex",
                spoken_response=resp,
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
                self.record_spoken_output(spoken)
                return VoiceRouteResult(
                    route="permission_feedback",
                    spoken_response=spoken,
                    permission_updated=dec.verdict,
                )

        # 2. Subagent / Episode status check
        if any(p in cmd for p in ("a che punto", "stato dei lavori", "stato agenti", "progressi")):
            if self.active_background_tasks:
                summary = ", ".join(f"{tid}: {st}" for tid, st in self.active_background_tasks.items())
                spoken = f"Ho {len(self.active_background_tasks)} task attivi: {summary}."
                self.record_spoken_output(spoken)
                return VoiceRouteResult(
                    route="status_report",
                    spoken_response=spoken,
                )
            if self.wiki_db:
                macro = self.wiki_db.query_macro_graph(AccessContext(), limit=1)
                if macro["episodes"]:
                    last = macro["episodes"][0]
                    spoken = f"Ultimo task registrato: {last['title']} con stato {last['outcome_status']}."
                    self.record_spoken_output(spoken)
                    return VoiceRouteResult(
                        route="status_report",
                        spoken_response=spoken,
                    )
            spoken = "Non ci sono task attivi al momento."
            self.record_spoken_output(spoken)
            return VoiceRouteResult(
                route="status_report",
                spoken_response=spoken,
            )

        # 3. System 2: Explicit-Only Task Creation!
        # Everyday conversations NEVER create tasks unless explicitly requested.
        if force_task or is_explicit_task_request(cmd):
            task_id = self.agentic_dispatch_fn(cmd)
            self.active_background_tasks[task_id] = "in_progress"
            spoken = f"Ho creato il task esplicito {task_id}. Puoi seguirlo e archiviarlo quando vuoi."
            self.record_spoken_output(spoken)
            return VoiceRouteResult(
                route="system2_agentic",
                spoken_response=spoken,
                dispatched_task_goal=cmd,
            )

        # 4. System 1: Conversational & Grounded Response (with Smart Memory Curation)
        if self.reflex_llm_fn is not None:
            answer = self.reflex_llm_fn(cmd)
        else:
            builtin = self._instant_builtin_reflex(cmd)
            answer = builtin if builtin is not None else f"Risposta rapida System 1: {cmd}"

        curation_info = None
        if self.curator:
            curation_info = self.curator.record_chat_turn(AccessContext(), cmd, answer)

        self.record_spoken_output(answer)
        return VoiceRouteResult(
            route="system1_reflex",
            spoken_response=answer,
            memory_curation=curation_info,
        )
