"""Modular & Optional Remote Gateway, Key/Account Auth & Cross-Harness Exposure for Cortical.

Zero mandatory external dependencies (pure Python stdlib + SQLite WAL).
Designed to stay completely optional and lightweight:
- Localhost connections can optionally bypass authentication (`allow_localhost_bypass=True`).
- Remote/Internet traffic (tunnel or reverse proxy) requires either a Gateway Key
  (`X-Cortical-Key`, `Authorization: Bearer ...`, `?key=...`, or `cortical_key` cookie)
  or an authenticated user session (`cortical_session` cookie / Bearer session token).
- User registration is strictly bounded by configurable `max_users` (default: 1, pre-assigned
  to `DEFAULT_OWNER_EMAIL`, default `owner@example.com`) with PBKDF2-HMAC-SHA256 passwords and one-time password
  creation tokens sent via email / outbox.
"""

from __future__ import annotations

import contextlib
import email.utils
from email.message import EmailMessage
import hashlib
import hmac
import json
import os
import platform
import re
import secrets
import shutil
import smtplib
import sqlite3
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterator, Optional

DEFAULT_OWNER_EMAIL = os.environ.get("CORTICAL_OWNER_EMAIL", "owner@example.com")
DEFAULT_OWNER_NAME = os.environ.get("CORTICAL_OWNER_NAME", "Local Owner")
DEFAULT_DUCKDNS_DOMAIN = os.environ.get("CORTICAL_DUCKDNS_DOMAIN", "my-cortical")
DEFAULT_GITHUB_PORTAL_URL = "https://ccancellieri.github.io/cortical/"

GATEWAY_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS cortical_gateway_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS cortical_users (
    user_id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT 'user',
    password_hash TEXT NOT NULL DEFAULT '',
    password_salt TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending_password',
    created_at REAL NOT NULL,
    last_login_at REAL
);

CREATE TABLE IF NOT EXISTS cortical_auth_tokens (
    token_hash TEXT PRIMARY KEY,
    email TEXT NOT NULL,
    purpose TEXT NOT NULL,
    expires_at REAL NOT NULL,
    used INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS cortical_sessions (
    session_token_hash TEXT PRIMARY KEY,
    email TEXT NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    user_agent TEXT NOT NULL DEFAULT '',
    remote_ip TEXT NOT NULL DEFAULT ''
);
"""

_EXEMPT_EXACT_PATHS = frozenset({
    "/health",
    "/auth/login",
    "/auth/setup-password",
    "/api/auth/status",
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/setup-password",
    "/api/auth/register",
})

_URL_PATTERNS = (
    re.compile(r"(https://[a-zA-Z0-9.-]+\.trycloudflare\.com)"),
    re.compile(r"(https://[a-zA-Z0-9.-]+\.lhr\.life)"),
    re.compile(r"(https://[a-zA-Z0-9.-]+\.localhost\.run)"),
    re.compile(r"(https://[a-zA-Z0-9.-]+\.pinggy\.(?:link|io|online))"),
    re.compile(r"(https://[a-zA-Z0-9.-]+\.ngrok[-a-z]*\.(?:app|io|dev|free))"),
)


def _sha256_hex(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _hash_password(password: str, salt_hex: Optional[str] = None) -> tuple[str, str]:
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
    return (dk.hex(), salt.hex())


def _verify_password(password: str, stored_hash: str, salt_hex: str) -> bool:
    if not stored_hash or not salt_hex:
        return False
    calc_hash, _ = _hash_password(password, salt_hex=salt_hex)
    return hmac.compare_digest(calc_hash, stored_hash)


def _mask_secret(secret: str) -> str:
    if not secret:
        return ""
    if len(secret) <= 10:
        return secret[:3] + "..."
    return f"{secret[:7]}...{secret[-4:]}"


def _parse_cookies(cookie_header: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for chunk in (cookie_header or "").split(";"):
        if "=" not in chunk:
            continue
        k, v = chunk.split("=", 1)
        out[k.strip()] = urllib.parse.unquote(v.strip())
    return out


class _LiveTunnelRuntime:
    """Process-scoped live tunnel tracker so SSH/cloudflared subprocess stays open across requests."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.proc: Optional[subprocess.Popen[str]] = None
        self.provider: str = ""
        self.public_url: str = ""
        self.started_at: float = 0.0
        self.last_error: str = ""
        self.log_tail: list[str] = []


_GLOBAL_TUNNEL = _LiveTunnelRuntime()


class CorticalRemoteGateway:
    """Manages optional Gateway Key auth, user cap/accounts, password setup tokens, tunnel & notifications."""

    def __init__(
        self,
        wiki_db_or_path: Any = None,
        *,
        outbox_dir: str | Path | None = None,
        local_port: int = 8765,
    ) -> None:
        if wiki_db_or_path is None:
            wiki_db_or_path = os.environ.get(
                "CORTICAL_WIKI_DB",
                str(Path.home() / ".cortical_data" / "wiki.db"),
            )
        if hasattr(wiki_db_or_path, "_connect") and hasattr(wiki_db_or_path, "db_path"):
            self._wiki_db = wiki_db_or_path
            self.db_path = Path(wiki_db_or_path.db_path)
        else:
            self._wiki_db = None
            self.db_path = Path(wiki_db_or_path).expanduser().resolve()
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.local_port = int(local_port)
        self.outbox_dir = Path(outbox_dir).expanduser().resolve() if outbox_dir else (self.db_path.parent / "outbox")
        self.outbox_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._ensure_schema_and_defaults()

    @contextlib.contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        if self._wiki_db is not None:
            with self._wiki_db._connect() as conn:
                yield conn
            return
        conn = sqlite3.connect(str(self.db_path), timeout=15.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _ensure_schema_and_defaults(self) -> None:
        now = time.time()
        with self._connect() as conn:
            conn.executescript(GATEWAY_SCHEMA_SQL)
            defaults = {
                "auth_enabled": "true",
                "allow_localhost_bypass": "true",
                "max_users": "1",
                "gateway_api_key": f"ctk_{secrets.token_urlsafe(24)}",
                "duckdns_domain": DEFAULT_DUCKDNS_DOMAIN,
                "duckdns_token": "",
                "public_gateway_url": "",
                "github_portal_url": DEFAULT_GITHUB_PORTAL_URL,
                "owner_email": DEFAULT_OWNER_EMAIL,
                "tunnel_provider": "localhost.run",
            }
            for k, v in defaults.items():
                conn.execute(
                    "INSERT OR IGNORE INTO cortical_gateway_config(key, value, updated_at) VALUES (?, ?, ?)",
                    (k, v, now),
                )
            row = conn.execute("SELECT COUNT(*) AS cnt FROM cortical_users").fetchone()
            if int(row["cnt"] if row else 0) == 0:
                uid = f"usr-{secrets.token_hex(6)}"
                conn.execute(
                    """INSERT OR IGNORE INTO cortical_users
                       (user_id, email, display_name, role, password_hash, password_salt, status, created_at)
                       VALUES (?, ?, ?, 'owner', '', '', 'pending_password', ?)""",
                    (uid, DEFAULT_OWNER_EMAIL.lower(), DEFAULT_OWNER_NAME, now),
                )

    def _get_config_map(self) -> dict[str, str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT key, value FROM cortical_gateway_config").fetchall()
        return {str(r["key"]): str(r["value"]) for r in rows}

    def _set_config_key(self, key: str, value: str) -> None:
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO cortical_gateway_config(key, value, updated_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
                (key, str(value), now),
            )

    def get_gateway_api_key(self) -> str:
        return self._get_config_map().get("gateway_api_key", "")

    def get_public_url(self) -> str:
        with _GLOBAL_TUNNEL.lock:
            if _GLOBAL_TUNNEL.proc is not None and _GLOBAL_TUNNEL.proc.poll() is None and _GLOBAL_TUNNEL.public_url:
                return _GLOBAL_TUNNEL.public_url
        return self._get_config_map().get("public_gateway_url", "")

    def _sanitize_user(self, row: sqlite3.Row) -> dict[str, Any]:
        has_pw = bool(row["password_hash"] and row["password_salt"])
        return {
            "user_id": row["user_id"],
            "email": row["email"],
            "display_name": row["display_name"],
            "role": row["role"],
            "has_password": has_pw,
            "status": "active" if has_pw else str(row["status"] or "pending_password"),
            "created_at": row["created_at"],
            "last_login_at": row["last_login_at"],
        }

    def list_users(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM cortical_users ORDER BY created_at ASC").fetchall()
        return [self._sanitize_user(r) for r in rows]

    def get_status(self, *, include_secret: bool = False) -> dict[str, Any]:
        cfg = self._get_config_map()
        users = self.list_users()
        max_users = max(1, int(cfg.get("max_users") or 1))
        api_key = cfg.get("gateway_api_key", "")
        with _GLOBAL_TUNNEL.lock:
            t_alive = _GLOBAL_TUNNEL.proc is not None and _GLOBAL_TUNNEL.proc.poll() is None
            t_url = _GLOBAL_TUNNEL.public_url if t_alive else ""
            t_prov = _GLOBAL_TUNNEL.provider if t_alive else cfg.get("tunnel_provider", "localhost.run")
            t_err = _GLOBAL_TUNNEL.last_error
        public_url = t_url or cfg.get("public_gateway_url", "")
        out = {
            "auth_enabled": cfg.get("auth_enabled", "true") == "true",
            "allow_localhost_bypass": cfg.get("allow_localhost_bypass", "true") == "true",
            "max_users": max_users,
            "registered_users_count": len(users),
            "slots_remaining": max(0, max_users - len(users)),
            "users": users,
            "gateway_key_masked": _mask_secret(api_key),
            "duckdns_domain": cfg.get("duckdns_domain", DEFAULT_DUCKDNS_DOMAIN),
            "duckdns_configured": bool(cfg.get("duckdns_token")),
            "duckdns_last_status": cfg.get("duckdns_last_status", ""),
            "duckdns_last_ip": cfg.get("duckdns_last_ip", ""),
            "smtp_host": cfg.get("smtp_host", ""),
            "smtp_port": int(cfg.get("smtp_port") or 587),
            "smtp_user": cfg.get("smtp_user", ""),
            "smtp_configured": bool(cfg.get("smtp_host") and cfg.get("smtp_user") and cfg.get("smtp_pass")),
            "github_portal_url": cfg.get("github_portal_url", DEFAULT_GITHUB_PORTAL_URL),
            "public_url": public_url,
            "tunnel": {
                "running": t_alive,
                "provider": t_prov,
                "public_url": public_url,
                "last_error": t_err,
            },
            "outbox_dir": str(self.outbox_dir),
            "cross_harness": {
                "mcp_tool_prefix": "wiki_gateway_*",
                "cli": "cortical gateway status|expose|config|invite",
                "pi_extension": ".pi/extensions/cortical-harness.ts",
                "skill": ".agents/skills/cortical-remote-gateway/SKILL.md",
                "header": "X-Cortical-Key",
            },
        }
        if include_secret:
            out["gateway_api_key"] = api_key
        return out

    def configure(self, updates: dict[str, Any]) -> dict[str, Any]:
        if "auth_enabled" in updates:
            self._set_config_key("auth_enabled", "true" if bool(updates["auth_enabled"]) else "false")
        if "allow_localhost_bypass" in updates:
            self._set_config_key(
                "allow_localhost_bypass",
                "true" if bool(updates["allow_localhost_bypass"]) else "false",
            )
        if "max_users" in updates and updates["max_users"] is not None:
            val = max(1, min(1000, int(updates["max_users"])))
            self._set_config_key("max_users", str(val))
        if "duckdns_domain" in updates and str(updates["duckdns_domain"] or "").strip():
            dom = str(updates["duckdns_domain"]).strip().lower().replace(".duckdns.org", "")
            self._set_config_key("duckdns_domain", dom)
        if "duckdns_token" in updates:
            self._set_config_key("duckdns_token", str(updates["duckdns_token"] or "").strip())
        if "smtp_host" in updates:
            self._set_config_key("smtp_host", str(updates["smtp_host"] or "").strip())
        if "smtp_port" in updates and updates["smtp_port"] is not None:
            self._set_config_key("smtp_port", str(int(updates["smtp_port"])))
        if "smtp_user" in updates:
            self._set_config_key("smtp_user", str(updates["smtp_user"] or "").strip())
        if "smtp_pass" in updates and str(updates["smtp_pass"] or "").strip():
            self._set_config_key("smtp_pass", str(updates["smtp_pass"]).strip())
        if "github_portal_url" in updates and str(updates["github_portal_url"] or "").strip():
            self._set_config_key("github_portal_url", str(updates["github_portal_url"]).strip())
        if "public_gateway_url" in updates:
            self._set_config_key("public_gateway_url", str(updates["public_gateway_url"] or "").strip())
        if bool(updates.get("rotate_key")):
            self._set_config_key("gateway_api_key", f"ctk_{secrets.token_urlsafe(24)}")
        return self.get_status(include_secret=True)

    def register_or_invite_user(
        self,
        email: str,
        *,
        display_name: str = "",
        role: str = "user",
        ttl_hours: float = 72.0,
    ) -> dict[str, Any]:
        clean_email = str(email or "").strip().lower()
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", clean_email):
            raise ValueError(f"Indirizzo email non valido: '{email}'")

        now = time.time()
        with self._connect() as conn:
            cfg_row = conn.execute(
                "SELECT value FROM cortical_gateway_config WHERE key='max_users'"
            ).fetchone()
            max_users = max(1, int(cfg_row["value"] if cfg_row else 1))
            existing = conn.execute(
                "SELECT * FROM cortical_users WHERE email=?",
                (clean_email,),
            ).fetchone()
            total_row = conn.execute("SELECT COUNT(*) AS cnt FROM cortical_users").fetchone()
            total_users = int(total_row["cnt"] if total_row else 0)

            if existing is None:
                if total_users >= max_users:
                    raise PermissionError(
                        f"Registrazione bloccata: limite massimo di {max_users} utenti raggiunto "
                        f"({total_users}/{max_users})."
                    )
                uid = f"usr-{secrets.token_hex(6)}"
                dname = display_name.strip() or clean_email.split("@", 1)[0]
                eff_role = role if role in {"owner", "admin", "user"} else "user"
                conn.execute(
                    """INSERT INTO cortical_users
                       (user_id, email, display_name, role, password_hash, password_salt, status, created_at)
                       VALUES (?, ?, ?, ?, '', '', 'pending_password', ?)""",
                    (uid, clean_email, dname, eff_role, now),
                )
            elif display_name.strip():
                conn.execute(
                    "UPDATE cortical_users SET display_name=? WHERE email=?",
                    (display_name.strip(), clean_email),
                )

            # Invalidate prior unused setup tokens for this email and issue a fresh one
            conn.execute(
                "UPDATE cortical_auth_tokens SET used=1 WHERE email=? AND purpose='setup_password'",
                (clean_email,),
            )
            raw_token = f"ctp_{secrets.token_urlsafe(28)}"
            token_hash = _sha256_hex(raw_token)
            expires_at = now + max(1.0, float(ttl_hours)) * 3600.0
            conn.execute(
                """INSERT INTO cortical_auth_tokens
                   (token_hash, email, purpose, expires_at, used, created_at)
                   VALUES (?, ?, 'setup_password', ?, 0, ?)""",
                (token_hash, clean_email, expires_at, now),
            )
            user_row = conn.execute("SELECT * FROM cortical_users WHERE email=?", (clean_email,)).fetchone()

        public_url = self.get_public_url() or f"http://127.0.0.1:{self.local_port}"
        setup_path = f"/auth/setup-password?token={urllib.parse.quote(raw_token)}&email={urllib.parse.quote(clean_email)}"
        return {
            "ok": True,
            "user": self._sanitize_user(user_row) if user_row else {"email": clean_email},
            "setup_token": raw_token,
            "setup_path": setup_path,
            "setup_url": f"{public_url.rstrip('/')}{setup_path}",
            "local_setup_url": f"http://127.0.0.1:{self.local_port}{setup_path}",
            "expires_in_hours": ttl_hours,
        }

    def setup_password(
        self,
        *,
        token: str = "",
        new_password: str = "",
        email_addr: str = "",
        api_key: str = "",
    ) -> dict[str, Any]:
        pw = str(new_password or "")
        if len(pw) < 8:
            raise ValueError("La password deve contenere almeno 8 caratteri.")

        now = time.time()
        target_email = str(email_addr or "").strip().lower()
        used_token = False

        with self._connect() as conn:
            if token:
                th = _sha256_hex(token.strip())
                trow = conn.execute(
                    "SELECT * FROM cortical_auth_tokens WHERE token_hash=? AND purpose='setup_password'",
                    (th,),
                ).fetchone()
                if trow is None:
                    raise PermissionError("Token di creazione password non valido.")
                if int(trow["used"]) != 0:
                    raise PermissionError("Questo link è già stato utilizzato. Richiedi un nuovo invito.")
                if float(trow["expires_at"]) < now:
                    raise PermissionError("Il link di creazione password è scaduto.")
                target_email = str(trow["email"]).lower()
                used_token = True
            else:
                cfg_key = self.get_gateway_api_key()
                if not (api_key and cfg_key and hmac.compare_digest(api_key.strip(), cfg_key)):
                    raise PermissionError("Serve un token email valido oppure la Chiave Gateway.")
                if not target_email:
                    first = conn.execute("SELECT email FROM cortical_users ORDER BY created_at ASC LIMIT 1").fetchone()
                    target_email = str(first["email"]) if first else DEFAULT_OWNER_EMAIL

            urow = conn.execute("SELECT * FROM cortical_users WHERE email=?", (target_email,)).fetchone()
            if urow is None:
                raise KeyError(f"Utente '{target_email}' non trovato.")

            pw_hash, pw_salt = _hash_password(pw)
            conn.execute(
                """UPDATE cortical_users
                   SET password_hash=?, password_salt=?, status='active', last_login_at=?
                   WHERE email=?""",
                (pw_hash, pw_salt, now, target_email),
            )
            if used_token:
                conn.execute(
                    "UPDATE cortical_auth_tokens SET used=1 WHERE token_hash=?",
                    (_sha256_hex(token.strip()),),
                )
            updated = conn.execute("SELECT * FROM cortical_users WHERE email=?", (target_email,)).fetchone()

        sess_token = self._create_session(target_email)
        return {
            "ok": True,
            "user": self._sanitize_user(updated) if updated else {"email": target_email},
            "session_token": sess_token,
        }

    def _create_session(
        self,
        email_addr: str,
        *,
        ttl_days: int = 30,
        user_agent: str = "",
        remote_ip: str = "",
    ) -> str:
        raw_sess = f"cts_{secrets.token_urlsafe(32)}"
        now = time.time()
        exp = now + ttl_days * 86400.0
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO cortical_sessions
                   (session_token_hash, email, created_at, expires_at, user_agent, remote_ip)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (_sha256_hex(raw_sess), email_addr.lower(), now, exp, user_agent[:200], remote_ip[:64]),
            )
        return raw_sess

    def login(
        self,
        *,
        email_addr: str = "",
        password: str = "",
        api_key: str = "",
        user_agent: str = "",
        remote_ip: str = "",
    ) -> dict[str, Any]:
        cfg_key = self.get_gateway_api_key()
        if api_key:
            if cfg_key and hmac.compare_digest(api_key.strip(), cfg_key):
                users = self.list_users()
                owner = users[0] if users else {"email": DEFAULT_OWNER_EMAIL, "role": "owner"}
                sess_token = self._create_session(owner["email"], user_agent=user_agent, remote_ip=remote_ip)
                return {
                    "ok": True,
                    "method": "api_key",
                    "user": owner,
                    "session_token": sess_token,
                }
            raise PermissionError("Chiave Gateway non valida.")

        clean_email = str(email_addr or "").strip().lower()
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM cortical_users WHERE email=?", (clean_email,)).fetchone()
            if row is None:
                raise PermissionError("Credenziali non valide.")
            if not row["password_hash"]:
                raise PermissionError(
                    "Password non ancora creata. Usa il link ricevuto via email oppure la Chiave Gateway."
                )
            if not _verify_password(password, str(row["password_hash"]), str(row["password_salt"])):
                raise PermissionError("Email o password non corrette.")
            now = time.time()
            conn.execute("UPDATE cortical_users SET last_login_at=? WHERE email=?", (now, clean_email))
            user_sanitized = self._sanitize_user(row)

        sess_token = self._create_session(clean_email, user_agent=user_agent, remote_ip=remote_ip)
        return {
            "ok": True,
            "method": "password",
            "user": user_sanitized,
            "session_token": sess_token,
        }

    def logout(self, session_token: str) -> dict[str, Any]:
        if session_token:
            with self._connect() as conn:
                conn.execute(
                    "DELETE FROM cortical_sessions WHERE session_token_hash=?",
                    (_sha256_hex(session_token.strip()),),
                )
        return {"ok": True}

    def check_request_auth(
        self,
        headers: dict[str, str],
        query: dict[str, list[str]],
        client_ip: str,
        path: str,
    ) -> dict[str, Any]:
        cfg = self._get_config_map()
        auth_enabled = cfg.get("auth_enabled", "true") == "true"
        allow_localhost = cfg.get("allow_localhost_bypass", "true") == "true"
        norm_headers = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
        host_hdr = norm_headers.get("host", "").split(":", 1)[0].strip().lower()

        has_proxy_headers = any(
            norm_headers.get(h)
            for h in ("x-forwarded-for", "x-forwarded-host", "cf-connecting-ip", "x-real-ip", "forwarded")
        )
        local_ips = {"127.0.0.1", "::1", "::ffff:127.0.0.1", "localhost", ""}
        local_hosts = {"127.0.0.1", "localhost", "::1", "[::1]", ""}
        is_remote = bool(has_proxy_headers or (client_ip not in local_ips) or (host_hdr not in local_hosts))

        if path in _EXEMPT_EXACT_PATHS or path.startswith("/ui/") or path.startswith("/examples/"):
            return {
                "authorized": True,
                "auth_enabled": auth_enabled,
                "is_remote": is_remote,
                "method": "exempt_route",
            }

        cookies = _parse_cookies(norm_headers.get("cookie", ""))
        auth_hdr = norm_headers.get("authorization", "")
        bearer_tok = auth_hdr[7:].strip() if auth_hdr.lower().startswith("bearer ") else ""
        key_candidate = (
            norm_headers.get("x-cortical-key", "").strip()
            or (query.get("key") or [""])[0].strip()
            or cookies.get("cortical_key", "").strip()
            or (bearer_tok if bearer_tok.startswith("ctk_") else "")
        )
        cfg_key = cfg.get("gateway_api_key", "")
        if key_candidate and cfg_key and hmac.compare_digest(key_candidate, cfg_key):
            users = self.list_users()
            return {
                "authorized": True,
                "auth_enabled": auth_enabled,
                "is_remote": is_remote,
                "method": "api_key",
                "set_key_cookie": key_candidate if (query.get("key") or [""])[0].strip() else "",
                "user": users[0] if users else {"email": DEFAULT_OWNER_EMAIL, "role": "owner"},
            }

        sess_candidate = (
            cookies.get("cortical_session", "").strip()
            or (bearer_tok if bearer_tok and not bearer_tok.startswith("ctk_") else "")
        )
        if sess_candidate:
            now = time.time()
            with self._connect() as conn:
                srow = conn.execute(
                    "SELECT email, expires_at FROM cortical_sessions WHERE session_token_hash=?",
                    (_sha256_hex(sess_candidate),),
                ).fetchone()
                if srow and float(srow["expires_at"]) > now:
                    urow = conn.execute("SELECT * FROM cortical_users WHERE email=?", (srow["email"],)).fetchone()
                    return {
                        "authorized": True,
                        "auth_enabled": auth_enabled,
                        "is_remote": is_remote,
                        "method": "session",
                        "user": self._sanitize_user(urow) if urow else {"email": srow["email"]},
                    }

        if not auth_enabled or (allow_localhost and not is_remote):
            users = self.list_users()
            return {
                "authorized": True,
                "auth_enabled": auth_enabled,
                "is_remote": is_remote,
                "method": "disabled" if not auth_enabled else "localhost_bypass",
                "user": users[0] if users else {"email": DEFAULT_OWNER_EMAIL, "role": "owner"},
            }

        return {
            "authorized": False,
            "auth_enabled": auth_enabled,
            "is_remote": is_remote,
            "method": "none",
            "reason": "Autenticazione richiesta per accesso remoto.",
        }

    def update_duckdns(self, domain: Optional[str] = None, token: Optional[str] = None) -> dict[str, Any]:
        cfg = self._get_config_map()
        dom = (domain or cfg.get("duckdns_domain") or DEFAULT_DUCKDNS_DOMAIN).strip().lower().replace(".duckdns.org", "")
        tok = (token if token is not None else cfg.get("duckdns_token") or "").strip()
        public_ip = ""
        try:
            with urllib.request.urlopen("https://api.ipify.org", timeout=4.0) as resp:
                public_ip = resp.read().decode("utf-8", errors="ignore").strip()
        except Exception:  # noqa: BLE001
            public_ip = ""

        if not tok or "<your-duckdns-token>" in tok:
            self._set_config_key("duckdns_last_ip", public_ip)
            self._set_config_key("duckdns_last_status", "missing_token")
            return {
                "ok": False,
                "domain": f"{dom}.duckdns.org",
                "public_ip": public_ip,
                "status": "missing_token",
                "detail": "Inserisci DUCKDNS_TOKEN in Studio -> Gateway per aggiornare il record DNS gratuito.",
            }

        url = (
            f"https://www.duckdns.org/update?domains={urllib.parse.quote(dom)}"
            f"&token={urllib.parse.quote(tok)}&ip={urllib.parse.quote(public_ip)}"
        )
        try:
            with urllib.request.urlopen(url, timeout=6.0) as resp:
                body = resp.read().decode("utf-8", errors="ignore").strip()
            ok = body == "OK"
            self._set_config_key("duckdns_last_ip", public_ip)
            self._set_config_key("duckdns_last_status", body)
            return {
                "ok": ok,
                "domain": f"{dom}.duckdns.org",
                "public_ip": public_ip,
                "status": body,
            }
        except Exception as exc:  # noqa: BLE001
            self._set_config_key("duckdns_last_status", f"error:{exc}")
            return {"ok": False, "domain": f"{dom}.duckdns.org", "public_ip": public_ip, "error": str(exc)}

    def stop_tunnel(self) -> dict[str, Any]:
        with _GLOBAL_TUNNEL.lock:
            proc = _GLOBAL_TUNNEL.proc
            _GLOBAL_TUNNEL.proc = None
            _GLOBAL_TUNNEL.public_url = ""
            _GLOBAL_TUNNEL.provider = ""
            if proc is not None:
                with contextlib.suppress(Exception):
                    proc.terminate()
        self._set_config_key("public_gateway_url", "")
        return {"ok": True, "running": False}

    def start_tunnel(
        self,
        *,
        provider: str = "auto",
        local_port: Optional[int] = None,
        wait_sec: float = 12.0,
        force: bool = False,
    ) -> dict[str, Any]:
        port = int(local_port or self.local_port)
        with _GLOBAL_TUNNEL.lock:
            if (
                not force
                and _GLOBAL_TUNNEL.proc is not None
                and _GLOBAL_TUNNEL.proc.poll() is None
                and _GLOBAL_TUNNEL.public_url
            ):
                return {
                    "ok": True,
                    "running": True,
                    "provider": _GLOBAL_TUNNEL.provider,
                    "public_url": _GLOBAL_TUNNEL.public_url,
                }
            if _GLOBAL_TUNNEL.proc is not None:
                with contextlib.suppress(Exception):
                    _GLOBAL_TUNNEL.proc.terminate()
                _GLOBAL_TUNNEL.proc = None
                _GLOBAL_TUNNEL.public_url = ""

        candidates: list[tuple[str, list[str]]] = []
        cf_bin = shutil.which("cloudflared") or str(Path.home() / ".cortical_data" / "bin" / "cloudflared")
        if provider in {"auto", "cloudflared"} and Path(cf_bin).exists():
            candidates.append(
                ("cloudflared", [str(cf_bin), "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{port}"])
            )
        ssh_bin = shutil.which("ssh") or "/usr/bin/ssh"
        if provider in {"auto", "localhost.run"} and Path(ssh_bin).exists():
            candidates.append(
                (
                    "localhost.run",
                    [
                        ssh_bin,
                        "-o",
                        "StrictHostKeyChecking=no",
                        "-o",
                        "UserKnownHostsFile=/dev/null",
                        "-o",
                        "ExitOnForwardFailure=yes",
                        "-o",
                        "ServerAliveInterval=30",
                        "-T",
                        "-R",
                        f"80:127.0.0.1:{port}",
                        "nokey@localhost.run",
                    ],
                )
            )
        if provider in {"auto", "pinggy"} and Path(ssh_bin).exists():
            candidates.append(
                (
                    "pinggy",
                    [
                        ssh_bin,
                        "-p",
                        "443",
                        "-o",
                        "StrictHostKeyChecking=no",
                        "-o",
                        "UserKnownHostsFile=/dev/null",
                        "-o",
                        "ServerAliveInterval=30",
                        "-T",
                        f"-R0:127.0.0.1:{port}",
                        "a.pinggy.io",
                    ],
                )
            )

        for prov_name, cmd in candidates:
            found_ev = threading.Event()
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
            except Exception as exc:  # noqa: BLE001
                with _GLOBAL_TUNNEL.lock:
                    _GLOBAL_TUNNEL.last_error = str(exc)
                continue

            with _GLOBAL_TUNNEL.lock:
                _GLOBAL_TUNNEL.proc = proc
                _GLOBAL_TUNNEL.provider = prov_name
                _GLOBAL_TUNNEL.public_url = ""
                _GLOBAL_TUNNEL.started_at = time.time()
                _GLOBAL_TUNNEL.last_error = ""
                _GLOBAL_TUNNEL.log_tail = []

            def _reader(p: subprocess.Popen[str], pname: str, ev: threading.Event) -> None:
                assert p.stdout is not None
                for raw_line in p.stdout:
                    clean_line = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", raw_line).strip()
                    if not clean_line:
                        continue
                    with _GLOBAL_TUNNEL.lock:
                        _GLOBAL_TUNNEL.log_tail.append(clean_line[:240])
                        _GLOBAL_TUNNEL.log_tail = _GLOBAL_TUNNEL.log_tail[-25:]
                    if pname == "localhost.run" and "localhost.run" in clean_line and "tunneled with tls" not in clean_line.lower():
                        # Skip doc/banner URLs like https://localhost.run/docs/
                        pass
                    for pat in _URL_PATTERNS:
                        m = pat.search(clean_line)
                        if m:
                            cand_url = m.group(1).rstrip("/")
                            if cand_url.endswith("localhost.run"):
                                continue
                            with _GLOBAL_TUNNEL.lock:
                                _GLOBAL_TUNNEL.public_url = cand_url
                            ev.set()
                            break

            t = threading.Thread(target=_reader, args=(proc, prov_name, found_ev), daemon=True)
            t.start()
            found_ev.wait(timeout=wait_sec)

            with _GLOBAL_TUNNEL.lock:
                live_url = _GLOBAL_TUNNEL.public_url
                alive = proc.poll() is None

            if alive and live_url:
                self._set_config_key("public_gateway_url", live_url)
                self._set_config_key("tunnel_provider", prov_name)
                return {
                    "ok": True,
                    "running": True,
                    "provider": prov_name,
                    "public_url": live_url,
                }
            with contextlib.suppress(Exception):
                proc.terminate()
            with _GLOBAL_TUNNEL.lock:
                _GLOBAL_TUNNEL.proc = None

        return {
            "ok": False,
            "running": False,
            "provider": provider,
            "public_url": self.get_public_url(),
            "error": _GLOBAL_TUNNEL.last_error or "Impossibile stabilire un tunnel HTTPS pubblico.",
            "log_tail": list(_GLOBAL_TUNNEL.log_tail[-6:]),
        }

    def send_access_email(
        self,
        *,
        recipient_email: str = DEFAULT_OWNER_EMAIL,
        base_public_url: Optional[str] = None,
        setup_token: Optional[str] = None,
        telegram_bot_token: str = "",
        telegram_chat_id: str = "",
    ) -> dict[str, Any]:
        clean_email = str(recipient_email or DEFAULT_OWNER_EMAIL).strip().lower()
        invite = None
        if not setup_token:
            invite = self.register_or_invite_user(clean_email)
            setup_token = str(invite["setup_token"])

        cfg = self._get_config_map()
        api_key = cfg.get("gateway_api_key", "")
        public_url = (base_public_url or self.get_public_url() or f"http://127.0.0.1:{self.local_port}").rstrip("/")
        portal_url = cfg.get("github_portal_url", DEFAULT_GITHUB_PORTAL_URL)
        setup_url = f"{public_url}/auth/setup-password?token={urllib.parse.quote(setup_token)}&email={urllib.parse.quote(clean_email)}"
        local_setup_url = f"http://127.0.0.1:{self.local_port}/auth/setup-password?token={urllib.parse.quote(setup_token)}&email={urllib.parse.quote(clean_email)}"
        quick_key_url = f"{public_url}/?key={urllib.parse.quote(api_key)}"

        subject = "Cortical Mission Control — Crea la tua password e accedi da remoto"
        text_body = (
            f"Ciao {DEFAULT_OWNER_NAME},\n\n"
            f"il servizio Cortical Chat & Mission Control e' pronto per l'accesso remoto.\n\n"
            f"1) CREA LA TUA PASSWORD (Account {clean_email}, limite massimo utenti: {cfg.get('max_users', '1')}):\n"
            f"   Link diretto remoto: {setup_url}\n"
            f"   Link locale di backup: {local_setup_url}\n\n"
            f"2) CHIAVE GATEWAY OPZIONALE (per Chat Web, API, pi, OpenCode, OpenClaw, Codex, Claude, DeepSeek):\n"
            f"   Chiave (X-Cortical-Key): {api_key}\n"
            f"   Accesso rapido 1-click: {quick_key_url}\n\n"
            f"3) PORTALE & DOMINIO PERSONALE:\n"
            f"   Portale GitHub Pages: {portal_url}\n"
            f"   Tunnel HTTPS attivo: {public_url}\n\n"
            f"Il token di setup scade tra 72 ore ed e' monouso.\n"
        )
        html_body = f"""<!DOCTYPE html>
<html lang="it">
<body style="font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;background:#0f172a;color:#e2e8f0;padding:24px;">
  <div style="max-width:620px;margin:0 auto;background:#1e293b;border:1px solid #334155;border-radius:12px;padding:24px;">
    <h2 style="margin-top:0;color:#38bdf8;">Cortical Mission Control — Accesso Remoto</h2>
    <p>Ciao Carlo, il tuo account <strong>{clean_email}</strong> e' registrato (limite utenti: <strong>1/{cfg.get('max_users', '1')}</strong>).</p>
    <p>
      <a href="{setup_url}" style="display:inline-block;background:#0284c7;color:#ffffff;padding:12px 18px;border-radius:8px;text-decoration:none;font-weight:700;">
        Crea la tua Password &amp; Entra
      </a>
    </p>
    <p style="font-size:13px;color:#94a3b8;">
      Link Setup Remoto: <a href="{setup_url}" style="color:#38bdf8;">{setup_url}</a><br/>
      Portale GitHub Pages: <a href="{portal_url}" style="color:#38bdf8;">{portal_url}</a><br/>
      Accesso 1-click con Chiave: <a href="{quick_key_url}" style="color:#38bdf8;">{quick_key_url}</a>
    </p>
    <div style="background:#0f172a;border:1px solid #334155;border-radius:8px;padding:12px;font-family:monospace;font-size:13px;">
      Header: X-Cortical-Key<br/>
      Chiave: <strong>{api_key}</strong>
    </div>
  </div>
</body>
</html>"""

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = f"Cortical Gateway <{os.environ.get('CORTICAL_SMTP_FROM', clean_email)}>"
        msg["To"] = clean_email
        msg["Date"] = email.utils.formatdate(localtime=True)
        msg.set_content(text_body)
        msg.add_alternative(html_body, subtype="html")

        eml_path = self.outbox_dir / "cortical_invite_latest.eml"
        html_path = self.outbox_dir / "cortical_invite_latest.html"
        eml_path.write_bytes(msg.as_bytes())
        html_path.write_text(html_body, encoding="utf-8")

        attempts: list[dict[str, Any]] = []
        delivered = False
        sent_via: list[str] = []

        # Transport 1: Explicit SMTP relay if configured (env or DB config)
        smtp_host = (os.environ.get("CORTICAL_SMTP_HOST") or cfg.get("smtp_host") or "").strip()
        if smtp_host:
            smtp_port = int(os.environ.get("CORTICAL_SMTP_PORT") or cfg.get("smtp_port") or 587)
            smtp_user = (os.environ.get("CORTICAL_SMTP_USER") or cfg.get("smtp_user") or "").strip()
            smtp_pass = (os.environ.get("CORTICAL_SMTP_PASS") or cfg.get("smtp_pass") or "").strip()
            if smtp_user and not os.environ.get("CORTICAL_SMTP_FROM"):
                del msg["From"]
                msg["From"] = f"Cortical Gateway <{smtp_user}>"
            try:
                with smtplib.SMTP(smtp_host, smtp_port, timeout=10.0) as srv:
                    srv.starttls()
                    if smtp_user and smtp_pass:
                        srv.login(smtp_user, smtp_pass)
                    srv.send_message(msg)
                delivered = True
                sent_via.append(f"smtp:{smtp_host}")
                attempts.append({"transport": "smtp_relay", "ok": True})
            except Exception as exc:  # noqa: BLE001
                attempts.append({"transport": "smtp_relay", "ok": False, "error": str(exc)})

        # Transport 2: Direct MX lookup (works if ISP allows outbound port 25)
        if not delivered and shutil.which("dig"):
            try:
                domain_part = clean_email.split("@", 1)[1]
                dig_out = subprocess.run(
                    ["dig", "+short", "MX", domain_part],
                    capture_output=True,
                    text=True,
                    timeout=4.0,
                    check=False,
                ).stdout.strip()
                mx_hosts = [
                    line.split()[-1].rstrip(".")
                    for line in dig_out.splitlines()
                    if line.strip()
                ]
                for mx in mx_hosts[:2]:
                    try:
                        with smtplib.SMTP(mx, 25, timeout=5.0) as srv:
                            srv.ehlo_or_helo_if_needed()
                            srv.send_message(msg)
                        delivered = True
                        sent_via.append(f"direct_mx:{mx}")
                        attempts.append({"transport": f"direct_mx:{mx}", "ok": True})
                        break
                    except Exception as exc:  # noqa: BLE001
                        attempts.append({"transport": f"direct_mx:{mx}", "ok": False, "error": str(exc)})
            except Exception as exc:  # noqa: BLE001
                attempts.append({"transport": "direct_mx", "ok": False, "error": str(exc)})

        # Transport 3: macOS Apple Mail app if running or sendmail queue fallback
        if not delivered and platform.system() == "Darwin" and shutil.which("osascript"):
            try:
                safe_subj = subject.replace('"', '\\"')
                safe_body = text_body.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
                apple_script = (
                    'tell application "System Events" to set mailRunning to (name of processes) contains "Mail"\n'
                    'if not mailRunning then error "Apple Mail not running"\n'
                    'tell application "Mail"\n'
                    '  if (count of accounts) is 0 then error "No Apple Mail accounts configured"\n'
                    f'  set newMsg to make new outgoing message with properties {{subject:"{safe_subj}", content:"{safe_body}", visible:false}}\n'
                    '  tell newMsg\n'
                    f'    make new to recipient at end of to recipients with properties {{address:"{clean_email}"}}\n'
                    '    send\n'
                    '  end tell\n'
                    'end tell'
                )
                r = subprocess.run(
                    ["osascript", "-e", apple_script],
                    capture_output=True,
                    text=True,
                    timeout=6.0,
                    check=False,
                )
                if r.returncode == 0:
                    delivered = True
                    sent_via.append("apple_mail")
                    attempts.append({"transport": "apple_mail", "ok": True})
                else:
                    attempts.append({"transport": "apple_mail", "ok": False, "error": (r.stderr or r.stdout).strip()})
            except Exception as exc:  # noqa: BLE001
                attempts.append({"transport": "apple_mail", "ok": False, "error": str(exc)})

        # Transport 4: Optional Telegram notification fallback if configured in env/param
        tg_tok = (telegram_bot_token or os.environ.get("CORTICAL_TELEGRAM_BOT_TOKEN") or "").strip()
        tg_chat = (telegram_chat_id or os.environ.get("CORTICAL_TELEGRAM_CHAT_ID") or "").strip()
        if tg_tok and tg_chat:
            try:
                req_data = urllib.parse.urlencode(
                    {"chat_id": tg_chat, "text": text_body[:3800], "disable_web_page_preview": "true"}
                ).encode("utf-8")
                req = urllib.request.Request(
                    f"https://api.telegram.org/bot{tg_tok}/sendMessage",
                    data=req_data,
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=6.0) as resp:
                    tg_ok = resp.status == 200
                if tg_ok:
                    sent_via.append("telegram_backup")
                attempts.append({"transport": "telegram_backup", "ok": tg_ok})
            except Exception as exc:  # noqa: BLE001
                attempts.append({"transport": "telegram_backup", "ok": False, "error": str(exc)})

        return {
            "ok": True,
            "delivered_externally": delivered,
            "sent_via": sent_via,
            "recipient_email": clean_email,
            "public_url": public_url,
            "portal_url": portal_url,
            "setup_url": setup_url,
            "local_setup_url": local_setup_url,
            "quick_key_url": quick_key_url,
            "gateway_key_masked": _mask_secret(api_key),
            "outbox_eml": str(eml_path),
            "outbox_html": str(html_path),
            "attempts": attempts,
        }


def render_auth_portal_html(
    *,
    mode: str = "login",
    token: str = "",
    email_hint: str = DEFAULT_OWNER_EMAIL,
    public_url: str = "",
    max_users: int = 1,
    registered_count: int = 1,
) -> str:
    """Renders standalone dark-mode login & password-setup page for /auth/login and /auth/setup-password."""
    esc_token = html_escape(token)
    esc_email = html_escape(email_hint or DEFAULT_OWNER_EMAIL)
    esc_pub = html_escape(public_url)
    is_setup = mode == "setup"
    title = "Crea la tua Password — Cortical" if is_setup else "Accesso Remoto — Cortical"
    return f"""<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <style>
    :root {{ --bg:#0b1120; --panel:#111827; --border:#1f2937; --text:#f1f5f9; --muted:#94a3b8; --accent:#38bdf8; --ok:#34d399; --err:#f87171; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; min-height:100vh; display:flex; align-items:center; justify-content:center; padding:20px; background:radial-gradient(circle at top,#162544,#0b1120 65%); color:var(--text); font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif; }}
    .card {{ width:100%; max-width:440px; background:var(--panel); border:1px solid var(--border); border-radius:16px; padding:26px; box-shadow:0 20px 50px rgba(0,0,0,0.45); }}
    .badge {{ display:inline-block; padding:4px 10px; border-radius:999px; background:rgba(56,189,248,0.14); color:var(--accent); font-size:12px; font-weight:700; margin-bottom:10px; }}
    h1 {{ margin:0 0 6px; font-size:1.3rem; }}
    p.sub {{ margin:0 0 18px; color:var(--muted); font-size:0.88rem; line-height:1.45; }}
    .tabs {{ display:flex; gap:8px; margin-bottom:16px; }}
    .tab {{ flex:1; text-align:center; padding:9px; border-radius:10px; border:1px solid var(--border); background:#0f172a; color:var(--muted); cursor:pointer; font-size:0.84rem; font-weight:600; }}
    .tab.active {{ background:rgba(56,189,248,0.16); color:var(--accent); border-color:rgba(56,189,248,0.45); }}
    label {{ display:block; font-size:0.78rem; color:var(--muted); margin:10px 0 4px; font-weight:600; }}
    input {{ width:100%; padding:10px 12px; border-radius:9px; border:1px solid #334155; background:#0b1220; color:var(--text); font-size:0.92rem; }}
    button.primary {{ width:100%; margin-top:16px; padding:11px; border:0; border-radius:10px; background:#0284c7; color:#fff; font-weight:700; font-size:0.94rem; cursor:pointer; }}
    button.primary:hover {{ background:#0369a1; }}
    .msg {{ margin-top:12px; padding:10px 12px; border-radius:9px; font-size:0.83rem; display:none; }}
    .msg.ok {{ display:block; background:rgba(52,211,153,0.14); border:1px solid rgba(52,211,153,0.4); color:var(--ok); }}
    .msg.err {{ display:block; background:rgba(248,113,113,0.14); border:1px solid rgba(248,113,113,0.4); color:var(--err); }}
    .foot {{ margin-top:14px; font-size:0.76rem; color:var(--muted); text-align:center; }}
  </style>
</head>
<body>
  <div class="card">
    <span class="badge">Cortical Gateway · Account {registered_count}/{max_users}</span>
    <h1>{title}</h1>
    <p class="sub">Accesso protetto a chat, voce e agenti locali. {f'Gateway: {esc_pub}' if esc_pub else ''}</p>
    <div class="tabs">
      <div class="tab {'active' if not is_setup else ''}" id="tab-login" onclick="switchPane('login')">🔐 Accedi</div>
      <div class="tab {'active' if is_setup else ''}" id="tab-setup" onclick="switchPane('setup')">🔑 Crea Password</div>
    </div>

    <div id="pane-login" style="display:{'none' if is_setup else 'block'};">
      <label for="login-email">Email</label>
      <input id="login-email" type="email" value="{esc_email}" placeholder="owner@example.com" />
      <label for="login-pw">Password (oppure usa la Chiave Gateway sotto)</label>
      <input id="login-pw" type="password" placeholder="••••••••" />
      <label for="login-key">Oppure Chiave Gateway (X-Cortical-Key)</label>
      <input id="login-key" type="password" placeholder="ctk_..." />
      <button class="primary" onclick="doLogin()">Entra in Cortical</button>
    </div>

    <div id="pane-setup" style="display:{'block' if is_setup else 'none'};">
      <label for="setup-email">Account Email</label>
      <input id="setup-email" type="email" value="{esc_email}" />
      <label for="setup-token">Token Email (o Chiave Gateway)</label>
      <input id="setup-token" type="text" value="{esc_token}" placeholder="ctp_... oppure ctk_..." />
      <label for="setup-pw1">Nuova Password (min 8 caratteri)</label>
      <input id="setup-pw1" type="password" placeholder="Minimo 8 caratteri" />
      <label for="setup-pw2">Conferma Password</label>
      <input id="setup-pw2" type="password" placeholder="Ripeti password" />
      <button class="primary" onclick="doSetupPassword()">Imposta Password &amp; Accedi</button>
    </div>

    <div class="msg" id="auth-msg"></div>
    <div class="foot">Registrazioni chiuse al limite configurato ({registered_count}/{max_users} utenti).</div>
  </div>
  <script>
    function switchPane(mode) {{
      document.getElementById('pane-login').style.display = mode === 'login' ? 'block' : 'none';
      document.getElementById('pane-setup').style.display = mode === 'setup' ? 'block' : 'none';
      document.getElementById('tab-login').classList.toggle('active', mode === 'login');
      document.getElementById('tab-setup').classList.toggle('active', mode === 'setup');
      document.getElementById('auth-msg').className = 'msg';
    }}
    function showMsg(txt, ok) {{
      const el = document.getElementById('auth-msg');
      el.textContent = txt;
      el.className = 'msg ' + (ok ? 'ok' : 'err');
    }}
    async function doLogin() {{
      const email = document.getElementById('login-email').value.trim();
      const password = document.getElementById('login-pw').value;
      const api_key = document.getElementById('login-key').value.trim();
      const r = await fetch('/api/auth/login', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ email, password, api_key }}),
      }});
      const d = await r.json();
      if (!r.ok) return showMsg(d.error || 'Accesso fallito', false);
      if (d.session_token) localStorage.setItem('cortical_session_token', d.session_token);
      if (api_key) localStorage.setItem('cortical_gateway_key', api_key);
      showMsg('Accesso effettuato! Reindirizzamento...', true);
      setTimeout(() => {{ location.href = '/'; }}, 450);
    }}
    async function doSetupPassword() {{
      const email = document.getElementById('setup-email').value.trim();
      const tok = document.getElementById('setup-token').value.trim();
      const pw1 = document.getElementById('setup-pw1').value;
      const pw2 = document.getElementById('setup-pw2').value;
      if (pw1.length < 8) return showMsg('La password deve avere almeno 8 caratteri.', false);
      if (pw1 !== pw2) return showMsg('Le password non coincidono.', false);
      const payload = tok.startsWith('ctk_')
        ? {{ email, api_key: tok, password: pw1 }}
        : {{ email, token: tok, password: pw1 }};
      const r = await fetch('/api/auth/setup-password', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify(payload),
      }});
      const d = await r.json();
      if (!r.ok) return showMsg(d.error || 'Errore creazione password', false);
      if (d.session_token) localStorage.setItem('cortical_session_token', d.session_token);
      showMsg('Password impostata! Accesso in corso...', true);
      setTimeout(() => {{ location.href = '/'; }}, 500);
    }}
  </script>
</body>
</html>"""


def html_escape(val: str) -> str:
    return (
        str(val or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )
