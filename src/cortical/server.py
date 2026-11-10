"""Cortical Live HTTP, Voice & Second Brain Service (`cortical serve`).

Provides:
1. Interactive Live Web & Voice Console at `http://127.0.0.1:8765/`
2. Live REST API for:
   - `GET  /health`
   - `POST /api/voice` (System 1 Fast Reflex via local LLM `:8080`/`:11434` + System 2 Agentic + native TTS)
   - `GET  /api/wiki/navigate?path=/&depth=light`
   - `GET  /api/wiki/search?q=...&depth=medium`
   - `POST /api/wiki/verify`
   - `GET  /api/wiki/macro-graph`
   - `POST /api/permissions/evaluate`
   - `POST /api/permissions/feedback`
"""

from __future__ import annotations

import dataclasses
import json
import platform
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional

from .hardware.profiler import HardwareProfiler
from .permissions.gate import AdaptivePermissionGate
from .voice.engine import CorticalVoiceEngine
from .wiki.db import AccessContext, CorticalWikiDB, DepthTier
from .wiki.fact_check import CitationVerifier

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Cortical — Live Agentic Harness, 4-Tier Second Brain & Voice Console</title>
  <style>
    :root {
      --bg: #0b0f19;
      --panel: #131b2e;
      --border: #243252;
      --accent: #38bdf8;
      --accent2: #818cf8;
      --ok: #34d399;
      --warn: #fbbf24;
      --err: #f87171;
      --text: #e2e8f0;
      --muted: #94a3b8;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0; padding: 24px;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg); color: var(--text);
    }
    header {
      display: flex; justify-content: space-between; align-items: center;
      border-bottom: 1px solid var(--border); padding-bottom: 16px; margin-bottom: 24px;
    }
    h1 { margin: 0; font-size: 1.5rem; letter-spacing: -0.02em; }
    .badge {
      background: rgba(56, 189, 248, 0.15); color: var(--accent);
      border: 1px solid var(--accent); border-radius: 999px;
      padding: 4px 12px; font-size: 0.8rem; font-weight: 600;
    }
    .grid {
      display: grid; grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));
      gap: 20px;
    }
    .card {
      background: var(--panel); border: 1px solid var(--border);
      border-radius: 12px; padding: 18px;
    }
    .card h2 { margin-top: 0; font-size: 1.05rem; color: var(--accent); }
    .row { display: flex; gap: 8px; margin-bottom: 10px; }
    input, select, button {
      background: #0f172a; color: var(--text); border: 1px solid var(--border);
      border-radius: 8px; padding: 8px 12px; font-size: 0.9rem;
    }
    input { flex: 1; }
    button {
      background: linear-gradient(135deg, var(--accent), var(--accent2));
      color: #0b0f19; font-weight: 700; cursor: pointer; border: none;
    }
    button.secondary {
      background: #1e293b; color: var(--text); border: 1px solid var(--border);
    }
    pre {
      background: #070a12; border: 1px solid var(--border); border-radius: 8px;
      padding: 12px; overflow: auto; max-height: 280px; font-size: 0.8rem;
      color: #cbd5e1; margin: 0;
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>Cortical — Live Second Brain, Adaptive Gate & Dual-Path Voice</h1>
      <div style="color: var(--muted); font-size: 0.85rem; margin-top: 4px;">
        Apache-2.0 · Author: Carlo Cancellieri · <span id="hw-info">Loading hardware profile...</span>
      </div>
    </div>
    <span class="badge" id="status-badge">ONLINE</span>
  </header>

  <div class="grid">
    <!-- 1. Voice & Orchestrator Console -->
    <div class="card">
      <h2>1. Dual-Path Voice & Orchestrator Console (System 1 + System 2)</h2>
      <div class="row">
        <input id="voice-input" placeholder="Es: 'Ehi Cortical, che ore sono?' oppure 'Orchestra un sottoagente...'" />
        <button onclick="sendVoice(false)">Invia</button>
        <button class="secondary" onclick="sendVoice(true)" title="Pronuncia ad alta voce (TTS)">🔊 Parla</button>
        <button class="secondary" onclick="startMic()" title="Usa microfono browser">🎤 Mic</button>
      </div>
      <div class="row">
        <button class="secondary" onclick="quickVoice('Ehi Cortical basta')">🛑 Stop / Barge-in</button>
        <button class="secondary" onclick="quickVoice('Cortical, a che punto sono gli agenti?')">📊 Stato Subagenti</button>
        <button class="secondary" onclick="quickVoice('Ehi Cortical, approva e ricorda sempre')">✅ Approva Permesso</button>
      </div>
      <pre id="voice-out">Pronto per i test live.</pre>
    </div>

    <!-- 2. 4-Tier Merkle Second Brain -->
    <div class="card">
      <h2>2. Deterministic 4-Tier Merkle Wiki (light / medium / high / max)</h2>
      <div class="row">
        <input id="wiki-path" value="/" placeholder="Percorso nodo (es. / o /README.md)" />
        <select id="wiki-depth">
          <option value="light">light (~50 tok)</option>
          <option value="medium">medium (~250 tok)</option>
          <option value="high">high (~1000 tok)</option>
          <option value="max">max (Full Raw)</option>
        </select>
        <button onclick="navigateWiki()">Naviga</button>
      </div>
      <div class="row">
        <input id="wiki-query" placeholder="Ricerca FTS5 con filtro RBAC..." />
        <button class="secondary" onclick="searchWiki()">Cerca</button>
      </div>
      <pre id="wiki-out">Seleziona un nodo o effettua una ricerca.</pre>
    </div>

    <!-- 3. Adaptive Permission Gate -->
    <div class="card">
      <h2>3. Adaptive Permission Gate & Hard Guardrails</h2>
      <div class="row">
        <select id="perm-tool">
          <option value="bash">bash</option>
          <option value="write_file">write_file</option>
          <option value="chrome">chrome-devtools-mcp</option>
        </select>
        <input id="perm-cmd" value="pytest tests/" placeholder="Comando o argomento..." />
        <button onclick="evalPerm()">Valuta</button>
      </div>
      <div class="row">
        <button class="secondary" onclick="feedbackPerm(true)">👍 Approva & Impara</button>
        <button class="secondary" onclick="feedbackPerm(false)">👎 Nega</button>
        <button class="secondary" onclick="testHardBlock()">🛡️ Test Hard Block (rm -rf /)</button>
      </div>
      <pre id="perm-out">Testa il Risk Score dinamico e l'apprendimento dei permessi.</pre>
    </div>

    <!-- 4. High-Level Episode Macro-Graph & Fact Checker -->
    <div class="card">
      <h2>4. Macro-Graph Episodico & NLI Fact-Checker</h2>
      <div class="row">
        <button onclick="loadMacroGraph()">🔗 Mostra Macro-Grafo Task</button>
        <button class="secondary" onclick="testFactCheck()">🔍 Test Verifica Citazione NLI</button>
      </div>
      <pre id="graph-out">Caricamento grafo...</pre>
    </div>
  </div>

  <script>
    async function loadHealth() {
      const r = await fetch('/health');
      const d = await r.json();
      document.getElementById('hw-info').textContent =
        `${d.os_name} (${d.arch}) · Tier: ${d.tier} · LLM: ${d.active_base_url}`;
    }
    async function sendVoice(speak) {
      const text = document.getElementById('voice-input').value;
      const r = await fetch('/api/voice', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({utterance: text, speak})
      });
      document.getElementById('voice-out').textContent = JSON.stringify(await r.json(), null, 2);
    }
    function quickVoice(t) {
      document.getElementById('voice-input').value = t;
      sendVoice(false);
    }
    function startMic() {
      const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!SR) { alert('Web Speech API non supportata in questo browser'); return; }
      const rec = new SR();
      rec.lang = 'it-IT';
      rec.onresult = (e) => {
        document.getElementById('voice-input').value = e.results[0][0].transcript;
        sendVoice(true);
      };
      rec.start();
    }
    async function navigateWiki() {
      const p = encodeURIComponent(document.getElementById('wiki-path').value || '/');
      const d = document.getElementById('wiki-depth').value;
      const r = await fetch(`/api/wiki/navigate?path=${p}&depth=${d}`);
      document.getElementById('wiki-out').textContent = JSON.stringify(await r.json(), null, 2);
    }
    async function searchWiki() {
      const q = encodeURIComponent(document.getElementById('wiki-query').value);
      const d = document.getElementById('wiki-depth').value;
      const r = await fetch(`/api/wiki/search?q=${q}&depth=${d}`);
      document.getElementById('wiki-out').textContent = JSON.stringify(await r.json(), null, 2);
    }
    async function evalPerm() {
      const tool = document.getElementById('perm-tool').value;
      const cmd = document.getElementById('perm-cmd').value;
      const r = await fetch('/api/permissions/evaluate', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({tool, args: {command: cmd, path: cmd}})
      });
      document.getElementById('perm-out').textContent = JSON.stringify(await r.json(), null, 2);
    }
    async function feedbackPerm(approved) {
      const tool = document.getElementById('perm-tool').value;
      const cmd = document.getElementById('perm-cmd').value;
      const r = await fetch('/api/permissions/feedback', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({tool, args: {command: cmd, path: cmd}, approved, remember: true})
      });
      document.getElementById('perm-out').textContent = JSON.stringify(await r.json(), null, 2);
    }
    function testHardBlock() {
      document.getElementById('perm-tool').value = 'bash';
      document.getElementById('perm-cmd').value = 'rm -rf /';
      evalPerm();
    }
    async function loadMacroGraph() {
      const r = await fetch('/api/wiki/macro-graph');
      document.getElementById('graph-out').textContent = JSON.stringify(await r.json(), null, 2);
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
      document.getElementById('graph-out').textContent = JSON.stringify(await r.json(), null, 2);
    }
    loadHealth();
    navigateWiki();
    loadMacroGraph();
  </script>
</body>
</html>
"""


def speak_native_tts(text: str) -> bool:
    """Non-blocking cross-platform local TTS (`say` on macOS, `espeak-ng`/`spd-say` fallback on Linux)."""
    try:
        sys_name = platform.system()
        if sys_name == "Darwin" and shutil.which("say"):
            subprocess.Popen(
                ["say", text],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        if sys_name == "Linux" and shutil.which("spd-say"):
            subprocess.Popen(
                ["spd-say", "-l", "it", text],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
    except Exception:  # noqa: BLE001
        pass
    return False


def query_local_reflex_llm(prompt: str, base_url: str, timeout: float = 4.0) -> str:
    """Queries the discovered local OpenAI-compatible server (`:8080` llama-server, `:11434` Ollama, `:20128` OmniRoute)."""
    url = base_url.rstrip("/") + "/chat/completions"
    model_name = "pi-free-smart" if ":20128" in base_url else "local-model"
    payload = {
        "model": model_name,
        "messages": [
            {
                "role": "system",
                "content": "Sei Cortical, assistente AI locale rapido e conciso. Rispondi in italiano in 1-2 frasi.",
            },
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 90,
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
            # Strip <think>...</think> blocks if a reasoning model is loaded
            if "</think>" in content:
                content = content.split("</think>", 1)[1].strip()
            return content
    except Exception:  # noqa: BLE001
        return f"Cortical System 1 attivo (modalità deterministica offline): ricevuto '{prompt}'."


class CorticalLiveService:
    """Holds shared state for the live Cortical HTTP & Voice server."""

    def __init__(
        self,
        wiki_db_path: str | Path,
        perm_db_path: str | Path,
        profiler: Optional[HardwareProfiler] = None,
    ) -> None:
        self.started_at = time.time()
        self.wiki_db = CorticalWikiDB(wiki_db_path)
        self.verifier = CitationVerifier(self.wiki_db)
        self.perm_gate = AdaptivePermissionGate(perm_db_path)
        self.profiler = profiler or HardwareProfiler()
        self.hw_profile = self.profiler.detect()
        self.model_rec = self.profiler.recommend_models(self.hw_profile)

        def _reflex(prompt: str) -> str:
            return query_local_reflex_llm(prompt, self.model_rec.active_base_url)

        def _dispatch_agentic(goal: str) -> str:
            ep_id = f"live-{int(time.time() * 1000) % 100000}"
            self.wiki_db.record_episode(
                AccessContext(),
                episode_id=ep_id,
                title=f"Voice Agentic Task: {goal[:48]}",
                goal=goal,
                outcome_status="running",
                learned_summary="Delegated via Cortical System 2 Voice Orchestrator.",
                skills_used=["cortical-second-brain"],
                relations=[
                    {
                        "relation": "relates_to",
                        "target_type": "subtree",
                        "target_id": "/",
                    }
                ],
            )
            return ep_id

        self.voice_engine = CorticalVoiceEngine(
            wiki_db=self.wiki_db,
            permission_gate=self.perm_gate,
            reflex_llm_fn=_reflex,
            agentic_dispatch_fn=_dispatch_agentic,
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
                    "reuse_existing_endpoint": self.model_rec.reuse_existing_endpoint,
                    "active_base_url": self.model_rec.active_base_url,
                    "discovered_endpoints": self.hw_profile.discovered_endpoints,
                },
            )

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
            t0 = time.perf_counter()
            res = self.voice_engine.handle_utterance(utterance)
            elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            tts_triggered = speak_native_tts(res.spoken_response) if speak else False
            out = dataclasses.asdict(res)
            out["latency_ms"] = elapsed_ms
            out["tts_triggered"] = tts_triggered
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
    print(f"Cortical Live Server listening on http://{host}:{port}")
    httpd.serve_forever()
