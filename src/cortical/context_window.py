"""Context window budgeting, multi-message chunking, and LLM paragraph summarization.

Prevents brutal character truncation by splitting long context along paragraph
boundaries, optionally summarizing older paragraphs via the local LLM, and
serializing chunks into multiple chat messages while tracking token occupancy.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Optional


DEFAULT_MODEL_CONTEXT_WINDOWS: dict[str, int] = {
    "qwen3.8:27b-iq2_xs": 32768,
    "qwen3.8:27b": 32768,
    "qwen3:8b": 32768,
    "qwen2.5:1.5b": 32768,
}


def estimate_tokens(text: str) -> int:
    """Estimates token count (~4 chars/token) without external tokenizer dependencies."""
    s = str(text or "")
    if not s.strip():
        return 0
    return max(1, (len(s) + 3) // 4)


def clamp_context_window(value: Any, fallback: int = 32768) -> int:
    """Clamps a configured context window to a safe operational range."""
    try:
        num = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(2048, min(262144, num))


def get_model_context_window(
    model_id: str,
    configured_windows: Optional[dict[str, Any]] = None,
    fallback: int = 32768,
) -> int:
    """Resolves the configured context window (in tokens) for a given model."""
    mid = str(model_id or "").strip()
    if configured_windows and mid in configured_windows:
        return clamp_context_window(configured_windows[mid], fallback=fallback)
    if mid in DEFAULT_MODEL_CONTEXT_WINDOWS:
        return DEFAULT_MODEL_CONTEXT_WINDOWS[mid]
    low = mid.lower()
    if "qwen3" in low or "qwen2.5" in low or "llama3" in low or "gemma" in low:
        return 32768
    return fallback


def split_into_paragraphs(text: str, max_para_tokens: int = 900) -> list[str]:
    """Splits text along paragraph (or sentence) boundaries without mid-word truncation."""
    raw = str(text or "").strip()
    if not raw:
        return []
    blocks = [b.strip() for b in re.split(r"\n\s*\n+", raw) if b.strip()]
    result: list[str] = []
    max_chars = max(200, max_para_tokens * 4)
    for blk in blocks:
        if len(blk) <= max_chars:
            result.append(blk)
            continue
        # Split oversized block on line or sentence boundaries
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", blk) if s.strip()]
        cur = ""
        for sent in sentences:
            if cur and len(cur) + len(sent) + 1 > max_chars:
                result.append(cur)
                cur = sent
            else:
                cur = f"{cur} {sent}".strip() if cur else sent
        if cur:
            result.append(cur)
    return result


def _summarize_paragraph_group(
    paragraphs: list[str],
    target_tokens: int,
    summarize_fn: Optional[Callable[[str, int], Optional[str]]] = None,
) -> list[str]:
    """Summarizes older paragraphs via local LLM or clean sentence-level compaction."""
    joined = "\n\n".join(paragraphs)
    if summarize_fn is not None:
        try:
            prompt = (
                f"Riassumi fedelmente i seguenti paragrafi mantenendo tutti i fatti tecnici, "
                f"percorsi file, nomi e decisioni, entro circa {target_tokens} token, senza troncare frasi:\n\n{joined}"
            )
            summary = summarize_fn(prompt, target_tokens)
            if summary and summary.strip():
                return split_into_paragraphs(summary.strip(), max_para_tokens=max(300, target_tokens))
        except Exception:  # noqa: BLE001
            pass

    # Deterministic fallback: keep leading + key sentences of each paragraph intact
    compacted: list[str] = []
    budget_chars = max(320, target_tokens * 4)
    used_chars = 0
    for p in paragraphs:
        sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", p) if s.strip()]
        if not sents:
            continue
        pick = sents[0]
        if len(sents) > 1 and len(pick) + len(sents[-1]) + 1 <= 360:
            pick = f"{pick} ... {sents[-1]}"
        if used_chars + len(pick) + 2 > budget_chars and compacted:
            break
        compacted.append(pick)
        used_chars += len(pick) + 2
    return compacted


def fit_context_to_window(
    *,
    system_prompt: str,
    user_prompt: str,
    extra_context: str = "",
    history_messages: Optional[list[dict[str, str]]] = None,
    context_window_tokens: int = 32768,
    reserve_output_tokens: int = 1500,
    summarize_fn: Optional[Callable[[str, int], Optional[str]]] = None,
    chunk_tokens: int = 1200,
    strategy_override: str = "auto",
) -> dict[str, Any]:
    """Fits context + history into the model window via multi-message chunking and LLM summarization.

    Never performs brutal mid-string truncation. Returns ready-to-send `messages`,
    `fitted_context` (for single-prompt runners), and `telemetry` (window & occupancy).
    """
    win = clamp_context_window(context_window_tokens)
    base_tokens = estimate_tokens(system_prompt) + estimate_tokens(user_prompt)
    avail_tokens = max(512, win - base_tokens - max(256, reserve_output_tokens))

    hist_list = [
        {"role": str(m["role"]), "content": str(m["content"])}
        for m in (history_messages or [])
        if m.get("role") in {"user", "assistant"} and str(m.get("content") or "").strip()
    ]
    paragraphs = split_into_paragraphs(extra_context, max_para_tokens=max(400, chunk_tokens // 2))

    ctx_tokens = sum(estimate_tokens(p) for p in paragraphs)
    hist_tokens = sum(estimate_tokens(m["content"]) for m in hist_list)
    strat_req = (strategy_override or "auto").strip().lower()
    strategy = "direct"

    # 1. If combined context + history exceeds budget (or summarize forced), summarize older paragraphs first
    if paragraphs and (strat_req == "summarize" or (strat_req != "direct" and ctx_tokens + hist_tokens > avail_tokens)):
        strategy = "llm_paragraph_summary" if summarize_fn is not None else "paragraph_compaction"
        # Reserve up to 35% of available budget for recent chat history
        hist_budget = min(hist_tokens, int(avail_tokens * 0.35))
        kept_hist: list[dict[str, str]] = []
        running_h = 0
        for m in reversed(hist_list):
            t = estimate_tokens(m["content"])
            if running_h + t <= hist_budget or not kept_hist:
                kept_hist.append(m)
                running_h += t
        hist_list = list(reversed(kept_hist))
        ctx_budget = max(320, avail_tokens - running_h)

        if ctx_tokens > ctx_budget:
            # Keep newest/tail paragraphs intact if possible, summarize earlier paragraphs
            tail_paras: list[str] = []
            tail_tok = 0
            tail_limit = int(ctx_budget * 0.55)
            idx = len(paragraphs) - 1
            while idx >= 0:
                pt = estimate_tokens(paragraphs[idx])
                if tail_tok + pt <= tail_limit or not tail_paras:
                    tail_paras.append(paragraphs[idx])
                    tail_tok += pt
                    idx -= 1
                else:
                    break
            tail_paras.reverse()
            head_paras = paragraphs[: idx + 1]
            if head_paras:
                head_budget = max(160, ctx_budget - tail_tok)
                summarized_head = _summarize_paragraph_group(head_paras, head_budget, summarize_fn=summarize_fn)
                paragraphs = summarized_head + tail_paras
            else:
                paragraphs = tail_paras

    # 2. Serialize paragraphs into multi-message chunks (so large context is split cleanly across messages)
    chunks: list[str] = []
    cur_chunk: list[str] = []
    cur_tok = 0
    per_chunk_limit = max(400, min(chunk_tokens, avail_tokens))
    for p in paragraphs:
        pt = estimate_tokens(p)
        if cur_chunk and cur_tok + pt > per_chunk_limit:
            chunks.append("\n\n".join(cur_chunk))
            cur_chunk = [p]
            cur_tok = pt
        else:
            cur_chunk.append(p)
            cur_tok += pt
    if cur_chunk:
        chunks.append("\n\n".join(cur_chunk))

    if len(chunks) > 1 and strategy == "direct":
        strategy = "multi_message"

    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    total_chunks = len(chunks)
    for i, ch in enumerate(chunks, start=1):
        prefix = f"[Contesto {i}/{total_chunks}]\n" if total_chunks > 1 else "[Contesto]\n"
        messages.append({"role": "user", "content": prefix + ch})
    messages.extend(hist_list)
    messages.append({"role": "user", "content": user_prompt})

    used_tokens = sum(estimate_tokens(m["content"]) for m in messages)
    occupancy_pct = round(min(100.0, (used_tokens / float(win)) * 100.0), 1)
    return {
        "messages": messages,
        "fitted_context": "\n\n".join(chunks),
        "telemetry": {
            "context_window_tokens": win,
            "used_tokens": used_tokens,
            "remaining_tokens": max(0, win - used_tokens),
            "occupancy_pct": occupancy_pct,
            "strategy": strategy,
            "chunks_count": total_chunks,
        },
    }
