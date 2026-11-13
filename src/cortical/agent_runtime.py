"""Claude Code / Codex-style agent runtime primitives.

- ApprovalBroker: interactive, non-blocking tool approvals for headless `pi` runs
  (modes: ask / auto_edit / full_auto; decisions: once / session / always / deny).
- run_streaming_process: subprocess runner with reader thread, idle + hard
  watchdogs, cooperative stop, and pause while an approval is pending.
- build_agent_prompt / parse_agent_status: explicit completion protocol so a
  task always ends in DONE, NEEDS_INPUT or BLOCKED instead of hanging.
"""
from __future__ import annotations

import queue
import re
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

APPROVAL_MODES = ("ask", "auto_edit", "full_auto")
APPROVAL_DECISIONS = ("allow_once", "allow_session", "allow_always", "deny")
EDIT_TOOLS = {"edit", "write", "edit_file", "write_file"}
READ_TOOLS = {"read", "read_file", "grep", "find", "ls", "glob"}


@dataclass
class PendingApproval:
    approval_id: str
    session_id: str
    tool: str
    args: dict[str, Any]
    pattern: str
    risk: float
    reason: str
    role: str = ""
    model: str = ""
    created_at: float = field(default_factory=time.time)
    status: str = "pending"  # pending | allowed | denied | expired
    decision: str = ""
    feedback: str = ""
    event: threading.Event = field(default_factory=threading.Event, repr=False)

    def summary(self) -> str:
        if self.tool == "bash":
            return str(self.args.get("command") or self.args.get("cmd") or "")[:400]
        path = self.args.get("path") or self.args.get("file_path")
        if path:
            return f"{self.tool} {path}"
        return f"{self.tool} {str(self.args)[:300]}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "approval_id": self.approval_id,
            "session_id": self.session_id,
            "tool": self.tool,
            "args": self.args,
            "summary": self.summary(),
            "pattern": self.pattern,
            "risk": self.risk,
            "reason": self.reason,
            "role": self.role,
            "model": self.model,
            "created_at": self.created_at,
            "age_sec": round(time.time() - self.created_at, 1),
            "status": self.status,
            "decision": self.decision,
            "feedback": self.feedback,
        }


def _auto_edit_allows(tool: str, pattern: str) -> bool:
    """Codex 'auto-edit': file edits and dev/test/read commands run without prompting."""
    t = tool.lower()
    if t in EDIT_TOOLS or t in READ_TOOLS:
        return True
    return pattern.startswith(("bash:readonly:", "bash:test:", "bash:dev:"))


class ApprovalBroker:
    """Thread-safe broker between headless agent tool calls and the UI."""

    def __init__(
        self,
        gate: Any,
        default_timeout_sec: float = 600.0,
        on_change: Optional[Callable[[str, dict[str, Any]], None]] = None,
    ) -> None:
        self.gate = gate
        self.default_timeout_sec = default_timeout_sec
        self.on_change = on_change
        self._lock = threading.Lock()
        self._pending: dict[str, PendingApproval] = {}
        self._modes: dict[str, str] = {}
        self._session_allow: dict[str, set[str]] = {}

    # ----- modes -------------------------------------------------------
    def set_mode(self, session_id: str, mode: str) -> str:
        m = mode if mode in APPROVAL_MODES else "ask"
        with self._lock:
            self._modes[session_id] = m
        return m

    def get_mode(self, session_id: str) -> str:
        with self._lock:
            return self._modes.get(session_id, "ask")

    # ----- requests ----------------------------------------------------
    def request(
        self,
        session_id: str,
        tool: str,
        args: dict[str, Any],
        role: str = "",
        model: str = "",
    ) -> dict[str, Any]:
        """Evaluates a tool call; returns allow/deny immediately or a pending approval id."""
        dec = self.gate.evaluate(tool, args)
        base = {"pattern": dec.normalized_pattern, "risk": dec.risk_score, "reason": dec.reason}
        if dec.verdict == "deny":
            return {"decision": "deny", "pending": False, **base}
        if dec.verdict == "allow":
            return {"decision": "allow", "pending": False, **base}
        mode = self.get_mode(session_id)
        with self._lock:
            session_ok = dec.normalized_pattern in self._session_allow.get(session_id, set())
        if session_ok or mode == "full_auto" or (mode == "auto_edit" and _auto_edit_allows(tool, dec.normalized_pattern)):
            why = "session-approved pattern" if session_ok else f"approval mode {mode}"
            return {"decision": "allow", "pending": False, **base, "reason": why}
        pa = PendingApproval(
            approval_id=f"apr-{uuid.uuid4().hex[:10]}",
            session_id=session_id,
            tool=tool,
            args=dict(args or {}),
            pattern=dec.normalized_pattern,
            risk=float(dec.risk_score),
            reason=dec.reason,
            role=role,
            model=model,
        )
        with self._lock:
            self._pending[pa.approval_id] = pa
        self._notify(pa)
        return {"decision": "pending", "pending": True, "approval_id": pa.approval_id, **base}

    def wait(self, approval_id: str, timeout_sec: float = 25.0) -> dict[str, Any]:
        """Long-poll: blocks until resolved, the poll window elapses, or the approval expires."""
        with self._lock:
            pa = self._pending.get(approval_id)
        if pa is None:
            return {"status": "unknown", "decision": "deny", "reason": "approval not found"}
        pa.event.wait(timeout=max(0.0, timeout_sec))
        if pa.status == "pending" and time.time() - pa.created_at > self.default_timeout_sec:
            self._finalize(pa, "expired", "deny", "Timeout: nessuna risposta dall'utente")
        return self._result(pa)

    def resolve(self, approval_id: str, decision: str, feedback: str = "") -> dict[str, Any]:
        with self._lock:
            pa = self._pending.get(approval_id)
        if pa is None:
            return {"ok": False, "error": "approval not found"}
        if pa.status != "pending":
            return {"ok": False, "error": f"already {pa.status}", **self._result(pa)}
        dec = decision if decision in APPROVAL_DECISIONS else "deny"
        if dec == "allow_session":
            with self._lock:
                self._session_allow.setdefault(pa.session_id, set()).add(pa.pattern)
        try:
            if dec == "allow_always":
                self.gate.record_user_feedback(pa.tool, pa.args, approved=True, remember_always=True)
            elif dec == "deny":
                self.gate.record_user_feedback(pa.tool, pa.args, approved=False, remember_always=False)
        except Exception:  # noqa: BLE001
            pass
        status = "denied" if dec == "deny" else "allowed"
        self._finalize(pa, status, dec, feedback)
        return {"ok": True, **self._result(pa)}

    def cancel_session(self, session_id: str, reason: str = "Task interrotto") -> int:
        with self._lock:
            items = [p for p in self._pending.values() if p.session_id == session_id and p.status == "pending"]
        for pa in items:
            self._finalize(pa, "denied", "deny", reason)
        return len(items)

    def has_pending(self, session_id: str) -> bool:
        with self._lock:
            return any(p.session_id == session_id and p.status == "pending" for p in self._pending.values())

    def list_pending(self, session_id: Optional[str] = None) -> list[dict[str, Any]]:
        self._expire_stale()
        with self._lock:
            items = [
                p for p in self._pending.values()
                if p.status == "pending" and (session_id is None or p.session_id == session_id)
            ]
        return [p.to_dict() for p in sorted(items, key=lambda x: x.created_at)]

    # ----- internals ---------------------------------------------------
    def _expire_stale(self) -> None:
        now = time.time()
        with self._lock:
            stale = [p for p in self._pending.values() if p.status == "pending" and now - p.created_at > self.default_timeout_sec]
        for pa in stale:
            self._finalize(pa, "expired", "deny", "Timeout: nessuna risposta dall'utente")

    def _finalize(self, pa: PendingApproval, status: str, decision: str, feedback: str) -> None:
        pa.status = status
        pa.decision = decision
        pa.feedback = feedback or pa.feedback
        pa.event.set()
        self._notify(pa)

    def _notify(self, pa: PendingApproval) -> None:
        if self.on_change is not None:
            try:
                self.on_change(pa.session_id, pa.to_dict())
            except Exception:  # noqa: BLE001
                pass

    @staticmethod
    def _result(pa: PendingApproval) -> dict[str, Any]:
        allowed = pa.status == "allowed"
        reason = pa.feedback or ("Approvato dall'utente" if allowed else "Negato dall'utente")
        return {
            "approval_id": pa.approval_id,
            "status": pa.status,
            "decision": "allow" if allowed else ("pending" if pa.status == "pending" else "deny"),
            "user_decision": pa.decision,
            "reason": reason,
            "feedback": pa.feedback,
        }


# ---------------------------------------------------------------------------
# Streaming subprocess runner with watchdogs
# ---------------------------------------------------------------------------

def run_streaming_process(
    cmd: list[str],
    *,
    cwd: str,
    env: dict[str, str],
    on_line: Callable[[str], None],
    stop_event: Optional[threading.Event] = None,
    idle_timeout_sec: float = 240.0,
    hard_timeout_sec: float = 1800.0,
    is_paused: Optional[Callable[[], bool]] = None,
    should_abort: Optional[Callable[[], bool]] = None,
    on_start: Optional[Callable[[subprocess.Popen[str]], None]] = None,
    popen_fn: Optional[Callable[..., Any]] = None,
    poll_interval: float = 0.5,
) -> dict[str, Any]:
    """Runs a process, streaming stdout lines; never blocks forever.

    exit_reason: completed | stopped | idle_timeout | hard_timeout | aborted | spawn_error
    Idle time does not accumulate while `is_paused()` is True (e.g. awaiting approval).
    """
    opener = popen_fn or subprocess.Popen
    try:
        proc = opener(
            cmd,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
    except Exception as exc:  # noqa: BLE001
        return {"exit_reason": "spawn_error", "stderr": str(exc), "returncode": None, "lines": 0}
    if on_start is not None:
        on_start(proc)

    q: "queue.Queue[Optional[str]]" = queue.Queue()
    err_chunks: list[str] = []

    def _pump_stdout() -> None:
        try:
            for ln in proc.stdout:  # type: ignore[union-attr]
                q.put(ln)
        except Exception:  # noqa: BLE001
            pass
        finally:
            q.put(None)

    def _pump_stderr() -> None:
        try:
            for ln in proc.stderr:  # type: ignore[union-attr]
                if sum(len(c) for c in err_chunks) < 8000:
                    err_chunks.append(ln)
        except Exception:  # noqa: BLE001
            pass

    threading.Thread(target=_pump_stdout, daemon=True).start()
    if getattr(proc, "stderr", None) is not None:
        threading.Thread(target=_pump_stderr, daemon=True).start()

    started = time.time()
    last_activity = started
    reason = "completed"
    n_lines = 0
    while True:
        try:
            item = q.get(timeout=poll_interval)
        except queue.Empty:
            item = ""
        now = time.time()
        if item is None:
            break
        if item:
            n_lines += 1
            last_activity = now
            try:
                on_line(item)
            except Exception:  # noqa: BLE001
                pass
        if is_paused is not None and is_paused():
            last_activity = now
        if stop_event is not None and stop_event.is_set():
            reason = "stopped"
        elif should_abort is not None and should_abort():
            reason = "aborted"
        elif now - started > hard_timeout_sec:
            reason = "hard_timeout"
        elif now - last_activity > idle_timeout_sec:
            reason = "idle_timeout"
        else:
            continue
        _terminate(proc)
        break
    try:
        proc.wait(timeout=5)
    except Exception:  # noqa: BLE001
        _terminate(proc, force=True)
    finally:
        for pipe in (getattr(proc, "stdout", None), getattr(proc, "stderr", None)):
            if pipe is not None:
                try:
                    pipe.close()
                except Exception:  # noqa: BLE001
                    pass
    return {
        "exit_reason": reason,
        "stderr": "".join(err_chunks).strip(),
        "returncode": getattr(proc, "returncode", None),
        "lines": n_lines,
        "elapsed_sec": round(time.time() - started, 2),
    }


def _terminate(proc: Any, force: bool = False) -> None:
    try:
        if proc.poll() is None:
            proc.kill() if force else proc.terminate()
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# Prompt + completion protocol
# ---------------------------------------------------------------------------

STATUS_RE = re.compile(r"STATUS\s*[:=]\s*\**\s*(DONE|NEEDS_INPUT|BLOCKED)\b", re.IGNORECASE)


def build_agent_prompt(
    goal: str,
    *,
    workspace: str,
    is_follow_up: bool = False,
    attachments: str = "",
    wiki_context: str = "",
    lang: str = "it",
) -> str:
    """Concise Claude-Code-style task prompt with an explicit completion protocol."""
    if is_follow_up:
        head = f"Follow-up from the user in this same task (keep all previous context):\n{goal.strip()}"
    else:
        head = f"Task: {goal.strip()}"
    parts = [
        head,
        "",
        f"Workspace: {workspace}",
        "How to work:",
        "1. Explore first with read/grep/find/ls inside the workspace; never run `ls -R` on parent (`../`) directories.",
        "2. If a target file or directory does not exist yet, create it directly with write (or `mkdir -p`) instead of searching for it.",
        "3. Make real changes with edit/write and verify them with bash (tests, lint, run).",
        "4. Keep going autonomously until the task is fully done; do not ask for confirmation for normal steps.",
        "5. Never start long-running servers or interactive commands (no `npm run dev`, no editors, no prompts); use timeouts.",
        "6. If a tool call is denied, read the reason/feedback and adapt instead of retrying the same call.",
        "",
        "When you finish, end your final message with:",
        "## Result",
        "<what you did, files changed, how you verified it>",
        "STATUS: DONE  |  STATUS: NEEDS_INPUT (then ask ONE precise question)  |  STATUS: BLOCKED (then explain why)",
        f"Reply in {'Italian' if lang == 'it' else 'English'} unless the user writes in another language.",
    ]
    if attachments.strip():
        parts += ["", "[Attached context]", attachments.strip()]
    if wiki_context.strip():
        parts += ["", "[Second Brain notes]", wiki_context.strip()]
    return "\n".join(parts)


def parse_agent_status(final_text: str, tool_count: int = 0, exit_reason: str = "completed") -> dict[str, str]:
    """Maps the agent final message + runner exit reason to a task status."""
    txt = final_text or ""
    if exit_reason == "stopped":
        return {"status": "stopped", "label": "Interrotto"}
    if exit_reason in {"idle_timeout", "hard_timeout"}:
        return {"status": "stalled", "label": "Bloccato (timeout)"}
    if exit_reason == "spawn_error":
        return {"status": "blocked", "label": "Errore avvio agente"}
    m = None
    for m in STATUS_RE.finditer(txt):
        pass
    if m is not None:
        tag = m.group(1).upper()
        mapping = {
            "DONE": ("completed", "Completato"),
            "NEEDS_INPUT": ("needs_input", "Serve una tua risposta"),
            "BLOCKED": ("blocked", "Bloccato"),
        }
        st, label = mapping[tag]
        return {"status": st, "label": label}
    if not txt.strip():
        return {"status": "blocked", "label": "Nessuna risposta dal modello"}
    if txt.rstrip().endswith("?"):
        return {"status": "needs_input", "label": "Serve una tua risposta"}
    return {"status": "completed", "label": "Completato" if tool_count else "Risposto"}


def extract_question(final_text: str) -> str:
    """Returns the last question line from the agent final message (for NEEDS_INPUT)."""
    lines = [ln.strip() for ln in (final_text or "").splitlines() if ln.strip()]
    for ln in reversed(lines):
        if "?" in ln and not ln.upper().startswith("STATUS"):
            return ln[:400]
    return ""
