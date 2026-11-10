"""Hardware Auto-Profiler (`cortical doctor`) & Zero-Latency Endpoint Discovery.

Inspects CPU, RAM, GPU/VRAM across macOS (Apple Silicon Metal) and Linux (NVIDIA CUDA/Vulkan),
discovers any pre-existing local inference servers (`:8080` llama-server, `:11434` Ollama,
`:1234` LM Studio, `:8081` whisper-server), and generates optimal model configurations
without degrading latency on small machines.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional


PortProbeFn = Callable[[str, int], bool]


def default_port_probe(host: str, port: int, timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


@dataclass
class HardwareProfile:
    os_name: str              # 'Darwin' | 'Linux'
    arch: str                 # 'arm64' | 'x86_64'
    cpu_brand: str
    cpu_cores: int
    ram_total_gb: float
    gpu_vendor: str           # 'apple_metal' | 'nvidia_cuda' | 'vulkan_igpu' | 'cpu_only'
    gpu_name: str
    vram_gb: float
    unified_memory: bool
    tier: str                 # 'tier1_constrained' | 'tier2_pro_16gb' | 'tier3_workstation'
    discovered_endpoints: dict[str, str] = field(default_factory=dict)
    installed_tools: dict[str, str] = field(default_factory=dict)


@dataclass
class ModelProfileRecommendation:
    tier: str
    reuse_existing_endpoint: bool
    active_base_url: str
    fast_reflex_model: str
    orchestrator_model: str
    coder_model: str
    vision_gui_model: str
    notes: list[str]


class HardwareProfiler:
    """Detects hardware capabilities, active local LLM/voice servers, and generates configs."""

    KNOWN_ENDPOINTS = {
        "llama_server_8080": ("127.0.0.1", 8080, "http://127.0.0.1:8080/v1"),
        "whisper_server_8081": ("127.0.0.1", 8081, "http://127.0.0.1:8081/inference"),
        "whisper_server_18183": ("127.0.0.1", 18183, "http://127.0.0.1:18183/inference"),
        "omniroute_20128": ("127.0.0.1", 20128, "http://127.0.0.1:20128/v1"),
        "ollama_11434": ("127.0.0.1", 11434, "http://127.0.0.1:11434/v1"),
        "lmstudio_1234": ("127.0.0.1", 1234, "http://127.0.0.1:1234/v1"),
    }

    def __init__(self, port_probe: Optional[PortProbeFn] = None) -> None:
        self.port_probe = port_probe or default_port_probe

    def detect(self, override_specs: Optional[dict[str, Any]] = None) -> HardwareProfile:
        if override_specs:
            profile = HardwareProfile(
                os_name=override_specs.get("os_name", platform.system()),
                arch=override_specs.get("arch", platform.machine()),
                cpu_brand=override_specs.get("cpu_brand", "Custom CPU"),
                cpu_cores=int(override_specs.get("cpu_cores", os.cpu_count() or 4)),
                ram_total_gb=float(override_specs.get("ram_total_gb", 16.0)),
                gpu_vendor=override_specs.get("gpu_vendor", "cpu_only"),
                gpu_name=override_specs.get("gpu_name", "Generic GPU"),
                vram_gb=float(override_specs.get("vram_gb", 4.0)),
                unified_memory=bool(override_specs.get("unified_memory", False)),
                tier="",
                discovered_endpoints=dict(override_specs.get("discovered_endpoints", {})),
                installed_tools=dict(override_specs.get("installed_tools", {})),
            )
            profile.tier = self._classify_tier(profile)
            return profile

        os_name = platform.system()
        arch = platform.machine()
        cpu_cores = os.cpu_count() or 4
        cpu_brand = self._detect_cpu_brand(os_name)
        ram_gb = self._detect_ram_gb(os_name)
        gpu_vendor, gpu_name, vram_gb, unified = self._detect_gpu(os_name, arch, ram_gb)

        discovered: dict[str, str] = {}
        for name, (host, port, url) in self.KNOWN_ENDPOINTS.items():
            if self.port_probe(host, port):
                discovered[name] = url

        tools: dict[str, str] = {}
        for binary in (
            "pi",
            "chrome-devtools-mcp",
            "llama-server",
            "llama-swap",
            "ollama",
            "whisper-server",
            "piper",
            "playwright",
        ):
            found = shutil.which(binary)
            if found:
                tools[binary] = found

        profile = HardwareProfile(
            os_name=os_name,
            arch=arch,
            cpu_brand=cpu_brand,
            cpu_cores=cpu_cores,
            ram_total_gb=ram_gb,
            gpu_vendor=gpu_vendor,
            gpu_name=gpu_name,
            vram_gb=vram_gb,
            unified_memory=unified,
            tier="",
            discovered_endpoints=discovered,
            installed_tools=tools,
        )
        profile.tier = self._classify_tier(profile)
        return profile

    def _classify_tier(self, p: HardwareProfile) -> str:
        if p.ram_total_gb >= 32.0 and (p.vram_gb >= 16.0 or p.unified_memory):
            return "tier3_workstation"
        if p.unified_memory and p.ram_total_gb >= 16.0:
            return "tier2_pro_16gb"
        if p.vram_gb >= 10.0:
            return "tier2_pro_16gb"
        return "tier1_constrained"

    def recommend_models(self, profile: HardwareProfile) -> ModelProfileRecommendation:
        existing_llm = (
            profile.discovered_endpoints.get("llama_server_8080")
            or profile.discovered_endpoints.get("ollama_11434")
            or profile.discovered_endpoints.get("lmstudio_1234")
            or profile.discovered_endpoints.get("omniroute_20128")
        )
        reuse = bool(existing_llm)
        base_url = existing_llm or "http://127.0.0.1:8080/v1"
        notes: list[str] = []

        if reuse:
            notes.append(
                f"Detected active inference server at {existing_llm}; reusing it with ZERO extra VRAM overhead."
            )
        if (
            "whisper_server_8081" in profile.discovered_endpoints
            or "whisper_server_18183" in profile.discovered_endpoints
        ):
            notes.append(
                "Detected active whisper-server; Cortical Voice will attach to it directly."
            )

        if profile.tier == "tier1_constrained":
            notes.append(
                "Constrained VRAM profile (<= 4GB VRAM): keeps LFM2.5-1.2B hot in VRAM for <1s voice/crawler reflex; uses Qwen3-4B-Q4_K_M on-demand."
            )
            return ModelProfileRecommendation(
                tier=profile.tier,
                reuse_existing_endpoint=reuse,
                active_base_url=base_url,
                fast_reflex_model="LFM2.5-1.2B-Instruct-QAD-Q4_0.gguf",
                orchestrator_model="Qwen3-4B-Instruct-Q4_K_M.gguf",
                coder_model="Qwen2.5-Coder-3B-Instruct-Q4_K_M.gguf",
                vision_gui_model="ShowUI-2B-Q4_K_M.gguf",
                notes=notes,
            )

        if profile.tier == "tier2_pro_16gb":
            notes.append(
                "16GB Unified/Mid-Range GPU profile: uses Qwen3-8B/14B for orchestration, Qwen2.5-Coder-7B for coding, and UI-TARS-1.5-7B for GUI automation."
            )
            return ModelProfileRecommendation(
                tier=profile.tier,
                reuse_existing_endpoint=reuse,
                active_base_url=base_url,
                fast_reflex_model="LFM2.5-1.2B-Instruct-QAD-Q4_0.gguf",
                orchestrator_model="Qwen3-8B-Q6_K.gguf",
                coder_model="Qwen2.5-Coder-7B-Instruct-Q6_K.gguf",
                vision_gui_model="UI-TARS-1.5-7B-Q4_K_M.gguf",
                notes=notes,
            )

        notes.append(
            "Workstation >=32GB profile: unlocks 30B MoE/Dense orchestrator and 32B coder."
        )
        return ModelProfileRecommendation(
            tier=profile.tier,
            reuse_existing_endpoint=reuse,
            active_base_url=base_url,
            fast_reflex_model="Qwen3-4B-Instruct-Q8_0.gguf",
            orchestrator_model="Qwen3-30B-A3B-Q4_K_M.gguf",
            coder_model="Qwen2.5-Coder-32B-Instruct-Q4_K_M.gguf",
            vision_gui_model="Qwen2.5-VL-14B-Instruct-Q4_K_M.gguf",
            notes=notes,
        )

    def generate_pi_configs(
        self,
        output_dir: str | Path,
        repo_root: str | Path,
        profile: Optional[HardwareProfile] = None,
    ) -> dict[str, Any]:
        """Generates `.pi/mcp.json` and `hardware_profile.json` tailored to the machine."""
        prof = profile or self.detect()
        rec = self.recommend_models(prof)
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        root_str = str(Path(repo_root).resolve())

        chrome_cmd = prof.installed_tools.get("chrome-devtools-mcp", "npx")
        chrome_args = (
            ["--no-usage-statistics", "--no-performance-crux", f"--workspace={root_str}"]
            if chrome_cmd != "npx"
            else ["-y", "chrome-devtools-mcp@latest", "--no-usage-statistics"]
        )

        python_bin = str(Path(root_str) / ".venv" / "bin" / "python")
        if not Path(python_bin).exists():
            python_bin = shutil.which("python3") or "python3"

        mcp_config = {
            "mcpServers": {
                "cortical-wiki": {
                    "command": python_bin,
                    "args": ["-m", "cortical.wiki.mcp_server"],
                    "env": {
                        "PYTHONPATH": str(Path(root_str) / "src"),
                        "CORTICAL_WIKI_DB": str(Path(root_str) / ".cortical_data" / "wiki.db"),
                    },
                    "exposure": "deferred",
                    "description": "Cortical 4-Tier Merkle Second Brain, Fact-Checking & Episode Macro-Graph.",
                },
                "chrome": {
                    "command": chrome_cmd,
                    "args": chrome_args,
                    "exposure": "deferred",
                    "description": "Inspect and automate Chrome tabs, DOM, network, console and forms.",
                },
            }
        }

        mcp_file = out_path / "mcp.json"
        mcp_file.write_text(json.dumps(mcp_config, indent=2) + "\n", encoding="utf-8")

        summary = {
            "profile": asdict(prof),
            "recommendation": asdict(rec),
            "mcp_config_path": str(mcp_file),
        }
        (out_path / "hardware_profile.json").write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf-8"
        )
        return summary

    def _detect_cpu_brand(self, os_name: str) -> str:
        try:
            if os_name == "Darwin":
                out = subprocess.check_output(
                    ["sysctl", "-n", "machdep.cpu.brand_string"], text=True, timeout=2
                ).strip()
                if out:
                    return out
            elif os_name == "Linux" and Path("/proc/cpuinfo").exists():
                for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
                    if "model name" in line:
                        return line.split(":", 1)[1].strip()
        except Exception:  # noqa: BLE001
            pass
        return platform.processor() or "Generic CPU"

    def _detect_ram_gb(self, os_name: str) -> float:
        try:
            if os_name == "Darwin":
                mem_bytes = int(
                    subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True, timeout=2).strip()
                )
                return round(mem_bytes / (1024**3), 1)
            if os_name == "Linux" and Path("/proc/meminfo").exists():
                for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        return round(kb / (1024**2), 1)
        except Exception:  # noqa: BLE001
            pass
        return 16.0

    def _detect_gpu(self, os_name: str, arch: str, ram_gb: float) -> tuple[str, str, float, bool]:
        if os_name == "Darwin" and arch == "arm64":
            # Apple Silicon Unified Memory (~70% usable by Metal by default)
            return ("apple_metal", "Apple Silicon Metal GPU", round(ram_gb * 0.72, 1), True)

        if shutil.which("nvidia-smi"):
            try:
                out = subprocess.check_output(
                    [
                        "nvidia-smi",
                        "--query-gpu=name,memory.total",
                        "--format=csv,noheader,nounits",
                    ],
                    text=True,
                    timeout=3,
                ).strip()
                first = out.splitlines()[0]
                name, mem_mib = [x.strip() for x in first.split(",", 1)]
                return ("nvidia_cuda", name, round(float(mem_mib) / 1024.0, 1), False)
            except Exception:  # noqa: BLE001
                pass

        return ("cpu_only", "CPU / Integrated Graphics", 0.0, False)
