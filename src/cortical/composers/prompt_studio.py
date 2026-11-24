"""Cortical Prompt Studio & One-Shot Ephemeral Loopback Browser Elicitor (`cortical next` — ADR-017).

Zero external dependencies (Python 3.10+ stdlib only), zero persistent daemons, zero external CDNs.
Provides:
1. Context Harvester + `TOON` compaction + `fail_closed` Privacy Vault boundary (`harvest_prompt_context`).
2. Persistent Loop Learning Store (`LoopMemoryStore` -> `loop_memory.json` + `.cortical_data/prompts/`).
3. Adaptive 2–5 Question Generator (`generate_adaptive_questions`) with Zero-LLM Stdlib + optional `@role:daily_coder`.
4. Deterministic 5-Trigger Confidence Gate (`evaluate_five_trigger_gate`) for autonomous Coordinator loops.
5. Role-Targeted Continuation Prompt Synthesizer (`synthesize_continuation_prompt`).
6. One-Shot Ephemeral `127.0.0.1:0` Browser Elicitor (`run_ephemeral_browser_elicitor`) with 256-bit token auth,
   strict `Host`/`Origin` anti-DNS-rebinding protection, and guaranteed immediate socket closure.
"""

from __future__ import annotations

import http.server
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Any, Callable, Optional

from ..compression.engine import compress_structured
from ..config import DEFAULT_VAULT_DB, invoke_configured_runner, load_cortical_config, remote_orchestrator_active
from ..privacy.sanitizer import classify_and_sanitize
from ..privacy.vault import PrivacyVault


TARGET_PROFILES: dict[str, dict[str, Any]] = {
    "pi": {
        "id": "pi",
        "label": "Local Worker (pi · @role:deep_reasoner / @role:daily_coder)",
        "role_header": "Local-First Autonomous Coding Worker (`pi` + `@role:deep_reasoner` / `@role:daily_coder`)",
        "remote_egress": False,
        "summary": "100% local execution at $0 cloud cost using Serena LSP, RTK compaction, and stdlib unittest.",
    },
    "argon": {
        "id": "argon",
        "label": "Coordinator (Argon · @role:orchestrator)",
        "role_header": "Principal Coordinator & Architecture Orchestrator (`Argon` · `@role:orchestrator`)",
        "remote_egress": False,
        "summary": "Decomposes work into tracked GitHub Issues/ADRs, delegates slices to workers, and enforces quality gates.",
    },
    "neon": {
        "id": "neon",
        "label": "QA & UX Persona (Neon · @role:reviewer)",
        "role_header": "End-to-End UX Researcher, Accessibility Auditor & QA Engineer (`Neon` · `@role:reviewer`)",
        "remote_egress": False,
        "summary": "Impersonates real users across CLI/SPA/harnesses, measures cognitive friction, and verifies edge cases.",
    },
    "hybrid": {
        "id": "hybrid",
        "label": "Hybrid (Remote Supervisor + Local Workers · fail_closed)",
        "role_header": "Hybrid Remote Supervisor + Local-First Execution Layer (`fail_closed` Privacy Boundary)",
        "remote_egress": True,
        "summary": "Keeps bulk reads/PII strictly local via cortical_local_offload while sending TOON summaries upstream.",
    },
    "general": {
        "id": "general",
        "label": "General Coding Harness (All 8 Harnesses)",
        "role_header": "Autonomous Principal Software Engineer (Cortical Unified 8-Harness Contract)",
        "remote_egress": True,
        "summary": "Portable structured continuation prompt compatible with Antigravity, Claude Code, Codex, OpenCode, OpenClaw, dsh & pi.",
    },
}

_REMOTE_HARNESS_TARGETS = {"hybrid", "general", "antigravity", "claude-code", "codex", "openclaw", "opencode", "dsh"}

_DESTRUCTIVE_RE = re.compile(
    r"\b(?:rm\s+-rf|drop\s+table|delete\s+all|force[- ]?push|reset\s+--hard|publish\s+publicly|"
    r"production\s+deploy|destroy|wipe|format\s+disk|open\s+external\s+pr)\b",
    re.IGNORECASE,
)
_BROAD_SCOPE_RE = re.compile(
    r"\b(?:entire\s+codebase|rewrite\s+all|every\s+module|global\s+refactor|monorepo[- ]wide|migrate\s+everything)\b",
    re.IGNORECASE,
)
_AMBIGUOUS_RE = re.compile(r"\b(?:maybe|not\s+sure|whatever|something\s+like|either\s+or|idk)\b|\?", re.IGNORECASE)
_PRIVACY_SENSITIVE_RE = re.compile(
    r"(?:@private:|max_security|\.cortical_data|\.env\b|secret|iban|password|private\s+key|credential|ssn|tax\s*id)",
    re.IGNORECASE,
)
_KNOWN_DOMAIN_RE = re.compile(
    r"\b(?:cortical|vault|toon|mcp|sync|harness|runner|adr|wiki|dashboard|settings\.html|cli|doctor|bench|prompt|next|privacy|role)\b",
    re.IGNORECASE,
)


def normalize_target_profile(target: Optional[str], preferred: str = "general") -> tuple[str, str]:
    """Maps a CLI/MCP target name (`pi`, `argon`, `neon`, `claude-code`, etc.) to `(profile_key, raw_target)`."""
    raw = str(target or preferred or "general").strip().lower()
    if raw in TARGET_PROFILES:
        return raw, raw
    if raw in {"unsloth-studio", "local"}:
        return "pi", raw
    if raw in {"antigravity", "claude-code", "codex", "opencode", "openclaw", "dsh"}:
        return "hybrid", raw
    return ("general", raw or "general")


def is_remote_target(profile_key: str, raw_target: str, config: Optional[dict[str, Any]] = None) -> bool:
    """Returns True whenever synthesized prompts might traverse a remote cloud orchestrator/harness."""
    cfg = config or load_cortical_config()
    if remote_orchestrator_active(cfg):
        return True
    if raw_target in _REMOTE_HARNESS_TARGETS:
        return True
    return bool((TARGET_PROFILES.get(profile_key) or {}).get("remote_egress", True))


def resolve_cortical_runtime_dir(repo_root: Optional[Path] = None, data_dir: Optional[Path] = None) -> Path:
    """Resolves `.cortical_data` runtime directory for `loop_memory.json` and `.cortical_data/prompts/`."""
    if data_dir is not None:
        return Path(data_dir).expanduser().resolve()
    env_dir = os.environ.get("CORTICAL_LOOP_DIR")
    if env_dir:
        return Path(env_dir).expanduser().resolve()
    base = Path(repo_root or Path.cwd()).expanduser().resolve()
    return base / ".cortical_data"


class LoopMemoryStore:
    """Persists structured outcomes, preferences, rejected approaches, and reusable templates across prompt loops."""

    def __init__(self, path: Optional[Path] = None, *, repo_root: Optional[Path] = None, data_dir: Optional[Path] = None) -> None:
        base_dir = resolve_cortical_runtime_dir(repo_root=repo_root, data_dir=data_dir)
        self.path = Path(path).expanduser().resolve() if path is not None else (base_dir / "loop_memory.json")
        self.prompts_dir = self.path.parent / "prompts"

    def _default(self) -> dict[str, Any]:
        return {
            "schema": "cortical-loop-memory/v1",
            "iteration_count": 0,
            "preferred_target": "general",
            "recurring_constraints": [
                "Keep dependencies = [] in pyproject.toml (Python 3.10+ stdlib only).",
                "Enforce fail_closed Privacy Vault boundaries on remote egress.",
            ],
            "rejected_approaches": [],
            "answered_preferences": {},
            "last_completed_issue": None,
            "last_commit": "",
            "open_blockers": [],
            "history": [],
            "templates": [],
        }

    def load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return self._default()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return self._default()
            merged = self._default()
            merged.update(raw)
            return merged
        except Exception:  # noqa: BLE001
            return self._default()

    def save(self, state: dict[str, Any]) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return self.path

    def save_template(self, name: str, target: str, prompt_text: str, metadata: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        state = self.load()
        clean_name = re.sub(r"[^a-zA-Z0-9._ -]+", "", str(name or "Reusable Template")).strip()[:80] or "Reusable Template"
        tpl = {
            "id": re.sub(r"[^a-z0-9_-]+", "-", clean_name.lower()).strip("-") or "template",
            "name": clean_name,
            "target": target,
            "prompt": prompt_text,
            "metadata": metadata or {},
            "saved_at": int(time.time()),
        }
        templates = [t for t in state.get("templates", []) if t.get("id") != tpl["id"]]
        templates.insert(0, tpl)
        state["templates"] = templates[:20]
        self.save(state)
        return tpl

    def record_outcome(
        self,
        *,
        seed: str,
        target: str,
        answers: dict[str, Any],
        comments: dict[str, str],
        directives: str,
        confidence_score: float,
        mode_used: str,
        synthesized_prompt: str,
        issue: Optional[int] = None,
        last_commit: str = "",
    ) -> dict[str, Any]:
        state = self.load()
        state["iteration_count"] = int(state.get("iteration_count") or 0) + 1
        state["preferred_target"] = target or state.get("preferred_target") or "general"
        if issue is not None:
            state["last_completed_issue"] = int(issue)
        if last_commit:
            state["last_commit"] = last_commit

        prefs = dict(state.get("answered_preferences") or {})
        for qid, ans in (answers or {}).items():
            prefs[qid] = ans
        state["answered_preferences"] = prefs

        constraints = list(state.get("recurring_constraints") or [])
        rejected = list(state.get("rejected_approaches") or [])
        for note in [directives, *(comments or {}).values()]:
            for raw_line in str(note or "").splitlines():
                line = raw_line.strip(" -*\t")
                if len(line) < 6:
                    continue
                low = line.lower()
                if low.startswith(("avoid ", "never ", "do not ", "don't ", "no ")) and line not in rejected:
                    rejected.append(line[:180])
                elif line not in constraints:
                    constraints.append(line[:180])
        state["recurring_constraints"] = constraints[-12:]
        state["rejected_approaches"] = rejected[-10:]

        ts = int(time.time())
        short_id = secrets.token_hex(3)
        self.prompts_dir.mkdir(parents=True, exist_ok=True)
        prompt_file = self.prompts_dir / f"prompt_{ts}_{short_id}.md"
        prompt_file.write_text(synthesized_prompt.rstrip() + "\n", encoding="utf-8")

        entry = {
            "ts": ts,
            "seed": seed[:200],
            "target": target,
            "mode_used": mode_used,
            "confidence_score": confidence_score,
            "issue": issue,
            "prompt_path": str(prompt_file),
        }
        hist = list(state.get("history") or [])
        hist.append(entry)
        state["history"] = hist[-25:]
        self.save(state)
        return {"memory_path": str(self.path), "prompt_path": str(prompt_file), "iteration_count": state["iteration_count"]}


def _run_quick_cmd(cmd: list[str], cwd: Path, timeout: float = 2.2) -> str:
    try:
        res = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout, check=False)
        return (res.stdout or "").strip() if res.returncode == 0 else ""
    except Exception:  # noqa: BLE001
        return ""


def _sanitize_for_egress(text: str, *, remote_egress: bool, custom_terms: Optional[list[str]] = None) -> tuple[str, int]:
    if not text:
        return "", 0
    if not remote_egress:
        return text, 0
    res = classify_and_sanitize(
        text,
        policy="fail_closed",
        profile="medium",
        custom_terms=custom_terms,
        use_local_ner=False,
    )
    return str(res.get("sanitized_text") or ""), int(res.get("entity_count") or 0)


def harvest_prompt_context(
    seed: str = "",
    *,
    repo_root: Optional[Path] = None,
    vault_db: Optional[Path] = None,
    loop_store: Optional[LoopMemoryStore] = None,
    target: Optional[str] = None,
    focus_issue: Optional[int] = None,
    resume: bool = False,
    allow_gh: bool = True,
    config: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Gathers repo state, issues, ADRs, sanitized Vault context & `loop_memory` with `TOON` compaction."""
    cfg = config or load_cortical_config()
    root = Path(repo_root or Path.cwd()).expanduser().resolve()
    store = loop_store or LoopMemoryStore(repo_root=root)
    mem = store.load()

    prof_key, raw_target = normalize_target_profile(target, preferred=str(mem.get("preferred_target") or "general"))
    remote_egress = is_remote_target(prof_key, raw_target, cfg)
    custom_terms = list((cfg.get("privacy") or {}).get("custom_terms") or []) or None

    branch = _run_quick_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"], root) or "main"
    status_raw = _run_quick_cmd(["git", "status", "--porcelain"], root)
    dirty_files = [ln[3:].strip() for ln in status_raw.splitlines() if len(ln) > 3][:25]
    dirty_count = len([ln for ln in status_raw.splitlines() if ln.strip()])
    commits_raw = _run_quick_cmd(["git", "log", "-n", "5", "--oneline"], root)
    recent_commits = [c.strip() for c in commits_raw.splitlines() if c.strip()]
    last_commit = recent_commits[0].split(" ", 1)[0] if recent_commits else ""

    open_issues: list[dict[str, Any]] = []
    if allow_gh and shutil.which("gh"):
        gh_raw = _run_quick_cmd(
            ["gh", "issue", "list", "--state", "open", "--limit", "10", "--json", "number,title,labels"],
            root,
            timeout=2.8,
        )
        if gh_raw:
            try:
                parsed = json.loads(gh_raw)
                if isinstance(parsed, list):
                    for it in parsed:
                        lbls = [str(l.get("name") or "") for l in (it.get("labels") or []) if isinstance(l, dict)]
                        open_issues.append({"number": it.get("number"), "title": str(it.get("title") or ""), "labels": lbls})
            except Exception:  # noqa: BLE001
                open_issues = []

    adr_dir = root / "docs" / "adr"
    adrs: list[dict[str, str]] = []
    if adr_dir.is_dir():
        for p in sorted(adr_dir.glob("ADR-*.md"))[-8:]:
            first_h1 = next((ln.lstrip("# ").strip() for ln in p.read_text(encoding="utf-8", errors="ignore").splitlines() if ln.startswith("# ")), p.stem)
            adrs.append({"id": p.name.split("-", 2)[:2] and "-".join(p.name.split("-")[:2]), "title": first_h1[:110]})

    eff_seed_raw = str(seed or "").strip()
    if not eff_seed_raw or resume:
        if focus_issue is not None:
            matched = next((i for i in open_issues if i.get("number") == focus_issue), None)
            eff_seed_raw = f"Implement and verify GitHub Issue #{focus_issue}" + (f": {matched['title']}" if matched else "")
        elif open_issues:
            top_i = open_issues[0]
            eff_seed_raw = f"Continue next priority slice from Issue #{top_i['number']}: {top_i['title']}"
        elif dirty_files:
            eff_seed_raw = f"Complete, test, and verify in-progress changes across {', '.join(dirty_files[:3])}"
        elif recent_commits:
            eff_seed_raw = f"Continue logical next engineering step following commit {recent_commits[0]}"
        else:
            eff_seed_raw = "Continue from current repository state and verify full test suite"

    redacted_total = 0
    clean_seed, red_s = _sanitize_for_egress(eff_seed_raw, remote_egress=remote_egress, custom_terms=custom_terms)
    redacted_total += red_s

    clean_commits: list[str] = []
    for c in recent_commits:
        sc, rc = _sanitize_for_egress(c, remote_egress=remote_egress, custom_terms=custom_terms)
        redacted_total += rc
        clean_commits.append(sc)

    clean_dirty = [
        d for d in dirty_files
        if ".cortical_data" not in d and not d.endswith((".env", ".pem", ".key"))
    ]

    v_db = Path(vault_db or os.environ.get("CORTICAL_VAULT_DB") or DEFAULT_VAULT_DB).expanduser()
    safe_aliases: list[dict[str, Any]] = []
    blocked_local_only_count = 0
    if v_db.is_file():
        try:
            vault = PrivacyVault(v_db)
            all_items = vault.list_items(include_local_only=True)
            for it in all_items:
                is_priv = bool(it.get("local_only")) or str(it.get("resolved_policy")) == "fail_closed" and str(it.get("profile")) == "max_security"
                if remote_egress and (bool(it.get("local_only")) or str(it.get("profile")) == "max_security"):
                    blocked_local_only_count += 1
                    continue
                safe_aliases.append({
                    "uri": f"@private:{it['alias']}",
                    "profile": it.get("profile", "medium"),
                    "tokens_est": it.get("tokens_est", 0),
                    "local_only": bool(it.get("local_only", False)) and not is_priv,
                })
        except Exception:  # noqa: BLE001
            pass

    structured_packet = {
        "branch": branch,
        "dirty_count": dirty_count,
        "dirty_files": clean_dirty[:10],
        "recent_commits": clean_commits[:5],
        "open_issues": open_issues[:6],
        "recent_adrs": adrs[-5:],
        "safe_vault_aliases": safe_aliases[:8],
    }
    comp = compress_structured(json.dumps(structured_packet, ensure_ascii=False), fmt="json")

    return {
        "seed_raw_had_pii": redacted_total > 0,
        "redacted_entities": redacted_total,
        "seed": clean_seed,
        "resume": resume,
        "focus_issue": focus_issue,
        "profile_key": prof_key,
        "raw_target": raw_target,
        "remote_egress": remote_egress,
        "privacy_posture": "fail_closed (remote guard active)" if remote_egress else "local air-gapped",
        "blocked_local_only_count": blocked_local_only_count,
        "git": {
            "branch": branch,
            "dirty_count": dirty_count,
            "dirty_files": clean_dirty,
            "recent_commits": clean_commits,
            "last_commit": last_commit,
        },
        "open_issues": open_issues,
        "adrs": adrs,
        "safe_vault_aliases": safe_aliases,
        "loop_memory": {
            "iteration_count": mem.get("iteration_count", 0),
            "preferred_target": mem.get("preferred_target", "general"),
            "recurring_constraints": mem.get("recurring_constraints", []),
            "rejected_approaches": mem.get("rejected_approaches", []),
            "answered_preferences": mem.get("answered_preferences", {}),
            "last_completed_issue": mem.get("last_completed_issue"),
            "templates": mem.get("templates", []),
        },
        "toon_packet": comp["compressed"],
        "toon_format": comp["format_used"],
        "toon_saving_pct": comp["saving_pct"],
    }


def evaluate_five_trigger_gate(
    context: dict[str, Any],
    *,
    raw_seed: Optional[str] = None,
    confidence_threshold: float = 0.72,
) -> dict[str, Any]:
    """Deterministic 5-Trigger Confidence Gate deciding autonomous execution vs human browser elicitation."""
    probe_text = f"{raw_seed or ''} {context.get('seed') or ''}".strip()
    git_info = context.get("git") or {}
    mem_info = context.get("loop_memory") or {}
    dirty_cnt = int(git_info.get("dirty_count") or 0)
    remote = bool(context.get("remote_egress"))

    # 1. Irreversibility
    irrev_match = _DESTRUCTIVE_RE.search(probe_text)
    irrev_score = 0.85 if irrev_match else 0.05
    irrev_reason = f"Detected irreversible/public keyword '{irrev_match.group(0)}'" if irrev_match else "Reversible local workspace operations"

    # 2. Scope / Scale
    broad_match = _BROAD_SCOPE_RE.search(probe_text)
    if broad_match:
        scope_score = 0.78
        scope_reason = f"Broad cross-repo scope keyword '{broad_match.group(0)}'"
    elif dirty_cnt > 8:
        scope_score = 0.68
        scope_reason = f"High dirty worktree count ({dirty_cnt} modified/untracked files)"
    else:
        scope_score = 0.10
        scope_reason = f"Bounded scope ({dirty_cnt} dirty file(s))"

    # 3. Ambiguity
    meaningful_words = [w for w in re.findall(r"[a-zA-Z0-9_-]{3,}", str(raw_seed if raw_seed is not None else context.get("seed", ""))) if w.lower() not in {"the", "and", "for", "with", "this", "that", "from"}]
    ambig_match = _AMBIGUOUS_RE.search(str(raw_seed if raw_seed is not None else ""))
    if not context.get("resume") and context.get("focus_issue") is None and len(meaningful_words) < 3:
        ambig_score = 0.80
        ambig_reason = f"Seed intent is terse/underspecified ({len(meaningful_words)} meaningful words)"
    elif ambig_match:
        ambig_score = 0.66
        ambig_reason = f"Uncertainty marker '{ambig_match.group(0)}' present in seed"
    else:
        ambig_score = 0.08
        ambig_reason = "Actionable seed objective"

    # 4. Privacy / Compliance
    priv_match = _PRIVACY_SENSITIVE_RE.search(probe_text)
    if remote and (context.get("seed_raw_had_pii") or priv_match):
        priv_score = 0.82
        priv_reason = "Sensitive/private marker or redacted PII detected while targeting a remote-capable profile"
    elif context.get("blocked_local_only_count", 0) > 0 and remote and "@private" in probe_text.lower():
        priv_score = 0.75
        priv_reason = "Vault contains max_security local-only items alongside @private reference"
    else:
        priv_score = 0.05
        priv_reason = f"Privacy boundary verified ({context.get('privacy_posture')})"

    # 5. Novelty
    iter_cnt = int(mem_info.get("iteration_count") or 0)
    known_domain = bool(_KNOWN_DOMAIN_RE.search(probe_text))
    if iter_cnt == 0 and not known_domain and not context.get("focus_issue"):
        nov_score = 0.70
        nov_reason = "Cold-start loop_memory on a domain term outside indexed ADRs/packages"
    else:
        nov_score = 0.10 if iter_cnt > 0 else 0.20
        nov_reason = f"Grounded in loop_memory (iterations={iter_cnt}) & ADR domain"

    triggers = {
        "irreversibility": {"score": irrev_score, "triggered": irrev_score >= 0.65, "reason": irrev_reason},
        "scope_scale": {"score": scope_score, "triggered": scope_score >= 0.65, "reason": scope_reason},
        "ambiguity": {"score": ambig_score, "triggered": ambig_score >= 0.65, "reason": ambig_reason},
        "privacy_compliance": {"score": priv_score, "triggered": priv_score >= 0.65, "reason": priv_reason},
        "novelty": {"score": nov_score, "triggered": nov_score >= 0.65, "reason": nov_reason},
    }
    fired = [k for k, v in triggers.items() if v["triggered"]]
    max_s = max(v["score"] for v in triggers.values())
    extra_penalty = max(0, len(fired) - 1) * 0.10
    confidence = round(max(0.0, min(1.0, 1.0 - max_s - extra_penalty)), 2)
    autonomous_ok = (confidence >= confidence_threshold) and (len(fired) == 0)

    return {
        "confidence_score": confidence,
        "threshold": confidence_threshold,
        "autonomous_allowed": autonomous_ok,
        "triggered_gates": fired,
        "triggers": triggers,
    }


def generate_adaptive_questions(
    context: dict[str, Any],
    *,
    use_local_llm: bool = False,
    config: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    """Generates 2–5 adaptive clarifying questions (Zero-LLM Stdlib default + optional `@role:daily_coder` enrichment)."""
    prefs = (context.get("loop_memory") or {}).get("answered_preferences") or {}
    issues = context.get("open_issues") or []
    dirty_cnt = int((context.get("git") or {}).get("dirty_count") or 0)
    remote = bool(context.get("remote_egress"))
    focus_issue = context.get("focus_issue")

    questions: list[dict[str, Any]] = [
        {
            "id": "execution_strategy",
            "title": "Execution Depth & Verification Cadence",
            "type": "radio",
            "default": prefs.get("execution_strategy") or "targeted_tdd",
            "options": [
                {
                    "value": "targeted_tdd",
                    "label": "(Recommended) Targeted slice + regression tests + single-shot unittest run",
                    "tradeoff": "Balances high velocity with strict stdlib verification while minimizing token burn.",
                },
                {
                    "value": "adr_plan_first",
                    "label": "ADR & GitHub Issue decomposition first before touching implementation code",
                    "tradeoff": "Best for architectural changes spanning multiple subpackages, adds 1 planning step.",
                },
                {
                    "value": "minimal_patch",
                    "label": "Minimal surgical bugfix / refinement on existing symbols only",
                    "tradeoff": "Fastest turnaround and lowest diff risk, skips broader refactoring.",
                },
            ],
        },
        {
            "id": "token_privacy_guardrails",
            "title": "Token-Saving & Privacy Firewall Guardrails",
            "type": "checkbox",
            "default": prefs.get("token_privacy_guardrails") or ["toon_serena", "fail_closed_vault", "local_offload"],
            "options": [
                {
                    "value": "toon_serena",
                    "label": "(Recommended) TOON payload compression + Serena symbol-level navigation",
                    "tradeoff": "Cuts structured JSON & code-reading tokens by 62%–95% with zero fidelity loss.",
                },
                {
                    "value": "fail_closed_vault",
                    "label": "Enforce fail_closed Privacy Vault (@private:<alias>, block max_security remote egress)",
                    "tradeoff": "Guarantees zero raw PII or secret files ever enter cloud context windows.",
                },
                {
                    "value": "local_offload",
                    "label": "Delegate bulk file/diff reads & reviews to @role:fast_coder / @role:reviewer locally",
                    "tradeoff": "Saves cloud tokens ($0 local inference) when a local runner is active.",
                },
            ],
        },
    ]

    if issues or focus_issue is not None:
        top_num = focus_issue if focus_issue is not None else issues[0]["number"]
        top_title = next((i["title"] for i in issues if i["number"] == top_num), "selected GitHub Issue")
        questions.append({
            "id": "issue_anchor",
            "title": "Issue & ADR Traceability Anchor",
            "type": "radio",
            "default": f"issue_{top_num}",
            "options": [
                {
                    "value": f"issue_{top_num}",
                    "label": f"(Recommended) Anchor commits & verification on Issue #{top_num} ({top_title[:58]})",
                    "tradeoff": "Keeps GitHub Issues, ADR index, and commit history synchronized 1:1.",
                },
                {
                    "value": "new_issue",
                    "label": "Open a dedicated atomic GitHub Issue before implementing",
                    "tradeoff": "Cleanest audit trail if this work diverges from currently open issues.",
                },
                {
                    "value": "no_issue_mutation",
                    "label": "Local implementation only (do not modify GitHub Issues yet)",
                    "tradeoff": "Keeps work strictly local until human review.",
                },
            ],
        })

    if dirty_cnt > 0 or remote:
        questions.append({
            "id": "safety_posture",
            "title": "Workspace & Config Mutation Safety",
            "type": "radio",
            "default": prefs.get("safety_posture") or "dry_run_backup",
            "options": [
                {
                    "value": "dry_run_backup",
                    "label": "(Recommended) Preview harness/file mutations with --dry-run & preserve uncommitted work",
                    "tradeoff": "Prevents accidental dotfile or worktree overwrites; provides instant --rollback.",
                },
                {
                    "value": "isolated_tempdir",
                    "label": "Validate strictly inside isolated tempfile sandboxes before workspace edits",
                    "tradeoff": "Maximum isolation for risky parser/hook/server changes.",
                },
                {
                    "value": "commit_and_push",
                    "label": "Commit verified changes & push to origin/main once full test suite is 100% green",
                    "tradeoff": "Completes full CI/GitHub Pages delivery in one autonomous pass.",
                },
            ],
        })

    if use_local_llm and len(questions) < 5:
        try:
            cfg = config or load_cortical_config()
            raw = invoke_configured_runner(
                f"Given task '{context.get('seed')}', suggest ONE concise multiple-choice architectural question as JSON "
                '{"title":"...","options":[{"value":"opt1","label":"(Recommended) ...","tradeoff":"..."},{"value":"opt2","label":"...","tradeoff":"..."}]}',
                system_prompt="Output valid JSON object only, no markdown fences.",
                config=cfg,
                model_override="@role:daily_coder",
                max_tokens=260,
                timeout=8.0,
                role="prompt_studio_elicitor",
            )
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                parsed = json.loads(m.group(0))
                opts = parsed.get("options") or []
                if parsed.get("title") and isinstance(opts, list) and len(opts) >= 2:
                    questions.append({
                        "id": "local_llm_focus",
                        "title": str(parsed["title"])[:100],
                        "type": "radio",
                        "default": str(opts[0].get("value") or "opt1"),
                        "options": [
                            {
                                "value": str(o.get("value") or f"opt{i}"),
                                "label": str(o.get("label") or f"Option {i}"),
                                "tradeoff": str(o.get("tradeoff") or ""),
                            }
                            for i, o in enumerate(opts[:3], 1)
                        ],
                    })
        except Exception:  # noqa: BLE001
            pass

    return questions[:5]


def default_answers_for_questions(questions: list[dict[str, Any]]) -> dict[str, Any]:
    """Extracts the `(Recommended)` default selection map for autonomous or pre-filled runs."""
    out: dict[str, Any] = {}
    for q in questions:
        qid = q["id"]
        if q.get("default") is not None:
            out[qid] = q["default"]
        elif q.get("type") == "checkbox":
            out[qid] = [q["options"][0]["value"]] if q.get("options") else []
        else:
            out[qid] = q["options"][0]["value"] if q.get("options") else ""
    return out


def synthesize_continuation_prompt(
    context: dict[str, Any],
    questions: list[dict[str, Any]],
    *,
    answers: Optional[dict[str, Any]] = None,
    comments: Optional[dict[str, str]] = None,
    directives: str = "",
    target_override: Optional[str] = None,
    config: Optional[dict[str, Any]] = None,
) -> str:
    """Synthesizes a deterministic, high-precision, `fail_closed`-safe continuation prompt."""
    cfg = config or load_cortical_config()
    prof_key, raw_target = normalize_target_profile(target_override or context.get("raw_target"), preferred=context.get("profile_key", "general"))
    prof = TARGET_PROFILES.get(prof_key, TARGET_PROFILES["general"])
    remote_egress = is_remote_target(prof_key, raw_target, cfg)
    custom_terms = list((cfg.get("privacy") or {}).get("custom_terms") or []) or None

    eff_answers = answers if answers is not None else default_answers_for_questions(questions)
    eff_comments = comments or {}

    clean_directives, _ = _sanitize_for_egress(str(directives or "").strip(), remote_egress=remote_egress, custom_terms=custom_terms)
    seed_txt, _ = _sanitize_for_egress(str(context.get("seed") or "").strip(), remote_egress=remote_egress, custom_terms=custom_terms)

    decision_lines: list[str] = []
    for q in questions:
        qid = q["id"]
        sel = eff_answers.get(qid, q.get("default"))
        sel_vals = sel if isinstance(sel, list) else [sel]
        chosen_labels = [
            opt["label"].replace("(Recommended) ", "")
            for opt in (q.get("options") or [])
            if opt.get("value") in sel_vals
        ]
        line = f"- **{q['title']}:** {', '.join(chosen_labels) if chosen_labels else str(sel)}"
        note_raw = str(eff_comments.get(qid) or "").strip()
        if note_raw:
            clean_note, _ = _sanitize_for_egress(note_raw, remote_egress=remote_egress, custom_terms=custom_terms)
            line += f" *(User note: {clean_note})*"
        decision_lines.append(line)

    mem = context.get("loop_memory") or {}
    constraints = list(mem.get("recurring_constraints") or [])
    rejected = list(mem.get("rejected_approaches") or [])

    lines = [
        f"# Role & Execution Target: {prof['role_header']}",
        f"- **Target Harness / Persona:** `{raw_target}` (`{prof['label']}`)",
        f"- **Privacy & Egress Posture:** `{'fail_closed (Zero Raw PII / max_security Blocked)' if remote_egress else '100% Local Air-Gapped'}`",
        "",
        "## 1. Primary Objective",
        seed_txt,
        "",
        "## 2. Elicited Architectural & Execution Decisions",
        *(decision_lines or ["- Execute targeted stdlib-only slice and verify with unittest."]),
    ]

    if clean_directives:
        lines.extend(["", "## 3. Additional User Directives & Hard Constraints", clean_directives])

    if constraints or rejected:
        lines.extend(["", "## 4. Accumulated Loop Memory (Carry-Forward Invariants)"])
        for c in constraints[:6]:
            cc, _ = _sanitize_for_egress(str(c), remote_egress=remote_egress, custom_terms=custom_terms)
            lines.append(f"- **Invariant:** {cc}")
        for r in rejected[:5]:
            rc, _ = _sanitize_for_egress(str(r), remote_egress=remote_egress, custom_terms=custom_terms)
            lines.append(f"- **Avoid (Rejected in Prior Loop):** {rc}")

    lines.extend([
        "",
        f"## 5. Compact Repository, Issue & ADR State (`{context.get('toon_format', 'toon')}`, `{context.get('toon_saving_pct', 0)}%` saved)",
        "```text",
        str(context.get("toon_packet") or "{}"),
        "```",
        "",
        "## 6. Mandatory Acceptance & Verification Gate",
        "- Preserve `dependencies = []` in `pyproject.toml` (Python 3.10+ stdlib only) and zero persistent background daemons.",
        "- Use `@role:*` semantic model abstractions (`@role:daily_coder`, `@role:reviewer`, `@role:deep_reasoner`) instead of hardcoded model tags.",
        "- Run the test suite in one shot via `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q` and ensure 100% pass before completion.",
    ])
    return "\n".join(lines)


def render_elicitor_html(
    context: dict[str, Any],
    questions: list[dict[str, Any]],
    gate: dict[str, Any],
    *,
    token: str,
) -> str:
    """Renders the sleek Zero-CDN dark/light Ephemeral Browser Elicitor UI."""
    payload = {
        "context": context,
        "questions": questions,
        "gate": gate,
        "profiles": TARGET_PROFILES,
        "defaultAnswers": default_answers_for_questions(questions),
        "token": token,
    }
    state_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Cortical Prompt Studio — Ephemeral Browser Elicitor</title>
  <style>
    :root {{
      --bg: #070b14; --bg-elev: #0d1424; --card: #121c30; --card-hover: #182540;
      --border: #233250; --border-strong: #354b76; --text: #e6eef8; --muted: #93a6c2;
      --accent: #38bdf8; --accent-soft: rgba(56,189,248,0.14);
      --ok: #34d399; --ok-soft: rgba(52,211,153,0.14);
      --warn: #fbbf24; --warn-soft: rgba(251,191,36,0.15);
      --violet: #a78bfa; --violet-soft: rgba(167,139,250,0.15);
      --mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Inter, sans-serif;
    }}
    [data-theme="light"] {{
      --bg: #f4f7fb; --bg-elev: #ffffff; --card: #ffffff; --card-hover: #eef4fc;
      --border: #d5e0f0; --border-strong: #9cb3d4; --text: #0f172a; --muted: #475569;
      --accent: #0284c7; --accent-soft: rgba(2,132,199,0.10);
      --ok: #059669; --ok-soft: rgba(5,150,105,0.12);
      --warn: #d97706; --warn-soft: rgba(217,119,6,0.12);
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: var(--bg); color: var(--text); font-family: var(--sans); font-size: 14px; line-height: 1.5; }}
    header {{
      position: sticky; top: 0; z-index: 20; background: var(--bg-elev); border-bottom: 1px solid var(--border);
      padding: 12px 22px; display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap;
    }}
    .brand {{ display: flex; align-items: center; gap: 10px; font-weight: 800; font-size: 15px; }}
    .mark {{ width: 28px; height: 28px; border-radius: 8px; background: linear-gradient(135deg,#38bdf8,#818cf8); color: #070b14; display: grid; place-items: center; font-weight: 900; }}
    .wrap {{ max-width: 1320px; margin: 0 auto; padding: 20px 22px 48px; display: grid; grid-template-columns: 1.15fr 0.85fr; gap: 18px; align-items: start; }}
    @media (max-width: 980px) {{ .wrap {{ grid-template-columns: 1fr; }} }}
    .card {{ background: var(--card); border: 1px solid var(--border); border-radius: 11px; padding: 16px 18px; margin-bottom: 14px; }}
    .pill {{ display: inline-flex; align-items: center; gap: 5px; padding: 3px 9px; border-radius: 999px; font-size: 11.5px; font-weight: 650; border: 1px solid var(--border); background: var(--bg-elev); }}
    .pill.ok {{ color: var(--ok); background: var(--ok-soft); border-color: rgba(52,211,153,0.35); }}
    .pill.info {{ color: var(--accent); background: var(--accent-soft); border-color: rgba(56,189,248,0.35); }}
    .pill.warn {{ color: var(--warn); background: var(--warn-soft); border-color: rgba(251,191,36,0.35); }}
    .pill.violet {{ color: var(--violet); background: var(--violet-soft); border-color: rgba(167,139,250,0.35); }}
    .opt-card {{
      display: flex; gap: 10px; align-items: flex-start; padding: 10px 12px; border-radius: 9px;
      border: 1px solid var(--border); margin-top: 8px; cursor: pointer; transition: 0.12s;
    }}
    .opt-card:hover {{ background: var(--card-hover); border-color: var(--border-strong); }}
    .opt-card.selected {{ background: var(--accent-soft); border-color: var(--accent); }}
    .input, .select, .textarea {{
      width: 100%; padding: 8px 10px; border-radius: 8px; border: 1px solid var(--border-strong);
      background: var(--bg-elev); color: var(--text); font-family: inherit; font-size: 13.5px;
    }}
    .textarea {{ font-family: var(--mono); font-size: 12px; resize: vertical; }}
    .btn {{
      display: inline-flex; align-items: center; gap: 6px; padding: 8px 14px; border-radius: 8px;
      border: 1px solid var(--border-strong); background: var(--card); color: var(--text); cursor: pointer; font-weight: 650; font-size: 13px;
    }}
    .btn:hover {{ background: var(--card-hover); border-color: var(--accent); }}
    .btn.primary {{ background: #0284c7; border-color: #38bdf8; color: #fff; }}
    .hint {{ color: var(--muted); font-size: 12px; }}
    .preview-pane {{ position: sticky; top: 70px; }}
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <span class="mark">C</span>
      <span>Cortical Prompt Studio</span>
      <span class="pill ok">One-Shot Ephemeral Loopback · Zero Persistent Port</span>
    </div>
    <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
      <span class="hint">Shortcuts: <code>1-9</code> quick-select · <code>Cmd/Ctrl+Enter</code> submit</span>
      <button class="btn" type="button" onclick="toggleTheme()">🌗 Theme</button>
    </div>
  </header>

  <main class="wrap" id="app-main"></main>

  <script>
  const DATA = {state_json};
  const ST = {{
    seed: DATA.context.seed || '',
    target: DATA.context.profile_key || 'general',
    answers: JSON.parse(JSON.stringify(DATA.defaultAnswers || {{}})),
    comments: {{}},
    directives: '',
    manualPrompt: null,
    activeQ: 0,
    done: false,
  }};
  const esc = (s) => String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');

  function toggleTheme() {{
    const cur = document.documentElement.getAttribute('data-theme');
    document.documentElement.setAttribute('data-theme', cur === 'light' ? 'dark' : 'light');
  }}

  function buildLivePrompt() {{
    if (ST.manualPrompt !== null) return ST.manualPrompt;
    const prof = DATA.profiles[ST.target] || DATA.profiles.general;
    const isRem = Boolean(prof.remote_egress);
    const decs = DATA.questions.map((q) => {{
      const sel = ST.answers[q.id];
      const vals = Array.isArray(sel) ? sel : [sel];
      const lbls = (q.options || []).filter((o) => vals.includes(o.value)).map((o) => o.label.replace('(Recommended) ', ''));
      const note = (ST.comments[q.id] || '').trim();
      return `- **${{q.title}}:** ${{lbls.join(', ') || sel}}${{note ? ` *(User note: ${{note}})*` : ''}}`;
    }});
    const mem = DATA.context.loop_memory || {{}};
    const invs = (mem.recurring_constraints || []).slice(0, 6).map((c) => `- **Invariant:** ${{c}}`);
    const rejs = (mem.rejected_approaches || []).slice(0, 5).map((r) => `- **Avoid (Rejected in Prior Loop):** ${{r}}`);
    let out = `# Role & Execution Target: ${{prof.role_header}}\\n` +
      `- **Target Harness / Persona:** \\`${{ST.target}}\\` (\\`${{prof.label}}\\`)\\n` +
      `- **Privacy & Egress Posture:** \\`${{isRem ? 'fail_closed (Zero Raw PII / max_security Blocked)' : '100% Local Air-Gapped'}}\\`\\n\\n` +
      `## 1. Primary Objective\\n${{ST.seed.trim()}}\\n\\n` +
      `## 2. Elicited Architectural & Execution Decisions\\n${{decs.join('\\n')}}\\n`;
    if (ST.directives.trim()) out += `\\n## 3. Additional User Directives & Hard Constraints\\n${{ST.directives.trim()}}\\n`;
    if (invs.length || rejs.length) out += `\\n## 4. Accumulated Loop Memory (Carry-Forward Invariants)\\n${{invs.concat(rejs).join('\\n')}}\\n`;
    out += `\\n## 5. Compact Repository, Issue & ADR State (\\`${{DATA.context.toon_format}}\\`, \\`${{DATA.context.toon_saving_pct}}%\\` saved)\\n` +
      '```text\\n' + (DATA.context.toon_packet || '{{}}') + '\\n```\\n\\n' +
      `## 6. Mandatory Acceptance & Verification Gate\\n` +
      `- Preserve \\`dependencies = []\\` in \\`pyproject.toml\\` (Python 3.10+ stdlib only) and zero persistent background daemons.\\n` +
      `- Use \\`@role:*\\` semantic model abstractions (\\`@role:daily_coder\\`, \\`@role:reviewer\\`, \\`@role:deep_reasoner\\`) instead of hardcoded model tags.\\n` +
      `- Run the test suite in one shot via \\`PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q\\` and ensure 100% pass before completion.`;
    return out;
  }}

  function pickOption(qIdx, qid, type, val) {{
    ST.activeQ = qIdx;
    ST.manualPrompt = null;
    if (type === 'checkbox') {{
      const cur = Array.isArray(ST.answers[qid]) ? ST.answers[qid].slice() : [];
      ST.answers[qid] = cur.includes(val) ? cur.filter((x) => x !== val) : cur.concat([val]);
    }} else {{
      ST.answers[qid] = val;
    }}
    render();
  }}

  async function submitAction(kind) {{
    const promptText = buildLivePrompt();
    if (kind === 'template') {{
      const name = window.prompt('Template name:', ST.seed.slice(0, 42) || 'Cortical Prompt Template');
      if (!name) return;
      await fetch('/save-template?token=' + encodeURIComponent(DATA.token), {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ token: DATA.token, name, target: ST.target, prompt: promptText }}),
      }});
      alert('Saved reusable template: ' + name);
      return;
    }}
    const url = (kind === 'cancel' ? '/cancel' : '/submit') + '?token=' + encodeURIComponent(DATA.token);
    const res = await fetch(url, {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{
        token: DATA.token,
        seed: ST.seed,
        target: ST.target,
        answers: ST.answers,
        comments: ST.comments,
        directives: ST.directives,
        prompt: promptText,
      }}),
    }});
    if (res.ok) {{
      ST.done = true;
      document.getElementById('app-main').innerHTML = `
        <div class="card" style="grid-column:1/-1;text-align:center;padding:36px;">
          <span class="pill ok">✓ Ephemeral Port Closed Cleanly</span>
          <h2 style="margin:12px 0 6px;">${{kind === 'cancel' ? 'Session Cancelled' : 'Continuation Prompt Returned to Agent'}}</h2>
          <p class="hint">The one-shot loopback socket has shut down (0 open ports). You may close this browser tab.</p>
        </div>`;
    }}
  }}

  function copyPrompt() {{
    navigator.clipboard?.writeText(buildLivePrompt());
  }}

  function render() {{
    if (ST.done) return;
    const c = DATA.context;
    const g = DATA.gate;
    const issuesHtml = (c.open_issues || []).slice(0, 4).map((i) => `<span class="pill info">#${{i.number}} ${{esc(i.title.slice(0,36))}}</span>`).join(' ') || '<span class="hint">No open gh issues fetched</span>';
    const qCards = DATA.questions.map((q, qi) => {{
      const sel = ST.answers[q.id];
      const vals = Array.isArray(sel) ? sel : [sel];
      return `
        <div class="card" onclick="ST.activeQ=${{qi}}">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;">
            <strong>Q${{qi + 1}}. ${{esc(q.title)}}</strong>
            <span class="pill ${{q.type==='checkbox'?'violet':'info'}}">${{q.type === 'checkbox' ? 'Multi-select' : 'Single choice'}}</span>
          </div>
          ${{(q.options || []).map((o, oi) => {{
            const checked = vals.includes(o.value);
            return `
              <div class="opt-card ${{checked ? 'selected' : ''}}" onclick="event.stopPropagation();pickOption(${{qi}}, '${{esc(q.id)}}', '${{q.type}}', '${{esc(o.value)}}')">
                <input type="${{q.type}}" ${{checked ? 'checked' : ''}} tabindex="-1" style="margin-top:3px;pointer-events:none;" />
                <div>
                  <div><strong>[${{oi + 1}}]</strong> ${{esc(o.label)}}</div>
                  <div class="hint">${{esc(o.tradeoff || '')}}</div>
                </div>
              </div>`;
          }}).join('')}}
          <div style="margin-top:10px;">
            <input class="input" placeholder="Comment / custom note for Q${{qi + 1}} (optional)..." value="${{esc(ST.comments[q.id] || '')}}" oninput="ST.manualPrompt=null;ST.comments['${{esc(q.id)}}']=this.value;document.getElementById('live-preview').value=buildLivePrompt()" />
          </div>
        </div>`;
    }}).join('');

    document.getElementById('app-main').innerHTML = `
      <div>
        <div class="card">
          <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px;">
            <span class="pill ok">🌿 Branch: ${{esc(c.git?.branch || 'main')}} (${{c.git?.dirty_count || 0}} dirty)</span>
            <span class="pill ${{c.remote_egress ? 'warn' : 'ok'}}">🛡️ ${{esc(c.privacy_posture)}}</span>
            <span class="pill violet">🎯 Confidence: ${{g.confidence_score}} (Iter #${{(c.loop_memory?.iteration_count || 0) + 1}})</span>
          </div>
          <div style="margin-bottom:10px;display:flex;gap:6px;flex-wrap:wrap;">${{issuesHtml}}</div>
          <div style="display:grid;grid-template-columns:1.3fr 0.7fr;gap:10px;">
            <div>
              <label class="hint"><strong>Seed Intent / Objective</strong></label>
              <input class="input" value="${{esc(ST.seed)}}" oninput="ST.manualPrompt=null;ST.seed=this.value;document.getElementById('live-preview').value=buildLivePrompt()" />
            </div>
            <div>
              <label class="hint"><strong>Target Execution Profile</strong></label>
              <select class="select" onchange="ST.manualPrompt=null;ST.target=this.value;render()">
                ${{Object.values(DATA.profiles).map((p) => `<option value="${{esc(p.id)}}" ${{ST.target===p.id?'selected':''}}>${{esc(p.label)}}</option>`).join('')}}
              </select>
            </div>
          </div>
        </div>
        ${{qCards}}
        <div class="card">
          <label><strong>Additional Directives / Global Constraints</strong></label>
          <textarea class="textarea" rows="3" style="margin-top:6px;" placeholder="Add specific file paths, acceptance rules, or 'Avoid ...' notes (persisted to loop_memory.json)..." oninput="ST.manualPrompt=null;ST.directives=this.value;document.getElementById('live-preview').value=buildLivePrompt()">${{esc(ST.directives)}}</textarea>
        </div>
      </div>

      <div class="preview-pane">
        <div class="card">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;gap:8px;flex-wrap:wrap;">
            <strong>⚡ Live Synthesized Continuation Prompt</strong>
            <span class="pill ok">TOON -${{c.toon_saving_pct}}%</span>
          </div>
          <textarea id="live-preview" class="textarea" rows="22" oninput="ST.manualPrompt=this.value">${{esc(buildLivePrompt())}}</textarea>
          <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:12px;">
            <button class="btn primary" type="button" onclick="submitAction('submit')">✓ Approve &amp; Return to Agent</button>
            <button class="btn" type="button" onclick="copyPrompt()">📋 Copy to Clipboard</button>
            <button class="btn" type="button" onclick="submitAction('template')">💾 Save as Reusable Template</button>
            <button class="btn" type="button" onclick="submitAction('cancel')">✕ Cancel</button>
          </div>
        </div>
      </div>`;
  }}

  document.addEventListener('keydown', (e) => {{
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {{ e.preventDefault(); submitAction('submit'); return; }}
    const tag = (e.target?.tagName || '').toLowerCase();
    if (['input', 'textarea', 'select'].includes(tag)) return;
    const num = Number(e.key);
    if (num >= 1 && num <= 9) {{
      const q = DATA.questions[ST.activeQ || 0];
      const opt = q?.options?.[num - 1];
      if (q && opt) pickOption(ST.activeQ || 0, q.id, q.type, opt.value);
    }}
  }});

  render();
  </script>
</body>
</html>"""


def open_browser_url(url: str, preferred_browser: str = "default") -> bool:
    """Opens `url` in Chrome (when requested and available) or the default system browser."""
    pref = str(preferred_browser or "default").strip().lower()
    if pref == "chrome":
        if sys.platform == "darwin" and Path("/Applications/Google Chrome.app").exists():
            res = subprocess.run(["open", "-a", "Google Chrome", url], capture_output=True, check=False)
            if res.returncode == 0:
                return True
        for cand in ("google-chrome", "chromium", "chrome"):
            if shutil.which(cand):
                subprocess.Popen([cand, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
    try:
        return bool(webbrowser.open(url))
    except Exception:  # noqa: BLE001
        return False


def create_ephemeral_elicitor_server(
    context: dict[str, Any],
    questions: list[dict[str, Any]],
    gate: dict[str, Any],
    *,
    loop_store: Optional[LoopMemoryStore] = None,
    token: Optional[str] = None,
) -> tuple[http.server.HTTPServer, str, dict[str, Any], threading.Event]:
    """Creates a bound `127.0.0.1:0` HTTPServer with single-use token auth and strict `Host` validation."""
    secret_tok = token or secrets.token_urlsafe(32)
    done_event = threading.Event()
    state_box: dict[str, Any] = {"submitted": False, "cancelled": False, "payload": None}

    class _EphemeralHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return

        def _send_bytes(self, status: int, body: bytes, content_type: str = "application/json; charset=utf-8") -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()
            self.wfile.write(body)

        def _check_host_and_origin(self, *, is_post: bool = False) -> bool:
            port = self.server.server_address[1]
            allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
            host_hdr = str(self.headers.get("Host") or "").strip().lower()
            if host_hdr not in allowed_hosts:
                self._send_bytes(
                    421,
                    json.dumps({"ok": False, "error": "DNS rebinding guard: invalid Host header"}).encode("utf-8"),
                )
                return False
            if is_post:
                origin = str(self.headers.get("Origin") or "").strip().lower()
                if origin and origin not in {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}:
                    self._send_bytes(
                        403,
                        json.dumps({"ok": False, "error": "Cross-origin POST rejected"}).encode("utf-8"),
                    )
                    return False
            return True

        def _extract_query_token(self) -> str:
            parsed = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(parsed.query)
            return str((qs.get("token") or [""])[0])

        def do_GET(self) -> None:
            if not self._check_host_and_origin(is_post=False):
                return
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != "/elicit":
                self._send_bytes(404, json.dumps({"error": "Not found"}).encode("utf-8"))
                return
            q_tok = self._extract_query_token()
            if not q_tok or not secrets.compare_digest(q_tok, secret_tok):
                self._send_bytes(403, json.dumps({"ok": False, "error": "Invalid or missing session token"}).encode("utf-8"))
                return
            html = render_elicitor_html(context, questions, gate, token=secret_tok).encode("utf-8")
            self._send_bytes(200, html, content_type="text/html; charset=utf-8")

        def do_POST(self) -> None:
            if not self._check_host_and_origin(is_post=True):
                return
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path not in {"/submit", "/cancel", "/save-template"}:
                self._send_bytes(404, json.dumps({"error": "Not found"}).encode("utf-8"))
                return
            try:
                length = min(262144, int(self.headers.get("Content-Length") or 0))
                raw = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
                body = json.loads(raw) if raw.strip() else {}
            except Exception:  # noqa: BLE001
                self._send_bytes(400, json.dumps({"ok": False, "error": "Malformed JSON"}).encode("utf-8"))
                return

            cand_tok = str(body.get("token") or self._extract_query_token() or "")
            if not cand_tok or not secrets.compare_digest(cand_tok, secret_tok):
                self._send_bytes(403, json.dumps({"ok": False, "error": "Invalid or missing session token"}).encode("utf-8"))
                return

            if parsed.path == "/save-template":
                if loop_store is not None:
                    tpl = loop_store.save_template(
                        str(body.get("name") or "Template"),
                        str(body.get("target") or context.get("profile_key") or "general"),
                        str(body.get("prompt") or ""),
                    )
                else:
                    tpl = {"name": str(body.get("name") or "Template")}
                self._send_bytes(200, json.dumps({"ok": True, "template": tpl}).encode("utf-8"))
                return

            if parsed.path == "/cancel":
                state_box["cancelled"] = True
                self._send_bytes(200, json.dumps({"ok": True, "cancelled": True}).encode("utf-8"))
                done_event.set()
                return

            state_box["submitted"] = True
            state_box["payload"] = body
            self._send_bytes(200, json.dumps({"ok": True, "submitted": True}).encode("utf-8"))
            done_event.set()

    httpd = http.server.HTTPServer(("127.0.0.1", 0), _EphemeralHandler)
    httpd.timeout = 0.15
    return httpd, secret_tok, state_box, done_event


def run_ephemeral_browser_elicitor(
    context: dict[str, Any],
    questions: list[dict[str, Any]],
    gate: dict[str, Any],
    *,
    loop_store: Optional[LoopMemoryStore] = None,
    timeout_sec: float = 240.0,
    preferred_browser: str = "default",
    open_browser: bool = True,
    on_ready: Optional[Callable[[str, int, str], None]] = None,
) -> dict[str, Any]:
    """Spins up one-shot `127.0.0.1:0` elicitor, waits for submit/cancel/timeout, and guarantees socket closure."""
    httpd, tok, state_box, done_event = create_ephemeral_elicitor_server(
        context, questions, gate, loop_store=loop_store
    )
    port = int(httpd.server_address[1])
    url = f"http://127.0.0.1:{port}/elicit?token={tok}"
    try:
        if on_ready is not None:
            on_ready(url, port, tok)
        if open_browser:
            open_browser_url(url, preferred_browser=preferred_browser)
        deadline = time.monotonic() + max(0.2, float(timeout_sec))
        while not done_event.is_set() and time.monotonic() < deadline:
            httpd.handle_request()
    finally:
        try:
            httpd.server_close()
        except Exception:  # noqa: BLE001
            pass

    timed_out = not state_box["submitted"] and not state_box["cancelled"]
    return {
        "url_used": url,
        "port_closed": True,
        "submitted": bool(state_box["submitted"]),
        "cancelled": bool(state_box["cancelled"]),
        "timed_out": timed_out,
        "payload": state_box["payload"],
    }


def _has_desktop_display() -> bool:
    if os.environ.get("SSH_CONNECTION") and not os.environ.get("DISPLAY") and sys.platform != "darwin":
        return False
    if sys.platform in {"darwin", "win32"}:
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def run_tui_elicitor(context: dict[str, Any], questions: list[dict[str, Any]]) -> dict[str, Any]:
    """Headless/SSH fallback elicitor: interactive TTY prompts when attached, else recommended defaults."""
    answers = default_answers_for_questions(questions)
    comments: dict[str, str] = {}
    directives = ""
    if not sys.stdin.isatty():
        return {"answers": answers, "comments": comments, "directives": directives, "interactive_tty": False}

    print(f"\n=== Cortical Prompt Studio (Headless TUI) · Branch={context['git']['branch']} ===", file=sys.stderr)
    print(f"Objective: {context['seed']}\n", file=sys.stderr)
    for idx, q in enumerate(questions, 1):
        print(f"Q{idx}. {q['title']}", file=sys.stderr)
        for oi, opt in enumerate(q.get("options") or [], 1):
            print(f"  [{oi}] {opt['label']} — {opt.get('tradeoff', '')}", file=sys.stderr)
        raw = input("Choice number(s) (Enter for Recommended): ").strip()
        if raw:
            nums = [int(x) for x in re.findall(r"\d+", raw) if 1 <= int(x) <= len(q["options"])]
            if nums:
                if q["type"] == "checkbox":
                    answers[q["id"]] = [q["options"][n - 1]["value"] for n in nums]
                else:
                    answers[q["id"]] = q["options"][nums[0] - 1]["value"]
        note = input("Optional comment (Enter to skip): ").strip()
        if note:
            comments[q["id"]] = note
    directives = input("Global directives / constraints (Enter to skip): ").strip()
    return {"answers": answers, "comments": comments, "directives": directives, "interactive_tty": True}


def run_next_prompt_flow(
    seed: str = "",
    *,
    mode: str = "browser",
    preferred_browser: str = "default",
    target: Optional[str] = None,
    focus_issue: Optional[int] = None,
    resume: bool = False,
    timeout_sec: float = 240.0,
    confidence_threshold: float = 0.72,
    use_local_llm: bool = False,
    allow_gh: bool = True,
    open_browser: bool = True,
    repo_root: Optional[Path] = None,
    vault_db: Optional[Path] = None,
    data_dir: Optional[Path] = None,
    config: Optional[dict[str, Any]] = None,
    on_browser_ready: Optional[Callable[[str, int, str], None]] = None,
) -> dict[str, Any]:
    """End-to-end orchestrator for `cortical next` across `browser`, `tui`, and `auto` (`auto_if_confident`) modes."""
    cfg = config or load_cortical_config()
    root = Path(repo_root or Path.cwd()).expanduser().resolve()
    store = LoopMemoryStore(repo_root=root, data_dir=data_dir)

    raw_seed = str(seed or "")
    ctx = harvest_prompt_context(
        raw_seed,
        repo_root=root,
        vault_db=vault_db,
        loop_store=store,
        target=target,
        focus_issue=focus_issue,
        resume=resume,
        allow_gh=allow_gh,
        config=cfg,
    )
    gate = evaluate_five_trigger_gate(ctx, raw_seed=raw_seed, confidence_threshold=confidence_threshold)
    questions = generate_adaptive_questions(ctx, use_local_llm=use_local_llm, config=cfg)

    req_mode = str(mode or "browser").strip().lower()
    if req_mode == "auto_if_confident":
        req_mode = "auto"

    answers = default_answers_for_questions(questions)
    comments: dict[str, str] = {}
    directives = ""
    chosen_target = ctx["raw_target"]
    final_seed = ctx["seed"]
    manual_prompt_override: Optional[str] = None
    mode_used = req_mode
    escalated = False
    browser_meta: Optional[dict[str, Any]] = None

    if req_mode == "auto":
        if gate["autonomous_allowed"]:
            mode_used = "auto_synthesized"
        else:
            escalated = True
            if open_browser and _has_desktop_display():
                mode_used = "auto_escalated_browser"
                req_mode = "browser"
            else:
                mode_used = "auto_escalation_required_headless"

    if req_mode == "browser":
        if open_browser and not _has_desktop_display():
            tui_res = run_tui_elicitor(ctx, questions)
            answers = tui_res["answers"]
            comments = tui_res["comments"]
            directives = tui_res["directives"]
            mode_used = "tui_headless_fallback"
        else:
            b_res = run_ephemeral_browser_elicitor(
                ctx,
                questions,
                gate,
                loop_store=store,
                timeout_sec=timeout_sec,
                preferred_browser=preferred_browser,
                open_browser=open_browser,
                on_ready=on_browser_ready,
            )
            browser_meta = {k: v for k, v in b_res.items() if k != "payload"}
            if b_res["submitted"] and isinstance(b_res.get("payload"), dict):
                pl = b_res["payload"]
                final_seed = str(pl.get("seed") or final_seed)
                chosen_target = str(pl.get("target") or chosen_target)
                if isinstance(pl.get("answers"), dict):
                    answers.update(pl["answers"])
                if isinstance(pl.get("comments"), dict):
                    comments = {str(k): str(v) for k, v in pl["comments"].items() if str(v).strip()}
                directives = str(pl.get("directives") or "")
                # Re-verify privacy firewall even if user edited live prompt manually in browser
                if pl.get("prompt"):
                    p_key, r_tgt = normalize_target_profile(chosen_target)
                    rem = is_remote_target(p_key, r_tgt, cfg)
                    c_terms = list((cfg.get("privacy") or {}).get("custom_terms") or []) or None
                    manual_clean, _ = _sanitize_for_egress(str(pl["prompt"]), remote_egress=rem, custom_terms=c_terms)
                    manual_prompt_override = manual_clean
                mode_used = "browser_submitted" if not escalated else "auto_escalated_browser_submitted"
            elif b_res["cancelled"]:
                mode_used = "browser_cancelled"
            else:
                mode_used = "browser_timeout_defaults"
    elif req_mode == "tui":
        tui_res = run_tui_elicitor(ctx, questions)
        answers = tui_res["answers"]
        comments = tui_res["comments"]
        directives = tui_res["directives"]
        mode_used = "tui"

    ctx["seed"] = final_seed
    synthesized = manual_prompt_override or synthesize_continuation_prompt(
        ctx,
        questions,
        answers=answers,
        comments=comments,
        directives=directives,
        target_override=chosen_target,
        config=cfg,
    )

    outcome = store.record_outcome(
        seed=final_seed,
        target=chosen_target,
        answers=answers,
        comments=comments,
        directives=directives,
        confidence_score=gate["confidence_score"],
        mode_used=mode_used,
        synthesized_prompt=synthesized,
        issue=focus_issue,
        last_commit=ctx["git"].get("last_commit", ""),
    )

    return {
        "ok": mode_used != "browser_cancelled",
        "mode_requested": mode,
        "mode_used": mode_used,
        "escalated": escalated,
        "target": chosen_target,
        "seed": final_seed,
        "confidence_gate": gate,
        "questions": questions,
        "answers": answers,
        "comments": comments,
        "directives": directives,
        "prompt": synthesized,
        "prompt_audit_path": outcome["prompt_path"],
        "loop_memory_path": outcome["memory_path"],
        "iteration_count": outcome["iteration_count"],
        "privacy_posture": ctx["privacy_posture"],
        "toon_saving_pct": ctx["toon_saving_pct"],
        "browser": browser_meta,
    }
