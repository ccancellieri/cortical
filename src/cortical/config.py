"""Zero-dependency declarative configuration, pluggable LLM runners & local telemetry store."""

from __future__ import annotations

import copy
import json
import os
import sqlite3
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable, Optional

def default_data_dir() -> Path:
    """Visible, OS-neutral data folder (`~/Documents/Cortical`), overridable via `CORTICAL_DATA_DIR`."""
    env = os.environ.get("CORTICAL_DATA_DIR")
    if env:
        return Path(env).expanduser()
    docs = Path.home() / "Documents"
    return (docs if docs.is_dir() else Path.home()) / "Cortical"


DATA_DIR = default_data_dir()
DEFAULT_CONFIG_PATH = DATA_DIR / "cortical.config.json"
DEFAULT_CONFIG_DIR = DATA_DIR / "cortical.config.d"
DEFAULT_TELEMETRY_DB = DATA_DIR / "telemetry.db"
DEFAULT_VAULT_DB = DATA_DIR / "vault.db"

DEFAULT_CONFIG: dict[str, Any] = {
    "active_runner": "ollama",
    "active_model": "",
    "max_context_window": 200000,
    "custom_models": [],
    "models_by_role": {
        "router": "qwen2.5:1.5b",
        "ner": "qwen2.5:1.5b",
        "daily_coder": "qwen3.5:9b-q3_k_xl",
        "deep_reasoner": "qwen3.8:27b-iq2_xxs",
        "orchestrator": "qwen3.8:27b-iq2_xxs",
    },
    "runners": {
        "ollama": {
            "type": "ollama",
            "base_url": "http://127.0.0.1:11434",
            "default_model": "qwen3.5:9b-q3_k_xl",
            "heavy_model": "qwen3.8:27b-iq2_xxs",
            "enabled": True,
        },
        "unsloth": {
            "type": "openai_compatible",
            "base_url": "http://127.0.0.1:8888/v1",
            "default_model": "qwen3.5:9b-q3_k_xl",
            "heavy_model": "qwen3.8:27b-iq2_xxs",
            "enabled": False,
        },
        "llama_cpp": {
            "type": "openai_compatible",
            "base_url": "http://127.0.0.1:8080/v1",
            "default_model": "local-model",
            "heavy_model": "local-model",
            "enabled": False,
        },
        "mlx_lm": {
            "type": "openai_compatible",
            "base_url": "http://127.0.0.1:8080/v1",
            "default_model": "mlx-community/Qwen3.5-9B-Instruct-4bit",
            "heavy_model": "mlx-community/Qwen3.5-9B-Instruct-4bit",
            "enabled": False,
        },
        "openai_compatible": {
            "type": "openai_compatible",
            "base_url": "http://127.0.0.1:4000/v1",
            "default_model": "local-model",
            "heavy_model": "local-model",
            "enabled": False,
        },
    },
    "router": {
        "enabled": False,
        "provider": "litellm",
        "base_url": "http://127.0.0.1:4000/v1",
    },
    "composers": {
        "serena": True,
        "rtk": True,
        "pinchtab": True,
        "playwright_mcp": True,
        "context_mode": True,
    },
    "harnesses": {
        "antigravity": True,
        "pi": True,
        "opencode": True,
        "openclaw": True,
        "codex": True,
        "claude-code": True,
        "dsh": True,
        "unsloth-studio": True,
    },
    "privacy": {
        "default_policy": "auto",
        "default_profile": "medium",
        "ner_model": "qwen2.5:1.5b",
        "vision_model": "",
        "use_local_ner": True,
        "custom_terms": [],
    },
    "routing": {
        "mode": "auto",  # "auto" (mixed), "full_local", "cloud_first"
        "enforce_cloud_budget": False,
        "prefer_local_offload": True,
        "cloud_token_threshold": 50000,
        "cloud_budget_tokens": 1000000,
        "fallback_on_rate_limit": True,
    },
    "brain": {
        "auto_distill": True,
        "factorize_jaccard_threshold": 0.35,
    },
    "compression": {
        "enable_toon": True,
        "min_toon_saving_pct": 10.0,
        "max_context_share": 0.15,
    },
    "report": {
        "auto_report": True,
        "language": "auto",
        "cloud_preset": "cloud_standard",
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


def load_cortical_config(
    config_path: Optional[Path] = None,
    config_dir: Optional[Path] = None,
) -> dict[str, Any]:
    """Loads `DEFAULT_CONFIG` + `cortical.config.d/*.json` + `cortical.config.json`."""
    merged = copy.deepcopy(DEFAULT_CONFIG)
    d_path = Path(config_dir or os.environ.get("CORTICAL_CONFIG_DIR") or DEFAULT_CONFIG_DIR)
    if d_path.is_dir():
        for fp in sorted(d_path.glob("*.json")):
            try:
                part = json.loads(fp.read_text(encoding="utf-8"))
                if isinstance(part, dict):
                    merged = _deep_merge(merged, part)
            except Exception:  # noqa: BLE001
                continue

    p = Path(config_path or os.environ.get("CORTICAL_CONFIG_PATH") or DEFAULT_CONFIG_PATH)
    if p.is_file():
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                merged = _deep_merge(merged, raw)
        except Exception:  # noqa: BLE001
            pass
    return merged


def save_cortical_config(cfg: dict[str, Any], config_path: Optional[Path] = None) -> Path:
    """Persists user configuration cleanly to disk."""
    p = Path(config_path or os.environ.get("CORTICAL_CONFIG_PATH") or DEFAULT_CONFIG_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return p


def ensure_telemetry_schema(db_path: Path | str) -> sqlite3.Connection:
    """Opens telemetry SQLite WAL DB and ensures `agent_runs` table exists."""
    p = Path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS agent_runs (
               run_id TEXT PRIMARY KEY,
               episode_id TEXT NOT NULL,
               role TEXT NOT NULL,
               model TEXT NOT NULL,
               provider TEXT NOT NULL,
               status TEXT NOT NULL,
               goal TEXT NOT NULL,
               input_tokens INTEGER NOT NULL DEFAULT 0,
               output_tokens INTEGER NOT NULL DEFAULT 0,
               total_tokens INTEGER NOT NULL DEFAULT 0,
               elapsed_sec REAL NOT NULL DEFAULT 0.0,
               finished_at REAL NOT NULL
           )"""
    )
    return conn


RunnerFn = Callable[[str, str, dict[str, Any]], str]
_CUSTOM_RUNNERS: dict[str, RunnerFn] = {}


def register_runner_adapter(name: str, fn: RunnerFn) -> None:
    """Registers a custom local LLM runner `(system_prompt, user_prompt, runner_cfg) -> text`."""
    _CUSTOM_RUNNERS[str(name).strip().lower()] = fn


def _record_runner_telemetry(
    *,
    model: str,
    runner_name: str,
    role: str,
    prompt: str,
    in_tok: int,
    out_tok: int,
    elapsed_sec: float,
    episode_id: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> None:
    """Records local runner token usage into telemetry DB (ignoring `mock_*` when `db_path` is None)."""
    if os.environ.get("CORTICAL_DISABLE_RUNNER_TELEMETRY") == "1":
        return
    r_low = str(runner_name or "").strip().lower()
    m_low = str(model or "").strip().lower()
    if db_path is None and (r_low.startswith("mock") or m_low.startswith("mock")):
        return
    target = Path(db_path) if db_path is not None else Path(os.environ.get("CORTICAL_TELEMETRY_DB") or DEFAULT_TELEMETRY_DB)
    try:
        with ensure_telemetry_schema(target) as conn:
            now = time.time()
            conn.execute(
                """INSERT OR REPLACE INTO agent_runs(
                       run_id, episode_id, role, model, provider, status, goal,
                       input_tokens, output_tokens, total_tokens, elapsed_sec, finished_at
                   ) VALUES (?, ?, ?, ?, ?, 'completed', ?, ?, ?, ?, ?, ?)""",
                (
                    f"loc-{int(now * 1000)}-{os.getpid()}",
                    episode_id or f"local-{time.strftime('%Y%m%d')}",
                    role,
                    model,
                    runner_name,
                    prompt[:160],
                    max(1, int(in_tok)),
                    max(1, int(out_tok)),
                    max(1, int(in_tok) + int(out_tok)),
                    max(0.0, float(elapsed_sec)),
                    now,
                ),
            )
    except Exception:  # noqa: BLE001
        pass


def invoke_configured_runner(
    user_prompt: str,
    system_prompt: str = "",
    *,
    config: Optional[dict[str, Any]] = None,
    runner_name: Optional[str] = None,
    model_override: Optional[str] = None,
    max_tokens: int = 800,
    timeout: float = 45.0,
    num_ctx: Optional[int] = None,
    temperature: float = 0.15,
    role: str = "local_runner",
    episode_id: Optional[str] = None,
    record_telemetry: bool = True,
    db_path: Optional[Path] = None,
) -> str:
    """Invokes the configured local runner (`ollama`, `unsloth`, `llama_cpp`, `mlx_lm`, `openai_compatible`, custom)."""
    cfg = config or load_cortical_config()
    r_name = str(runner_name or cfg.get("active_runner") or "ollama").strip()
    r_cfg = dict((cfg.get("runners") or {}).get(r_name) or {})
    r_type = str(r_cfg.get("type") or r_name).lower()
    model = str(model_override or cfg.get("active_model") or r_cfg.get("default_model") or "qwen3.5:9b-q3_k_xl")
    t0 = time.perf_counter()

    if r_name.lower() in _CUSTOM_RUNNERS:
        reply = _CUSTOM_RUNNERS[r_name.lower()](system_prompt, user_prompt, {**r_cfg, "model": model})
        elapsed_sec = round(time.perf_counter() - t0, 2)
        if record_telemetry:
            _record_runner_telemetry(
                model=model,
                runner_name=r_name,
                role=role,
                prompt=user_prompt,
                in_tok=max(1, (len(system_prompt) + len(user_prompt)) // 4),
                out_tok=max(1, len(reply) // 4),
                elapsed_sec=elapsed_sec,
                episode_id=episode_id,
                db_path=db_path,
            )
        return reply

    base = str(r_cfg.get("base_url") or "http://127.0.0.1:11434").strip().rstrip("/")
    if r_type == "ollama":
        if base.endswith("/v1"):
            base = base[:-3]
        if num_ctx is not None:
            eff_num_ctx = max(2048, int(num_ctx))
        else:
            eff_num_ctx = 8192
            try:
                from .hardware.context_window import compute_dynamic_num_ctx, get_model_context_window

                nat = get_model_context_window(model, auto_discover=False)
                eff_num_ctx = max(4096, min(32768, compute_dynamic_num_ctx(base_ctx=nat, model_id=model)))
            except Exception:  # noqa: BLE001
                eff_num_ctx = 8192
        payload = {
            "model": model,
            "stream": False,
            "think": False,
            "keep_alive": "90s",
            "messages": [
                *([{"role": "system", "content": system_prompt}] if system_prompt else []),
                {"role": "user", "content": user_prompt},
            ],
            "options": {"temperature": float(temperature), "num_predict": max_tokens, "num_ctx": eff_num_ctx},
        }
        req = urllib.request.Request(
            f"{base}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        reply = str((data.get("message") or {}).get("content") or "").strip()
        elapsed_sec = round(time.perf_counter() - t0, 2)
        if record_telemetry:
            _record_runner_telemetry(
                model=model,
                runner_name=r_name,
                role=role,
                prompt=user_prompt,
                in_tok=int(data.get("prompt_eval_count") or max(1, (len(system_prompt) + len(user_prompt)) // 4)),
                out_tok=int(data.get("eval_count") or max(1, len(reply) // 4)),
                elapsed_sec=elapsed_sec,
                episode_id=episode_id,
                db_path=db_path,
            )
        return reply

    if not base.endswith("/v1"):
        base += "/v1"
    payload = {
        "model": model,
        "messages": [
            *([{"role": "system", "content": system_prompt}] if system_prompt else []),
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": float(temperature),
    }
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    choices = data.get("choices") or []
    reply = str((choices[0].get("message") or {}).get("content") or "").strip() if choices else ""
    elapsed_sec = round(time.perf_counter() - t0, 2)
    if record_telemetry and reply:
        usage = data.get("usage") or {}
        _record_runner_telemetry(
            model=model,
            runner_name=r_name,
            role=role,
            prompt=user_prompt,
            in_tok=int(usage.get("prompt_tokens") or max(1, (len(system_prompt) + len(user_prompt)) // 4)),
            out_tok=int(usage.get("completion_tokens") or max(1, len(reply) // 4)),
            elapsed_sec=elapsed_sec,
            episode_id=episode_id,
            db_path=db_path,
        )
    return reply
