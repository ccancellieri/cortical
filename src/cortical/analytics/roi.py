"""Zero-cloud-token ROI analytics (mtime+size cached remote transcripts + local `agent_runs`)."""

from __future__ import annotations

from datetime import datetime
import json
import os
import time
from pathlib import Path
from typing import Any, Optional

from ..config import DEFAULT_TELEMETRY_DB, ensure_telemetry_schema

LOCAL_PROVIDERS = {"router", "ollama", "cortical_local", "local", "unsloth"}
LOCAL_MODEL_PREFIXES = ("qwen", "minicpm", "llama", "mistral", "deepseek", "gemma", "phi", "codellama")

CLOUD_RATES_USD_PER_1M = {
    "cloud_standard": {"input": 3.0, "cache_read": 0.30, "output": 15.0},
    "cloud_economy": {"input": 0.50, "cache_read": 0.05, "output": 2.0},
}


def _estimate_cost(in_tok: int, cache_tok: int, out_tok: int, preset: str = "cloud_standard") -> float:
    rates = CLOUD_RATES_USD_PER_1M.get(preset) or CLOUD_RATES_USD_PER_1M["cloud_standard"]
    return round((in_tok * rates["input"] + cache_tok * rates["cache_read"] + out_tok * rates["output"]) / 1_000_000.0, 4)


def _default_brain_dir() -> Path:
    return Path.home() / ".gemini" / "antigravity" / "brain"


def collect_remote_transcript_usage(
    brain_dir: Optional[Path] = None,
    conversation_id: Optional[str] = None,
    cache_path: Optional[Path] = None,
) -> dict[str, Any]:
    """Scans local Antigravity transcripts using `(path, mtime_ns, size)` caching to avoid reparsing unchanged logs."""
    root = Path(brain_dir) if brain_dir is not None else _default_brain_dir()
    if not root.is_dir():
        return {"chat_count": 0, "input_tokens": 0, "cache_read_tokens": 0, "output_tokens": 0, "active_tokens": 0, "chats": []}

    c_file = Path(cache_path or ".cortical_data/transcript_cache.json")
    try:
        disk_cache: dict[str, Any] = json.loads(c_file.read_text(encoding="utf-8")) if c_file.is_file() else {}
    except Exception:  # noqa: BLE001
        disk_cache = {}

    pattern = f"{conversation_id}*/.system_generated/logs/transcript.jsonl" if conversation_id else "*/.system_generated/logs/transcript.jsonl"
    chats: list[dict[str, Any]] = []
    cache_dirty = False
    for fp in sorted(root.glob(pattern)):
        try:
            st = fp.stat()
            sig = [2, int(st.st_mtime_ns), int(st.st_size)]
            key = str(fp)
            if disk_cache.get(key, {}).get("sig") == sig:
                parsed = disk_cache[key]["data"]
            else:
                in_t = cache_t = out_t = lt_in = lt_cache = lt_out = lt_steps = lt_tools = 0
                for raw_line in fp.read_text(encoding="utf-8", errors="replace").splitlines():
                    if not raw_line.strip():
                        continue
                    try:
                        obj = json.loads(raw_line)
                    except json.JSONDecodeError:
                        continue
                    if obj.get("type") == "USER_INPUT":
                        lt_in = lt_cache = lt_out = lt_steps = lt_tools = 0
                        continue
                    usage = obj.get("usage") if isinstance(obj.get("usage"), dict) else obj
                    i = int(usage.get("input_tokens") or 0)
                    c = int(usage.get("cache_read_tokens") or 0)
                    o = int(usage.get("output_tokens") or 0)
                    if i or c or o:
                        in_t += i
                        cache_t += c
                        out_t += o
                        lt_in += i
                        lt_cache += c
                        lt_out += o
                    if obj.get("type") == "PLANNER_RESPONSE":
                        lt_steps += 1
                        lt_tools += len(obj.get("tool_calls") or [])
                parsed = {
                    "conversation_id": fp.parents[2].name,
                    "mtime_ns": int(st.st_mtime_ns),
                    "input_tokens": in_t,
                    "cache_read_tokens": cache_t,
                    "output_tokens": out_t,
                    "active_tokens": in_t + out_t,
                    "last_turn": {
                        "input_tokens": lt_in,
                        "cache_read_tokens": lt_cache,
                        "output_tokens": lt_out,
                        "active_tokens": lt_in + lt_out,
                        "planner_steps": lt_steps,
                        "tool_calls": lt_tools,
                    },
                }
                disk_cache[key] = {"sig": sig, "data": parsed}
                cache_dirty = True
            chats.append(parsed)
        except OSError:
            continue

    chats.sort(key=lambda c: int(c.get("mtime_ns") or 0), reverse=True)

    if cache_dirty and brain_dir is None:
        try:
            c_file.parent.mkdir(parents=True, exist_ok=True)
            c_file.write_text(json.dumps(disk_cache), encoding="utf-8")
        except OSError:
            pass

    tot_in = sum(c["input_tokens"] for c in chats)
    tot_cache = sum(c["cache_read_tokens"] for c in chats)
    tot_out = sum(c["output_tokens"] for c in chats)
    return {
        "chat_count": len(chats),
        "input_tokens": tot_in,
        "cache_read_tokens": tot_cache,
        "output_tokens": tot_out,
        "active_tokens": tot_in + tot_out,
        "chats": chats,
    }


def _parse_ts_epoch(raw_ts: Any, fallback: float = 0.0) -> float:
    if isinstance(raw_ts, (int, float)):
        val = float(raw_ts)
        return val / 1000.0 if val > 1e12 else val
    if isinstance(raw_ts, str) and raw_ts.strip():
        try:
            return datetime.fromisoformat(raw_ts.strip().replace("Z", "+00:00")).timestamp()
        except ValueError:
            pass
    return fallback


def collect_pi_local_runs(
    pi_sessions_dir: Optional[Path] = None,
    window_sec: float = 1800.0,
    cache_path: Optional[Path] = None,
) -> list[dict[str, Any]]:
    """Collects local LLM token usage from `pi` agent session JSONL logs with mtime+size caching."""
    root = Path(pi_sessions_dir) if pi_sessions_dir is not None else (Path.home() / ".pi" / "agent" / "sessions")
    if not root.is_dir():
        return []

    c_file = Path(cache_path or ".cortical_data/pi_usage_cache.json")
    try:
        disk_cache: dict[str, Any] = json.loads(c_file.read_text(encoding="utf-8")) if (pi_sessions_dir is None and c_file.is_file()) else {}
    except Exception:  # noqa: BLE001
        disk_cache = {}

    runs: list[dict[str, Any]] = []
    cache_dirty = False
    for fp in sorted(root.glob("**/*.jsonl")):
        try:
            st = fp.stat()
            sig = [int(st.st_mtime_ns), int(st.st_size)]
            key = str(fp)
            if pi_sessions_dir is None and disk_cache.get(key, {}).get("sig") == sig:
                file_runs = disk_cache[key]["runs"]
            else:
                file_runs = []
                for raw_line in fp.read_text(encoding="utf-8", errors="replace").splitlines():
                    if not raw_line.strip():
                        continue
                    try:
                        obj = json.loads(raw_line)
                    except json.JSONDecodeError:
                        continue
                    msg = obj.get("message")
                    if not isinstance(msg, dict) or msg.get("role") != "assistant":
                        continue
                    usage = msg.get("usage")
                    if not isinstance(usage, dict):
                        continue
                    prov = str(msg.get("provider") or "").lower()
                    model = str(msg.get("model") or "")
                    if not (prov in LOCAL_PROVIDERS or model.lower().startswith(LOCAL_MODEL_PREFIXES)):
                        continue
                    in_t = int(usage.get("input") or usage.get("input_tokens") or 0)
                    out_t = int(usage.get("output") or usage.get("output_tokens") or 0)
                    tot_t = int(usage.get("totalTokens") or usage.get("total_tokens") or (in_t + out_t))
                    if tot_t <= 0:
                        continue
                    ts = _parse_ts_epoch(obj.get("timestamp") or msg.get("timestamp"), fallback=float(st.st_mtime))
                    file_runs.append({
                        "provider": f"pi:{prov or 'local'}",
                        "model": model,
                        "input_tokens": in_t,
                        "output_tokens": out_t,
                        "total_tokens": tot_t,
                        "elapsed_sec": 0.0,
                        "finished_at": ts,
                    })
                if pi_sessions_dir is None:
                    disk_cache[key] = {"sig": sig, "runs": file_runs}
                    cache_dirty = True
            runs.extend(file_runs)
        except OSError:
            continue

    if cache_dirty and pi_sessions_dir is None:
        try:
            c_file.parent.mkdir(parents=True, exist_ok=True)
            c_file.write_text(json.dumps(disk_cache), encoding="utf-8")
        except OSError:
            pass

    return runs


def collect_local_runs(db_path: Path | str | None = None, window_sec: float = 1800.0) -> dict[str, Any]:
    """Aggregates real local LLM `agent_runs` (+ `pi` local sessions when using default DB)."""
    target = Path(db_path or os.environ.get("CORTICAL_TELEMETRY_DB") or DEFAULT_TELEMETRY_DB)
    real_rows: list[dict[str, Any]] = []
    if target.is_file():
        with ensure_telemetry_schema(target) as conn:
            rows = [dict(r) for r in conn.execute("SELECT * FROM agent_runs ORDER BY finished_at DESC LIMIT 1000").fetchall()]
        real_rows = [r for r in rows if not str(r.get("provider") or "").lower().startswith("mock")]

    is_default_db = db_path is None or Path(db_path).expanduser().resolve() == DEFAULT_TELEMETRY_DB.expanduser().resolve()
    if is_default_db and not os.environ.get("CORTICAL_TELEMETRY_DB"):
        real_rows.extend(collect_pi_local_runs(window_sec=window_sec))

    if not real_rows:
        return {"global": {"run_count": 0, "total_tokens": 0, "elapsed_sec": 0.0, "models": []}, "active_window": {"run_count": 0, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "elapsed_sec": 0.0, "models": []}}

    now = time.time()
    recent = [r for r in real_rows if (now - float(r.get("finished_at") or 0.0)) <= window_sec]

    def _agg(items: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "run_count": len(items),
            "input_tokens": sum(int(r.get("input_tokens") or 0) for r in items),
            "output_tokens": sum(int(r.get("output_tokens") or 0) for r in items),
            "total_tokens": sum(int(r.get("total_tokens") or 0) for r in items),
            "elapsed_sec": round(sum(float(r.get("elapsed_sec") or 0.0) for r in items), 2),
            "models": list(dict.fromkeys(str(r.get("model") or "") for r in items if r.get("model"))),
        }

    return {"global": _agg(real_rows), "active_window": _agg(recent)}


def build_roi_report(
    *,
    db_path: Path | str | None = None,
    brain_dir: Optional[Path] = None,
    conversation_id: Optional[str] = None,
    preset: str = "cloud_standard",
) -> dict[str, Any]:
    """Builds unified local/remote/ROI metrics with zero remote tokens."""
    loc = collect_local_runs(db_path=db_path)
    rem = collect_remote_transcript_usage(brain_dir=brain_dir, conversation_id=conversation_id)
    target_chat = (rem.get("chats") or [{}])[0]
    lt = target_chat.get("last_turn") or {}
    aw = loc["active_window"]

    t_rem_act = int(lt.get("active_tokens") or 0)
    t_loc_tot = int(aw.get("total_tokens") or 0)
    offload_pct = round((t_loc_tot / max(1, t_loc_tot + t_rem_act)) * 100.0, 2)
    return {
        "generated_at": time.time(),
        "local": loc,
        "remote": rem,
        "current_turn": {
            "remote": {**lt, "estimated_cost_usd": _estimate_cost(int(lt.get("input_tokens") or 0), int(lt.get("cache_read_tokens") or 0), int(lt.get("output_tokens") or 0), preset)},
            "local": {**aw, "usd_saved_est": _estimate_cost(int(aw["input_tokens"]), 0, int(aw["output_tokens"]), preset)},
            "offload_share_pct": offload_pct,
        },
    }


def format_roi_markdown(report: dict[str, Any]) -> str:
    """Formats a compact per-turn + cumulative Markdown ROI summary."""
    ct = report.get("current_turn") or {}
    r = ct.get("remote") or {}
    l = ct.get("local") or {}
    g = (report.get("local") or {}).get("global") or {}
    g_in = int(g.get("input_tokens") or 0)
    g_tot = int(g.get("total_tokens") or 0)
    g_out = int(g.get("output_tokens") or 0)
    g_saved = _estimate_cost(g_in or g_tot, 0, g_out)
    models = ", ".join(l.get("models") or g.get("models") or []) or "none"
    return "\n".join([
        "### Cortical Token & Offload Report (0 Cloud Tokens Used)",
        "",
        "| Scope | Tokens (In / Out / Active) | Execution | Cost / Saved |",
        "| --- | --- | --- | --- |",
        f"| **Remote Cloud (Turn)** | {r.get('input_tokens', 0):,} in · {r.get('output_tokens', 0):,} out · {r.get('active_tokens', 0):,} act ({r.get('cache_read_tokens', 0):,} cache) | {r.get('planner_steps', 0)} steps · {r.get('tool_calls', 0)} tools | ~${r.get('estimated_cost_usd', 0.0):.2f} |",
        f"| **Cortical Local (Window)** | {l.get('input_tokens', 0):,} in · {l.get('output_tokens', 0):,} out · {l.get('total_tokens', 0):,} tot | {l.get('run_count', 0)} runs · {l.get('elapsed_sec', 0.0):.1f}s ({models}) | $0 · **Saved ~${l.get('usd_saved_est', 0.0):.2f}** ({ct.get('offload_share_pct', 0.0):.1f}% offload) |",
        f"| **Cortical Local (Cumulative)** | {g_in:,} in · {g_out:,} out · {g_tot:,} tot | {g.get('run_count', 0)} runs · {len(g.get('models') or [])} models | $0 · **Saved ~${g_saved:.2f}** |",
    ])


def evaluate_routing_state(
    *,
    config: Optional[dict[str, Any]] = None,
    db_path: Path | str | None = None,
    brain_dir: Optional[Path] = None,
    conversation_id: Optional[str] = None,
) -> dict[str, Any]:
    """Determines effective LLM routing (`full_local` | `mixed` | `cloud`) from mode & remaining cloud token budget."""
    from ..config import load_cortical_config

    cfg = config or load_cortical_config()
    rt = cfg.get("routing") or {}
    mode = str(rt.get("mode") or "auto").lower().strip()
    enforce = bool(rt.get("enforce_cloud_budget", True))
    budget = int(rt.get("cloud_budget_tokens") or 1000000)
    threshold = int(rt.get("cloud_token_threshold") or 50000)

    report = build_roi_report(db_path=db_path, brain_dir=brain_dir, conversation_id=conversation_id)
    turn_rem = (report.get("current_turn") or {}).get("remote") or {}
    used_active = int(turn_rem.get("active_tokens") or 0)
    remaining = max(0, budget - used_active)
    handoff_rec = bool(enforce and mode != "cloud_first" and remaining <= threshold)

    if mode == "full_local":
        eff = "full_local"
        reason = "User selected Full Local mode: route all turns offline to Ollama."
        handoff_rec = True
    elif mode == "cloud_first":
        eff = "cloud"
        reason = "Cloud First mode active."
    else:
        if not enforce:
            eff = "mixed"
            reason = "Cloud budget threshold disabled (optional; enable in Dashboard → Settings → Harnesses & Routing). Prefer local LLM offload whenever possible."
        elif remaining <= threshold:
            eff = "full_local"
            reason = f"Remaining cloud budget ({remaining:,} tok) <= threshold ({threshold:,} tok): switching to local LLM."
        else:
            eff = "mixed"
            reason = f"Mixed (Auto): {remaining:,} cloud tokens remaining above threshold ({threshold:,})."

    return {
        "configured_mode": mode,
        "effective_mode": eff,
        "enforce_cloud_budget": enforce,
        "prefer_local_offload": bool(rt.get("prefer_local_offload", True)),
        "cloud_budget_tokens": budget,
        "cloud_token_threshold": threshold,
        "remote_active_tokens": used_active,
        "cloud_remaining_tokens": remaining,
        "handoff_recommended": handoff_rec,
        "reason": reason,
        "roi": report,
    }


def export_roi_json(
    data_dir: Path | str,
    *,
    config: Optional[dict[str, Any]] = None,
    db_path: Path | str | None = None,
) -> Path:
    """Writes `roi.json` into the Cortical data folder for zero-server static UI charts/tables."""
    out_dir = Path(data_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    state = evaluate_routing_state(config=config, db_path=db_path)
    p = out_dir / "roi.json"
    p.write_text(json.dumps(state, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    return p
