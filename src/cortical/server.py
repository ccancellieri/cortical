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
import shlex
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

from .grounding import (
    detect_language,
    extract_browser_intent,
    extract_page_read_intent,
    extract_weather_intent,
    fetch_weather_forecast,
    format_page_reading_response,
    read_active_chrome_page,
    visual_chrome_navigate_and_search,
)
from .hardware.profiler import HardwareProfiler
from .memory import MemoryCurator
from .permissions.gate import AdaptivePermissionGate
from .skills_hub import CorticalSkillHub
from .voice.engine import CorticalVoiceEngine, is_human_discourse_or_question, is_self_echo
from .wiki.db import AccessContext, CorticalWikiDB, DepthTier
from .wiki.fact_check import CitationVerifier
from .wiki.mcp_server import CorticalWikiMCPServer

_ACTIVE_TTS_LOCK = threading.Lock()
_ACTIVE_TTS_PROC: Optional[subprocess.Popen[bytes]] = None
_LAST_SPOKEN_TEXT: str = ""
_LAST_SPOKEN_AT: float = 0.0
_TTS_DUCKED: bool = False

_TTS_AUDIO_CACHE: dict[str, tuple[bytes, str]] = {}
_TTS_CACHE_MAX = 16

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

NEURAL_ENGLISH_VOICES = {
    "JennyNeural": "en-US-JennyNeural",
    "GuyNeural": "en-US-GuyNeural",
    "AriaNeural": "en-US-AriaNeural",
    "SoniaNeural": "en-GB-SoniaNeural",
    "en-US-JennyNeural": "en-US-JennyNeural",
    "en-US-GuyNeural": "en-US-GuyNeural",
    "en-US-AriaNeural": "en-US-AriaNeural",
    "en-GB-SoniaNeural": "en-GB-SoniaNeural",
}

NEURAL_VOICES = {**NEURAL_ITALIAN_VOICES, **NEURAL_ENGLISH_VOICES}


def resolve_neural_voice(voice: str, lang: str = "it") -> tuple[Optional[str], str]:
    """Resolves requested voice ID or 'auto' into (edge_tts_voice, resolved_lang)."""
    req = (voice or "IsabellaNeural").strip()
    if req == "auto":
        return ("en-US-JennyNeural", "en") if lang == "en" else ("it-IT-IsabellaNeural", "it")
    if req in NEURAL_ENGLISH_VOICES:
        return (NEURAL_ENGLISH_VOICES[req], "en")
    if req in NEURAL_ITALIAN_VOICES:
        return (NEURAL_ITALIAN_VOICES[req], "it")
    # Match language to selected offline/fallback voice if text language switched dynamically
    if lang == "en" and req in {"IsabellaNeural", "ElsaNeural", "Federica"}:
        return ("en-US-JennyNeural", "en")
    if req in {"Samantha", "Daniel"}:
        return (None, "en")
    return (None, "en" if lang == "en" else "it")


def shape_expressive_text(text: str, lang: str = "auto") -> str:
    """Naturalizes symbols, escaped unicode codes, numbers, and abbreviations for expressive IT or EN speech."""
    import re as _re

    out = text.strip()

    def _repl_u(m: _re.Match[str]) -> str:
        try:
            return chr(int(m.group(1), 16))
        except Exception:
            return m.group(0)

    out = _re.sub(r"\\u([0-9a-fA-F]{4})", _repl_u, out)
    out = _re.sub(r"\\x([0-9a-fA-F]{2})", _repl_u, out)
    out = out.replace("\\n", " ").replace("\\t", " ").replace('\\"', '"')
    out = _re.sub(r"\\[0-9]{2,3}", " ", out)

    eff_lang = detect_language(out) if lang == "auto" else lang
    out = _re.sub(r"[`*_#]+", "", out)
    out = _re.sub(r"\(\s*", ", ", out)
    out = _re.sub(r"\s*\)", ", ", out)

    if eff_lang == "en":
        out = _re.sub(r"\bmin\s+(\d+)", r"minimum \1", out, flags=_re.IGNORECASE)
        out = _re.sub(r"\bmax\s+(\d+)", r"maximum \1", out, flags=_re.IGNORECASE)
        out = _re.sub(r"(\d+)[.,](\d+)\s*°C", r"\1 point \2 degrees Celsius", out)
        out = _re.sub(r"(\d+)\s*°C", r"\1 degrees Celsius", out)
        out = _re.sub(r"(\d+(?:[.,]\d+)?)\s*km/h", r"\1 kilometers per hour", out)
        out = _re.sub(r"(\d+)\s*%", r"\1 percent", out)
        out = _re.sub(r"\bMCP\b", "M C P", out)
    else:
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


def shape_expressive_italian_text(text: str) -> str:
    """Naturalizes technical symbols, numbers, and punctuation for expressive Italian speech."""
    return shape_expressive_text(text, lang="it")


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


def is_tts_speaking_or_cooling_down(cooldown_sec: float = 1.2) -> bool:
    """Returns True while TTS is actively playing OR within `cooldown_sec` after playback ends."""
    if _TTS_DUCKED:
        return False
    if is_tts_speaking():
        return True
    now_m = time.monotonic()
    if _LAST_TTS_ENDED_AT > 0:
        return (now_m - _LAST_TTS_ENDED_AT) <= cooldown_sec
    if _LAST_SPOKEN_AT > 0 and _LAST_SPOKEN_TEXT:
        est_duration = min(5.0, max(2.0, len(_LAST_SPOKEN_TEXT) / 15.0 + 0.8))
        return (now_m - _LAST_SPOKEN_AT) <= est_duration
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


def synthesize_tts_audio_bytes(
    text: str,
    voice: str = "IsabellaNeural",
    lang: str = "auto",
) -> tuple[Optional[bytes], str, str]:
    """Synthesizes expressive IT/EN speech bytes (MP3 via edge-tts or macOS say AIFF fallback) for Web Audio ducking."""
    global _LAST_SPOKEN_TEXT, _LAST_SPOKEN_AT, _TTS_DUCKED
    if not text or not text.strip():
        return (None, "audio/mpeg", voice)
    eff_lang = detect_language(text) if lang == "auto" else lang
    spoken_natural = shape_expressive_text(text, lang=eff_lang)
    neural_voice, resolved_lang = resolve_neural_voice(voice, lang=eff_lang)
    _LAST_SPOKEN_TEXT = spoken_natural
    _LAST_SPOKEN_AT = time.monotonic()
    _TTS_DUCKED = False

    edge_bin = (
        shutil.which("edge-tts")
        or str(Path(__file__).resolve().parents[2] / ".venv" / "bin" / "edge-tts")
    )
    if neural_voice and Path(edge_bin).exists():
        tmp_mp3 = Path(f"/tmp/cortical_web_tts_{os.getpid()}_{int(time.time() * 1000)}.mp3")
        try:
            proc = subprocess.run(
                [edge_bin, "--voice", neural_voice, "--text", spoken_natural, "--write-media", str(tmp_mp3)],
                capture_output=True,
                timeout=12.0,
                check=False,
            )
            if proc.returncode == 0 and tmp_mp3.exists() and tmp_mp3.stat().st_size > 128:
                return (tmp_mp3.read_bytes(), "audio/mpeg", neural_voice)
        except Exception:  # noqa: BLE001
            pass
        finally:
            tmp_mp3.unlink(missing_ok=True)

    # Offline fallback on macOS returning browser-playable MP4/AAC or WAV via say + afconvert
    if platform.system() == "Darwin" and shutil.which("say") and shutil.which("afconvert"):
        offline_voice = "Samantha" if resolved_lang == "en" else (voice if voice in {"Alice", "Federica", "Luca"} else "Alice")
        tmp_aiff = Path(f"/tmp/cortical_web_say_{os.getpid()}_{int(time.time() * 1000)}.aiff")
        tmp_wav = tmp_aiff.with_suffix(".wav")
        try:
            subprocess.run(["say", "-v", offline_voice, "-o", str(tmp_aiff), spoken_natural], check=False, timeout=8.0)
            if tmp_aiff.exists():
                subprocess.run(
                    ["afconvert", "-f", "WAVE", "-d", "LEI16@22050", str(tmp_aiff), str(tmp_wav)],
                    check=False,
                    timeout=8.0,
                )
                if tmp_wav.exists() and tmp_wav.stat().st_size > 128:
                    return (tmp_wav.read_bytes(), "audio/wav", offline_voice)
        except Exception:  # noqa: BLE001
            pass
        finally:
            tmp_aiff.unlink(missing_ok=True)
            tmp_wav.unlink(missing_ok=True)
    return (None, "audio/mpeg", neural_voice or voice)


def cache_tts_audio(audio_bytes: bytes, mime_type: str) -> str:
    """Stores short-lived TTS audio bytes in a bounded in-memory ring cache and returns its ID."""
    audio_id = f"tts_{int(time.time() * 1000)}_{len(_TTS_AUDIO_CACHE)}"
    _TTS_AUDIO_CACHE[audio_id] = (audio_bytes, mime_type)
    while len(_TTS_AUDIO_CACHE) > _TTS_CACHE_MAX:
        oldest_key = next(iter(_TTS_AUDIO_CACHE))
        _TTS_AUDIO_CACHE.pop(oldest_key, None)
    return audio_id


def speak_native_tts(
    text: str,
    voice: str = "IsabellaNeural",
    rate: int = 192,
    volume: float = 1.0,
    lang: str = "auto",
) -> bool:
    """Speaks IT or EN text using Expressive Neural TTS (`edge-tts`) or Piper/Prosodic `say` fallback."""
    global _ACTIVE_TTS_PROC, _LAST_SPOKEN_TEXT, _LAST_SPOKEN_AT, _TTS_DUCKED
    if not text or not text.strip():
        return False
    stop_native_tts()
    eff_lang = detect_language(text) if lang == "auto" else lang
    spoken_natural = shape_expressive_text(text, lang=eff_lang)
    neural_voice, resolved_lang = resolve_neural_voice(voice, lang=eff_lang)
    _LAST_SPOKEN_TEXT = spoken_natural
    _LAST_SPOKEN_AT = time.monotonic()
    _TTS_DUCKED = False
    vol_clamp = max(0.15, min(1.0, float(volume)))
    fallback_mac_voice = "Samantha" if resolved_lang == "en" else "Alice"

    try:
        sys_name = platform.system()
        edge_bin = (
            shutil.which("edge-tts")
            or str(Path(__file__).resolve().parents[2] / ".venv" / "bin" / "edge-tts")
        )
        if neural_voice and Path(edge_bin).exists():
            mp3_path = f"/tmp/cortical_tts_{os.getpid()}_{int(time.time() * 1000)}.mp3"
            quoted_text = shlex.quote(spoken_natural)
            if sys_name == "Darwin" and shutil.which("afplay"):
                cmd = (
                    f'"{edge_bin}" --voice "{neural_voice}" '
                    f'--text {quoted_text} --write-media "{mp3_path}" >/dev/null 2>&1 '
                    f'&& (afplay -v {vol_clamp:.2f} "{mp3_path}" >/dev/null 2>&1; rm -f "{mp3_path}") '
                    f'|| (rm -f "{mp3_path}"; say -v {fallback_mac_voice} -r {rate} {quoted_text})'
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
                    f'--text {quoted_text} --write-media "{mp3_path}" >/dev/null 2>&1 '
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
            allowed_voices = {"Alice", "Reed", "Shelley", "Eddy", "Sandy", "Flo", "Federica", "Luca", "Samantha", "Daniel"}
            chosen_voice = voice if voice in allowed_voices else fallback_mac_voice
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
                    f'printf %s {shlex.quote(spoken_natural)} | "{piper_bin}" --model "{paola_model}" '
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


def _query_llm_endpoints(
    system_prompt: str,
    user_prompt: str,
    base_url: str,
    timeout: float = 8.0,
) -> Optional[str]:
    """Queries available local/LAN OpenAI-compatible servers in priority order."""
    candidates = [
        (base_url, "qwen2.5:1.5b" if ":11434" in base_url else "local-model"),
        ("http://127.0.0.1:8080/v1", "local-model"),
        ("http://127.0.0.1:11434/v1", "qwen2.5:1.5b"),
        ("http://192.168.8.142:8080/v1", "local-model"),
    ]
    seen: set[str] = set()
    for endpoint, model_name in candidates:
        if not endpoint or endpoint in seen or ":20128" in endpoint:
            continue
        seen.add(endpoint)
        url = endpoint.rstrip("/") + "/chat/completions"
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
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
    return None


def query_local_reflex_llm(prompt: str, base_url: str, timeout: float = 8.0, lang: str = "auto") -> str:
    """Queries deterministic IT/EN grounding first, then available local/LAN OpenAI-compatible servers."""
    now = datetime.datetime.now()
    norm = prompt.lower().strip()
    eff_lang = detect_language(prompt) if lang == "auto" else ("en" if lang == "en" else "it")

    # 1. Instant deterministic IT/EN reflexes (< 2ms)
    if any(k in norm for k in ("che ore sono", "che ora e", "che ora è", "dimmi l ora", "orario", "what time is it", "what's the time", "tell me the time")):
        return f"It's {now.strftime('%H:%M')}." if eff_lang == "en" else f"Sono le {now.strftime('%H:%M')}."
    if any(k in norm for k in ("che giorno", "data di oggi", "quanti ne abbiamo", "what day is it", "what's the date", "today's date")):
        if eff_lang == "en":
            days_en = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
            months_en = ("", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")
            return f"Today is {days_en[now.weekday()]}, {months_en[now.month]} {now.day}, {now.year}."
        giorni = ("lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica")
        mesi = (
            "", "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
            "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
        )
        return f"Oggi è {giorni[now.weekday()]} {now.day} {mesi[now.month]} {now.year}."
    if any(k in norm for k in ("chi sei", "cosa fai", "presentati", "who are you", "what do you do", "introduce yourself")):
        if eff_lang == "en":
            return (
                "I'm Cortical, your bilingual local agentic assistant. "
                "I use the 3+1 Merkle Wiki for curated memory and orchestrate pi multi-agent tasks only when explicitly requested."
            )
        return (
            "Sono Cortical, il tuo assistente agentico bilingue locale. "
            "Uso la Wiki Merkle a 3+1 livelli per la memoria e coordino gli agenti su pi solo quando richiesto."
        )
    if any(k in norm for k in ("come stai", "tutto bene", "mi senti", "how are you", "can you hear me")):
        return (
            "Doing great! I hear you loud and clear in English."
            if eff_lang == "en"
            else "Tutto perfetto! Ti sento forte e chiaro in italiano."
        )

    # 2. Deterministic Weather & Browser Grounding (IT & EN)
    weather_intent = extract_weather_intent(prompt)
    if weather_intent is not None:
        forecast = fetch_weather_forecast(
            city=weather_intent["city"],
            day_offset=weather_intent["day_offset"],
            open_browser=bool(weather_intent.get("open_browser", False)),
            lang=eff_lang,
        )
        return str(forecast.get("summary") or forecast["summary_it"])

    # 3. Active Chrome Tab Reading & Concept Summarization (IT & EN)
    read_intent = extract_page_read_intent(prompt)
    if read_intent is not None:
        page = read_active_chrome_page()
        if eff_lang == "en":
            sys_sum = (
                f"You are Cortical, a bilingual voice assistant created by Carlo Cancellieri. "
                f"Local time: {now.strftime('%H:%M')}. Summarize key concepts in clear, natural spoken English."
            )
        else:
            sys_sum = (
                f"Sei Cortical, assistente vocale italiano creato da Carlo Cancellieri. "
                f"Ora locale: {now.strftime('%H:%M')}. Riassumi i concetti chiave in italiano chiaro e scorrevole."
            )
        return format_page_reading_response(
            page,
            mode=read_intent["mode"],
            summarize_llm_fn=lambda lp: _query_llm_endpoints(sys_sum, lp, base_url, timeout=timeout) or "",
            lang=eff_lang,
        )

    # 4. Visual Chrome Navigation, Form Filling & Search Submission (in focus!)
    browser_intent = extract_browser_intent(prompt)
    if browser_intent is not None:
        nav = visual_chrome_navigate_and_search(
            site=browser_intent.get("site"),
            query=browser_intent.get("query"),
            url=browser_intent.get("url"),
            focus=bool(browser_intent.get("focus", True)),
            lang=eff_lang,
        )
        return str(nav.get("summary") or nav["summary_it"])

    # 5. Candidate LLM endpoints (Local llama-server :8080, Local Ollama :11434, LAN :8080)
    if eff_lang == "en":
        sys_chat = (
            f"You are Cortical, a bilingual engineering & voice assistant created by Carlo Cancellieri. "
            f"Local time: {now.strftime('%H:%M')}. Reply ALWAYS and ONLY in clear, natural English "
            "(2-3 complete sentences without cutting off)."
        )
    else:
        sys_chat = (
            f"Sei Cortical, assistente vocale e ingegneristico italiano creato da Carlo Cancellieri. "
            f"Ora locale: {now.strftime('%H:%M')}. Rispondi SEMPRE e SOLO in italiano corretto, "
            "in modo completo, fluido e naturale (2-3 frasi concluse senza troncare)."
        )
    llm_out = _query_llm_endpoints(sys_chat, prompt, base_url, timeout=timeout)
    if llm_out:
        return llm_out

    if eff_lang == "en":
        return f"I received your request: '{prompt}'. If you want an operational multi-agent task, say 'create a task for {prompt}'."
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
            orch_cfg = self.wiki_db.get_concept_config(ctx, "concept:orchestratore-multi-agente")
            max_loops = int(orch_cfg.get("max_agent_loops", 6))
            analyst_model = str(orch_cfg.get("analyst_model", "qwen2.5:1.5b"))
            impl_model = str(orch_cfg.get("implementer_model", "qwen2.5:1.5b"))
            rev_model = str(orch_cfg.get("reviewer_model", "qwen2.5:1.5b"))
            attachments = self.wiki_db.list_context_attachments(ctx, scope_id="chat")
            att_summary = (
                ", ".join(f"{a['item_type']}:{a['label']}" for a in attachments)
                if attachments
                else "Nessun file/cartella allegata (contesto isolato)"
            )

            self._append_step(
                session_id,
                "thinking",
                f"Inizializzazione Task Esplicito `pi` (Wiki: {wiki_depth.upper()}, Max Loop: {max_loops})",
                f"Obiettivo: {goal}\nModelli Configurati: Analyst={analyst_model}, Implementer={impl_model}, Reviewer={rev_model}\nContesto Allegato: {att_summary}",
            )
            self.memory_curator.add_task_working_note(session_id, f"Avvio task: {goal} | Allegati: {att_summary}")
            time.sleep(0.1)

            try:
                root_nav = self.wiki_db.navigate(ctx, path="/", depth=DepthTier(wiki_depth))
                children_summary = "\n".join(
                    f"  • {c['path']} ({c['node_type']}): {c['summary'][:120]}"
                    for c in root_nav.get("children", [])[:10]
                ) or "  • (Radice pronta, nessun sotto-nodo)"
                sub_hash = root_nav["subtree_hash"][:16]
            except KeyError:
                children_summary = (
                    "\n".join(
                        f"  • [{a['item_type'].upper()}] {a['label']}: {a.get('summary_preview', '')[:120]}"
                        for a in attachments
                    )
                    or "  • Nessun file sorgente pre-caricato automaticamente (usa '+ Allega al Contesto' per aggiungere file o cartelle)."
                )
                sub_hash = "isolated-context"

            self._append_step(
                session_id,
                "tool_call",
                f"mcp__cortical-wiki__wiki_navigate(path='/', depth='{wiki_depth}')",
                f"Subtree Hash: {sub_hash}…\nContesto Attivo:\n{children_summary}",
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
        cmd_str = f"cd {json.dumps(str(self.repo_root))} && pi"
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
  <title>Cortical Mission Control — Concept Graph, 3+1 Second Brain & Multi-Agent Workbench</title>
  <style>
    :root {
      --bg: #070b14;
      --bg-sidebar: #0c1221;
      --panel: #111a2e;
      --panel-hover: #17233d;
      --border: #223254;
      --accent: #38bdf8;
      --accent-glow: rgba(56, 189, 248, 0.18);
      --indigo: #818cf8;
      --emerald: #34d399;
      --amber: #fbbf24;
      --rose: #f87171;
      --violet: #c084fc;
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
      min-height: 58px; background: var(--bg-sidebar); border-bottom: 1px solid var(--border);
      display: flex; align-items: center; justify-content: space-between; padding: 6px 14px;
      flex-shrink: 0; gap: 10px; flex-wrap: wrap;
    }
    .brand { display: flex; align-items: center; gap: 10px; min-width: 190px; }
    .brand-logo {
      width: 32px; height: 32px; border-radius: 9px;
      background: linear-gradient(135deg, var(--accent), var(--indigo));
      display: flex; align-items: center; justify-content: center;
      font-weight: 900; font-size: 1rem; color: #070b14; font-family: var(--mono);
      box-shadow: 0 0 16px rgba(56, 189, 248, 0.3);
    }
    .brand-title { font-weight: 800; font-size: 1rem; letter-spacing: -0.02em; }
    .brand-sub { font-size: 0.7rem; color: var(--muted); max-width: 260px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

    /* PRIMARY CENTRAL VIEW SWITCHER */
    .main-nav {
      display: flex; align-items: center; gap: 4px; flex-wrap: wrap;
      background: #080d19; padding: 4px; border-radius: 11px; border: 1px solid var(--border);
    }
    .nav-tab {
      padding: 6px 11px; border-radius: 8px; font-size: 0.79rem; font-weight: 700;
      cursor: pointer; color: var(--muted); border: 1px solid transparent;
      display: inline-flex; align-items: center; gap: 6px; transition: all 0.15s; white-space: nowrap;
    }
    .nav-tab:hover { color: var(--text); background: rgba(255,255,255,0.04); }
    .nav-tab.active {
      background: linear-gradient(135deg, rgba(56,189,248,0.2), rgba(129,140,248,0.2));
      color: var(--accent); border-color: rgba(56,189,248,0.5);
      box-shadow: 0 2px 10px rgba(56,189,248,0.12);
    }

    .voice-bar {
      display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
      background: var(--panel); border: 1px solid var(--border);
      padding: 4px 9px; border-radius: 14px; max-width: 100%;
    }
    .pulse-dot {
      width: 10px; height: 10px; border-radius: 50%; background: var(--muted);
      transition: all 0.2s; flex-shrink: 0;
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
      font-size: 0.75rem; color: var(--accent); font-family: var(--mono);
      min-width: 90px; max-width: 190px; white-space: nowrap;
      overflow: hidden; text-overflow: ellipsis;
    }
    .btn {
      background: linear-gradient(135deg, var(--accent), var(--indigo));
      color: #070b14; border: none; border-radius: 8px; padding: 7px 12px;
      font-size: 0.79rem; font-weight: 700; cursor: pointer; display: inline-flex;
      align-items: center; gap: 6px; transition: all 0.15s; white-space: nowrap;
    }
    .btn:hover { opacity: 0.92; transform: translateY(-1px); }
    .btn-ghost {
      background: #152038; color: var(--text); border: 1px solid var(--border);
      font-weight: 600;
    }
    .btn-danger {
      background: rgba(248, 113, 113, 0.16); color: var(--rose);
      border: 1px solid rgba(248, 113, 113, 0.4); font-weight: 700;
    }
    select, input, textarea {
      background: #0a101f; color: var(--text); border: 1px solid var(--border);
      border-radius: 8px; padding: 7px 10px; font-size: 0.82rem;
    }
    .workspace {
      flex: 1; display: grid;
      grid-template-columns: 310px 1fr;
      min-height: 0;
    }
    .sidebar {
      display: flex; flex-direction: column; min-height: 0;
      border-right: 1px solid var(--border); background: var(--bg-sidebar);
    }
    .main-stage {
      display: flex; flex-direction: column; min-height: 0; background: var(--bg);
    }
    .stage-view {
      flex: 1; display: flex; flex-direction: column; min-height: 0; overflow: hidden;
    }
    .pane-header {
      padding: 11px 15px; font-size: 0.75rem; font-weight: 700;
      text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted);
      border-bottom: 1px solid var(--border); background: var(--bg-sidebar);
      display: flex; justify-content: space-between; align-items: center;
      flex-shrink: 0;
    }
    .pane-body { flex: 1; overflow-y: auto; padding: 14px; min-height: 0; }
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
      font-size: 0.66rem; padding: 2px 7px; border-radius: 999px;
      font-family: var(--mono); text-transform: uppercase;
    }
    .status-working { background: rgba(56, 189, 248, 0.2); color: var(--accent); }
    .status-completed { background: rgba(52, 211, 153, 0.2); color: var(--emerald); }
    .status-archived { background: rgba(129, 140, 248, 0.2); color: var(--indigo); }
    .status-stopped, .status-error { background: rgba(248, 113, 113, 0.2); color: var(--rose); }
    .step-card {
      background: var(--panel); border: 1px solid var(--border);
      border-radius: 10px; padding: 12px 15px; margin-bottom: 10px;
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
    .step-title { font-weight: 700; font-size: 0.9rem; margin-bottom: 6px; color: var(--text); }
    .step-detail {
      margin: 0; font-family: var(--mono); font-size: 0.79rem;
      color: #cbd5e1; white-space: pre-wrap; background: #060911;
      padding: 10px; border-radius: 7px; border: 1px solid #1a2640;
      max-height: 260px; overflow-y: auto; line-height: 1.45;
    }
    .composer {
      padding: 11px 18px; background: var(--bg-sidebar);
      border-top: 1px solid var(--border); display: flex; flex-direction: column; gap: 8px;
      flex-shrink: 0;
    }
    .composer-row { display: flex; gap: 8px; align-items: center; }
    .composer input { flex: 1; padding: 10px 13px; font-size: 0.9rem; }

    /* DEDICATED CENTRAL CONCEPT GRAPH VIEW */
    .graph-stage-grid {
      flex: 1; display: grid; grid-template-columns: 1fr 370px; min-height: 0;
    }
    .graph-main-area {
      display: flex; flex-direction: column; min-height: 0; padding: 14px;
      border-right: 1px solid var(--border);
    }
    .graph-toolbar {
      display: flex; justify-content: space-between; align-items: center;
      gap: 10px; margin-bottom: 10px; flex-wrap: wrap;
    }
    .filter-pills { display: flex; gap: 5px; flex-wrap: wrap; }
    .pill {
      padding: 5px 10px; border-radius: 999px; font-size: 0.74rem; font-weight: 600;
      cursor: pointer; background: var(--panel); color: var(--muted);
      border: 1px solid var(--border); transition: all 0.15s;
    }
    .pill.active {
      background: var(--accent-glow); color: var(--accent); border-color: var(--accent);
    }
    .graph-canvas-wrap {
      flex: 1; background: radial-gradient(circle at center, #0d1629 0%, #060a12 100%);
      border: 1px solid var(--border); border-radius: 12px;
      position: relative; overflow: hidden; min-height: 360px;
      cursor: grab;
    }
    .graph-canvas-wrap:active { cursor: grabbing; }
    .graph-zoom-controls {
      position: absolute; bottom: 14px; right: 14px; display: flex; gap: 6px;
      background: rgba(12, 18, 33, 0.9); padding: 6px; border-radius: 9px;
      border: 1px solid var(--border);
    }
    .graph-legend {
      position: absolute; top: 12px; left: 14px;
      display: flex; gap: 12px; flex-wrap: wrap; font-size: 0.73rem; color: #cbd5e1;
      background: rgba(12, 18, 33, 0.85); padding: 7px 12px; border-radius: 8px;
      border: 1px solid var(--border); font-family: var(--mono); pointer-events: none;
    }
    .legend-dot {
      width: 10px; height: 10px; border-radius: 50%; display: inline-block; margin-right: 5px; vertical-align: middle;
    }
    .concept-drawer {
      display: flex; flex-direction: column; min-height: 0; background: var(--bg-sidebar);
      padding: 16px; overflow-y: auto;
    }
    .concept-badge {
      display: inline-block; padding: 3px 9px; border-radius: 999px;
      font-size: 0.7rem; font-family: var(--mono); text-transform: uppercase;
      background: var(--accent-glow); color: var(--accent); border: 1px solid rgba(56,189,248,0.4);
      margin-bottom: 8px;
    }
    .tier-box {
      background: var(--panel); border: 1px solid var(--border); border-radius: 9px;
      padding: 10px 12px; margin-bottom: 10px;
    }
    .tier-label {
      font-size: 0.7rem; font-family: var(--mono); color: var(--accent);
      text-transform: uppercase; font-weight: 700; margin-bottom: 4px;
    }
    .second-brain-grid {
      flex: 1; display: grid; grid-template-columns: 1fr 1fr; gap: 14px;
      padding: 14px; overflow-y: auto; min-height: 0;
    }
    .card-panel {
      background: var(--bg-sidebar); border: 1px solid var(--border);
      border-radius: 12px; display: flex; flex-direction: column; min-height: 0; overflow: hidden;
    }
    .tree-node {
      padding: 6px 9px; border-radius: 6px; font-family: var(--mono);
      font-size: 0.78rem; cursor: pointer; display: flex; justify-content: space-between;
      color: #cbd5e1;
    }
    .tree-node:hover { background: var(--panel-hover); color: var(--accent); }

    /* INTERACTIVE HELP ICONS (?) WITH HOVER TOOLTIP & CLICK-TO-DOCS DRAWER */
    .help-btn {
      display: inline-flex; align-items: center; justify-content: center;
      width: 18px; height: 18px; border-radius: 50%;
      background: rgba(56, 189, 248, 0.14); color: var(--accent);
      border: 1px solid rgba(56, 189, 248, 0.45);
      font-size: 0.7rem; font-weight: 800; font-family: var(--mono);
      cursor: pointer; margin-left: 6px; transition: all 0.15s;
      vertical-align: middle; user-select: none;
    }
    .help-btn:hover {
      background: var(--accent); color: #070b14;
      box-shadow: 0 0 10px rgba(56, 189, 248, 0.5);
      transform: scale(1.08);
    }
    .floating-tooltip {
      position: fixed; z-index: 9999; pointer-events: none;
      max-width: 310px; background: #0b1324; color: #f1f5f9;
      border: 1px solid var(--accent); border-radius: 10px;
      padding: 10px 12px; font-size: 0.77rem; line-height: 1.45;
      box-shadow: 0 12px 28px rgba(0, 0, 0, 0.65);
      display: none;
    }
    .floating-tooltip .tt-hint {
      display: block; margin-top: 5px; font-size: 0.68rem;
      color: var(--accent); font-family: var(--mono);
    }

    /* SCOPED CONTEXT ATTACHMENT BAR (ChatGPT / Claude Code Style) */
    .context-bar {
      display: flex; align-items: center; justify-content: space-between;
      gap: 8px; flex-wrap: wrap; padding: 6px 10px;
      background: #080e1c; border: 1px solid var(--border); border-radius: 9px;
    }
    .context-chips {
      display: flex; align-items: center; gap: 6px; flex-wrap: wrap; flex: 1;
    }
    .ctx-chip {
      display: inline-flex; align-items: center; gap: 6px;
      padding: 3px 9px; border-radius: 999px; font-size: 0.74rem;
      background: rgba(56, 189, 248, 0.13); color: #e2e8f0;
      border: 1px solid rgba(56, 189, 248, 0.35); font-family: var(--mono);
    }
    .ctx-chip .chip-rm {
      cursor: pointer; color: var(--rose); font-weight: 800; margin-left: 2px;
    }
    .ctx-add-btns {
      display: flex; align-items: center; gap: 5px; flex-wrap: wrap;
    }
    .btn-xs {
      padding: 4px 8px; font-size: 0.72rem; border-radius: 7px;
      background: #131e36; color: #e2e8f0; border: 1px solid var(--border);
      cursor: pointer; font-weight: 600; display: inline-flex; align-items: center; gap: 4px;
    }
    .btn-xs:hover { border-color: var(--accent); color: var(--accent); }

    /* STUDIO 3-COLUMN GRID FOR TAB 3 */
    .studio-grid {
      flex: 1; display: grid; grid-template-columns: 1.15fr 1fr 0.95fr; gap: 14px;
      padding: 14px; overflow-y: auto; min-height: 0;
    }
    .cfg-row {
      display: flex; flex-direction: column; gap: 4px; margin-bottom: 9px;
    }
    .cfg-row label {
      font-size: 0.73rem; color: #cbd5e1; font-weight: 600;
    }

    /* INTERACTIVE DOCUMENTATION DRAWER */
    .help-drawer-backdrop {
      position: fixed; inset: 0; background: rgba(3, 6, 14, 0.68);
      z-index: 9000; display: none; justify-content: flex-end;
    }
    .help-drawer {
      width: 500px; max-width: 92vw; height: 100vh;
      background: var(--bg-sidebar); border-left: 1px solid var(--accent);
      display: flex; flex-direction: column; box-shadow: -12px 0 34px rgba(0,0,0,0.7);
    }
    .doc-section {
      background: var(--panel); border: 1px solid var(--border);
      border-radius: 10px; padding: 13px 15px; margin-bottom: 12px;
      transition: border-color 0.25s, box-shadow 0.25s;
    }
    .doc-section.highlight {
      border-color: var(--accent);
      box-shadow: 0 0 18px rgba(56, 189, 248, 0.28);
    }
    .doc-section h4 {
      margin: 0 0 6px 0; color: var(--accent); font-size: 0.9rem;
    }
    .doc-section p {
      margin: 0; font-size: 0.8rem; color: #cbd5e1; line-height: 1.5;
    }
  </style>
</head>
<body>
  <!-- GLOBAL FLOATING TOOLTIP FOR (?) HELP ICONS -->
  <div id="global-tooltip" class="floating-tooltip"></div>
  <input type="file" id="hidden-file-picker" style="display:none;" onchange="handleBrowserFileSelected(event)" />

  <!-- INTERACTIVE DOCUMENTATION DRAWER (OPENS ON CLICKING ANY '?' ICON) -->
  <div id="help-drawer-backdrop" class="help-drawer-backdrop" onclick="closeHelpDrawer(event)">
    <div class="help-drawer" onclick="event.stopPropagation()">
      <div class="pane-header" style="border-bottom-color: rgba(56,189,248,0.3);">
        <span id="help-drawer-title" style="color:var(--accent); font-size:0.84rem;">📖 Guida Interattiva di Cortical v0.4 (IT / EN)</span>
        <div style="display:flex; gap:6px; align-items:center;">
          <button class="btn btn-ghost" style="padding:3px 8px; font-size:0.72rem;" id="btn-drawer-lang" onclick="toggleUiLanguage()">🇬🇧 EN</button>
          <button class="btn btn-ghost" id="btn-help-close" style="padding:3px 9px;" onclick="closeHelpDrawer()">✕ Chiudi</button>
        </div>
      </div>
      <div class="pane-body" id="help-drawer-body">
        <div class="doc-section" id="doc-stream">
          <h4>⚡ Stream Operativo, Audio Ducking & Isolamento Voce Utente</h4>
          <p>Mostra in tempo reale la conversazione vocale/testuale e i passaggi degli agenti. Cortical riproduce la propria voce tramite <b>Web Audio GainNode</b> abbinato alla cancellazione acustica dell'eco WebRTC (<code>echoCancellation</code>) e analisi spettrale: quando parli, <b>abbassa istantaneamente il volume dell'assistente al 14%</b> (stile Alexa / Google Home), isola e dà priorità alla tua frase, e se fai una nuova domanda interrompe la risposta precedente ricalcolando subito. Supporta italiano e inglese.</p>
        </div>
        <div class="doc-section" id="doc-attachments">
          <h4>📎 Contesto Allegato per Chat e Task (File, Cartelle, Skill, Plugin)</h4>
          <p>Cortical <b>non</b> pre-carica automaticamente la propria cartella sorgente. Come in ChatGPT o Claude Code, per ogni discussione o task puoi allegare esplicitamente <b>📄 File</b>, <b>📁 Cartelle</b>, <b>⚡ Skill</b> e <b>🔌 Plugin/MCP</b>. Gli elementi allegati vengono sintetizzati nei 3+1 livelli (Light, Medium, High, Max) e passati automaticamente al Cortical Harness.</p>
        </div>
        <div class="doc-section" id="doc-graph">
          <h4>🧠 Grafo Semantico dei Concetti (MCP)</h4>
          <p>Rappresenta la memoria concettuale (non l'elenco grezzo dei file): mostra i <b>5 Pilastri Fondamentali del Framework</b> (anello doppio 🔒) insieme ai concetti estratti dai tuoi allegati, agli insight appresi dalle conversazioni, alle skill generate e ai task.</p>
        </div>
        <div class="doc-section" id="doc-concept-config">
          <h4>⚙️ Configurazione ed Eliminazione dei Concetti</h4>
          <p>Cliccando un nodo nel Grafo dei Concetti:<br/>
          • <b>Concetti Fondamentali del Framework (🔒 Core):</b> sono protetti da eliminazione, ma puoi <b>configurarli dal vivo</b> (es. in <i>Orchestratore Multi-Agente</i> imposti quanti loop massimi fanno gli agenti e quali modelli usare per Analyst, Implementer e Reviewer).<br/>
          • <b>Concetti Sviluppati / Utente (✨ Utente):</b> puoi sia configurarli sia eliminarli definitivamente dalla memoria cliccando <b>🗑️ Elimina Concetto dalla Memoria</b>.</p>
        </div>
        <div class="doc-section" id="doc-studio">
          <h4>🧭 Studio Contesto 3+1, Skill Router & Sicurezza</h4>
          <p>La terza tab centrale sostituisce i vecchi dump JSON con uno studio operativo in 3 colonne:<br/>
          1. <b>Ispezione Sintesi 3+1 degli Allegati:</b> vedi come Cortical comprime i tuoi file e cartelle in L1 (~50 token), L2 (~250 token), L3 (~1000 token) e +1 Max.<br/>
          2. <b>Simulatore Prompt & Skill:</b> verifica quali skill e quali modelli vengono iniettati per qualsiasi richiesta.<br/>
          3. <b>Adaptive Permission Gate:</b> gestisci i comandi auto-approvati e testa i blocchi deterministici.</p>
        </div>
        <div class="doc-section" id="doc-tasks">
          <h4>🤖 Task Espliciti Multi-Agente & Archiviazione 3+1</h4>
          <p>Le chiacchierate quotidiane (ora, meteo, domande veloci) non aprono task. Un task si apre solo quando clicchi <b>+ Nuovo Task</b>, selezioni la modalità Task nel composer o usi <code>/task</code> in <code>pi</code>. Quando clicchi <b>📦 Archivia</b>, Cortical sintetizza la discussione nei 3+1 livelli e valuta se compilare una nuova Skill procedurale.</p>
        </div>
      </div>
    </div>
  </div>

  <!-- TOP MISSION CONTROL BAR WITH PRIMARY CENTRAL NAVIGATION -->
  <div class="topbar">
    <div class="brand">
      <div class="brand-logo">C</div>
      <div>
        <div class="brand-title">Cortical Mission Control</div>
        <div class="brand-sub" id="hw-banner">Inizializzazione profilo hardware...</div>
      </div>
    </div>

    <!-- DEDICATED CENTRAL WORKSPACE TABS -->
    <div class="main-nav">
      <div class="nav-tab active" id="main-tab-stream" onclick="switchMainStage('stream')">
        <span id="lbl-tab-stream">⚡ Stream & Voce</span>
        <span class="help-btn" data-tip="Flusso live, audio ducking stile Alexa, isolamento voce e passi degli agenti." data-tip-en="Live stream, Alexa-style audio ducking, user voice isolation & agent steps." onclick="openHelpSection('doc-stream', event)">?</span>
      </div>
      <div class="nav-tab" id="main-tab-graph" onclick="switchMainStage('graph')">
        <span id="lbl-tab-graph">🧠 Grafo dei Concetti</span> <span id="nav-graph-count" style="font-family:var(--mono); font-size:0.72rem; opacity:0.85;">(MCP)</span>
        <span class="help-btn" data-tip="Mappa interattiva dei concetti: configura i parametri del framework (loop, modelli) o elimina i concetti utente." data-tip-en="Interactive concept map: configure framework pillars (loops, models) or delete user concepts." onclick="openHelpSection('doc-graph', event)">?</span>
      </div>
      <div class="nav-tab" id="main-tab-brain" onclick="switchMainStage('brain')">
        <span id="lbl-tab-brain">📎 Contesto 3+1, Skill & Sicurezza</span>
        <span class="help-btn" data-tip="Gestisci file/cartelle/skill/plugin allegati, ispeziona sintesi 3+1 e permessi." data-tip-en="Manage attached files/folders/skills/plugins, inspect 3+1 syntheses and permissions." onclick="openHelpSection('doc-studio', event)">?</span>
      </div>
    </div>

    <!-- VOICE, DUCKING & BILINGUAL CONTROLS -->
    <div class="voice-bar">
      <div class="pulse-dot" id="mic-dot"></div>
      <span class="live-transcript" id="live-transcript">Ducking & AEC pronti · Di' "Ehi Cortical..."</span>
      <span id="acoustic-duck-badge" style="font-family:var(--mono); font-size:0.7rem; padding:3px 7px; border-radius:6px; border:1px solid var(--border); color:var(--muted);">🔊 100%</span>
      <button class="btn" id="btn-always-on" onclick="toggleAlwaysOnMic()">🎤 Mic: OFF</button>
      <select id="tts-voice" title="Bilingual Neural Voice (IT / EN)">
        <option value="auto" selected>🌐 Auto (IT / EN)</option>
        <option value="IsabellaNeural">🇮🇹 Isabella Neurale</option>
        <option value="GiuseppeNeural">🇮🇹 Giuseppe Neurale</option>
        <option value="ElsaNeural">🇮🇹 Elsa Neurale</option>
        <option value="DiegoNeural">🇮🇹 Diego Neurale</option>
        <option value="JennyNeural">🇺🇸 Jenny Neural (EN)</option>
        <option value="GuyNeural">🇺🇸 Guy Neural (EN)</option>
        <option value="AriaNeural">🇺🇸 Aria Neural (EN)</option>
        <option value="SoniaNeural">🇬🇧 Sonia Neural (EN)</option>
        <option value="Federica">🇮🇹 Federica (Offline)</option>
        <option value="Samantha">🇺🇸 Samantha (Offline EN)</option>
      </select>
      <button class="btn btn-danger" id="btn-stop-top" onclick="triggerStopBargeIn()" title="Ferma immediatamente voce e agenti / Stop immediately">🛑 Stop</button>
      <button class="btn btn-ghost" onclick="openNativePiTerminal()" title="Apre pi nel Terminale / Open pi in Terminal">🖥️ `pi`</button>
      <button class="btn btn-ghost" id="btn-ui-lang" style="border-color: rgba(56,189,248,0.55); color: var(--accent);" onclick="toggleUiLanguage()" title="Switch Language / Cambia Lingua (IT / EN)">🌐 IT / EN</button>
      <button class="btn btn-ghost" id="btn-guide-top" onclick="openHelpSection('doc-stream', event)" title="Guida Interattiva / Interactive Guide">📖 Guida</button>
    </div>
  </div>

  <!-- MAIN WORKSPACE: LEFT TASK SIDEBAR + CENTRAL MULTI-STAGE VIEW -->
  <div class="workspace">
    <!-- LEFT SIDEBAR: EXPLICIT MULTI-AGENT TASKS & QUICK CONCEPT SUMMARY -->
    <div class="sidebar">
      <div class="pane-header">
        <span>
          Task Espliciti `pi`
          <span class="help-btn" data-tip="Elenco dei task multi-agente aperti su richiesta. Puoi archiviarli nei 3+1 livelli o cancellarli." onclick="openHelpSection('doc-tasks', event)">?</span>
        </span>
        <div style="display:flex; gap:5px;">
          <button class="btn btn-ghost" style="padding:3px 7px; font-size:0.68rem;" onclick="clearArchivedTasks()" title="Rimuove tutti i task già archiviati">🧹 Pulisci</button>
          <button class="btn" style="padding:3px 8px; font-size:0.72rem;" onclick="spawnQuickAgent()">+ Nuovo Task</button>
        </div>
      </div>
      <div class="pane-body" id="agent-roster" style="flex: 1;">
        <div style="color:var(--muted); font-size:0.78rem;">
          Le conversazioni normali non aprono task. Crea un task solo quando vuoi orchestrare un lavoro strutturato con sintesi 3+1 finale.
        </div>
      </div>

      <!-- QUICK CONCEPT GRAPH LAUNCHER CARD -->
      <div style="padding: 12px 14px; border-top: 1px solid var(--border); background: #090f1d;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
          <span style="font-size:0.74rem; font-weight:700; color:var(--accent); text-transform:uppercase;">
            🧠 Mappa Concettuale
            <span class="help-btn" data-tip="Apre il Grafo dei Concetti per configurare loop/modelli degli agenti o rimuovere concetti appresi." onclick="openHelpSection('doc-concept-config', event)">?</span>
          </span>
          <span id="sidebar-graph-stats" style="font-size:0.71rem; font-family:var(--mono); color:var(--muted);">-- concetti</span>
        </div>
        <div style="font-size:0.76rem; color:var(--muted); margin-bottom:9px;">
          Configura i pilastri del framework (loop agenti, modelli LLM) o elimina concetti utente dal grafo.
        </div>
        <button class="btn" style="width:100%; justify-content:center;" onclick="switchMainStage('graph')">
          🧠 Apri Grafo & Configura Concetti
        </button>
      </div>
    </div>

    <!-- CENTRAL STAGE (3 SWITCHABLE FULL-SIZE VIEWS + PERSISTENT COMPOSER) -->
    <div class="main-stage">
      <!-- STAGE 1: LIVE CONVERSATION & MULTI-AGENT EXECUTION STREAM -->
      <div class="stage-view" id="stage-stream">
        <div class="pane-header">
          <span>
            Stream Conversazionale & Multi-Agente (Isolamento Sorgenti · Contesto Allegato · Voce Anti-Eco)
            <span class="help-btn" data-tip="Cronologia live delle risposte vocali/testuali e delle azioni eseguite dagli agenti nel contesto corrente." onclick="openHelpSection('doc-stream', event)">?</span>
          </span>
          <span style="font-family:var(--mono); font-size:0.73rem; color:var(--accent);" id="active-session-badge">CHAT & VOICE</span>
        </div>
        <div class="pane-body" id="agent-stream">
          <div class="step-card output">
            <div class="step-meta"><span>CORTICAL v0.4 READY</span><span>Contesto Allegato · Concetti Configurabili · Guida Interattiva</span></div>
            <div class="step-title">Benvenuto in Cortical v0.4 — Controllo Totale su Contesto e Concetti</div>
            <pre class="step-detail">• 📎 Contesto Isolato (Stile ChatGPT / Claude Code): Cortical NON pre-carica più la propria cartella sorgente. Usa la barra "📎 Contesto Attivo" qui sotto per allegare 📄 File, 📁 Cartelle, ⚡ Skill o 🔌 Plugin specifici alla tua chat o al tuo task.
• 🧠 Grafo dei Concetti Configurabile: nella tab "🧠 Grafo dei Concetti", clicca sui concetti fondamentali (🔒) per configurare quanti loop massimi eseguono gli agenti e quali modelli usare per ogni ruolo, oppure elimina (🗑️) i concetti sviluppati dall'utente.
• ❓ Aiuto Contestuale Ovunque: passa il mouse sulle icone "?" per una spiegazione immediata, oppure cliccale per aprire il capitolo dedicato della Guida Interattiva.</pre>
          </div>
        </div>
      </div>

      <!-- STAGE 2: DEDICATED CENTRAL CONCEPT KNOWLEDGE GRAPH -->
      <div class="stage-view" id="stage-graph" style="display:none;">
        <div class="graph-stage-grid">
          <div class="graph-main-area">
            <div class="graph-toolbar">
              <div class="filter-pills" id="graph-filter-pills">
                <span class="pill active" onclick="setGraphFilter('all', this)">Tutti i Nodi</span>
                <span class="pill" onclick="setGraphFilter('concept', this)">🧠 Concetti</span>
                <span class="pill" onclick="setGraphFilter('memoria', this)">📚 Memoria 3+1</span>
                <span class="pill" onclick="setGraphFilter('agenti', this)">🤖 Agenti & Loop</span>
                <span class="pill" onclick="setGraphFilter('voce', this)">🎙️ Voce</span>
                <span class="pill" onclick="setGraphFilter('sicurezza', this)">🛡️ Sicurezza</span>
                <span class="pill" onclick="setGraphFilter('insight', this)">💡 Insight</span>
                <span class="pill" onclick="setGraphFilter('skill', this)">⚡ Skill</span>
                <span class="pill" onclick="setGraphFilter('task', this)">🎯 Task</span>
              </div>
              <div style="display:flex; gap:6px; align-items:center;">
                <input id="graph-search-input" placeholder="Filtra concetto..." style="width:165px; padding:5px 9px;" oninput="renderKnowledgeGraphSvg()" />
                <button class="btn btn-ghost" style="padding:5px 10px;" onclick="loadMcpKnowledgeGraph()">🔄 Sincronizza</button>
                <span class="help-btn" data-tip="Trascina i nodi con il mouse. I nodi con doppio anello (🔒) sono pilastri configurabili del framework; gli altri sono concetti utente eliminabili." onclick="openHelpSection('doc-graph', event)">?</span>
              </div>
            </div>

            <div class="graph-canvas-wrap" id="graph-canvas-container">
              <div class="graph-legend">
                <span><i class="legend-dot" style="background:#38bdf8; border:2px solid #fff;"></i>🔒 Pilastro Framework (Configurabile)</span>
                <span><i class="legend-dot" style="background:#c084fc;"></i>✨ Concetto Utente (Eliminabile)</span>
                <span><i class="legend-dot" style="background:#34d399;"></i>💡 Insight</span>
                <span><i class="legend-dot" style="background:#fbbf24;"></i>⚡ Skill / Task</span>
              </div>
              <svg id="mcp-graph-svg" width="100%" height="100%" viewBox="0 0 920 560"></svg>
              <div class="graph-zoom-controls">
                <button class="btn btn-ghost" style="padding:4px 9px;" onclick="zoomGraph(1.2)" title="Ingrandisci">＋</button>
                <button class="btn btn-ghost" style="padding:4px 9px;" onclick="zoomGraph(0.84)" title="Riduci">－</button>
                <button class="btn btn-ghost" style="padding:4px 9px;" onclick="resetGraphView()" title="Centra grafo">Centra</button>
              </div>
            </div>
          </div>

          <!-- RIGHT CONCEPT INSPECTOR, CONFIGURATOR & DELETION DRAWER -->
          <div class="concept-drawer">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
              <span style="font-size:0.74rem; font-weight:700; color:var(--muted); text-transform:uppercase; letter-spacing:0.06em;">
                Scheda & Configurazione Concetto
              </span>
              <span class="help-btn" data-tip="Configura i parametri operativi del concetto (es. loop massimi agenti, modelli LLM) o elimina i concetti sviluppati dall'utente." onclick="openHelpSection('doc-concept-config', event)">?</span>
            </div>
            <div id="concept-detail-panel">
              <div class="concept-badge" id="cd-badge">🔒 PILASTRO FRAMEWORK</div>
              <h3 id="cd-title" style="margin: 0 0 8px 0; font-size: 1.08rem; color: var(--text);">Orchestratore Multi-Agente</h3>

              <!-- DYNAMIC CONFIGURATION FORM FOR SELECTED CONCEPT -->
              <div class="tier-box" id="cd-config-box" style="border-color: rgba(56,189,248,0.4);">
                <div class="tier-label">⚙️ Configurazione Parametri del Concetto</div>
                <div id="cd-config-form" style="margin-top:6px; font-size:0.78rem; color:var(--muted);">
                  Clicca su un nodo del grafo (es. "Orchestratore Multi-Agente") per configurarne loop massimi, modelli e comportamento.
                </div>
              </div>

              <!-- DELETE ACTION FOR USER-DEVELOPED CONCEPTS -->
              <div id="cd-delete-box" style="margin-bottom:10px;"></div>

              <div class="tier-box">
                <div class="tier-label">Livello 1 — Sintesi Light (~50 token)</div>
                <div id="cd-summary-l1" style="font-size:0.82rem; color:#e2e8f0; line-height:1.45;">
                  Seleziona un nodo nel grafo per visualizzarne la sintesi e i parametri.
                </div>
              </div>
              <div class="tier-box">
                <div class="tier-label">Livello 2 — Struttura & Relazioni (~250 token)</div>
                <div id="cd-summary-l2" style="font-size:0.79rem; color:var(--muted); line-height:1.45;">
                  I pilastri fondamentali del framework possono essere configurati in tempo reale; i concetti utente possono anche essere eliminati.
                </div>
              </div>
              <div class="tier-box">
                <div class="tier-label">Connessioni Semantiche & Fonti</div>
                <div id="cd-connections" style="font-size:0.76rem; font-family:var(--mono); color:#cbd5e1; margin-bottom:4px;">--</div>
                <div id="cd-sources" style="font-size:0.73rem; font-family:var(--mono); color:var(--accent);">framework:core</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- STAGE 3: CLEAR, NON-DUPLICATE CONTEXT, 3+1 SYNTHESIS & SECURITY STUDIO -->
      <div class="stage-view" id="stage-brain" style="display:none;">
        <div class="studio-grid">
          <!-- COLUMN 1: SCOPED CONTEXT MANAGER (FILES, FOLDERS, SKILLS, PLUGINS) & 3+1 PREVIEW -->
          <div class="card-panel">
            <div class="pane-header">
              <span>
                📎 1. Contesto Allegato & Sintesi 3+1
                <span class="help-btn" data-tip="Allega file, cartelle, skill o plugin alla chat/task corrente e visualizza come vengono sintetizzati nei 3+1 livelli." onclick="openHelpSection('doc-attachments', event)">?</span>
              </span>
              <button class="btn btn-ghost" style="padding:3px 8px; font-size:0.7rem;" onclick="loadScopedContext()">🔄 Aggiorna</button>
            </div>
            <div class="pane-body">
              <div style="font-size:0.77rem; color:var(--muted); margin-bottom:10px; line-height:1.4;">
                Aggiungi solo i file, le cartelle, le skill e i plugin che vuoi passare all'harness per questa conversazione o task:
              </div>
              <div style="display:grid; grid-template-columns: 110px 1fr 95px; gap:6px; margin-bottom:8px;">
                <select id="ctx-item-type">
                  <option value="file">📄 File</option>
                  <option value="folder">📁 Cartella</option>
                  <option value="skill">⚡ Skill</option>
                  <option value="plugin">🔌 Plugin/MCP</option>
                </select>
                <input id="ctx-item-ref" placeholder="Percorso file/cartella o nome skill/plugin..." onkeydown="if(event.key==='Enter') attachFromStudio()" />
                <select id="ctx-item-tier" title="Livello sintesi 3+1">
                  <option value="light">L1 Light</option>
                  <option value="medium" selected>L2 Medium</option>
                  <option value="high">L3 High</option>
                  <option value="max">+1 Max</option>
                </select>
              </div>
              <div style="display:flex; gap:6px; margin-bottom:12px;">
                <button class="btn" style="flex:1; justify-content:center;" onclick="attachFromStudio()">+ Allega al Contesto Attivo</button>
                <button class="btn btn-ghost" onclick="document.getElementById('hidden-file-picker').click()">📂 Sfoglia File Locale…</button>
              </div>

              <div style="font-size:0.72rem; font-weight:700; color:var(--accent); text-transform:uppercase; margin-bottom:6px;">
                Elementi Attualmente Allegati al Contesto
              </div>
              <div id="studio-context-list" style="margin-bottom:12px;"></div>

              <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                <span style="font-size:0.72rem; font-weight:700; color:var(--muted); text-transform:uppercase;">
                  Ispezione Sintesi 3+1 del Nodo Selezionato
                </span>
                <select id="wiki-depth" onchange="navigateWiki(currentWikiPath)" style="padding:2px 6px; font-size:0.71rem;">
                  <option value="light">L1 LIGHT (~50t)</option>
                  <option value="medium" selected>L2 MEDIUM (~250t)</option>
                  <option value="high">L3 HIGH (~1000t)</option>
                  <option value="max">+1 MAX (Integrale)</option>
                </select>
              </div>
              <pre class="step-detail" id="wiki-node-view" style="max-height:170px;">Nessun file pre-caricato. Allega un file o una cartella qui sopra per ispezionare in tempo reale le sue 4 sintesi gerarchiche (Light, Medium, High, Max).</pre>
            </div>
          </div>

          <!-- COLUMN 2: PARALLEL SKILL ROUTER & PROMPT ENHANCEMENT SIMULATOR -->
          <div class="card-panel">
            <div class="pane-header">
              <span>
                ⚡ 2. Skill in Parallelo & Simulatore Harness
                <span class="help-btn" data-tip="Mostra le Skill disponibili (3+1 Memoria + Procedurali) e simula come il tuo prompt viene arricchito prima di arrivare al modello." onclick="openHelpSection('doc-studio', event)">?</span>
              </span>
              <button class="btn btn-ghost" style="padding:3px 8px; font-size:0.7rem;" onclick="loadSkillsHub()">🔄 Skill</button>
            </div>
            <div class="pane-body">
              <div style="font-size:0.77rem; color:var(--muted); margin-bottom:8px;">
                Verifica come l'harness combina il tuo <b>Contesto Allegato</b>, la <b>Skill di Memoria 3+1</b> e i <b>Modelli Configurati</b>:
              </div>
              <div style="display:flex; gap:6px; margin-bottom:10px;">
                <input id="skill-test-input" placeholder="Simula un prompt (es: 'analizza gli allegati e crea i test')..." style="flex:1;" onkeydown="if(event.key==='Enter') testPromptEnhancer()" />
                <button class="btn" onclick="testPromptEnhancer()">Simula</button>
              </div>
              <pre class="step-detail" id="skill-enhance-view" style="max-height:185px; margin-bottom:12px;">Premi "Simula" per vedere il payload esatto (allegati + livello 3+1 + skill + modelli/loop) che viene iniettato nel contesto dell'agente.</pre>
              <div style="font-size:0.72rem; font-weight:700; color:var(--muted); text-transform:uppercase; margin-bottom:6px;">
                Catalogo Skill (Clicca "+ Allega" per forzarne l'attivazione nella chat)
              </div>
              <div id="skills-list-view"></div>
            </div>
          </div>

          <!-- COLUMN 3: ADAPTIVE PERMISSION GATE & CURATED CONVERSATION MEMORY -->
          <div class="card-panel">
            <div class="pane-header">
              <span>
                🛡️ 3. Sicurezza Adattiva & Memoria Curata
                <span class="help-btn" data-tip="Valuta la sicurezza dei comandi prima dell'esecuzione e mostra gli insight salvati (filtrando le chiacchierate effimere)." onclick="openHelpSection('doc-studio', event)">?</span>
              </span>
              <button class="btn btn-ghost" style="padding:3px 8px; font-size:0.7rem;" onclick="loadSmartMemory()">🧠 Memoria</button>
            </div>
            <div class="pane-body">
              <div style="font-size:0.72rem; font-weight:700; color:var(--accent); text-transform:uppercase; margin-bottom:6px;">
                🛡️ Verifica Comandi (Adaptive Permission Gate)
              </div>
              <div style="font-size:0.76rem; color:var(--muted); margin-bottom:8px;">
                Blocca comandi distruttivi (<code>rm -rf /</code>) e impara i comandi sicuri che approvi:
              </div>
              <div style="display:flex; gap:5px; margin-bottom:8px; flex-wrap:wrap;">
                <select id="perm-tool">
                  <option value="bash">bash</option>
                  <option value="write_file">write_file</option>
                  <option value="chrome">chrome</option>
                </select>
                <input id="perm-cmd" value="pytest tests/" style="flex:1; min-width:120px;" />
              </div>
              <div style="display:flex; gap:6px; margin-bottom:10px;">
                <button class="btn" onclick="evalPerm()">Valuta Comando</button>
                <button class="btn btn-ghost" onclick="feedbackPerm(true)">👍 Approva & Impara</button>
                <button class="btn btn-danger" onclick="testHardBlock()">Test Blocco</button>
              </div>
              <pre class="step-detail" id="perm-view" style="max-height:125px; margin-bottom:14px;">Adaptive Permission Gate pronto.</pre>

              <div style="font-size:0.72rem; font-weight:700; color:var(--emerald); text-transform:uppercase; margin-bottom:6px;">
                💡 Memoria Conversazionale Curata (Max 20 Turni FIFO)
              </div>
              <pre class="step-detail" id="memory-state-view" style="max-height:175px;">Clicca "🧠 Memoria" per ispezionare il buffer leggero delle chiacchierate e gli insight estratti.</pre>
            </div>
          </div>
        </div>
      </div>

      <!-- PERSISTENT PROMPT, CONTEXT ATTACHMENT BAR & VOICE COMPOSER -->
      <div class="composer">
        <!-- CHATGPT / CLAUDE CODE STYLE SCOPED CONTEXT ATTACHMENT BAR -->
        <div class="context-bar">
          <div class="context-chips" id="composer-context-chips">
            <span style="font-size:0.74rem; color:var(--muted); font-family:var(--mono);">
              📎 Contesto Attivo: <i style="color:#64748b;">Nessun file/cartella pre-caricata (contesto pulito)</i>
            </span>
          </div>
          <div class="ctx-add-btns">
            <button class="btn-xs" onclick="document.getElementById('hidden-file-picker').click()" title="Sfoglia e allega un file dal tuo computer">+ 📄 Sfoglia File</button>
            <button class="btn-xs" onclick="quickAttachPrompt('file')" title="Allega un file tramite percorso">+ 📄 Percorso File</button>
            <button class="btn-xs" onclick="quickAttachPrompt('folder')" title="Allega una cartella specifica al contesto">+ 📁 Cartella</button>
            <button class="btn-xs" onclick="quickAttachPrompt('skill')" title="Attiva una Skill specifica nella chat">+ ⚡ Skill</button>
            <button class="btn-xs" onclick="quickAttachPrompt('plugin')" title="Attiva un Plugin o Server MCP nella chat">+ 🔌 Plugin</button>
            <span class="help-btn" data-tip="Come in ChatGPT o Claude Code, allega file, cartelle, skill o plugin specifici per questa conversazione o task. Cortical non carica file non richiesti." onclick="openHelpSection('doc-attachments', event)">?</span>
          </div>
        </div>

        <div class="composer-row">
          <select id="dispatch-mode">
            <option value="auto">💬 Conversazione & Voce (Crea task solo se richiesto esplicitamente)</option>
            <option value="agent">🤖 Apri Nuovo Task Multi-Agente `pi` (Con Sintesi 3+1 & Contesto Allegato)</option>
          </select>
          <select id="agent-depth">
            <option value="light">Memoria 3+1: L1 LIGHT</option>
            <option value="medium" selected>Memoria 3+1: L2 MEDIUM</option>
            <option value="high">Memoria 3+1: L3 HIGH</option>
            <option value="max">Memoria 3+1: +1 MAX (Full)</option>
          </select>
          <label style="font-size:0.79rem; color:var(--muted); display:flex; align-items:center; gap:5px; cursor:pointer;">
            <input type="checkbox" id="chk-speak" checked /> Pronuncia risposta (Voce Neurale Ita)
          </label>
        </div>
        <div class="composer-row">
          <input id="prompt-input" placeholder="Chiedi a Cortical (con i file/skill allegati qui sopra) o di' 'Ehi Cortical...'" onkeydown="if(event.key==='Enter') submitComposer()" />
          <button class="btn" onclick="submitComposer()">Invia ↵</button>
        </div>
      </div>
    </div>
  </div>

  <script>
    let currentWikiPath = '/';
    let selectedSessionId = null;
    let selectedConceptNode = null;
    let alwaysOnActive = false;
    let recognition = null;
    let lastSpokenResponseText = '';
    let lastSpokenAtMs = 0;
    let localTtsShieldUntilMs = 0;
    let activeAbortController = null;
    let cachedAttachments = [];
    let uiLang = localStorage.getItem('cortical_ui_lang') || 'it';

    // Interactive Concept Graph State
    let cachedGraphData = { nodes: [], edges: [], stats: {} };
    let currentGraphFilter = 'all';
    let graphZoom = 1.0;
    let graphPanX = 0;
    let graphPanY = 0;
    let isPanningGraph = false;
    let panStartX = 0;
    let panStartY = 0;
    let draggedNodeId = null;
    let nodePositions = {};

    const I18N = {
      it: {
        guideTitle: '📖 Guida Interattiva di Cortical v0.4 (IT / EN)',
        close: '✕ Chiudi',
        toggleLangBtn: '🇮🇹 IT',
        drawerLangBtn: '🇬🇧 EN',
        tabStream: '⚡ Stream & Voce',
        tabGraph: '🧠 Grafo dei Concetti',
        tabBrain: '📎 Contesto 3+1, Skill & Sicurezza',
        guideBtn: '📖 Guida',
        micOff: '🎤 Mic: OFF',
        micOn: '🟢 Mic Attivo',
        micDenied: '🎤 Mic: Negato',
        promptPlaceholder: "Chiedi a Cortical (IT o EN) con i file/skill allegati o di' 'Ehi Cortical...'",
        liveReady: `Ducking & AEC pronti · Di' "Ehi Cortical..." o "Hey Cortical..."`,
        duckNormal: '🔊 100%',
        duckLow: '🔉 14% Duck · Priorità Voce',
        newTaskBtn: '+ Nuovo Task',
        clearBtn: '🧹 Pulisci',
        openGraphBtn: '🧠 Apri Grafo & Configura Concetti',
        tooltipHint: '💡 Clicca per aprire la guida interattiva',
      },
      en: {
        guideTitle: '📖 Cortical v0.4 Interactive Guide (EN / IT)',
        close: '✕ Close',
        toggleLangBtn: '🇬🇧 EN',
        drawerLangBtn: '🇮🇹 IT',
        tabStream: '⚡ Stream & Voice',
        tabGraph: '🧠 Concept Graph',
        tabBrain: '📎 Context 3+1, Skills & Safety',
        guideBtn: '📖 Guide',
        micOff: '🎤 Mic: OFF',
        micOn: '🟢 Mic Active',
        micDenied: '🎤 Mic: Denied',
        promptPlaceholder: "Ask Cortical (EN or IT) with attached files/skills or say 'Hey Cortical...'",
        liveReady: 'Ducking & AEC Ready · Say "Hey Cortical..." or "Ehi Cortical..."',
        duckNormal: '🔊 100%',
        duckLow: '🔉 14% Duck · Voice Priority',
        newTaskBtn: '+ New Task',
        clearBtn: '🧹 Clear',
        openGraphBtn: '🧠 Open Graph & Configure Concepts',
        tooltipHint: '💡 Click to open the interactive guide',
      }
    };

    const GUIDE_DOCS = {
      it: {
        'doc-stream': ['⚡ Stream Operativo, Audio Ducking & Isolamento Voce Utente', 'Mostra in tempo reale la conversazione vocale/testuale e i passaggi degli agenti. Cortical riproduce la propria voce tramite <b>Web Audio GainNode</b> abbinato alla cancellazione acustica dell\\\'eco WebRTC (<code>echoCancellation</code>) e analisi spettrale: quando parli, <b>abbassa istantaneamente il volume dell\\\'assistente al 14%</b> (stile Alexa / Google Home), isola e dà priorità alla tua frase, e se fai una nuova domanda interrompe la risposta precedente ricalcolando subito. Supporta italiano e inglese.'],
        'doc-attachments': ['📎 Contesto Allegato per Chat e Task (File, Cartelle, Skill, Plugin)', 'Cortical <b>non</b> pre-carica automaticamente la propria cartella sorgente. Come in ChatGPT o Claude Code, per ogni discussione o task puoi allegare esplicitamente <b>📄 File</b>, <b>📁 Cartelle</b>, <b>⚡ Skill</b> e <b>🔌 Plugin/MCP</b>. Gli elementi allegati vengono sintetizzati nei 3+1 livelli (Light, Medium, High, Max) e passati automaticamente al Cortical Harness.'],
        'doc-graph': ['🧠 Grafo Semantico dei Concetti (MCP)', 'Rappresenta la memoria concettuale (non l\\\'elenco grezzo dei file): mostra i <b>5 Pilastri Fondamentali del Framework</b> (anello doppio 🔒) insieme ai concetti estratti dai tuoi allegati, agli insight appresi dalle conversazioni, alle skill generate e ai task.'],
        'doc-concept-config': ['⚙️ Configurazione ed Eliminazione dei Concetti', 'Cliccando un nodo nel Grafo dei Concetti:<br/>• <b>Concetti Fondamentali del Framework (🔒 Core):</b> sono protetti da eliminazione, ma puoi <b>configurarli dal vivo</b> (es. in <i>Orchestratore Multi-Agente</i> imposti quanti loop massimi fanno gli agenti e quali modelli usare).<br/>• <b>Concetti Sviluppati / Utente (✨ Utente):</b> puoi sia configurarli sia eliminarli definitivamente dalla memoria cliccando <b>🗑️ Elimina Concetto dalla Memoria</b>.'],
        'doc-studio': ['🧭 Studio Contesto 3+1, Skill Router & Sicurezza', 'La terza tab centrale unifica 3 strumenti:<br/>1. <b>Ispezione Sintesi 3+1 degli Allegati:</b> compressione in L1 (~50 tok), L2 (~250 tok), L3 (~1000 tok) e +1 Max.<br/>2. <b>Simulatore Prompt & Skill:</b> verifica quali skill e modelli vengono attivati.<br/>3. <b>Adaptive Permission Gate:</b> gestisci permessi automatici e blocchi di sicurezza.'],
        'doc-tasks': ['🤖 Task Espliciti Multi-Agente & Archiviazione 3+1', 'Le chiacchierate quotidiane (ora, meteo, ricerche veloci) non aprono task. Un task si apre solo quando lo richiedi esplicitamente o clicchi <b>+ Nuovo Task</b>. Quando archivi (<b>📦 Archivia</b>), Cortical sintetizza la discussione nei 3+1 livelli e valuta la compilazione di nuove Skill.']
      },
      en: {
        'doc-stream': ['⚡ Live Stream, Alexa-Style Ducking & User Voice Isolation', 'Displays live bilingual voice/text chat and agent steps. Assistant audio plays through a <b>Web Audio GainNode</b> paired with WebRTC hardware echo cancellation (<code>echoCancellation</code>) and spectral tone comparison: when you speak, Cortical <b>smoothly lowers playback volume to 14%</b> (like Alexa / Google Home), isolates your voice from its own assistant tone, and cancels the previous reply to recalculate your new question immediately. Supports English & Italian.'],
        'doc-attachments': ['📎 Scoped Context Attachments (Files, Folders, Skills, Plugins)', 'Cortical <b>never</b> auto-loads its own source repository. Just like ChatGPT or Claude Code, explicitly attach <b>📄 Files</b>, <b>📁 Folders</b>, <b>⚡ Skills</b>, and <b>🔌 Plugins/MCP</b> for any chat or task. Attachments are summarized across 3+1 tiers (Light, Medium, High, Max) and passed cleanly into the Cortical Harness.'],
        'doc-graph': ['🧠 Semantic Concept Knowledge Graph (MCP)', 'Displays conceptual memory rather than raw file dumps: shows the <b>5 Core Framework Pillars</b> (double ring 🔒) connected to concepts extracted from attachments, curated conversation insights, procedural skills, and explicit tasks.'],
        'doc-concept-config': ['⚙️ Concept Configuration & Deletion', 'Click any node in the Concept Graph:<br/>• <b>Core Framework Pillars (🔒 Core):</b> protected from deletion, yet <b>live-configurable</b> (e.g., tune max agent loops and Analyst/Implementer/Reviewer models).<br/>• <b>User-Developed Concepts (✨ User):</b> configurable and permanently removable with <b>🗑️ Delete Concept from Memory</b>.'],
        'doc-studio': ['🧭 3+1 Context Studio, Skill Router & Safety Gate', 'Unifies three live panels:<br/>1. <b>3+1 Attachment Synthesis:</b> inspect compression across L1 (~50 tok), L2 (~250 tok), L3 (~1000 tok), and +1 Max.<br/>2. <b>Skill & Prompt Router Simulator:</b> preview selected skills and tier routing.<br/>3. <b>Adaptive Permission Gate:</b> manage safe patterns and deterministic blocks.'],
        'doc-tasks': ['🤖 Explicit Multi-Agent Tasks & 3+1 Archival', 'Everyday chitchat (clock, weather, quick browser searches) never creates tasks. Tasks spawn only when explicitly requested or via <b>+ New Task</b>. Archiving (<b>📦 Archive</b>) distills discussions into 3+1 Wiki levels and evaluates reusable Skill compilation.']
      }
    };

    function applyUiTranslations(lang) {
      uiLang = (lang === 'en') ? 'en' : 'it';
      localStorage.setItem('cortical_ui_lang', uiLang);
      const t = I18N[uiLang];
      const setTxt = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
      setTxt('help-drawer-title', t.guideTitle);
      setTxt('btn-help-close', t.close);
      setTxt('btn-ui-lang', t.toggleLangBtn);
      setTxt('btn-drawer-lang', t.drawerLangBtn);
      setTxt('lbl-tab-stream', t.tabStream);
      setTxt('lbl-tab-graph', t.tabGraph);
      setTxt('lbl-tab-brain', t.tabBrain);
      setTxt('btn-guide-top', t.guideBtn);
      const micBtn = document.getElementById('btn-always-on');
      if (micBtn) micBtn.textContent = alwaysOnActive ? t.micOn : t.micOff;
      const pi = document.getElementById('prompt-input');
      if (pi && !micFinalBuffer && !micInterimBuffer) pi.placeholder = t.promptPlaceholder;
      const lt = document.getElementById('live-transcript');
      if (lt && !alwaysOnActive) lt.textContent = t.liveReady;
      const guideSet = GUIDE_DOCS[uiLang] || GUIDE_DOCS.it;
      Object.entries(guideSet).forEach(([secId, [title, body]]) => {
        const sec = document.getElementById(secId);
        if (sec) {
          const h4 = sec.querySelector('h4');
          const p = sec.querySelector('p');
          if (h4) h4.innerHTML = title;
          if (p) p.innerHTML = body;
        }
      });
      if (recognition) {
        recognition.lang = (uiLang === 'en') ? 'en-US' : 'it-IT';
      }
    }

    function setUiLanguage(lang) {
      applyUiTranslations(lang);
    }

    function toggleUiLanguage() {
      setUiLanguage(uiLang === 'en' ? 'it' : 'en');
    }

    // =========================================================================
    // INTERACTIVE HELP (?) HOVER TOOLTIPS & CLICK-TO-DOCS DRAWER
    // =========================================================================
    function initHelpTooltips() {
      const tooltip = document.getElementById('global-tooltip');
      if (!tooltip) return;

      document.body.addEventListener('mouseover', (e) => {
        const target = e.target.closest('[data-tip]');
        if (!target) return;
        const tip = (uiLang === 'en' && target.getAttribute('data-tip-en'))
          ? target.getAttribute('data-tip-en')
          : target.getAttribute('data-tip');
        if (!tip) return;
        const hint = (I18N[uiLang] || I18N.it).tooltipHint;
        tooltip.innerHTML = `${tip}<span class="tt-hint">${hint}</span>`;
        tooltip.style.display = 'block';
        positionTooltip(e, tooltip);
      });

      document.body.addEventListener('mousemove', (e) => {
        if (tooltip.style.display === 'block') {
          positionTooltip(e, tooltip);
        }
      });

      document.body.addEventListener('mouseout', (e) => {
        const target = e.target.closest('[data-tip]');
        if (target) {
          tooltip.style.display = 'none';
        }
      });

      document.body.addEventListener('click', (e) => {
        if (e.target.closest('.help-btn')) {
          tooltip.style.display = 'none';
        }
      });
    }

    function positionTooltip(e, tooltip) {
      const pad = 12;
      let x = e.clientX + pad;
      let y = e.clientY + pad;
      if (x + 320 > window.innerWidth) {
        x = Math.max(10, window.innerWidth - 330);
      }
      if (y + 120 > window.innerHeight) {
        y = Math.max(10, e.clientY - 90);
      }
      tooltip.style.left = `${x}px`;
      tooltip.style.top = `${y}px`;
    }

    function openHelpSection(sectionId, event) {
      if (event) event.stopPropagation();
      const tooltip = document.getElementById('global-tooltip');
      if (tooltip) tooltip.style.display = 'none';

      const backdrop = document.getElementById('help-drawer-backdrop');
      if (backdrop) backdrop.style.display = 'flex';

      document.querySelectorAll('.doc-section').forEach(sec => sec.classList.remove('highlight'));
      if (sectionId) {
        const target = document.getElementById(sectionId);
        if (target) {
          target.classList.add('highlight');
          setTimeout(() => {
            target.scrollIntoView({ behavior: 'smooth', block: 'center' });
          }, 60);
        }
      }
    }

    function closeHelpDrawer(event) {
      if (event) event.stopPropagation();
      const backdrop = document.getElementById('help-drawer-backdrop');
      if (backdrop) backdrop.style.display = 'none';
    }

    // =========================================================================
    // SCOPED CONTEXT ATTACHMENTS (FILES, FOLDERS, SKILLS, PLUGINS)
    // =========================================================================
    async function loadScopedContext() {
      try {
        const r = await fetch('/api/context');
        const data = await r.json();
        cachedAttachments = data.attachments || [];
        renderContextChips();
      } catch (err) {
        console.error("Errore caricamento contesto:", err);
      }
    }

    function renderContextChips() {
      const chipsContainer = document.getElementById('composer-context-chips');
      const studioList = document.getElementById('studio-context-list');

      const iconMap = {
        file: '📄',
        folder: '📁',
        skill: '⚡',
        plugin: '🔌'
      };

      if (!cachedAttachments.length) {
        if (chipsContainer) {
          chipsContainer.innerHTML = `
            <span style="font-size:0.74rem; color:var(--muted); font-family:var(--mono);">
              📎 Contesto Attivo: <i style="color:#64748b;">Nessun file/cartella pre-caricata (contesto pulito)</i>
            </span>
          `;
        }
        if (studioList) {
          studioList.innerHTML = `<div style="font-size:0.76rem; color:var(--muted); font-style:italic;">Nessun elemento allegato. Usa i pulsanti sopra per aggiungere file, cartelle, skill o plugin.</div>`;
        }
        return;
      }

      if (chipsContainer) {
        chipsContainer.innerHTML = cachedAttachments.map(att => {
          const icon = iconMap[att.item_type] || '📎';
          const name = att.item_ref.split('/').pop() || att.item_ref;
          const tierBadge = att.depth_tier ? ` · ${att.depth_tier.toUpperCase()}` : '';
          return `
            <span class="ctx-chip" title="${att.item_ref} (~${att.tokens_estimate || 0} tok)">
              <span>${icon} ${name}${tierBadge}</span>
              <span class="chip-rm" onclick="detachContextItem('${att.id}', event)" title="Rimuovi dal contesto">✕</span>
            </span>
          `;
        }).join('');
      }

      if (studioList) {
        studioList.innerHTML = cachedAttachments.map(att => {
          const icon = iconMap[att.item_type] || '📎';
          return `
            <div style="background:rgba(15,23,42,0.85); border:1px solid var(--border); border-radius:8px; padding:6px 10px; margin-bottom:6px; font-size:0.75rem; display:flex; justify-content:space-between; align-items:center;">
              <div>
                <div><b>${icon} ${att.item_type.toUpperCase()}:</b> <code style="color:var(--accent);">${att.item_ref}</code></div>
                <div style="font-size:0.69rem; color:var(--muted); font-family:var(--mono);">Tier: ${att.depth_tier.toUpperCase()} · ~${att.tokens_estimate || 0} tokens · Scope: ${att.scope_id}</div>
              </div>
              <div style="display:flex; gap:5px;">
                <button class="btn btn-ghost" style="padding:2px 7px; font-size:0.67rem;" onclick="inspectAttachment3Plus1('${att.id}')" title="Ispeziona sintesi 3+1">🔍 Sintesi</button>
                <button class="btn btn-danger" style="padding:2px 7px; font-size:0.67rem;" onclick="detachContextItem('${att.id}', event)" title="Rimuovi">✕</button>
              </div>
            </div>
          `;
        }).join('');
      }
    }

    async function attachContextItemApi(itemType, itemRef, depthTier = 'medium', label = null, inlineContent = null) {
      if (!itemRef) return;
      try {
        const r = await fetch('/api/context/attach', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            scope_id: 'chat',
            item_type: itemType,
            item_ref: itemRef,
            depth_tier: depthTier,
            label: label,
            inline_content: inlineContent
          })
        });
        const d = await r.json();
        if (d.error) {
          alert(`Impossibile allegare: ${d.error}`);
          return;
        }
        await loadScopedContext();
        await loadMcpKnowledgeGraph();
        appendStreamCard(
          'system',
          `CONTEXT ATTACHED → ${itemType.toUpperCase()}`,
          `~${d.tokens_estimate || 0} tok`,
          `📎 Allegato: ${d.item_ref}`,
          `Tipo: ${d.item_type} | Livello 3+1: ${d.depth_tier.toUpperCase()} | Hash: ${d.merkle_hash || 'inline'}`
        );
      } catch (err) {
        alert("Errore durante l'allegato: " + err.message);
      }
    }

    async function detachContextItem(attachmentId, event) {
      if (event) event.stopPropagation();
      try {
        const r = await fetch('/api/context/detach', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ attachment_id: attachmentId })
        });
        const d = await r.json();
        await loadScopedContext();
        await loadMcpKnowledgeGraph();
        appendStreamCard(
          'system',
          'CONTEXT DETACHED',
          'OK',
          `Rimosso allegato ${attachmentId}`,
          ''
        );
      } catch (err) {
        console.error("Errore rimozione allegato:", err);
      }
    }

    function quickAttachPrompt(type) {
      let promptMsg = "Inserisci il percorso assoluto o relativo del File da allegare:";
      let defaultVal = "src/cortical/server.py";
      if (type === 'folder') {
        promptMsg = "Inserisci il percorso della Cartella da allegare:";
        defaultVal = "src/cortical";
      } else if (type === 'skill') {
        promptMsg = "Inserisci il nome della Skill da attivare:";
        defaultVal = "ai-reviewer-mandate-and-complexity";
      } else if (type === 'plugin') {
        promptMsg = "Inserisci il nome del Plugin/MCP da attivare:";
        defaultVal = "mcp:cortical-wiki";
      }

      const val = prompt(promptMsg, defaultVal);
      if (val && val.trim()) {
        const tier = document.getElementById('agent-depth')?.value || 'medium';
        attachContextItemApi(type, val.trim(), tier);
      }
    }

    function attachFromStudio() {
      const typeEl = document.getElementById('ctx-item-type');
      const refEl = document.getElementById('ctx-item-ref');
      const tierEl = document.getElementById('ctx-item-tier');
      if (!refEl || !refEl.value.trim()) {
        alert("Inserisci un percorso o nome valido nel campo.");
        return;
      }
      const itemType = typeEl.value;
      const itemRef = refEl.value.trim();
      const depthTier = tierEl.value;
      attachContextItemApi(itemType, itemRef, depthTier);
      refEl.value = '';
    }

    async function handleBrowserFileSelected(event) {
      const input = event.target;
      if (!input.files || !input.files[0]) return;
      const file = input.files[0];
      const tier = document.getElementById('agent-depth')?.value || 'medium';
      try {
        const inlineContent = await file.text();
        await attachContextItemApi('file', file.name, tier, file.name, inlineContent);
      } catch (err) {
        const fullPath = prompt(
          `File selezionato: "${file.name}".\\nInserisci il percorso relativo o assoluto del file sul tuo sistema:`,
          file.name
        );
        if (fullPath && fullPath.trim()) {
          await attachContextItemApi('file', fullPath.trim(), tier);
        }
      } finally {
        input.value = '';
      }
    }

    function inspectAttachment3Plus1(attachmentId) {
      const att = cachedAttachments.find(a => a.id === attachmentId);
      if (!att) return;
      const view = document.getElementById('wiki-node-view');
      if (view) {
        view.textContent = JSON.stringify(att, null, 2);
      }
    }

    // =========================================================================
    // NAVIGATION & VOICE UTILS
    // =========================================================================
    function switchMainStage(stage) {
      ['stream', 'graph', 'brain'].forEach(s => {
        const view = document.getElementById(`stage-${s}`);
        const tab = document.getElementById(`main-tab-${s}`);
        if (view) view.style.display = (s === stage) ? 'flex' : 'none';
        if (tab) tab.classList.toggle('active', s === stage);
      });
      if (stage === 'graph') {
        loadMcpKnowledgeGraph();
      } else if (stage === 'brain') {
        loadSkillsHub();
        loadScopedContext();
        loadSmartMemory();
        navigateWiki(currentWikiPath);
      }
    }

    // =========================================================================
    // WEB AUDIO GAINNODE DUCKING, HARDWARE AEC3 & SPECTRAL VOICE PRIORITY
    // =========================================================================
    let assistantAudioCtx = null;
    let assistantGainNode = null;
    let assistantAnalyser = null;
    let assistantAudioEl = null;
    let assistantSourceNode = null;
    let micMediaStream = null;
    let micAnalyser = null;
    let acousticMonitorTimer = null;
    let duckRestoreTimer = null;
    let acousticUserPriorityDetected = false;
    let assistantDucked = false;
    let assistantBaselineCentroidHz = 0;
    let lastMicRms = 0;
    let lastAssistantRms = 0;

    function updateDuckBadge(ducked) {
      const badge = document.getElementById('acoustic-duck-badge');
      if (!badge) return;
      const t = I18N[uiLang] || I18N.it;
      if (ducked) {
        badge.textContent = t.duckLow;
        badge.style.color = '#fbbf24';
        badge.style.borderColor = 'rgba(251,191,36,0.55)';
      } else {
        badge.textContent = t.duckNormal;
        badge.style.color = 'var(--muted)';
        badge.style.borderColor = 'var(--border)';
      }
    }

    function ensureAssistantAudioPipeline() {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return false;
      if (!assistantAudioCtx) {
        assistantAudioCtx = new AC();
        assistantGainNode = assistantAudioCtx.createGain();
        assistantGainNode.gain.value = 1.0;
        assistantAnalyser = assistantAudioCtx.createAnalyser();
        assistantAnalyser.fftSize = 1024;
        assistantAudioEl = new Audio();
        assistantAudioEl.crossOrigin = 'anonymous';
        assistantSourceNode = assistantAudioCtx.createMediaElementSource(assistantAudioEl);
        assistantSourceNode.connect(assistantAnalyser);
        assistantAnalyser.connect(assistantGainNode);
        assistantGainNode.connect(assistantAudioCtx.destination);
        assistantAudioEl.onended = () => {
          localTtsShieldUntilMs = 0;
          restoreAssistantAudio(1.0);
        };
      }
      if (assistantAudioCtx.state === 'suspended') {
        assistantAudioCtx.resume().catch(() => {});
      }
      return true;
    }

    function isAssistantAudioPlaying() {
      return Boolean(assistantAudioEl && !assistantAudioEl.paused && !assistantAudioEl.ended);
    }

    function duckAssistantAudio(level = 0.14) {
      if (!assistantGainNode || !assistantAudioCtx) return;
      const now = assistantAudioCtx.currentTime;
      assistantGainNode.gain.cancelScheduledValues(now);
      assistantGainNode.gain.setTargetAtTime(level, now, 0.035);
      assistantDucked = true;
      updateDuckBadge(true);
    }

    function restoreAssistantAudio(level = 1.0) {
      if (!assistantGainNode || !assistantAudioCtx) return;
      const now = assistantAudioCtx.currentTime;
      assistantGainNode.gain.cancelScheduledValues(now);
      assistantGainNode.gain.setTargetAtTime(level, now, 0.14);
      assistantDucked = false;
      updateDuckBadge(false);
    }

    function stopAssistantAudio() {
      if (duckRestoreTimer) {
        clearTimeout(duckRestoreTimer);
        duckRestoreTimer = null;
      }
      if (assistantAudioEl) {
        try {
          assistantAudioEl.pause();
          assistantAudioEl.currentTime = 0;
        } catch (_) {}
      }
      restoreAssistantAudio(1.0);
    }

    async function playAssistantAudioUrl(url) {
      if (!url || !ensureAssistantAudioPipeline()) return;
      stopAssistantAudio();
      assistantAudioEl.src = url;
      assistantBaselineCentroidHz = 0;
      restoreAssistantAudio(1.0);
      try {
        await assistantAudioEl.play();
      } catch (err) {
        console.warn('Web Audio play warning:', err);
      }
    }

    function getAnalyserRmsAndCentroid(analyser, sampleRate) {
      if (!analyser) return { rms: 0, centroidHz: 0 };
      const timeData = new Float32Array(analyser.fftSize);
      analyser.getFloatTimeDomainData(timeData);
      let sumSq = 0;
      for (let i = 0; i < timeData.length; i++) sumSq += timeData[i] * timeData[i];
      const rms = Math.sqrt(sumSq / timeData.length);

      const freqData = new Uint8Array(analyser.frequencyBinCount);
      analyser.getByteFrequencyData(freqData);
      const binHz = (sampleRate || 48000) / (analyser.fftSize || 1024);
      let weighted = 0;
      let total = 0;
      for (let i = 1; i < freqData.length; i++) {
        const mag = freqData[i];
        weighted += mag * (i * binHz);
        total += mag;
      }
      return { rms, centroidHz: total > 0 ? weighted / total : 0 };
    }

    async function startAcousticMonitor() {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return;
      ensureAssistantAudioPipeline();
      try {
        if (!micMediaStream) {
          // Enabling hardware WebRTC AEC3 on the same Chrome AudioContext reference eliminates assistant tone leakage
          micMediaStream = await navigator.mediaDevices.getUserMedia({
            audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 }
          });
          const micSource = assistantAudioCtx.createMediaStreamSource(micMediaStream);
          micAnalyser = assistantAudioCtx.createAnalyser();
          micAnalyser.fftSize = 1024;
          micSource.connect(micAnalyser);
        }
        if (acousticMonitorTimer) clearInterval(acousticMonitorTimer);
        acousticMonitorTimer = setInterval(() => {
          if (!alwaysOnActive || !micAnalyser || !assistantAudioCtx) return;
          const sr = assistantAudioCtx.sampleRate || 48000;
          const micStats = getAnalyserRmsAndCentroid(micAnalyser, sr);
          const asstStats = getAnalyserRmsAndCentroid(assistantAnalyser, sr);
          lastMicRms = Number(micStats.rms.toFixed(4));
          lastAssistantRms = Number(asstStats.rms.toFixed(4));

          if (isAssistantAudioPlaying() && asstStats.rms > 0.015 && asstStats.centroidHz > 80) {
            assistantBaselineCentroidHz = assistantBaselineCentroidHz
              ? (assistantBaselineCentroidHz * 0.85 + asstStats.centroidHz * 0.15)
              : asstStats.centroidHz;
          }

          if (isAssistantAudioPlaying()) {
            const pitchDiffRatio = (assistantBaselineCentroidHz > 80 && micStats.centroidHz > 80)
              ? Math.abs(micStats.centroidHz - assistantBaselineCentroidHz) / assistantBaselineCentroidHz
              : 0;
            const userSpeakingNow = micStats.rms > 0.024 && (micStats.rms > asstStats.rms * 0.9 || pitchDiffRatio > 0.14);
            if (userSpeakingNow) {
              acousticUserPriorityDetected = true;
              if (!assistantDucked) duckAssistantAudio(0.14);
              if (duckRestoreTimer) clearTimeout(duckRestoreTimer);
              duckRestoreTimer = setTimeout(() => {
                if (!micInterimBuffer && !micFinalBuffer && isAssistantAudioPlaying()) {
                  restoreAssistantAudio(1.0);
                  acousticUserPriorityDetected = false;
                }
              }, 1600);
            }
          }
        }, 70);
      } catch (err) {
        console.warn('Hardware AEC getUserMedia unavailable:', err);
      }
    }

    function stopAcousticMonitor() {
      if (acousticMonitorTimer) {
        clearInterval(acousticMonitorTimer);
        acousticMonitorTimer = null;
      }
      if (micMediaStream) {
        micMediaStream.getTracks().forEach(t => t.stop());
        micMediaStream = null;
      }
      micAnalyser = null;
      acousticUserPriorityDetected = false;
    }

    function hasWakeOrBargeInWord(s) {
      return /\\b(cortical|peppe|ferma|fermati|stop|basta|silenzio|zitto|annulla|aspetta|quiet|cancel|nevermind|enough|wait)\\b/i.test(s || '');
    }

    function detectLangClient(s) {
      if (!s) return uiLang || 'it';
      if (/[àèéìòù]/i.test(s)) return 'it';
      const enHits = (s.match(/\\b(the|what|when|where|how|weather|tomorrow|open|search|browser|wikipedia|read|summarize|page|hey|create|task)\\b/gi) || []).length;
      const itHits = (s.match(/\\b(che|cosa|come|meteo|domani|apri|cerca|browser|leggi|riassumi|pagina|ehi|crea|task|ora)\\b/gi) || []).length;
      if (enHits > itHits) return 'en';
      if (itHits > enHits) return 'it';
      return uiLang || 'it';
    }

    function isTtsShieldActive() {
      return isAssistantAudioPlaying() || Date.now() < localTtsShieldUntilMs;
    }

    function normalizeTokens(s) {
      return (s || '')
        .toLowerCase()
        .replace(/(\\d+)[.,](\\d+)\\s*°c/gi, '$1 virgola $2 gradi')
        .replace(/(\\d+)\\s*°c/gi, '$1 gradi')
        .replace(/\\bmin\\s+(\\d+)/gi, 'minima $1')
        .replace(/\\bmax\\s+(\\d+)/gi, 'massima $1')
        .replace(/(\\d+)\\s*%/g, '$1 per cento')
        .replace(/[^\\w\\sàèéìòù]/g, ' ')
        .split(/\\s+/)
        .filter(w => w.length > 1);
    }

    function isSelfEchoClient(candidate) {
      if (!candidate) return false;
      if (hasWakeOrBargeInWord(candidate)) return false;
      const candWords = normalizeTokens(candidate);
      const spokenWords = new Set(normalizeTokens(lastSpokenResponseText || ''));
      const overlap = (candWords.length && spokenWords.size)
        ? (candWords.filter(w => spokenWords.has(w)).length / candWords.length)
        : 0;
      // During short TTS acoustic shield, ignore short 1-3 word bleeds or phrases overlapping with TTS,
      // but NEVER drop clear multi-word human commands (>=4 distinct non-overlapping words).
      if (isTtsShieldActive()) {
        if (candWords.length < 4 || overlap >= 0.35) return true;
        return false;
      }
      if (!lastSpokenResponseText) return false;
      const elapsedSec = (Date.now() - lastSpokenAtMs) / 1000.0;
      if (elapsedSec > 25.0) return false;
      if (!candWords.length || !spokenWords.size) return false;
      const candJoined = candWords.join(' ');
      const spokenJoined = normalizeTokens(lastSpokenResponseText).join(' ');
      if (candJoined.length >= 5 && spokenJoined.includes(candJoined)) return true;
      return overlap >= 0.45;
    }

    async function loadHealth() {
      try {
        const r = await fetch('/health');
        const d = await r.json();
        document.getElementById('hw-banner').textContent =
          `${d.os_name} (${d.arch}) · ${d.tier} · ${d.tts_engine} · LLM: ${d.active_base_url}`;
      } catch (err) {
        console.error("Errore loadHealth:", err);
      }
    }

    function appendStreamCard(type, metaLeft, metaRight, title, detail) {
      const stream = document.getElementById('agent-stream');
      if (!stream) return;
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

      if (fromMic && isSelfEchoClient(text) && !acousticUserPriorityDetected) {
        document.getElementById('live-transcript').textContent = `🔇 [Eco altoparlante ignorato / Speaker bleed ignored]`;
        return;
      }

      // Spoken language switching shortcuts
      if (/\\b(parla inglese|in inglese|switch to english|speak english)\\b/i.test(text)) {
        setUiLanguage('en');
        const vSel = document.getElementById('tts-voice');
        if (vSel && !vSel.value.includes('Jenny') && !vSel.value.includes('Guy') && vSel.value !== 'auto') {
          vSel.value = 'JennyNeural';
        }
      } else if (/\\b(parla italiano|in italiano|switch to italian|speak italian)\\b/i.test(text)) {
        setUiLanguage('it');
        const vSel = document.getElementById('tts-voice');
        if (vSel && vSel.value !== 'auto') vSel.value = 'IsabellaNeural';
      }

      if (activeAbortController) {
        activeAbortController.abort();
      }
      const wordCount = normalizeTokens(text).length;
      const wasSpeaking = isAssistantAudioPlaying();
      const hadUserPriority = acousticUserPriorityDetected || hasWakeOrBargeInWord(text) || (wordCount >= 3 && !isSelfEchoClient(text));
      if (!fromMic || hadUserPriority) {
        localTtsShieldUntilMs = 0;
        stopAssistantAudio();
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
      const utteranceLang = detectLangClient(text);

      if (mode === 'agent') {
        switchMainStage('stream');
        await spawnAgentSession(text, depth, speak);
        return;
      }

      activeAbortController = new AbortController();
      try {
        const r = await fetch('/api/voice', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            utterance: text,
            speak,
            client_audio: true,
            client_tts_speaking: wasSpeaking,
            voice,
            lang: utteranceLang,
            wiki_depth: depth,
            from_mic: fromMic,
            discourse_hints: {
              acoustic_user_priority: hadUserPriority,
              mic_rms: lastMicRms,
              assistant_rms: lastAssistantRms
            }
          }),
          signal: activeAbortController.signal
        });
        const d = await r.json();
        acousticUserPriorityDetected = false;

        if (d.route === 'ignored_echo') {
          document.getElementById('live-transcript').textContent = `🔇 [Eco ignorato / Self-echo ignored]`;
          return;
        }

        if (d.spoken_response) {
          lastSpokenResponseText = d.spoken_response;
          lastSpokenAtMs = Date.now();
          if (d.audio_url && speak && d.route !== 'stop') {
            await playAssistantAudioUrl(d.audio_url);
          } else if (speak && d.route !== 'stop') {
            const estMs = Math.min(7500, Math.max(2500, d.spoken_response.length * 55 + 1100));
            localTtsShieldUntilMs = Date.now() + estMs;
          } else {
            localTtsShieldUntilMs = Date.now() + 900;
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
      const goal = prompt("Inserisci l'obiettivo per il nuovo Task esplicito pi:", "Analizza la struttura del repository e riassumi i concetti chiave");
      if (goal) {
        switchMainStage('stream');
        spawnAgentSession(goal, document.getElementById('agent-depth').value, true);
      }
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
      try {
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
                3+1: ${s.wiki_depth.toUpperCase()} · Steps: ${s.steps.length}
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
      } catch (err) {
        console.error("Errore refreshAgents:", err);
      }
    }

    function selectSession(sid) {
      selectedSessionId = sid;
      switchMainStage('stream');
      refreshAgents();
    }

    async function triggerStopBargeIn() {
      if (activeAbortController) activeAbortController.abort();
      stopAssistantAudio();
      if (window.speechSynthesis) window.speechSynthesis.cancel();
      await fetch('/api/voice', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          utterance: uiLang === 'en' ? 'Hey Cortical stop' : 'Ehi Cortical basta',
          speak: true,
          client_audio: true,
          lang: uiLang,
          voice: document.getElementById('tts-voice').value
        })
      });
      refreshAgents();
    }

    async function openNativePiTerminal() {
      const r = await fetch('/api/agents/open-terminal', {method: 'POST', body: '{}'});
      const d = await r.json();
      appendStreamCard('subagent', 'TERMINAL LAUNCHER', d.platform || 'CLI', 'Apertura sessione interattiva `pi`', JSON.stringify(d, null, 2));
    }

    let micFinalBuffer = '';
    let micInterimBuffer = '';
    let micCommitTimer = null;
    let micRestartTimer = null;
    let micIsRecognizing = false;

    function flushMicTranscriptBuffer() {
      if (micCommitTimer) {
        clearTimeout(micCommitTimer);
        micCommitTimer = null;
      }
      const combined = `${micFinalBuffer} ${micInterimBuffer}`.replace(/\\s+/g, ' ').trim();
      micFinalBuffer = '';
      micInterimBuffer = '';
      const promptInput = document.getElementById('prompt-input');
      if (promptInput) {
        promptInput.placeholder = (I18N[uiLang] || I18N.it).promptPlaceholder;
      }
      if (!combined) return;
      if (isSelfEchoClient(combined) && !acousticUserPriorityDetected) {
        const lt = document.getElementById('live-transcript');
        if (lt) lt.textContent = '🔇 [Eco altoparlante ignorato / Bleed ignored]';
        return;
      }
      const lt = document.getElementById('live-transcript');
      if (lt) {
        lt.textContent = `🗣️ "${combined}"`;
        lt.title = combined;
      }
      submitComposer(combined);
    }

    function scheduleMicCommit(delayMs) {
      if (micCommitTimer) clearTimeout(micCommitTimer);
      micCommitTimer = setTimeout(flushMicTranscriptBuffer, delayMs);
    }

    function startMicRecognizer() {
      if (!alwaysOnActive || !recognition || micIsRecognizing) return;
      try {
        recognition.start();
      } catch (_) {}
    }

    function toggleAlwaysOnMic() {
      const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!SR) {
        alert("Il browser corrente non espone Web Speech API (usa Chrome o Edge per il microfono continuo).");
        return;
      }
      if (alwaysOnActive) {
        alwaysOnActive = false;
        stopAcousticMonitor();
        if (micCommitTimer) clearTimeout(micCommitTimer);
        if (micRestartTimer) clearTimeout(micRestartTimer);
        micFinalBuffer = '';
        micInterimBuffer = '';
        if (recognition) {
          try { recognition.stop(); } catch (_) {}
        }
        micIsRecognizing = false;
        document.getElementById('mic-dot').classList.remove('listening');
        document.getElementById('btn-always-on').textContent = (I18N[uiLang] || I18N.it).micOff;
        document.getElementById('live-transcript').textContent = (uiLang === 'en') ? 'Microphone paused.' : 'Microfono in pausa.';
        return;
      }

      alwaysOnActive = true;
      micFinalBuffer = '';
      micInterimBuffer = '';
      startAcousticMonitor();
      document.getElementById('mic-dot').classList.add('listening');
      document.getElementById('btn-always-on').textContent = (I18N[uiLang] || I18N.it).micOn;
      document.getElementById('live-transcript').textContent = (uiLang === 'en')
        ? 'Listening (AEC + Ducking active, speak naturally)...'
        : 'In ascolto (AEC + Ducking attivi, parla pure)...';

      recognition = new SR();
      recognition.lang = (uiLang === 'en') ? 'en-US' : 'it-IT';
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.maxAlternatives = 1;

      recognition.onstart = () => {
        micIsRecognizing = true;
        if (!micFinalBuffer && !micInterimBuffer) {
          document.getElementById('live-transcript').textContent = '🎙️ In ascolto...';
        }
      };

      recognition.onspeechstart = () => {
        document.getElementById('mic-dot').classList.add('listening');
        if (!micFinalBuffer && !micInterimBuffer) {
          document.getElementById('live-transcript').textContent = '🎙️ Voce rilevata...';
        }
      };

      recognition.onresult = (event) => {
        let currentInterim = '';
        for (let i = event.resultIndex; i < event.results.length; ++i) {
          const chunk = (event.results[i][0]?.transcript || '').trim();
          if (!chunk) continue;
          if (isSelfEchoClient(chunk) && !micFinalBuffer) {
            const lt = document.getElementById('live-transcript');
            if (lt) lt.textContent = '🔇 [Scudo Anti-Eco: ignoro la mia voce]';
            continue;
          }
          if (event.results[i].isFinal) {
            micFinalBuffer = `${micFinalBuffer} ${chunk}`.replace(/\\s+/g, ' ').trim();
            micInterimBuffer = '';
            // If user explicitly issued a stop/barge-in word, flush immediately without waiting!
            if (hasWakeOrBargeInWord(micFinalBuffer) && micFinalBuffer.split(/\\s+/).length <= 4) {
              flushMicTranscriptBuffer();
              return;
            }
            scheduleMicCommit(1250);
          } else {
            currentInterim += chunk + ' ';
            // Smooth Alexa-style ducking as soon as non-echo interim user speech starts!
            if (isAssistantAudioPlaying() && !isSelfEchoClient(currentInterim)) {
              acousticUserPriorityDetected = true;
              duckAssistantAudio(0.14);
            }
            if (hasWakeOrBargeInWord(currentInterim)) {
              localTtsShieldUntilMs = 0;
              stopAssistantAudio();
              fetch('/api/voice/duck', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({force_stop: true})
              }).catch(() => {});
            }
          }
        }
        if (currentInterim.trim()) {
          micInterimBuffer = currentInterim.trim();
          // Fallback silence commit if Chromium delays emitting isFinal on long sentences
          scheduleMicCommit(2200);
        }
        const livePreview = `${micFinalBuffer} ${micInterimBuffer}`.replace(/\\s+/g, ' ').trim();
        if (livePreview) {
          const lt = document.getElementById('live-transcript');
          if (lt) {
            lt.textContent = `🎙️ ${livePreview}`;
            lt.title = livePreview;
          }
          const pi = document.getElementById('prompt-input');
          if (pi && !pi.value) {
            pi.placeholder = `🎙️ Trascrizione live: "${livePreview}"`;
          }
        }
      };

      recognition.onerror = (ev) => {
        const errCode = ev?.error || 'unknown';
        const lt = document.getElementById('live-transcript');
        if (errCode === 'not-allowed' || errCode === 'service-not-allowed') {
          alwaysOnActive = false;
          micIsRecognizing = false;
          document.getElementById('mic-dot').classList.remove('listening');
          document.getElementById('btn-always-on').textContent = '🎤 Mic: Negato';
          if (lt) lt.textContent = '🚫 Permesso microfono negato dal browser.';
          appendStreamCard('permission', 'MICROFONO BLOCCATO', errCode, 'Consenti accesso al microfono nel browser (lucchetto URL).', '');
          return;
        }
        if (errCode === 'audio-capture') {
          if (lt) lt.textContent = '⚠️ Nessun microfono audio rilevato.';
          return;
        }
        if (errCode === 'network' && lt) {
          lt.textContent = '⚠️ Rete Web Speech momentaneamente instabile, riconnessione...';
        }
      };

      recognition.onend = () => {
        micIsRecognizing = false;
        // Flush any accumulated long-phrase transcript before restarting
        if (micFinalBuffer || micInterimBuffer) {
          flushMicTranscriptBuffer();
        }
        if (alwaysOnActive) {
          if (micRestartTimer) clearTimeout(micRestartTimer);
          micRestartTimer = setTimeout(startMicRecognizer, 220);
        }
      };

      startMicRecognizer();
    }

    // =========================================================================
    // INTERACTIVE CONCEPT KNOWLEDGE GRAPH (MCP `wiki_get_knowledge_graph`)
    // =========================================================================
    async function loadMcpKnowledgeGraph() {
      try {
        const mcpReq = {
          jsonrpc: '2.0',
          id: Date.now(),
          method: 'tools/call',
          params: {
            name: 'wiki_get_knowledge_graph',
            arguments: { max_nodes: 60 }
          }
        };
        const r = await fetch('/api/mcp', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(mcpReq)
        });
        const mcpRes = await r.json();
        const rawText = mcpRes?.result?.content?.[0]?.text || '{}';
        cachedGraphData = JSON.parse(rawText);
        const stats = cachedGraphData.stats || {};
        const label = `${stats.concept_count || stats.node_count || 0} concetti · ${stats.edge_count || 0} relazioni`;
        const sidebarStats = document.getElementById('sidebar-graph-stats');
        if (sidebarStats) sidebarStats.textContent = label;
        const navCount = document.getElementById('nav-graph-count');
        if (navCount) navCount.textContent = `(${stats.node_count || 0})`;
        computeConceptLayout(cachedGraphData);
        renderKnowledgeGraphSvg();
      } catch (err) {
        console.error("Errore loadMcpKnowledgeGraph:", err);
      }
    }

    function setGraphFilter(filter, el) {
      currentGraphFilter = filter;
      document.querySelectorAll('#graph-filter-pills .pill').forEach(p => p.classList.remove('active'));
      if (el) el.classList.add('active');
      renderKnowledgeGraphSvg();
    }

    function zoomGraph(factor) {
      graphZoom = Math.max(0.45, Math.min(2.6, graphZoom * factor));
      renderKnowledgeGraphSvg();
    }

    function resetGraphView() {
      graphZoom = 1.0;
      graphPanX = 0;
      graphPanY = 0;
      computeConceptLayout(cachedGraphData, true);
      renderKnowledgeGraphSvg();
    }

    function computeConceptLayout(graph, forceReset = false) {
      const nodes = graph.nodes || [];
      const W = 920, H = 560, cx = W / 2, cy = H / 2;
      const primaryConcepts = nodes.filter(n => n.kind === 'concept');
      const otherNodes = nodes.filter(n => n.kind !== 'hub' && n.kind !== 'concept');

      nodes.forEach((n) => {
        if (!forceReset && nodePositions[n.id]) return;
        if (n.kind === 'hub') {
          nodePositions[n.id] = { x: cx, y: cy };
          return;
        }
        const pIdx = primaryConcepts.findIndex(c => c.id === n.id);
        if (pIdx !== -1) {
          const ring = (pIdx % 2 === 0) ? 155 : 210;
          const angle = (2 * Math.PI * pIdx) / Math.max(1, primaryConcepts.length) - Math.PI / 2;
          nodePositions[n.id] = {
            x: Math.round(cx + ring * Math.cos(angle)),
            y: Math.round(cy + ring * Math.sin(angle))
          };
          return;
        }
        const oIdx = Math.max(0, otherNodes.findIndex(o => o.id === n.id));
        const ring = 250;
        const angle = (2 * Math.PI * oIdx) / Math.max(1, otherNodes.length) + 0.35;
        nodePositions[n.id] = {
          x: Math.round(cx + ring * Math.cos(angle)),
          y: Math.round(cy + ring * Math.sin(angle))
        };
      });
    }

    function nodeMatchesFilter(n, q) {
      if (q) {
        const hay = `${n.label || ''} ${n.summary || ''} ${n.category || ''}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      if (currentGraphFilter === 'all') return true;
      if (n.kind === 'hub') return true;
      if (currentGraphFilter === 'concept') return n.kind === 'concept';
      if (currentGraphFilter === 'memoria') return n.category === 'memoria';
      if (currentGraphFilter === 'agenti') return n.category === 'agenti';
      if (currentGraphFilter === 'voce') return n.category === 'voce';
      if (currentGraphFilter === 'sicurezza') return n.category === 'sicurezza';
      if (currentGraphFilter === 'insight') return n.kind === 'insight';
      if (currentGraphFilter === 'skill') return n.kind === 'skill';
      if (currentGraphFilter === 'task') return (n.kind || '').startsWith('task_');
      return n.category === currentGraphFilter;
    }

    function renderKnowledgeGraphSvg() {
      const svg = document.getElementById('mcp-graph-svg');
      if (!svg) return;
      const q = (document.getElementById('graph-search-input')?.value || '').trim().toLowerCase();
      const allNodes = cachedGraphData.nodes || [];
      const allEdges = cachedGraphData.edges || [];
      const nodes = allNodes.filter(n => nodeMatchesFilter(n, q));
      const visibleIds = new Set(nodes.map(n => n.id));
      const edges = allEdges.filter(e => visibleIds.has(e.source) && visibleIds.has(e.target));

      if (!nodes.length) {
        svg.innerHTML = '<text x="460" y="280" fill="#94a3b8" text-anchor="middle" font-size="14">Nessun concetto corrispondente al filtro selezionato</text>';
        return;
      }

      const colorByKind = {
        hub: '#38bdf8',
        concept: '#c084fc',
        insight: '#34d399',
        skill: '#fbbf24',
        task_active: '#fbbf24',
        task_archived: '#818cf8'
      };
      const catColor = {
        memoria: '#38bdf8',
        architettura: '#c084fc',
        agenti: '#fbbf24',
        voce: '#34d399',
        sicurezza: '#f87171'
      };

      let html = `<g transform="translate(${graphPanX}, ${graphPanY}) scale(${graphZoom})">`;

      // Render semantic edges with relation labels
      edges.forEach(e => {
        const s = nodePositions[e.source];
        const t = nodePositions[e.target];
        if (!s || !t) return;
        const mx = (s.x + t.x) / 2;
        const my = (s.y + t.y) / 2;
        const stroke = e.kind === 'macro' ? '#fbbf24' : (e.kind === 'insight_link' ? '#34d399' : '#2b3f66');
        const dash = e.kind === 'macro' ? 'stroke-dasharray="5,4"' : '';
        html += `
          <line x1="${s.x}" y1="${s.y}" x2="${t.x}" y2="${t.y}" stroke="${stroke}" stroke-width="1.8" ${dash} opacity="0.82" />
          <text x="${mx}" y="${my - 4}" fill="#64748b" font-size="9.5" font-family="monospace" text-anchor="middle">${e.relation || ''}</text>
        `;
      });

      // Render interactive concept nodes (pill/circle badges)
      nodes.forEach(n => {
        const p = nodePositions[n.id];
        if (!p) return;
        const isCore = !!n.is_framework_core;
        const col = n.kind === 'concept' ? (catColor[n.category] || '#c084fc') : (colorByKind[n.kind] || '#38bdf8');
        const r = n.kind === 'hub' ? 18 : (n.kind === 'concept' ? 13 : 10);
        const safeId = n.id.replace(/'/g, "\\'");
        const label = n.label || n.key;
        const coreBorder = isCore ? 'stroke="#38bdf8" stroke-width="3"' : 'stroke="#070b14" stroke-width="2"';
        html += `
          <g style="cursor:pointer;" onmousedown="startDragNode(event, '${safeId}')" onclick="inspectConceptById('${safeId}')">
            <circle cx="${p.x}" cy="${p.y}" r="${r + 5}" fill="${col}" opacity="${isCore ? '0.28' : '0.14'}" />
            <circle cx="${p.x}" cy="${p.y}" r="${r}" fill="${col}" ${coreBorder} />
            ${isCore ? `<circle cx="${p.x}" cy="${p.y}" r="${r + 2.5}" fill="none" stroke="#fff" stroke-width="1" opacity="0.8" />` : ''}
            <rect x="${p.x - Math.min(115, label.length * 3.8 + 10)}" y="${p.y + r + 5}" width="${Math.min(230, label.length * 7.6 + 20)}" height="19" rx="5" fill="rgba(7,11,20,0.88)" stroke="${isCore ? 'rgba(56,189,248,0.5)' : 'rgba(192,132,252,0.3)'}" />
            <text x="${p.x}" y="${p.y + r + 18}" fill="#f1f5f9" font-size="11" font-weight="600" text-anchor="middle">${label}</text>
          </g>
        `;
      });

      html += `</g>`;
      svg.innerHTML = html;
    }

    function startDragNode(event, nodeId) {
      event.stopPropagation();
      draggedNodeId = nodeId;
    }

    // Setup pan & node drag on the central SVG canvas
    (function initGraphCanvasInteractions() {
      window.addEventListener('DOMContentLoaded', () => {
        const wrap = document.getElementById('graph-canvas-container');
        const svg = document.getElementById('mcp-graph-svg');
        if (!wrap || !svg) return;

        wrap.addEventListener('mousedown', (e) => {
          if (draggedNodeId) return;
          isPanningGraph = true;
          panStartX = e.clientX - graphPanX;
          panStartY = e.clientY - graphPanY;
        });

        window.addEventListener('mousemove', (e) => {
          if (draggedNodeId && nodePositions[draggedNodeId]) {
            const rect = svg.getBoundingClientRect();
            const svgX = ((e.clientX - rect.left) * (920 / rect.width) - graphPanX) / graphZoom;
            const svgY = ((e.clientY - rect.top) * (560 / rect.height) - graphPanY) / graphZoom;
            nodePositions[draggedNodeId] = { x: Math.round(svgX), y: Math.round(svgY) };
            renderKnowledgeGraphSvg();
          } else if (isPanningGraph) {
            graphPanX = e.clientX - panStartX;
            graphPanY = e.clientY - panStartY;
            renderKnowledgeGraphSvg();
          }
        });

        window.addEventListener('mouseup', () => {
          draggedNodeId = null;
          isPanningGraph = false;
        });
      });
    })();

    // =========================================================================
    // CONCEPT INSPECTOR, DYNAMIC CONFIG FORM & USER CONCEPT DELETION
    // =========================================================================
    function inspectConceptById(nodeId) {
      selectedConceptNode = (cachedGraphData.nodes || []).find(n => n.id === nodeId);
      if (!selectedConceptNode) return;
      const node = selectedConceptNode;

      const isCore = !!node.is_framework_core;
      const badgeEl = document.getElementById('cd-badge');
      badgeEl.textContent = isCore ? `🔒 PILASTRO FRAMEWORK (${(node.category || 'core').toUpperCase()})` : `✨ CONCETTO UTENTE (${(node.category || 'utente').toUpperCase()})`;
      badgeEl.style.background = isCore ? 'rgba(56,189,248,0.2)' : 'rgba(192,132,252,0.2)';
      badgeEl.style.borderColor = isCore ? 'var(--accent)' : 'var(--purple)';

      document.getElementById('cd-title').textContent = node.label || node.key;
      document.getElementById('cd-summary-l1').textContent = node.summary || 'Nessuna sintesi L1 disponibile.';
      document.getElementById('cd-summary-l2').textContent = node.summary_medium || node.summary || 'Nessun dettaglio L2 aggiuntivo.';

      // Dynamic Config Form
      const cfgForm = document.getElementById('cd-config-form');
      const cfg = node.config || {};
      const cfgKeys = Object.keys(cfg);

      if (cfgKeys.length > 0) {
        let formHtml = `<div style="margin-bottom:8px; font-weight:600; color:#e2e8f0;">Modifica parametri del concetto:</div>`;
        cfgKeys.forEach(k => {
          const val = cfg[k];
          const isNum = typeof val === 'number';
          formHtml += `
            <div class="cfg-row">
              <label>${k.replace(/_/g, ' ').toUpperCase()}:</label>
              <input id="cfg-input-${k}" type="${isNum ? 'number' : 'text'}" value="${val}" style="padding:4px 8px; font-size:0.77rem; width:100%;" />
            </div>
          `;
        });
        formHtml += `
          <button class="btn" style="width:100%; justify-content:center; margin-top:6px;" onclick="saveSelectedConceptConfig('${node.id}')">
            💾 Salva Configurazione Concetto
          </button>
        `;
        cfgForm.innerHTML = formHtml;
      } else {
        cfgForm.innerHTML = `
          <div style="color:var(--muted); font-size:0.75rem; margin-bottom:6px;">Questo concetto non ha parametri personalizzati definiti.</div>
          <button class="btn btn-ghost" style="font-size:0.72rem;" onclick="addCustomConfigField('${node.id}')">+ Aggiungi Parametro</button>
        `;
      }

      // Deletion Box
      const delBox = document.getElementById('cd-delete-box');
      if (isCore) {
        delBox.innerHTML = `
          <div style="font-size:0.72rem; color:var(--muted); background:rgba(255,255,255,0.03); border:1px solid var(--border); border-radius:7px; padding:6px 9px;">
            🔒 <b>Pilastro del Framework:</b> Questo concetto è fondamentale per l'architettura di Cortical e non può essere eliminato. Puoi tuttavia configurarne i parametri operativi qui sopra.
          </div>
        `;
      } else {
        delBox.innerHTML = `
          <button class="btn btn-danger" style="width:100%; justify-content:center;" onclick="deleteSelectedConcept('${node.id}')">
            🗑️ Elimina Concetto dalla Memoria
          </button>
        `;
      }

      // Connected Edges
      const connected = (cachedGraphData.edges || [])
        .filter(e => e.source === node.id || e.target === node.id)
        .map(e => {
          const otherId = e.source === node.id ? e.target : e.source;
          const otherNode = (cachedGraphData.nodes || []).find(n => n.id === otherId);
          return `• [${e.relation}] → ${otherNode ? otherNode.label : otherId}`;
        });
      document.getElementById('cd-connections').textContent = connected.length ? connected.join('\\n') : 'Nessuna connessione diretta.';
      document.getElementById('cd-sources').textContent = (node.sources || ['/']).join(', ');
    }

    async function saveSelectedConceptConfig(conceptId) {
      if (!selectedConceptNode) return;
      const cfg = selectedConceptNode.config || {};
      const updates = {};
      Object.keys(cfg).forEach(k => {
        const input = document.getElementById(`cfg-input-${k}`);
        if (input) {
          const origType = typeof cfg[k];
          if (origType === 'number') {
            updates[k] = parseFloat(input.value) || 0;
          } else {
            updates[k] = input.value;
          }
        }
      });

      try {
        const r = await fetch('/api/graph/concept/config', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ concept_id: conceptId, config: updates })
        });
        const d = await r.json();
        appendStreamCard(
          'system',
          'CONCEPT CONFIG UPDATED',
          conceptId,
          `Configurazione aggiornata per ${selectedConceptNode.label || conceptId}`,
          JSON.stringify(d, null, 2)
        );
        await loadMcpKnowledgeGraph();
        inspectConceptById(conceptId);
      } catch (err) {
        alert("Errore salvataggio configurazione: " + err.message);
      }
    }

    async function deleteSelectedConcept(nodeId) {
      if (!confirm(`Sei sicuro di voler eliminare definitivamente il concetto "${nodeId}" dal grafo della memoria?`)) return;
      try {
        const r = await fetch('/api/graph/concept/delete', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ node_id: nodeId })
        });
        const d = await r.json();
        if (d.error) {
          alert(`Eliminazione non consentita: ${d.error}`);
          return;
        }
        appendStreamCard(
          'permission',
          'CONCEPT DELETED FROM MEMORY',
          nodeId,
          `🗑️ Concetto "${nodeId}" eliminato con successo dal grafo della conoscenza.`,
          ''
        );
        selectedConceptNode = null;
        document.getElementById('cd-title').textContent = "Seleziona un concetto";
        document.getElementById('cd-config-form').innerHTML = "Clicca su un nodo del grafo per configurarne i parametri.";
        document.getElementById('cd-delete-box').innerHTML = "";
        await loadMcpKnowledgeGraph();
      } catch (err) {
        alert("Errore cancellazione concetto: " + err.message);
      }
    }

    function addCustomConfigField(conceptId) {
      const key = prompt("Nome del nuovo parametro (es: timeout_sec, model_override):");
      if (!key) return;
      const val = prompt(`Valore per ${key}:`, "default");
      if (val === null) return;
      if (!selectedConceptNode.config) selectedConceptNode.config = {};
      selectedConceptNode.config[key] = val;
      saveSelectedConceptConfig(conceptId);
    }

    // =========================================================================
    // SMART MEMORY, 3+1 WIKI & PERMISSION GATE
    // =========================================================================
    async function loadSmartMemory() {
      try {
        const r = await fetch('/api/memory/state');
        const d = await r.json();
        const memView = document.getElementById('memory-state-view');
        if (memView) memView.textContent = JSON.stringify(d, null, 2);
      } catch (err) {
        console.error("Errore loadSmartMemory:", err);
      }
    }

    async function navigateWiki(path = '/') {
      currentWikiPath = path;
      const depth = document.getElementById('wiki-depth').value;
      try {
        const r = await fetch(`/api/wiki/navigate?path=${encodeURIComponent(path)}&depth=${depth}`);
        const d = await r.json();
        const wikiView = document.getElementById('wiki-node-view');
        if (wikiView) wikiView.textContent = JSON.stringify(d, null, 2);

        const children = d.children || [];
        const tree = document.getElementById('wiki-tree');
        if (tree) {
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
      } catch (err) {
        console.error("Errore navigateWiki:", err);
      }
    }

    async function searchWiki() {
      const q = document.getElementById('wiki-search-input').value;
      const depth = document.getElementById('wiki-depth').value;
      const r = await fetch(`/api/wiki/search?q=${encodeURIComponent(q)}&depth=${depth}`);
      document.getElementById('wiki-node-view').textContent = JSON.stringify(await r.json(), null, 2);
    }

    async function loadSkillsHub() {
      try {
        const r = await fetch('/api/skills/state');
        const d = await r.json();
        const box = document.getElementById('skills-list-view');
        const skills = d.skills || [];
        if (box) {
          box.innerHTML = skills.map(s => `
            <div style="background:rgba(15,23,42,0.85); border:1px solid ${s.category === 'memory_tier' ? 'rgba(56,189,248,0.4)' : s.category === 'learned' ? 'rgba(52,211,153,0.4)' : 'var(--border)'}; border-radius:8px; padding:8px 10px; margin-bottom:6px; font-size:0.77rem;">
              <div style="display:flex; justify-content:space-between; align-items:center;">
                <b style="color:${s.category === 'memory_tier' ? 'var(--accent)' : s.category === 'learned' ? 'var(--emerald)' : '#f8fafc'};">${s.name}</b>
                <span class="status-pill" style="background:rgba(255,255,255,0.06); color:var(--muted);">${s.category}</span>
              </div>
              <div style="color:var(--muted); margin-top:3px;">${s.description}</div>
            </div>
          `).join('');
        }
      } catch (err) {
        console.error("Errore loadSkillsHub:", err);
      }
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
        `[Mode]: ${d.mode} | [Livello 3+1]: ${d.recommended_depth}\\n` +
        `[Memory Skill]: ${d.memory_tier_skill}\\n` +
        `[Procedural Skills]: ${(d.selected_procedural_skills || []).join(', ')}\\n` +
        `[Team Roster]: ${(d.team_roster || []).map(x => x.id).join(' -> ')}\\n\\n` +
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

    // =========================================================================
    // BOOTSTRAP INITIALIZATION
    // =========================================================================
    window.addEventListener('DOMContentLoaded', () => {
      initHelpTooltips();
      applyUiTranslations(uiLang);
      loadHealth();
      loadScopedContext();
      navigateWiki('/');
      loadMcpKnowledgeGraph();
      loadSmartMemory();
      loadSkillsHub();
      setInterval(refreshAgents, 2000);
    });
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
        self.wiki_db.ensure_workspace(AccessContext(), root_path="/", can_write=True)
        # Do NOT auto-load Cortical's own source directory unless explicitly attached by user
        self.wiki_db.clear_unattached_self_repo_nodes(AccessContext(), self.repo_root)
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
                    "version": "0.4.0",
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

        # Scoped Context Attachments (Files, Folders, Skills, Plugins — ChatGPT / Claude Code style)
        if method == "GET" and path == "/api/context":
            scope_id = (query.get("scope_id") or [None])[0]
            return (
                HTTPStatus.OK,
                {
                    "attachments": self.wiki_db.list_context_attachments(ctx, scope_id=scope_id),
                    "available_skills": [s.name for s in self.skill_hub.discover_skills()],
                    "available_plugins": [
                        "mcp:cortical-wiki",
                        "mcp:chrome-devtools",
                        "plugin:weather-grounding",
                        "plugin:adaptive-permission-gate",
                    ],
                },
            )

        if method == "POST" and path == "/api/context/attach":
            try:
                att = self.wiki_db.attach_context_item(
                    ctx,
                    scope_id=str(body.get("scope_id", "chat")),
                    item_type=str(body.get("item_type", "file")),
                    item_ref=str(body.get("item_ref", "")),
                    depth_tier=str(body.get("depth_tier", "medium")),
                    label=str(body["label"]) if body.get("label") else None,
                    inline_content=str(body["inline_content"]) if body.get("inline_content") else None,
                )
                return (HTTPStatus.OK, att)
            except ValueError as exc:
                return (HTTPStatus.BAD_REQUEST, {"error": str(exc)})

        if method == "POST" and path == "/api/context/detach":
            att_id = str(body.get("attachment_id", ""))
            return (HTTPStatus.OK, self.wiki_db.detach_context_item(ctx, attachment_id=att_id))

        # Concept Graph Configuration & User Concept Deletion Endpoints
        if method == "GET" and path == "/api/graph/concept/config":
            cid = (query.get("concept_id") or ["concept:orchestratore-multi-agente"])[0]
            return (
                HTTPStatus.OK,
                {
                    "concept_id": cid,
                    "config": self.wiki_db.get_concept_config(ctx, cid),
                },
            )

        if method == "POST" and path == "/api/graph/concept/config":
            cid = str(body.get("concept_id", "concept:orchestratore-multi-agente"))
            updates = dict(body.get("config") or {})
            return (HTTPStatus.OK, self.wiki_db.update_concept_config(ctx, cid, updates))

        if method == "POST" and path == "/api/graph/concept/delete":
            nid = str(body.get("node_id", ""))
            try:
                return (HTTPStatus.OK, self.wiki_db.delete_concept_node(ctx, nid))
            except PermissionError as exc:
                return (HTTPStatus.FORBIDDEN, {"error": str(exc), "is_framework_core": True})

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

        # Adaptive Skills & Prompt Router Endpoints
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
            scope_id = str(body.get("scope_id", "chat"))
            return (
                HTTPStatus.OK,
                self.skill_hub.enhance_prompt(
                    prompt_text,
                    active_episode_id=str(active_ep) if active_ep else None,
                    scope_id=scope_id,
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
                if target == "/":
                    atts = self.wiki_db.list_context_attachments(ctx)
                    return (
                        HTTPStatus.OK,
                        {
                            "path": "/",
                            "parent_path": None,
                            "node_type": "dir",
                            "depth_tier": depth,
                            "content": "Contesto pulito (nessuna cartella sorgente pre-caricata automaticamente). Allega file, cartelle, skill o plugin tramite '+ Allega al Contesto'.",
                            "children": [
                                {
                                    "path": wp,
                                    "node_type": "file",
                                    "subtree_hash": a["attachment_id"],
                                    "summary": a.get("summary_preview", a["label"]),
                                }
                                for a in atts
                                for wp in a.get("metadata", {}).get("wiki_paths", [])
                            ],
                            "macro_relations": [],
                        },
                    )
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
            client_audio = bool(body.get("client_audio", False))
            voice_name = str(body.get("voice", "IsabellaNeural"))
            from_mic = bool(body.get("from_mic", False))
            preferred_lang = str(body.get("lang", "")) or None
            discourse_hints = body.get("discourse_hints") if isinstance(body.get("discourse_hints"), dict) else None
            tts_active = bool(body.get("client_tts_speaking", False)) or is_tts_speaking_or_cooling_down()
            t0 = time.perf_counter()
            res = self.voice_engine.handle_utterance(
                utterance,
                from_mic=from_mic,
                tts_currently_speaking=tts_active,
                discourse_hints=discourse_hints,
                preferred_lang=preferred_lang,
            )
            elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            tts_triggered = False
            audio_url = None
            used_voice = voice_name
            if speak and res.route != "ignored_echo" and res.spoken_response:
                if client_audio:
                    audio_bytes, mime, used_voice = synthesize_tts_audio_bytes(
                        res.spoken_response,
                        voice=voice_name,
                        lang=res.lang,
                    )
                    if audio_bytes:
                        aid = cache_tts_audio(audio_bytes, mime)
                        audio_url = f"/api/tts/audio?id={aid}"
                        tts_triggered = True
                    else:
                        tts_triggered = speak_native_tts(res.spoken_response, voice=voice_name, lang=res.lang)
                else:
                    tts_triggered = speak_native_tts(res.spoken_response, voice=voice_name, lang=res.lang)
            out = dataclasses.asdict(res)
            out["latency_ms"] = elapsed_ms
            out["tts_triggered"] = tts_triggered
            out["audio_url"] = audio_url
            out["tts_voice_used"] = used_voice
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

            if parsed.path == "/api/tts/audio":
                q = urllib.parse.parse_qs(parsed.query)
                aid = (q.get("id") or [""])[0]
                item = _TTS_AUDIO_CACHE.get(aid)
                if not item:
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": "Audio segment not found"})
                    return
                audio_bytes, mime = item
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(audio_bytes)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(audio_bytes)
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
