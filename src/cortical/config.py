"""Zero-dependency configuration & pluggable LLM RunnerRegistry for Cortical.

Supports `cortical.config.json` for configuring:
  - Pluggable LLM runners (`ollama`, `llama_cpp`, `mlx_lm`, `openai_compatible`)
  - Context window cap (`max_context_window`, default 200,000)
  - Token report & retention (`auto_report`, `default_range_days`, `retention_days`)
  - Skill compilation tuning (`auto_compile`, `consolidation_overlap`, etc.)
  - Extensible privacy profiles (`max_security`, `low`, `medium`, `max_context`, custom)
"""

from __future__ import annotations

import copy
import json
import os
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable, Optional

DEFAULT_CONFIG_PATH = Path("cortical.config.json")
DEFAULT_CONFIG_DIR = Path("cortical.config.d")

DEFAULT_CONFIG: dict[str, Any] = {
    "active_runner": "ollama",
    "active_model": "",
    "max_context_window": 200000,
    "components": {
        "wiki_mcp": {
            "enabled": True,
            "module": "cortical.wiki.mcp_server",
            "title_it": "Second Brain Wiki 4-Tier (MCP)",
            "title_en": "4-Tier Second Brain Wiki (MCP)",
            "desc_it": "Indicizza cartelle/file allegati in un albero Merkle a 4 livelli (Light ~50 tok, Medium ~250, High ~1000, Max) con ricerca FTS5 e RBAC SQLite.",
            "desc_en": "Indexes attached folders/files into a 4-tier Merkle tree (Light ~50 tok, Medium ~250, High ~1000, Max) with FTS5 search and SQLite RBAC.",
        },
        "token_analytics": {
            "enabled": True,
            "module": "cortical.token_analytics",
            "title_it": "Analitica Token & ROI",
            "title_en": "Token Analytics & ROI",
            "desc_it": "Misura consumo locale/remoto dalle trascrizioni a 0 token cloud con cache su disco e calcolo costi su preset LiteLLM.",
            "desc_en": "Measures local/remote usage from local transcripts at 0 cloud tokens with disk caching and LiteLLM-aligned cost estimation.",
        },
        "privacy_sanitizer": {
            "enabled": True,
            "module": "cortical.privacy_sanitizer",
            "title_it": "Privacy Sanitizer & GDPR",
            "title_en": "Privacy Sanitizer & GDPR",
            "desc_it": "Rimuove metadati OOXML/PDF, pseudonimizza ID e termini personalizzati, e filtra quasi-identificatori tramite LLM locale offline.",
            "desc_en": "Strips OOXML/PDF metadata, pseudonymizes IDs & custom terms, and rewrites GDPR quasi-identifiers via offline local LLM.",
        },
        "skills_hub": {
            "enabled": True,
            "module": "cortical.skills_hub",
            "title_it": "Cortical Skill Engine",
            "title_en": "Cortical Skill Engine",
            "desc_it": "Motore interno di routing ed evoluzione delle skill procedurali (SKILL.md), consolidamento e collegamento ai task nel Macro-Graph.",
            "desc_en": "Internal procedural skill router & evolution engine (SKILL.md), consolidating overlapping lessons and linking tasks in the Macro-Graph.",
        },
        "permission_gate": {
            "enabled": True,
            "module": "cortical.permissions.gate",
            "title_it": "Adaptive Permission Gate",
            "title_en": "Adaptive Permission Gate",
            "desc_it": "Valutazione deterministica sub-millisecondo dei comandi bash/tool con guardrail hard e apprendimento progressivo del rischio.",
            "desc_en": "Sub-millisecond deterministic bash/tool risk evaluation with hard guardrails and progressive pattern learning.",
        },
        "context_window": {
            "enabled": True,
            "module": "cortical.context_window",
            "title_it": "Auto-Scaler Contesto 200k",
            "title_en": "200k Dynamic Context Auto-Scaler",
            "desc_it": "Scopre automaticamente modello attivo e contesto nativo (/api/ps, /api/show) scalando num_ctx sulla RAM libera fino al cap configurato.",
            "desc_en": "Auto-discovers active model & native context (/api/ps, /api/show) and scales num_ctx to live RAM headroom up to the configured cap.",
        },
    },
    "runners": {
        "ollama": {
            "type": "ollama",
            "base_url": "http://127.0.0.1:11434",
            "default_model": "qwen3.5:9b-q3_k_xl",
            "heavy_model": "qwen3.8:27b-iq2_xxs",
            "enabled": True,
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
            "base_url": "http://127.0.0.1:8888/v1",
            "default_model": "local-model",
            "heavy_model": "local-model",
            "enabled": False,
        },
    },
    "report": {
        "auto_report": True,
        "language": "auto",
        "default_range_days": 30,
        "retention_days": 90,
        "cloud_preset": "cloud_standard",
    },
    "privacy_sanitizer": {
        "sanitizer_model": "qwen2.5:1.5b",
        "custom_terms": [],
        "enable_person_name_heuristic": True,
    },
    "skills": {
        "auto_compile": True,
        "min_terms": 4,
        "consolidation_overlap": 3,
        "consolidation_jaccard": 0.30,
        "require_verified_artifact": True,
    },
    "local_loop": {
        "enabled": True,
        "router_model": "qwen2.5:1.5b",
        "analyst_model": "qwen3.5:9b-q3_k_xl",
        "reviewer_model": "qwen3:8b",
        "reasoner_model": "qwen3:8b",
        "heavy_model": "qwen3.8:27b-iq2_xxs",
        "max_iterations": 3,
        "default_privacy_profile": "medium",
        "escalate_to_remote_only_when_needed": True,
    },
    "privacy_profiles": {
        "max_security": {
            "description": "Local-only reasoning: never sends raw files or excerpts to remote LLMs.",
            "local_only": True,
            "allow_local_conclusions": True,
            "summary_only": True,
            "strip_metadata": True,
            "use_local_llm": True,
            "redact": True,
            "strip_categories": ["SECRET", "EMAIL", "PHONE", "IBAN", "TAX_ID", "IP", "PERSON_NAME", "CUSTOM"],
            "preserve_categories": [],
        },
        "low": {
            "description": "Ultra-sanitized summary: sends only an anonymized high-level summary.",
            "local_only": False,
            "allow_local_conclusions": True,
            "summary_only": True,
            "strip_metadata": True,
            "use_local_llm": True,
            "redact": True,
            "strip_categories": ["SECRET", "EMAIL", "PHONE", "IBAN", "TAX_ID", "IP", "PERSON_NAME", "CUSTOM"],
            "preserve_categories": [],
        },
        "medium": {
            "description": "Selective domain-aware pseudonymization: hides personal IDs, keeps financial/domain metrics.",
            "local_only": False,
            "allow_local_conclusions": True,
            "summary_only": False,
            "strip_metadata": True,
            "use_local_llm": False,
            "redact": False,
            "strip_categories": ["SECRET", "EMAIL", "PHONE", "IBAN", "TAX_ID", "IP", "PERSON_NAME", "CUSTOM"],
            "preserve_categories": ["AMOUNTS", "METRICS"],
        },
        "max_context": {
            "description": "Full raw file passthrough (only use for non-sensitive public/code files).",
            "local_only": False,
            "allow_local_conclusions": False,
            "summary_only": False,
            "strip_metadata": False,
            "use_local_llm": False,
            "redact": False,
            "strip_categories": [],
            "preserve_categories": ["ALL"],
        },
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
    """Loads `DEFAULT_CONFIG` + `cortical.config.d/*.json` drop-ins + `cortical.config.json`."""
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


def is_component_enabled(name: str, config: Optional[dict[str, Any]] = None) -> bool:
    """Returns True if an optional Cortical component/MCP is enabled in config."""
    cfg = config or load_cortical_config()
    comp = (cfg.get("components") or {}).get(name)
    if comp is None:
        return True
    return bool(comp.get("enabled", True))


def resolve_component(name: str, config: Optional[dict[str, Any]] = None) -> Any:
    """Safely imports an optional Cortical component if enabled and installed, else None."""
    cfg = config or load_cortical_config()
    if not is_component_enabled(name, cfg):
        return None
    comp = (cfg.get("components") or {}).get(name) or {}
    mod_name = str(comp.get("module") or "").strip()
    if not mod_name:
        return None
    try:
        import importlib

        return importlib.import_module(mod_name)
    except Exception:  # noqa: BLE001
        return None


def save_cortical_config(cfg: dict[str, Any], config_path: Optional[Path] = None) -> Path:
    """Persists user configuration overrides cleanly to disk (preserving `cortical.config.d` modularity)."""
    p = Path(config_path or os.environ.get("CORTICAL_CONFIG_PATH") or DEFAULT_CONFIG_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return p


RunnerFn = Callable[[str, str, dict[str, Any]], str]
_CUSTOM_RUNNERS: dict[str, RunnerFn] = {}


def register_runner_adapter(name: str, fn: RunnerFn) -> None:
    """Registers a custom local LLM runner adapter `(system_prompt, user_prompt, runner_cfg) -> text`."""
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
    """Persists local runner token usage into `agent_runs` whenever an existing Wiki DB is available."""
    if os.environ.get("CORTICAL_DISABLE_RUNNER_TELEMETRY") == "1":
        return
    r_low = str(runner_name or "").strip().lower()
    m_low = str(model or "").strip().lower()
    if db_path is None and (r_low.startswith("mock") or m_low.startswith("mock")):
        return
    target = Path(db_path) if db_path is not None else Path(os.environ.get("CORTICAL_WIKI_DB") or ".cortical_data/wiki.db")
    if not target.is_file():
        return
    try:
        from .wiki.db import AccessContext, CorticalWikiDB

        db = CorticalWikiDB(target)
        now = time.time()
        db.upsert_agent_run(
            AccessContext(),
            run_id=f"loc-{int(now * 1000)}-{os.getpid()}",
            episode_id=episode_id or f"local-{time.strftime('%Y%m%d')}",
            role=role,
            model=model,
            provider=runner_name,
            status="completed",
            goal=prompt[:160],
            input_tokens=max(1, int(in_tok)),
            output_tokens=max(1, int(out_tok)),
            total_tokens=max(1, int(in_tok) + int(out_tok)),
            elapsed_sec=max(0.0, float(elapsed_sec)),
            finished_at=now,
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
    max_tokens: int = 450,
    timeout: float = 45.0,
    num_ctx: Optional[int] = None,
    temperature: float = 0.15,
    role: str = "local_runner",
    episode_id: Optional[str] = None,
    record_telemetry: bool = True,
    db_path: Optional[Path] = None,
) -> str:
    """Invokes the active pluggable runner (`ollama`, `llama_cpp`, `mlx_lm`, `openai_compatible`, or custom)."""
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
            in_tok = max(1, (len(system_prompt) + len(user_prompt)) // 4)
            out_tok = max(1, len(reply) // 4)
            _record_runner_telemetry(
                model=model,
                runner_name=r_name,
                role=role,
                prompt=user_prompt,
                in_tok=in_tok,
                out_tok=out_tok,
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
                from .context_window import compute_dynamic_num_ctx, get_model_context_window

                nat_ctx = get_model_context_window(model, auto_discover=False)
                dyn = compute_dynamic_num_ctx(base_ctx=nat_ctx, model_id=model)
                eff_num_ctx = max(4096, min(16384, int(dyn)))
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
            "options": {
                "temperature": float(temperature),
                "num_predict": max_tokens,
                "num_ctx": eff_num_ctx,
            },
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
            in_tok = int(data.get("prompt_eval_count") or max(1, (len(system_prompt) + len(user_prompt)) // 4))
            out_tok = int(data.get("eval_count") or max(1, len(reply) // 4))
            _record_runner_telemetry(
                model=model,
                runner_name=r_name,
                role=role,
                prompt=user_prompt,
                in_tok=in_tok,
                out_tok=out_tok,
                elapsed_sec=elapsed_sec,
                episode_id=episode_id,
                db_path=db_path,
            )
        return reply

    # Standard OpenAI-compatible runner (llama.cpp server, mlx-lm server, vLLM, Unsloth Studio)
    if not base.endswith("/v1"):
        base = base + "/v1"
    payload = {
        "model": model,
        "messages": [
            *([{"role": "system", "content": system_prompt}] if system_prompt else []),
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.15,
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
        in_tok = int(usage.get("prompt_tokens") or max(1, (len(system_prompt) + len(user_prompt)) // 4))
        out_tok = int(usage.get("completion_tokens") or max(1, len(reply) // 4))
        _record_runner_telemetry(
            model=model,
            runner_name=r_name,
            role=role,
            prompt=user_prompt,
            in_tok=in_tok,
            out_tok=out_tok,
            elapsed_sec=elapsed_sec,
            episode_id=episode_id,
            db_path=db_path,
        )
    return reply
