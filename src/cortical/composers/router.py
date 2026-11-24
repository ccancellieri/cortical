"""Managed Local HTTP Router (LiteLLM Proxy) installer, config generator & lifecycle control."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from ..config import default_data_dir, load_cortical_config, resolve_orchestrator_spec, save_cortical_config
from ..hardware.context_window import DEFAULT_MODEL_CONTEXT_WINDOWS, compute_adaptive_timeout, compute_dynamic_num_ctx


def _router_port(config: dict[str, Any]) -> int:
    base = str(((config.get("router") or {}).get("base_url")) or "http://127.0.0.1:4000/v1")
    parsed = urlparse(base)
    return int(parsed.port or 4000)


def _router_host(config: dict[str, Any]) -> str:
    base = str(((config.get("router") or {}).get("base_url")) or "http://127.0.0.1:4000/v1")
    parsed = urlparse(base)
    return str(parsed.hostname or "127.0.0.1")


def _litellm_works(bin_path: str) -> bool:
    """Checks that `litellm` binary exists and has `[proxy]` dependencies installed."""
    py = Path(bin_path).parent / "python"
    if not py.is_file():
        py = Path(bin_path).parent / "python3"
    if py.is_file():
        chk = subprocess.run(
            [str(py), "-c", "import litellm, fastapi_sso, uvicorn"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return chk.returncode == 0
    res = subprocess.run([bin_path, "--help"], capture_output=True, text=True, timeout=15)
    return res.returncode == 0


def resolve_router_bin(data_dir: Optional[Path] = None) -> Optional[str]:
    dd = Path(data_dir or default_data_dir())
    venv_bin = dd / ".router_venv" / ("Scripts" if os.name == "nt" else "bin") / ("litellm.exe" if os.name == "nt" else "litellm")
    if venv_bin.is_file() and _litellm_works(str(venv_bin)):
        return str(venv_bin)
    sys_bin = shutil.which("litellm")
    if sys_bin and _litellm_works(sys_bin):
        return sys_bin
    return None


def ensure_litellm_installed(data_dir: Optional[Path] = None) -> dict[str, Any]:
    """Installs `litellm[proxy]` into `<data_dir>/.router_venv` using `uv` or `pip` if missing."""
    dd = Path(data_dir or default_data_dir())
    dd.mkdir(parents=True, exist_ok=True)
    existing = resolve_router_bin(dd)
    if existing:
        return {"ok": True, "bin": existing, "installed_now": False}

    venv_dir = dd / ".router_venv"
    uv_bin = shutil.which("uv")
    if uv_bin:
        if not venv_dir.exists():
            subprocess.run([uv_bin, "venv", str(venv_dir)], check=True, capture_output=True, text=True)
        res = subprocess.run(
            [uv_bin, "pip", "install", "--python", str(venv_dir / "bin" / "python"), "litellm[proxy]"],
            capture_output=True,
            text=True,
        )
    else:
        if not venv_dir.exists():
            subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True, capture_output=True, text=True)
        py = venv_dir / ("Scripts" if os.name == "nt" else "bin") / ("python.exe" if os.name == "nt" else "python")
        res = subprocess.run(
            [str(py), "-m", "pip", "install", "--quiet", "litellm[proxy]"],
            capture_output=True,
            text=True,
        )
    if res.returncode != 0:
        return {"ok": False, "error": (res.stderr or res.stdout or "Failed to install litellm[proxy]").strip()}
    bin_path = resolve_router_bin(dd)
    return {"ok": bool(bin_path), "bin": bin_path, "installed_now": True}


def _ollama_model_yaml(model_name: str, ollama_model: str, ollama_base: str, num_ctx: int, timeout_sec: int) -> list[str]:
    """Formats one LiteLLM `ollama_chat/` entry with thinking off, keep_alive, dynamic num_ctx & adaptive timeout."""
    return [
        f"  - model_name: {model_name}",
        "    litellm_params:",
        f"      model: ollama_chat/{ollama_model}",
        f"      api_base: {ollama_base}",
        f"      num_ctx: {num_ctx}",
        "      keep_alive: 30m",
        "      reasoning_effort: none",
        f"      timeout: {timeout_sec}",
    ]


def _openai_runner_model_yaml(model_name: str, target_model: str, v1_base: str, timeout_sec: int) -> list[str]:
    """Formats one LiteLLM OpenAI-compatible local runner entry (`unsloth`, `lm_studio`, `llama_cpp`, `mlx_lm`, `vllm`)."""
    return [
        f"  - model_name: {model_name}",
        "    litellm_params:",
        f"      model: openai/{target_model}",
        f"      api_base: {v1_base}",
        "      api_key: local",
        f"      timeout: {timeout_sec}",
    ]


def render_litellm_config_yaml(config: Optional[dict[str, Any]] = None, *, hw: Optional[dict[str, Any]] = None) -> str:
    """Renders deterministic `litellm_config.yaml` mapping Cortical roles, dynamic num_ctx, timeouts & orchestrator."""
    cfg = config or load_cortical_config()
    from ..config import resolve_active_runner_endpoint

    r_name, r_type, _ = resolve_active_runner_endpoint(cfg, v1=False)
    _, _, ollama_base = resolve_active_runner_endpoint(cfg, runner_name=r_name, v1=False)
    _, _, runner_v1_base = resolve_active_runner_endpoint(cfg, runner_name=r_name, v1=True)
    hw_eff = hw or {"total_ram_gb": 16.0, "free_ram_gb": 10.0, "unified_memory": True, "vram_gb": 11.2, "memory_pressure_level": 1}
    orch = resolve_orchestrator_spec(cfg, hw=hw_eff)

    from ..roles import MODEL_ROLES, resolve_role_model

    candidates = [resolve_role_model(r, cfg) for r in ("daily_coder", "deep_reasoner", "router", "fast_coder", "reviewer", "summarizer", "ner", "vision")]
    models = [m for m in dict.fromkeys(candidates) if m]

    def _ctx_and_timeout(mid: str) -> tuple[int, int]:
        base_ctx = DEFAULT_MODEL_CONTEXT_WINDOWS.get(mid, 32768)
        dyn_ctx = compute_dynamic_num_ctx(
            base_ctx,
            mid,
            ram_available_gb=float(hw_eff.get("free_ram_gb") or 10.0),
            vram_gb=float(hw_eff.get("vram_gb") or 11.2),
            unified_memory=bool(hw_eff.get("unified_memory", True)),
            total_ram_gb=float(hw_eff.get("total_ram_gb") or 16.0),
            memory_pressure_level=int(hw_eff.get("memory_pressure_level") or 1),
        )
        return dyn_ctx, compute_adaptive_timeout(mid, num_ctx=dyn_ctx, is_remote=False)

    def _emit_local_entry(alias_name: str, target_m: str) -> list[str]:
        dyn_ctx, t_sec = _ctx_and_timeout(target_m)
        if r_type == "ollama":
            return _ollama_model_yaml(alias_name, target_m, ollama_base, dyn_ctx, t_sec)
        return _openai_runner_model_yaml(alias_name, target_m, runner_v1_base, t_sec)

    lines = ["model_list:"]
    for m in models:
        lines.extend(_emit_local_entry(m, m))

    daily = resolve_role_model("daily_coder", cfg)
    deep = resolve_role_model("deep_reasoner", cfg)
    role_aliases: list[tuple[str, str]] = [("local-default", daily)]
    for rkey, meta in MODEL_ROLES.items():
        if rkey in {"orchestrator", "embedder"}:
            continue
        role_aliases.append((str(meta["alias"]), resolve_role_model(rkey, cfg)))
    for alias, target_m in role_aliases:
        lines.extend(_emit_local_entry(alias, target_m))

    fallbacks: list[str] = []
    if orch["is_remote"] and orch.get("api_key_env"):
        r_model = orch["model"] if "/" in orch["model"] else f"{orch['litellm_prefix']}/{orch['model']}"
        lines.extend([
            "  - model_name: cortical-orchestrator",
            "    litellm_params:",
            f"      model: {r_model}",
            f"      api_key: os.environ/{orch['api_key_env']}",
            f"      timeout: {orch['timeout_sec']}",
        ])
        fallbacks.append('{"cortical-orchestrator": ["cortical-deep", "cortical-fast"]}')
    else:
        o_target = deep if orch["model"] in {"cortical-deep", "cortical-orchestrator", "local-default"} else orch["model"]
        o_ctx, o_sec = _ctx_and_timeout(o_target)
        lines.extend(_ollama_model_yaml("cortical-orchestrator", o_target, ollama_base, o_ctx, o_sec))

    if os.environ.get("OPENROUTER_API_KEY"):
        or_model = str(((cfg.get("router") or {}).get("openrouter_model")) or "openrouter/google/gemini-2.5-flash")
        lines.extend([
            "  - model_name: cloud-primary",
            "    litellm_params:",
            f"      model: {or_model}",
            "      api_key: os.environ/OPENROUTER_API_KEY",
        ])
        fallbacks.append(f'{{"cloud-primary": ["{daily}"]}}')

    if fallbacks:
        lines.extend([
            "router_settings:",
            f"  fallbacks: [{', '.join(fallbacks)}]",
        ])
    lines.extend([
        "litellm_settings:",
        "  drop_params: true",
        "  num_retries: 2",
        f"  request_timeout: {max(600, int(orch.get('timeout_sec') or 600))}",
        "general_settings:",
        "  dangerously_permit_weak_or_unset_master_key: true",
    ])
    return "\n".join(lines) + "\n"


def write_litellm_config(config: Optional[dict[str, Any]] = None, data_dir: Optional[Path] = None) -> Path:
    """Generates `<data_dir>/litellm_config.yaml` mapping Cortical roles & Ollama models."""
    dd = Path(data_dir or default_data_dir())
    dd.mkdir(parents=True, exist_ok=True)
    out = dd / "litellm_config.yaml"
    out.write_text(render_litellm_config_yaml(config=config), encoding="utf-8")
    return out


def router_status(config: Optional[dict[str, Any]] = None, data_dir: Optional[Path] = None) -> dict[str, Any]:
    cfg = config or load_cortical_config()
    dd = Path(data_dir or default_data_dir())
    host = _router_host(cfg)
    port = _router_port(cfg)
    url = f"http://{host}:{port}/v1/models"
    healthy = False
    try:
        with urllib.request.urlopen(url, timeout=1.5) as resp:
            healthy = resp.status == 200
    except Exception:
        healthy = False
    pid_file = dd / "router.pid"
    pid = int(pid_file.read_text().strip()) if pid_file.is_file() and pid_file.read_text().strip().isdigit() else None
    return {
        "enabled": bool((cfg.get("router") or {}).get("enabled", False)),
        "healthy": healthy,
        "url": f"http://{host}:{port}/v1",
        "pid": pid,
        "bin": resolve_router_bin(dd),
        "config_yaml": str(dd / "litellm_config.yaml"),
    }


def start_router(config: Optional[dict[str, Any]] = None, data_dir: Optional[Path] = None, *, enable_in_config: bool = True) -> dict[str, Any]:
    cfg = config or load_cortical_config()
    dd = Path(data_dir or default_data_dir())
    inst = ensure_litellm_installed(dd)
    if not inst.get("ok"):
        return inst
    cfg_yaml = write_litellm_config(cfg, dd)
    if enable_in_config:
        cfg.setdefault("router", {})
        cfg["router"]["enabled"] = True
        cfg["router"]["provider"] = "litellm"
        save_cortical_config(cfg)

    st = router_status(cfg, dd)
    if st["healthy"]:
        return {"ok": True, "already_running": True, **st}

    host = _router_host(cfg)
    port = _router_port(cfg)
    log_path = dd / "router.log"
    with log_path.open("a", encoding="utf-8") as logf:
        proc = subprocess.Popen(
            [str(inst["bin"]), "--config", str(cfg_yaml), "--host", host, "--port", str(port)],
            stdout=logf,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    (dd / "router.pid").write_text(str(proc.pid), encoding="utf-8")

    for _ in range(25):
        time.sleep(0.4)
        if router_status(cfg, dd)["healthy"]:
            return {"ok": True, "already_running": False, **router_status(cfg, dd)}
        if proc.poll() is not None:
            break
    tail = log_path.read_text(encoding="utf-8", errors="ignore")[-800:] if log_path.is_file() else ""
    return {"ok": False, "error": f"Router failed to become healthy on {host}:{port}", "log_tail": tail}


def stop_router(data_dir: Optional[Path] = None) -> dict[str, Any]:
    dd = Path(data_dir or default_data_dir())
    pid_file = dd / "router.pid"
    if not pid_file.is_file():
        return {"ok": True, "stopped": False, "reason": "No router.pid"}
    raw = pid_file.read_text().strip()
    if raw.isdigit():
        try:
            os.kill(int(raw), signal.SIGTERM)
        except ProcessLookupError:
            pass
    pid_file.unlink(missing_ok=True)
    return {"ok": True, "stopped": True, "pid": raw}
