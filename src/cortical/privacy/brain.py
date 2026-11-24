"""3+1 Progressive Synthesis & Factorized Local Brain (Concepts, Tasks, Files, Skills) inside SQLite WAL."""

from __future__ import annotations

import json
import re
import sqlite3
import time
from typing import Any, Callable, Optional

_STOPWORDS = frozenset({
    "the", "and", "for", "with", "that", "this", "from", "into", "your", "are", "was", "have",
    "has", "not", "but", "can", "will", "all", "any", "use", "using", "used", "when", "where",
    "del", "della", "dei", "delle", "degli", "con", "per", "una", "uno", "che", "non", "sono",
    "come", "anche", "solo", "nella", "nelle", "nel", "sul", "sulla", "tra", "fra", "file", "files",
})


def _extract_keywords(text: str, limit: int = 12) -> list[str]:
    counts: dict[str, int] = {}
    for tok in re.findall(r"[a-zA-Z0-9_-]{3,28}", text.lower()):
        if tok in _STOPWORDS or tok.isdigit():
            continue
        if tok.startswith(("email_", "iban_", "phone_", "tax_id_", "secret_", "custom_", "person_name_")):
            continue
        counts[tok] = counts.get(tok, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [k for k, _ in ranked[:limit]]


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _slugify(title: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", title.strip().lower()).strip("-")
    return s[:48] or "general-knowledge"


def build_3plus1_tiers(alias: str, text: str, *, is_public: bool) -> dict[str, Any]:
    """Builds 3 progressive synthesis tiers (light/medium/high) + max policy flag."""
    lines = [ln.strip() for ln in str(text or "").splitlines() if ln.strip()]
    kws = _extract_keywords(text, limit=8)
    head = lines[0][:140] if lines else alias
    privacy_tag = "PUBLIC RAW" if is_public else "SANITIZED"

    light = f"[L1 LIGHT · @private:{alias} · {privacy_tag}] {head} | topics: {', '.join(kws[:5]) or alias}"
    med_lines = lines[:8]
    medium = (
        f"[L2 MEDIUM · @private:{alias} · {privacy_tag}]\n"
        f"Topics: {', '.join(kws) or alias}\n"
        + "\n".join(f"- {ln[:160]}" for ln in med_lines)
    )
    high_body = "\n".join(lines[:32])[:3600]
    high = f"[L3 HIGH · @private:{alias} · {privacy_tag}]\nTopics: {', '.join(kws) or alias}\n\n{high_body}"
    return {
        "alias": alias,
        "tier_light": light[:320],
        "tier_medium": medium[:1400],
        "tier_high": high[:4200],
        "max_is_raw": 1 if is_public else 0,
    }


class LocalBrain:
    """Factorizes distilled concepts, tasks, and procedural skills across ingested Vault files."""

    def __init__(self, connect_fn: Callable[[], sqlite3.Connection]) -> None:
        self._connect = connect_fn
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS brain_tiers (
                    alias TEXT PRIMARY KEY,
                    tier_light TEXT NOT NULL,
                    tier_medium TEXT NOT NULL,
                    tier_high TEXT NOT NULL,
                    max_is_raw INTEGER NOT NULL DEFAULT 0,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS brain_concepts (
                    slug TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    keywords_json TEXT NOT NULL,
                    sources_json TEXT NOT NULL,
                    tasks_json TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS brain_skills (
                    slug TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    procedure_md TEXT NOT NULL,
                    keywords_json TEXT NOT NULL,
                    sources_json TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );
                """
            )

    def _distill_candidates(
        self,
        alias: str,
        text: str,
        *,
        use_local_llm: bool = False,
        llm_fn: Optional[Callable[[str], str]] = None,
        model: Optional[str] = None,
        config: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        kws = _extract_keywords(text, limit=10)
        lines = [ln.strip() for ln in str(text or "").splitlines() if ln.strip()]
        heading = next((ln.lstrip("# ").strip() for ln in lines if ln.startswith("#") or len(ln) < 70), alias.replace("_", " ").title())
        proc_lines = [ln for ln in lines if re.match(r"^(?:\d+[.)]|[-*]|```|\$|pip |python|ollama|git )", ln)]

        if use_local_llm:
            prompt = (
                "Distill this sanitized document into strict JSON: "
                '{"concept_title":"Short Topic","summary":"1-2 sentences","keywords":["k1","k2"],'
                '"skill_title":"Optional Action Skill or empty","procedure":"concise steps if procedural else empty"}.\n\n'
                f"TEXT:\n{text[:2400]}"
            )
            try:
                if llm_fn is not None:
                    raw = llm_fn(prompt)
                else:
                    from ..config import invoke_configured_runner
                    from ..roles import normalize_role_or_model

                    raw = invoke_configured_runner(
                        prompt,
                        system_prompt="Return compact valid JSON only.",
                        config=config,
                        model_override=normalize_role_or_model(model, config, default_role="summarizer"),
                        max_tokens=260,
                        timeout=12.0,
                        role="brain_distill",
                    )
                m = re.search(r"\{.*\}", str(raw or ""), flags=re.S)
                if m:
                    parsed = json.loads(m.group(0))
                    if isinstance(parsed, dict) and parsed.get("concept_title"):
                        return {
                            "concept_title": str(parsed["concept_title"])[:80],
                            "summary": str(parsed.get("summary") or "")[:400] or (" ".join(lines[:3])[:300]),
                            "keywords": [str(k).lower() for k in (parsed.get("keywords") or kws)[:10]],
                            "skill_title": str(parsed.get("skill_title") or "")[:80],
                            "procedure": str(parsed.get("procedure") or "")[:600],
                        }
            except Exception:  # noqa: BLE001
                pass

        return {
            "concept_title": heading[:60] if heading else alias,
            "summary": " ".join(lines[:3])[:300] or f"Distilled knowledge from @private:{alias}.",
            "keywords": kws or [_slugify(alias)],
            "skill_title": f"Workflow: {heading[:48]}" if len(proc_lines) >= 2 else "",
            "procedure": "\n".join(proc_lines[:8])[:600] if len(proc_lines) >= 2 else "",
        }

    def distill_and_factorize(
        self,
        alias: str,
        text: str,
        *,
        is_public: bool,
        task_tag: str = "vault_ingest",
        jaccard_threshold: float = 0.35,
        use_local_llm: bool = False,
        llm_fn: Optional[Callable[[str], str]] = None,
        model: Optional[str] = None,
        config: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Stores 3+1 tiers and factorizes extracted concepts/skills against existing knowledge."""
        now = time.time()
        tiers = build_3plus1_tiers(alias, text, is_public=is_public)
        cand = self._distill_candidates(alias, text, use_local_llm=use_local_llm, llm_fn=llm_fn, model=model, config=config)
        cand_kws = set(cand["keywords"])

        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO brain_tiers(alias, tier_light, tier_medium, tier_high, max_is_raw, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (alias, tiers["tier_light"], tiers["tier_medium"], tiers["tier_high"], tiers["max_is_raw"], now),
            )

            # Factorize concept against existing concepts (merge when Jaccard >= threshold)
            best_slug, best_row, best_sim = None, None, 0.0
            for row in conn.execute("SELECT * FROM brain_concepts").fetchall():
                existing_kws = set(json.loads(row["keywords_json"] or "[]"))
                sim = _jaccard(cand_kws, existing_kws)
                if sim >= jaccard_threshold and sim > best_sim:
                    best_slug, best_row, best_sim = row["slug"], row, sim

            if best_row is not None:
                merged_kws = sorted(set(json.loads(best_row["keywords_json"])) | cand_kws)[:16]
                merged_srcs = sorted(set(json.loads(best_row["sources_json"])) | {alias})
                merged_tasks = sorted(set(json.loads(best_row["tasks_json"])) | {task_tag})
                merged_sum = best_row["summary"]
                if cand["summary"] and cand["summary"][:40] not in merged_sum:
                    merged_sum = f"{merged_sum} | {cand['summary']}"[:600]
                concept_slug = best_slug
                conn.execute(
                    """UPDATE brain_concepts SET summary = ?, keywords_json = ?, sources_json = ?, tasks_json = ?, updated_at = ?
                       WHERE slug = ?""",
                    (merged_sum, json.dumps(merged_kws), json.dumps(merged_srcs), json.dumps(merged_tasks), now, concept_slug),
                )
                concept_merged = True
            else:
                concept_slug = _slugify(cand["concept_title"])
                existing_same = conn.execute("SELECT * FROM brain_concepts WHERE slug = ?", (concept_slug,)).fetchone()
                srcs = sorted(set(json.loads(existing_same["sources_json"])) | {alias}) if existing_same else [alias]
                tasks = sorted(set(json.loads(existing_same["tasks_json"])) | {task_tag}) if existing_same else [task_tag]
                conn.execute(
                    """INSERT OR REPLACE INTO brain_concepts(slug, title, summary, keywords_json, sources_json, tasks_json, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (concept_slug, cand["concept_title"], cand["summary"], json.dumps(sorted(cand_kws)), json.dumps(srcs), json.dumps(tasks), now),
                )
                concept_merged = existing_same is not None

            skill_slug = ""
            skill_merged = False
            if cand["skill_title"] and cand["procedure"]:
                s_best_slug, s_best_row, s_best_sim = None, None, 0.0
                for row in conn.execute("SELECT * FROM brain_skills").fetchall():
                    sim = _jaccard(cand_kws, set(json.loads(row["keywords_json"] or "[]")))
                    if sim >= jaccard_threshold and sim > s_best_sim:
                        s_best_slug, s_best_row, s_best_sim = row["slug"], row, sim
                if s_best_row is not None:
                    skill_slug = str(s_best_slug)
                    skill_merged = True
                    m_kws = sorted(set(json.loads(s_best_row["keywords_json"])) | cand_kws)[:16]
                    m_srcs = sorted(set(json.loads(s_best_row["sources_json"])) | {alias})
                    proc = s_best_row["procedure_md"]
                    if cand["procedure"][:40] not in proc:
                        proc = f"{proc}\n\n# + {alias}\n{cand['procedure']}"[:1200]
                    conn.execute(
                        "UPDATE brain_skills SET procedure_md = ?, keywords_json = ?, sources_json = ?, updated_at = ? WHERE slug = ?",
                        (proc, json.dumps(m_kws), json.dumps(m_srcs), now, skill_slug),
                    )
                else:
                    skill_slug = _slugify(cand["skill_title"])
                    conn.execute(
                        """INSERT OR REPLACE INTO brain_skills(slug, title, procedure_md, keywords_json, sources_json, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (skill_slug, cand["skill_title"], cand["procedure"], json.dumps(sorted(cand_kws)), json.dumps([alias]), now),
                    )

        return {
            "alias": alias,
            "concept_slug": concept_slug,
            "concept_merged": concept_merged,
            "skill_slug": skill_slug,
            "skill_merged": skill_merged,
            "tiers": tiers,
        }

    def read_tier(self, alias: str, tier: str = "max") -> Optional[str]:
        t = str(tier or "max").lower().strip()
        if t in {"max", "l4"}:
            return None
        col = {"light": "tier_light", "l1": "tier_light", "medium": "tier_medium", "l2": "tier_medium", "high": "tier_high", "l3": "tier_high"}.get(t)
        if not col:
            return None
        with self._connect() as conn:
            row = conn.execute(f"SELECT {col} FROM brain_tiers WHERE alias = ?", (alias,)).fetchone()
        return str(row[0]) if row else None

    def delete_alias(self, alias: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM brain_tiers WHERE alias = ?", (alias,))

    def get_snapshot(self, include_local_only: bool = True) -> dict[str, Any]:
        """Returns multi-aspect Brain index (by concept, by task, by file, by skill) + 3+1 tiers."""
        with self._connect() as conn:
            v_rows = conn.execute("SELECT alias, source_name, profile, local_only, tokens_est FROM vault_items ORDER BY updated_at DESC").fetchall()
            allowed = {r["alias"] for r in v_rows if include_local_only or not r["local_only"]}
            tiers_map = {r["alias"]: dict(r) for r in conn.execute("SELECT * FROM brain_tiers").fetchall() if r["alias"] in allowed}
            concepts = [
                {
                    "slug": r["slug"],
                    "title": r["title"],
                    "summary": r["summary"],
                    "keywords": json.loads(r["keywords_json"]),
                    "sources": [s for s in json.loads(r["sources_json"]) if s in allowed],
                    "tasks": json.loads(r["tasks_json"]),
                }
                for r in conn.execute("SELECT * FROM brain_concepts ORDER BY updated_at DESC").fetchall()
            ]
            concepts = [c for c in concepts if c["sources"] or include_local_only]
            skills = [
                {
                    "slug": r["slug"],
                    "title": r["title"],
                    "procedure_md": r["procedure_md"],
                    "keywords": json.loads(r["keywords_json"]),
                    "sources": [s for s in json.loads(r["sources_json"]) if s in allowed],
                }
                for r in conn.execute("SELECT * FROM brain_skills ORDER BY updated_at DESC").fetchall()
            ]
            skills = [sk for sk in skills if sk["sources"] or include_local_only]

        by_file = [
            {
                "alias": r["alias"],
                "source_name": r["source_name"],
                "profile": r["profile"],
                "local_only": bool(r["local_only"]),
                "tokens_est": int(r["tokens_est"]),
                "tiers": tiers_map.get(r["alias"], {}),
            }
            for r in v_rows
            if r["alias"] in allowed
        ]
        by_task: dict[str, list[dict[str, Any]]] = {}
        for c in concepts:
            for tk in c["tasks"]:
                by_task.setdefault(tk, []).append({"slug": c["slug"], "title": c["title"], "sources": c["sources"]})

        return {
            "stats": {
                "files": len(by_file),
                "concepts": len(concepts),
                "skills": len(skills),
                "tasks": len(by_task),
            },
            "by_concept": concepts,
            "by_task": [{"task": k, "concepts": v} for k, v in sorted(by_task.items())],
            "by_file": by_file,
            "by_skill": skills,
        }
