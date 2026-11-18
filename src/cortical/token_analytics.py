"""Zero-remote-token analytics & ROI reporting for Cortical + Cloud LLM usage.

Reads local Antigravity/Cloud conversation transcripts (`transcript.jsonl`) and
Cortical's SQLite Second Brain (`agent_runs`, `task_episodes`, `memory_insights`,
`task_discussion_synthesis`, `learned_skills_registry`) to compute:
  - Measured (or char-estimated fallback) remote cloud token usage per chat & globally
  - Measured local Cortical/Ollama token usage per task & globally
  - Aggregated ROI & estimated cloud tokens/cost saved
  - Optional local-LLM-orchestrated executive narrative (0 remote tokens)
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Optional

from .context_window import (
    compute_dynamic_num_ctx,
    get_model_context_window,
    get_system_memory_snapshot,
)
from .wiki.db import AccessContext, CorticalWikiDB

DEFAULT_BRAIN_DIR = Path.home() / ".gemini" / "antigravity" / "brain"

# Reference cloud pricing presets (USD per 1M tokens) aligned with LiteLLM
# `model_prices_and_context_window.json` for rough cost-savings estimation.
CLOUD_RATE_PRESETS_USD_PER_1M: dict[str, dict[str, float]] = {
    "cloud_standard": {"input": 2.00, "cache_read": 0.15, "output": 10.00},
    "openai_gpt": {"input": 2.50, "cache_read": 1.25, "output": 10.00},
    "claude_sonnet": {"input": 3.00, "cache_read": 0.30, "output": 15.00},
    "gemini_pro": {"input": 2.00, "cache_read": 0.10, "output": 10.00},
    "deepseek_v3": {"input": 0.27, "cache_read": 0.07, "output": 1.10},
    "gemini_flash": {"input": 0.30, "cache_read": 0.075, "output": 2.50},
}
DEFAULT_CLOUD_RATES_USD_PER_1M = CLOUD_RATE_PRESETS_USD_PER_1M["cloud_standard"]


def get_active_cloud_rates() -> tuple[str, dict[str, float]]:
    """Returns `(preset_name, rates_dict)` from `CORTICAL_CLOUD_RATES_JSON` or `CORTICAL_CLOUD_PRESET`."""
    raw_json = os.environ.get("CORTICAL_CLOUD_RATES_JSON", "").strip()
    if raw_json:
        try:
            parsed = json.loads(raw_json)
            if isinstance(parsed, dict):
                return ("custom", {
                    "input": float(parsed.get("input", 2.0)),
                    "cache_read": float(parsed.get("cache_read", 0.15)),
                    "output": float(parsed.get("output", 10.0)),
                })
        except Exception:  # noqa: BLE001
            pass
    preset = os.environ.get("CORTICAL_CLOUD_PRESET", "cloud_standard").strip().lower()
    if preset in CLOUD_RATE_PRESETS_USD_PER_1M:
        return (preset, dict(CLOUD_RATE_PRESETS_USD_PER_1M[preset]))
    return ("cloud_standard", dict(DEFAULT_CLOUD_RATES_USD_PER_1M))

# Conservative heuristic for context tokens saved per 3+1 synthesis or insight reuse
# compared to re-reading raw files across cloud turns.
TOKENS_SAVED_PER_3PLUS1_SYNTHESIS = 1800
TOKENS_SAVED_PER_INSIGHT_HIT = 350
TOKENS_SAVED_PER_SKILL_USE = 600


def _estimate_tokens_from_chars(text: str) -> int:
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


def _estimate_cloud_cost_usd(
    input_tokens: int,
    cache_read_tokens: int,
    output_tokens: int,
    rates: Optional[dict[str, float]] = None,
) -> float:
    if rates is None:
        _, r = get_active_cloud_rates()
    else:
        r = rates
    cost = (
        (max(0, input_tokens) / 1_000_000.0) * float(r.get("input", 2.00))
        + (max(0, cache_read_tokens) / 1_000_000.0) * float(r.get("cache_read", 0.10))
        + (max(0, output_tokens) / 1_000_000.0) * float(r.get("output", 10.00))
    )
    return round(cost, 4)


def parse_transcript_usage(transcript_path: Path) -> dict[str, Any]:
    """Extracts measured (or char-estimated) remote usage from a `transcript.jsonl`."""
    conv_id = transcript_path.parent.parent.parent.name
    input_tokens = 0
    cache_read_tokens = 0
    output_tokens = 0
    est_input_tokens = 0
    est_output_tokens = 0
    measured_steps = 0
    estimated_steps = 0
    planner_steps = 0
    total_steps = 0
    tool_calls = 0
    uses_cortical = False
    title = ""
    started_at = ""
    updated_at = ""
    turn_in = 0
    turn_cache = 0
    turn_out = 0
    turn_est_in = 0
    turn_est_out = 0
    turn_planner_steps = 0
    turn_tool_calls = 0
    prev_turn_snap: Optional[dict[str, Any]] = None

    try:
        raw_lines = transcript_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {
            "conversation_id": conv_id,
            "title": conv_id,
            "source": "unavailable",
            "input_tokens": 0,
            "cache_read_tokens": 0,
            "output_tokens": 0,
            "active_tokens": 0,
            "total_processed_tokens": 0,
            "estimated_cost_usd": 0.0,
            "steps": 0,
            "planner_steps": 0,
            "tool_calls": 0,
            "uses_cortical": False,
            "started_at": "",
            "updated_at": "",
            "last_turn": {
                "input_tokens": 0,
                "cache_read_tokens": 0,
                "output_tokens": 0,
                "active_tokens": 0,
                "estimated_cost_usd": 0.0,
                "planner_steps": 0,
                "tool_calls": 0,
            },
        }

    for line in raw_lines:
        s = line.strip()
        if not s:
            continue
        try:
            step = json.loads(s)
        except json.JSONDecodeError:
            continue

        total_steps += 1
        ts = str(step.get("created_at") or "")
        if ts:
            if not started_at:
                started_at = ts
            updated_at = ts

        stype = str(step.get("type") or "")
        content = str(step.get("content") or "")
        thinking = str(step.get("thinking") or "")
        tcalls = step.get("tool_calls") or []
        if stype == "USER_INPUT":
            if turn_planner_steps > 0:
                p_in = (turn_in + turn_est_in) if measured_steps > 0 else turn_est_in
                p_out = (turn_out + turn_est_out) if measured_steps > 0 else turn_est_out
                prev_turn_snap = {
                    "input_tokens": p_in,
                    "cache_read_tokens": turn_cache,
                    "output_tokens": p_out,
                    "active_tokens": p_in + p_out,
                    "estimated_cost_usd": _estimate_cloud_cost_usd(p_in, turn_cache, p_out),
                    "planner_steps": turn_planner_steps,
                    "tool_calls": turn_tool_calls,
                }
            turn_in = 0
            turn_cache = 0
            turn_out = 0
            turn_est_in = 0
            turn_est_out = 0
            turn_planner_steps = 0
            turn_tool_calls = 0
        if isinstance(tcalls, list):
            tool_calls += len(tcalls)
            turn_tool_calls += len(tcalls)

        if not uses_cortical:
            hay = (content + " " + json.dumps(tcalls, ensure_ascii=False)).lower()
            if "cortical" in hay or "wiki_search" in hay or "wiki_navigate" in hay or "127.0.0.1:8765" in hay:
                uses_cortical = True

        if stype == "USER_INPUT" and not title and content.strip():
            cleaned = re.sub(r"</?USER_REQUEST>", " ", content)
            cleaned = re.sub(r"\s+", " ", cleaned).strip()
            title = cleaned[:90] + ("..." if len(cleaned) > 90 else "")

        if stype == "PLANNER_RESPONSE" or isinstance(step.get("usage"), dict):
            planner_steps += 1
            turn_planner_steps += 1
            u_dict = step.get("usage") if isinstance(step.get("usage"), dict) else step
            has_u = any(k in u_dict for k in ("input_tokens", "prompt_tokens", "output_tokens", "completion_tokens"))
            if has_u:
                measured_steps += 1
                s_in = int(u_dict.get("input_tokens") or u_dict.get("prompt_tokens") or 0)
                s_cache = int(u_dict.get("cache_read_tokens") or u_dict.get("cache_read_input_tokens") or 0)
                s_out = int(u_dict.get("output_tokens") or u_dict.get("completion_tokens") or 0)
                input_tokens += s_in
                cache_read_tokens += s_cache
                output_tokens += s_out
                turn_in += s_in
                turn_cache += s_cache
                turn_out += s_out
            else:
                estimated_steps += 1
                eo = _estimate_tokens_from_chars(thinking + " " + json.dumps(tcalls, ensure_ascii=False))
                est_output_tokens += eo
                est_input_tokens += 1500  # conservative per-turn prompt baseline when runtime omits usage
                turn_est_out += eo
                turn_est_in += 1500
        elif stype == "USER_INPUT":
            ei = _estimate_tokens_from_chars(content)
            turn_est_in += ei
            if measured_steps == 0:
                est_input_tokens += ei
        elif stype == "GENERIC":
            eo = _estimate_tokens_from_chars(content)
            turn_est_out += eo
            if measured_steps == 0:
                est_output_tokens += eo

    if measured_steps > 0:
        source = "measured" if estimated_steps == 0 else "mixed"
        eff_in = input_tokens + est_input_tokens
        eff_out = output_tokens + est_output_tokens
        t_eff_in = turn_in + turn_est_in
        t_eff_out = turn_out + turn_est_out
    else:
        source = "estimated"
        eff_in = est_input_tokens
        eff_out = est_output_tokens
        t_eff_in = turn_est_in
        t_eff_out = turn_est_out

    active_tokens = eff_in + eff_out
    total_processed = active_tokens + cache_read_tokens
    t_active = t_eff_in + t_eff_out
    last_turn_obj = (
        prev_turn_snap
        if turn_planner_steps == 0 and prev_turn_snap is not None
        else {
            "input_tokens": t_eff_in,
            "cache_read_tokens": turn_cache,
            "output_tokens": t_eff_out,
            "active_tokens": t_active,
            "estimated_cost_usd": _estimate_cloud_cost_usd(t_eff_in, turn_cache, t_eff_out),
            "planner_steps": turn_planner_steps,
            "tool_calls": turn_tool_calls,
        }
    )
    return {
        "conversation_id": conv_id,
        "title": title or conv_id,
        "source": source,
        "input_tokens": eff_in,
        "cache_read_tokens": cache_read_tokens,
        "output_tokens": eff_out,
        "active_tokens": active_tokens,
        "total_processed_tokens": total_processed,
        "estimated_cost_usd": _estimate_cloud_cost_usd(eff_in, cache_read_tokens, eff_out),
        "steps": total_steps,
        "planner_steps": planner_steps,
        "tool_calls": tool_calls,
        "uses_cortical": uses_cortical,
        "started_at": started_at,
        "updated_at": updated_at,
        "last_turn": last_turn_obj,
    }


def _median(vals: list[int | float]) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    mid = len(s) // 2
    if len(s) % 2 == 1:
        return float(s[mid])
    return round((float(s[mid - 1]) + float(s[mid])) / 2.0, 2)


def compute_trend_and_cohort_stats(
    chats: list[dict[str, Any]],
    recent_window: int = 10,
) -> dict[str, Any]:
    """Computes Recent vs Historical adoption, medians, and daily series for charts."""
    recent = chats[:recent_window]
    historical = chats[recent_window:]

    def _cohort(items: list[dict[str, Any]]) -> dict[str, Any]:
        n = len(items)
        cort = sum(1 for c in items if c.get("uses_cortical"))
        act = [int(c.get("active_tokens") or 0) for c in items]
        costs = [float(c.get("estimated_cost_usd") or 0.0) for c in items]
        return {
            "chat_count": n,
            "cortical_chats": cort,
            "adoption_rate_pct": round((cort / max(1, n)) * 100.0, 1) if n else 0.0,
            "median_active_tokens": int(_median(act)),
            "avg_active_tokens": int(round(sum(act) / max(1, n))) if n else 0,
            "avg_cost_usd": round(sum(costs) / max(1, n), 2) if n else 0.0,
        }

    rec_stats = _cohort(recent)
    hist_stats = _cohort(historical)
    adoption_delta_pp = round(rec_stats["adoption_rate_pct"] - hist_stats["adoption_rate_pct"], 1) if historical else 0.0

    cort_items = [c for c in chats if c.get("uses_cortical")]
    non_cort_items = [c for c in chats if not c.get("uses_cortical")]

    by_day: dict[str, dict[str, Any]] = {}
    for c in chats:
        day = str(c.get("updated_at") or c.get("started_at") or "")[:10] or "unknown"
        if day == "unknown":
            continue
        slot = by_day.setdefault(
            day,
            {"date": day, "chats": 0, "cortical_chats": 0, "active_tokens": 0, "cost_usd": 0.0},
        )
        slot["chats"] += 1
        if c.get("uses_cortical"):
            slot["cortical_chats"] += 1
        slot["active_tokens"] += int(c.get("active_tokens") or 0)
        slot["cost_usd"] = round(slot["cost_usd"] + float(c.get("estimated_cost_usd") or 0.0), 2)

    daily_series = sorted(by_day.values(), key=lambda x: x["date"])[-14:]
    return {
        "recent_window": recent_window,
        "recent": rec_stats,
        "historical": hist_stats,
        "adoption_delta_pp": adoption_delta_pp,
        "cortical_vs_non_cortical": {
            "cortical": _cohort(cort_items),
            "non_cortical": _cohort(non_cort_items),
        },
        "daily_series": daily_series,
    }


_TRANSCRIPT_MEM_CACHE: dict[tuple[str, int, int], dict[str, Any]] = {}
DEFAULT_TRANSCRIPT_CACHE_PATH = Path(".cortical_data/transcript_usage_cache.json")


def _detect_report_lang(
    explicit_lang: Optional[str],
    chats: list[dict[str, Any]],
) -> str:
    """Resolves report language (`it`, `en`, `es`) from arg, config, or latest chat prompt."""
    cand = (explicit_lang or "").strip().lower()
    if not cand:
        from .config import load_cortical_config

        cand = str((load_cortical_config().get("report") or {}).get("language") or "auto").strip().lower()
    if cand in {"it", "en", "es"}:
        return cand
    sample = " ".join(str(c.get("title") or "") for c in chats[:2]).lower()
    if any(w in sample for w in (" per ", " come ", " non ", " che ", " aggiorna ", " usiamo ", " vorrei ", " voglio ")):
        return "it"
    if any(w in sample for w in (" para ", " como ", " quiero ", " por favor ")):
        return "es"
    return "en" if sample else "it"


def collect_remote_transcripts_usage(
    brain_dir: Optional[Path] = None,
    conversation_id: Optional[str] = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Scans local coding-agent transcripts with `(path, mtime_ns, size)` caching (0 cloud tokens)."""
    root = Path(brain_dir) if brain_dir is not None else DEFAULT_BRAIN_DIR
    chats: list[dict[str, Any]] = []
    candidates: list[Path] = []
    if root.exists():
        if conversation_id:
            exact = root / conversation_id / ".system_generated" / "logs" / "transcript.jsonl"
            candidates = [exact] if exact.exists() else list(root.glob(f"{conversation_id}*/.system_generated/logs/transcript.jsonl"))
        else:
            candidates = list(root.glob("*/.system_generated/logs/transcript.jsonl"))

    # Optional multi-harness transcript dirs when brain_dir is not explicitly overridden
    if brain_dir is None and not conversation_id:
        extra_roots = [
            Path.home() / ".claude" / "projects",
            Path.home() / ".codex" / "sessions",
        ]
        env_dirs = os.environ.get("CORTICAL_TRANSCRIPTS_DIRS", "").strip()
        if env_dirs:
            extra_roots.extend(Path(p.strip()) for p in env_dirs.split(os.pathsep) if p.strip())
        for er in extra_roots:
            if er.exists():
                candidates.extend(er.rglob("*.jsonl"))

    candidates = sorted(
        set(candidates),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[: max(1, limit)]

    disk_cache: dict[str, dict[str, Any]] = {}
    use_disk_cache = (brain_dir is None) and DEFAULT_TRANSCRIPT_CACHE_PATH.parent.is_dir()
    if use_disk_cache and DEFAULT_TRANSCRIPT_CACHE_PATH.is_file():
        try:
            disk_cache = json.loads(DEFAULT_TRANSCRIPT_CACHE_PATH.read_text(encoding="utf-8")) or {}
        except Exception:  # noqa: BLE001
            disk_cache = {}
    cache_dirty = False

    for fp in candidates:
        try:
            st = fp.stat()
            mkey = (str(fp), int(st.st_mtime_ns), int(st.st_size))
        except OSError:
            chats.append(parse_transcript_usage(fp))
            continue

        cached = _TRANSCRIPT_MEM_CACHE.get(mkey)
        if isinstance(cached, dict) and "last_turn" not in cached:
            cached = None
        if cached is None and use_disk_cache:
            d_entry = disk_cache.get(str(fp))
            if (
                isinstance(d_entry, dict)
                and d_entry.get("_v") == 2
                and d_entry.get("_mtime_ns") == mkey[1]
                and d_entry.get("_size") == mkey[2]
            ):
                cached = d_entry.get("data")
                if isinstance(cached, dict) and "last_turn" in cached:
                    _TRANSCRIPT_MEM_CACHE[mkey] = cached
                else:
                    cached = None
        if cached is not None:
            chats.append(dict(cached))
            continue

        parsed = parse_transcript_usage(fp)
        _TRANSCRIPT_MEM_CACHE[mkey] = parsed
        if use_disk_cache:
            disk_cache[str(fp)] = {"_v": 2, "_mtime_ns": mkey[1], "_size": mkey[2], "data": parsed}
            cache_dirty = True
        chats.append(parsed)

    if use_disk_cache and cache_dirty:
        try:
            DEFAULT_TRANSCRIPT_CACHE_PATH.write_text(json.dumps(disk_cache), encoding="utf-8")
        except OSError:
            pass

    tot_in = sum(c["input_tokens"] for c in chats)
    tot_cache = sum(c["cache_read_tokens"] for c in chats)
    tot_out = sum(c["output_tokens"] for c in chats)
    tot_active = tot_in + tot_out
    tot_processed = tot_active + tot_cache
    cache_hit_pct = round((tot_cache / max(1, tot_in + tot_cache)) * 100.0, 2)
    measured_cnt = sum(1 for c in chats if c["source"] in {"measured", "mixed"})
    cortical_cnt = sum(1 for c in chats if c["uses_cortical"])
    trend_stats = compute_trend_and_cohort_stats(chats)

    return {
        "brain_dir": str(root),
        "chat_count": len(chats),
        "measured_chat_count": measured_cnt,
        "estimated_chat_count": len(chats) - measured_cnt,
        "cortical_assisted_chats": cortical_cnt,
        "input_tokens": tot_in,
        "cache_read_tokens": tot_cache,
        "output_tokens": tot_out,
        "active_tokens": tot_active,
        "total_processed_tokens": tot_processed,
        "cache_hit_pct": cache_hit_pct,
        "estimated_cost_usd": _estimate_cloud_cost_usd(tot_in, tot_cache, tot_out),
        "trend_stats": trend_stats,
        "chats": chats,
    }


def _collect_memory_and_skill_stats(wiki_db: CorticalWikiDB, ctx: AccessContext) -> dict[str, Any]:
    """Queries Cortical SQLite for Second Brain memory & learned skill metrics."""
    episodes_total = 0
    episodes_archived = 0
    syntheses_3plus1 = 0
    memory_insights = 0
    learned_skills = 0
    skill_uses = 0
    skill_helpful = 0

    with wiki_db._connect() as conn:
        try:
            row = conn.execute(
                """SELECT COUNT(*) AS tot,
                          SUM(CASE WHEN outcome_status = 'archived' THEN 1 ELSE 0 END) AS arch
                   FROM task_episodes WHERE tenant_id = ? AND workspace_id = ?""",
                (ctx.tenant_id, ctx.workspace_id),
            ).fetchone()
            if row:
                episodes_total = int(row["tot"] or 0)
                episodes_archived = int(row["arch"] or 0)
        except Exception:  # noqa: BLE001
            pass

        for tbl, attr in (
            ("task_discussion_synthesis", "synth"),
            ("memory_insights", "ins"),
        ):
            try:
                r = conn.execute(
                    f"SELECT COUNT(*) AS c FROM {tbl} WHERE tenant_id = ? AND workspace_id = ?",
                    (ctx.tenant_id, ctx.workspace_id),
                ).fetchone()
                if attr == "synth" and r:
                    syntheses_3plus1 = int(r["c"] or 0)
                elif attr == "ins" and r:
                    memory_insights = int(r["c"] or 0)
            except Exception:  # noqa: BLE001
                pass

        try:
            r = conn.execute(
                """SELECT COUNT(*) AS c,
                          COALESCE(SUM(use_count), 0) AS uses,
                          COALESCE(SUM(helpful_count), 0) AS helpful
                   FROM learned_skills_registry
                   WHERE tenant_id = ? AND workspace_id = ?""",
                (ctx.tenant_id, ctx.workspace_id),
            ).fetchone()
            if r:
                learned_skills = int(r["c"] or 0)
                skill_uses = int(r["uses"] or 0)
                skill_helpful = int(r["helpful"] or 0)
        except Exception:  # noqa: BLE001
            pass

    est_mem_saved = (
        syntheses_3plus1 * TOKENS_SAVED_PER_3PLUS1_SYNTHESIS
        + memory_insights * TOKENS_SAVED_PER_INSIGHT_HIT
        + skill_uses * TOKENS_SAVED_PER_SKILL_USE
    )
    return {
        "episodes_total": episodes_total,
        "episodes_archived": episodes_archived,
        "syntheses_3plus1": syntheses_3plus1,
        "memory_insights": memory_insights,
        "learned_skills": learned_skills,
        "skill_uses": skill_uses,
        "skill_helpful": skill_helpful,
        "estimated_memory_tokens_saved": est_mem_saved,
    }


def _collect_per_task_stats(wiki_db: CorticalWikiDB, ctx: AccessContext, limit: int = 50) -> list[dict[str, Any]]:
    """Aggregates local LLM token usage and estimated savings per Cortical task."""
    ep_meta: dict[str, dict[str, Any]] = {}
    with wiki_db._connect() as conn:
        try:
            rows = conn.execute(
                """SELECT episode_id, goal, outcome_status FROM task_episodes
                   WHERE tenant_id = ? AND workspace_id = ?""",
                (ctx.tenant_id, ctx.workspace_id),
            ).fetchall()
            for row in rows:
                ep_meta[str(row["episode_id"])] = dict(row)
        except Exception:  # noqa: BLE001
            pass
    runs = wiki_db.list_agent_runs(ctx, episode_id=None, limit=1000)

    grouped: dict[str, dict[str, Any]] = {}
    for r in runs:
        eid = str(r.get("episode_id") or "unassigned")
        meta = ep_meta.get(eid, {})
        slot = grouped.setdefault(
            eid,
            {
                "episode_id": eid,
                "goal": str(meta.get("goal") or r.get("goal") or eid)[:120],
                "status": str(meta.get("outcome_status") or r.get("status") or "open"),
                "run_count": 0,
                "local_input_tokens": 0,
                "local_output_tokens": 0,
                "local_total_tokens": 0,
                "elapsed_sec": 0.0,
                "latest_at": 0.0,
                "models": set(),
            },
        )
        i_tok = int(r.get("input_tokens") or 0)
        o_tok = int(r.get("output_tokens") or 0)
        t_tok = int(r.get("total_tokens") or (i_tok + o_tok))
        ts_val = float(r.get("finished_at") or r.get("started_at") or 0.0)
        slot["run_count"] += 1
        slot["local_input_tokens"] += i_tok
        slot["local_output_tokens"] += o_tok
        slot["local_total_tokens"] += t_tok
        slot["elapsed_sec"] = round(slot["elapsed_sec"] + float(r.get("elapsed_sec") or 0.0), 2)
        if ts_val > slot["latest_at"]:
            slot["latest_at"] = ts_val
        if r.get("model"):
            slot["models"].add(str(r["model"]))

    out: list[dict[str, Any]] = []
    for slot in grouped.values():
        loc_tot = slot["local_total_tokens"]
        slot["models"] = sorted(slot["models"])
        # Conservative 1:1 cloud offload equivalent (local tokens executed at $0 cloud cost)
        slot["estimated_cloud_tokens_saved"] = loc_tot
        slot["estimated_usd_saved"] = _estimate_cloud_cost_usd(
            slot["local_input_tokens"], 0, slot["local_output_tokens"]
        )
        out.append(slot)

    out.sort(key=lambda x: x["local_total_tokens"], reverse=True)
    return out[:limit]


def _default_local_ollama_insight(prompt: str, model: Optional[str] = None, lang: str = "it") -> str:
    """Calls the configured pluggable local runner (0 remote tokens) to summarize token ROI."""
    from .config import invoke_configured_runner

    lang_hint = {"en": "English", "es": "Spanish"}.get(lang, "Italian")
    sys_prompt = (
        f"You are Cortical's local analyst (0 cloud tokens). Reply concisely in {lang_hint} "
        "(max 4 complete bullets) evaluating per-task, per-chat, and global metrics using ONLY the numbers in the JSON."
    )
    return invoke_configured_runner(
        prompt,
        system_prompt=sys_prompt,
        model_override=model or os.environ.get("CORTICAL_REPORT_MODEL") or None,
        max_tokens=450,
        timeout=20.0,
    )


def prune_old_token_data(
    wiki_db: CorticalWikiDB,
    retention_days: int = 90,
    reset_all: bool = False,
    ctx: Optional[AccessContext] = None,
) -> dict[str, int]:
    """Prunes granular `agent_runs` older than `retention_days` (or resets all when `reset_all=True`)."""
    access_ctx = ctx or AccessContext()
    cutoff = time.time() - max(1, int(retention_days)) * 86400.0
    deleted_runs = 0
    with wiki_db._connect() as conn:
        if reset_all:
            cur = conn.execute(
                "DELETE FROM agent_runs WHERE tenant_id = ? AND workspace_id = ?",
                (access_ctx.tenant_id, access_ctx.workspace_id),
            )
            deleted_runs = int(cur.rowcount or 0)
        else:
            cur = conn.execute(
                """DELETE FROM agent_runs
                   WHERE tenant_id = ? AND workspace_id = ?
                     AND COALESCE(finished_at, started_at, 0) < ?""",
                (access_ctx.tenant_id, access_ctx.workspace_id, cutoff),
            )
            deleted_runs = int(cur.rowcount or 0)
    return {"deleted_runs": deleted_runs, "retention_days": retention_days, "reset_all": int(reset_all)}


def orchestrate_local_insight(
    report: dict[str, Any],
    llm_fn: Optional[Callable[[str], str]] = None,
    model: Optional[str] = None,
    lang: str = "it",
) -> dict[str, Any]:
    """Generates an executive ROI insight using ONLY local LLM (or deterministic fallback)."""
    g = report.get("global_stats") or {}
    rem = g.get("remote") or {}
    loc = g.get("local") or {}
    roi = g.get("roi") or {}
    mem = g.get("memory_and_skills") or {}

    per_task = report.get("per_task") or []
    per_chat = report.get("per_chat") or []
    cort_chats = [c for c in per_chat if c.get("uses_cortical")]
    non_cort_chats = [c for c in per_chat if not c.get("uses_cortical")]

    trend = rem.get("trend_stats") or {}
    rec_t = trend.get("recent") or {}
    hist_t = trend.get("historical") or {}
    cvn = trend.get("cortical_vs_non_cortical") or {}

    compact_metrics = {
        "remote_chats_total": rem.get("chat_count", 0),
        "remote_cortical_chats": len(cort_chats),
        "remote_non_cortical_chats": len(non_cort_chats),
        "recent_adoption_pct": rec_t.get("adoption_rate_pct", 0.0),
        "historical_adoption_pct": hist_t.get("adoption_rate_pct", 0.0),
        "adoption_delta_pp": trend.get("adoption_delta_pp", 0.0),
        "cortical_median_tokens": (cvn.get("cortical") or {}).get("median_active_tokens", 0),
        "non_cortical_median_tokens": (cvn.get("non_cortical") or {}).get("median_active_tokens", 0),
        "remote_active_tokens": rem.get("active_tokens", 0),
        "remote_cache_hit_pct": rem.get("cache_hit_pct", 0.0),
        "remote_est_cost_usd": rem.get("estimated_cost_usd", 0.0),
        "local_runs": loc.get("run_count", 0),
        "local_total_tokens": loc.get("total_tokens", 0),
        "local_elapsed_sec": loc.get("total_elapsed_sec", 0.0),
        "top_tasks": [
            {"id": t.get("episode_id"), "tok": t.get("local_total_tokens"), "runs": t.get("run_count")}
            for t in per_task[:3]
        ],
        "memory_tokens_saved_est": mem.get("estimated_memory_tokens_saved", 0),
        "cloud_tokens_saved_est": roi.get("estimated_cloud_tokens_saved", 0),
        "offload_share_pct": roi.get("cloud_offload_share_pct", 0.0),
        "est_usd_saved": roi.get("estimated_usd_saved", 0.0),
    }
    prompt = f"Metriche aggregate Cortical + Cloud:\n{json.dumps(compact_metrics, ensure_ascii=False)}"

    try:
        fn = llm_fn or (lambda p: _default_local_ollama_insight(p, model=model, lang=lang))
        text = (fn(prompt) or "").strip()
        if text:
            return {"source": "local_llm", "model": model or "ollama", "text": text}
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, RuntimeError):
        pass

    # Deterministic 0-token fallback when Ollama is offline/busy
    saved_tok = int(roi.get("estimated_cloud_tokens_saved") or 0)
    saved_usd = float(roi.get("estimated_usd_saved") or 0.0)
    offload_pct = float(roi.get("cloud_offload_share_pct") or 0.0)
    cache_pct = float(rem.get("cache_hit_pct") or 0.0)
    fallback = (
        f"Offload locale + Second Brain 3+1: stimati {saved_tok:,} token cloud risparmiati "
        f"(~${saved_usd:.2f}, quota offload attivo {offload_pct:.1f}%). "
        f"Cache prompt remota al {cache_pct:.1f}% su {rem.get('chat_count', 0)} chat; "
        f"{loc.get('run_count', 0)} run locali eseguiti a costo cloud $0."
    )
    return {"source": "deterministic_local", "model": "none", "text": fallback}


def build_token_report(
    wiki_db: CorticalWikiDB,
    ctx: Optional[AccessContext] = None,
    episode_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    brain_dir: Optional[Path] = None,
    include_narrative: bool = False,
    llm_fn: Optional[Callable[[str], str]] = None,
    model: Optional[str] = None,
    lang: Optional[str] = None,
) -> dict[str, Any]:
    """Builds the unified local + remote + ROI Token Report with 0 remote tokens."""
    access_ctx = ctx or AccessContext()
    local_summary = wiki_db.get_token_usage_summary(access_ctx, episode_id=episode_id)
    local_global = wiki_db.get_token_usage_summary(access_ctx, episode_id=None) if episode_id else local_summary
    remote = collect_remote_transcripts_usage(brain_dir=brain_dir, conversation_id=conversation_id)
    eff_lang = _detect_report_lang(lang, remote.get("chats") or [])
    mem_skills = _collect_memory_and_skill_stats(wiki_db, access_ctx)
    per_task = _collect_per_task_stats(wiki_db, access_ctx)

    loc_tot = int(local_global.get("total_tokens") or 0)
    loc_in = int(local_global.get("input_tokens") or 0)
    loc_out = int(local_global.get("output_tokens") or 0)
    loc_runs = int(local_global.get("run_count") or 0)
    total_elapsed_sec = round(sum(float(t.get("elapsed_sec") or 0.0) for t in per_task), 2)
    avg_elapsed_sec = round(total_elapsed_sec / max(1, loc_runs), 2) if loc_runs else 0.0
    mem_saved = int(mem_skills.get("estimated_memory_tokens_saved") or 0)
    est_cloud_saved = loc_tot + mem_saved
    rem_active = int(remote.get("active_tokens") or 0)
    offload_share_pct = round((loc_tot / max(1, loc_tot + rem_active)) * 100.0, 2)
    preset_name, active_rates = get_active_cloud_rates()
    local_offload_usd_saved = round(_estimate_cloud_cost_usd(loc_in, 0, loc_out, rates=active_rates), 4)
    memory_usd_saved = round(_estimate_cloud_cost_usd(mem_saved, 0, 0, rates=active_rates), 4)
    est_usd_saved = round(
        _estimate_cloud_cost_usd(loc_in + mem_saved, 0, loc_out, rates=active_rates),
        4,
    )
    mem_snap = get_system_memory_snapshot()
    # Enrich per-model local stats with context window, dynamic num_ctx & elapsed_sec (0 cloud tokens)
    all_runs = wiki_db.list_agent_runs(access_ctx, episode_id=None, limit=1000)
    model_elapsed: dict[str, float] = {}
    for r in all_runs:
        m_name = str(r.get("model") or "unknown")
        model_elapsed[m_name] = round(model_elapsed.get(m_name, 0.0) + float(r.get("elapsed_sec") or 0.0), 2)
    enriched_by_model: list[dict[str, Any]] = []
    for entry in local_global.get("by_model", []):
        m_id = str(entry.get("model") or "unknown")
        nat_ctx = get_model_context_window(m_id, auto_discover=False)
        dyn_ctx = compute_dynamic_num_ctx(
            base_ctx=nat_ctx,
            model_id=m_id,
            ram_available_gb=mem_snap["ram_available_gb"],
            model_metadata={"context_length": nat_ctx},
        )
        enriched_by_model.append({
            **entry,
            "elapsed_sec": model_elapsed.get(m_id, 0.0),
            "context_window": nat_ctx,
            "dynamic_num_ctx": dyn_ctx,
        })
    explanations = {
        "remote_usage": (
            "Somma diretta da `transcript.jsonl` (`PLANNER_RESPONSE`: `input_tokens` non-cached, "
            "`cache_read_tokens` da prompt cache, `output_tokens`); fallback ~4 char/token se assente."
        ),
        "local_offload": (
            f"Token eseguiti su Ollama locale (`agent_runs`: {loc_in:,} in + {loc_out:,} out = {loc_tot:,} tot) "
            f"in {total_elapsed_sec:.1f}s totali (media {avg_elapsed_sec:.1f}s/run) a costo cloud $0.00."
        ),
        "memory_saved": (
            f"Stima riuso Second Brain 3+1: {mem_skills.get('syntheses_3plus1', 0)} sintesi×1.800 + "
            f"{mem_skills.get('memory_insights', 0)} insight×350 + {mem_skills.get('skill_uses', 0)} usi skill×600 = {mem_saved:,} tok."
        ),
        "cloud_savings_usd": (
            f"Valore cloud evitato: `({loc_in:,} input + {mem_saved:,} memoria) × ${active_rates['input']}/1M + "
            f"{loc_out:,} output × ${active_rates['output']}/1M` (preset `{preset_name}`, tariffe LiteLLM)."
        ),
        "offload_share": (
            f"Quota lavoro attivo offloaded in locale: `{loc_tot:,} ÷ ({loc_tot:,} + {rem_active:,}) = {offload_share_pct:.1f}%`."
        ),
    }

    all_chats = remote.get("chats", [])
    target_chat = next(
        (c for c in all_chats if conversation_id and str(c.get("conversation_id") or "").startswith(str(conversation_id))),
        all_chats[0] if all_chats else {},
    )
    lt = target_chat.get("last_turn") or {}
    t_rem_in = int(lt.get("input_tokens") or 0)
    t_rem_cache = int(lt.get("cache_read_tokens") or 0)
    t_rem_out = int(lt.get("output_tokens") or 0)
    t_rem_act = int(lt.get("active_tokens") or (t_rem_in + t_rem_out))
    t_rem_cost = round(_estimate_cloud_cost_usd(t_rem_in, t_rem_cache, t_rem_out, rates=active_rates), 4)
    t_rem_cache_pct = round((t_rem_cache / max(1, t_rem_in + t_rem_cache)) * 100.0, 1)

    now_ts = time.time()
    t_loc_models: list[str] = []
    t_loc_episodes: list[str] = []
    if episode_id:
        ep_runs = wiki_db.list_agent_runs(access_ctx, episode_id=episode_id, limit=200)
        t_loc_in = int(local_summary.get("input_tokens") or 0)
        t_loc_out = int(local_summary.get("output_tokens") or 0)
        t_loc_tot = int(local_summary.get("total_tokens") or 0)
        t_loc_runs = int(local_summary.get("run_count") or 0)
        t_loc_elapsed = round(sum(float(r.get("elapsed_sec") or 0.0) for r in ep_runs), 2)
        t_loc_ep = episode_id
        t_loc_episodes = [episode_id]
        t_loc_models = list(dict.fromkeys(str(r.get("model") or "") for r in ep_runs if r.get("model")))
    else:
        recent_runs = [
            r for r in all_runs
            if not str(r.get("provider") or "").strip().lower().startswith("mock")
            and (now_ts - float(r.get("finished_at") or r.get("started_at") or 0.0)) <= 1800.0
        ]
        if recent_runs:
            t_loc_in = sum(int(r.get("input_tokens") or 0) for r in recent_runs)
            t_loc_out = sum(int(r.get("output_tokens") or 0) for r in recent_runs)
            t_loc_tot = sum(int(r.get("total_tokens") or (int(r.get("input_tokens") or 0) + int(r.get("output_tokens") or 0))) for r in recent_runs)
            t_loc_runs = len(recent_runs)
            t_loc_elapsed = round(sum(float(r.get("elapsed_sec") or 0.0) for r in recent_runs), 2)
            t_loc_episodes = list(dict.fromkeys(str(r.get("episode_id") or "") for r in recent_runs if r.get("episode_id")))
            t_loc_ep = t_loc_episodes[0] if len(t_loc_episodes) == 1 else (f"{len(t_loc_episodes)} episodes" if t_loc_episodes else "")
            t_loc_models = list(dict.fromkeys(str(r.get("model") or "") for r in recent_runs if r.get("model")))
        elif per_task:
            non_mock_tasks = [t for t in per_task if not str(t.get("episode_id") or "").startswith("mock")]
            if len(non_mock_tasks) == 1:
                only_t = non_mock_tasks[0]
                t_loc_in = int(only_t.get("local_input_tokens") or 0)
                t_loc_out = int(only_t.get("local_output_tokens") or 0)
                t_loc_tot = int(only_t.get("local_total_tokens") or 0)
                t_loc_runs = int(only_t.get("run_count") or 0)
                t_loc_elapsed = float(only_t.get("elapsed_sec") or 0.0)
                t_loc_ep = str(only_t.get("episode_id") or "")
                t_loc_episodes = [t_loc_ep] if t_loc_ep else []
                t_loc_models = list(only_t.get("models") or [])
            else:
                t_loc_in = t_loc_out = t_loc_tot = t_loc_runs = 0
                t_loc_elapsed = 0.0
                t_loc_ep = ""
        else:
            t_loc_in = t_loc_out = t_loc_tot = t_loc_runs = 0
            t_loc_elapsed = 0.0
            t_loc_ep = ""

    t_mem_saved = 0
    if target_chat.get("uses_cortical") or t_loc_tot > 0 or mem_saved > 0:
        t_mem_saved = (
            (TOKENS_SAVED_PER_3PLUS1_SYNTHESIS if mem_skills.get("syntheses_3plus1", 0) else 0)
            + TOKENS_SAVED_PER_INSIGHT_HIT * min(2, int(mem_skills.get("memory_insights") or 0))
            + (TOKENS_SAVED_PER_SKILL_USE if mem_skills.get("skill_uses", 0) else 0)
            + (t_loc_runs * 1200 if t_loc_runs > 0 else 0)
        )
    t_loc_usd = round(_estimate_cloud_cost_usd(t_loc_in, 0, t_loc_out, rates=active_rates), 4)
    t_tot_usd = round(_estimate_cloud_cost_usd(t_loc_in + t_mem_saved, 0, t_loc_out, rates=active_rates), 4)
    t_share_pct = round((t_loc_tot / max(1, t_loc_tot + t_rem_act)) * 100.0, 2)
    t_eff_share_pct = round(((t_loc_tot + t_mem_saved) / max(1, t_loc_tot + t_mem_saved + t_rem_act)) * 100.0, 2)

    report: dict[str, Any] = {
        "generated_at": time.time(),
        "zero_remote_tokens_used": True,
        "language": eff_lang,
        "episode_id": episode_id,
        "conversation_id": target_chat.get("conversation_id") or conversation_id,
        "rate_preset": preset_name,
        "rates_usd_per_1m": active_rates,
        "explanations": explanations,
        "local_scope": local_summary,
        "current_turn": {
            "conversation_id": target_chat.get("conversation_id") or "",
            "episode_id": t_loc_ep,
            "episode_ids": t_loc_episodes,
            "remote": {
                "input_tokens": t_rem_in,
                "cache_read_tokens": t_rem_cache,
                "output_tokens": t_rem_out,
                "active_tokens": t_rem_act,
                "cache_hit_pct": t_rem_cache_pct,
                "estimated_cost_usd": t_rem_cost,
                "planner_steps": int(lt.get("planner_steps") or 0),
                "tool_calls": int(lt.get("tool_calls") or 0),
            },
            "local": {
                "run_count": t_loc_runs,
                "input_tokens": t_loc_in,
                "output_tokens": t_loc_out,
                "total_tokens": t_loc_tot,
                "elapsed_sec": t_loc_elapsed,
                "models_used": t_loc_models,
            },
            "roi": {
                "memory_tokens_saved": t_mem_saved,
                "total_tokens_saved": t_loc_tot + t_mem_saved,
                "local_offload_usd_saved": t_loc_usd,
                "estimated_usd_saved": t_tot_usd,
                "offload_share_pct": t_share_pct,
                "effective_offload_share_pct": t_eff_share_pct,
            },
        },
        "per_task": per_task,
        "per_chat": all_chats,
        "global_stats": {
            "remote": {k: v for k, v in remote.items() if k != "chats"},
            "local": {
                "run_count": loc_runs,
                "input_tokens": loc_in,
                "output_tokens": loc_out,
                "total_tokens": loc_tot,
                "total_elapsed_sec": total_elapsed_sec,
                "avg_elapsed_sec": avg_elapsed_sec,
                "system_ram_gb": mem_snap,
                "by_model": enriched_by_model,
            },
            "memory_and_skills": mem_skills,
            "roi": {
                "offloaded_local_tokens": loc_tot,
                "estimated_memory_tokens_saved": mem_saved,
                "estimated_cloud_tokens_saved": est_cloud_saved,
                "cloud_offload_share_pct": offload_share_pct,
                "local_offload_usd_saved": local_offload_usd_saved,
                "memory_usd_saved": memory_usd_saved,
                "estimated_usd_saved": est_usd_saved,
            },
        },
    }

    if include_narrative:
        report["local_llm_insight"] = orchestrate_local_insight(report, llm_fn=llm_fn, model=model, lang=eff_lang)
    return report


def format_token_report_markdown(
    report: dict[str, Any],
    dashboard_path: Optional[Path] = None,
    respect_config: bool = False,
    lang: Optional[str] = None,
    turn_only: bool = True,
) -> str:
    """Formats a `build_token_report` payload into a compact per-response Markdown report (or full history when `turn_only=False`)."""
    if respect_config:
        from .config import load_cortical_config

        if not bool((load_cortical_config().get("report") or {}).get("auto_report", True)):
            return ""
    eff_lang = (lang or report.get("language") or "it").lower()
    is_en = eff_lang == "en"

    if turn_only and isinstance(report.get("current_turn"), dict):
        ct = report["current_turn"]
        ct_rem = ct.get("remote") or {}
        ct_loc = ct.get("local") or {}
        ct_roi = ct.get("roi") or {}
        loc_models = [str(m) for m in (ct_loc.get("models_used") or []) if m]
        models_tag = f" ({', '.join(loc_models[:4])})" if loc_models else ""
        eff_share = float(ct_roi.get("effective_offload_share_pct") or 0.0)
        raw_share = float(ct_roi.get("offload_share_pct") or 0.0)
        share_str = (
            f"{raw_share:.1f}% offload · {eff_share:.1f}% eff."
            if eff_share > raw_share
            else f"{raw_share:.1f}% offload"
        )
        lines = [
            "### Token Report (Current Response · 0 Extra Cloud Tokens)" if is_en else "### Token Report (Questa Risposta · 0 Token Cloud Extra)",
            "",
            "| Scope | Tokens (In / Out / Total) | Execution & Cache | Cost / Savings |" if is_en else "| Ambito | Token (In / Out / Tot) | Esecuzione & Cache | Costo / Risparmio |",
            "| --- | --- | --- | --- |",
            (
                f"| **Remote Cloud (This Reply)** | {ct_rem.get('input_tokens', 0):,} in · {ct_rem.get('output_tokens', 0):,} out · {ct_rem.get('active_tokens', 0):,} active ({ct_rem.get('cache_read_tokens', 0):,} cache) "
                f"| {ct_rem.get('planner_steps', 0)} steps · {ct_rem.get('tool_calls', 0)} tools · Cache {ct_rem.get('cache_hit_pct', 0.0):.1f}% "
                f"| Est. cost: ~${ct_rem.get('estimated_cost_usd', 0.0):.2f} |"
                if is_en else
                f"| **Cloud Remoto (Risposta)** | {ct_rem.get('input_tokens', 0):,} in · {ct_rem.get('output_tokens', 0):,} out · {ct_rem.get('active_tokens', 0):,} attivi ({ct_rem.get('cache_read_tokens', 0):,} cache) "
                f"| {ct_rem.get('planner_steps', 0)} step · {ct_rem.get('tool_calls', 0)} tool · Cache {ct_rem.get('cache_hit_pct', 0.0):.1f}% "
                f"| Costo stimato: ~${ct_rem.get('estimated_cost_usd', 0.0):.2f} |"
            ),
            (
                f"| **Local Cortical (Run)** | {ct_loc.get('input_tokens', 0):,} in · {ct_loc.get('output_tokens', 0):,} out · {ct_loc.get('total_tokens', 0):,} tot "
                f"| {ct_loc.get('run_count', 0)} runs · {ct_loc.get('elapsed_sec', 0.0):.1f}s{models_tag} "
                f"| Cloud $0 · **Saved ~${ct_roi.get('local_offload_usd_saved', 0.0):.2f}** ({share_str}) |"
                if is_en else
                f"| **Cortical Locale (Run)** | {ct_loc.get('input_tokens', 0):,} in · {ct_loc.get('output_tokens', 0):,} out · {ct_loc.get('total_tokens', 0):,} tot "
                f"| {ct_loc.get('run_count', 0)} run · {ct_loc.get('elapsed_sec', 0.0):.1f}s{models_tag} "
                f"| Cloud $0 · **Risparmiati ~${ct_roi.get('local_offload_usd_saved', 0.0):.2f}** ({share_str}) |"
            ),
            (
                f"| **Context & 3+1 Compression** | {ct_roi.get('memory_tokens_saved', 0):,} ctx tok saved "
                f"| Zero-server Merkle/3+1 "
                f"| **Total Saved: ~${ct_roi.get('estimated_usd_saved', 0.0):.2f}** ({ct_roi.get('total_tokens_saved', 0):,} tok) |"
                if is_en else
                f"| **Contesto & Compressione 3+1** | {ct_roi.get('memory_tokens_saved', 0):,} tok contesto risparmiati "
                f"| Zero-server Merkle/3+1 "
                f"| **Totale Risparmiati: ~${ct_roi.get('estimated_usd_saved', 0.0):.2f}** ({ct_roi.get('total_tokens_saved', 0):,} tok) |"
            ),
        ]
        if dashboard_path is not None:
            tok_uri = Path(dashboard_path).resolve().as_uri()
            wiki_uri = (Path(dashboard_path).resolve().parent / "wiki.html").as_uri()
            lines.extend([
                "",
                f"**Full History & Analytics (0 cloud tok):** [token_report.html]({tok_uri}) · [wiki.html]({wiki_uri})"
                if is_en else
                f"**Storico & Analitica Completa (0 token cloud):** [token_report.html]({tok_uri}) · [wiki.html]({wiki_uri})",
            ])
        return "\n".join(lines)

    g = report.get("global_stats") or {}
    rem = g.get("remote") or {}
    loc = g.get("local") or {}
    roi = g.get("roi") or {}
    mem = g.get("memory_and_skills") or {}
    trend = rem.get("trend_stats") or {}
    rec_t = trend.get("recent") or {}
    hist_t = trend.get("historical") or {}

    lines = [
        "### Token Report (Cortical + Remote Cloud · 0 Remote Tokens)",
        "",
        "| Scope | Tokens (In / Out / Total) | Time & Frequency | Cost / Cloud Savings |" if is_en else "| Ambito | Token (In / Out / Tot) | Tempo & Frequenza | Costo / Risparmio |",
        "| --- | --- | --- | --- |",
        (
            f"| **Remote Cloud** | {rem.get('input_tokens', 0):,} in · {rem.get('output_tokens', 0):,} out · {rem.get('active_tokens', 0):,} active ({rem.get('cache_read_tokens', 0):,} cache) "
            f"| {rem.get('chat_count', 0)} chats ({rem.get('measured_chat_count', 0)} measured) · Cache {rem.get('cache_hit_pct', 0.0):.1f}% "
            f"| Est. cost: ~${rem.get('estimated_cost_usd', 0.0):.2f} |"
            if is_en else
            f"| **Cloud Remoto** | {rem.get('input_tokens', 0):,} in · {rem.get('output_tokens', 0):,} out · {rem.get('active_tokens', 0):,} attivi ({rem.get('cache_read_tokens', 0):,} cache) "
            f"| {rem.get('chat_count', 0)} chat ({rem.get('measured_chat_count', 0)} misurate) · Cache {rem.get('cache_hit_pct', 0.0):.1f}% "
            f"| Costo stimato: ~${rem.get('estimated_cost_usd', 0.0):.2f} |"
        ),
        (
            f"| **Local Cortical (Offload)** | {loc.get('input_tokens', 0):,} in · {loc.get('output_tokens', 0):,} out · {loc.get('total_tokens', 0):,} tot "
            f"| {loc.get('run_count', 0)} runs · {loc.get('total_elapsed_sec', 0.0):.1f}s (avg {loc.get('avg_elapsed_sec', 0.0):.1f}s) "
            f"| Cloud $0 · **Saved ~${roi.get('local_offload_usd_saved', 0.0):.2f}** ({roi.get('cloud_offload_share_pct', 0.0):.1f}% offload) |"
            if is_en else
            f"| **Cortical Locale (Offload)** | {loc.get('input_tokens', 0):,} in · {loc.get('output_tokens', 0):,} out · {loc.get('total_tokens', 0):,} tot "
            f"| {loc.get('run_count', 0)} run · {loc.get('total_elapsed_sec', 0.0):.1f}s (media {loc.get('avg_elapsed_sec', 0.0):.1f}s) "
            f"| Cloud $0 · **Risparmiati ~${roi.get('local_offload_usd_saved', 0.0):.2f}** ({roi.get('cloud_offload_share_pct', 0.0):.1f}% offload) |"
        ),
        (
            f"| **3+1 Memory & Skills** | {mem.get('estimated_memory_tokens_saved', 0):,} ctx tok saved "
            f"| {mem.get('syntheses_3plus1', 0)} synth · {mem.get('memory_insights', 0)} insights · {mem.get('learned_skills', 0)} skills ({mem.get('skill_uses', 0)} uses) "
            f"| **Total Saved: ~${roi.get('estimated_usd_saved', 0.0):.2f}** ({roi.get('estimated_cloud_tokens_saved', 0):,} tok) |"
            if is_en else
            f"| **Memoria 3+1 & Skill** | {mem.get('estimated_memory_tokens_saved', 0):,} tok contesto risparmiati "
            f"| {mem.get('syntheses_3plus1', 0)} sintesi · {mem.get('memory_insights', 0)} insight · {mem.get('learned_skills', 0)} skill ({mem.get('skill_uses', 0)} usi) "
            f"| **Totale Risparmiati: ~${roi.get('estimated_usd_saved', 0.0):.2f}** ({roi.get('estimated_cloud_tokens_saved', 0):,} tok) |"
        ),
    ]
    if rec_t:
        lines.extend([
            "",
            f"**Trend Adozione (Ultime {trend.get('recent_window', 10)} chat vs Storico):** "
            f"Recente `{rec_t.get('adoption_rate_pct', 0.0):.1f}%` ({rec_t.get('cortical_chats', 0)}/{rec_t.get('chat_count', 0)}) "
            f"vs Storico `{hist_t.get('adoption_rate_pct', 0.0):.1f}%` ({hist_t.get('cortical_chats', 0)}/{hist_t.get('chat_count', 0)}) · "
            f"Delta `{trend.get('adoption_delta_pp', 0.0):+.1f} pp` · "
            f"Mediana token attivi recenti `{rec_t.get('median_active_tokens', 0):,}` vs storici `{hist_t.get('median_active_tokens', 0):,}`",
        ])

    by_model = loc.get("by_model") or []
    if by_model:
        ram_info = loc.get("system_ram_gb") or {}
        lines.extend([
            "",
            f"**Modelli Locali Usati & Contesto (RAM {ram_info.get('ram_available_gb', '?')}/{ram_info.get('ram_total_gb', '?')} GB):**",
        ])
        for m in by_model:
            lines.append(
                f"- `{m['model']}`: {m['runs']} run · {m['total_tokens']:,} tok "
                f"({m.get('elapsed_sec', 0.0):.1f}s) · ctx nativo `{m.get('context_window', 32768):,}` "
                f"(dinamico `{m.get('dynamic_num_ctx', 32768):,}`)"
            )

    per_task = (report.get("per_task") or [])[:5]
    if per_task:
        lines.extend(["", "**Top Local Cortical Tasks:**"])
        for t in per_task:
            lines.append(
                f"- `{t['episode_id']}` ({t['status']}): {t['local_total_tokens']:,} local tok "
                f"({t['run_count']} runs, {', '.join(t.get('models') or ['local'])}) — {t['goal'][:60]}"
            )

    per_chat = (report.get("per_chat") or [])[:5]
    if per_chat:
        lines.extend(["", "**Recent Remote Chats:**"])
        for c in per_chat:
            tag = " [cortical]" if c.get("uses_cortical") else ""
            lines.append(
                f"- `{c['conversation_id'][:8]}` ({c['source']}){tag}: "
                f"in {c['input_tokens']:,} + cache {c['cache_read_tokens']:,} + out {c['output_tokens']:,} "
                f"(~${c['estimated_cost_usd']:.2f}) — {c['title'][:55]}"
            )

    insight = report.get("local_llm_insight")
    if isinstance(insight, dict) and insight.get("text"):
        lines.extend(["", f"**Local Analyst ({insight.get('source', 'local')}):** {insight['text']}"])

    exp = report.get("explanations") or {}
    if exp:
        lines.extend([
            "",
            "**Note Metodologiche (calcolo a 0 token cloud):**",
            f"- **[1] Remote:** {exp.get('remote_usage', '')}",
            f"- **[2] Locale & Tempo:** {exp.get('local_offload', '')}",
            f"- **[3] Memoria 3+1:** {exp.get('memory_saved', '')}",
            f"- **[4] Risparmio USD:** {exp.get('cloud_savings_usd', '')}",
            f"- **[5] Quota Offload:** {exp.get('offload_share', '')}",
        ])

    if dashboard_path is not None:
        tok_uri = Path(dashboard_path).resolve().as_uri()
        wiki_uri = (Path(dashboard_path).resolve().parent / "wiki.html").as_uri()
        lines.extend([
            "",
            f"**Dashboard Statiche (Zero-Server):** [token_report.html]({tok_uri}) · [wiki.html]({wiki_uri})",
        ])

    return "\n".join(lines)


def render_static_token_dashboard_html(report: dict[str, Any]) -> str:
    """Renders a self-contained, zero-server static HTML ROI & Token Dashboard."""
    safe_json = json.dumps(report, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Cortical Token Report · Global &amp; Per-Task ROI</title>
  <style>
    :root {{ --bg:#0b1120; --card:#131c2e; --border:#24324a; --text:#e2e8f0; --muted:#94a3b8; --accent:#38bdf8; --emerald:#34d399; --amber:#fbbf24; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; background:var(--bg); color:var(--text); line-height:1.5; }}
    .wrap {{ width:100%; max-width:1280px; margin:0 auto; padding:24px 20px 56px; }}
    .top {{ display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; margin-bottom:20px; }}
    h1 {{ margin:0; font-size:1.55rem; }}
    .pill {{ font-size:0.78rem; padding:4px 10px; border-radius:999px; border:1px solid var(--border); color:var(--emerald); background:rgba(52,211,153,0.08); }}
    .kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:12px; margin-bottom:20px; }}
    .kpi {{ padding:16px; border:1px solid var(--border); border-radius:12px; background:var(--card); }}
    .kpi .v {{ font-size:1.65rem; font-weight:800; color:var(--emerald); }}
    .kpi .l {{ font-size:0.82rem; color:var(--muted); margin-top:4px; }}
    .grid2 {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(340px,1fr)); gap:14px; margin-bottom:20px; }}
    .card {{ padding:16px; border:1px solid var(--border); border-radius:12px; background:var(--card); min-width:0; }}
    .card h2 {{ margin:0 0 10px; font-size:1rem; color:var(--accent); }}
    .bar-row {{ margin-bottom:10px; }}
    .bar-meta {{ display:flex; justify-content:space-between; font-size:0.82rem; margin-bottom:4px; gap:8px; flex-wrap:wrap; }}
    .bar-bg {{ height:10px; border-radius:999px; background:#090e1a; overflow:hidden; border:1px solid var(--border); }}
    .bar-fill {{ height:100%; background:linear-gradient(90deg,var(--accent),var(--emerald)); }}
    .row {{ display:flex; justify-content:space-between; gap:12px; padding:8px 0; border-bottom:1px solid var(--border); font-size:0.84rem; overflow-wrap:anywhere; }}
    .row:last-child {{ border-bottom:none; }}
    code {{ color:var(--accent); font-size:0.8rem; word-break:break-word; }}
    .notes {{ font-size:0.82rem; color:var(--muted); }}
    .notes li {{ margin-bottom:5px; }}
    svg.chart {{ width:100%; height:190px; display:block; }}
    .delta-up {{ color:var(--emerald); font-weight:700; }}
    .delta-down {{ color:var(--amber); font-weight:700; }}
    .info-tip {{ position:relative; display:inline-flex; align-items:center; justify-content:center; width:17px; height:17px; border-radius:50%; border:1px solid var(--accent); color:var(--accent); font-size:0.7rem; cursor:pointer; user-select:none; vertical-align:middle; margin-left:4px; }}
    .info-pop {{ display:none; position:absolute; left:0; top:22px; z-index:60; width:270px; padding:9px 11px; border-radius:8px; background:#090e1a; border:1px solid var(--accent); color:var(--text); font-size:0.76rem; font-weight:400; line-height:1.45; box-shadow:0 8px 24px rgba(0,0,0,0.5); text-align:left; }}
    .info-tip:hover .info-pop, .info-tip:focus .info-pop, .info-tip.open .info-pop {{ display:block; }}
  </style>
</head>
<body>
  <div class="wrap" id="app">Caricamento...</div>
  <script>
    const REPORT = {safe_json};
    const g = REPORT.global_stats || {{}};
    const rem = g.remote || {{}};
    const loc = g.local || {{}};
    const roi = g.roi || {{}};
    const mem = g.memory_and_skills || {{}};
    const exp = REPORT.explanations || {{}};
    const fmt = (n) => Number(n || 0).toLocaleString('en-US');
    const esc = (s) => String(s || '').replace(/[&<>"']/g, (c) => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));

    const totWork = Math.max(1, Number(loc.total_tokens || 0) + Number(rem.active_tokens || 0));
    const locPct = ((Number(loc.total_tokens || 0) / totWork) * 100).toFixed(1);
    const remPct = ((Number(rem.active_tokens || 0) / totWork) * 100).toFixed(1);
    const cachePct = Number(rem.cache_hit_pct || 0).toFixed(1);

    const trend = rem.trend_stats || {{}};
    const recT = trend.recent || {{}};
    const histT = trend.historical || {{}};
    const deltaPp = Number(trend.adoption_delta_pp || 0);
    const series = trend.daily_series || [];
    const maxDayTok = Math.max(1, ...series.map((d) => Number(d.active_tokens || 0)));
    const svgW = 640, svgH = 175, padL = 10, padB = 26, usableH = svgH - padB - 14;
    const barW = series.length ? Math.max(14, Math.floor((svgW - padL * 2) / series.length) - 6) : 24;
    const barsSvg = series.map((d, i) => {{
      const x = padL + i * (barW + 6);
      const h = Math.max(4, Math.round((Number(d.active_tokens || 0) / maxDayTok) * usableH));
      const y = svgH - padB - h;
      const cortRatio = d.chats ? (d.cortical_chats / d.chats) : 0;
      const ch = Math.round(h * cortRatio);
      const cy = svgH - padB - ch;
      const lbl = (d.date || '').slice(5);
      return `<g><title>${{esc(d.date)}}: ${{fmt(d.active_tokens)}} active tok · ${{d.cortical_chats}}/${{d.chats}} Cortical chat · ~$${{Number(d.cost_usd||0).toFixed(2)}}</title>`
        + `<rect x="${{x}}" y="${{y}}" width="${{barW}}" height="${{h}}" rx="4" fill="#1e3a5f" />`
        + (ch > 0 ? `<rect x="${{x}}" y="${{cy}}" width="${{barW}}" height="${{ch}}" rx="4" fill="#34d399" />` : '')
        + `<text x="${{x + barW/2}}" y="${{svgH - 8}}" text-anchor="middle" fill="#94a3b8" font-size="10">${{esc(lbl)}}</text></g>`;
    }}).join('');

    const tip = (txt) => `<span class="info-tip" tabindex="0" onclick="this.classList.toggle('open')">i<span class="info-pop">${{esc(txt)}}</span></span>`;
    let LANG = localStorage.getItem('cortical_lang') || 'it';
    let CURRENT_DAYS = Number(REPORT.range_days || 0);
    let STUDY_METRIC = 'tokens';
    let STUDY_MODEL = 'all';

    const I18N = {{
      it: {{
        sub: 'Generato localmente a 0 token cloud',
        zero: 'Zero Token Remoti',
        k1: 'Token Cloud Risparmiati (stima)',
        k2: 'Risparmio Stimato',
        k3: 'Token Locali (Cortical)',
        k4: 'Cloud Attivi',
        bal: 'Bilancio Lavoro Attivo & Efficienza Cache',
        locLbl: 'Locale Cortical',
        remLbl: 'Cloud Attivo',
        cacheLbl: 'Prompt Cache Hit Remoto',
        trendTitle: '📈 Adozione Recente vs Storico',
        recentChats: 'Ultime',
        recAdopt: 'Adozione Recente',
        histAdopt: 'Adozione Storica',
        deltaAdopt: 'Variazione Adozione',
        medTok: 'Mediana Token Attivi (Recente vs Storico)',
        dailyTrend: '📊 Trend Giornaliero',
        noDaily: 'Dati giornalieri non sufficienti.',
        all: 'Tutto',
        insightTitle: '🧠 Analisi Locale',
        studyTitle: '🤖 Studio per Modello, Tempo & Task',
        mTok: 'Metrica: Token Totali',
        mTime: 'Metrica: Tempo (s)',
        mRuns: 'Metrica: Numero Run',
        allModels: 'Tutti i Modelli',
        topTasks: '⚡ Top Task Locali (Cortical)',
        noRuns: 'Nessun run locale registrato.',
        noModelTasks: 'Nessun task per questo modello.',
        noModels: 'Nessun modello locale registrato.',
        cloudChats: '☁️ Chat Cloud',
        measured: 'misurate',
        estimated: 'stimate',
        noChats: 'Nessuna chat in questa finestra.',
        noTranscripts: 'Nessun transcript remoto trovato.',
        lastPrefix: 'ultimi ',
        daysSuffix: 'g',
        notesTitle: '📐 Note Metodologiche & Formule',
        n1: 'Remoto',
        n2: 'Locale & Tempo',
        n3: 'Memoria 3+1',
        n4: 'Risparmio USD',
        n5: 'Quota Offload',
        syn: 'sintesi',
        ins: 'insight',
        skl: 'skill (Cortical Skill Engine)',
      }},
      en: {{
        sub: 'Computed locally at 0 cloud tokens',
        zero: 'Zero Remote Tokens',
        k1: 'Est. Cloud Tokens Saved',
        k2: 'Est. USD Saved',
        k3: 'Local Tokens (Cortical)',
        k4: 'Remote Active Tokens',
        bal: 'Active Work Balance & Cache Efficiency',
        locLbl: 'Cortical Local',
        remLbl: 'Remote Active',
        cacheLbl: 'Remote Prompt Cache Hit',
        trendTitle: '📈 Recent vs Historical Adoption',
        recentChats: 'Last',
        recAdopt: 'Recent Adoption',
        histAdopt: 'Historical Adoption',
        deltaAdopt: 'Adoption Delta',
        medTok: 'Median Active Tokens (Recent vs Hist.)',
        dailyTrend: '📊 Daily Trend',
        noDaily: 'Not enough daily data.',
        all: 'All',
        insightTitle: '🧠 Local LLM Analysis',
        studyTitle: '🤖 Model, Time & Task Study',
        mTok: 'Metric: Total Tokens',
        mTime: 'Metric: Elapsed Time (s)',
        mRuns: 'Metric: Run Count',
        allModels: 'All Models',
        topTasks: '⚡ Top Local Tasks (Cortical)',
        noRuns: 'No local runs recorded.',
        noModelTasks: 'No tasks for this model.',
        noModels: 'No local models recorded.',
        cloudChats: '☁️ Cloud Chats',
        measured: 'measured',
        estimated: 'estimated',
        noChats: 'No chats in this window.',
        noTranscripts: 'No remote transcripts found.',
        lastPrefix: 'last ',
        daysSuffix: 'd',
        notesTitle: '📐 Methodology & Formulas',
        n1: 'Remote',
        n2: 'Local & Time',
        n3: '3+1 Memory',
        n4: 'USD Savings',
        n5: 'Offload Share',
        syn: 'syntheses',
        ins: 'insights',
        skl: 'skills (Cortical Skill Engine)',
      }},
    }};

    window.toggleLang = function() {{
      LANG = LANG === 'it' ? 'en' : 'it';
      localStorage.setItem('cortical_lang', LANG);
      window.renderDashboard();
    }};

    window.renderModelStudy = function() {{
      const sel = document.getElementById('study-metric');
      if (sel) STUDY_METRIC = sel.value || 'tokens';
      const L = I18N[LANG] || I18N.it;
      const items = loc.by_model || [];
      const vals = items.map((m) => STUDY_METRIC === 'elapsed' ? Number(m.elapsed_sec||0) : (STUDY_METRIC === 'runs' ? Number(m.runs||0) : Number(m.total_tokens||0)));
      const maxV = Math.max(1, ...vals);
      const target = document.getElementById('model-study-bars');
      if (!target) return;
      target.innerHTML = items.map((m, idx) => {{
        const v = vals[idx];
        const pct = Math.max(2, Math.round((v / maxV) * 100));
        const lbl = STUDY_METRIC === 'elapsed' ? `${{v.toFixed(1)}}s` : fmt(v);
        return `<div class="bar-row"><div class="bar-meta"><span><code>${{esc(m.model)}}</code></span><span><b>${{lbl}}</b></span></div><div class="bar-bg"><div class="bar-fill" style="width:${{pct}}%"></div></div></div>`;
      }}).join('') || `<div class="row">${{esc(L.noModels)}}</div>`;
    }};

    window.renderTaskFilter = function() {{
      const sel = document.getElementById('study-model');
      if (sel) STUDY_MODEL = sel.value || 'all';
      const L = I18N[LANG] || I18N.it;
      const filtered = (REPORT.per_task || []).filter((t) => STUDY_MODEL === 'all' || (t.models || []).includes(STUDY_MODEL)).slice(0, 10);
      const box = document.getElementById('tasks-box');
      if (!box) return;
      box.innerHTML = filtered.map((t) =>
        `<div class="row"><span><code>${{esc(t.episode_id)}}</code> · ${{esc(t.goal)}}</span><span style="white-space:nowrap;"><b>${{fmt(t.local_total_tokens)}}</b> tok (${{t.run_count}} run · ${{Number(t.elapsed_sec||0).toFixed(1)}}s)</span></div>`
      ).join('') || `<div class="row">${{esc(STUDY_MODEL === 'all' ? L.noRuns : L.noModelTasks)}}</div>`;
    }};

    window.setRangeDays = function(days) {{
      CURRENT_DAYS = Number(days || 0);
      const L = I18N[LANG] || I18N.it;
      const cutoff = CURRENT_DAYS > 0 ? (Date.now() - CURRENT_DAYS * 86400000) : 0;
      const chats = (REPORT.per_chat || []).filter((c) => {{
        if (!cutoff) return true;
        const ts = Date.parse(c.updated_at || c.started_at || '');
        return !ts || ts >= cutoff;
      }});
      const titleEl = document.getElementById('chats-title');
      const box = document.getElementById('chats-box');
      if (titleEl) {{
        const winLbl = CURRENT_DAYS ? `${{L.lastPrefix}}${{CURRENT_DAYS}}${{L.daysSuffix}}` : `${{rem.measured_chat_count || 0}} ${{L.measured}} / ${{rem.estimated_chat_count || 0}} ${{L.estimated}}`;
        titleEl.textContent = `${{L.cloudChats}} (${{winLbl}} · ${{chats.length}} chat)`;
      }}
      if (box) {{
        box.innerHTML = chats.slice(0, 10).map((c) =>
          `<div class="row"><span><code>${{esc((c.conversation_id||'').slice(0,8))}}</code> (${{esc(c.source)}}) ${{c.uses_cortical ? '⚡' : ''}} · ${{esc(c.title)}}</span><span style="white-space:nowrap;">in ${{fmt(c.input_tokens)}} · out ${{fmt(c.output_tokens)}} (~$${{Number(c.estimated_cost_usd||0).toFixed(2)}})</span></div>`
        ).join('') || `<div class="row">${{esc(REPORT.per_chat && REPORT.per_chat.length ? L.noChats : L.noTranscripts)}}</div>`;
      }}
    }};

    window.renderDashboard = function() {{
      const L = I18N[LANG] || I18N.it;
      const modelsHtml = (loc.by_model || []).map((m) =>
        `<div class="row"><span><code>${{esc(m.model)}}</code> (${{m.runs}} run · ${{Number(m.elapsed_sec||0).toFixed(1)}}s)</span><span style="white-space:nowrap;"><b>${{fmt(m.total_tokens)}}</b> tok · ctx ${{fmt(m.context_window)}} (dyn ${{fmt(m.dynamic_num_ctx)}})</span></div>`
      ).join('') || `<div class="row">${{esc(L.noModels)}}</div>`;

      const trendCard = `
        <div class="grid2">
          <div class="card">
            <h2>${{L.trendTitle}} (${{L.recentChats}} ${{trend.recent_window || 10}} chat)</h2>
            <div class="row"><span>${{L.recAdopt}}</span><span><b>${{Number(recT.adoption_rate_pct||0).toFixed(1)}}%</b> (${{recT.cortical_chats||0}}/${{recT.chat_count||0}} chat)</span></div>
            <div class="row"><span>${{L.histAdopt}}</span><span><b>${{Number(histT.adoption_rate_pct||0).toFixed(1)}}%</b> (${{histT.cortical_chats||0}}/${{histT.chat_count||0}} chat)</span></div>
            <div class="row"><span>${{L.deltaAdopt}}</span><span class="${{deltaPp >= 0 ? 'delta-up' : 'delta-down'}}">${{deltaPp >= 0 ? '+' : ''}}${{deltaPp.toFixed(1)}} pp</span></div>
            <div class="row"><span>${{L.medTok}}</span><span><b>${{fmt(recT.median_active_tokens)}}</b> vs ${{fmt(histT.median_active_tokens)}}</span></div>
          </div>
          <div class="card">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; margin-bottom:10px;">
              <h2 style="margin:0;">${{L.dailyTrend}}</h2>
              <div style="display:flex; gap:6px; flex-wrap:wrap; align-items:center; font-size:0.76rem; color:var(--muted);">
                <button class="pill" style="cursor:pointer;padding:2px 8px;" onclick="setRangeDays(7)">7${{L.daysSuffix}}</button>
                <button class="pill" style="cursor:pointer;padding:2px 8px;" onclick="setRangeDays(30)">30${{L.daysSuffix}}</button>
                <button class="pill" style="cursor:pointer;padding:2px 8px;" onclick="setRangeDays(90)">90${{L.daysSuffix}}</button>
                <button class="pill" style="cursor:pointer;padding:2px 8px;" onclick="setRangeDays(0)">${{L.all}}</button>
                <span style="display:inline-flex; align-items:center; gap:5px;"><i style="width:10px; height:10px; border-radius:3px; background:#1e3a5f; display:inline-block;"></i> Cloud</span>
                <span style="display:inline-flex; align-items:center; gap:5px;"><i style="width:10px; height:10px; border-radius:3px; background:#34d399; display:inline-block;"></i> Cortical</span>
              </div>
            </div>
            ${{series.length ? `<svg class="chart" viewBox="0 0 ${{svgW}} ${{svgH}}" preserveAspectRatio="none">${{barsSvg}}</svg>` : `<div style="color:var(--muted);">${{L.noDaily}}</div>`}}
          </div>
        </div>`;

      const insightHtml = REPORT.local_llm_insight?.text
        ? `<div class="card" style="margin-bottom:20px; border-color:var(--accent);"><h2>${{L.insightTitle}} (${{esc(REPORT.local_llm_insight.source)}})</h2><div style="white-space:pre-wrap; font-size:0.9rem;">${{esc(REPORT.local_llm_insight.text)}}</div></div>`
        : '';

      document.getElementById('app').innerHTML = `
        <div class="top">
          <div>
            <h1>📊 Cortical Token Report &amp; Cloud ROI</h1>
            <div style="font-size:0.84rem; color:var(--muted);"><b>${{L.sub}}</b> · <a href="./wiki.html" style="color:var(--accent);">🧠 Wiki</a> · <a href="./settings.html" style="color:var(--accent);">⚙️ Settings</a> · <a href="./help.html" style="color:var(--accent);">❓ Help</a> · <a href="./index.html" style="color:var(--accent);">🏠 Home</a></div>
          </div>
          <div style="display:flex; gap:6px; flex-wrap:wrap; align-items:center;">
            <button class="pill" style="cursor:pointer;" onclick="toggleLang()">${{LANG === 'it' ? '🇮🇹 IT' : '🇬🇧 EN'}}</button>
            <span class="pill">${{L.zero}}</span>
          </div>
        </div>
        <div class="kpis">
          <div class="kpi"><div class="v">${{fmt(roi.estimated_cloud_tokens_saved)}}</div><div class="l">${{L.k1}} ${{tip((exp.local_offload||'') + ' ' + (exp.memory_saved||''))}}</div></div>
          <div class="kpi"><div class="v">~$${{Number(roi.estimated_usd_saved || 0).toFixed(2)}}</div><div class="l">${{L.k2}} (${{Number(roi.cloud_offload_share_pct || 0).toFixed(1)}}% offload) ${{tip(exp.cloud_savings_usd||'')}}</div></div>
          <div class="kpi"><div class="v">${{fmt(loc.total_tokens)}}</div><div class="l">${{L.k3}} (${{loc.run_count || 0}} run · ${{Number(loc.total_elapsed_sec || 0).toFixed(1)}}s) ${{tip(exp.local_offload||'')}}</div></div>
          <div class="kpi"><div class="v">${{fmt(rem.active_tokens)}}</div><div class="l">${{L.k4}} (${{rem.chat_count || 0}} chat · ~$${{Number(rem.estimated_cost_usd || 0).toFixed(2)}}) ${{tip(exp.remote_usage||'')}}</div></div>
        </div>
        <div class="card" style="margin-bottom:20px;">
          <h2>${{L.bal}} ${{tip(exp.offload_share||'')}}</h2>
          <div class="bar-row"><div class="bar-meta"><span>${{L.locLbl}} (${{fmt(loc.total_tokens)}} tok · $0.00)</span><span>${{locPct}}%</span></div><div class="bar-bg"><div class="bar-fill" style="width:${{locPct}}%"></div></div></div>
          <div class="bar-row"><div class="bar-meta"><span>${{L.remLbl}} (${{fmt(rem.active_tokens)}} tok)</span><span>${{remPct}}%</span></div><div class="bar-bg"><div class="bar-fill" style="width:${{remPct}}%; background:var(--amber);"></div></div></div>
          <div class="bar-row" style="margin-bottom:0;"><div class="bar-meta"><span>${{L.cacheLbl}} (${{fmt(rem.cache_read_tokens)}} cache read)</span><span>${{cachePct}}%</span></div><div class="bar-bg"><div class="bar-fill" style="width:${{cachePct}}%"></div></div></div>
        </div>
        ${{trendCard}}
        ${{insightHtml}}
        <div class="card" style="margin-bottom:20px;">
          <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; margin-bottom:10px;">
            <h2 style="margin:0;">${{L.studyTitle}} (RAM ${{loc.system_ram_gb?.ram_available_gb ?? '?'}} / ${{loc.system_ram_gb?.ram_total_gb ?? '?'}} GB)</h2>
            <div style="display:flex; gap:8px; flex-wrap:wrap;">
              <select id="study-metric" onchange="renderModelStudy()" style="background:#090e1a;color:var(--text);border:1px solid var(--border);border-radius:6px;padding:4px 8px;font-size:0.8rem;">
                <option value="tokens" ${{STUDY_METRIC === 'tokens' ? 'selected' : ''}}>${{L.mTok}}</option>
                <option value="elapsed" ${{STUDY_METRIC === 'elapsed' ? 'selected' : ''}}>${{L.mTime}}</option>
                <option value="runs" ${{STUDY_METRIC === 'runs' ? 'selected' : ''}}>${{L.mRuns}}</option>
              </select>
              <select id="study-model" onchange="renderTaskFilter()" style="background:#090e1a;color:var(--text);border:1px solid var(--border);border-radius:6px;padding:4px 8px;font-size:0.8rem;">
                <option value="all" ${{STUDY_MODEL === 'all' ? 'selected' : ''}}>${{L.allModels}}</option>
                ${{(loc.by_model || []).map((m) => `<option value="${{esc(m.model)}}" ${{STUDY_MODEL === m.model ? 'selected' : ''}}>${{esc(m.model)}}</option>`).join('')}}
              </select>
            </div>
          </div>
          <div id="model-study-bars" style="margin-bottom:10px;"></div>
          ${{modelsHtml}}
        </div>
        <div class="grid2">
          <div class="card"><h2>${{L.topTasks}}</h2><div id="tasks-box"></div></div>
          <div class="card"><h2 id="chats-title">${{L.cloudChats}}</h2><div id="chats-box"></div></div>
        </div>
        <div class="card">
          <h2>${{L.notesTitle}}</h2>
          <ul class="notes">
            <li><b>[1] ${{L.n1}}:</b> ${{esc(exp.remote_usage)}}</li>
            <li><b>[2] ${{L.n2}}:</b> ${{esc(exp.local_offload)}}</li>
            <li><b>[3] ${{L.n3}}:</b> ${{esc(exp.memory_saved)}} (${{mem.syntheses_3plus1 || 0}} ${{L.syn}}, ${{mem.memory_insights || 0}} ${{L.ins}}, ${{mem.learned_skills || 0}} ${{L.skl}})</li>
            <li><b>[4] ${{L.n4}}:</b> ${{esc(exp.cloud_savings_usd)}}</li>
            <li><b>[5] ${{L.n5}}:</b> ${{esc(exp.offload_share)}}</li>
          </ul>
        </div>`;
      window.renderModelStudy();
      window.renderTaskFilter();
      window.setRangeDays(CURRENT_DAYS);
    }};

    window.renderDashboard();
  </script>
</body>
</html>
"""


def export_static_token_dashboard(report: dict[str, Any], output_path: Path) -> Path:
    """Writes the self-contained static Token Report HTML dashboard to `output_path`."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_static_token_dashboard_html(report), encoding="utf-8")
    return out
