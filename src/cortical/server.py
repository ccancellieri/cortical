"""Cortical Mission Control — Live `pi` Agentic IDE, 4-Tier Second Brain & Italian Voice Server.

Provides:
1. Claude Code / Codex / Antigravity-style Mission Control UI at `http://127.0.0.1:8765/`
2. Authentic Italian TTS (`say -v Alice` on macOS, `piper` `it_IT-paola-medium` on Linux)
   with physical self-echo isolation, audio ducking (`/api/voice/duck`), and instant barge-in recalculation.
3. Explicit-only task creation (everyday conversations do NOT create tasks automatically) +
   Smart Bounded Chat Memory (`MemoryCurator`, FIFO max 20 turns, ephemeral filter, task closing questions & compact archival).
4. Standard MCP JSON-RPC 2.0 endpoint (`POST /api/mcp`) powering an interactive SVG Knowledge Graph Visualizer (`wiki_get_knowledge_graph`).
5. Real-time Weather & Browser Grounding (`src/cortical/grounding.py`) for both voice and `pi`.
"""

from __future__ import annotations

import dataclasses
import datetime
import json
import os
import platform
import shutil
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional

from .grounding import extract_weather_intent, fetch_weather_forecast
from .hardware.profiler import HardwareProfiler
from .memory import MemoryCurator
from .permissions.gate import AdaptivePermissionGate
from .skills_hub import CorticalSkillHub
from .voice.engine import CorticalVoiceEngine, is_self_echo
from .wiki.db import AccessContext, CorticalWikiDB, DepthTier
from .wiki.fact_check import CitationVerifier
from .wiki.mcp_server import CorticalWikiMCPServer

_ACTIVE_TTS_LOCK = threading.Lock()
_ACTIVE_TTS_PROC: Optional[subprocess.Popen[bytes]] = None
_LAST_SPOKEN_TEXT: str = ""
_LAST_SPOKEN_AT: float = 0.0
_TTS_DUCKED: bool = False

NEURAL_ITALIAN_VOICES = {
    "IsabellaNeural": "it-IT-IsabellaNeural",
    "GiuseppeNeural": "it-IT-GiuseppeMultilingualNeural",
    "ElsaNeural": "it-IT-ElsaNeural",
    "DiegoNeural": "it-IT-DiegoNeural",
    "it-IT-IsabellaNeural": "it-IT-IsabellaNeural",
    "it-IT-GiuseppeMultilingualNeural": "it-IT-GiuseppeMultilingualNeural",
    "it-IT-ElsaNeural": "it-IT-ElsaNeural",
    "it-IT-DiegoNeural": "it-IT-DiegoNeural",
}


def shape_expressive_italian_text(text: str) -> str:
    """Naturalizes technical symbols, numbers, and punctuation for expressive Italian speech."""
    import re as _re

    out = text.strip()
    out = _re.sub(r"[`*_#]+", "", out)
    out = _re.sub(r"\(\s*", ", ", out)
    out = _re.sub(r"\s*\)", ", ", out)
    out = _re.sub(r"\bmin\s+(\d+)", r"minima \1", out, flags=_re.IGNORECASE)
    out = _re.sub(r"\bmax\s+(\d+)", r"massima \1", out, flags=_re.IGNORECASE)
    out = _re.sub(r"(\d+)[.,](\d+)\s*°C", r"\1 virgola \2 gradi", out)
    out = _re.sub(r"(\d+)\s*°C", r"\1 gradi", out)
    out = _re.sub(r"(\d+)[.,](\d+)\s*km/h", r"\1 chilometri orari", out)
    out = _re.sub(r"(\d+)\s*km/h", r"\1 chilometri orari", out)
    out = _re.sub(r"(\d+)\s*%", r"\1 per cento", out)
    out = _re.sub(r"\bMCP\b", "emme ci pì", out)
    out = _re.sub(r"\bpi\b", "pì", out)
    out = _re.sub(r",\s*,+", ", ", out)
    out = _re.sub(r",\s*\.", ".", out)
    out = _re.sub(r"\s+", " ", out).strip()
    return out


_LAST_TTS_ENDED_AT: float = 0.0


def is_tts_speaking() -> bool:
    """Returns True if native TTS is currently playing audio."""
    global _LAST_TTS_ENDED_AT
    with _ACTIVE_TTS_LOCK:
        if _ACTIVE_TTS_PROC is None:
            return False
        alive = _ACTIVE_TTS_PROC.poll() is None
        if not alive and _LAST_TTS_ENDED_AT < _LAST_SPOKEN_AT:
            _LAST_TTS_ENDED_AT = time.monotonic()
        return alive


def is_tts_speaking_or_cooling_down(cooldown_sec: float = 2.2) -> bool:
    """Returns True while TTS is actively playing OR within `cooldown_sec` after playback ends."""
    if is_tts_speaking():
        return True
    now_m = time.monotonic()
    if _LAST_TTS_ENDED_AT > 0 and (now_m - _LAST_TTS_ENDED_AT) <= cooldown_sec:
        return True
    # Also estimate speech duration (~13 chars/sec + 1.4s synthesis buffer) as safety net
    if _LAST_SPOKEN_AT > 0 and _LAST_SPOKEN_TEXT:
        est_duration = max(3.2, len(_LAST_SPOKEN_TEXT) / 13.5 + 1.8)
        if (now_m - _LAST_SPOKEN_AT) <= est_duration:
            return True
    return False


def stop_native_tts() -> None:
    """Immediately terminates any active TTS process for instant barge-in (<20ms)."""
    global _ACTIVE_TTS_PROC, _TTS_DUCKED, _LAST_TTS_ENDED_AT
    with _ACTIVE_TTS_LOCK:
        _TTS_DUCKED = False
        if _ACTIVE_TTS_PROC is not None:
            try:
                _ACTIVE_TTS_PROC.terminate()
            except Exception:  # noqa: BLE001
                pass
            _ACTIVE_TTS_PROC = None
            _LAST_TTS_ENDED_AT = time.monotonic()
    if platform.system() == "Darwin":
        subprocess.run(["pkill", "-x", "say"], stderr=subprocess.DEVNULL, check=False)
        subprocess.run(["pkill", "-x", "afplay"], stderr=subprocess.DEVNULL, check=False)


def duck_native_tts(force_stop: bool = False) -> dict[str, Any]:
    """Ducks ongoing TTS output ONLY when an explicit barge-in / user interruption is confirmed."""
    global _TTS_DUCKED
    was_speaking = is_tts_speaking()
    _TTS_DUCKED = True
    if force_stop and was_speaking:
        stop_native_tts()
    return {"ducked": True, "was_speaking": was_speaking}


def speak_native_tts(
    text: str,
    voice: str = "IsabellaNeural",
    rate: int = 192,
    volume: float = 1.0,
) -> bool:
    """Speaks Italian text using Expressive Neural TTS (`edge-tts` Isabella/Giuseppe) or Piper/Prosodic say fallback."""
    global _ACTIVE_TTS_PROC, _LAST_SPOKEN_TEXT, _LAST_SPOKEN_AT, _TTS_DUCKED
    if not text or not text.strip():
        return False
    stop_native_tts()
    spoken_natural = shape_expressive_italian_text(text)
    _LAST_SPOKEN_TEXT = f"{text.strip()} {spoken_natural}".strip()
    _LAST_SPOKEN_AT = time.monotonic()
    _TTS_DUCKED = False
    vol_clamp = max(0.15, min(1.0, float(volume)))

    try:
        sys_name = platform.system()
        # 1. Expressive Neural Italian TTS via edge-tts (`it-IT-IsabellaNeural`, `it-IT-GiuseppeMultilingualNeural`, etc.)
        edge_bin = (
            shutil.which("edge-tts")
            or str(Path(__file__).resolve().parents[2] / ".venv" / "bin" / "edge-tts")
        )
        neural_voice = NEURAL_ITALIAN_VOICES.get(voice)
        if neural_voice and Path(edge_bin).exists():
            # Unique atomic MP3 path per utterance prevents file overwrite/stutter
            mp3_path = f"/tmp/cortical_tts_{os.getpid()}_{int(time.time() * 1000)}.mp3"
            if sys_name == "Darwin" and shutil.which("afplay"):
                cmd = (
                    f'"{edge_bin}" --voice "{neural_voice}" '
                    f'--text {json.dumps(spoken_natural)} --write-media "{mp3_path}" >/dev/null 2>&1 '
                    f'&& (afplay -v {vol_clamp:.2f} "{mp3_path}" >/dev/null 2>&1; rm -f "{mp3_path}") '
                    f'|| (rm -f "{mp3_path}"; say -v Alice -r {rate} {json.dumps(spoken_natural)})'
                )
                with _ACTIVE_TTS_LOCK:
                    _ACTIVE_TTS_PROC = subprocess.Popen(
                        ["bash", "-c", cmd],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                return True
            if sys_name == "Linux" and (shutil.which("mpv") or shutil.which("ffplay")):
                player = "mpv --no-terminal" if shutil.which("mpv") else "ffplay -nodisp -autoexit -loglevel quiet"
                cmd = (
                    f'"{edge_bin}" --voice "{neural_voice}" '
                    f'--text {json.dumps(spoken_natural)} --write-media "{mp3_path}" >/dev/null 2>&1 '
                    f'&& ({player} "{mp3_path}" >/dev/null 2>&1; rm -f "{mp3_path}")'
                )
                with _ACTIVE_TTS_LOCK:
                    _ACTIVE_TTS_PROC = subprocess.Popen(
                        ["bash", "-c", cmd],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                return True

        # 2. Offline Local Fallbacks (macOS Prosody-Modulated say / Linux Neural Piper)
        if sys_name == "Darwin" and shutil.which("say"):
            allowed_voices = {"Alice", "Reed", "Shelley", "Eddy", "Sandy", "Flo", "Federica", "Luca"}
            chosen_voice = voice if voice in allowed_voices else "Alice"
            prosodic = spoken_natural.replace(". ", ". [[slnc 120]] ")
            styled_text = f"[[volm {vol_clamp:.2f}]] {prosodic}"
            with _ACTIVE_TTS_LOCK:
                _ACTIVE_TTS_PROC = subprocess.Popen(
                    ["say", "-v", chosen_voice, "-r", str(rate), styled_text],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            return True

        if sys_name == "Linux":
            piper_bin = shutil.which("piper") or "/home/bianco/.local/bin/piper"
            paola_model = Path.home() / ".local/share/local-ai/models/piper/it_IT-paola-medium.onnx"
            if Path(piper_bin).exists() and paola_model.exists() and shutil.which("aplay"):
                cmd = (
                    f'printf %s {json.dumps(spoken_natural)} | "{piper_bin}" --model "{paola_model}" '
                    f"--length_scale 0.94 --noise_w 0.85 --output-raw "
                    f"| aplay -r 22050 -f S16_LE -t raw - >/dev/null 2>&1"
                )
                with _ACTIVE_TTS_LOCK:
                    _ACTIVE_TTS_PROC = subprocess.Popen(
                        ["bash", "-c", cmd],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                return True
            if shutil.which("spd-say"):
                with _ACTIVE_TTS_LOCK:
                    _ACTIVE_TTS_PROC = subprocess.Popen(
                        ["spd-say", "-l", "it", spoken_natural],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                return True
    except Exception:  # noqa: BLE001
        pass
    return False


def query_local_reflex_llm(prompt: str, base_url: str, timeout: float = 8.0) -> str:
    """Queries deterministic grounding first, then available local/LAN OpenAI-compatible servers in Italian."""
    now = datetime.datetime.now()
    norm = prompt.lower().strip()

    # 1. Instant deterministic Italian reflexes (< 2ms)
    if any(k in norm for k in ("che ore sono", "che ora e", "che ora è", "dimmi l ora", "orario")):
        return f"Sono le {now.strftime('%H:%M')}."
    if any(k in norm for k in ("che giorno", "data di oggi", "quanti ne abbiamo")):
        giorni = ("lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica")
        mesi = (
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
        return f"Oggi è {giorni[now.weekday()]} {now.day} {mesi[now.month]} {now.year}."
    if any(k in norm for k in ("chi sei", "cosa fai", "presentati")):
        return (
            "Sono Cortical, il tuo assistente agentico locale. "
            "Uso la Wiki Merkle a 4 livelli per la memoria e coordino gli agenti su pi solo quando richiesto."
        )
    if any(k in norm for k in ("come stai", "tutto bene", "mi senti")):
        return "Tutto perfetto! Ti sento forte e chiaro in italiano."

    # 2. Deterministic Weather & Browser Grounding (e.g., "procedi cerca il meteo a roma per domani")
    weather_intent = extract_weather_intent(prompt)
    if weather_intent is not None:
        forecast = fetch_weather_forecast(
            city=weather_intent["city"],
            day_offset=weather_intent["day_offset"],
            open_browser=bool(weather_intent.get("open_browser", False)),
        )
        return str(forecast["summary_it"])

    # 3. Candidate LLM endpoints (Local llama-server :8080, Local Ollama :11434, LAN laptop :8080)
    candidates = [
        (base_url, "qwen2.5:1.5b" if ":11434" in base_url else "local-model"),
        ("http://127.0.0.1:8080/v1", "local-model"),
        ("http://127.0.0.1:11434/v1", "qwen2.5:1.5b"),
        ("http://192.168.8.142:8080/v1", "local-model"),
    ]
    seen = set()
    for endpoint, model_name in candidates:
        if not endpoint or endpoint in seen or ":20128" in endpoint:
            continue
        seen.add(endpoint)
        url = endpoint.rstrip("/") + "/chat/completions"
        payload = {
            "model": model_name,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        f"Sei Cortical, assistente vocale e ingegneristico italiano creato da Carlo Cancellieri. "
                        f"Ora locale: {now.strftime('%H:%M')}. Rispondi SEMPRE e SOLO in italiano corretto, "
                        "in modo completo, fluido e naturale (2-3 frasi concluse senza troncare)."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 350,
            "temperature": 0.2,
        }
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
                data = json.loads(resp.read().decode("utf-8"))
                content = data["choices"][0]["message"]["content"].strip()
                if "</think>" in content:
                    content = content.split("</think>", 1)[1].strip()
                if "no longer supported" in content.lower() or "antigravity.google" in content.lower():
                    continue
                if content:
                    return content
        except Exception:  # noqa: BLE001
            continue

    return f"Ho ricevuto la richiesta: '{prompt}'. Se vuoi che diventi un task operativo, chiedimi 'crea un task per {prompt}'."


class PiAgentManager:
    """Manages explicit-only `pi` coding tasks with isolated working notes and compact archival."""

    def __init__(
        self,
        repo_root: Path,
        wiki_db: CorticalWikiDB,
        memory_curator: MemoryCurator,
        perm_gate: AdaptivePermissionGate,
        base_url_fn: Any,
    ) -> None:
        self.repo_root = repo_root
        self.wiki_db = wiki_db
        self.memory_curator = memory_curator
        self.perm_gate = perm_gate
        self.base_url_fn = base_url_fn
        self.sessions: dict[str, dict[str, Any]] = {}
        self.processes: dict[str, subprocess.Popen[str]] = {}
        self._lock = threading.Lock()

    def list_sessions(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(reversed(list(self.sessions.values())))

    def get_session(self, session_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            return self.sessions.get(session_id)

    def mark_archived(self, session_id: str, archived_trace: str) -> None:
        with self._lock:
            if session_id in self.sessions:
                self.sessions[session_id]["status"] = "archived"
                self.sessions[session_id]["archived_trace"] = archived_trace
                self.sessions[session_id]["steps"] = [
                    {
                        "index": 1,
                        "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
                        "type": "output",
                        "title": "📦 Task Archiviato (Memoria di lavoro isolata rimossa, sintesi 3+1 e traccia nel Macro-Grafo)",
                        "detail": archived_trace,
                        "meta": {"archived": True},
                    }
                ]

    def delete_session(self, session_id: str) -> bool:
        with self._lock:
            proc = self.processes.pop(session_id, None)
            if proc is not None:
                try:
                    proc.terminate()
                except Exception:  # noqa: BLE001
                    pass
            return self.sessions.pop(session_id, None) is not None

    def clear_archived_sessions(self) -> int:
        removed = 0
        with self._lock:
            for sid in [k for k, v in self.sessions.items() if v.get("status") == "archived"]:
                self.sessions.pop(sid, None)
                removed += 1
        return removed

    def stop_all(self) -> int:
        stopped = 0
        with self._lock:
            for sid, proc in list(self.processes.items()):
                try:
                    proc.terminate()
                except Exception:  # noqa: BLE001
                    pass
                if sid in self.sessions and self.sessions[sid]["status"] == "working":
                    self.sessions[sid]["status"] = "stopped"
                    self._append_step(
                        sid,
                        "system",
                        "🛑 Esecuzione interrotta dall'utente (Barge-in / Stop).",
                    )
                    stopped += 1
            self.processes.clear()
        return stopped

    def _append_step(
        self,
        session_id: str,
        step_type: str,
        title: str,
        detail: str = "",
        meta: Optional[dict[str, Any]] = None,
    ) -> None:
        s = self.sessions.get(session_id)
        if not s:
            return
        s["steps"].append(
            {
                "index": len(s["steps"]) + 1,
                "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
                "type": step_type,
                "title": title,
                "detail": detail,
                "meta": meta or {},
            }
        )
        s["updated_at"] = time.time()

    def spawn_agent(
        self,
        goal: str,
        role: str = "Orchestrator",
        wiki_depth: str = "medium",
        skills: Optional[list[str]] = None,
        speak_on_finish: bool = False,
    ) -> dict[str, Any]:
        session_id = f"pi-{int(time.time() * 1000) % 1000000}"
        skills_list = skills or ["cortical-second-brain", "modern-web-guidance"]
        session_obj: dict[str, Any] = {
            "session_id": session_id,
            "role": role,
            "goal": goal,
            "status": "working",
            "wiki_depth": wiki_depth,
            "skills": skills_list,
            "created_at": time.time(),
            "updated_at": time.time(),
            "steps": [],
            "final_report": None,
            "closing_questions": [],
        }
        with self._lock:
            self.sessions[session_id] = session_obj

        t = threading.Thread(
            target=self._run_agent_worker,
            args=(session_id, goal, wiki_depth, skills_list, speak_on_finish),
            daemon=True,
        )
        t.start()
        return session_obj

    def _run_agent_worker(
        self,
        session_id: str,
        goal: str,
        wiki_depth: str,
        skills: list[str],
        speak_on_finish: bool,
    ) -> None:
        ctx = AccessContext()
        try:
            self._append_step(
                session_id,
                "thinking",
                f"Inizializzazione Task Esplicito `pi` (Wiki Depth: {wiki_depth.upper()}, Memoria Isolata per Task)",
                f"Obiettivo: {goal}",
            )
            self.memory_curator.add_task_working_note(session_id, f"Avvio task: {goal}")
            time.sleep(0.1)

            root_nav = self.wiki_db.navigate(ctx, path="/", depth=DepthTier(wiki_depth))
            children_summary = "\n".join(
                f"  • {c['path']} ({c['node_type']}): {c['summary'][:120]}"
                for c in root_nav.get("children", [])[:10]
            )
            self._append_step(
                session_id,
                "tool_call",
                f"mcp__cortical-wiki__wiki_navigate(path='/', depth='{wiki_depth}')",
                f"Subtree Hash: {root_nav['subtree_hash'][:16]}…\nNodi trovati:\n{children_summary}",
                {"tool": "wiki_navigate", "depth": wiki_depth},
            )

            hits = self.wiki_db.search(ctx, query=goal, depth=DepthTier(wiki_depth), limit=4)
            if hits:
                hit_lines = "\n".join(
                    f"  • {h['path']} [tier={h['depth_tier']}]: {h['content'][:180]}..."
                    for h in hits
                )
            else:
                hit_lines = "  • Nessun match FTS5 specifico; uso la vista strutturale di root."
            self._append_step(
                session_id,
                "tool_call",
                f"mcp__cortical-wiki__wiki_search(query={json.dumps(goal[:40])}, depth='{wiki_depth}')",
                f"Risultati pertinenti dalla Wiki Merkle:\n{hit_lines}",
                {"tool": "wiki_search", "hits": len(hits)},
            )
            self.memory_curator.add_task_working_note(session_id, f"Ricerca FTS5: {len(hits)} nodi trovati")

            perm_dec = self.perm_gate.evaluate("wiki_navigate", {"path": "/", "depth": wiki_depth})
            self._append_step(
                session_id,
                "permission",
                f"Adaptive Permission Gate → {perm_dec.verdict.upper()} (risk={perm_dec.risk_score})",
                f"Pattern: {perm_dec.normalized_pattern} — {perm_dec.reason}",
            )

            pi_output_text = query_local_reflex_llm(goal, self.base_url_fn(), timeout=8.0)

            touched = [h["path"] for h in hits] if hits else ["/"]
            self.wiki_db.record_episode(
                ctx,
                episode_id=session_id,
                title=f"[{session_id}] {goal[:52]}",
                goal=goal,
                outcome_status="active",
                learned_summary=pi_output_text[:300],
                skills_used=skills,
                relations=[
                    {
                        "relation": "relates_to",
                        "target_type": "subtree",
                        "target_id": p,
                    }
                    for p in touched
                ],
            )
            closure_info = self.memory_curator.prepare_task_closure(session_id)
            questions = closure_info.get("closing_questions", [])
            q_text = "\n".join(f"  ? {q}" for q in questions)
            self._append_step(
                session_id,
                "output",
                "Task attivo completato — Pronto per revisione o archiviazione sintetica",
                f"{pi_output_text}\n\nDomande di chiusura task (prima dell'archiviazione):\n{q_text}",
            )

            with self._lock:
                if self.sessions[session_id]["status"] == "working":
                    self.sessions[session_id]["status"] = "completed"
                    self.sessions[session_id]["final_report"] = pi_output_text
                    self.sessions[session_id]["closing_questions"] = questions

            if speak_on_finish:
                speak_native_tts(f"Task completato. {pi_output_text[:160]}")

        except Exception as exc:  # noqa: BLE001
            self._append_step(session_id, "system", f"Errore agente: {exc}")
            with self._lock:
                self.sessions[session_id]["status"] = "error"

    def open_native_pi_terminal(self) -> dict[str, Any]:
        """Opens a native OS Terminal window running interactive `pi` with the Cortical harness loaded."""
        sys_name = platform.system()
        ext_path = self.repo_root / ".pi/extensions/cortical-harness.ts"
        cmd_str = f"cd {json.dumps(str(self.repo_root))} && pi -e {json.dumps(str(ext_path))}"
        try:
            if sys_name == "Darwin":
                apple_script = (
                    f'tell application "Terminal"\n'
                    f'  activate\n'
                    f'  do script {json.dumps(cmd_str)}\n'
                    f'end tell'
                )
                subprocess.Popen(["osascript", "-e", apple_script])
                return {"opened": True, "platform": "macOS Terminal.app", "command": cmd_str}
            if sys_name == "Linux":
                for term in ("gnome-terminal", "x-terminal-emulator", "xterm"):
                    if shutil.which(term):
                        subprocess.Popen([term, "--", "bash", "-c", cmd_str + "; exec bash"])
                        return {"opened": True, "platform": term, "command": cmd_str}
        except Exception as exc:  # noqa: BLE001
            return {"opened": False, "error": str(exc), "command": cmd_str}
        return {"opened": False, "command": cmd_str}


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Cortical Mission Control — Agentic IDE, 4-Tier Second Brain & Voice</title>
  <style>
    :root {
      --bg: #090d16;
      --bg-sidebar: #0d1322;
      --panel: #131c31;
      --panel-hover: #192540;
      --border: #233253;
      --accent: #38bdf8;
      --accent-glow: rgba(56, 189, 248, 0.18);
      --indigo: #818cf8;
      --emerald: #34d399;
      --amber: #fbbf24;
      --rose: #f87171;
      --text: #f1f5f9;
      --muted: #94a3b8;
      --mono: "SF Mono", "JetBrains Mono", Menlo, Consolas, monospace;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0; height: 100vh; display: flex; flex-direction: column;
      font-family: -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", sans-serif;
      background: var(--bg); color: var(--text); overflow: hidden;
    }
    .topbar {
      height: 58px; background: var(--bg-sidebar); border-bottom: 1px solid var(--border);
      display: flex; align-items: center; justify-content: space-between; padding: 0 18px;
      flex-shrink: 0;
    }
    .brand { display: flex; align-items: center; gap: 12px; }
    .brand-logo {
      width: 32px; height: 32px; border-radius: 8px;
      background: linear-gradient(135deg, var(--accent), var(--indigo));
      display: flex; align-items: center; justify-content: center;
      font-weight: 900; color: #090d16; font-family: var(--mono);
    }
    .brand-title { font-weight: 700; font-size: 1.05rem; letter-spacing: -0.02em; }
    .brand-sub { font-size: 0.75rem; color: var(--muted); }
    .voice-bar {
      display: flex; align-items: center; gap: 10px;
      background: var(--panel); border: 1px solid var(--border);
      padding: 6px 12px; border-radius: 999px;
    }
    .pulse-dot {
      width: 10px; height: 10px; border-radius: 50%; background: var(--muted);
      transition: all 0.2s;
    }
    .pulse-dot.listening {
      background: var(--emerald);
      box-shadow: 0 0 12px var(--emerald);
      animation: pulse 1.3s infinite;
    }
    @keyframes pulse {
      0% { transform: scale(0.95); opacity: 1; }
      50% { transform: scale(1.25); opacity: 0.65; }
      100% { transform: scale(0.95); opacity: 1; }
    }
    .live-transcript {
      font-size: 0.82rem; color: var(--accent); font-family: var(--mono);
      min-width: 220px; max-width: 340px; white-space: nowrap;
      overflow: hidden; text-overflow: ellipsis;
    }
    .btn {
      background: linear-gradient(135deg, var(--accent), var(--indigo));
      color: #090d16; border: none; border-radius: 7px; padding: 7px 12px;
      font-size: 0.8rem; font-weight: 700; cursor: pointer; display: inline-flex;
      align-items: center; gap: 6px; transition: opacity 0.15s;
    }
    .btn:hover { opacity: 0.92; }
    .btn-ghost {
      background: #17223b; color: var(--text); border: 1px solid var(--border);
      font-weight: 600;
    }
    .btn-danger {
      background: rgba(248, 113, 113, 0.16); color: var(--rose);
      border: 1px solid rgba(248, 113, 113, 0.4); font-weight: 700;
    }
    select, input, textarea {
      background: #0b1120; color: var(--text); border: 1px solid var(--border);
      border-radius: 7px; padding: 7px 10px; font-size: 0.83rem;
    }
    .workspace {
      flex: 1; display: grid;
      grid-template-columns: 300px 1fr 410px;
      min-height: 0;
    }
    .pane {
      display: flex; flex-direction: column; min-height: 0;
      border-right: 1px solid var(--border);
    }
    .pane:last-child { border-right: none; }
    .pane-header {
      padding: 11px 14px; font-size: 0.76rem; font-weight: 700;
      text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted);
      border-bottom: 1px solid var(--border); background: var(--bg-sidebar);
      display: flex; justify-content: space-between; align-items: center;
    }
    .pane-body { flex: 1; overflow-y: auto; padding: 12px; }
    .agent-item {
      padding: 10px 12px; border-radius: 9px; background: var(--panel);
      border: 1px solid var(--border); margin-bottom: 8px; cursor: pointer;
      transition: border-color 0.15s, background 0.15s;
    }
    .agent-item:hover, .agent-item.active {
      border-color: var(--accent); background: var(--panel-hover);
    }
    .agent-item-top {
      display: flex; justify-content: space-between; align-items: center;
      font-size: 0.8rem; font-weight: 700; margin-bottom: 4px;
    }
    .status-pill {
      font-size: 0.68rem; padding: 2px 7px; border-radius: 999px;
      font-family: var(--mono); text-transform: uppercase;
    }
    .status-working { background: rgba(56, 189, 248, 0.2); color: var(--accent); }
    .status-completed { background: rgba(52, 211, 153, 0.2); color: var(--emerald); }
    .status-archived { background: rgba(129, 140, 248, 0.2); color: var(--indigo); }
    .status-stopped, .status-error { background: rgba(248, 113, 113, 0.2); color: var(--rose); }
    .step-card {
      background: var(--panel); border: 1px solid var(--border);
      border-radius: 10px; padding: 12px 14px; margin-bottom: 10px;
      border-left: 3px solid var(--accent);
    }
    .step-card.tool_call { border-left-color: var(--indigo); }
    .step-card.subagent { border-left-color: var(--amber); }
    .step-card.output { border-left-color: var(--emerald); }
    .step-card.permission { border-left-color: var(--rose); }
    .step-meta {
      display: flex; justify-content: space-between; font-size: 0.74rem;
      color: var(--muted); font-family: var(--mono); margin-bottom: 5px;
    }
    .step-title { font-weight: 700; font-size: 0.88rem; margin-bottom: 6px; color: var(--text); }
    .step-detail {
      margin: 0; font-family: var(--mono); font-size: 0.78rem;
      color: #cbd5e1; white-space: pre-wrap; background: #070b13;
      padding: 9px; border-radius: 6px; border: 1px solid #1a2640;
      max-height: 240px; overflow-y: auto;
    }
    .composer {
      padding: 12px 16px; background: var(--bg-sidebar);
      border-top: 1px solid var(--border); display: flex; flex-direction: column; gap: 8px;
    }
    .composer-row { display: flex; gap: 8px; align-items: center; }
    .composer input { flex: 1; padding: 10px 12px; font-size: 0.9rem; }
    .tree-node {
      padding: 6px 8px; border-radius: 6px; font-family: var(--mono);
      font-size: 0.78rem; cursor: pointer; display: flex; justify-content: space-between;
      color: #cbd5e1;
    }
    .tree-node:hover { background: var(--panel-hover); color: var(--accent); }
    .tabs { display: flex; gap: 4px; flex-wrap: wrap; }
    .tab {
      padding: 4px 8px; border-radius: 6px; font-size: 0.71rem; cursor: pointer;
      background: #0b1120; color: var(--muted); border: 1px solid var(--border);
    }
    .tab.active { background: var(--accent-glow); color: var(--accent); border-color: var(--accent); }
    .graph-canvas-wrap {
      background: #060a12; border: 1px solid var(--border); border-radius: 8px;
      height: 360px; position: relative; overflow: hidden; margin-bottom: 8px;
    }
    .graph-legend {
      display: flex; gap: 10px; flex-wrap: wrap; font-size: 0.71rem; color: var(--muted);
      margin-bottom: 8px; font-family: var(--mono);
    }
    .legend-dot {
      width: 9px; height: 9px; border-radius: 50%; display: inline-block; margin-right: 4px;
    }
  </style>
</head>
<body>
  <!-- TOP MISSION CONTROL BAR -->
  <div class="topbar">
    <div class="brand">
      <div class="brand-logo">C</div>
      <div>
        <div class="brand-title">Cortical Mission Control</div>
        <div class="brand-sub" id="hw-banner">Inizializzazione profilo hardware...</div>
      </div>
    </div>

    <!-- ALWAYS-ON VOICE CONTROL BAR WITH SELF-ECHO GUARD & DUCKING -->
    <div class="voice-bar">
      <div class="pulse-dot" id="mic-dot"></div>
      <span class="live-transcript" id="live-transcript">Anti-Echo & Ducking attivi · Di' "Hei Cortical, meteo a Roma domani"</span>
      <button class="btn" id="btn-always-on" onclick="toggleAlwaysOnMic()">🎤 Ascolto Continuo: OFF</button>
      <select id="tts-voice" title="Voce Italiana Espressiva">
        <option value="IsabellaNeural" selected>🇮🇹 Voce: Isabella Neurale (Espressiva)</option>
        <option value="GiuseppeNeural">🇮🇹 Voce: Giuseppe Neurale (Multilingue)</option>
        <option value="ElsaNeural">🇮🇹 Voce: Elsa Neurale (Brillante)</option>
        <option value="DiegoNeural">🇮🇹 Voce: Diego Neurale (Dinamico)</option>
        <option value="Alice">🇮🇹 Voce: Alice (Locale Offline)</option>
      </select>
      <button class="btn btn-danger" onclick="triggerStopBargeIn()" title="Ferma immediatamente voce e agenti">🛑 BASTA / STOP</button>
    </div>

    <div style="display:flex; gap:8px;">
      <button class="btn btn-ghost" onclick="openNativePiTerminal()">🖥️ Apri `pi` in Terminale</button>
    </div>
  </div>

  <!-- 3-PANE IDE WORKSPACE -->
  <div class="workspace">
    <!-- LEFT PANE: EXPLICIT TASKS & 4-TIER WIKI TREE -->
    <div class="pane">
      <div class="pane-header">
        <span>Task Multi-Agente `pi`</span>
        <div style="display:flex; gap:5px;">
          <button class="btn btn-ghost" style="padding:3px 7px; font-size:0.68rem;" onclick="clearArchivedTasks()" title="Rimuove tutti i task già archiviati">🧹 Pulisci</button>
          <button class="btn" style="padding:3px 8px; font-size:0.72rem;" onclick="spawnQuickAgent()">+ Nuovo Task</button>
        </div>
      </div>
      <div class="pane-body" id="agent-roster" style="max-height: 46%;">
        <div style="color:var(--muted); font-size:0.78rem;">
          Le chiacchierate normali non creano task. I task vengono creati solo su richiesta esplicita ("crea un task..." o "+ Nuovo Task") e restano isolati fino all'archiviazione.
        </div>
      </div>

      <div class="pane-header">
        <span>Second Brain (4-Tier Merkle)</span>
        <select id="wiki-depth" onchange="navigateWiki(currentWikiPath)" style="padding:2px 6px; font-size:0.72rem;">
          <option value="light">LIGHT (~50t)</option>
          <option value="medium" selected>MEDIUM (~250t)</option>
          <option value="high">HIGH (~1000t)</option>
          <option value="max">MAX (Raw)</option>
        </select>
      </div>
      <div class="pane-body" id="wiki-tree"></div>
    </div>

    <!-- CENTER PANE: LIVE STREAM -->
    <div class="pane">
      <div class="pane-header">
        <span id="stream-title">Conversazione & Stream Esecutivo (Anti-Echo · Ducking · Meteo Live)</span>
        <span style="font-family:var(--mono); font-size:0.72rem; color:var(--accent);" id="active-session-badge">CHAT & VOICE</span>
      </div>
      <div class="pane-body" id="agent-stream">
        <div class="step-card output">
          <div class="step-meta"><span>CORTICAL v0.2 READY</span><span>Anti-Echo · Smart Memory · MCP Graph</span></div>
          <div class="step-title">Novità attive in Cortical</div>
          <pre class="step-detail">• Isolamento Eco & Audio Ducking: Cortical ignora la propria voce e abbassa/interrompe la risposta se inizi a parlare, ricalcolando subito per la nuova domanda.
• Zero Task Automatici: le chiacchierate quotidiane ("che ore sono", "cerca il meteo a Roma domani") non creano task. Usa "Crea un task per..." o "+ Nuovo Task" per i task.
• Memoria Intelligente & Archiviazione Task: le domande effimere restano in un buffer leggero auto-pulito (max 20 turni); quando archivi un task, la memoria pesante del task viene rimossa lasciando solo una traccia sintetica nel grafo.
• Grafo della Conoscenza MCP: clicca sul tab "🕸️ Grafo MCP" a destra per visualizzare i nodi tramite protocollo MCP standard.</pre>
        </div>
      </div>

      <!-- PROMPT COMPOSER -->
      <div class="composer">
        <div class="composer-row">
          <select id="dispatch-mode">
            <option value="auto">💬 Conversazione & Voce (Crea task solo se richiesto esplicitamente)</option>
            <option value="agent">🤖 Crea Task Esplicito `pi` (Con Memoria Isolata)</option>
          </select>
          <select id="agent-depth">
            <option value="light">Contesto Wiki: LIGHT</option>
            <option value="medium" selected>Contesto Wiki: MEDIUM</option>
            <option value="high">Contesto Wiki: HIGH</option>
            <option value="max">Contesto Wiki: MAX (Full File)</option>
          </select>
          <label style="font-size:0.78rem; color:var(--muted); display:flex; align-items:center; gap:4px;">
            <input type="checkbox" id="chk-speak" checked /> Pronuncia risposta (TTS Ita)
          </label>
        </div>
        <div class="composer-row">
          <input id="prompt-input" placeholder="Prova: 'procedi cerca il meteo a roma per domani' oppure 'crea un task per analizzare la wiki'..." onkeydown="if(event.key==='Enter') submitComposer()" />
          <button class="btn" onclick="submitComposer()">Invia ↵</button>
        </div>
      </div>
    </div>

    <!-- RIGHT PANE: INSPECTOR (MCP GRAPH VISUALIZER / MEMORY / WIKI / PERMISSIONS) -->
    <div class="pane">
      <div class="pane-header">
        <span>Inspector</span>
        <div class="tabs">
          <span class="tab active" id="tab-graph" onclick="switchInspector('graph')">🕸️ Grafo MCP</span>
          <span class="tab" id="tab-skills" onclick="switchInspector('skills')">⚡ Skill & 3+1</span>
          <span class="tab" id="tab-mem" onclick="switchInspector('mem')">🧠 Memoria</span>
          <span class="tab" id="tab-wiki" onclick="switchInspector('wiki')">Wiki</span>
          <span class="tab" id="tab-perm" onclick="switchInspector('perm')">Permessi</span>
        </div>
      </div>
      <div class="pane-body">
        <!-- Interactive MCP Knowledge Graph Visualizer -->
        <div id="insp-graph">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
            <button class="btn btn-ghost" style="padding:4px 9px; font-size:0.74rem;" onclick="loadMcpKnowledgeGraph()">🔄 Aggiorna via MCP (`wiki_get_knowledge_graph`)</button>
            <span id="graph-stats" style="font-size:0.72rem; font-family:var(--mono); color:var(--accent);"></span>
          </div>
          <div class="graph-legend">
            <span><i class="legend-dot" style="background:#38bdf8;"></i>Dir/Merkle</span>
            <span><i class="legend-dot" style="background:#94a3b8;"></i>File</span>
            <span><i class="legend-dot" style="background:#fbbf24;"></i>Task Attivo</span>
            <span><i class="legend-dot" style="background:#818cf8;"></i>Task Archiviato</span>
            <span><i class="legend-dot" style="background:#34d399;"></i>Insight Memoria</span>
          </div>
          <div class="graph-canvas-wrap">
            <svg id="mcp-graph-svg" width="100%" height="100%" viewBox="0 0 380 350"></svg>
          </div>
          <pre class="step-detail" id="graph-view" style="max-height: 190px;">Clicca un nodo nel grafo sopra per ispezionare la traccia MCP.</pre>
        </div>

        <!-- Parallel 3+1 Memory Synthesis & Learned Skills Hub -->
        <div id="insp-skills" style="display:none;">
          <div style="display:flex; gap:6px; margin-bottom:8px;">
            <input id="skill-test-prompt" placeholder="Testa Prompt Enhancer (es: 'implementa un endpoint FastAPI con wiki')" style="flex:1;" onkeydown="if(event.key==='Enter') testPromptEnhancer()" />
            <button class="btn" onclick="testPromptEnhancer()">Arricchisci</button>
            <button class="btn btn-ghost" onclick="loadSkillsHub()">🔄 Skill</button>
          </div>
          <pre class="step-detail" id="skills-view" style="max-height: calc(100vh - 180px);">Caricamento Skill Hub (3+1 Memory Skills + Skill Apprese)...</pre>
        </div>

        <!-- Smart Memory & Chat Buffer Inspector -->
        <div id="insp-mem" style="display:none;">
          <div style="display:flex; gap:6px; margin-bottom:8px;">
            <button class="btn btn-ghost" onclick="loadSmartMemory()">🔄 Aggiorna Stato Memoria</button>
          </div>
          <pre class="step-detail" id="mem-view" style="max-height: calc(100vh - 180px);">Caricamento memoria...</pre>
        </div>

        <!-- Wiki Inspector -->
        <div id="insp-wiki" style="display:none;">
          <div style="display:flex; gap:6px; margin-bottom:8px;">
            <input id="wiki-search-input" placeholder="Cerca nella Wiki (FTS5)..." style="flex:1;" onkeydown="if(event.key==='Enter') searchWiki()" />
            <button class="btn btn-ghost" onclick="searchWiki()">Cerca</button>
          </div>
          <pre class="step-detail" id="wiki-node-view" style="max-height: calc(100vh - 180px);">Seleziona un file a sinistra per ispezionare le sintesi light/medium/high/max.</pre>
        </div>

        <!-- Permissions Inspector -->
        <div id="insp-perm" style="display:none;">
          <div style="display:flex; gap:6px; margin-bottom:8px;">
            <select id="perm-tool">
              <option value="bash">bash</option>
              <option value="write_file">write_file</option>
              <option value="chrome">chrome</option>
            </select>
            <input id="perm-cmd" value="pytest tests/" style="flex:1;" />
          </div>
          <div style="display:flex; gap:6px; margin-bottom:10px;">
            <button class="btn" onclick="evalPerm()">Valuta</button>
            <button class="btn btn-ghost" onclick="feedbackPerm(true)">👍 Approva & Impara</button>
            <button class="btn btn-danger" onclick="testHardBlock()">🛡️ Test rm -rf /</button>
          </div>
          <pre class="step-detail" id="perm-view">Adaptive Permission Gate pronto.</pre>
        </div>
      </div>
    </div>
  </div>

  <script>
    let currentWikiPath = '/';
    let selectedSessionId = null;
    let alwaysOnActive = false;
    let recognition = null;
    let lastSpokenResponseText = '';
    let lastSpokenAtMs = 0;
    let localTtsShieldUntilMs = 0;
    let activeAbortController = null;

    function hasWakeOrBargeInWord(s) {
      return /\b(cortical|peppe|ferma|fermati|stop|basta|silenzio|zitto|annulla|aspetta)\b/i.test(s || '');
    }

    function isTtsShieldActive() {
      return Date.now() < localTtsShieldUntilMs;
    }

    function normalizeTokens(s) {
      return (s || '')
        .toLowerCase()
        .replace(/(\d+)[.,](\d+)\s*°c/gi, '$1 virgola $2 gradi')
        .replace(/(\d+)\s*°c/gi, '$1 gradi')
        .replace(/\bmin\s+(\d+)/gi, 'minima $1')
        .replace(/\bmax\s+(\d+)/gi, 'massima $1')
        .replace(/(\d+)\s*%/g, '$1 per cento')
        .replace(/[^\w\sàèéìòù]/g, ' ')
        .split(/\s+/)
        .filter(w => w.length > 1);
    }

    // Client-side Self-Echo Guard: detects if WebSpeech picked up Cortical's own spoken output
    function isSelfEchoClient(candidate) {
      if (!candidate) return false;
      if (hasWakeOrBargeInWord(candidate)) return false;
      // While Cortical is actively speaking (or in acoustic tail cooldown), any non-wake-word mic input is speaker bleed
      if (isTtsShieldActive()) return true;
      if (!lastSpokenResponseText) return false;
      const elapsedSec = (Date.now() - lastSpokenAtMs) / 1000.0;
      if (elapsedSec > 25.0) return false;
      const candWords = normalizeTokens(candidate);
      const spokenWords = new Set(normalizeTokens(lastSpokenResponseText));
      if (!candWords.length || !spokenWords.size) return false;
      const candJoined = candWords.join(' ');
      const spokenJoined = normalizeTokens(lastSpokenResponseText).join(' ');
      if (candJoined.length >= 5 && spokenJoined.includes(candJoined)) return true;
      const overlap = candWords.filter(w => spokenWords.has(w)).length / candWords.length;
      return overlap >= 0.45;
    }

    async function loadHealth() {
      const r = await fetch('/health');
      const d = await r.json();
      document.getElementById('hw-banner').textContent =
        `${d.os_name} (${d.arch}) · Tier: ${d.tier} · Voce: Italiana (${d.tts_engine}) · LLM: ${d.active_base_url}`;
    }

    function appendStreamCard(type, metaLeft, metaRight, title, detail) {
      const stream = document.getElementById('agent-stream');
      const div = document.createElement('div');
      div.className = `step-card ${type}`;
      div.innerHTML = `
        <div class="step-meta"><span>${metaLeft}</span><span>${metaRight}</span></div>
        <div class="step-title">${title}</div>
        <pre class="step-detail">${detail}</pre>
      `;
      stream.appendChild(div);
      stream.scrollTop = stream.scrollHeight;
    }

    async function submitComposer(overrideText) {
      const input = document.getElementById('prompt-input');
      const fromMic = (overrideText !== undefined);
      const text = (fromMic ? overrideText : input.value).trim();
      if (!text) return;
      if (!fromMic) input.value = '';

      // 1. Self-Echo & Acoustic Shield Check for Microphone Input
      if (fromMic && isSelfEchoClient(text)) {
        document.getElementById('live-transcript').textContent = `🔇 [Eco altoparlante ignorato]`;
        return;
      }

      // 2. Barge-in Abort only when typed manually or when user explicitly says Wake/Stop word
      if (activeAbortController) {
        activeAbortController.abort();
      }
      if (!fromMic || hasWakeOrBargeInWord(text)) {
        await fetch('/api/voice/duck', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({force_stop: true})
        }).catch(() => {});
      }

      const mode = document.getElementById('dispatch-mode').value;
      const depth = document.getElementById('agent-depth').value;
      const speak = document.getElementById('chk-speak').checked;
      const voice = document.getElementById('tts-voice').value;

      if (mode === 'agent') {
        await spawnAgentSession(text, depth, speak);
        return;
      }

      if (speak) {
        // Pre-arm acoustic shield before server starts speaking
        localTtsShieldUntilMs = Date.now() + 4500;
      }

      activeAbortController = new AbortController();
      try {
        const r = await fetch('/api/voice', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({utterance: text, speak, voice, wiki_depth: depth, from_mic: fromMic}),
          signal: activeAbortController.signal
        });
        const d = await r.json();

        if (d.route === 'ignored_echo') {
          document.getElementById('live-transcript').textContent = `🔇 [Eco ignorato dal server]`;
          return;
        }

        if (d.spoken_response) {
          lastSpokenResponseText = d.spoken_response;
          lastSpokenAtMs = Date.now();
          if (speak && d.route !== 'stop') {
            // Keep acoustic shield active for the full duration of the spoken response + 2.2s tail
            const estMs = Math.max(4800, d.spoken_response.length * 82 + 2400);
            localTtsShieldUntilMs = Date.now() + estMs;
          } else {
            localTtsShieldUntilMs = Date.now() + 1200;
          }
        }

        if (d.spawned_session_id) {
          selectedSessionId = d.spawned_session_id;
          await refreshAgents();
          await loadMcpKnowledgeGraph();
        } else {
          selectedSessionId = null;
          appendStreamCard(
            d.route === 'stop' ? 'permission' : 'output',
            `VOICE & CHAT ROUTER → ${d.route.toUpperCase()}`,
            `${d.latency_ms} ms`,
            `Tu: "${text}"`,
            `Cortical: ${d.spoken_response}`
          );
          await loadMcpKnowledgeGraph();
        }
      } catch (err) {
        if (err.name === 'AbortError') {
          appendStreamCard('system', 'BARGE-IN RECALCULATION', 'ABORTED', `Domanda precedente interrotta per ricalcolare la nuova richiesta`, '');
        }
      } finally {
        activeAbortController = null;
      }
    }

    async function spawnAgentSession(goal, depth, speak) {
      const r = await fetch('/api/agents/spawn', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({goal, wiki_depth: depth, speak})
      });
      const sess = await r.json();
      selectedSessionId = sess.session_id;
      await refreshAgents();
      await loadMcpKnowledgeGraph();
    }

    function spawnQuickAgent() {
      const goal = prompt("Inserisci l'obiettivo per il nuovo Task esplicito pi:", "Analizza la struttura del repository e riassumi i moduli principali");
      if (goal) spawnAgentSession(goal, document.getElementById('agent-depth').value, true);
    }

    async function closeAndArchiveTask(event, sessionId) {
      event.stopPropagation();
      const prevRes = await fetch('/api/tasks/close-preview', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({episode_id: sessionId})
      });
      const prev = await prevRes.json();
      const questions = (prev.closing_questions || []).join('\\n• ');
      const notes = prompt(
        `Chiusura & Archiviazione Task ${sessionId}\\n\\nDomande di chiusura di Cortical:\\n• ${questions}\\n\\nInserisci la lezione appresa (Cortical salverà la sintesi a 3+1 livelli e valuterà se creare una nuova Skill per il futuro):`,
        "Confermo la sintesi e salvo le lezioni apprese nei 3+1 livelli."
      );
      if (notes === null) return;
      const archRes = await fetch('/api/tasks/archive', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({episode_id: sessionId, user_closing_notes: notes})
      });
      const arch = await archRes.json();
      const skillInfo = arch.skill_evaluation?.should_create_skill
        ? `\\n✨ Nuova Skill Generata: ${arch.skill_evaluation.skill_id} (${arch.skill_evaluation.skill_path})`
        : `\\nℹ️ Valutazione Skill: ${arch.skill_evaluation?.reason || 'nessuna nuova skill richiesta'}`;
      appendStreamCard(
        'output',
        `TASK ARCHIVED (3+1 MEMORY + SKILL EVAL) → ${sessionId}`,
        `Note rimosse: ${arch.purged_working_notes}`,
        `📦 Task ${sessionId} archiviato nei 3+1 livelli`,
        `Traccia L1 conservata: ${arch.archived_trace}${skillInfo}`
      );
      await refreshAgents();
      await loadMcpKnowledgeGraph();
    }

    async function deleteTask(event, sessionId) {
      event.stopPropagation();
      if (!confirm(`Vuoi cancellare definitivamente il task ${sessionId} e tutti i suoi dati?`)) return;
      await fetch('/api/tasks/delete', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({episode_id: sessionId})
      });
      if (selectedSessionId === sessionId) selectedSessionId = null;
      appendStreamCard('permission', `TASK DELETED → ${sessionId}`, 'REMOVED', `🗑️ Task ${sessionId} cancellato definitivamente.`, '');
      await refreshAgents();
      await loadMcpKnowledgeGraph();
    }

    async function clearArchivedTasks() {
      const r = await fetch('/api/tasks/clear-archived', {method: 'POST', body: '{}'});
      const d = await r.json();
      appendStreamCard('system', 'CLEANUP ARCHIVED TASKS', `${d.deleted_count || 0} rimossi`, '🧹 Task archiviati rimossi dalla lista.', JSON.stringify(d, null, 2));
      await refreshAgents();
      await loadMcpKnowledgeGraph();
    }

    async function refreshAgents() {
      const r = await fetch('/api/agents');
      const data = await r.json();
      const sessions = data.sessions || [];
      const roster = document.getElementById('agent-roster');
      if (!sessions.length) {
        roster.innerHTML = `<div style="color:var(--muted); font-size:0.78rem;">Nessun task attivo. Le chiacchierate non creano task. Usa "+ Nuovo Task" o "/task" in pi per aprirne uno.</div>`;
        return;
      }

      roster.innerHTML = sessions.map(s => `
        <div class="agent-item ${s.session_id === selectedSessionId ? 'active' : ''}" onclick="selectSession('${s.session_id}')">
          <div class="agent-item-top">
            <span>🤖 ${s.session_id}</span>
            <span class="status-pill status-${s.status}">${s.status}</span>
          </div>
          <div style="font-size:0.78rem; color:#cbd5e1; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
            ${s.goal}
          </div>
          <div style="display:flex; justify-content:space-between; align-items:center; margin-top:6px; gap:4px;">
            <span style="font-size:0.68rem; color:var(--muted); font-family:var(--mono);">
              Wiki: ${s.wiki_depth.toUpperCase()} · Steps: ${s.steps.length}
            </span>
            <div style="display:flex; gap:4px;">
              ${s.status !== 'archived' ? `<button class="btn btn-ghost" style="padding:2px 6px; font-size:0.67rem;" onclick="closeAndArchiveTask(event, '${s.session_id}')" title="Archivia nei 3+1 livelli e valuta nuova Skill">📦 Archivia</button>` : ''}
              <button class="btn btn-danger" style="padding:2px 6px; font-size:0.67rem;" onclick="deleteTask(event, '${s.session_id}')" title="Cancella definitivamente il task">🗑️ Cancella</button>
            </div>
          </div>
        </div>
      `).join('');

      if (selectedSessionId) {
        const active = sessions.find(s => s.session_id === selectedSessionId);
        if (active) {
          document.getElementById('active-session-badge').textContent = `${active.session_id} (${active.status.toUpperCase()})`;
          const stream = document.getElementById('agent-stream');
          stream.innerHTML = active.steps.map(st => `
            <div class="step-card ${st.type}">
              <div class="step-meta"><span>STEP #${st.index} · ${st.type.toUpperCase()}</span><span>${st.timestamp}</span></div>
              <div class="step-title">${st.title}</div>
              ${st.detail ? `<pre class="step-detail">${st.detail}</pre>` : ''}
            </div>
          `).join('');
        }
      }
    }

    function selectSession(sid) {
      selectedSessionId = sid;
      refreshAgents();
    }

    async function triggerStopBargeIn() {
      if (activeAbortController) activeAbortController.abort();
      if (window.speechSynthesis) window.speechSynthesis.cancel();
      await fetch('/api/voice', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({utterance: 'Ehi Cortical basta', speak: true, voice: document.getElementById('tts-voice').value})
      });
      refreshAgents();
    }

    async function openNativePiTerminal() {
      const r = await fetch('/api/agents/open-terminal', {method: 'POST', body: '{}'});
      const d = await r.json();
      appendStreamCard('subagent', 'TERMINAL LAUNCHER', d.platform || 'CLI', 'Apertura sessione interattiva `pi`', JSON.stringify(d, null, 2));
    }

    // Continuous Always-On Wake-Word Microphone with Self-Echo Filtering & Audio Ducking
    function toggleAlwaysOnMic() {
      const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!SR) {
        alert("Il browser corrente non espone Web Speech API (usa Chrome o Edge per il microfono continuo).");
        return;
      }
      if (alwaysOnActive) {
        alwaysOnActive = false;
        if (recognition) recognition.stop();
        document.getElementById('mic-dot').classList.remove('listening');
        document.getElementById('btn-always-on').textContent = '🎤 Ascolto Continuo: OFF';
        document.getElementById('live-transcript').textContent = 'Microfono in pausa.';
        return;
      }

      alwaysOnActive = true;
      document.getElementById('mic-dot').classList.add('listening');
      document.getElementById('btn-always-on').textContent = '🟢 Ascolto Attivo (Anti-Echo)';
      document.getElementById('live-transcript').textContent = 'In ascolto... (ignoro la mia voce, abbasso il volume se parli)';

      recognition = new SR();
      recognition.lang = 'it-IT';
      recognition.continuous = true;
      recognition.interimResults = true;

      recognition.onresult = (event) => {
        let interim = '';
        for (let i = event.resultIndex; i < event.results.length; ++i) {
          const transcript = event.results[i][0].transcript.trim();
          if (isSelfEchoClient(transcript)) {
            document.getElementById('live-transcript').textContent = `🔇 [Scudo Anti-Eco: ignoro la mia voce]`;
            continue;
          }
          if (event.results[i].isFinal) {
            document.getElementById('live-transcript').textContent = `🗣️ "${transcript}"`;
            submitComposer(transcript);
          } else {
            interim += transcript + ' ';
            // Only interrupt ongoing TTS during interim speech if user explicitly says a Wake/Stop word
            if (hasWakeOrBargeInWord(interim)) {
              fetch('/api/voice/duck', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({force_stop: true})
              }).catch(() => {});
            }
          }
        }
        if (interim && !isTtsShieldActive()) {
          document.getElementById('live-transcript').textContent = `🎙️ … ${interim}`;
        }
      };

      recognition.onerror = () => {};
      recognition.onend = () => {
        if (alwaysOnActive) {
          try { recognition.start(); } catch (_) {}
        }
      };
      recognition.start();
    }

    // Standard MCP Call (`POST /api/mcp`) to render the Interactive SVG Knowledge Graph
    async function loadMcpKnowledgeGraph() {
      const mcpReq = {
        jsonrpc: '2.0',
        id: Date.now(),
        method: 'tools/call',
        params: {
          name: 'wiki_get_knowledge_graph',
          arguments: { max_nodes: 45 }
        }
      };
      const r = await fetch('/api/mcp', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(mcpReq)
      });
      const mcpRes = await r.json();
      const rawText = mcpRes?.result?.content?.[0]?.text || '{}';
      const graph = JSON.parse(rawText);
      const stats = graph.stats || {};
      document.getElementById('graph-stats').textContent =
        `${stats.node_count || 0} nodi · ${stats.edge_count || 0} archi`;
      renderKnowledgeGraphSvg(graph);
    }

    function renderKnowledgeGraphSvg(graph) {
      const svg = document.getElementById('mcp-graph-svg');
      const nodes = graph.nodes || [];
      const edges = graph.edges || [];
      if (!nodes.length) {
        svg.innerHTML = '<text x="190" y="175" fill="#94a3b8" text-anchor="middle" font-size="12">Nessun nodo nel grafo</text>';
        return;
      }

      const W = 380, H = 350, cx = W / 2, cy = H / 2;
      const posMap = {};
      const colorMap = {
        dir: '#38bdf8',
        file: '#94a3b8',
        task_active: '#fbbf24',
        task_archived: '#818cf8',
        insight: '#34d399'
      };

      nodes.forEach((n, idx) => {
        if (n.id === 'subtree:/' || n.id === 'node:/') {
          posMap[n.id] = { x: cx, y: cy };
          return;
        }
        const nType = n.type || n.kind || 'file';
        const ring = nType === 'dir' ? 75 : (nType.startsWith('task_') ? 128 : 148);
        const angle = (2 * Math.PI * idx) / Math.max(1, nodes.length - 1);
        posMap[n.id] = {
          x: Math.round(cx + ring * Math.cos(angle)),
          y: Math.round(cy + ring * Math.sin(angle))
        };
      });

      let html = '';
      edges.forEach(e => {
        const s = posMap[e.source];
        const t = posMap[e.target];
        if (!s || !t) return;
        const stroke = e.kind === 'macro' ? '#fbbf24' : '#233253';
        const dash = e.kind === 'macro' ? 'stroke-dasharray="4,3"' : '';
        html += `<line x1="${s.x}" y1="${s.y}" x2="${t.x}" y2="${t.y}" stroke="${stroke}" stroke-width="1.3" ${dash} opacity="0.75" />`;
      });

      nodes.forEach(n => {
        const p = posMap[n.id];
        if (!p) return;
        const col = colorMap[n.type] || '#38bdf8';
        const r = n.id === 'node:/' ? 10 : (n.type.startsWith('task_') ? 8 : 6);
        const safeJson = encodeURIComponent(JSON.stringify(n));
        const shortLabel = (n.label || '').slice(0, 16);
        html += `
          <g style="cursor:pointer;" onclick="inspectGraphNode('${safeJson}')">
            <circle cx="${p.x}" cy="${p.y}" r="${r}" fill="${col}" stroke="#090d16" stroke-width="2" />
            <text x="${p.x}" y="${p.y + r + 10}" fill="#cbd5e1" font-size="9" font-family="monospace" text-anchor="middle">${shortLabel}</text>
          </g>
        `;
      });

      svg.innerHTML = html;
    }

    function inspectGraphNode(encoded) {
      const node = JSON.parse(decodeURIComponent(encoded));
      document.getElementById('graph-view').textContent = JSON.stringify(node, null, 2);
    }

    async function loadSmartMemory() {
      const r = await fetch('/api/memory/state');
      const d = await r.json();
      document.getElementById('mem-view').textContent = JSON.stringify(d, null, 2);
    }

    async function navigateWiki(path = '/') {
      currentWikiPath = path;
      const depth = document.getElementById('wiki-depth').value;
      const r = await fetch(`/api/wiki/navigate?path=${encodeURIComponent(path)}&depth=${depth}`);
      const d = await r.json();
      document.getElementById('wiki-node-view').textContent = JSON.stringify(d, null, 2);

      const children = d.children || [];
      const tree = document.getElementById('wiki-tree');
      let html = '';
      if (path !== '/') {
        const parent = d.parent_path || '/';
        html += `<div class="tree-node" onclick="navigateWiki('${parent}')"><span>⬅️ .. (${parent})</span><span>DIR</span></div>`;
      }
      html += children.map(c => `
        <div class="tree-node" onclick="navigateWiki('${c.path}')">
          <span>${c.node_type === 'dir' ? '📁' : '📄'} ${c.path.split('/').pop() || '/'}</span>
          <span style="color:var(--muted); font-size:0.7rem;">${c.node_type}</span>
        </div>
      `).join('');
      tree.innerHTML = html || `<div class="tree-node" onclick="navigateWiki('/')"><span>📁 / (Torna a root)</span></div>`;
    }

    async function searchWiki() {
      const q = document.getElementById('wiki-search-input').value;
      const depth = document.getElementById('wiki-depth').value;
      const r = await fetch(`/api/wiki/search?q=${encodeURIComponent(q)}&depth=${depth}`);
      document.getElementById('wiki-node-view').textContent = JSON.stringify(await r.json(), null, 2);
    }

    function switchInspector(tab) {
      ['graph', 'skills', 'mem', 'wiki', 'perm'].forEach(t => {
        const el = document.getElementById(`insp-${t}`);
        const tb = document.getElementById(`tab-${t}`);
        if (el) el.style.display = (t === tab) ? 'block' : 'none';
        if (tb) tb.classList.toggle('active', t === tab);
      });
      if (tab === 'graph') loadMcpKnowledgeGraph();
      if (tab === 'skills') loadSkillsHub();
      if (tab === 'mem') loadSmartMemory();
    }

    async function loadSkillsHub() {
      const r = await fetch('/api/skills/state');
      const d = await r.json();
      const box = document.getElementById('skills-list-view');
      const skills = d.skills || [];
      box.innerHTML = skills.map(s => `
        <div style="background:rgba(15,23,42,0.85); border:1px solid ${s.category === 'memory_tier' ? 'rgba(56,189,248,0.4)' : s.category === 'learned' ? 'rgba(52,211,153,0.4)' : 'var(--border)'}; border-radius:6px; padding:6px 8px; margin-bottom:5px; font-size:0.75rem;">
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <b style="color:${s.category === 'memory_tier' ? 'var(--accent)' : s.category === 'learned' ? 'var(--ok)' : '#f8fafc'};">${s.name}</b>
            <span class="tag">${s.category}</span>
          </div>
          <div style="color:var(--muted); margin-top:2px;">${s.description}</div>
        </div>
      `).join('');
    }

    async function testPromptEnhancer() {
      const prompt = document.getElementById('skill-test-input').value.trim();
      if (!prompt) return;
      const r = await fetch('/api/skills/enhance', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({prompt})
      });
      const d = await r.json();
      document.getElementById('skill-enhance-view').textContent =
        `[Mode]: ${d.mode} | [Depth 3+1]: ${d.recommended_depth}\n` +
        `[Memory Skill]: ${d.memory_tier_skill}\n` +
        `[Procedural Skills]: ${(d.selected_procedural_skills || []).join(', ')}\n` +
        `[Team Roster]: ${(d.team_roster || []).map(x => x.id).join(' -> ')}\n\n` +
        (d.context_injection || '(Conversazione casual: nessun overhead iniettato)');
    }

    async function evalPerm() {
      const tool = document.getElementById('perm-tool').value;
      const cmd = document.getElementById('perm-cmd').value;
      const r = await fetch('/api/permissions/evaluate', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({tool, args: {command: cmd, path: cmd}})
      });
      document.getElementById('perm-view').textContent = JSON.stringify(await r.json(), null, 2);
    }

    async function feedbackPerm(approved) {
      const tool = document.getElementById('perm-tool').value;
      const cmd = document.getElementById('perm-cmd').value;
      const r = await fetch('/api/permissions/feedback', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({tool, args: {command: cmd, path: cmd}, approved, remember: true})
      });
      document.getElementById('perm-view').textContent = JSON.stringify(await r.json(), null, 2);
    }

    function testHardBlock() {
      document.getElementById('perm-tool').value = 'bash';
      document.getElementById('perm-cmd').value = 'rm -rf /';
      evalPerm();
    }

    loadHealth();
    navigateWiki('/');
    loadMcpKnowledgeGraph();
    setInterval(refreshAgents, 2000);
  </script>
</body>
</html>
"""


class CorticalLiveService:
    """Holds shared state for the live Cortical Mission Control HTTP, MCP, Memory, `pi` Agent & Voice server."""

    def __init__(
        self,
        wiki_db_path: str | Path,
        perm_db_path: str | Path,
        repo_root: Optional[str | Path] = None,
        profiler: Optional[HardwareProfiler] = None,
    ) -> None:
        self.started_at = time.time()
        self.repo_root = Path(repo_root or os.getcwd()).resolve()
        self.wiki_db = CorticalWikiDB(wiki_db_path)
        self.verifier = CitationVerifier(self.wiki_db)
        self.perm_gate = AdaptivePermissionGate(perm_db_path)
        self.profiler = profiler or HardwareProfiler()
        self.hw_profile = self.profiler.detect()
        self.model_rec = self.profiler.recommend_models(self.hw_profile)

        def _reflex(prompt: str) -> str:
            return query_local_reflex_llm(prompt, self.model_rec.active_base_url)

        self.memory_curator = MemoryCurator(self.wiki_db, llm_fn=_reflex)
        self.skill_hub = CorticalSkillHub(self.wiki_db, self.repo_root / ".pi" / "skills", llm_fn=_reflex)
        self.mcp_server = CorticalWikiMCPServer(wiki_db_path)

        self.agent_mgr = PiAgentManager(
            repo_root=self.repo_root,
            wiki_db=self.wiki_db,
            memory_curator=self.memory_curator,
            perm_gate=self.perm_gate,
            base_url_fn=lambda: self.model_rec.active_base_url,
        )

        def _dispatch_agentic(goal: str) -> str:
            sess = self.agent_mgr.spawn_agent(goal=goal, wiki_depth="medium", speak_on_finish=True)
            return str(sess["session_id"])

        def _on_stop() -> None:
            stop_native_tts()
            self.agent_mgr.stop_all()

        def _on_duck() -> None:
            duck_native_tts(force_stop=True)

        self.voice_engine = CorticalVoiceEngine(
            wiki_db=self.wiki_db,
            permission_gate=self.perm_gate,
            reflex_llm_fn=_reflex,
            agentic_dispatch_fn=_dispatch_agentic,
            stop_callback=_on_stop,
            duck_callback=_on_duck,
            memory_curator=self.memory_curator,
        )

    def handle_api(
        self,
        method: str,
        path: str,
        query: dict[str, list[str]],
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        ctx = AccessContext()

        if method == "GET" and path == "/health":
            tts_engine = (
                "Edge-TTS Neural (Isabella/Giuseppe it-IT) + macOS say"
                if self.hw_profile.os_name == "Darwin"
                else "Edge-TTS Neural (Isabella/Giuseppe it-IT) + Piper Neural"
            )
            return (
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "service": "cortical-live",
                    "version": "0.3.0",
                    "uptime_sec": round(time.time() - self.started_at, 2),
                    "os_name": self.hw_profile.os_name,
                    "arch": self.hw_profile.arch,
                    "tier": self.hw_profile.tier,
                    "tts_engine": tts_engine,
                    "reuse_existing_endpoint": self.model_rec.reuse_existing_endpoint,
                    "active_base_url": self.model_rec.active_base_url,
                    "discovered_endpoints": self.hw_profile.discovered_endpoints,
                },
            )

        # Standard MCP JSON-RPC 2.0 HTTP Bridge
        if method == "POST" and path == "/api/mcp":
            resp = self.mcp_server.handle_request(body)
            return (HTTPStatus.OK, resp or {})

        # Smart Memory & Task Lifecycle Endpoints
        if method == "GET" and path == "/api/memory/state":
            return (
                HTTPStatus.OK,
                {
                    "chat_buffer": self.memory_curator.get_recent_chat(limit=20),
                    "curated_insights": self.memory_curator.list_insights(limit=25),
                    "macro_graph": self.wiki_db.query_macro_graph(ctx),
                },
            )

        if method == "POST" and path == "/api/tasks/close-preview":
            ep_id = str(body.get("episode_id", ""))
            return (HTTPStatus.OK, self.memory_curator.prepare_task_closure(ep_id))

        if method == "POST" and path == "/api/tasks/archive":
            ep_id = str(body.get("episode_id", ""))
            notes = str(body.get("user_closing_notes", ""))
            synth = self.skill_hub.synthesize_task_discussion_3plus1(ep_id, notes)
            skill_eval = self.skill_hub.evaluate_and_compile_skill(ep_id, notes).to_dict()
            res = self.memory_curator.archive_task(ep_id, user_closing_notes=notes)
            if res.get("status") == "archived":
                self.agent_mgr.mark_archived(ep_id, str(res.get("archived_trace", "")))
            res["synthesis_3plus1"] = synth
            res["skill_evaluation"] = skill_eval
            return (HTTPStatus.OK, res)

        if method == "POST" and path == "/api/tasks/delete":
            ep_id = str(body.get("episode_id", ""))
            mem_res = self.memory_curator.delete_task(ep_id)
            ag_res = self.agent_mgr.delete_session(ep_id)
            return (HTTPStatus.OK, {**mem_res, "agent_session": ag_res})

        if method == "POST" and path == "/api/tasks/clear-archived":
            mem_res = self.memory_curator.clear_archived_tasks()
            ag_res = self.agent_mgr.clear_archived_sessions()
            return (HTTPStatus.OK, {**mem_res, **ag_res})

        # Skills Hub & Prompt Enhancer Endpoints (mcp-skill-hub evolution)
        if method == "GET" and path == "/api/skills/state":
            return (
                HTTPStatus.OK,
                {
                    "skills": [
                        {
                            "name": s.name,
                            "description": s.description,
                            "category": s.category,
                            "recommended_tools": s.recommended_tools,
                        }
                        for s in self.skill_hub.discover_skills()
                    ],
                    "learned_registry": self.skill_hub.list_learned_skills(),
                    "syntheses_3plus1": self.skill_hub.get_task_syntheses(limit=15),
                },
            )

        if method == "POST" and path == "/api/skills/enhance":
            prompt_text = str(body.get("prompt", "")).strip()
            active_ep = body.get("active_episode_id")
            return (
                HTTPStatus.OK,
                self.skill_hub.enhance_prompt(
                    prompt_text,
                    active_episode_id=str(active_ep) if active_ep else None,
                ).to_dict(),
            )

        # Voice Ducking & Echo State Endpoints
        if method == "POST" and path == "/api/voice/duck":
            force_stop = bool(body.get("force_stop", False))
            return (HTTPStatus.OK, duck_native_tts(force_stop=force_stop))

        if method == "GET" and path == "/api/voice/state":
            return (
                HTTPStatus.OK,
                {
                    "tts_speaking": is_tts_speaking(),
                    "tts_shield_active": is_tts_speaking_or_cooling_down(),
                    "last_spoken_text": self.voice_engine.last_spoken_text or _LAST_SPOKEN_TEXT,
                },
            )

        if method == "GET" and path == "/api/agents":
            return (HTTPStatus.OK, {"sessions": self.agent_mgr.list_sessions()})

        if method == "POST" and path == "/api/agents/spawn":
            goal = str(body.get("goal", "")).strip()
            depth = str(body.get("wiki_depth", "medium"))
            speak = bool(body.get("speak", False))
            sess = self.agent_mgr.spawn_agent(goal=goal, wiki_depth=depth, speak_on_finish=speak)
            return (HTTPStatus.OK, sess)

        if method == "POST" and path == "/api/agents/open-terminal":
            return (HTTPStatus.OK, self.agent_mgr.open_native_pi_terminal())

        if method == "GET" and path == "/api/wiki/navigate":
            target = (query.get("path") or ["/"])[0]
            depth = (query.get("depth") or ["light"])[0]
            try:
                return (HTTPStatus.OK, self.wiki_db.navigate(ctx, path=target, depth=DepthTier(depth)))
            except KeyError as exc:
                return (HTTPStatus.NOT_FOUND, {"error": str(exc)})

        if method == "GET" and path == "/api/wiki/search":
            q = (query.get("q") or [""])[0]
            depth = (query.get("depth") or ["medium"])[0]
            return (
                HTTPStatus.OK,
                {"results": self.wiki_db.search(ctx, query=q, depth=DepthTier(depth))},
            )

        if method == "GET" and path == "/api/wiki/macro-graph":
            return (HTTPStatus.OK, self.wiki_db.query_macro_graph(ctx))

        if method == "GET" and path == "/api/wiki/knowledge-graph":
            return (HTTPStatus.OK, self.wiki_db.get_knowledge_graph(ctx))

        if method == "POST" and path == "/api/wiki/verify":
            res = self.verifier.verify_and_record(
                ctx,
                claim_text=str(body.get("claim_text", "")),
                source_path=str(body.get("source_path", "/")),
                quoted_span=str(body.get("quoted_span", "")),
            )
            return (HTTPStatus.OK, dataclasses.asdict(res))

        if method == "POST" and path == "/api/permissions/evaluate":
            tool = str(body.get("tool", "bash"))
            args = dict(body.get("args") or {})
            dec = self.perm_gate.evaluate(tool, args)
            if dec.verdict == "ask":
                self.voice_engine.register_pending_permission(tool, args)
            return (HTTPStatus.OK, dataclasses.asdict(dec))

        if method == "POST" and path == "/api/permissions/feedback":
            tool = str(body.get("tool", "bash"))
            args = dict(body.get("args") or {})
            dec = self.perm_gate.record_user_feedback(
                tool,
                args,
                approved=bool(body.get("approved", True)),
                remember_always=bool(body.get("remember", True)),
            )
            return (HTTPStatus.OK, dataclasses.asdict(dec))

        if method == "POST" and path == "/api/voice":
            utterance = str(body.get("utterance", ""))
            speak = bool(body.get("speak", False))
            voice_name = str(body.get("voice", "IsabellaNeural"))
            from_mic = bool(body.get("from_mic", False))
            t0 = time.perf_counter()
            res = self.voice_engine.handle_utterance(
                utterance,
                from_mic=from_mic,
                tts_currently_speaking=is_tts_speaking_or_cooling_down(),
            )
            elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            tts_triggered = False
            if speak and res.route != "ignored_echo" and res.spoken_response:
                tts_triggered = speak_native_tts(res.spoken_response, voice=voice_name)
            out = dataclasses.asdict(res)
            out["latency_ms"] = elapsed_ms
            out["tts_triggered"] = tts_triggered
            if res.route == "system2_agentic":
                sessions = self.agent_mgr.list_sessions()
                if sessions:
                    out["spawned_session_id"] = sessions[0]["session_id"]
            return (HTTPStatus.OK, out)

        return (HTTPStatus.NOT_FOUND, {"error": f"Unknown endpoint: {method} {path}"})


def run_live_server(
    host: str,
    port: int,
    wiki_db_path: str | Path,
    perm_db_path: str | Path,
) -> None:
    service = CorticalLiveService(wiki_db_path=wiki_db_path, perm_db_path=perm_db_path)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path in {"/", "/index.html"}:
                data = DASHBOARD_HTML.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return

            q = urllib.parse.parse_qs(parsed.query)
            status, payload = service.handle_api("GET", parsed.path, q, {})
            self._send_json(status, payload)

        def do_POST(self) -> None:  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
            body = json.loads(raw) if raw.strip() else {}
            q = urllib.parse.parse_qs(parsed.query)
            status, payload = service.handle_api("POST", parsed.path, q, body)
            self._send_json(status, payload)

        def _send_json(self, status: int, payload: dict[str, Any]) -> None:
            data = json.dumps(payload, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return

    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"Cortical Mission Control listening on http://{host}:{port}")
    httpd.serve_forever()
