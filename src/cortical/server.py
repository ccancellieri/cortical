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

from concurrent.futures import ThreadPoolExecutor, as_completed
import dataclasses
import datetime
import hashlib
import json
import os
import platform
import re
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

from .context_window import clamp_context_window, fit_context_to_window, get_model_context_window
from .grounding import (
    detect_language,
    discover_chrome_profiles,
    extract_browser_intent,
    extract_page_read_intent,
    extract_weather_intent,
    fetch_weather_forecast,
    format_page_reading_response,
    read_active_chrome_page,
    save_chrome_profile_preference,
    visual_chrome_navigate_and_search,
)
from .hardware.profiler import HardwareProfiler, discover_ollama_models, pick_best_local_agent_model
from .memory import MemoryCurator
from .model_ops import (
    RECOMMENDED_MODEL_PRESETS,
    delete_ollama_model,
    list_ollama_models_detailed,
    pull_ollama_model,
    sync_pi_models_json,
)
from .permissions.gate import AdaptivePermissionGate
from .role_registry import (
    add_custom_role,
    delete_custom_role,
    get_all_roles,
    resolve_role_execution,
)
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


def _normalize_effort(val: Any) -> str:
    raw = str(val or "medium").strip().lower()
    if raw in {"low", "basso"}:
        return "low"
    if raw in {"high", "alto"}:
        return "high"
    return "medium"


def _query_llm_endpoints(
    system_prompt: str,
    user_prompt: str,
    base_url: str,
    timeout: float = 20.0,
    extra_messages: Optional[list[dict[str, str]]] = None,
    preferred_model: Optional[str] = None,
    effort: str = "medium",
    context_window: Optional[int] = None,
    extra_context: str = "",
    strategy_override: str = "auto",
    thinking_mode: str = "auto",
) -> Optional[str]:
    """Queries available local/LAN OpenAI-compatible servers with multi-message context fitting."""
    default_ollama = preferred_model or "qwen2.5:1.5b"
    candidates = [
        (base_url, default_ollama if ":11434" in base_url else "local-model"),
        ("http://127.0.0.1:11434/v1", default_ollama),
        ("http://127.0.0.1:8080/v1", "local-model"),
    ]
    lan_url = os.environ.get("CORTICAL_LAN_LLM", "").strip()
    if lan_url:
        candidates.append((lan_url, "local-model"))
    eff = _normalize_effort(effort)
    max_tok = 700 if eff == "low" else (2000 if eff == "high" else 1200)
    eff_win = get_model_context_window(default_ollama) if context_window is None else clamp_context_window(context_window)
    fitted = fit_context_to_window(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        extra_context=extra_context,
        history_messages=extra_messages,
        context_window_tokens=eff_win,
        reserve_output_tokens=max_tok,
        strategy_override=strategy_override,
    )
    msgs = fitted["messages"]
    t_mode = (thinking_mode or "auto").strip().lower()
    if t_mode == "off":
        reasoning_eff = "none"
    elif t_mode in {"low", "medium", "high"}:
        reasoning_eff = t_mode
    else:
        reasoning_eff = "low" if eff == "high" else "none"
    seen: set[tuple[str, str]] = set()
    for endpoint, model_name in candidates:
        key = (endpoint or "", model_name)
        if not endpoint or key in seen or ":20128" in endpoint:
            continue
        seen.add(key)
        url = endpoint.rstrip("/") + "/chat/completions"
        payload: dict[str, Any] = {
            "model": model_name,
            "messages": msgs,
            "max_tokens": max_tok,
            "temperature": 0.2,
        }
        if ":11434" in endpoint or "qwen3" in model_name.lower():
            payload["reasoning_effort"] = reasoning_eff
        if ":11434" in endpoint:
            payload["options"] = {"num_ctx": eff_win}
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
                data = json.loads(resp.read().decode("utf-8"))
                msg_obj = data["choices"][0]["message"]
                content = _strip_think_blocks(str(msg_obj.get("content") or "")).strip()
                if "</think>" in content:
                    content = content.split("</think>", 1)[1].strip()
                if "no longer supported" in content.lower() or "antigravity.google" in content.lower():
                    continue
                if content:
                    return content
        except Exception:  # noqa: BLE001
            continue
    return None


def build_chat_context(
    wiki_db: CorticalWikiDB,
    memory_curator: MemoryCurator,
    prompt: str,
    scope_id: str = "chat",
) -> tuple[str, list[dict[str, str]]]:
    """Builds compact attachment/wiki context and rolling chat history for stateless reflex calls."""
    ctx = AccessContext()
    blocks: list[str] = []
    atts = wiki_db.list_context_attachments(ctx, scope_id=scope_id)
    for att in atts[:5]:
        line = f"[{att['item_type'].upper()}] {att['label']}: {att.get('summary_preview', '')[:220]}"
        for wp in att.get("metadata", {}).get("wiki_paths", [])[:2]:
            try:
                node = wiki_db.navigate(ctx, path=wp, depth=DepthTier.HIGH)
                line += f"\n  Contenuto ({wp}): {str(node.get('content', ''))[:900]}"
            except KeyError:
                pass
        blocks.append(line)

    hits = wiki_db.search(ctx, query=prompt, depth=DepthTier.MEDIUM, limit=2)
    for h in hits:
        blocks.append(f"[WIKI {h['path']}] {str(h.get('content', ''))[:320]}")

    history_msgs: list[dict[str, str]] = []
    for turn in reversed(memory_curator.get_recent_chat(limit=4, ctx=ctx, scope_id=scope_id)):
        if turn.get("user_text"):
            history_msgs.append({"role": "user", "content": str(turn["user_text"])})
        if turn.get("assistant_text"):
            history_msgs.append({"role": "assistant", "content": str(turn["assistant_text"])})

    return ("\n\n".join(blocks), history_msgs)


def query_local_reflex_llm(
    prompt: str,
    base_url: str,
    timeout: float = 8.0,
    lang: str = "auto",
    extra_context: str = "",
    chat_history: Optional[list[dict[str, str]]] = None,
    preferred_model: Optional[str] = None,
    context_window: Optional[int] = None,
    effort: str = "medium",
    browser_model: Optional[str] = None,
    browser_context_window: Optional[int] = None,
    strategy_override: str = "auto",
    thinking_mode: str = "auto",
) -> str:
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
            summarize_llm_fn=lambda lp: _query_llm_endpoints(
                sys_sum,
                lp,
                base_url,
                timeout=timeout,
                preferred_model=browser_model or preferred_model,
                context_window=browser_context_window or context_window,
                effort=effort,
            ) or "",
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
    if extra_context.strip():
        sys_chat += f"\n\n=== CONTESTO ATTIVO ALLEGATO / WIKI ===\n{extra_context.strip()}"
    llm_out = _query_llm_endpoints(
        sys_chat,
        prompt,
        base_url,
        timeout=timeout,
        extra_messages=chat_history,
        preferred_model=preferred_model,
        context_window=context_window,
        effort=effort,
        strategy_override=strategy_override,
        thinking_mode=thinking_mode,
    )
    if llm_out:
        return llm_out

    if eff_lang == "en":
        return f"I received your request: '{prompt}'. If you want an operational multi-agent task, say 'create a task for {prompt}'."
    return f"Ho ricevuto la richiesta: '{prompt}'. Se vuoi che diventi un task operativo, chiedimi 'crea un task per {prompt}'."


def _strip_think_blocks(text: str) -> str:
    """Removes leaked `<think>...</think>` blocks from local model outputs."""
    clean = re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL)
    if "<think>" in clean:
        clean = clean.split("<think>", 1)[0]
    return clean.strip()


def _extract_pi_content_text(content: Any) -> str:
    """Extracts plain text from either string or structured `pi` message content blocks."""
    if isinstance(content, str):
        return _strip_think_blocks(content)
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
            elif isinstance(item, str):
                parts.append(item)
        return _strip_think_blocks("\n".join(p for p in parts if p))
    return ""


def _parse_pi_json_event(raw_line: str) -> Optional[dict[str, Any]]:
    """Parses one LF-terminated JSONL event emitted by `pi --mode json`."""
    clean = (raw_line or "").strip()
    if not clean or not clean.startswith("{"):
        return None
    try:
        obj = json.loads(clean)
        return obj if isinstance(obj, dict) else None
    except Exception:  # noqa: BLE001
        return None


def _resolve_pi_binary() -> Optional[str]:
    """Finds the `pi` executable even under minimal launchd/systemd PATH."""
    found = shutil.which("pi")
    if found:
        return found
    candidates = (
        Path("/opt/homebrew/bin/pi"),
        Path("/usr/local/bin/pi"),
        Path.home() / ".local" / "bin" / "pi",
        Path.home() / ".npm-global" / "bin" / "pi",
    )
    for cand in candidates:
        if cand.is_file() and os.access(cand, os.X_OK):
            return str(cand)
    return None


class _EgressGuardProxy:
    """Local HTTP/CONNECT proxy that blocks and logs all outbound non-loopback network attempts."""

    def __init__(self, perm_gate: AdaptivePermissionGate) -> None:
        self.perm_gate = perm_gate
        self._context: dict[str, str] = {"session_id": "", "role": "", "model": ""}
        self._lock = threading.Lock()
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self.port: int = 0

    def set_context(self, *, session_id: str = "", role: str = "", model: str = "") -> None:
        with self._lock:
            self._context = {"session_id": session_id, "role": role, "model": model}

    def start(self) -> int:
        if self._httpd is not None:
            return self.port
        guard = self

        class _ProxyHandler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
                return

            def _handle_egress(self) -> None:
                target = str(self.path or "")
                host_hdr = str(self.headers.get("Host") or "")
                host = host_hdr.split(":")[0].lower() if host_hdr else ""
                if "://" in target:
                    host = urllib.parse.urlparse(target).hostname or host
                elif ":" in target and self.command == "CONNECT":
                    host = target.split(":")[0].lower()

                with guard._lock:
                    ctx_meta = dict(guard._context)
                clen = int(self.headers.get("Content-Length") or 0)
                body_excerpt = ""
                if clen > 0:
                    try:
                        body_excerpt = self.rfile.read(min(clen, 400)).decode("utf-8", errors="replace")
                    except Exception:  # noqa: BLE001
                        body_excerpt = ""

                guard.perm_gate.record_egress_event(
                    session_id=ctx_meta.get("session_id", ""),
                    role=ctx_meta.get("role", ""),
                    model=ctx_meta.get("model", ""),
                    source="egress_proxy",
                    method=self.command,
                    target_host=host or target[:120],
                    target_url=target[:350],
                    payload_excerpt=body_excerpt,
                    verdict="blocked",
                    reason=f"Blocked outbound {self.command} to {host or target} by Cortical strict isolation.",
                )
                msg = json.dumps({"error": "Blocked by Cortical Egress Isolation", "host": host}).encode("utf-8")
                self.send_response(403)
                self.send_header("Content-Type", "application/json")
                self.send_header("X-Cortical-Blocked", "egress-isolation")
                self.send_header("Content-Length", str(len(msg)))
                self.end_headers()
                self.wfile.write(msg)

            do_GET = _handle_egress
            do_POST = _handle_egress
            do_PUT = _handle_egress
            do_DELETE = _handle_egress
            do_HEAD = _handle_egress
            do_CONNECT = _handle_egress

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), _ProxyHandler)
        self.port = int(self._httpd.server_address[1])
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self.port

    def stop(self) -> None:
        if self._httpd is not None:
            try:
                self._httpd.shutdown()
                self._httpd.server_close()
            except Exception:  # noqa: BLE001
                pass
            self._httpd = None
            self.port = 0


def _build_pi_subprocess_env(
    repo_root: Path,
    *,
    effort: str = "medium",
    egress_proxy_port: int = 0,
    session_id: str = "",
    role: str = "",
    model: str = "",
) -> dict[str, str]:
    """Builds a subprocess environment with Homebrew/venv PATH and strict egress isolation."""
    env = dict(os.environ)
    extra_bins = [
        str(repo_root / ".venv" / "bin"),
        "/opt/homebrew/bin",
        "/usr/local/bin",
        str(Path.home() / ".local" / "bin"),
    ]
    cur_parts = [p for p in env.get("PATH", "/usr/bin:/bin:/usr/sbin:/sbin").split(":") if p]
    merged_parts = extra_bins + [p for p in cur_parts if p not in extra_bins]
    env["PATH"] = ":".join(merged_parts)
    env.setdefault("PYTHONPATH", str(repo_root / "src"))
    env["CORTICAL_ROOT"] = str(repo_root)
    env["PI_CORTICAL_WORKER"] = "1"
    env["PI_CORTICAL_FAST"] = "1"
    env["PI_EFFORT"] = _normalize_effort(effort)
    env["PI_ISOLATION_MODE"] = "strict"
    if session_id:
        env["PI_ACTIVE_SESSION_ID"] = session_id
    if role:
        env["PI_ACTIVE_ROLE"] = role
    if model:
        env["PI_ACTIVE_MODEL"] = model
    if egress_proxy_port > 0:
        proxy_url = f"http://127.0.0.1:{egress_proxy_port}"
        for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
            env[k] = proxy_url
        env["NO_PROXY"] = "127.0.0.1,localhost,::1"
        env["no_proxy"] = "127.0.0.1,localhost,::1"
    return env


def _wants_parallel_swarm(
    goal: str,
    has_custom_runner: bool,
    parallel_flag: Optional[bool],
    orch_cfg: dict[str, Any],
) -> bool:
    """Determines whether a task should orchestrate parallel specialized agents."""
    if parallel_flag is not None:
        return bool(parallel_flag)
    norm = (goal or "").lower()
    explicit = any(
        k in norm
        for k in (
            "parallelo", "parallel", "swarm", "multi-agente", "multi agente",
            "multiagent", "coordina agenti", "squadra", "più agenti", "diversi agenti",
        )
    )
    if explicit:
        return True
    if has_custom_runner:
        return False
    return bool(orch_cfg.get("parallel_agents", True))


def _wants_continuous_loop(goal: str, auto_loop_flag: Optional[bool]) -> bool:
    """Determines whether a task should iterate autonomously until Reviewer convergence or Stop."""
    if auto_loop_flag is not None:
        return bool(auto_loop_flag)
    norm = (goal or "").lower()
    return any(
        k in norm
        for k in (
            "in loop", "loop ", "finché", "finche", "until i stop",
            "in automatico", "continua fin", "iterativ", "autonomous loop",
        )
    )


def _clean_episode_title(raw_title: Any, session_id: str, goal: Any = "") -> str:
    """Normalizes stored episode titles, stripping legacy [pi-xxx] prefixes and truncating cleanly."""
    t = str(raw_title or "").strip()
    prefix = f"[{session_id}]"
    if t.startswith(prefix):
        t = t[len(prefix):].strip()
    if t and t != session_id and len(t) <= 60:
        return t
    return _synthesize_short_l1_title(str(goal or t or session_id))


def _synthesize_short_l1_title(
    goal: str,
    base_url: str | None = None,
    preferred_model: str | None = None,
) -> str:
    """Produces a crisp 2-4 word L1 synthesis title from a task goal, optionally using the local LLM."""
    raw = re.sub(r"\s+", " ", str(goal or "").strip())
    if not raw:
        return "Nuovo Task"
    if base_url:
        try:
            reply = _query_llm_endpoints(
                "Generate a concise 2-3 word title in the SAME language as the user's goal. "
                "Reply with ONLY the 2-3 word title, no quotes, no punctuation, no markdown.",
                raw[:400],
                base_url,
                timeout=12.0,
                preferred_model=preferred_model,
                max_tokens=24,
            )
            cleaned = re.sub(r"[\"'`*#:\n\r]+", " ", str(reply or "")).strip()
            words = [w for w in cleaned.split() if w][:4]
            if 1 <= len(words) <= 4:
                return " ".join(words)[:56]
        except Exception:  # noqa: BLE001
            pass
    stop = {"a", "ad", "al", "all", "alla", "alle", "con", "da", "dal", "de", "dei", "del", "della", "di", "e", "ed", "i", "il", "in", "la", "le", "lo", "nel", "nella", "o", "per", "su", "sul", "sulla", "tra", "un", "una", "uno", "the", "a", "an", "and", "or", "to", "for", "of", "in", "on", "with"}
    tokens = [re.sub(r"^[^\w]+|[^\w]+$", "", w) for w in raw.split()]
    kept = [w for w in tokens if w and w.lower() not in stop]
    chosen = (kept or tokens)[:3]
    return (" ".join(chosen) or raw[:36])[:56]


def _scan_external_platform_skills(target_skills_dir: Path) -> list[dict[str, Any]]:
    """Scans Antigravity, Codex, and Claude local skill directories for importable SKILL.md bundles."""
    home = Path.home()
    roots = [
        ("antigravity", home / ".gemini" / "config" / "skills"),
        ("antigravity", home / ".gemini" / "antigravity" / "skills"),
        ("codex", home / ".codex" / "skills"),
        ("claude", home / ".claude" / "skills"),
    ]
    found: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for platform, root in roots:
        if not root.exists() or not root.is_dir():
            continue
        for entry in sorted(root.iterdir()):
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            skill_md = entry / "SKILL.md"
            if not skill_md.exists():
                continue
            key = f"{platform}:{entry.name}"
            if key in seen_names:
                continue
            seen_names.add(key)
            desc = ""
            try:
                head = skill_md.read_text(encoding="utf-8", errors="ignore")[:900]
                m = re.search(r"description:\s*(.+)", head)
                if m:
                    desc = m.group(1).strip().strip('"\'')[:180]
            except OSError:
                pass
            imported = (target_skills_dir / entry.name / "SKILL.md").exists()
            found.append({
                "platform": platform,
                "name": entry.name,
                "path": str(skill_md),
                "description": desc,
                "imported": imported,
            })
    return found


class PiAgentManager:
    """Manages explicit-only `pi` coding tasks with isolated working notes and compact archival."""

    COORDINATOR_ROLES = {"coordinator", "orchestrator"}

    def __init__(
        self,
        repo_root: Path,
        wiki_db: CorticalWikiDB,
        memory_curator: MemoryCurator,
        perm_gate: AdaptivePermissionGate,
        base_url_fn: Any,
        skill_hub: Optional[CorticalSkillHub] = None,
        pi_runner: Optional[Any] = None,
        audio_enabled_fn: Optional[Any] = None,
    ) -> None:
        self.repo_root = repo_root
        self.wiki_db = wiki_db
        self.memory_curator = memory_curator
        self.perm_gate = perm_gate
        self.base_url_fn = base_url_fn
        self.skill_hub = skill_hub
        self.pi_runner = pi_runner
        self.audio_enabled_fn = audio_enabled_fn or (lambda: True)
        self.sessions: dict[str, dict[str, Any]] = {}
        self.processes: dict[str, subprocess.Popen[str]] = {}
        self.stop_events: dict[str, threading.Event] = {}
        self._lock = threading.Lock()
        self._tts_lock = threading.Lock()
        self._pending_coordinator_speeches: list[str] = []
        self.egress_proxy = _EgressGuardProxy(perm_gate)
        self.egress_proxy_port: int = 0
        self._hydrate_from_db()

    def _ensure_egress_proxy(self) -> int:
        if self.egress_proxy_port <= 0:
            self.egress_proxy_port = self.egress_proxy.start()
        return self.egress_proxy_port

    def clear_pending_speech(self) -> None:
        with self._tts_lock:
            self._pending_coordinator_speeches.clear()

    def _handle_agent_speech_on_finish(
        self,
        role: str,
        final_text: str,
        speak_on_finish: bool,
    ) -> bool:
        """Speaks at most once, from Coordinator only, after ALL working agents have finished and only if audio is ON."""
        if not self.audio_enabled_fn():
            self.clear_pending_speech()
            return False

        is_coordinator = (role or "").strip().lower() in self.COORDINATOR_ROLES
        clean_summary = re.sub(r"\s+", " ", final_text or "").strip()

        with self._lock:
            still_working = any(s.get("status") == "working" for s in self.sessions.values())

        with self._tts_lock:
            if is_coordinator and speak_on_finish and clean_summary:
                self._pending_coordinator_speeches.append(clean_summary[:180])
            if still_working or not self._pending_coordinator_speeches:
                return False
            if not self.audio_enabled_fn():
                self._pending_coordinator_speeches.clear()
                return False
            parts = list(self._pending_coordinator_speeches)
            self._pending_coordinator_speeches.clear()

        if len(parts) == 1:
            announcement = parts[0]
        else:
            announcement = "Tutti gli agenti hanno terminato. " + " ".join(parts[:3])
        return speak_native_tts(announcement[:280])

    def _hydrate_from_db(self) -> None:
        """Loads persisted task episodes and cleans up any stale 'working' runs from prior server lifetimes."""
        ctx = AccessContext()
        self.wiki_db.mark_orphan_working_runs_stopped(ctx)
        page = self.wiki_db.search_episodes_paginated(ctx, query="", offset=0, limit=80)
        for ep in reversed(page.get("episodes", [])):
            sid = str(ep["episode_id"])
            runs = self.wiki_db.list_agent_runs(ctx, episode_id=sid, limit=30)
            out_st = str(ep.get("outcome_status") or "open")
            life = "archived" if out_st == "archived" else "open"
            self.sessions[sid] = {
                "session_id": sid,
                "title": _clean_episode_title(ep.get("title"), sid, ep.get("goal")),
                "role": runs[0]["role"] if runs else "Orchestrator",
                "goal": str(ep.get("goal") or ep.get("title") or sid),
                "status": "archived" if life == "archived" else ("completed" if out_st in {"active", "completed"} else out_st),
                "lifecycle_state": life,
                "wiki_depth": "medium",
                "skills": json.loads(ep.get("skills_used") or "[]"),
                "created_at": float(ep.get("created_at") or time.time()),
                "updated_at": float(ep.get("created_at") or time.time()),
                "steps": [
                    {
                        "index": 1,
                        "timestamp": datetime.datetime.fromtimestamp(float(ep.get("created_at") or time.time())).strftime("%H:%M:%S"),
                        "type": "output",
                        "title": "📦 Task Archiviato" if life == "archived" else "🟢 Task Aperto (Persistito)",
                        "detail": str(ep.get("learned_summary") or ep.get("synth_l2") or ""),
                        "meta": {"persisted": True},
                    }
                ],
                "runs": runs,
                "token_summary": self.wiki_db.get_token_usage_summary(ctx, episode_id=sid),
                "final_report": ep.get("learned_summary"),
                "closing_questions": [],
            }

    def list_sessions(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(reversed(list(self.sessions.values())))

    def stop_run(self, run_id: str, session_id: Optional[str] = None) -> dict[str, Any]:
        """Stops a single working agent run and updates both SQLite and in-memory state."""
        ctx = AccessContext()
        rid = str(run_id or "").strip()
        if not rid:
            return {"stopped": False, "error": "missing run_id"}
        updated_db = self.wiki_db.stop_agent_run(ctx, rid)
        stopped_sid = session_id
        with self._lock:
            for sid, sess in self.sessions.items():
                if session_id and sid != session_id:
                    continue
                for r in sess.get("runs", []):
                    if r.get("run_id") == rid and r.get("status") == "working":
                        r["status"] = "stopped"
                        stopped_sid = sid
                        updated_db = True
                if stopped_sid == sid and not any(r.get("status") == "working" for r in sess.get("runs", [])):
                    if sess.get("status") == "working":
                        sess["status"] = "stopped"
                        ev = self.stop_events.get(sid)
                        if ev:
                            ev.set()
                        proc = self.processes.get(sid)
                        if proc and proc.poll() is None:
                            try:
                                proc.terminate()
                            except Exception:  # noqa: BLE001
                                pass
        return {"stopped": updated_db, "run_id": rid, "session_id": stopped_sid}

    def search_sessions(self, query: str = "", offset: int = 0, limit: int = 15) -> dict[str, Any]:
        """Paginated FTS5 + semantic search combining live working tasks and persisted SQLite episodes."""
        ctx = AccessContext()
        q_clean = (query or "").strip().lower()
        if not q_clean:
            all_sess = self.list_sessions()
            all_sess.sort(key=lambda s: (1 if s.get("status") == "working" else 0, float(s.get("updated_at") or 0.0)), reverse=True)
            total = len(all_sess)
            page = all_sess[max(0, offset): max(0, offset) + max(1, limit)]
            return {"sessions": page, "total": total, "offset": max(0, offset), "limit": max(1, limit), "has_more": (max(0, offset) + len(page)) < total}

        db_page = self.wiki_db.search_episodes_paginated(ctx, query=query, offset=0, limit=200)
        matched_ids = [ep["episode_id"] for ep in db_page["episodes"]]
        # Include any in-memory live session matching query not yet flushed to SQLite
        with self._lock:
            for sid, s in self.sessions.items():
                if sid not in matched_ids:
                    blob = f"{sid} {s.get('goal', '')} {s.get('final_report', '')}".lower()
                    if any(tok in blob for tok in q_clean.split() if len(tok) >= 2):
                        matched_ids.insert(0, sid)
            ordered = [self.sessions[sid] for sid in matched_ids if sid in self.sessions]
        total = len(ordered)
        page = ordered[max(0, offset): max(0, offset) + max(1, limit)]
        return {"sessions": page, "total": total, "offset": max(0, offset), "limit": max(1, limit), "has_more": (max(0, offset) + len(page)) < total}

    def get_session(self, session_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            return self.sessions.get(session_id)

    def mark_archived(self, session_id: str, archived_trace: str) -> None:
        with self._lock:
            if session_id in self.sessions:
                self.sessions[session_id]["status"] = "archived"
                self.sessions[session_id]["lifecycle_state"] = "archived"
                self.sessions[session_id]["archived_trace"] = archived_trace
                self.sessions[session_id]["updated_at"] = time.time()
                self._append_step(
                    session_id,
                    "output",
                    "📦 Task Archiviato (Memoria di lavoro isolata rimossa, sintesi 3+1 nel Macro-Grafo; puoi riprenderlo in qualsiasi momento)",
                    archived_trace,
                    {"archived": True},
                )

    def reopen_session(self, session_id: str) -> dict[str, Any]:
        """Reopens an archived/completed task so the user can continue working in its scope."""
        ctx = AccessContext()
        self.wiki_db.reopen_episode(ctx, session_id)
        with self._lock:
            s = self.sessions.get(session_id)
            if not s:
                return {"reopened": False, "session_id": session_id}
            s["lifecycle_state"] = "open"
            if s.get("status") == "archived":
                s["status"] = "completed"
            s["updated_at"] = time.time()
            self._append_step(
                session_id,
                "system",
                "🔓 Task riaperto — Controllo e contesto ripristinati.",
            )
            return {"reopened": True, "session_id": session_id, "session": s}

    def rename_session(self, session_id: str, title: str) -> dict[str, Any]:
        clean_title = str(title or "").strip()[:120]
        if not clean_title:
            return {"updated": False, "session_id": session_id, "error": "Empty title"}
        with self._lock:
            s = self.sessions.get(session_id)
            if s is not None:
                s["title"] = clean_title
                s["updated_at"] = time.time()
        db_res = self.wiki_db.update_episode_title(AccessContext(), session_id, clean_title)
        return {"updated": bool(db_res.get("updated") or s is not None), "session_id": session_id, "title": clean_title}

    def delete_session(self, session_id: str) -> bool:
        with self._lock:
            ev = self.stop_events.pop(session_id, None)
            if ev is not None:
                ev.set()
            for key in [k for k in self.processes if k == session_id or k.startswith(f"{session_id}:")]:
                proc = self.processes.pop(key, None)
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
        self.clear_pending_speech()
        with self._lock:
            for ev in self.stop_events.values():
                ev.set()
            stopped_sids: set[str] = set()
            for key, proc in list(self.processes.items()):
                sid = key.split(":", 1)[0]
                try:
                    proc.terminate()
                except Exception:  # noqa: BLE001
                    pass
                if sid in self.sessions and self.sessions[sid]["status"] == "working":
                    stopped_sids.add(sid)
            for sid, sess in self.sessions.items():
                if sess.get("status") == "working":
                    stopped_sids.add(sid)
            for sid in stopped_sids:
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
        role: str = "Coordinator",
        wiki_depth: str = "medium",
        skills: Optional[list[str]] = None,
        speak_on_finish: bool = False,
        parallel: Optional[bool] = None,
        auto_loop: Optional[bool] = None,
        effort: str = "medium",
    ) -> dict[str, Any]:
        eff = _normalize_effort(effort)
        session_id = f"pi-{int(time.time() * 1000) % 1000000}"
        skills_list = skills or ["cortical-second-brain", "modern-web-guidance"]
        initial_title = _synthesize_short_l1_title(goal)
        session_obj: dict[str, Any] = {
            "session_id": session_id,
            "title": initial_title,
            "role": role,
            "goal": goal,
            "status": "working",
            "lifecycle_state": "open",
            "wiki_depth": wiki_depth,
            "effort": eff,
            "skills": skills_list,
            "created_at": time.time(),
            "updated_at": time.time(),
            "steps": [],
            "runs": [],
            "token_summary": {"total_tokens": 0, "input_tokens": 0, "output_tokens": 0, "by_model": []},
            "final_report": None,
            "closing_questions": [],
        }
        stop_ev = threading.Event()
        with self._lock:
            self.sessions[session_id] = session_obj
            self.stop_events[session_id] = stop_ev
        try:
            self.wiki_db.record_episode(
                AccessContext(),
                episode_id=session_id,
                title=initial_title,
                goal=goal,
                outcome_status="open",
                learned_summary="",
                skills_used=skills_list,
            )
        except Exception:  # noqa: BLE001
            pass

        t = threading.Thread(
            target=self._run_agent_worker,
            args=(session_id, goal, wiki_depth, skills_list, speak_on_finish, role, parallel, auto_loop, eff),
            daemon=True,
        )
        t.start()
        return session_obj

    def continue_session(
        self,
        session_id: str,
        follow_up_goal: str,
        wiki_depth: Optional[str] = None,
        speak_on_finish: bool = False,
        role: str = "Coordinator",
        parallel: Optional[bool] = None,
        auto_loop: Optional[bool] = None,
        effort: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """Continues an existing open or archived task with a new user prompt in its own scope."""
        ctx = AccessContext()
        with self._lock:
            s = self.sessions.get(session_id)
            if not s:
                return None
            eff_depth = wiki_depth or s.get("wiki_depth", "medium")
            eff = _normalize_effort(effort or s.get("effort", "medium"))
            if s.get("lifecycle_state") == "archived" or s.get("status") == "archived":
                self.wiki_db.reopen_episode(ctx, session_id)
            s["lifecycle_state"] = "open"
            s["status"] = "working"
            s["wiki_depth"] = eff_depth
            s["effort"] = eff
            s["updated_at"] = time.time()
            stop_ev = threading.Event()
            self.stop_events[session_id] = stop_ev
            self._append_step(session_id, "user_turn", "Richiesta utente nel task", follow_up_goal)
            skills_list = list(s.get("skills") or ["cortical-second-brain"])

        t = threading.Thread(
            target=self._run_agent_worker,
            args=(session_id, follow_up_goal, eff_depth, skills_list, speak_on_finish, role, parallel, auto_loop, eff),
            daemon=True,
        )
        t.start()
        return s

    def _resolve_local_pi_model(self, configured_model: str) -> str:
        installed = discover_ollama_models(self.base_url_fn()) or discover_ollama_models()
        if not installed:
            return configured_model
        if not configured_model or configured_model not in installed:
            return pick_best_local_agent_model(installed, fallback=configured_model or "qwen2.5:1.5b")
        return configured_model

    def _consume_pi_event(
        self,
        session_id: str,
        evt: dict[str, Any],
        state: dict[str, Any],
    ) -> None:
        etype = str(evt.get("type") or "")
        if etype == "tool_execution_start":
            tname = str(evt.get("toolName") or "tool")
            targs = evt.get("args") if isinstance(evt.get("args"), dict) else {}
            state["pending_args"][str(evt.get("toolCallId") or tname)] = (tname, targs)
            self._append_step(session_id, "tool_call", f"pi:{tname}", json.dumps(targs)[:200], {"tool": tname})
            return
        if etype == "tool_execution_end":
            cid = str(evt.get("toolCallId") or evt.get("toolName") or "")
            tname, targs = state["pending_args"].pop(cid, (str(evt.get("toolName") or "tool"), {}))
            res_obj = evt.get("result") if isinstance(evt.get("result"), dict) else {}
            out_txt = _extract_pi_content_text(res_obj.get("content"))
            is_err = bool(evt.get("isError"))
            meta: dict[str, Any] = {"tool": tname, "is_error": is_err}
            if targs.get("command"):
                meta["command"] = str(targs["command"])
            if targs.get("path"):
                meta["path"] = str(targs["path"])
            step = {
                "type": "tool_result",
                "title": f"{tname} ({'ERR' if is_err else 'OK'})",
                "detail": out_txt[:360] or json.dumps(targs)[:180],
                "meta": meta,
            }
            state["executed_steps"].append(step)
            state["tool_count"] += 1
            self.memory_curator.add_task_working_note(session_id, f"{step['title']}: {step['detail'][:160]}")
            return
        if etype == "error" or evt.get("error"):
            err_msg = str(evt.get("errorMessage") or evt.get("error") or evt)[:300]
            self._append_step(session_id, "system", "⚠️ Errore runtime `pi`", err_msg)
            return
        if etype in {"turn_end", "message_end"}:
            msg = evt.get("message") if isinstance(evt.get("message"), dict) else {}
            if msg.get("role") == "assistant":
                if msg.get("stopReason") == "error" or msg.get("errorMessage"):
                    err_msg = str(msg.get("errorMessage") or msg.get("stopReason") or "error")[:300]
                    self._append_step(session_id, "system", f"⚠️ Errore modello ({state.get('model', 'local')})", err_msg)
                txt = _extract_pi_content_text(msg.get("content"))
                if txt:
                    state["final_text"] = txt
                usage = msg.get("usage")
                if etype == "turn_end" and isinstance(usage, dict):
                    state["usage"]["input_tokens"] += int(usage.get("input") or 0)
                    state["usage"]["output_tokens"] += int(usage.get("output") or 0)
                    state["usage"]["total_tokens"] += int(usage.get("totalTokens") or (int(usage.get("input") or 0) + int(usage.get("output") or 0)))
                if msg.get("model"):
                    state["model"] = str(msg["model"])

    def _run_pi_local_loop(
        self,
        session_id: str,
        prompt: str,
        model_id: str,
        max_loops: int,
        timeout_sec: float = 180.0,
        proc_key: Optional[str] = None,
        stop_event: Optional[threading.Event] = None,
        tools: str = "read,bash,edit,write",
        effort: str = "medium",
        role: str = "Coordinator",
    ) -> Optional[dict[str, Any]]:
        """Executes a real local `pi -p --mode json` tool loop when available."""
        base_state: dict[str, Any] = {
            "pending_args": {},
            "executed_steps": [],
            "final_text": "",
            "tool_count": 0,
            "model": model_id,
            "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        }
        if self.pi_runner is not None:
            lines = self.pi_runner(prompt=prompt, model=model_id, max_loops=max_loops)
            for raw in lines or []:
                evt = raw if isinstance(raw, dict) else _parse_pi_json_event(str(raw))
                if evt:
                    self._consume_pi_event(session_id, evt, base_state)
            return base_state if (base_state["final_text"] or base_state["executed_steps"]) else None

        if os.environ.get("CORTICAL_DISABLE_LIVE_PI") == "1":
            return None
        pi_bin = _resolve_pi_binary()
        ollama_models = discover_ollama_models(self.base_url_fn()) or discover_ollama_models()
        if not pi_bin or not ollama_models:
            why = "binario `pi` non trovato" if not pi_bin else "nessun modello Ollama attivo su :11434"
            self._append_step(session_id, "system", f"⚠️ Harness locale non avviato ({why})")
            return None

        eff = _normalize_effort(effort)
        thinking_flag = "low" if eff == "high" else "off"
        resolved_model = self._resolve_local_pi_model(model_id)
        is_heavy_model = any(tag in resolved_model.lower() for tag in ("27b", "30b", "32b", "70b"))
        eff_timeout = max(240.0, timeout_sec) if is_heavy_model else (240.0 if eff == "high" else timeout_sec)
        base_state["model"] = resolved_model
        proxy_port = self._ensure_egress_proxy()
        self.egress_proxy.set_context(session_id=session_id, role=role, model=resolved_model)
        is_tiny_model = any(tag in resolved_model.lower() for tag in ("0.5b", "1b", "1.5b", "3b"))
        prompt_low = prompt.lower()
        needs_mcp = any(k in prompt_low for k in ("chrome", "browser", "wiki_create_research_doc", "wiki_upsert_concept", "wiki_get_egress_audit", "second brain"))
        eff_tools = "read,grep,bash" if is_tiny_model else tools
        cmd = [
            pi_bin, "-p", "--mode", "json", "--no-session", "--approve",
            "--no-skills", "--no-prompt-templates", "--no-themes",
            "--tools", eff_tools, "--thinking", thinking_flag,
            "--provider", "ollama", "--model", resolved_model,
        ]
        if not is_tiny_model:
            skill_list = ["pi-core-tools-mastery"] if eff == "low" else ["pi-core-tools-mastery", "autonomous-self-improvement"]
            if needs_mcp:
                skill_list.append("chrome-complex-workflows" if ("chrome" in prompt_low or "browser" in prompt_low) else "second-brain-3plus1-workflow")
            for skill_name in skill_list:
                skill_dir = self.repo_root / ".agents" / "skills" / skill_name
                if (skill_dir / "SKILL.md").is_file():
                    cmd.extend(["--skill", str(skill_dir)])
        harness_path = self.repo_root / ".pi" / "extensions" / "cortical-harness.ts"
        if harness_path.is_file():
            ext_flags = ["--no-extensions"]
            if not is_tiny_model and needs_mcp:
                ext_flags.extend(["-e", "builtin:mcp", "-e", "builtin:tool-search"])
            ext_flags.extend(["-e", str(harness_path)])
            cmd.extend(ext_flags)
        cmd.append(prompt)

        key = proc_key or session_id
        proc = subprocess.Popen(
            cmd,
            cwd=str(self.repo_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=_build_pi_subprocess_env(
                self.repo_root,
                effort=eff,
                egress_proxy_port=proxy_port,
                session_id=session_id,
                role=role,
                model=resolved_model,
            ),
        )
        with self._lock:
            self.processes[key] = proc
        deadline = time.time() + eff_timeout
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                if (stop_event is not None and stop_event.is_set()) or time.time() > deadline or base_state["tool_count"] >= max(max_loops * 5, 12):
                    proc.terminate()
                    break
                evt = _parse_pi_json_event(line)
                if evt:
                    self._consume_pi_event(session_id, evt, base_state)
            proc.wait(timeout=3)
        except Exception:  # noqa: BLE001
            proc.terminate()
        finally:
            with self._lock:
                self.processes.pop(key, None)

        if not (base_state["final_text"] or base_state["executed_steps"]) and proc.stderr is not None:
            err_txt = (proc.stderr.read() or "").strip()
            if err_txt:
                self._append_step(session_id, "system", "⚠️ Output diagnostico stderr `pi`", err_txt[:400])
        return base_state if (base_state["final_text"] or base_state["executed_steps"]) else None

    def _record_run_start(
        self,
        ctx: AccessContext,
        *,
        run_id: str,
        session_id: str,
        role: str,
        model: str,
        goal: str,
        started_at: float,
    ) -> None:
        run_rec = {
            "run_id": run_id,
            "episode_id": session_id,
            "role": role,
            "model": model,
            "provider": "ollama",
            "status": "working",
            "goal": goal[:200],
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "elapsed_sec": 0.0,
            "started_at": started_at,
        }
        with self._lock:
            sess = self.sessions.get(session_id)
            if sess is not None:
                sess.setdefault("runs", []).insert(0, run_rec)
        self.wiki_db.upsert_agent_run(
            ctx, run_id=run_id, episode_id=session_id, role=role,
            model=model, provider="ollama", status="working", goal=goal, started_at=started_at,
        )

    def _record_run_finish(
        self,
        ctx: AccessContext,
        *,
        run_id: str,
        session_id: str,
        role: str,
        model: str,
        status: str,
        goal: str,
        in_tok: int,
        out_tok: int,
        tot_tok: int,
        started_at: float,
    ) -> float:
        elapsed_sec = round(time.time() - started_at, 2)
        self.wiki_db.upsert_agent_run(
            ctx, run_id=run_id, episode_id=session_id, role=role,
            model=model, provider="ollama", status=status, goal=goal,
            input_tokens=in_tok, output_tokens=out_tok, total_tokens=tot_tok,
            elapsed_sec=elapsed_sec, started_at=started_at, finished_at=time.time(),
        )
        tok_summary = self.wiki_db.get_token_usage_summary(ctx, episode_id=session_id)
        with self._lock:
            sess = self.sessions.get(session_id)
            if sess is not None:
                for r in sess.get("runs", []):
                    if r["run_id"] == run_id:
                        r.update({
                            "status": status,
                            "model": model,
                            "input_tokens": in_tok,
                            "output_tokens": out_tok,
                            "total_tokens": tot_tok,
                            "elapsed_sec": elapsed_sec,
                        })
                sess["token_summary"] = tok_summary
                sess["updated_at"] = time.time()
        return elapsed_sec

    def _execute_role_pi_run(
        self,
        ctx: AccessContext,
        *,
        session_id: str,
        run_role: str,
        model_id: str,
        goal: str,
        prompt: str,
        max_loops: int,
        stop_ev: threading.Event,
        tools: str = "read,bash,edit,write",
        effort: str = "medium",
    ) -> dict[str, Any]:
        run_id = f"run-{session_id}-{run_role.lower()}-{int(time.time() * 1000) % 100000}"
        t_start = time.time()
        resolved_model = self._resolve_local_pi_model(model_id)
        self._record_run_start(
            ctx, run_id=run_id, session_id=session_id, role=run_role,
            model=resolved_model, goal=goal, started_at=t_start,
        )
        pi_res = self._run_pi_local_loop(
            session_id=session_id,
            prompt=prompt,
            model_id=model_id,
            max_loops=max_loops,
            proc_key=f"{session_id}:{run_id}",
            stop_event=stop_ev,
            tools=tools,
            effort=effort,
            role=run_role,
        )
        executed_steps = list(pi_res.get("executed_steps") or []) if pi_res else []
        usage = (pi_res or {}).get("usage") or {}
        in_tok = int(usage.get("input_tokens") or 0)
        out_tok = int(usage.get("output_tokens") or 0)
        tot_tok = int(usage.get("total_tokens") or (in_tok + out_tok))
        if pi_res and pi_res.get("model"):
            resolved_model = str(pi_res["model"])
        output_text = str((pi_res or {}).get("final_text") or "").strip()
        run_status = "stopped" if stop_ev.is_set() else "completed"
        elapsed = self._record_run_finish(
            ctx, run_id=run_id, session_id=session_id, role=run_role,
            model=resolved_model, status=run_status, goal=goal,
            in_tok=in_tok, out_tok=out_tok, tot_tok=tot_tok, started_at=t_start,
        )
        return {
            "run_id": run_id,
            "role": run_role,
            "model": resolved_model,
            "pi_res": pi_res,
            "executed_steps": executed_steps,
            "output_text": output_text,
            "in_tok": in_tok,
            "out_tok": out_tok,
            "tot_tok": tot_tok,
            "elapsed_sec": elapsed,
        }

    def _run_parallel_swarm_iteration(
        self,
        ctx: AccessContext,
        *,
        session_id: str,
        goal: str,
        iteration: int,
        att_block: str,
        enh_block: str,
        orch_cfg: dict[str, Any],
        prior_notes: str,
        stop_ev: threading.Event,
        effort: str = "medium",
    ) -> dict[str, Any]:
        """Runs Analyst + Implementer in parallel, then Reviewer, returning steps and loop verdict."""
        max_loops = int(orch_cfg.get("max_agent_loops", 6))
        analyst_model = str(orch_cfg.get("analyst_model", "qwen3.8:27b-iq2_xs"))
        impl_model = str(orch_cfg.get("implementer_model", "qwen3.8:27b-iq2_xs"))
        rev_model = str(orch_cfg.get("reviewer_model", "qwen3.8:27b-iq2_xs"))

        shared_ctx = (
            (f"[ALLEGATI CONTESTO]\n{att_block}\n\n" if att_block else "")
            + (f"[CONTESTO SKILL/WIKI]\n{enh_block}\n\n" if enh_block else "")
            + (f"[ITERAZIONE PRECEDENTE]\n{prior_notes}\n\n" if prior_notes else "")
        )
        analyst_prompt = (
            f"Ruolo: Analyst (Iterazione {iteration}) | Task ({session_id}): {goal}\n"
            "CHIAMA SUBITO i tool `read` e `bash` (rg/ls/cat) per ispezionare file/directory reali. "
            "NON fare domande all'utente e NON inventare. Riporta solo fatti, percorsi e numeri verificati.\n\n"
            + shared_ctx
        ).strip()
        impl_prompt = (
            f"Ruolo: Implementer (Iterazione {iteration}) | Task ({session_id}): {goal}\n"
            "CHIAMA SUBITO i tool (`read`/`edit`/`write`/`bash`) per eseguire verifiche, navigazione Chrome/CDP, "
            "modifiche al codice o test reali. NON fare domande all'utente. Riporta solo risultati reali eseguiti.\n\n"
            + shared_ctx
        ).strip()

        self._append_step(
            session_id,
            "subagent",
            f"🔀 Avvio squadra parallela · Iterazione {iteration} (Analyst + Implementer)",
            f"Obiettivo: {goal[:180]}",
            {"iteration": iteration, "roles": ["Analyst", "Implementer"]},
        )

        worker_specs = [
            ("Analyst", analyst_model, analyst_prompt, "read,grep,find,ls,bash"),
            ("Implementer", impl_model, impl_prompt, "read,bash,edit,write,grep,find,ls"),
        ]
        # Serialize heavy local Ollama workers (>=14B) on the single local GPU to prevent contention/timeouts
        has_heavy_local = self.pi_runner is None and any(
            tag in (analyst_model + " " + impl_model).lower()
            for tag in ("14b", "27b", "30b", "32b", "70b")
        )
        worker_results: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=1 if has_heavy_local else 2) as pool:
            futs = [
                pool.submit(
                    self._execute_role_pi_run,
                    ctx,
                    session_id=session_id,
                    run_role=r_name,
                    model_id=r_model,
                    goal=goal,
                    prompt=r_prompt,
                    max_loops=max_loops,
                    stop_ev=stop_ev,
                    tools=r_tools,
                    effort=effort,
                )
                for r_name, r_model, r_prompt, r_tools in worker_specs
            ]
            for fut in as_completed(futs):
                wres = fut.result()
                worker_results.append(wres)
                self._append_step(
                    session_id,
                    "subagent",
                    f"Agente `{wres['role']}` ({wres['model']} · {len(wres['executed_steps'])} tool · {wres['tot_tok']} tok · {wres['elapsed_sec']}s)",
                    wres["output_text"] or "Nessun output testuale restituito.",
                    {"role": wres["role"], "run_id": wres["run_id"], "tools": len(wres["executed_steps"])},
                )

        all_steps = [st for w in worker_results for st in w["executed_steps"]]
        if stop_ev.is_set():
            return {"results": worker_results, "review": None, "steps": all_steps, "verdict": "STOPPED"}

        digest = "\n\n".join(
            f"[{w['role']} · {len(w['executed_steps'])} tool ({', '.join(st.get('meta', {}).get('tool', '?') for st in w['executed_steps'][:6]) or 'none'})]\n{w['output_text'][:600]}"
            for w in worker_results
        )
        rev_prompt = (
            f"Ruolo: Reviewer (Iterazione {iteration}) | Task ({session_id}): {goal}\n"
            "Controlla ciò che Analyst e Implementer hanno eseguito realmente (usa `read` o `bash` solo se devi verificare un file/test).\n"
            "Se manca ancora una verifica concreta o una modifica richiesta dall'obiettivo, chiudi con `VERDICT: CONTINUE` indicando il file e l'azione esatta per la prossima iterazione.\n"
            "Altrimenti chiudi la risposta con `VERDICT: DONE`.\n\n"
            f"{digest}"
        ).strip()
        rev_res = self._execute_role_pi_run(
            ctx,
            session_id=session_id,
            run_role="Reviewer",
            model_id=rev_model,
            goal=goal,
            prompt=rev_prompt,
            max_loops=max_loops,
            stop_ev=stop_ev,
            tools="read,grep,find,ls,bash",
            effort=effort,
        )
        all_steps.extend(rev_res["executed_steps"])
        self._append_step(
            session_id,
            "subagent",
            f"Agente `Reviewer` ({rev_res['model']} · {len(rev_res['executed_steps'])} tool · {rev_res['tot_tok']} tok · {rev_res['elapsed_sec']}s)",
            rev_res["output_text"] or "Verifica completata.",
            {"role": "Reviewer", "run_id": rev_res["run_id"]},
        )
        rev_up = rev_res["output_text"].upper()
        impl_ok = any(
            w["role"] == "Implementer" and (bool(w["output_text"].strip()) or bool(w["executed_steps"]))
            for w in worker_results
        )
        verdict_matches = re.findall(r"VERDICT\s*:\s*(CONTINUE|DONE)", rev_up)
        last_verdict = verdict_matches[-1] if verdict_matches else ""
        if not impl_ok:
            verdict = "CONTINUE"
        elif last_verdict == "CONTINUE":
            verdict = "CONTINUE"
        elif last_verdict == "DONE" or rev_up.strip().endswith("DONE"):
            verdict = "DONE"
        else:
            verdict = "CONTINUE" if "CONTINUE" in rev_up else "DONE"
        return {"results": worker_results, "review": rev_res, "steps": all_steps, "verdict": verdict}

    def _auto_answer_questions_locally(
        self,
        session_id: str,
        goal: str,
        questions: list[str],
        context_text: str,
        preferred_model: str,
        effort: str = "medium",
    ) -> list[dict[str, str]]:
        """Autonomously answers loop/closing questions so continuous local tasks never stall."""
        clean_qs = [str(q).strip() for q in questions if str(q).strip()]
        if not clean_qs:
            return []
        q_block = "\n".join(f"{idx + 1}. {q}" for idx, q in enumerate(clean_qs[:4]))
        llm_ans = _query_llm_endpoints(
            "Sei il Coordinatore autonomo locale di Cortical. Rispondi alle domande operative in italiano sintetico e concreto usando solo i dati del contesto, senza chiedere conferme all'utente.",
            f"Obiettivo: {goal}\n\nContesto/Risultati:\n{context_text[:900]}\n\nDomande da risolvere autonomamente:\n{q_block}",
            self.base_url_fn(),
            timeout=18.0,
            preferred_model=preferred_model,
            effort=effort,
        )
        answer_text = (llm_ans or "").strip()
        if not answer_text:
            answer_text = (
                f"Decisione autonoma: mantieni l'obiettivo '{goal[:80]}' sulla traccia Wiki `/` e `/src`, "
                "conservando i risultati verificati ed evitando passaggi esterni bloccati."
            )
        self.memory_curator.add_task_working_note(session_id, f"[AUTO-ANSWER] {answer_text[:280]}")
        self._append_step(
            session_id,
            "thinking",
            "🤖 Risposta autonoma alle domande del loop",
            f"Domande:\n{q_block}\n\nDecisione autonoma:\n{answer_text}",
            {"autonomous": True, "question_count": len(clean_qs)},
        )
        return [{"question": q, "answer": answer_text} for q in clean_qs]

    def _run_agent_worker(
        self,
        session_id: str,
        goal: str,
        wiki_depth: str,
        skills: list[str],
        speak_on_finish: bool,
        run_role: str = "Orchestrator",
        parallel: Optional[bool] = None,
        auto_loop: Optional[bool] = None,
        effort: str = "medium",
    ) -> None:
        eff = _normalize_effort(effort)
        ctx = AccessContext()
        run_id = f"run-{session_id}-{int(time.time() * 1000) % 100000}"
        t_start = time.time()
        resolved_model = "local-reflex"
        with self._lock:
            stop_ev = self.stop_events.setdefault(session_id, threading.Event())
        try:
            orch_cfg = self.wiki_db.get_concept_config(ctx, "concept:orchestratore-multi-agente")
            max_loops = int(orch_cfg.get("max_agent_loops", 6))
            role_key = "coordinator" if run_role == "Coordinator" else "implementer"
            coord_exec = resolve_role_execution(orch_cfg, "coordinator")
            analyst_exec = resolve_role_execution(orch_cfg, "analyst")
            impl_exec = resolve_role_execution(orch_cfg, "implementer")
            rev_exec = resolve_role_execution(orch_cfg, "reviewer")
            coord_model = coord_exec["model"]
            analyst_model = analyst_exec["model"]
            impl_model = impl_exec["model"]
            rev_model = rev_exec["model"]
            active_exec = coord_exec if role_key == "coordinator" else impl_exec
            resolved_model = self._resolve_local_pi_model(active_exec["model"])
            active_ctx_window = active_exec["context_window"]
            use_parallel = _wants_parallel_swarm(goal, self.pi_runner is not None, parallel, orch_cfg)
            use_loop = _wants_continuous_loop(goal, auto_loop)

            self._record_run_start(
                ctx, run_id=run_id, session_id=session_id, role=run_role,
                model=resolved_model, goal=goal, started_at=t_start,
            )

            task_atts = self.wiki_db.list_context_attachments(ctx, scope_id=session_id)
            chat_atts = self.wiki_db.list_context_attachments(ctx, scope_id="chat")
            attachments = task_atts or chat_atts
            eff_scope = session_id if task_atts else "chat"
            att_summary = (
                ", ".join(f"{a['item_type']}:{a['label']}" for a in attachments)
                if attachments
                else "Nessun file/cartella allegata (contesto isolato)"
            )

            mode_label = "Parallel Swarm + Loop" if (use_parallel and use_loop) else ("Parallel Swarm" if use_parallel else "Single Coordinator")
            self._append_step(
                session_id,
                "thinking",
                f"Inizializzazione `{run_role}` ({resolved_model} · {mode_label} · Wiki: {wiki_depth.upper()} · Max Loop: {max_loops})",
                f"Obiettivo: {goal}\nModelli Configurati: Analyst={analyst_model}, Implementer={impl_model}, Reviewer={rev_model}\nContesto Allegato ({eff_scope}): {att_summary}",
            )
            self.memory_curator.add_task_working_note(session_id, f"Avvio run {run_id}: {goal} | Allegati: {att_summary}")
            time.sleep(0.05)

            att_context_lines: list[str] = []
            for a in attachments[:6]:
                att_context_lines.append(f"[{a['item_type'].upper()}] {a['label']}: {a.get('summary_preview', '')[:180]}")
            att_block = "\n".join(att_context_lines)

            hits = self.wiki_db.search(ctx, query=goal, depth=DepthTier(wiki_depth), limit=4)
            hit_lines = "\n".join(f"  • {h['path']} [tier={h['depth_tier']}]: {h['content'][:160]}..." for h in hits) if hits else "  • Nessun match FTS5 specifico."
            self._append_step(
                session_id,
                "tool_call",
                f"mcp__cortical-wiki__wiki_search(query={json.dumps(goal[:40])}, depth='{wiki_depth}')",
                f"Allegati ({eff_scope}):\n" + (att_block or "  • Nessuno") + f"\n\nWiki Merkle:\n{hit_lines}",
                {"tool": "wiki_search", "hits": len(hits)},
            )

            enh_instructions = ""
            if self.skill_hub is not None:
                enh = self.skill_hub.enhance_prompt(goal, ctx=ctx, active_episode_id=session_id, scope_id=eff_scope)
                enh_instructions = enh.enhanced_system_instructions[:450]

            executed_steps: list[dict[str, Any]] = []
            in_tok = 0
            out_tok = 0
            tot_tok = 0
            pi_output_text = ""

            if use_parallel:
                loop_limit = max(max_loops, 4) if use_loop else 1
                prior_notes = ""
                iter_summaries: list[str] = []
                for it_idx in range(1, loop_limit + 1):
                    if stop_ev.is_set():
                        break
                    it_res = self._run_parallel_swarm_iteration(
                        ctx,
                        session_id=session_id,
                        goal=goal,
                        iteration=it_idx,
                        att_block=att_block,
                        enh_block=enh_instructions,
                        orch_cfg=orch_cfg,
                        prior_notes=prior_notes,
                        stop_ev=stop_ev,
                        effort=eff,
                    )
                    executed_steps.extend(it_res["steps"])
                    part_texts = [
                        f"- **{r['role']}** ({len(r['executed_steps'])} tool, {r['tot_tok']} tok): {r['output_text'][:2500]}"
                        for r in it_res["results"]
                        if r["output_text"] or r["executed_steps"]
                    ]
                    if it_res["review"] and (it_res["review"]["output_text"] or it_res["review"]["executed_steps"]):
                        rv = it_res["review"]
                        part_texts.append(f"- **Reviewer** ({rv['tot_tok']} tok): {rv['output_text'][:2500]}")
                    prior_raw = "\n".join(part_texts)
                    fitted_prior = fit_context_to_window(
                        system_prompt="Coordinator loop context",
                        user_prompt=goal,
                        extra_context=prior_raw,
                        context_window_tokens=active_ctx_window,
                        summarize_fn=lambda p, _t: _query_llm_endpoints(
                            "Sintetizza i paragrafi mantenendo tutti i fatti e file citati.",
                            p,
                            self.base_url_fn(),
                            timeout=18.0,
                            preferred_model=resolved_model,
                            context_window=active_ctx_window,
                        ),
                    )
                    prior_notes = fitted_prior["fitted_context"]
                    if part_texts:
                        iter_summaries.append(f"### Iterazione {it_idx} ({it_res['verdict']})\n" + "\n".join(part_texts))
                    if it_res["verdict"] == "CONTINUE" and use_loop and it_idx < loop_limit and not stop_ev.is_set():
                        rv_txt = (it_res.get("review") or {}).get("output_text", "")
                        loop_qs = [ln.strip() for ln in rv_txt.splitlines() if "?" in ln][:2]
                        if not loop_qs:
                            loop_qs = [f"Qual è il prossimo passo concreto per completare l'iterazione {it_idx + 1} di '{goal[:60]}'?"]
                        auto_ans = self._auto_answer_questions_locally(
                            session_id,
                            goal,
                            loop_qs,
                            prior_notes,
                            preferred_model=analyst_model or impl_model,
                            effort=eff,
                        )
                        if auto_ans:
                            prior_notes = prior_notes + "\n- **Auto-Risposta Loop**: " + auto_ans[0]["answer"][:300]
                    if it_res["verdict"] in {"DONE", "STOPPED"} or not use_loop:
                        break
                pi_output_text = "\n\n".join(iter_summaries).strip()

            if not pi_output_text:
                fitted_local = fit_context_to_window(
                    system_prompt="Coordinator task prompt",
                    user_prompt=goal,
                    extra_context=enh_instructions if attachments else "",
                    context_window_tokens=min(active_ctx_window, 8192) if eff == "low" else active_ctx_window,
                    reserve_output_tokens=2048,
                )
                compact_ctx = fitted_local["fitted_context"]
                local_prompt = (
                    f"Obiettivo Task ({session_id}): {goal}\n"
                    "CHIAMA I TOOL REALI (`read`, `edit`, `write`, `bash`) in sequenza, NON fingere modifiche non eseguite, verifica con un comando reale e riporta solo i fatti osservati.\n\n"
                    + (f"[ALLEGATI CONTESTO]\n{att_block}\n\n" if att_block else "")
                    + (f"[CONTESTO WIKI]\n{compact_ctx}" if compact_ctx else "")
                ).strip()
                pi_res = self._run_pi_local_loop(
                    session_id=session_id,
                    prompt=local_prompt,
                    model_id=coord_model if run_role == "Coordinator" else impl_model,
                    max_loops=max_loops,
                    proc_key=f"{session_id}:{run_id}",
                    stop_event=stop_ev,
                    effort=eff,
                    role=run_role,
                )
                executed_steps.extend(list(pi_res.get("executed_steps") or []) if pi_res else [])
                used_tool_names = {str((st.get("meta") or {}).get("tool") or "").lower() for st in executed_steps}
                goal_low = goal.lower()
                if any(k in goal_low for k in ("edit", "write", "modifica", "aggiungi")) and not (used_tool_names & {"edit", "write"}):
                    self._append_step(
                        session_id,
                        "system",
                        "⚠️ Anti-Hallucination Guard: nessuna modifica file (`edit`/`write`) eseguita dai tool reali.",
                        f"Tool chiamati: {sorted(used_tool_names) or ['nessuno']}",
                    )
                usage = (pi_res or {}).get("usage") or {}
                in_tok = int(usage.get("input_tokens") or 0)
                out_tok = int(usage.get("output_tokens") or 0)
                tot_tok = int(usage.get("total_tokens") or (in_tok + out_tok))
                if pi_res and pi_res.get("model"):
                    resolved_model = str(pi_res["model"])

                if pi_res and pi_res.get("final_text"):
                    pi_output_text = str(pi_res["final_text"])
                else:
                    ctx_str, _ch_hist = build_chat_context(self.wiki_db, self.memory_curator, goal, scope_id=eff_scope)
                    steps_txt = "\n".join(f"- {s['title']}: {s['detail'][:200]}" for s in executed_steps[:6])
                    synth_prompt = f"Task: {goal}\n\nAzioni/Tool già eseguiti:\n{steps_txt or 'Nessun tool eseguito.'}"
                    llm_fb = _query_llm_endpoints(
                        "Sei un assistente tecnico locale. Sintetizza in italiano chiaro e fattuale il risultato del task dai dati forniti."
                        + (f"\n\nContesto:\n{ctx_str[:1400]}" if ctx_str else ""),
                        synth_prompt,
                        self.base_url_fn(),
                        timeout=25.0,
                        preferred_model=resolved_model,
                    )
                    pi_output_text = llm_fb or (
                        f"Task {session_id} completato ({len(executed_steps)} passi tool eseguiti).\n"
                        + (steps_txt or f"Contesto ispezionato ({eff_scope}): {att_summary}")
                    )
                    if tot_tok == 0:
                        in_tok = max(12, len(local_prompt) // 4)
                        out_tok = max(8, len(pi_output_text) // 4)
                        tot_tok = in_tok + out_tok

            if tot_tok == 0 and pi_output_text:
                in_tok = max(28, (len(goal) + len(enh_instructions)) // 4)
                out_tok = max(20, len(pi_output_text) // 4)
                tot_tok = in_tok + out_tok

            if len(self.sessions.get(session_id, {}).get("steps", [])) <= 12:
                try:
                    refined = _synthesize_short_l1_title(goal, self.base_url_fn(), preferred_model=resolved_model)
                    if refined:
                        self.rename_session(session_id, refined)
                except Exception:  # noqa: BLE001
                    pass

            final_run_status = "stopped" if stop_ev.is_set() else "completed"
            elapsed_sec = self._record_run_finish(
                ctx, run_id=run_id, session_id=session_id, role=run_role,
                model=resolved_model, status=final_run_status, goal=goal,
                in_tok=in_tok, out_tok=out_tok, tot_tok=tot_tok, started_at=t_start,
            )
            tok_summary = self.wiki_db.get_token_usage_summary(ctx, episode_id=session_id)

            compiled_skill_id = None
            if self.skill_hub is not None and executed_steps:
                synth = self.skill_hub.synthesize_task_discussion_3plus1(
                    episode_id=session_id,
                    goal=goal,
                    discussion_steps=executed_steps,
                    user_closing_notes=pi_output_text[:400],
                    ctx=ctx,
                )
                if orch_cfg.get("auto_compile_skills_on_close", True):
                    ev = self.skill_hub.evaluate_and_compile_skill(
                        episode_id=session_id,
                        goal=goal,
                        lessons_learned=synth["lessons_learned"],
                        discussion_steps=executed_steps,
                        ctx=ctx,
                    )
                    if ev.should_create_skill:
                        compiled_skill_id = ev.skill_id

            touched = [h["path"] for h in hits] if hits else ["/"]
            self.wiki_db.record_episode(
                ctx,
                episode_id=session_id,
                title=f"[{session_id}] {goal[:52]}",
                goal=goal,
                outcome_status="open",
                learned_summary=pi_output_text[:300],
                skills_used=skills,
                relations=[
                    {"relation": "relates_to", "target_type": "subtree", "target_id": p}
                    for p in touched
                ],
            )
            closure_info = self.memory_curator.prepare_task_closure(session_id)
            questions = closure_info.get("closing_questions", [])
            auto_answered: list[dict[str, str]] = []
            if use_loop and questions and not stop_ev.is_set():
                auto_answered = self._auto_answer_questions_locally(
                    session_id,
                    goal,
                    questions,
                    pi_output_text,
                    preferred_model=analyst_model or impl_model,
                    effort=eff,
                )
                questions = []
            tot_all_tokens = int(tok_summary.get("total_tokens") or tot_tok)
            self._append_step(
                session_id,
                "output",
                f"Agente `{run_role}` {'interrotto' if stop_ev.is_set() else 'completato'} ({resolved_model} · {tot_all_tokens} tok · {elapsed_sec}s) — Task ancora aperto",
                pi_output_text,
                {"run_id": run_id, "model": resolved_model, "total_tokens": tot_all_tokens},
            )

            with self._lock:
                sess = self.sessions.get(session_id)
                if sess is not None:
                    sess["token_summary"] = tok_summary
                    sess["updated_at"] = time.time()
                    if sess["status"] in {"working", "stopped"}:
                        sess["status"] = "stopped" if stop_ev.is_set() else "completed"
                        sess["lifecycle_state"] = "open"
                        sess["final_report"] = pi_output_text
                        sess["closing_questions"] = questions
                        sess["auto_answered_questions"] = auto_answered
                        sess["compiled_skill_id"] = compiled_skill_id

            if not stop_ev.is_set():
                self._handle_agent_speech_on_finish(run_role, pi_output_text, speak_on_finish)

        except Exception as exc:  # noqa: BLE001
            self._record_run_finish(
                ctx, run_id=run_id, session_id=session_id, role=run_role,
                model=resolved_model, status="error", goal=goal,
                in_tok=0, out_tok=0, tot_tok=0, started_at=t_start,
            )
            self._append_step(session_id, "system", f"Errore agente: {exc}")
            with self._lock:
                if session_id in self.sessions:
                    self.sessions[session_id]["status"] = "error"
                    self.sessions[session_id]["lifecycle_state"] = "open"

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


UI_DIR = Path(__file__).with_name("ui").resolve()
DASHBOARD_HTML = Path(__file__).with_name("dashboard.html").read_text(encoding="utf-8")

_UI_MIME_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".mjs": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".html": "text/html; charset=utf-8",
}


def resolve_ui_asset(url_path: str) -> Optional[tuple[bytes, str]]:
    """Safely resolves a static frontend asset under `/ui/` without allowing path traversal."""
    if not url_path.startswith("/ui/"):
        return None
    rel = url_path[4:].lstrip("/")
    if not rel or ".." in Path(rel).parts:
        return None
    candidate = (UI_DIR / rel).resolve()
    try:
        if not candidate.is_relative_to(UI_DIR) or not candidate.is_file():
            return None
    except ValueError:
        return None
    mime = _UI_MIME_TYPES.get(candidate.suffix.lower(), "application/octet-stream")
    return (candidate.read_bytes(), mime)


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

        def _resolve_role(role_id: str) -> dict[str, Any]:
            orch_cfg = self.wiki_db.get_concept_config(AccessContext(), "concept:orchestratore-multi-agente")
            return resolve_role_execution(orch_cfg, role_id)

        def _reflex_for_role(role_id: str):
            def _fn(prompt: str) -> str:
                r = _resolve_role(role_id)
                return query_local_reflex_llm(
                    prompt,
                    self.model_rec.active_base_url,
                    preferred_model=r["model"],
                    context_window=r["context_window"],
                    effort=r["effort"],
                )
            return _fn

        self.memory_curator = MemoryCurator(self.wiki_db, llm_fn=_reflex_for_role("memory_curator"))
        agents_skills = self.repo_root / ".agents" / "skills"
        legacy_skills = self.repo_root / ".pi" / "skills"
        skills_dir = agents_skills if (agents_skills.exists() or not legacy_skills.exists()) else legacy_skills
        self.skill_hub = CorticalSkillHub(self.wiki_db, skills_dir, llm_fn=_reflex_for_role("skill_compiler"))
        self.mcp_server = CorticalWikiMCPServer(wiki_db_path)

        self.audio_responses_enabled: bool = True
        self._current_chat_scope = threading.local()
        self._dispatch_speak_flag = threading.local()

        def _reflex_with_context(prompt: str) -> str:
            active_scope = getattr(self._current_chat_scope, "value", "chat") or "chat"
            extra_ctx, hist = build_chat_context(self.wiki_db, self.memory_curator, prompt, scope_id=active_scope)
            orch_cfg = self.wiki_db.get_concept_config(AccessContext(), "concept:orchestratore-multi-agente")
            scope_prefs = ((orch_cfg.get("scope_preferences") or {}).get(active_scope)) or {}
            role_id = "chat" if active_scope == "chat" else "coordinator"
            r_chat = _resolve_role(role_id)
            r_browser = _resolve_role("browser_agent")
            return query_local_reflex_llm(
                prompt,
                self.model_rec.active_base_url,
                extra_context=extra_ctx,
                chat_history=hist,
                preferred_model=r_chat["model"],
                context_window=r_chat["context_window"],
                effort=r_chat["effort"],
                browser_model=r_browser["model"],
                browser_context_window=r_browser["context_window"],
                strategy_override=str(scope_prefs.get("context_strategy") or "auto"),
                thinking_mode=str(scope_prefs.get("thinking_mode") or "auto"),
            )

        self.agent_mgr = PiAgentManager(
            repo_root=self.repo_root,
            wiki_db=self.wiki_db,
            memory_curator=self.memory_curator,
            perm_gate=self.perm_gate,
            base_url_fn=lambda: self.model_rec.active_base_url,
            skill_hub=self.skill_hub,
            audio_enabled_fn=lambda: self.audio_responses_enabled,
        )

        def _dispatch_agentic(goal: str) -> str:
            req_speak = getattr(self._dispatch_speak_flag, "value", None)
            should_speak = self.audio_responses_enabled if req_speak is None else bool(req_speak and self.audio_responses_enabled)
            sess = self.agent_mgr.spawn_agent(goal=goal, role="Coordinator", wiki_depth="medium", speak_on_finish=should_speak)
            return str(sess["session_id"])

        def _on_stop() -> None:
            stop_native_tts()
            self.agent_mgr.stop_all()

        def _on_duck() -> None:
            duck_native_tts(force_stop=True)

        self.voice_engine = CorticalVoiceEngine(
            wiki_db=self.wiki_db,
            permission_gate=self.perm_gate,
            reflex_llm_fn=_reflex_with_context,
            agentic_dispatch_fn=_dispatch_agentic,
            stop_callback=_on_stop,
            duck_callback=_on_duck,
            memory_curator=self.memory_curator,
            sessions_status_fn=self.agent_mgr.list_sessions,
        )

    def _discover_catalog(self) -> dict[str, Any]:
        """Discovers installable/attachable Skills, Plugins, and MCP servers in the workspace."""
        skills = [
            {
                "name": s.name,
                "description": s.description,
                "category": s.category,
                "path": str(s.path),
            }
            for s in self.skill_hub.discover_skills()
        ]
        plugins = [
            {"name": "plugin:weather-grounding", "description": "Meteo & Browser Open-Meteo Grounding"},
            {"name": "plugin:adaptive-permission-gate", "description": "Controllo sicurezza & approvazioni comandi"},
        ]
        plugins_dir = self.repo_root / ".agents" / "plugins"
        if plugins_dir.is_dir():
            for child in sorted(plugins_dir.iterdir()):
                if child.is_dir():
                    plugins.append({"name": f"plugin:{child.name}", "path": str(child), "description": f"Plugin locale ({child.name})"})

        mcp_servers: list[dict[str, Any]] = []
        mcp_json = self.repo_root / ".pi" / "mcp.json"
        if mcp_json.is_file():
            try:
                raw = json.loads(mcp_json.read_text(encoding="utf-8"))
                for name, cfg in (raw.get("mcpServers") or {}).items():
                    mcp_servers.append({
                        "name": f"mcp:{name}",
                        "description": str(cfg.get("description") or cfg.get("command") or name),
                        "path": str(mcp_json),
                    })
            except Exception:  # noqa: BLE001
                pass
        if not any(m["name"] == "mcp:cortical-wiki" for m in mcp_servers):
            mcp_servers.append({"name": "mcp:cortical-wiki", "description": "Cortical 4-Tier Merkle Second Brain MCP"})
        if not any(m["name"] == "mcp:chrome-devtools" for m in mcp_servers):
            mcp_servers.append({"name": "mcp:chrome-devtools", "description": "Chrome DevTools DOM & Browser Automation MCP"})
        return {"skills": skills, "plugins": plugins, "mcp_servers": mcp_servers}

    def _browse_fs(self, raw_path: Optional[str]) -> dict[str, Any]:
        """Lists folders and files cleanly for UI skill/plugin/MCP/file browsing."""
        target = Path(raw_path).expanduser() if raw_path else self.repo_root
        try:
            resolved = target.resolve()
        except Exception:  # noqa: BLE001
            resolved = self.repo_root
        if not resolved.exists() or not resolved.is_dir():
            resolved = self.repo_root
        entries: list[dict[str, Any]] = []
        try:
            children = sorted(resolved.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError:
            children = []
        for p in children[:160]:
            if p.name.startswith(".") and p.name not in {".agents", ".pi"}:
                continue
            if p.name in {"node_modules", "__pycache__", ".venv", ".git"}:
                continue
            hint = "folder" if p.is_dir() else "file"
            if p.is_dir() and (p / "SKILL.md").is_file():
                hint = "skill"
            elif p.is_dir() and ((p / "package.json").is_file() or (p / ".pi-plugin").exists()):
                hint = "plugin"
            elif p.is_file() and (p.name == "mcp.json" or p.name.endswith(".mcp.json") or p.name == "opencode.json"):
                hint = "mcp"
            entries.append({
                "name": p.name,
                "path": str(p),
                "is_dir": p.is_dir(),
                "hint": hint,
            })
        parent = str(resolved.parent) if resolved.parent != resolved else str(resolved)
        return {"current_path": str(resolved), "parent_path": parent, "entries": entries}

    def _import_context_item(
        self,
        ctx: AccessContext,
        *,
        scope_id: str,
        item_type: str,
        item_ref: str,
        depth_tier: str = "medium",
    ) -> dict[str, Any]:
        """Imports a Skill folder, Plugin folder, or MCP JSON from disk and attaches it to scope_id."""
        ref_path = Path(item_ref).expanduser()
        eff_type = item_type.lower().strip()
        eff_ref = item_ref.strip()
        eff_label: Optional[str] = None
        if eff_type == "skill" and ref_path.exists():
            src_dir = ref_path.parent if ref_path.is_file() and ref_path.name == "SKILL.md" else ref_path
            if (src_dir / "SKILL.md").is_file():
                slug = re.sub(r"[^a-z0-9_-]+", "-", src_dir.name.lower()).strip("-") or "imported-skill"
                dest_dir = self.skill_hub.skills_root / slug
                if src_dir.resolve() != dest_dir.resolve():
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_dir / "SKILL.md", dest_dir / "SKILL.md")
                eff_ref = slug
                eff_label = slug
        elif eff_type == "mcp" and ref_path.is_file():
            try:
                cfg = json.loads(ref_path.read_text(encoding="utf-8"))
                servers = cfg.get("mcpServers") or (cfg.get("mcp") or {}).get("servers") or {}
                if isinstance(servers, dict) and servers:
                    first_name = next(iter(servers.keys()))
                    mcp_file = self.repo_root / ".pi" / "mcp.json"
                    mcp_file.parent.mkdir(parents=True, exist_ok=True)
                    existing = json.loads(mcp_file.read_text(encoding="utf-8")) if mcp_file.is_file() else {"mcpServers": {}}
                    existing.setdefault("mcpServers", {}).update(servers)
                    mcp_file.write_text(json.dumps(existing, indent=2), encoding="utf-8")
                    eff_ref = f"mcp:{first_name}"
                    eff_label = eff_ref
            except Exception:  # noqa: BLE001
                pass
        elif eff_type == "plugin" and ref_path.is_dir():
            eff_label = f"plugin:{ref_path.name}"
        return self.wiki_db.attach_context_item(
            ctx,
            scope_id=scope_id,
            item_type=eff_type,
            item_ref=eff_ref,
            depth_tier=depth_tier,
            label=eff_label,
        )

    def _get_models_config_payload(self, ctx: AccessContext, scope_id: str = "chat") -> dict[str, Any]:
        orch_cfg = self.wiki_db.get_concept_config(ctx, "concept:orchestratore-multi-agente")
        roles = get_all_roles(orch_cfg)
        role_models = {f"{r['id']}_model": r["model"] for r in roles}
        role_context_windows = {r["id"]: r["context_window"] for r in roles}
        role_efforts = {r["id"]: r["effort"] for r in roles}

        raw_windows = orch_cfg.get("model_context_windows")
        configured_windows: dict[str, int] = dict(raw_windows) if isinstance(raw_windows, dict) else {}
        base_url = self.model_rec.active_base_url or "http://127.0.0.1:11434"
        ollama_detailed = list_ollama_models_detailed(base_url)
        detailed_by_name = {m["name"]: m for m in ollama_detailed}
        discovered = [m["name"] for m in ollama_detailed] or discover_ollama_models(base_url)
        all_models = sorted(
            {
                *discovered,
                *[r["model"] for r in roles],
                *configured_windows.keys(),
            }
            - {""}
        )
        models_info = []
        for m in all_models:
            det = detailed_by_name.get(m, {})
            models_info.append(
                {
                    "model": m,
                    "context_window": get_model_context_window(m, configured_windows),
                    "installed": m in discovered,
                    "size_gb": det.get("size_gb", 0.0),
                    "digest": det.get("digest", ""),
                    "parameter_size": det.get("parameter_size", ""),
                    "quantization": det.get("quantization", ""),
                    "is_duplicate": bool(det.get("is_duplicate", False)),
                    "is_hf": bool(det.get("is_hf", m.startswith("hf.co/"))),
                }
            )
        # Compute live context occupancy telemetry for the active scope
        ctx_str, hist_msgs = build_chat_context(self.wiki_db, self.memory_curator, "", scope_id=scope_id)
        active_role = resolve_role_execution(orch_cfg, "chat" if scope_id == "chat" else "coordinator")
        active_model = active_role["model"]
        active_win = active_role["context_window"]
        scope_prefs_all = orch_cfg.get("scope_preferences") if isinstance(orch_cfg.get("scope_preferences"), dict) else {}
        cur_prefs = dict(scope_prefs_all.get(scope_id) or {})
        cur_prefs.setdefault("context_strategy", "auto")
        cur_prefs.setdefault("thinking_mode", "auto")
        fitted = fit_context_to_window(
            system_prompt="Cortical Mission Control",
            user_prompt="",
            extra_context=ctx_str,
            history_messages=hist_msgs,
            context_window_tokens=active_win,
            strategy_override=str(cur_prefs["context_strategy"]),
        )
        telemetry = dict(fitted["telemetry"])
        telemetry["active_model"] = active_model
        telemetry["scope_id"] = scope_id
        telemetry["thinking_mode"] = cur_prefs["thinking_mode"]
        return {
            "available_models": all_models,
            "models": models_info,
            "roles": roles,
            "role_models": role_models,
            "role_context_windows": role_context_windows,
            "role_efforts": role_efforts,
            "model_context_windows": {m["model"]: m["context_window"] for m in models_info},
            "presets": RECOMMENDED_MODEL_PRESETS,
            "context_telemetry": telemetry,
            "scope_preferences": cur_prefs,
        }

    def _update_models_config(self, ctx: AccessContext, body: dict[str, Any]) -> dict[str, Any]:
        orch_cfg = self.wiki_db.get_concept_config(ctx, "concept:orchestratore-multi-agente")
        updates: dict[str, Any] = {}
        roles = get_all_roles(orch_cfg)
        rm_in = body.get("role_models") if isinstance(body.get("role_models"), dict) else body
        for r in roles:
            rk = f"{r['id']}_model"
            val = str(rm_in.get(rk, "")).strip()
            if val:
                updates[rk] = val

        rcw_in = body.get("role_context_windows")
        if isinstance(rcw_in, dict):
            merged_rcw = dict(orch_cfg.get("role_context_windows") or {})
            for rid, w_val in rcw_in.items():
                rid_clean = str(rid or "").strip()
                if rid_clean:
                    merged_rcw[rid_clean] = clamp_context_window(w_val)
            updates["role_context_windows"] = merged_rcw

        reff_in = body.get("role_efforts")
        if isinstance(reff_in, dict):
            merged_eff = dict(orch_cfg.get("role_efforts") or {})
            for rid, e_val in reff_in.items():
                rid_clean = str(rid or "").strip()
                if rid_clean and str(e_val).strip().lower() in ("low", "medium", "high"):
                    merged_eff[rid_clean] = str(e_val).strip().lower()
            updates["role_efforts"] = merged_eff

        win_in = body.get("model_context_windows")
        if isinstance(win_in, dict):
            merged = dict(orch_cfg.get("model_context_windows") or {})
            for m_id, w_val in win_in.items():
                mid = str(m_id or "").strip()
                if mid:
                    merged[mid] = clamp_context_window(w_val)
            updates["model_context_windows"] = merged
            sync_pi_models_json(merged)

        if updates:
            self.wiki_db.update_concept_config(ctx, "concept:orchestratore-multi-agente", updates)
        return self._get_models_config_payload(ctx, scope_id=str(body.get("scope_id", "chat")))

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

        # Scoped Context Attachments (Files, Folders, Skills, Plugins, MCP — per-chat or per-task)
        if method == "GET" and path == "/api/context":
            scope_id = (query.get("scope_id") or [None])[0]
            catalog = self._discover_catalog()
            return (
                HTTPStatus.OK,
                {
                    "attachments": self.wiki_db.list_context_attachments(ctx, scope_id=scope_id),
                    "available_skills": [s["name"] for s in catalog["skills"]],
                    "available_plugins": [p["name"] for p in catalog["plugins"]] + [m["name"] for m in catalog["mcp_servers"]],
                    "catalog": catalog,
                },
            )

        if method == "GET" and path == "/api/fs/list":
            raw_p = (query.get("path") or [None])[0]
            return (HTTPStatus.OK, self._browse_fs(raw_p))

        if method == "POST" and path == "/api/context/import":
            try:
                att = self._import_context_item(
                    ctx,
                    scope_id=str(body.get("scope_id", "chat")),
                    item_type=str(body.get("item_type", "skill")),
                    item_ref=str(body.get("item_ref", "")),
                    depth_tier=str(body.get("depth_tier", "medium")),
                )
                return (HTTPStatus.OK, att)
            except ValueError as exc:
                return (HTTPStatus.BAD_REQUEST, {"error": str(exc)})

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

        if method == "POST" and path == "/api/graph/concept/promote":
            cid = str(body.get("concept_id", "")).strip()
            title = str(body.get("title") or cid).strip()
            summary = str(body.get("summary") or "").strip()
            category = str(body.get("category") or "custom").strip()
            if not cid:
                return (HTTPStatus.BAD_REQUEST, {"error": "concept_id required"})
            cfg_updates: dict[str, Any] = {"custom_label": title}
            if summary:
                cfg_updates["custom_summary"] = summary
            if body.get("config") and isinstance(body["config"], dict):
                cfg_updates.update(body["config"])
            self.wiki_db.update_concept_config(ctx, cid, cfg_updates)

            slug = re.sub(r"[^a-z0-9_-]+", "-", title.lower()).strip("-") or "concept-skill"
            skill_name = f"concept-{slug[:40]}"
            skill_dir = self.repo_root / ".agents" / "skills" / skill_name
            skill_dir.mkdir(parents=True, exist_ok=True)
            cfg_lines = "\n".join(f"- `{k}`: `{v}`" for k, v in cfg_updates.items())
            skill_md = (
                f"---\nname: {skill_name}\n"
                f"description: Global platform skill promoted from Cortical concept '{title}' ({category}).\n---\n\n"
                f"# {title}\n\n{summary or 'Concetto globale promosso a skill di piattaforma Cortical.'}\n\n"
                f"## Parametri Configurati\n{cfg_lines}\n"
            )
            skill_path = skill_dir / "SKILL.md"
            skill_path.write_text(skill_md, encoding="utf-8")
            self.wiki_db.update_concept_config(ctx, cid, {"promoted_skill": skill_name})
            return (
                HTTPStatus.OK,
                {
                    "status": "promoted",
                    "concept_id": cid,
                    "title": title,
                    "skill_name": skill_name,
                    "skill_path": str(skill_path),
                },
            )

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
            try:
                return (HTTPStatus.OK, self.memory_curator.prepare_task_closure(ep_id))
            except KeyError:
                sess = self.agent_mgr.get_session(ep_id)
                if sess is not None:
                    self.wiki_db.record_episode(
                        ctx,
                        episode_id=ep_id,
                        title=f"[{ep_id}] {str(sess.get('goal') or ep_id)[:52]}",
                        goal=str(sess.get("goal") or ep_id),
                        outcome_status="open",
                        learned_summary=str(sess.get("final_report") or ""),
                        skills_used=list(sess.get("skills") or []),
                    )
                    return (HTTPStatus.OK, self.memory_curator.prepare_task_closure(ep_id))
                return (HTTPStatus.NOT_FOUND, {"error": f"Task '{ep_id}' not found."})

        if method == "POST" and path == "/api/tasks/archive":
            ep_id = str(body.get("episode_id", ""))
            notes = str(body.get("user_closing_notes", ""))
            sess = self.agent_mgr.get_session(ep_id)
            if sess is not None:
                # Ensure row exists even if archiving a working/early task
                try:
                    self.memory_curator.prepare_task_closure(ep_id)
                except KeyError:
                    self.wiki_db.record_episode(
                        ctx,
                        episode_id=ep_id,
                        title=f"[{ep_id}] {str(sess.get('goal') or ep_id)[:52]}",
                        goal=str(sess.get("goal") or ep_id),
                        outcome_status="open",
                        learned_summary=str(sess.get("final_report") or ""),
                        skills_used=list(sess.get("skills") or []),
                    )
            synth = self.skill_hub.synthesize_task_discussion_3plus1(ep_id, notes)
            skill_eval = self.skill_hub.evaluate_and_compile_skill(ep_id, notes).to_dict()
            res = self.memory_curator.archive_task(ep_id, user_closing_notes=notes)
            if res.get("status") == "archived":
                self.agent_mgr.mark_archived(ep_id, str(res.get("archived_trace", "")))
            res["synthesis_3plus1"] = synth
            res["skill_evaluation"] = skill_eval
            return (HTTPStatus.OK, res)

        if method == "POST" and path == "/api/tasks/reopen":
            ep_id = str(body.get("episode_id", ""))
            mem_res = self.memory_curator.reopen_task(ep_id)
            ag_res = self.agent_mgr.reopen_session(ep_id)
            return (HTTPStatus.OK, {**mem_res, **ag_res})

        if method == "GET" and path == "/api/chats":
            chat_scope = (query.get("scope_id") or ["chat"])[0] or "chat"
            return (
                HTTPStatus.OK,
                {
                    "chats": self.memory_curator.list_chats(ctx=ctx),
                    "active_scope": chat_scope,
                    "messages": self.memory_curator.get_recent_chat(limit=30, ctx=ctx, scope_id=chat_scope),
                },
            )

        if method == "POST" and path == "/api/chats/create":
            title = str(body.get("title", "")).strip()
            created = self.memory_curator.create_chat(title=title, ctx=ctx)
            return (HTTPStatus.OK, {"chat": created, "chats": self.memory_curator.list_chats(ctx=ctx)})

        if method == "POST" and path == "/api/chats/delete":
            cid = str(body.get("chat_id", "")).strip() or "chat"
            res = self.memory_curator.delete_chat(cid, ctx=ctx)
            res["chats"] = self.memory_curator.list_chats(ctx=ctx)
            return (HTTPStatus.OK, res)

        if method == "POST" and path == "/api/tasks/continue":
            sid = str(body.get("session_id", "")).strip()
            prompt = str(body.get("prompt", "")).strip()
            depth = str(body.get("wiki_depth", "medium"))
            effort = _normalize_effort(body.get("effort", "medium"))
            speak = bool(body.get("speak", False) and self.audio_responses_enabled)
            parallel = body.get("parallel") if isinstance(body.get("parallel"), bool) else None
            auto_loop = body.get("auto_loop") if isinstance(body.get("auto_loop"), bool) else None
            sess = self.agent_mgr.continue_session(
                sid,
                prompt,
                wiki_depth=depth,
                speak_on_finish=speak,
                parallel=parallel,
                auto_loop=auto_loop,
                effort=effort,
            )
            if not sess:
                return (HTTPStatus.NOT_FOUND, {"error": f"Task session {sid} not found"})
            return (HTTPStatus.OK, sess)

        if method == "GET" and path == "/api/tokens/summary":
            ep_id = (query.get("episode_id") or [None])[0]
            return (HTTPStatus.OK, self.wiki_db.get_token_usage_summary(ctx, episode_id=ep_id))

        if method == "POST" and path == "/api/tasks/rename":
            ep_id = str(body.get("episode_id") or body.get("session_id") or "").strip()
            title = str(body.get("title") or "").strip()
            if not ep_id or not title:
                return (HTTPStatus.BAD_REQUEST, {"error": "Missing episode_id or title"})
            return (HTTPStatus.OK, self.agent_mgr.rename_session(ep_id, title))

        if method == "POST" and path == "/api/tasks/delete":
            ep_id = str(body.get("episode_id", ""))
            mem_res = self.memory_curator.delete_task(ep_id)
            ag_res = self.agent_mgr.delete_session(ep_id)
            return (HTTPStatus.OK, {**mem_res, "agent_session": ag_res})

        if method == "POST" and path == "/api/tasks/clear-archived":
            mem_res = self.memory_curator.clear_archived_tasks()
            ag_res = self.agent_mgr.clear_archived_sessions()
            return (HTTPStatus.OK, {**mem_res, **ag_res})

        if method == "GET" and path == "/api/platform/sources":
            sources = _scan_external_platform_skills(self.skill_hub.skills_root)
            return (HTTPStatus.OK, {"sources": sources, "target_dir": str(self.skill_hub.skills_root)})

        if method == "POST" and path == "/api/platform/import":
            req_name = str(body.get("name", "")).strip()
            req_path = str(body.get("path", "")).strip()
            sources = _scan_external_platform_skills(self.skill_hub.skills_root)
            match = None
            for s in sources:
                if (req_path and s["path"] == req_path) or (req_name and s["name"] == req_name):
                    match = s
                    break
            if not match:
                return (HTTPStatus.NOT_FOUND, {"error": f"Platform skill not found: {req_name or req_path}"})
            src_skill = Path(match["path"])
            dst_dir = self.skill_hub.skills_root / match["name"]
            dst_dir.mkdir(parents=True, exist_ok=True)
            content = src_skill.read_text(encoding="utf-8", errors="ignore")
            (dst_dir / "SKILL.md").write_text(content, encoding="utf-8")
            # Also register all 4 Second Brain tiers (L1, L2, L3, +1) into WikiDB
            lines = [ln.strip() for ln in content.splitlines() if ln.strip() and not ln.strip().startswith("---")]
            l1 = f"Skill {match['name']} ({match['platform']}): {match['description'] or (lines[0] if lines else match['name'])}"[:220]
            l2 = "\n".join(lines[:14])[:1200]
            l3 = content[:4000]
            chash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            wiki_path = f"/.agents/skills/{match['name']}/SKILL.md"
            self.wiki_db.upsert_merkle_node(
                ctx,
                path=wiki_path,
                parent_path=f"/.agents/skills/{match['name']}",
                node_type="file",
                content_hash=chash,
                subtree_hash=chash,
                summary_light=l1,
                summary_medium=l2,
                summary_high=l3,
                raw_content=content,
            )
            self.wiki_db.update_concept_config(
                ctx,
                f"skill:{match['name']}",
                {"platform": match["platform"], "source_path": match["path"], "wiki_path": wiki_path},
            )
            return (
                HTTPStatus.OK,
                {
                    "imported": True,
                    "name": match["name"],
                    "platform": match["platform"],
                    "target": str(dst_dir / "SKILL.md"),
                    "concept_id": f"skill:{match['name']}",
                },
            )

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

        # Voice Ducking, Audio Switch & Echo State Endpoints
        if method == "POST" and path == "/api/voice/config":
            if "speak_enabled" in body:
                self.audio_responses_enabled = bool(body.get("speak_enabled"))
                if not self.audio_responses_enabled:
                    stop_native_tts()
                    self.agent_mgr.clear_pending_speech()
            return (HTTPStatus.OK, {"speak_enabled": self.audio_responses_enabled})

        if method == "POST" and path == "/api/voice/duck":
            force_stop = bool(body.get("force_stop", False))
            return (HTTPStatus.OK, duck_native_tts(force_stop=force_stop))

        if method == "GET" and path == "/api/voice/state":
            return (
                HTTPStatus.OK,
                {
                    "speak_enabled": self.audio_responses_enabled,
                    "tts_speaking": is_tts_speaking(),
                    "tts_shield_active": is_tts_speaking_or_cooling_down(),
                    "last_spoken_text": self.voice_engine.last_spoken_text or _LAST_SPOKEN_TEXT,
                },
            )

        if method == "GET" and path == "/api/models/config":
            scope_id = (query.get("scope_id") or ["chat"])[0]
            return (HTTPStatus.OK, self._get_models_config_payload(ctx, scope_id=scope_id))

        if method == "POST" and path == "/api/models/config":
            return (HTTPStatus.OK, self._update_models_config(ctx, body))

        if method == "POST" and path == "/api/models/pull":
            model_name = str(body.get("model") or "").strip()
            res = pull_ollama_model(model_name, base_url=self.model_rec.active_base_url or "http://127.0.0.1:11434")
            status = HTTPStatus.OK if res.get("ok") else HTTPStatus.BAD_REQUEST
            if res.get("ok"):
                res["config"] = self._get_models_config_payload(ctx)
            return (status, res)

        if method == "POST" and path == "/api/models/delete":
            model_name = str(body.get("model") or "").strip()
            res = delete_ollama_model(model_name, base_url=self.model_rec.active_base_url or "http://127.0.0.1:11434")
            status = HTTPStatus.OK if res.get("ok") else HTTPStatus.BAD_REQUEST
            if res.get("ok"):
                res["config"] = self._get_models_config_payload(ctx)
            return (status, res)

        if method == "POST" and path == "/api/roles/add":
            orch_cfg = self.wiki_db.get_concept_config(ctx, "concept:orchestratore-multi-agente")
            try:
                updated_cfg = add_custom_role(
                    orch_cfg,
                    role_id=str(body.get("id") or ""),
                    label=str(body.get("label") or ""),
                    description=str(body.get("description") or ""),
                    model=str(body.get("model") or "qwen3.8:27b-iq2_xs"),
                    context_window=int(body.get("context_window") or 16384),
                    effort=str(body.get("effort") or "medium"),
                    tools=list(body.get("tools") or []),
                )
            except ValueError as exc:
                return (HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            self.wiki_db.update_concept_config(ctx, "concept:orchestratore-multi-agente", updated_cfg)
            return (HTTPStatus.OK, {"ok": True, "config": self._get_models_config_payload(ctx)})

        if method == "POST" and path == "/api/roles/delete":
            orch_cfg = self.wiki_db.get_concept_config(ctx, "concept:orchestratore-multi-agente")
            try:
                updated_cfg = delete_custom_role(orch_cfg, str(body.get("id") or ""))
            except ValueError as exc:
                return (HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            self.wiki_db.update_concept_config(ctx, "concept:orchestratore-multi-agente", updated_cfg)
            return (HTTPStatus.OK, {"ok": True, "config": self._get_models_config_payload(ctx)})

        if method == "GET" and path == "/api/chrome/profiles":
            return (HTTPStatus.OK, discover_chrome_profiles())

        if method == "POST" and path == "/api/chrome/profile":
            saved = save_chrome_profile_preference(body or {})
            return (HTTPStatus.OK, {"ok": True, "selected": saved, "discovery": discover_chrome_profiles()})

        if method == "GET" and path == "/api/agents":
            q_str = (query.get("q") or [""])[0]
            offset = int((query.get("offset") or ["0"])[0] or 0)
            limit = int((query.get("limit") or ["20"])[0] or 20)
            page = self.agent_mgr.search_sessions(query=q_str, offset=offset, limit=limit)
            ep_filter = (query.get("episode_id") or [None])[0]
            scope_id = ep_filter or (query.get("scope_id") or ["chat"])[0] or "chat"
            page["token_summary"] = self.wiki_db.get_token_usage_summary(ctx, episode_id=ep_filter)
            mcfg = self._get_models_config_payload(ctx, scope_id=scope_id)
            page["context_telemetry"] = mcfg["context_telemetry"]
            page["scope_preferences"] = mcfg["scope_preferences"]
            page["role_models"] = mcfg["role_models"]
            if ep_filter:
                page["selected_session"] = self.agent_mgr.get_session(ep_filter)
            return (HTTPStatus.OK, page)

        if method == "GET" and path == "/api/agents/runs":
            ep_filter = (query.get("episode_id") or [None])[0]
            status_f = (query.get("status") or ["all"])[0]
            q_str = (query.get("q") or [""])[0]
            offset = int((query.get("offset") or ["0"])[0] or 0)
            limit = min(50, max(1, int((query.get("limit") or ["12"])[0] or 12)))
            runs = self.wiki_db.list_agent_runs(
                ctx, episode_id=ep_filter, limit=limit, offset=offset, status_filter=status_f, search_query=q_str
            )
            total = self.wiki_db.count_agent_runs(ctx, episode_id=ep_filter, status_filter=status_f, search_query=q_str)
            return (
                HTTPStatus.OK,
                {"runs": runs, "total_count": total, "offset": offset, "limit": limit, "has_more": (offset + len(runs)) < total},
            )

        if method == "POST" and path == "/api/agents/run/stop":
            rid = str(body.get("run_id") or "").strip()
            sid = str(body.get("session_id") or "").strip() or None
            res = self.agent_mgr.stop_run(rid, session_id=sid)
            return (HTTPStatus.OK if res.get("stopped") else HTTPStatus.NOT_FOUND, res)

        if method == "POST" and path == "/api/chat/preferences":
            scope_id = str(body.get("scope_id") or "chat").strip() or "chat"
            orch_cfg = self.wiki_db.get_concept_config(ctx, "concept:orchestratore-multi-agente")
            prefs_all = dict(orch_cfg.get("scope_preferences") or {})
            cur = dict(prefs_all.get(scope_id) or {})
            if body.get("context_strategy") in {"auto", "direct", "multi_message", "summarize"}:
                cur["context_strategy"] = str(body["context_strategy"])
            if body.get("thinking_mode") in {"auto", "off", "low", "medium", "high"}:
                cur["thinking_mode"] = str(body["thinking_mode"])
            prefs_all[scope_id] = cur
            self.wiki_db.update_concept_config(ctx, "concept:orchestratore-multi-agente", {"scope_preferences": prefs_all})
            mcfg = self._get_models_config_payload(ctx, scope_id=scope_id)
            return (HTTPStatus.OK, {"ok": True, "scope_id": scope_id, "scope_preferences": mcfg["scope_preferences"], "context_telemetry": mcfg["context_telemetry"]})

        if method == "POST" and path == "/api/agents/spawn":
            goal = str(body.get("goal", "")).strip()
            depth = str(body.get("wiki_depth", "medium"))
            effort = _normalize_effort(body.get("effort", "medium"))
            speak = bool(body.get("speak", False) and self.audio_responses_enabled)
            source_scope = str(body.get("source_scope_id") or "").strip()
            parallel = body.get("parallel") if isinstance(body.get("parallel"), bool) else None
            auto_loop = body.get("auto_loop") if isinstance(body.get("auto_loop"), bool) else None
            sess = self.agent_mgr.spawn_agent(
                goal=goal,
                role="Coordinator",
                wiki_depth=depth,
                speak_on_finish=speak,
                parallel=parallel,
                auto_loop=auto_loop,
                effort=effort,
            )
            if source_scope:
                for ca in self.wiki_db.list_context_attachments(ctx, scope_id=source_scope):
                    try:
                        self.wiki_db.attach_context_item(
                            ctx,
                            scope_id=str(sess["session_id"]),
                            item_type=ca["item_type"],
                            item_ref=ca["item_ref"],
                            depth_tier=ca.get("depth_tier", "medium"),
                            label=ca.get("label"),
                        )
                    except Exception:  # noqa: BLE001
                        pass
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

        if method == "GET" and path == "/api/security/egress":
            sid = (query.get("session_id") or [""])[0]
            limit = int((query.get("limit") or ["50"])[0] or 50)
            events = self.perm_gate.list_egress_events(limit=limit, session_id=sid)
            return (
                HTTPStatus.OK,
                {
                    "isolation_enabled": True,
                    "proxy_port": self.agent_mgr.egress_proxy_port,
                    "total_blocked": len(events),
                    "events": events,
                },
            )

        if method == "POST" and path == "/api/security/egress":
            if str(body.get("action") or "") == "clear":
                cleared = self.perm_gate.clear_egress_events()
                return (HTTPStatus.OK, {"cleared": cleared})
            ev = self.perm_gate.record_egress_event(
                session_id=str(body.get("session_id") or ""),
                role=str(body.get("role") or ""),
                model=str(body.get("model") or ""),
                source=str(body.get("source") or "harness_gate"),
                method=str(body.get("method") or ""),
                target_host=str(body.get("target_host") or ""),
                target_url=str(body.get("target_url") or ""),
                payload_excerpt=str(body.get("payload_excerpt") or ""),
                verdict=str(body.get("verdict") or "blocked"),
                reason=str(body.get("reason") or "Blocked by Cortical isolation."),
            )
            return (HTTPStatus.OK, {"recorded": True, "event": ev})

        if method == "POST" and path == "/api/voice":
            utterance = str(body.get("utterance", ""))
            session_id = str(body.get("session_id") or "").strip()
            chat_scope = str(body.get("scope_id") or "chat").strip() or "chat"
            speak = bool(body.get("speak", False))
            if not self.audio_responses_enabled:
                speak = False
            client_audio = bool(body.get("client_audio", False))
            voice_name = str(body.get("voice", "IsabellaNeural"))
            from_mic = bool(body.get("from_mic", False))
            preferred_lang = str(body.get("lang", "")) or None
            wiki_depth = str(body.get("wiki_depth", "medium"))
            discourse_hints = body.get("discourse_hints") if isinstance(body.get("discourse_hints"), dict) else None
            tts_active = bool(body.get("client_tts_speaking", False)) or is_tts_speaking_or_cooling_down()
            t0 = time.perf_counter()

            # Follow-up sent inside an open/reopened task continues THAT task in its own scope
            # (unless the utterance is a barge-in stop command).
            is_stop_cmd = bool(re.search(r"\b(ferma|fermati|stop|basta|annulla)\b", utterance.lower()))
            if session_id and utterance.strip() and not is_stop_cmd:
                cont = self.agent_mgr.continue_session(
                    session_id,
                    utterance.strip(),
                    wiki_depth=wiki_depth,
                    speak_on_finish=speak,
                    effort=_normalize_effort(body.get("effort", "medium")),
                )
                if cont is not None:
                    eff_lang = preferred_lang if preferred_lang in ("it", "en") else detect_language(utterance)
                    msg = (
                        f"Continuing task {session_id} with local agent."
                        if eff_lang == "en"
                        else f"Continuo il task {session_id} con l'agente locale."
                    )
                    c_tts = False
                    c_audio_url = None
                    c_voice = voice_name
                    if speak:
                        if client_audio:
                            ab, mime, c_voice = synthesize_tts_audio_bytes(msg, voice=voice_name, lang=eff_lang)
                            if ab:
                                aid = cache_tts_audio(ab, mime)
                                c_audio_url = f"/api/tts/audio?id={aid}"
                                c_tts = True
                            else:
                                c_tts = speak_native_tts(msg, voice=voice_name, lang=eff_lang)
                        else:
                            c_tts = speak_native_tts(msg, voice=voice_name, lang=eff_lang)
                    return (
                        HTTPStatus.OK,
                        {
                            "route": "system2_task_continue",
                            "spoken_response": msg,
                            "lang": eff_lang,
                            "spawned_session_id": session_id,
                            "latency_ms": round((time.perf_counter() - t0) * 1000.0, 2),
                            "tts_triggered": c_tts,
                            "audio_url": c_audio_url,
                            "tts_voice_used": c_voice,
                        },
                    )

            prev_scope = getattr(self._current_chat_scope, "value", "chat")
            prev_speak = getattr(self._dispatch_speak_flag, "value", None)
            self._current_chat_scope.value = chat_scope
            self._dispatch_speak_flag.value = speak
            try:
                res = self.voice_engine.handle_utterance(
                    utterance,
                    from_mic=from_mic,
                    tts_currently_speaking=tts_active,
                    discourse_hints=discourse_hints,
                    preferred_lang=preferred_lang,
                    scope_id=chat_scope,
                )
            finally:
                self._current_chat_scope.value = prev_scope
                self._dispatch_speak_flag.value = prev_speak
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
                    new_sid = sessions[0]["session_id"]
                    out["spawned_session_id"] = new_sid
                    for ca in self.wiki_db.list_context_attachments(ctx, scope_id=chat_scope):
                        try:
                            self.wiki_db.attach_context_item(
                                ctx,
                                scope_id=new_sid,
                                item_type=ca["item_type"],
                                item_ref=ca["item_ref"],
                                depth_tier=ca.get("depth_tier", "medium"),
                                label=ca.get("label"),
                            )
                        except Exception:  # noqa: BLE001
                            pass
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
                html_path = Path(__file__).with_name("dashboard.html")
                data = html_path.read_bytes() if html_path.is_file() else DASHBOARD_HTML.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)
                return

            if parsed.path.startswith("/ui/"):
                asset = resolve_ui_asset(parsed.path)
                if not asset:
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": "UI asset not found"})
                    return
                asset_bytes, mime = asset
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(asset_bytes)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(asset_bytes)
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
            try:
                status, payload = service.handle_api("GET", parsed.path, q, {})
                self._send_json(status, payload)
            except KeyError as exc:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
            except Exception as exc:  # noqa: BLE001
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

        def do_POST(self) -> None:  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
            try:
                body = json.loads(raw) if raw.strip() else {}
                q = urllib.parse.parse_qs(parsed.query)
                status, payload = service.handle_api("POST", parsed.path, q, body)
                self._send_json(status, payload)
            except KeyError as exc:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
            except Exception as exc:  # noqa: BLE001
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

        def _send_json(self, status: int, payload: dict[str, Any]) -> None:
            data = json.dumps(payload, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return

    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"Cortical Mission Control listening on http://{host}:{port}")
    httpd.serve_forever()
