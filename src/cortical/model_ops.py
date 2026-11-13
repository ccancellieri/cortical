"""Ollama model management and ~/.pi/agent/models.json context window synchronization."""
from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_OLLAMA_BASE = "http://127.0.0.1:11434"

RECOMMENDED_MODEL_PRESETS: List[Dict[str, str]] = [
    {
        "id": "qwen3.8:27b-iq2_xs",
        "label": "Qwen 3.8 27B (IQ2_XS, ~7.6 GB) — Primary Local Reasoning",
    },
    {
        "id": "hf.co/LiquidAI/LFM2.5-1.2B-Instruct-GGUF",
        "label": "LiquidAI LFM2.5 1.2B — Fast Voice/Reflex (<1s)",
    },
    {
        "id": "qwen3:8b",
        "label": "Qwen 3 8B (~5.2 GB) — Balanced Fast Coder/Analyst",
    },
    {
        "id": "qwen2.5-coder:7b",
        "label": "Qwen 2.5 Coder 7B (~4.7 GB) — Fast Code Edits",
    },
    {
        "id": "qwen2.5:1.5b",
        "label": "Qwen 2.5 1.5B (~1.0 GB) — Ultra-light Reflex",
    },
]


def normalize_model_family(name: str) -> str:
    """Normalize an Ollama or HuggingFace model name to detect duplicates/variants."""
    s = (name or "").strip().lower()
    if s.startswith("hf.co/"):
        s = s.split("/")[-1]
    s = re.sub(r"-gguf(:.*)?$", "", s)
    s = re.sub(r"-(ud-)?(iq\d+_[a-z0-9]+|q\d+_[a-z0-9_]+|fp16|bf16)$", "", s)
    s = re.sub(r":(latest)$", "", s)
    s = re.sub(r"[-_:]+", "", s)
    return s


def _ollama_root(base_url: str) -> str:
    """Normalizes an Ollama URL (stripping trailing /v1 if present)."""
    root = (base_url or DEFAULT_OLLAMA_BASE).strip().rstrip("/")
    if root.endswith("/v1"):
        root = root[:-3]
    return root or DEFAULT_OLLAMA_BASE


def list_ollama_models_detailed(
    base_url: str = DEFAULT_OLLAMA_BASE,
    timeout: float = 3.0,
) -> List[Dict[str, Any]]:
    """Query Ollama /api/tags and return detailed metadata with duplicate detection."""
    url = f"{_ollama_root(base_url)}/api/tags"
    raw_models: List[Dict[str, Any]] = []
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            raw_models = payload.get("models") or []
    except Exception:
        return []

    family_counts: Dict[str, int] = {}
    enriched: List[Dict[str, Any]] = []
    for item in raw_models:
        name = str(item.get("name") or item.get("model") or "").strip()
        if not name:
            continue
        fam = normalize_model_family(name)
        family_counts[fam] = family_counts.get(fam, 0) + 1
        size_bytes = int(item.get("size") or 0)
        details = item.get("details") or {}
        enriched.append(
            {
                "name": name,
                "family_key": fam,
                "size_bytes": size_bytes,
                "size_gb": round(size_bytes / (1024**3), 2) if size_bytes else 0.0,
                "digest": str(item.get("digest") or "")[:12],
                "modified_at": str(item.get("modified_at") or ""),
                "parameter_size": str(details.get("parameter_size") or ""),
                "quantization": str(details.get("quantization_level") or ""),
                "is_hf": name.startswith("hf.co/"),
            }
        )

    for entry in enriched:
        entry["is_duplicate"] = family_counts.get(entry["family_key"], 0) > 1
    return enriched


def pull_ollama_model(
    model_name: str,
    base_url: str = DEFAULT_OLLAMA_BASE,
    timeout: int = 300,
) -> Dict[str, Any]:
    """Pull an Ollama model via /api/pull (non-streaming) with CLI fallback."""
    clean = (model_name or "").strip()
    if not clean or any(ch in clean for ch in ("\n", "\r", ";", "&", "|")):
        return {"ok": False, "error": "Invalid model name"}

    url = f"{_ollama_root(base_url)}/api/pull"
    body = json.dumps({"model": clean, "stream": False}).encode("utf-8")
    try:
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("error"):
                return {"ok": False, "error": str(data["error"])}
            return {"ok": True, "model": clean, "status": data.get("status", "success")}
    except urllib.error.URLError:
        pass
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    try:
        proc = subprocess.run(
            ["ollama", "pull", clean],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if proc.returncode == 0:
            return {"ok": True, "model": clean, "status": "pulled"}
        return {"ok": False, "error": (proc.stderr or proc.stdout or "ollama pull failed").strip()}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def delete_ollama_model(
    model_name: str,
    base_url: str = DEFAULT_OLLAMA_BASE,
    timeout: int = 30,
) -> Dict[str, Any]:
    """Delete a local Ollama model via /api/delete with CLI fallback."""
    clean = (model_name or "").strip()
    if not clean or any(ch in clean for ch in ("\n", "\r", ";", "&", "|")):
        return {"ok": False, "error": "Invalid model name"}

    url = f"{_ollama_root(base_url)}/api/delete"
    body = json.dumps({"model": clean}).encode("utf-8")
    try:
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="DELETE",
        )
        with urllib.request.urlopen(req, timeout=timeout):
            return {"ok": True, "model": clean}
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {"ok": False, "error": f"Model '{clean}' not found in Ollama"}
    except Exception:
        pass

    try:
        proc = subprocess.run(
            ["ollama", "rm", clean],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if proc.returncode == 0:
            return {"ok": True, "model": clean}
        return {"ok": False, "error": (proc.stderr or proc.stdout or "ollama rm failed").strip()}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def sync_pi_models_json(
    model_windows: Dict[str, int],
    pi_models_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Update contextWindow entries in ~/.pi/agent/models.json for Ollama models."""
    path = pi_models_path or (Path.home() / ".pi" / "agent" / "models.json")
    if not path.exists():
        return {"updated": False, "reason": "models.json not found"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"updated": False, "reason": f"parse error: {exc}"}

    providers = data.get("providers") or {}
    ollama = providers.get("ollama") or {}
    models_list = ollama.get("models")
    if not isinstance(models_list, list):
        return {"updated": False, "reason": "no ollama.models array"}

    changed = 0
    existing_ids = set()
    for entry in models_list:
        if not isinstance(entry, dict):
            continue
        mid = str(entry.get("id") or "").strip()
        if not mid:
            continue
        existing_ids.add(mid)
        if mid in model_windows:
            try:
                win = max(2048, int(model_windows[mid]))
            except (TypeError, ValueError):
                continue
            if entry.get("contextWindow") != win:
                entry["contextWindow"] = win
                changed += 1

    # Add newly configured models so `pi` recognizes their custom contextWindow
    for mid, raw_win in (model_windows or {}).items():
        if mid in existing_ids:
            continue
        try:
            win = max(2048, int(raw_win))
        except (TypeError, ValueError):
            continue
        models_list.append(
            {
                "id": mid,
                "name": mid,
                "reasoning": False,
                "input": ["text"],
                "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
                "contextWindow": win,
                "maxTokens": min(8192, max(1024, win // 4)),
            }
        )
        changed += 1

    if changed:
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return {"updated": changed > 0, "changed": changed, "path": str(path)}
