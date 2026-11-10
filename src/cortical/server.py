"""Cortical Mission Control — Live `pi` Agentic IDE, 4-Tier Second Brain & Italian Voice Server.

Provides:
1. Claude Code / Codex / Antigravity-style Mission Control UI at `http://127.0.0.1:8765/`
2. Authentic Italian TTS (`say -v Alice` on macOS, `piper` `it_IT-paola-medium` on Linux)
   with instant physical barge-in termination (`stop_native_tts`).
3. Always-On Wake-Word Voice Router (`"Hei/Ehi/Hey Cortical"`) with <5ms built-in Italian
   reflexes (clock, date, status) + multi-endpoint local LLM fallback (`:11434` Ollama,
   `:8080` local/LAN `llama-server`).
4. Live `pi` Agent & Subagent Spawner (`/api/agents/spawn`, `/api/agents`, `/api/agents/open-terminal`)
   streaming real-time tool calls, thinking steps, Wiki navigations, and permission gates.
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

from .hardware.profiler import HardwareProfiler
from .permissions.gate import AdaptivePermissionGate
from .voice.engine import CorticalVoiceEngine, is_stop_command, strip_wake_word
from .wiki.db import AccessContext, CorticalWikiDB, DepthTier
from .wiki.fact_check import CitationVerifier

_ACTIVE_TTS_LOCK = threading.Lock()
_ACTIVE_TTS_PROC: Optional[subprocess.Popen[bytes]] = None


def stop_native_tts() -> None:
    """Immediately terminates any active TTS process for instant barge-in (<20ms)."""
    global _ACTIVE_TTS_PROC
    with _ACTIVE_TTS_LOCK:
        if _ACTIVE_TTS_PROC is not None:
            try:
                _ACTIVE_TTS_PROC.terminate()
            except Exception:  # noqa: BLE001
                pass
            _ACTIVE_TTS_PROC = None
    if platform.system() == "Darwin":
        subprocess.run(["pkill", "-x", "say"], stderr=subprocess.DEVNULL, check=False)


def speak_native_tts(text: str, voice: str = "Alice", rate: int = 188) -> bool:
    """Speaks Italian text using native macOS Italian voice (`Alice`) or Linux Piper (`paola`)."""
    global _ACTIVE_TTS_PROC
    if not text or not text.strip():
        return False
    stop_native_tts()
    try:
        sys_name = platform.system()
        if sys_name == "Darwin" and shutil.which("say"):
            allowed_voices = {"Alice", "Reed", "Shelley", "Eddy", "Sandy", "Flo", "Federica", "Luca"}
            chosen_voice = voice if voice in allowed_voices else "Alice"
            with _ACTIVE_TTS_LOCK:
                _ACTIVE_TTS_PROC = subprocess.Popen(
                    ["say", "-v", chosen_voice, "-r", str(rate), text],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            return True

        if sys_name == "Linux":
            # Check for Piper Italian model first (like on the Linux laptop)
            piper_bin = shutil.which("piper") or "/home/bianco/.local/bin/piper"
            paola_model = Path.home() / ".local/share/local-ai/models/piper/it_IT-paola-medium.onnx"
            if Path(piper_bin).exists() and paola_model.exists() and shutil.which("aplay"):
                cmd = f'printf %s {json.dumps(text)} | "{piper_bin}" --model "{paola_model}" --output-raw | aplay -r 22050 -f S16_LE -t raw - >/dev/null 2>&1'
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
                        ["spd-say", "-l", "it", text],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                return True
    except Exception:  # noqa: BLE001
        pass
    return False


def query_local_reflex_llm(prompt: str, base_url: str, timeout: float = 4.5) -> str:
    """Queries available local/LAN OpenAI-compatible servers in Italian, rejecting English deprecation notices."""
    now = datetime.datetime.now()
    norm = prompt.lower().strip()

    # 1. Instant deterministic Italian reflexes (< 2ms)
    if any(k in norm for k in ("che ore sono", "che ora e", "che ora è", "dimmi l ora", "orario")):
        return f"Sono le {now.strftime('%H:%M')}."
    if any(k in norm for k in ("che giorno", "data di oggi", "quanti ne abbiamo")):
        giorni = ("lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica")
        mesi = ("", "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre")
        return f"Oggi è {giorni[now.weekday()]} {now.day} {mesi[now.month]} {now.year}."
    if any(k in norm for k in ("chi sei", "cosa fai", "presentati")):
        return (
            "Sono Cortical, il tuo assistente agentico locale. "
            "Uso la Wiki Merkle a 4 livelli per la memoria e coordino gli agenti su pi."
        )
    if any(k in norm for k in ("come stai", "tutto bene", "mi senti")):
        return "Tutto perfetto! Ti sento forte e chiaro in italiano."

    # 2. Candidate LLM endpoints (Local llama-server :8080, Local Ollama :11434, LAN laptop :8080)
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
                        f"Ora locale: {now.strftime('%H:%M')}. Rispondi SEMPRE e SOLO in italiano, in massimo 2 frasi chiare."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 110,
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

    return f"Ho ricevuto la richiesta: '{prompt}'. Puoi anche delegarla come task agli agenti pi."


class PiAgentManager:
    """Manages live `pi` coding agents and subagent loops with step-by-step telemetry."""

    def __init__(
        self,
        repo_root: Path,
        wiki_db: CorticalWikiDB,
        perm_gate: AdaptivePermissionGate,
        base_url_fn: Any,
    ) -> None:
        self.repo_root = repo_root
        self.wiki_db = wiki_db
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
                "type": step_type,  # 'thinking' | 'tool_call' | 'subagent' | 'output' | 'permission' | 'system'
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
            # Step 1: Load 4-Tier Merkle Second Brain context deterministically
            self._append_step(
                session_id,
                "thinking",
                f"Inizializzazione Orchestratore `pi` (Wiki Depth: {wiki_depth.upper()}, Skills: {', '.join(skills)})",
                f"Obiettivo assegnato: {goal}",
            )
            time.sleep(0.15)

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

            # Step 2: Search relevant files in FTS5 Second Brain
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

            # Step 3: Adaptive Permission Gate check
            perm_dec = self.perm_gate.evaluate("wiki_navigate", {"path": "/", "depth": wiki_depth})
            self._append_step(
                session_id,
                "permission",
                f"Adaptive Permission Gate → {perm_dec.verdict.upper()} (risk={perm_dec.risk_score})",
                f"Pattern: {perm_dec.normalized_pattern} — {perm_dec.reason}",
            )

            # Step 4: Try invoking real `pi --mode json -p` if configured, or synthesize with local LLM
            pi_bin = shutil.which("pi")
            pi_output_text = ""
            if pi_bin:
                self._append_step(
                    session_id,
                    "subagent",
                    "delegate_subagent(harness='pi --mode json', extension='.pi/extensions/cortical-harness.ts')",
                    f"Esecuzione sessione `pi` in {self.repo_root}...",
                )
                try:
                    pi_cmd = [
                        pi_bin,
                        "--mode",
                        "json",
                        "-p",
                        "--no-session",
                    ]
                    if ":11434" in self.base_url_fn():
                        pi_cmd.extend(["--provider", "ollama", "--model", "qwen2.5:1.5b"])
                    pi_cmd.extend(
                        [
                            "-e",
                            str(self.repo_root / ".pi/extensions/cortical-harness.ts"),
                            goal,
                        ]
                    )
                    proc = subprocess.Popen(
                        pi_cmd,
                        cwd=str(self.repo_root),
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                    with self._lock:
                        self.processes[session_id] = proc
                    out, _ = proc.communicate(timeout=12)
                    for line in out.splitlines():
                        if not line.strip().startswith("{"):
                            continue
                        ev = json.loads(line)
                        ev_type = ev.get("type", "")
                        if ev_type == "tool_call":
                            self._append_step(
                                session_id,
                                "tool_call",
                                f"pi tool_call: {ev.get('name', 'tool')}",
                                json.dumps(ev.get("args", {}), indent=2),
                            )
                        elif ev_type == "message_end":
                            msg = ev.get("message") or {}
                            if msg.get("role") == "assistant" and not msg.get("errorMessage"):
                                parts = msg.get("content") or []
                                for p in parts:
                                    if isinstance(p, dict) and p.get("text"):
                                        pi_output_text += p["text"] + "\n"
                except Exception:  # noqa: BLE001
                    pass
                finally:
                    with self._lock:
                        self.processes.pop(session_id, None)

            if not pi_output_text.strip():
                context_snippet = "\n".join(h["content"][:250] for h in hits[:2]) if hits else root_nav["content"]
                synthesis_prompt = (
                    f"Obiettivo: {goal}\n"
                    f"Contesto dalla Wiki Cortical (livello {wiki_depth}): {context_snippet[:600]}\n"
                    "Fornisci un report tecnico strutturato e conciso in italiano."
                )
                pi_output_text = query_local_reflex_llm(
                    synthesis_prompt, self.base_url_fn(), timeout=8.0
                )

            # Step 5: Consolidate learned episode into High-Level Macro-Graph
            touched = [h["path"] for h in hits] if hits else ["/"]
            self.wiki_db.record_episode(
                ctx,
                episode_id=session_id,
                title=f"[{ session_id }] {goal[:52]}",
                goal=goal,
                outcome_status="completed",
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
            self._append_step(
                session_id,
                "output",
                "submit_report(status='completed') + Consolidamento nel Macro-Grafo",
                pi_output_text,
            )

            with self._lock:
                if self.sessions[session_id]["status"] == "working":
                    self.sessions[session_id]["status"] = "completed"
                    self.sessions[session_id]["final_report"] = pi_output_text

            if speak_on_finish:
                speak_native_tts(f"Compito completato. {pi_output_text[:180]}")

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
    /* Top Mission Control Bar */
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
    /* Main 3-Pane Workspace */
    .workspace {
      flex: 1; display: grid;
      grid-template-columns: 300px 1fr 360px;
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
    /* Agent Roster Cards */
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
    .status-stopped, .status-error { background: rgba(248, 113, 113, 0.2); color: var(--rose); }
    /* Center Timeline (Claude Code / Antigravity style) */
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
    /* Bottom Composer */
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
    .tabs { display: flex; gap: 4px; }
    .tab {
      padding: 4px 9px; border-radius: 6px; font-size: 0.72rem; cursor: pointer;
      background: #0b1120; color: var(--muted); border: 1px solid var(--border);
    }
    .tab.active { background: var(--accent-glow); color: var(--accent); border-color: var(--accent); }
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

    <!-- ALWAYS-ON VOICE CONTROL BAR -->
    <div class="voice-bar">
      <div class="pulse-dot" id="mic-dot"></div>
      <span class="live-transcript" id="live-transcript">Premi "Ascolto Continuo" e di' "Hei Cortical, che ore sono?"</span>
      <button class="btn" id="btn-always-on" onclick="toggleAlwaysOnMic()">🎤 Ascolto Continuo: OFF</button>
      <select id="tts-voice" title="Voce Italiana">
        <option value="Alice">🇮🇹 Voce: Alice (Nativa)</option>
        <option value="Reed">🇮🇹 Voce: Reed (Ita)</option>
        <option value="Shelley">🇮🇹 Voce: Shelley (Ita)</option>
        <option value="Eddy">🇮🇹 Voce: Eddy (Ita)</option>
      </select>
      <button class="btn btn-danger" onclick="triggerStopBargeIn()" title="Ferma immediatamente voce e agenti">🛑 BASTA / STOP</button>
    </div>

    <div style="display:flex; gap:8px;">
      <button class="btn btn-ghost" onclick="openNativePiTerminal()">🖥️ Apri `pi` in Terminale</button>
    </div>
  </div>

  <!-- 3-PANE IDE WORKSPACE -->
  <div class="workspace">
    <!-- LEFT PANE: AGENT ROSTER & 4-TIER WIKI TREE -->
    <div class="pane">
      <div class="pane-header">
        <span>Agenti `pi` & Subagenti</span>
        <button class="btn" style="padding:3px 8px; font-size:0.72rem;" onclick="spawnQuickAgent()">+ Nuovo Task</button>
      </div>
      <div class="pane-body" id="agent-roster" style="max-height: 46%;">
        <div style="color:var(--muted); font-size:0.8rem;">Nessun agente avviato. Scrivi un obiettivo sotto o parla al microfono.</div>
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

    <!-- CENTER PANE: LIVE AGENT EXECUTION STREAM (CLAUDE CODE / ANTIGRAVITY STYLE) -->
    <div class="pane">
      <div class="pane-header">
        <span id="stream-title">Live Execution Stream — System 1 (Voce) & System 2 (`pi` Subagents)</span>
        <span style="font-family:var(--mono); font-size:0.72rem; color:var(--accent);" id="active-session-badge">READY</span>
      </div>
      <div class="pane-body" id="agent-stream">
        <div class="step-card output">
          <div class="step-meta"><span>CORTICAL READY</span><span>System 1 + System 2</span></div>
          <div class="step-title">Benvenuto in Cortical Mission Control</div>
          <pre class="step-detail">• Voce Italiana Nativa (Alice it_IT / Piper Paola) configurata.
• Per parlare a mani libere: clicca "🎤 Ascolto Continuo" in alto e di':
  - "Hei Cortical, che ore sono?" (System 1: risposta istantanea < 5ms)
  - "Hei Cortical, analizza il progetto e aggiorna la wiki" (System 2: avvia un agente `pi` qui sotto)
  - "Hei Cortical, basta" (Barge-in: ferma subito voce e agenti)</pre>
        </div>
      </div>

      <!-- PROMPT COMPOSER -->
      <div class="composer">
        <div class="composer-row">
          <select id="dispatch-mode">
            <option value="auto">⚡ Auto (System 1 Voce / System 2 Agente `pi`)</option>
            <option value="agent">🤖 Forza Agente `pi` (Con Steps & Wiki)</option>
            <option value="voice">🔊 Risposta Rapida Vocale (System 1)</option>
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
          <input id="prompt-input" placeholder="Scrivi un comando o parla al microfono (es: 'Hei Cortical, che ore sono?' o 'Analizza l'architettura della Wiki')..." onkeydown="if(event.key==='Enter') submitComposer()" />
          <button class="btn" onclick="submitComposer()">Esegui ↵</button>
        </div>
      </div>
    </div>

    <!-- RIGHT PANE: INSPECTOR (WIKI CONTENT / PERMISSIONS / MACRO-GRAPH) -->
    <div class="pane">
      <div class="pane-header">
        <span>Inspector</span>
        <div class="tabs">
          <span class="tab active" id="tab-wiki" onclick="switchInspector('wiki')">Wiki Node</span>
          <span class="tab" id="tab-perm" onclick="switchInspector('perm')">Permessi</span>
          <span class="tab" id="tab-graph" onclick="switchInspector('graph')">Macro-Grafo</span>
        </div>
      </div>
      <div class="pane-body">
        <!-- Wiki Inspector -->
        <div id="insp-wiki">
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

        <!-- Macro-Graph Inspector -->
        <div id="insp-graph" style="display:none;">
          <div style="display:flex; gap:6px; margin-bottom:10px;">
            <button class="btn btn-ghost" onclick="loadMacroGraph()">🔄 Aggiorna Macro-Grafo</button>
            <button class="btn btn-ghost" onclick="testFactCheck()">✅ Verifica Citazione NLI</button>
          </div>
          <pre class="step-detail" id="graph-view" style="max-height: calc(100vh - 180px);"></pre>
        </div>
      </div>
    </div>
  </div>

  <script>
    let currentWikiPath = '/';
    let selectedSessionId = null;
    let alwaysOnActive = false;
    let recognition = null;

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
      const text = (overrideText !== undefined ? overrideText : input.value).trim();
      if (!text) return;
      if (overrideText === undefined) input.value = '';

      const mode = document.getElementById('dispatch-mode').value;
      const depth = document.getElementById('agent-depth').value;
      const speak = document.getElementById('chk-speak').checked;
      const voice = document.getElementById('tts-voice').value;

      if (mode === 'agent') {
        await spawnAgentSession(text, depth, speak);
        return;
      }

      // Send through Dual-Path Voice & Intent Router
      const r = await fetch('/api/voice', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({utterance: text, speak, voice, wiki_depth: depth})
      });
      const d = await r.json();

      if (d.spawned_session_id) {
        selectedSessionId = d.spawned_session_id;
        await refreshAgents();
      } else {
        appendStreamCard(
          d.route === 'stop' ? 'permission' : 'output',
          `VOICE ROUTER → ${d.route.toUpperCase()}`,
          `${d.latency_ms} ms`,
          `Tu: "${text}"`,
          `Cortical: ${d.spoken_response}`
        );
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
    }

    function spawnQuickAgent() {
      const goal = prompt("Inserisci l'obiettivo per il nuovo agente pi:", "Analizza la struttura del repository e riassumi i moduli principali");
      if (goal) spawnAgentSession(goal, document.getElementById('agent-depth').value, true);
    }

    async function refreshAgents() {
      const r = await fetch('/api/agents');
      const data = await r.json();
      const sessions = data.sessions || [];
      const roster = document.getElementById('agent-roster');
      if (!sessions.length) return;

      if (!selectedSessionId) selectedSessionId = sessions[0].session_id;
      roster.innerHTML = sessions.map(s => `
        <div class="agent-item ${s.session_id === selectedSessionId ? 'active' : ''}" onclick="selectSession('${s.session_id}')">
          <div class="agent-item-top">
            <span>🤖 ${s.session_id}</span>
            <span class="status-pill status-${s.status}">${s.status}</span>
          </div>
          <div style="font-size:0.78rem; color:#cbd5e1; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
            ${s.goal}
          </div>
          <div style="font-size:0.7rem; color:var(--muted); margin-top:4px; font-family:var(--mono);">
            Wiki: ${s.wiki_depth.toUpperCase()} · Steps: ${s.steps.length}
          </div>
        </div>
      `).join('');

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

    function selectSession(sid) {
      selectedSessionId = sid;
      refreshAgents();
    }

    async function triggerStopBargeIn() {
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

    // Continuous Always-On Wake-Word Microphone (it-IT)
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
      document.getElementById('btn-always-on').textContent = '🟢 Ascolto Attivo (Ita)';
      document.getElementById('live-transcript').textContent = 'In ascolto in italiano... Di\\' "Hei Cortical, che ore sono?"';

      recognition = new SR();
      recognition.lang = 'it-IT';
      recognition.continuous = true;
      recognition.interimResults = true;

      recognition.onresult = (event) => {
        let interim = '';
        for (let i = event.resultIndex; i < event.results.length; ++i) {
          const transcript = event.results[i][0].transcript.trim();
          if (event.results[i].isFinal) {
            document.getElementById('live-transcript').textContent = `🗣️ "${transcript}"`;
            submitComposer(transcript);
          } else {
            interim += transcript + ' ';
          }
        }
        if (interim) {
          document.getElementById('live-transcript').textContent = `… ${interim}`;
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
      ['wiki', 'perm', 'graph'].forEach(t => {
        document.getElementById(`insp-${t}`).style.display = (t === tab) ? 'block' : 'none';
        document.getElementById(`tab-${t}`).classList.toggle('active', t === tab);
      });
      if (tab === 'graph') loadMacroGraph();
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

    async function loadMacroGraph() {
      const r = await fetch('/api/wiki/macro-graph');
      document.getElementById('graph-view').textContent = JSON.stringify(await r.json(), null, 2);
    }

    async function testFactCheck() {
      const r = await fetch('/api/wiki/verify', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          claim_text: 'Cortical uses a 4-tier deterministic Merkle tree with light, medium, high, and max levels.',
          source_path: '/README.md',
          quoted_span: '4-Tier Deterministic Merkle Tree'
        })
      });
      document.getElementById('graph-view').textContent = JSON.stringify(await r.json(), null, 2);
    }

    loadHealth();
    navigateWiki('/');
    setInterval(refreshAgents, 1500);
  </script>
</body>
</html>
"""


class CorticalLiveService:
    """Holds shared state for the live Cortical Mission Control HTTP, `pi` Agent & Voice server."""

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

        self.agent_mgr = PiAgentManager(
            repo_root=self.repo_root,
            wiki_db=self.wiki_db,
            perm_gate=self.perm_gate,
            base_url_fn=lambda: self.model_rec.active_base_url,
        )

        def _reflex(prompt: str) -> str:
            return query_local_reflex_llm(prompt, self.model_rec.active_base_url)

        def _dispatch_agentic(goal: str) -> str:
            sess = self.agent_mgr.spawn_agent(goal=goal, wiki_depth="medium", speak_on_finish=True)
            return str(sess["session_id"])

        def _on_stop() -> None:
            stop_native_tts()
            self.agent_mgr.stop_all()

        self.voice_engine = CorticalVoiceEngine(
            wiki_db=self.wiki_db,
            permission_gate=self.perm_gate,
            reflex_llm_fn=_reflex,
            agentic_dispatch_fn=_dispatch_agentic,
            stop_callback=_on_stop,
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
            tts_engine = "macOS say (Alice it_IT)" if self.hw_profile.os_name == "Darwin" else "Piper Neural (it_IT-paola)"
            return (
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "service": "cortical-live",
                    "version": "0.1.0",
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
            voice_name = str(body.get("voice", "Alice"))
            t0 = time.perf_counter()
            res = self.voice_engine.handle_utterance(utterance)
            elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            tts_triggered = speak_native_tts(res.spoken_response, voice=voice_name) if speak else False
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
