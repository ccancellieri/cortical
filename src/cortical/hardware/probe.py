"""Cross-platform workstation/laptop hardware probe & Tier 0..3 classifier (zero dependencies)."""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional


_TRACKED_BINARIES = (
    "ollama",
    "unsloth",
    "llama-server",
    "mlx_lm.server",
    "lms",
    "vllm",
    "uv",
    "serena",
    "rtk",
    "pinchtab",
    "npx",
    "claude",
    "codex",
    "opencode",
    "openclaw",
    "pi",
    "dsh",
)


def _run_text(cmd: list[str], timeout: float = 2.0) -> str:
    """Executes a lightweight system query safely, returning empty string on failure."""
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        return (res.stdout or "").strip() if res.returncode == 0 else ""
    except Exception:  # noqa: BLE001
        return ""


def _probe_memory_macos() -> dict[str, Any]:
    total_gb = 16.0
    free_gb = 6.0
    raw_total = _run_text(["sysctl", "-n", "hw.memsize"])
    if raw_total.isdigit():
        total_gb = round(int(raw_total) / (1024 ** 3), 2)
    vm_out = _run_text(["vm_stat"])
    if vm_out:
        m_ps = re.search(r"page size of (\d+) bytes", vm_out)
        page_bytes = int(m_ps.group(1)) if m_ps else 16384
        free_pages = 0
        for key in ("Pages free", "Pages inactive", "Pages speculative", "Pages purgeable"):
            m = re.search(rf"{re.escape(key)}:\s+(\d+)", vm_out)
            if m:
                free_pages += int(m.group(1))
        if free_pages > 0:
            free_gb = round((free_pages * page_bytes) / (1024 ** 3), 2)
    cpu_brand = _run_text(["sysctl", "-n", "machdep.cpu.brand_string"]) or platform.processor() or "Apple Silicon"
    unified = "apple" in cpu_brand.lower() or platform.machine().lower() in {"arm64", "aarch64"}
    raw_press = _run_text(["sysctl", "-n", "kern.memorystatus_vm_pressure_level"])
    pressure = int(raw_press) if raw_press.isdigit() else 1
    return {
        "total_ram_gb": total_gb,
        "free_ram_gb": min(total_gb, free_gb),
        "unified_memory": unified,
        "gpu_name": cpu_brand if unified else "macOS GPU",
        "vram_gb": round(total_gb * 0.70, 2) if unified else 0.0,
        "memory_pressure_level": pressure,
    }


def _probe_memory_linux() -> dict[str, Any]:
    total_gb = 16.0
    free_gb = 6.0
    meminfo = Path("/proc/meminfo")
    if meminfo.is_file():
        txt = meminfo.read_text(encoding="utf-8", errors="replace")
        mt = re.search(r"MemTotal:\s+(\d+)\s+kB", txt)
        ma = re.search(r"MemAvailable:\s+(\d+)\s+kB", txt)
        if mt:
            total_gb = round((int(mt.group(1)) * 1024) / (1024 ** 3), 2)
        if ma:
            free_gb = round((int(ma.group(1)) * 1024) / (1024 ** 3), 2)
    return {
        "total_ram_gb": total_gb,
        "free_ram_gb": min(total_gb, free_gb),
        "unified_memory": False,
        "gpu_name": "CPU Only",
        "vram_gb": 0.0,
    }


def _probe_memory_windows() -> dict[str, Any]:
    total_gb = 16.0
    free_gb = 6.0
    try:
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):  # type: ignore[misc]
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if hasattr(ctypes, "windll") and ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            total_gb = round(stat.ullTotalPhys / (1024 ** 3), 2)
            free_gb = round(stat.ullAvailPhys / (1024 ** 3), 2)
    except Exception:  # noqa: BLE001
        pass
    return {
        "total_ram_gb": total_gb,
        "free_ram_gb": min(total_gb, free_gb),
        "unified_memory": False,
        "gpu_name": "CPU Only",
        "vram_gb": 0.0,
    }


def _probe_discrete_gpu() -> tuple[str, float]:
    if shutil.which("nvidia-smi"):
        out = _run_text(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"])
        if out:
            names: list[str] = []
            tot_mb = 0.0
            for line in out.splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 2:
                    names.append(parts[0])
                    try:
                        tot_mb += float(parts[1])
                    except ValueError:
                        pass
            if tot_mb > 0:
                return (" + ".join(names), round(tot_mb / 1024.0, 2))
    return ("", 0.0)


def _probe_ollama_capabilities(model_name: str, base_url: str = "http://127.0.0.1:11434", timeout: float = 0.6) -> list[str]:
    """Queries Ollama `/api/show` for real model capabilities (verifying multimodal projector when `model_info` is present)."""
    url = f"{base_url.rstrip('/')}/api/show"
    try:
        body = json.dumps({"model": model_name}).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        caps = [str(c).strip().lower() for c in (data.get("capabilities") or []) if str(c).strip()]
        if "vision" in caps and ("model_info" in data or "projector_info" in data):
            mi = data.get("model_info") or {}
            has_proj = bool(data.get("projector_info")) or any(
                any(w in k.lower() for w in ("vision", "clip", "mmproj")) for k in mi
            )
            if not has_proj:
                caps = [c for c in caps if c != "vision"]
        return caps or ["completion"]
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return ["completion"]


def _probe_ollama_tags(base_url: str = "http://127.0.0.1:11434", timeout: float = 0.8) -> tuple[bool, list[dict[str, Any]]]:
    url = f"{base_url.rstrip('/')}/api/tags"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        out: list[dict[str, Any]] = []
        for m in (data.get("models") or []):
            name = str(m.get("name") or m.get("model") or "").strip()
            if name:
                out.append({
                    "name": name,
                    "size_gb": round(int(m.get("size") or 0) / (1024 ** 3), 2),
                    "capabilities": _probe_ollama_capabilities(name, base_url=base_url),
                })
        return (True, out)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return (False, [])


def classify_hardware_tier(hw: dict[str, Any]) -> dict[str, Any]:
    """Classifies machine hardware into Tier 0..3 (explicitly modeling Tier 1A 4-6GB VRAM hybrid laptops and Tier 1B 16GB unified 27B XXS)."""
    ram = float(hw.get("total_ram_gb") or 0.0)
    vram = float(hw.get("vram_gb") or 0.0)
    unified = bool(hw.get("unified_memory"))
    disk = float(hw.get("disk_free_gb") or 0.0)

    if ram < 12.0 and vram < 4.0:
        tier = "tier_0_lean"
        label = "Tier 0 · Lean (<12 GB RAM, no 4GB+ GPU)"
        local_llm_viable = False
        notes = "Run Serena + RTK + Browser Snapshot + TOON + Deterministic Privacy; skip heavy local LLMs."
    elif (not unified and ram >= 12.0 and ram < 28.0 and 3.5 <= vram < 8.0) or (not unified and 12.0 <= ram < 28.0 and vram < 3.5):
        tier = "tier_1a_hybrid_laptop"
        label = "Tier 1A · Hybrid Laptop (16 GB RAM + 4–6 GB VRAM)"
        local_llm_viable = True
        notes = "Keep 1.5B–3B resident in 4–6 GB VRAM for NER/routing; run quantized 7B–8B in hybrid VRAM+RAM offload (8K–16K ctx)."
    elif (unified and 14.0 <= ram < 28.0) or (not unified and 8.0 <= vram < 20.0):
        tier = "tier_1b_unified_16_24"
        label = "Tier 1B · Unified 16–24 GB / 8–12 GB VRAM"
        local_llm_viable = True
        notes = "Runs 9B (UD-Q3_K_XL ~5.1 GB) up to 131K ctx AND 27B dynamic variable quant (4-bit XXS ~8.1 GB / UD-IQ2_XXS ~7.2 GB) for deep reasoning & orchestration."
    elif ram >= 60.0 or vram >= 44.0:
        tier = "tier_3_studio"
        label = "Tier 3 · High-Memory Workstation / Multi-GPU (64 GB+)"
        local_llm_viable = True
        notes = "Full parallel local loops, 32B–70B models, vision & local browser workers."
    else:
        tier = "tier_2_workstation"
        label = "Tier 2 · Workstation (32+ GB RAM / 20+ GB VRAM)"
        local_llm_viable = True
        notes = "Full agentic 27B–32B+ models + local browser worker + optional HTTP router."

    disk_ok = disk >= 12.0 or not local_llm_viable
    return {
        "tier": tier,
        "label": label,
        "local_llm_viable": local_llm_viable,
        "minimum_storage_ok": disk_ok,
        "recommendation": notes,
    }


def probe_hardware(
    os_name: Optional[str] = None,
    runners_probe: bool = True,
    home_dir: Optional[Path] = None,
) -> dict[str, Any]:
    """Probes RAM, VRAM/GPU, free disk, installed binaries, and Ollama models across macOS, Linux, and Windows."""
    target_os = (os_name or sys.platform).lower()
    if target_os.startswith("darwin") or target_os.startswith("mac"):
        norm_os = "macos"
        mem = _probe_memory_macos()
    elif target_os.startswith("win"):
        norm_os = "windows"
        mem = _probe_memory_windows()
    else:
        norm_os = "linux"
        mem = _probe_memory_linux()

    if not mem.get("unified_memory"):
        gpu_name, d_vram = _probe_discrete_gpu()
        if gpu_name:
            mem["gpu_name"] = gpu_name
            mem["vram_gb"] = d_vram

    try:
        disk_free_gb = round(shutil.disk_usage(str(home_dir or Path.home())).free / (1024 ** 3), 2)
    except Exception:  # noqa: BLE001
        disk_free_gb = 50.0

    binaries = {b: (shutil.which(b) or "") for b in _TRACKED_BINARIES}
    ollama_online, installed_models = _probe_ollama_tags() if runners_probe else (False, [])

    hw: dict[str, Any] = {
        "os": norm_os,
        "arch": platform.machine() or "unknown",
        "cpu_cores": os.cpu_count() or 4,
        "total_ram_gb": mem["total_ram_gb"],
        "free_ram_gb": mem["free_ram_gb"],
        "unified_memory": mem["unified_memory"],
        "gpu_name": mem["gpu_name"],
        "vram_gb": mem["vram_gb"],
        "disk_free_gb": disk_free_gb,
        "memory_pressure_level": int(mem.get("memory_pressure_level") or 1),
        "binaries": binaries,
        "ollama_online": ollama_online,
        "installed_ollama_models": installed_models,
    }
    hw["classification"] = classify_hardware_tier(hw)
    return hw
