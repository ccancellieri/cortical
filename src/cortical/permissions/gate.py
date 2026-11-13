"""Adaptive Permission Gate with Hard Guardrails and Progressive Pattern Learning.

Evaluates agent tool calls (`bash`, `write`, `edit`, `mcp`, `browser`):
1. Hard Guardrail Check: Irreversible/destructive commands or focus-stealing UI commands
   are strictly blocked (`verdict = 'deny'`).
2. Read-Only / Safe Builtins: Immediately allowed (`verdict = 'allow'`).
3. Adaptive Learned Patterns: Normalizes tool + command/path/domain signature and looks up
   historical user approvals in SQLite. Once a pattern reaches the approval threshold with
   zero incidents, its dynamic risk score drops below the auto-approve threshold.
"""

from __future__ import annotations

import contextlib
import json
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator


HARD_BLOCK_PATTERNS = [
    r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f\s+/(?:\s|$)",
    r"\bmkfs\b",
    r"\bdd\s+if=",
    r":\(\)\s*\{\s*:\|:&\s*\};:",
    r"\bchmod\s+-R\s+777\s+/",
    r"\b(?:cat|curl|scp|nc)\b.*(?:pass\.txt|sudo_pass\.txt|\.ssh/id_)",
    r"\bset\s+frontmost\s+to\s+true\b",
    r"\bAXRaise\b",
]

SENSITIVE_PATH_RE = re.compile(
    r"(?:~?/\.ssh/|~?/\.aws/|~?/\.netrc|\bid_rsa\b|\bid_ed25519\b|\bpass\.txt\b|\bsudo_pass\.txt\b|(?:^|[\s/\"'])\.env(?:\.local|\.prod)?(?:$|[\s\"']))",
    re.IGNORECASE,
)
OUTBOUND_NET_CMD_RE = re.compile(
    r"(?:^|[;&|\s])(?:curl|wget|nc|ncat|socat|ssh|scp|sftp|rsync|ftp|telnet|dig|nslookup|xh)\b",
    re.IGNORECASE,
)
INLINE_NET_API_RE = re.compile(
    r"(?:urllib\.request|requests\.(?:get|post|put|delete|request)|httpx\.|http\.client|socket\.connect|fetch\(|XMLHttpRequest)",
    re.IGNORECASE,
)
URL_HOST_RE = re.compile(r"https?://([A-Za-z0-9.\-:]+)", re.IGNORECASE)
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]", "0.0.0.0"}


def detect_egress_or_secret_attempt(cmd: str) -> tuple[bool, str, str]:
    """Detects outbound network calls to non-local hosts or sensitive secret access."""
    text = str(cmd or "").strip()
    if not text:
        return (False, "", "")
    if SENSITIVE_PATH_RE.search(text):
        return (True, "sensitive-path", "Blocked access to sensitive credential/key path.")

    urls = URL_HOST_RE.findall(text)
    for host_port in urls:
        host = host_port.split(":")[0].lower()
        if host and host not in LOCAL_HOSTS:
            return (True, host, f"Blocked outbound network target: {host_port}")

    if OUTBOUND_NET_CMD_RE.search(text) or INLINE_NET_API_RE.search(text):
        # Allow explicit loopback-only commands (e.g. curl http://127.0.0.1:8765/...)
        if urls and all(h.split(":")[0].lower() in LOCAL_HOSTS for h in urls):
            return (False, "", "")
        if any(lh in text.lower() for lh in ("127.0.0.1", "localhost", "::1")) and not urls:
            return (False, "", "")
        return (True, "external-network", "Blocked outbound network/exfiltration command in strict isolation mode.")
    return (False, "", "")

SAFE_READONLY_COMMANDS = {
    "ls",
    "pwd",
    "cat",
    "head",
    "tail",
    "find",
    "grep",
    "rg",
    "git status",
    "git diff",
    "git log",
    "uname",
    "whoami",
    "df",
}


@dataclass
class PermissionDecision:
    verdict: str  # 'allow' | 'ask' | 'deny'
    risk_score: float  # 0.0 (safe) -> 1.0 (critical)
    normalized_pattern: str
    reason: str
    learned_approvals: int = 0


class AdaptivePermissionGate:
    """SQLite-backed adaptive permission gate that learns from user approvals."""

    def __init__(
        self,
        db_path: str | Path,
        auto_approve_threshold: int = 2,
    ) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.auto_approve_threshold = auto_approve_threshold
        self._init_db()

    @contextlib.contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path), timeout=15.0)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS permission_patterns (
                    pattern_key TEXT PRIMARY KEY,
                    tool_name TEXT NOT NULL,
                    base_risk REAL NOT NULL,
                    approvals INTEGER NOT NULL DEFAULT 0,
                    denials INTEGER NOT NULL DEFAULT 0,
                    always_allow INTEGER NOT NULL DEFAULT 0,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS permission_audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tool_name TEXT NOT NULL,
                    pattern_key TEXT NOT NULL,
                    verdict TEXT NOT NULL,
                    risk_score REAL NOT NULL,
                    raw_args_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS egress_audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL DEFAULT '',
                    role TEXT NOT NULL DEFAULT '',
                    model TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT 'egress_proxy',
                    method TEXT NOT NULL DEFAULT '',
                    target_host TEXT NOT NULL DEFAULT '',
                    target_url TEXT NOT NULL DEFAULT '',
                    payload_excerpt TEXT NOT NULL DEFAULT '',
                    verdict TEXT NOT NULL DEFAULT 'blocked',
                    reason TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL
                );
                """
            )

    @staticmethod
    def _normalize_bash_pattern(cmd: str) -> tuple[str, float]:
        for pat in HARD_BLOCK_PATTERNS:
            if re.search(pat, cmd, flags=re.IGNORECASE):
                return (f"bash:HARD_BLOCK:{pat}", 1.0)
        egress_blocked, target, _why = detect_egress_or_secret_attempt(cmd)
        if egress_blocked:
            return (f"bash:HARD_BLOCK:egress:{target}", 1.0)

        tokens = cmd.split()
        idx = 0
        while idx < len(tokens) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[idx]):
            idx += 1
        eff_tokens = tokens[idx:]
        if not eff_tokens:
            return ("bash:empty", 0.0)

        exe_name = Path(eff_tokens[0]).name
        head_two = f"{exe_name} {eff_tokens[1]}" if len(eff_tokens) > 1 else exe_name
        if exe_name in SAFE_READONLY_COMMANDS or head_two in SAFE_READONLY_COMMANDS:
            return (f"bash:readonly:{exe_name}", 0.1)

        joined_tail = " ".join(eff_tokens[1:4])
        if (exe_name in {"python", "python3"} and "unittest" in joined_tail) or (
            exe_name == "node" and "--check" in joined_tail
        ):
            return (f"bash:test:{exe_name}", 0.12)

        if exe_name in {"python", "python3", "npm", "node", "git"}:
            sub = eff_tokens[1] if len(eff_tokens) > 1 and not eff_tokens[1].startswith("-") else "exec"
            return (f"bash:dev:{exe_name}:{sub}", 0.45)

        return (f"bash:cmd:{exe_name}", 0.65)

    def normalize_pattern(self, tool_name: str, args: dict[str, Any]) -> tuple[str, float]:
        """Extracts a reusable canonical pattern and initial base risk score."""
        tool = tool_name.lower()
        if tool in {"read", "read_file"}:
            target_path = str(args.get("path") or args.get("file_path") or "")
            if SENSITIVE_PATH_RE.search(target_path):
                return (f"{tool}:HARD_BLOCK:sensitive:{target_path}", 1.0)
            return (f"{tool}:*", 0.05)

        if tool in {"wiki_navigate", "wiki_search", "list_pages"}:
            return (f"{tool}:*", 0.05)

        if tool == "bash":
            cmd = str(args.get("command") or args.get("cmd") or "").strip()
            return self._normalize_bash_pattern(cmd)

        if tool in {"write", "write_file", "edit", "edit_file"}:
            target_path = str(args.get("path") or args.get("file_path") or "")
            if any(s in target_path for s in ("/etc/", "/System/", ".ssh", "pass.txt")):
                return (f"{tool}:HARD_BLOCK:{target_path}", 1.0)
            parent = str(Path(target_path).parent) if target_path else "."
            return (f"{tool}:dir:{parent}", 0.40)

        if "chrome" in tool or "browser" in tool or "playwright" in tool:
            action = str(args.get("action") or tool)
            if any(k in action.lower() for k in ("submit", "pay", "delete", "send")):
                return (f"browser:critical:{action}", 0.80)
            return (f"browser:ui:{action}", 0.35)

        return (f"{tool}:generic", 0.50)

    def evaluate(self, tool_name: str, args: dict[str, Any]) -> PermissionDecision:
        pattern_key, base_risk = self.normalize_pattern(tool_name, args)

        if "HARD_BLOCK" in pattern_key or base_risk >= 0.99:
            decision = PermissionDecision(
                verdict="deny",
                risk_score=1.0,
                normalized_pattern=pattern_key,
                reason="Blocked by non-bypassable security/focus guardrail.",
            )
            self._log(tool_name, pattern_key, decision, args)
            return decision

        if base_risk <= 0.15:
            decision = PermissionDecision(
                verdict="allow",
                risk_score=base_risk,
                normalized_pattern=pattern_key,
                reason="Safe read-only operation.",
            )
            self._log(tool_name, pattern_key, decision, args)
            return decision

        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM permission_patterns WHERE pattern_key = ?",
                (pattern_key,),
            ).fetchone()

        approvals = int(row["approvals"]) if row else 0
        denials = int(row["denials"]) if row else 0
        always_allow = bool(row["always_allow"]) if row else False

        # Dynamic risk decay with progressive approvals, penalized by denials
        effective_risk = max(
            0.05,
            min(0.95, base_risk - (0.15 * approvals) + (0.30 * denials)),
        )

        if denials > 0 and not always_allow:
            verdict = "ask" if effective_risk < 0.85 else "deny"
            reason = f"Previously denied ({denials}x); requires explicit confirmation."
        elif always_allow or approvals >= self.auto_approve_threshold or effective_risk <= 0.25:
            verdict = "allow"
            reason = f"Auto-approved by adaptive learning ({approvals} prior approvals)."
        else:
            verdict = "ask"
            reason = f"New/medium-risk pattern (risk={effective_risk:.2f}); awaiting user approval."

        decision = PermissionDecision(
            verdict=verdict,
            risk_score=round(effective_risk, 3),
            normalized_pattern=pattern_key,
            reason=reason,
            learned_approvals=approvals,
        )
        self._log(tool_name, pattern_key, decision, args)
        return decision

    def record_user_feedback(
        self,
        tool_name: str,
        args: dict[str, Any],
        *,
        approved: bool,
        remember_always: bool = False,
    ) -> PermissionDecision:
        """Updates the learned risk table after user approves or denies a prompt."""
        pattern_key, base_risk = self.normalize_pattern(tool_name, args)
        if "HARD_BLOCK" in pattern_key:
            raise ValueError("Cannot override a HARD_BLOCK guardrail.")

        now = time.time()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO permission_patterns(
                       pattern_key, tool_name, base_risk, approvals, denials, always_allow, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(pattern_key) DO UPDATE SET
                       approvals = approvals + excluded.approvals,
                       denials = denials + excluded.denials,
                       always_allow = MAX(always_allow, excluded.always_allow),
                       updated_at = excluded.updated_at""",
                (
                    pattern_key,
                    tool_name.lower(),
                    base_risk,
                    1 if approved else 0,
                    0 if approved else 1,
                    1 if (approved and remember_always) else 0,
                    now,
                ),
            )
        return self.evaluate(tool_name, args)

    def _log(
        self,
        tool_name: str,
        pattern_key: str,
        decision: PermissionDecision,
        args: dict[str, Any],
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO permission_audit_log(
                       tool_name, pattern_key, verdict, risk_score, raw_args_json, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    tool_name,
                    pattern_key,
                    decision.verdict,
                    decision.risk_score,
                    json.dumps(args, default=str),
                    time.time(),
                ),
            )

    def record_egress_event(
        self,
        *,
        session_id: str = "",
        role: str = "",
        model: str = "",
        source: str = "egress_proxy",
        method: str = "",
        target_host: str = "",
        target_url: str = "",
        payload_excerpt: str = "",
        verdict: str = "blocked",
        reason: str = "",
    ) -> dict[str, Any]:
        """Persists an outbound egress or secret-access attempt for security audit."""
        now = time.time()
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO egress_audit_log(
                       session_id, role, model, source, method, target_host,
                       target_url, payload_excerpt, verdict, reason, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(session_id or "")[:80],
                    str(role or "")[:60],
                    str(model or "")[:120],
                    str(source or "egress_proxy")[:40],
                    str(method or "")[:20],
                    str(target_host or "")[:180],
                    str(target_url or "")[:400],
                    str(payload_excerpt or "")[:600],
                    str(verdict or "blocked")[:20],
                    str(reason or "")[:240],
                    now,
                ),
            )
            ev_id = int(cur.lastrowid or 0)
        return {
            "id": ev_id,
            "session_id": session_id,
            "role": role,
            "model": model,
            "source": source,
            "method": method,
            "target_host": target_host,
            "target_url": target_url,
            "payload_excerpt": payload_excerpt[:600],
            "verdict": verdict,
            "reason": reason,
            "created_at": now,
        }

    def list_egress_events(self, limit: int = 50, session_id: str = "") -> list[dict[str, Any]]:
        """Lists recent blocked/audited outbound egress attempts."""
        with self._connect() as conn:
            if session_id:
                rows = conn.execute(
                    "SELECT * FROM egress_audit_log WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                    (session_id, max(1, min(limit, 200))),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM egress_audit_log ORDER BY id DESC LIMIT ?",
                    (max(1, min(limit, 200)),),
                ).fetchall()
        return [dict(r) for r in rows]

    def clear_egress_events(self) -> int:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM egress_audit_log")
            return int(cur.rowcount or 0)
