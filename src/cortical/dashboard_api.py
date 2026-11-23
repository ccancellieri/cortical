"""Stdlib-only Control Plane Backend API for the Cortical Dashboard.

Provides multi-tenant RBAC (`principal_id`), categorized settings with inline validation,
async Merkle-tree crawl job management with live progress streaming, live model health probes,
safe drag-and-drop file uploads, and RAG observability (FTS5 search, episodes, citation verification).
"""

from __future__ import annotations

import base64
import copy
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

from .composers.tools import inspect_composed_tools, install_composed_tool, test_composed_tool
from .wiki.store import DEFAULT_IGNORE_PATTERNS, KnowledgeStore, _normalize_principal
from .workspace import resolve_default_db

EMBEDDING_CATALOG: dict[str, dict[str, Any]] = {
    "nomic-embed-text": {"dimensions": 768, "tokenizer_family": "bert-wordpiece", "ram_gb": 0.6, "provider_type": "local"},
    "mxbai-embed-large": {"dimensions": 1024, "tokenizer_family": "bert-wordpiece", "ram_gb": 1.2, "provider_type": "local"},
    "bge-m3": {"dimensions": 1024, "tokenizer_family": "xlm-roberta", "ram_gb": 2.2, "provider_type": "local"},
    "all-minilm": {"dimensions": 384, "tokenizer_family": "bert-wordpiece", "ram_gb": 0.2, "provider_type": "local"},
    "text-embedding-3-small": {"dimensions": 1536, "tokenizer_family": "cl100k_base", "ram_gb": 0.0, "provider_type": "remote"},
    "text-embedding-3-large": {"dimensions": 3072, "tokenizer_family": "cl100k_base", "ram_gb": 0.0, "provider_type": "remote"},
}

LLM_CATALOG: dict[str, dict[str, Any]] = {
    "qwen3.5:9b-q3_k_xl": {"max_context_window": 131072, "ram_gb": 5.1, "provider_type": "local"},
    "qwen3.8:27b-iq2_xxs": {"max_context_window": 32768, "ram_gb": 7.2, "provider_type": "local"},
    "qwen2.5:1.5b": {"max_context_window": 32768, "ram_gb": 1.0, "provider_type": "local"},
    "qwen3:8b": {"max_context_window": 32768, "ram_gb": 5.2, "provider_type": "local"},
    "minicpm-ocr:latest": {"max_context_window": 32768, "ram_gb": 4.8, "provider_type": "local"},
    "gpt-4o-mini": {"max_context_window": 128000, "ram_gb": 0.0, "provider_type": "remote"},
    "claude-3-5-sonnet": {"max_context_window": 200000, "ram_gb": 0.0, "provider_type": "remote"},
}


def default_dashboard_settings(db_path: Optional[Path] = None) -> dict[str, Any]:
    resolved_db = str(db_path or resolve_default_db())
    return {
        "general_rbac": {
            "default_principal_id": "local_owner",
            "isolation_policy": "strict",
            "allow_tenant_creation": True,
            "require_citation_rbac": True,
        },
        "search_rag": {
            "fts5_tokenizer": "unicode61",
            "default_depth": 1,
            "default_limit": 10,
            "citation_threshold": 0.45,
            "bm25_k1": 1.2,
        },
        "storage_crawler": {
            "db_path": resolved_db,
            "ignore_patterns": list(DEFAULT_IGNORE_PATTERNS),
            "max_file_size_kb": 2048,
            "chunk_size": 1200,
            "chunk_overlap": 150,
            "auto_crawl_on_upload": True,
        },
        "models": {
            "embedding": {
                "provider_type": "local",
                "endpoint": "http://127.0.0.1:11434",
                "model_id": "nomic-embed-text",
                "dimensions": 768,
                "tokenizer_family": "bert-wordpiece",
                "ram_gb": 0.6,
            },
            "llm": {
                "provider_type": "local",
                "endpoint": "http://127.0.0.1:11434",
                "model_id": "qwen3.5:9b-q3_k_xl",
                "max_context_window": 131072,
                "ram_gb": 5.1,
            },
        },
        "advanced": {
            "log_level": "INFO",
            "sqlite_wal": True,
            "max_concurrent_crawls": 2,
            "request_timeout_sec": 10,
        },
    }


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def validate_filesystem_path(raw_path: str, *, require_dir: bool = True) -> dict[str, Any]:
    raw = str(raw_path or "").strip()
    if not raw:
        return {"valid": False, "error": "Path cannot be empty.", "resolved": ""}
    try:
        p = Path(raw).expanduser()
        resolved = str(p.resolve()) if p.exists() else str(p.absolute())
    except Exception as exc:  # noqa: BLE001
        return {"valid": False, "error": f"Invalid path syntax: {exc}", "resolved": ""}

    if not p.exists():
        return {
            "valid": False,
            "exists": False,
            "is_dir": False,
            "readable": False,
            "writable": False,
            "resolved": resolved,
            "error": f"Path does not exist: {resolved}",
        }
    if require_dir and not p.is_dir():
        return {
            "valid": False,
            "exists": True,
            "is_dir": False,
            "readable": os.access(p, os.R_OK),
            "writable": os.access(p, os.W_OK),
            "resolved": resolved,
            "error": "Path exists but is not a directory.",
        }
    readable = os.access(p, os.R_OK)
    writable = os.access(p, os.W_OK)
    if not readable:
        return {
            "valid": False,
            "exists": True,
            "is_dir": p.is_dir(),
            "readable": False,
            "writable": writable,
            "resolved": resolved,
            "error": "Directory is not readable by the current user.",
        }
    return {
        "valid": True,
        "exists": True,
        "is_dir": p.is_dir(),
        "readable": readable,
        "writable": writable,
        "resolved": resolved,
        "error": "",
    }


def validate_dashboard_settings(settings: dict[str, Any]) -> dict[str, Any]:
    errors: dict[str, str] = {}
    gr = settings.get("general_rbac") or {}
    if not str(gr.get("default_principal_id") or "").strip():
        errors["general_rbac.default_principal_id"] = "Default principal_id is required."
    if gr.get("isolation_policy") not in {"strict", "shared_read"}:
        errors["general_rbac.isolation_policy"] = "Isolation policy must be 'strict' or 'shared_read'."

    sr = settings.get("search_rag") or {}
    if sr.get("fts5_tokenizer") not in {"unicode61", "porter", "ascii"}:
        errors["search_rag.fts5_tokenizer"] = "Tokenizer must be unicode61, porter, or ascii."
    try:
        depth = int(sr.get("default_depth", 1))
        if depth < 0 or depth > 2:
            errors["search_rag.default_depth"] = "Depth must be between 0 and 2."
    except (TypeError, ValueError):
        errors["search_rag.default_depth"] = "Depth must be an integer."
    try:
        limit = int(sr.get("default_limit", 10))
        if limit < 1 or limit > 100:
            errors["search_rag.default_limit"] = "Limit must be between 1 and 100."
    except (TypeError, ValueError):
        errors["search_rag.default_limit"] = "Limit must be an integer."
    try:
        thr = float(sr.get("citation_threshold", 0.45))
        if thr < 0.1 or thr > 1.0:
            errors["search_rag.citation_threshold"] = "Citation threshold must be between 0.10 and 1.00."
    except (TypeError, ValueError):
        errors["search_rag.citation_threshold"] = "Citation threshold must be numeric."

    sc = settings.get("storage_crawler") or {}
    db_p = str(sc.get("db_path") or "").strip()
    if not db_p:
        errors["storage_crawler.db_path"] = "SQLite database path is required."
    try:
        cs = int(sc.get("chunk_size", 1200))
        co = int(sc.get("chunk_overlap", 150))
        if cs < 256 or cs > 8192:
            errors["storage_crawler.chunk_size"] = "Chunk size must be between 256 and 8192 characters."
        if co < 0 or co >= cs:
            errors["storage_crawler.chunk_overlap"] = "Chunk overlap must be >= 0 and smaller than chunk size."
    except (TypeError, ValueError):
        errors["storage_crawler.chunk_size"] = "Chunk size and overlap must be integers."

    md = settings.get("models") or {}
    for role in ("embedding", "llm"):
        cfg = md.get(role) or {}
        ep = str(cfg.get("endpoint") or "").strip()
        if not (ep.startswith("http://") or ep.startswith("https://")):
            errors[f"models.{role}.endpoint"] = "Endpoint must start with http:// or https://."
        if not str(cfg.get("model_id") or "").strip():
            errors[f"models.{role}.model_id"] = "Model identifier cannot be empty."

    adv = settings.get("advanced") or {}
    if adv.get("log_level") not in {"DEBUG", "INFO", "WARN", "ERROR"}:
        errors["advanced.log_level"] = "Log level must be DEBUG, INFO, WARN, or ERROR."
    try:
        tsec = int(adv.get("request_timeout_sec", 10))
        if tsec < 2 or tsec > 120:
            errors["advanced.request_timeout_sec"] = "Timeout must be between 2 and 120 seconds."
    except (TypeError, ValueError):
        errors["advanced.request_timeout_sec"] = "Timeout must be an integer."

    return {"valid": len(errors) == 0, "errors": errors}


class CrawlJobManager:
    """Thread-safe background job runner for async Merkle-tree delta/full crawls."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, dict[str, Any]] = {}

    def start_job(
        self,
        store: KnowledgeStore,
        *,
        root_id: Optional[str] = None,
        principal_id: str = "local_owner",
        full_reindex: bool = False,
        embedding_model: str = "",
        embedding_dim: int = 0,
        sanitize: bool = False,
        privacy_profile: str = "medium",
    ) -> dict[str, Any]:
        job_id = "crawl_" + uuid.uuid4().hex[:10]
        now = time.time()
        state: dict[str, Any] = {
            "job_id": job_id,
            "root_id": root_id,
            "principal_id": _normalize_principal(principal_id),
            "mode": "full_reindex" if full_reindex else "delta_sync",
            "status": "running",
            "processed": 0,
            "total": 0,
            "percent": 0,
            "logs": [f"[{time.strftime('%H:%M:%S')}] Starting {'Full Re-index' if full_reindex else 'Delta Sync'}..."],
            "summary": None,
            "error": "",
            "started_at": now,
            "finished_at": None,
        }
        with self._lock:
            self._jobs[job_id] = state

        def _on_progress(ev: dict[str, Any]) -> None:
            with self._lock:
                j = self._jobs[job_id]
                j["processed"] = int(ev.get("processed", 0))
                j["total"] = int(ev.get("total", 0))
                j["percent"] = int((j["processed"] / max(1, j["total"])) * 100) if j["total"] else 100
                act = ev.get("action", "scan")
                rel = ev.get("rel_path", "")
                if act in {"added", "modified", "error", "ignored"} or j["processed"] == j["total"]:
                    msg = f"[{time.strftime('%H:%M:%S')}] {act.upper()}: {rel}"
                    if ev.get("message"):
                        msg += f" ({ev['message']})"
                    j["logs"].append(msg)
                    if len(j["logs"]) > 120:
                        j["logs"] = j["logs"][-120:]

        def _worker() -> None:
            try:
                summary = store.crawl_delta(
                    root_id=root_id,
                    principal_id=principal_id,
                    full_reindex=full_reindex,
                    embedding_model=embedding_model,
                    embedding_dim=embedding_dim,
                    sanitize=sanitize,
                    privacy_profile=privacy_profile,
                    progress_cb=_on_progress,
                )
                with self._lock:
                    j = self._jobs[job_id]
                    j["status"] = "completed"
                    j["percent"] = 100
                    j["summary"] = summary
                    j["finished_at"] = time.time()
                    j["logs"].append(
                        f"[{time.strftime('%H:%M:%S')}] DONE: +{summary['added']} added, ~{summary['modified']} modified, "
                        f"={summary['unchanged']} unchanged, -{summary['removed']} removed, !{summary['errors']} errors."
                    )
            except Exception as exc:  # noqa: BLE001
                with self._lock:
                    j = self._jobs[job_id]
                    j["status"] = "error"
                    j["error"] = str(exc)
                    j["finished_at"] = time.time()
                    j["logs"].append(f"[{time.strftime('%H:%M:%S')}] ERROR: {exc}")

        threading.Thread(target=_worker, daemon=True).start()
        return copy.deepcopy(state)

    def get_job(self, job_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            j = self._jobs.get(job_id)
            return copy.deepcopy(j) if j else None

    def latest_job(self, principal_id: Optional[str] = None) -> Optional[dict[str, Any]]:
        with self._lock:
            items = list(self._jobs.values())
        if principal_id and principal_id != "local_owner":
            items = [j for j in items if j["principal_id"] == principal_id]
        if not items:
            return None
        items.sort(key=lambda x: x["started_at"], reverse=True)
        return copy.deepcopy(items[0])


def _default_http_json(url: str, payload: Optional[dict[str, Any]] = None, timeout: float = 4.0) -> tuple[int, dict[str, Any]]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        raw = resp.read().decode("utf-8", errors="replace")
        return resp.status, (json.loads(raw) if raw.strip() else {})


def probe_model_runtime(
    role: str,
    model_cfg: dict[str, Any],
    *,
    timeout: float = 4.0,
    http_fn: Optional[Callable[[str, Optional[dict[str, Any]], float], tuple[int, dict[str, Any]]]] = None,
) -> dict[str, Any]:
    """Runs a lightweight health/inference probe against an Embedding or LLM endpoint."""
    fn = http_fn or _default_http_json
    endpoint = str(model_cfg.get("endpoint") or "http://127.0.0.1:11434").rstrip("/")
    model_id = str(model_cfg.get("model_id") or "")
    provider_type = str(model_cfg.get("provider_type") or "local")
    t0 = time.perf_counter()

    try:
        if "/v1" in endpoint:
            if role == "embedding":
                code, body = fn(f"{endpoint}/embeddings", {"model": model_id, "input": "cortical health probe"}, timeout)
                ms = round((time.perf_counter() - t0) * 1000.0, 1)
                vec = ((body.get("data") or [{}])[0]).get("embedding") or []
                return {
                    "ok": 200 <= code < 300,
                    "status": "online" if 200 <= code < 300 else "offline",
                    "role": role,
                    "model_id": model_id,
                    "endpoint": endpoint,
                    "provider_type": provider_type,
                    "latency_ms": ms,
                    "vector_dim": len(vec) if isinstance(vec, list) else int(model_cfg.get("dimensions") or 0),
                    "detail": f"Embedding probe OK ({len(vec)} dims)" if vec else f"Endpoint responded HTTP {code}",
                }
            code, body = fn(
                f"{endpoint}/chat/completions",
                {"model": model_id, "messages": [{"role": "user", "content": "Reply OK"}], "max_tokens": 4},
                timeout,
            )
            ms = round((time.perf_counter() - t0) * 1000.0, 1)
            reply = (((body.get("choices") or [{}])[0]).get("message") or {}).get("content", "")
            return {
                "ok": 200 <= code < 300,
                "status": "online" if 200 <= code < 300 else "offline",
                "role": role,
                "model_id": model_id,
                "endpoint": endpoint,
                "provider_type": provider_type,
                "latency_ms": ms,
                "detail": f"LLM probe OK: {str(reply).strip()[:40] or 'ready'}",
            }

        # Native Ollama endpoint
        code, tags = fn(f"{endpoint}/api/tags", None, timeout)
        installed = [str(m.get("name") or "") for m in (tags.get("models") or []) if isinstance(m, dict)]
        has_model = any(m == model_id or m.startswith(model_id + ":") for m in installed)
        if role == "embedding":
            if not has_model:
                ms = round((time.perf_counter() - t0) * 1000.0, 1)
                return {
                    "ok": False,
                    "status": "offline",
                    "role": role,
                    "model_id": model_id,
                    "endpoint": endpoint,
                    "provider_type": provider_type,
                    "latency_ms": ms,
                    "detail": f"Model '{model_id}' not pulled in Ollama. Run: ollama pull {model_id}",
                }
            ecode, ebody = fn(f"{endpoint}/api/embeddings", {"model": model_id, "prompt": "cortical probe"}, timeout)
            ms = round((time.perf_counter() - t0) * 1000.0, 1)
            vec = ebody.get("embedding") or []
            return {
                "ok": 200 <= ecode < 300 and len(vec) > 0,
                "status": "online" if 200 <= ecode < 300 else "offline",
                "role": role,
                "model_id": model_id,
                "endpoint": endpoint,
                "provider_type": provider_type,
                "latency_ms": ms,
                "vector_dim": len(vec),
                "detail": f"Embedding verified ({len(vec)} dims, {ms} ms)",
            }

        # LLM probe on Ollama
        ms = round((time.perf_counter() - t0) * 1000.0, 1)
        if not has_model:
            return {
                "ok": False,
                "status": "offline",
                "role": role,
                "model_id": model_id,
                "endpoint": endpoint,
                "provider_type": provider_type,
                "latency_ms": ms,
                "detail": f"Ollama reachable ({len(installed)} models), but '{model_id}' is not installed.",
            }
        return {
            "ok": True,
            "status": "online",
            "role": role,
            "model_id": model_id,
            "endpoint": endpoint,
            "provider_type": provider_type,
            "latency_ms": ms,
            "detail": f"Model '{model_id}' ready on Ollama ({ms} ms)",
        }
    except urllib.error.HTTPError as exc:
        ms = round((time.perf_counter() - t0) * 1000.0, 1)
        return {
            "ok": False,
            "status": "offline",
            "role": role,
            "model_id": model_id,
            "endpoint": endpoint,
            "provider_type": provider_type,
            "latency_ms": ms,
            "detail": f"HTTP {exc.code}: {exc.reason}. Check endpoint or API credentials.",
        }
    except Exception as exc:  # noqa: BLE001
        ms = round((time.perf_counter() - t0) * 1000.0, 1)
        return {
            "ok": False,
            "status": "offline",
            "role": role,
            "model_id": model_id,
            "endpoint": endpoint,
            "provider_type": provider_type,
            "latency_ms": ms,
            "detail": f"Unreachable ({exc}). Ensure runtime is started at {endpoint}.",
        }


class DashboardController:
    """Clean, testable business-logic controller for all Dashboard REST routes."""

    def __init__(
        self,
        *,
        db_path: Optional[Path | str] = None,
        settings_path: Optional[Path | str] = None,
        http_probe_fn: Optional[Callable[[str, Optional[dict[str, Any]], float], tuple[int, dict[str, Any]]]] = None,
    ) -> None:
        resolved_db = Path(db_path or resolve_default_db()).expanduser()
        self.store = KnowledgeStore(resolved_db)
        self.settings_path = Path(settings_path or (resolved_db.parent / "dashboard_settings.json")).expanduser()
        self.jobs = CrawlJobManager()
        self._http_probe_fn = http_probe_fn
        self._last_probes: dict[str, dict[str, Any]] = {}

    def load_settings(self) -> dict[str, Any]:
        base = default_dashboard_settings(self.store.db_path)
        if self.settings_path.is_file():
            try:
                raw = json.loads(self.settings_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    return _deep_merge(base, raw)
            except Exception:  # noqa: BLE001
                pass
        return base

    def save_settings(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        merged = _deep_merge(self.load_settings(), payload)
        val = validate_dashboard_settings(merged)
        if not val["valid"]:
            return 400, {"ok": False, "error": "validation_failed", "errors": val["errors"]}
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings_path.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return 200, {"ok": True, "settings": merged}

    def reset_settings_section(self, section: str) -> tuple[int, dict[str, Any]]:
        defaults = default_dashboard_settings(self.store.db_path)
        if section not in defaults:
            return 400, {"ok": False, "error": f"Unknown settings section: {section}"}
        cur = self.load_settings()
        cur[section] = copy.deepcopy(defaults[section])
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings_path.write_text(json.dumps(cur, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return 200, {"ok": True, "section": section, "settings": cur}

    def get_context(self, principal_id: str = "local_owner") -> dict[str, Any]:
        pid = _normalize_principal(principal_id)
        settings = self.load_settings()
        principals = self.store.list_principals()
        idx_summary = self.store.index_summary(principal_id=pid)
        latest_job = self.jobs.latest_job(principal_id=pid)
        if latest_job and latest_job["status"] == "running":
            idx_summary["status"] = "syncing"

        models_cfg = settings["models"]
        embed_probe = self._last_probes.get("embedding") or {
            "status": "ready" if models_cfg["embedding"].get("model_id") else "unconfigured",
            "model_id": models_cfg["embedding"].get("model_id", ""),
        }
        llm_probe = self._last_probes.get("llm") or {
            "status": "ready" if models_cfg["llm"].get("model_id") else "unconfigured",
            "model_id": models_cfg["llm"].get("model_id", ""),
        }

        onboarding = {
            "step_models_configured": bool(models_cfg["embedding"].get("model_id") and models_cfg["llm"].get("model_id")),
            "step_root_registered": idx_summary["root_count"] > 0,
            "step_first_crawl_done": idx_summary["doc_count"] > 0,
        }
        onboarding["show_onboarding"] = not (onboarding["step_root_registered"] and onboarding["step_first_crawl_done"])

        return {
            "ok": True,
            "active_principal_id": pid,
            "principals": principals,
            "index": idx_summary,
            "runtime": {
                "embedding": embed_probe,
                "llm": llm_probe,
            },
            "active_job": latest_job,
            "onboarding": onboarding,
        }

    def check_embedding_compatibility(self, new_embed_cfg: dict[str, Any]) -> dict[str, Any]:
        cur = self.load_settings()["models"]["embedding"]
        old_id = str(cur.get("model_id") or "")
        new_id = str(new_embed_cfg.get("model_id") or "")
        old_dim = int(cur.get("dimensions") or 0)
        new_dim = int(new_embed_cfg.get("dimensions") or EMBEDDING_CATALOG.get(new_id, {}).get("dimensions") or old_dim)
        old_tok = str(cur.get("tokenizer_family") or "")
        new_tok = str(new_embed_cfg.get("tokenizer_family") or EMBEDDING_CATALOG.get(new_id, {}).get("tokenizer_family") or old_tok)
        changed = (old_id != new_id) or (old_dim != new_dim) or (old_tok != new_tok)
        dim_mismatch = old_dim != new_dim
        tok_mismatch = old_tok != new_tok
        return {
            "requires_reindex": changed,
            "dim_mismatch": dim_mismatch,
            "tokenizer_mismatch": tok_mismatch,
            "previous": {"model_id": old_id, "dimensions": old_dim, "tokenizer_family": old_tok},
            "next": {"model_id": new_id, "dimensions": new_dim, "tokenizer_family": new_tok},
        }

    def handle_request(
        self,
        method: str,
        raw_path: str,
        body: Optional[dict[str, Any]] = None,
    ) -> tuple[int, dict[str, Any]]:
        parsed = urllib.parse.urlparse(raw_path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)
        qget = lambda k, d="": (qs.get(k) or [d])[0]  # noqa: E731
        payload = body or {}

        if method == "GET" and path == "/api/context":
            return 200, self.get_context(qget("principal_id", "local_owner"))

        if method == "GET" and path == "/api/principals":
            return 200, {"ok": True, "principals": self.store.list_principals()}

        if method == "POST" and path == "/api/principals":
            pid = str(payload.get("principal_id") or "").strip()
            if not pid:
                return 400, {"ok": False, "error": "principal_id is required"}
            rec = self.store.ensure_principal(
                pid,
                display_name=str(payload.get("display_name") or pid),
                isolation_policy=str(payload.get("isolation_policy") or "strict"),
            )
            return 200, {"ok": True, "principal": rec, "principals": self.store.list_principals()}

        if method == "GET" and path == "/api/settings":
            return 200, {"ok": True, "settings": self.load_settings(), "defaults": default_dashboard_settings(self.store.db_path)}

        if method == "POST" and path == "/api/settings":
            return self.save_settings(payload)

        if method == "POST" and path == "/api/settings/reset":
            return self.reset_settings_section(str(payload.get("section") or ""))

        if method == "POST" and path == "/api/validate/path":
            res = validate_filesystem_path(str(payload.get("path") or ""), require_dir=bool(payload.get("require_dir", True)))
            return 200, {"ok": True, **res}

        if method == "GET" and path == "/api/roots":
            pid = qget("principal_id", "local_owner")
            return 200, {"ok": True, "roots": self.store.list_roots(principal_id=pid)}

        if method == "POST" and path == "/api/roots":
            pid = str(payload.get("principal_id") or "local_owner")
            rpath = str(payload.get("path") or "").strip()
            patterns = payload.get("ignore_patterns")
            try:
                root = self.store.add_root(rpath, principal_id=pid, ignore_patterns=patterns)
                return 200, {"ok": True, "root": root}
            except ValueError as exc:
                return 400, {"ok": False, "error": str(exc)}

        if method == "DELETE" and path == "/api/roots":
            rid = qget("root_id", str(payload.get("root_id") or ""))
            pid = qget("principal_id", str(payload.get("principal_id") or "local_owner"))
            removed = self.store.remove_root(rid, principal_id=pid)
            return (200, {"ok": True, "removed": True}) if removed else (404, {"ok": False, "error": "Root not found or unauthorized"})

        if method == "POST" and path == "/api/crawl/start":
            pid = str(payload.get("principal_id") or "local_owner")
            rid = payload.get("root_id") or None
            full = bool(payload.get("full_reindex", False))
            emb = self.load_settings()["models"]["embedding"]
            job = self.jobs.start_job(
                self.store,
                root_id=rid,
                principal_id=pid,
                full_reindex=full,
                embedding_model=str(emb.get("model_id") or ""),
                embedding_dim=int(emb.get("dimensions") or 0),
                sanitize=bool(payload.get("sanitize", False)),
                privacy_profile=str(payload.get("privacy_profile") or "medium"),
            )
            return 200, {"ok": True, "job": job}

        if method == "GET" and path == "/api/crawl/status":
            jid = qget("job_id", "")
            job = self.jobs.get_job(jid) if jid else self.jobs.latest_job(qget("principal_id", "local_owner"))
            return 200, {"ok": True, "job": job}

        if method == "GET" and path == "/api/files/tree":
            nav = self.store.navigate(
                principal_id=qget("principal_id", "local_owner"),
                root_id=qget("root_id") or None,
                status_filter=qget("status", "all"),
                privacy_filter=qget("privacy", "all"),
                search_path=qget("q", ""),
            )
            return 200, {"ok": True, **nav}

        if method == "GET" and path == "/api/files/inspect":
            doc = self.store.inspect_file(qget("doc_id", ""), principal_id=qget("principal_id", "local_owner"))
            if not doc:
                return 404, {"ok": False, "error": "Document not found or access denied for current principal."}
            return 200, {"ok": True, "document": doc}

        if method == "POST" and path == "/api/files/upload":
            pid = str(payload.get("principal_id") or "local_owner")
            rid = str(payload.get("root_id") or "")
            fname = Path(str(payload.get("filename") or "")).name
            if not fname or fname in {".", ".."}:
                return 400, {"ok": False, "error": "Invalid filename."}
            roots = [r for r in self.store.list_roots(principal_id=pid) if r["root_id"] == rid]
            if not roots:
                return 404, {"ok": False, "error": "Target root not found or unauthorized."}
            target_dir = Path(roots[0]["path"]).resolve()
            dest = (target_dir / fname).resolve()
            if not str(dest).startswith(str(target_dir)):
                return 400, {"ok": False, "error": "Path traversal rejected."}
            if "content_base64" in payload:
                raw = base64.b64decode(str(payload["content_base64"]))
            else:
                raw = str(payload.get("content_text") or "").encode("utf-8")
            dest.write_bytes(raw)
            job = None
            if bool(payload.get("auto_crawl", True)):
                emb = self.load_settings()["models"]["embedding"]
                job = self.jobs.start_job(
                    self.store,
                    root_id=rid,
                    principal_id=pid,
                    full_reindex=False,
                    embedding_model=str(emb.get("model_id") or ""),
                    embedding_dim=int(emb.get("dimensions") or 0),
                )
            return 200, {"ok": True, "saved_path": str(dest), "job": job}

        if method == "GET" and path == "/api/models/status":
            settings = self.load_settings()
            return 200, {
                "ok": True,
                "models": settings["models"],
                "probes": self._last_probes,
                "embedding_catalog": EMBEDDING_CATALOG,
                "llm_catalog": LLM_CATALOG,
            }

        if method == "POST" and path == "/api/models/probe":
            role = str(payload.get("role") or "llm")
            if role not in {"embedding", "llm"}:
                return 400, {"ok": False, "error": "Role must be 'embedding' or 'llm'."}
            settings = self.load_settings()
            cfg = payload.get("config") or settings["models"][role]
            timeout = float((settings.get("advanced") or {}).get("request_timeout_sec", 5))
            res = probe_model_runtime(role, cfg, timeout=min(timeout, 8.0), http_fn=self._http_probe_fn)
            self._last_probes[role] = res
            return 200, res

        if method == "POST" and path == "/api/models/config":
            new_models = payload.get("models") or {}
            if "embedding" in new_models:
                compat = self.check_embedding_compatibility(new_models["embedding"])
                if compat["requires_reindex"] and not bool(payload.get("confirm_reindex_ack", False)):
                    return 409, {"ok": False, "error": "embedding_incompatible", "compatibility": compat}
            code, res = self.save_settings({"models": new_models})
            if code != 200:
                return code, res
            job = None
            if bool(payload.get("trigger_reindex", False)):
                emb = res["settings"]["models"]["embedding"]
                job = self.jobs.start_job(
                    self.store,
                    principal_id=str(payload.get("principal_id") or "local_owner"),
                    full_reindex=True,
                    embedding_model=str(emb.get("model_id") or ""),
                    embedding_dim=int(emb.get("dimensions") or 0),
                )
            return 200, {"ok": True, "models": res["settings"]["models"], "job": job}

        if method == "POST" and path == "/api/search":
            pid = str(payload.get("principal_id") or "local_owner")
            sr = self.load_settings()["search_rag"]
            results = self.store.search(
                str(payload.get("query") or ""),
                principal_id=pid,
                limit=int(payload.get("limit") or sr.get("default_limit", 10)),
                depth=int(payload.get("depth") if payload.get("depth") is not None else sr.get("default_depth", 1)),
            )
            return 200, {"ok": True, "results": results, "count": len(results)}

        if method == "GET" and path == "/api/episodes":
            pid = qget("principal_id", "local_owner")
            dfrom = float(qget("date_from")) if qget("date_from") else None
            dto = float(qget("date_to")) if qget("date_to") else None
            eps = self.store.list_episodes(principal_id=pid, date_from=dfrom, date_to=dto)
            return 200, {"ok": True, "episodes": eps}

        if method == "POST" and path == "/api/episodes":
            pid = str(payload.get("principal_id") or "local_owner")
            ep = self.store.record_episode(
                title=str(payload.get("title") or ""),
                summary=str(payload.get("summary") or ""),
                principal_id=pid,
                tags=payload.get("tags") or [],
                source_refs=payload.get("source_refs") or [],
            )
            return 200, {"ok": True, "episode": ep}

        if method == "POST" and path == "/api/citations/verify":
            pid = str(payload.get("principal_id") or "local_owner")
            sr = self.load_settings()["search_rag"]
            res = self.store.verify_citation(
                str(payload.get("claim") or ""),
                principal_id=pid,
                doc_id=payload.get("doc_id") or None,
                threshold=float(payload.get("threshold") or sr.get("citation_threshold", 0.45)),
            )
            return 200, {"ok": True, **res}

        if method == "GET" and path == "/api/tools/status":
            return 200, {"ok": True, "tools": inspect_composed_tools()}

        if method == "POST" and path in {"/api/tools/test", "/api/tools/install"}:
            name = str(payload.get("name") or "").strip()
            res = test_composed_tool(name) if path.endswith("/test") else install_composed_tool(name)
            return 200, res

        return 404, {"ok": False, "error": "not_found"}
