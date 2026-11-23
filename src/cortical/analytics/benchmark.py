"""Reproducible comparative benchmark (`baseline vs Cortical`) across Compression, Privacy, Hardware `num_ctx` & MCP."""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from typing import Any

from ..compression.engine import compress_structured
from ..hardware.context_window import compute_dynamic_num_ctx, estimate_tokens
from ..hardware.models import BUILTIN_MODEL_CATALOG, recommend_models_for_hardware
from ..hardware.probe import classify_hardware_tier
from ..mcp_server import CorticalMCPServer
from ..privacy.sanitizer import classify_and_sanitize


def run_comparative_benchmark() -> dict[str, Any]:
    """Executes deterministic before-vs-after comparisons across core Cortical capabilities."""
    # 1. Compression: Raw Pretty JSON vs Cortical Lossless TOON
    sample_records = [
        {"id": i, "module": f"mod_{i}", "status": "ok" if i % 2 else "warn", "tokens": 120 + i * 7, "local": True}
        for i in range(1, 26)
    ]
    raw_pretty = json.dumps({"results": sample_records}, indent=2)
    raw_compact = json.dumps({"results": sample_records}, separators=(",", ":"))
    comp = compress_structured(raw_pretty, fmt="json", min_saving_pct=10.0)
    raw_compact_tok = estimate_tokens(raw_compact)
    vs_compact_pct = round(((raw_compact_tok - comp["compressed_tokens_est"]) / max(1, raw_compact_tok)) * 100.0, 2)

    # 2. Privacy Sanitizer precision on bilingual technical + PII sample (zero Title-Case false positives)
    sample_doc = (
        "Architecture Report: Cortical Control Plane uses Dynamic Context Scaling, Python Stdlib, "
        "Serena Language Server, and Apache License.\n"
        "Private Lead: Alice Rossi (alice.rossi@example.org, +39 347 111 2233), IBAN IT60X0542811101000000123456.\n"
    )
    san = classify_and_sanitize(sample_doc, policy="auto", profile="medium")
    technical_terms_preserved = all(
        term in san["sanitized_text"]
        for term in ("Cortical Control Plane", "Dynamic Context Scaling", "Python Stdlib", "Serena Language Server", "Apache License")
    )
    pii_masked = ("alice.rossi@example.org" not in san["sanitized_text"]) and ("IT60X0542811101000000123456" not in san["sanitized_text"])

    # 3. Variable hardware tiering (Tier 1A 4GB VRAM Laptop vs Tier 1B 16GB Unified w/ 27B 4-bit XXS)
    hw_1a = {"os": "windows", "total_ram_gb": 16.0, "free_ram_gb": 10.0, "unified_memory": False, "vram_gb": 4.0, "disk_free_gb": 80.0, "installed_ollama_models": []}
    hw_1a["classification"] = classify_hardware_tier(hw_1a)
    rec_1a = recommend_models_for_hardware(hw_1a)

    hw_1b = {"os": "macos", "total_ram_gb": 16.0, "free_ram_gb": 11.0, "unified_memory": True, "vram_gb": 11.2, "disk_free_gb": 80.0, "installed_ollama_models": []}
    hw_1b["classification"] = classify_hardware_tier(hw_1b)
    rec_1b = recommend_models_for_hardware(hw_1b)

    ctx_27b_16g = compute_dynamic_num_ctx(32768, "qwen3.8:27b-q4_xxs", ram_available_gb=11.0, unified_memory=True, model_ram_gb=8.1)

    # 4. Lean 7-tool MCP handshake & vault ingest/read latency
    with tempfile.TemporaryDirectory() as tmp:
        srv = CorticalMCPServer(vault_db=Path(tmp) / "vault.db")
        t0 = time.perf_counter()
        srv.handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        tools_res = srv.handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        srv.handle_request({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "cortical_ingest_private", "arguments": {"path_or_text": sample_doc, "alias": "bench_doc"}}})
        srv.handle_request({"jsonrpc": "2.0", "id": 4, "method": "resources/read", "params": {"uri": "cortical://private/bench_doc"}})
        mcp_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        tool_count = len((tools_res or {}).get("result", {}).get("tools", []))

    return {
        "compression_before_vs_after": {
            "raw_pretty_tokens_est": estimate_tokens(raw_pretty),
            "raw_compact_tokens_est": raw_compact_tok,
            "compressed_tokens_est": comp["compressed_tokens_est"],
            "format_used": comp["format_used"],
            "saving_vs_pretty_pct": comp["saving_pct"],
            "saving_vs_compact_pct": vs_compact_pct,
        },
        "privacy_before_vs_after": {
            "resolved_policy": san["resolved_policy"],
            "pii_masked": pii_masked,
            "technical_terms_preserved_pct": 100.0 if technical_terms_preserved else 0.0,
        },
        "hardware_variable_quant_sizing": {
            "tier_1a_hybrid_4gb_vram": {
                "tier": rec_1a["tier"],
                "router_ner": (rec_1a["recommended_by_role"].get("router") or {}).get("model_id"),
                "daily_coder": (rec_1a["recommended_by_role"].get("daily_coder") or {}).get("model_id"),
            },
            "tier_1b_unified_16gb_27b": {
                "tier": rec_1b["tier"],
                "deep_reasoner": (rec_1b["recommended_by_role"].get("deep_reasoner") or {}).get("model_id"),
                "num_ctx_27b_4bit_xxs": ctx_27b_16g,
            },
            "catalog_size": len(BUILTIN_MODEL_CATALOG),
        },
        "lean_mcp": {
            "tool_count": tool_count,
            "handshake_ingest_read_ms": mcp_ms,
        },
    }
