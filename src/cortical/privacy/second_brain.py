"""Unified Anonymized Second Brain: Bulk Disk Privatizer, Knowledge Reconciliation, Auto-Skills & Smart Escalation (ADR-018)."""

from __future__ import annotations

import json
import re
import socket
import urllib.parse
from pathlib import Path
from typing import Any, Callable, Optional

from ..compression.engine import compress_structured
from ..config import (
    DEFAULT_VAULT_DB,
    default_data_dir,
    invoke_configured_runner,
    load_cortical_config,
    resolve_active_runner_endpoint,
)
from ..roles import resolve_role_model
from ..wiki.store import KnowledgeStore
from .brain import _extract_keywords, _jaccard, _slugify
from .sanitizer import FailClosedError, classify_and_sanitize
from .vault import PrivacyVault, _verify_zero_residual_pii

DETAIL_TIERS: tuple[str, ...] = ("light", "medium", "high", "max_security")

_AMOUNT_DATE_RE = re.compile(
    r"(?:(?:€|\$|£|EUR|USD)\s*\d[\d.,]*|\d[\d.,]*\s*(?:€|\$|%|percent|EUR|USD|k|M|GB|GiB)|\b20\d{2}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}/20\d{2}\b)",
    re.IGNORECASE,
)
_PARAM_B_RE = re.compile(r"(?:^|[:\-_/])(\d+(?:\.\d+)?)\s*[bB](?:$|[:\-_/])")
_COMPLEX_TASK_RE = re.compile(
    r"\b(compare|confronta|contradict|contraddizion|reconcil|riconcilia|cross-check|audit|synthesize|sintetizza|multi|portfolio|portafoglio|due diligence|legal|fiscale|architettura|strategy|strategia)\b",
    re.IGNORECASE,
)


def normalize_detail_tier(tier: Optional[str], default: str = "medium") -> str:
    raw = str(tier or default).strip().lower()
    if raw in {"max", "max_security", "local_only", "strict"}:
        return "max_security"
    if raw in {"light", "medium", "high"}:
        return raw
    return default if default in DETAIL_TIERS else "medium"


def _tier_to_vault_profile(detail_tier: str) -> str:
    norm = normalize_detail_tier(detail_tier)
    if norm == "max_security":
        return "max_security"
    if norm == "light":
        return "low"
    if norm == "high":
        return "max_context"
    return "medium"


def _tier_to_brain_read_tier(detail_tier: str) -> str:
    norm = normalize_detail_tier(detail_tier)
    return "max" if norm == "max_security" else norm


def _estimate_model_params_b(model_id: str) -> float:
    m = _PARAM_B_RE.search(str(model_id or ""))
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    low = str(model_id or "").lower()
    if "deep" in low or "orchestrator" in low:
        return 27.0
    if "mini" in low or "nano" in low or "tiny" in low:
        return 2.0
    return 8.0


def _probe_local_endpoint_fast(base_url: str, timeout_sec: float = 0.45) -> bool:
    """Fast stdlib TCP socket check against configured local runner endpoint (zero daemon, <0.5s)."""
    try:
        parsed = urllib.parse.urlparse(str(base_url or ""))
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        with socket.create_connection((host, port), timeout=timeout_sec):
            return True
    except OSError:
        return False


def _default_wiki_db(vault_db: Path) -> Path:
    return vault_db.parent / "second_brain_wiki.db"


def privatize_second_brain(
    target_path: str | Path,
    *,
    vault_db: Optional[Path | str] = None,
    wiki_db: Optional[Path | str] = None,
    detail_tier: str = "medium",
    policy: str = "auto",
    custom_terms: Optional[list[str]] = None,
    task_tags: Optional[list[str]] = None,
    use_local_ner: bool = False,
    reconcile: bool = True,
    curate_skill: bool = False,
    skill_name: Optional[str] = None,
    skills_dir: Optional[Path | str] = None,
    dry_run: bool = False,
    max_vault_sync_files: int = 250,
    config: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Privatizes a file, folder, or entire drive into an Anonymized 3+1 Tier Second Brain."""
    cfg = config if config is not None else load_cortical_config()
    priv_cfg = cfg.get("privacy") or {}
    terms = list(custom_terms if custom_terms is not None else (priv_cfg.get("custom_terms") or []))
    norm_tier = normalize_detail_tier(detail_tier)
    vault_profile = _tier_to_vault_profile(norm_tier)
    eff_policy = "fail_closed" if norm_tier == "max_security" else str(policy or priv_cfg.get("default_policy") or "auto")

    src = Path(target_path).expanduser().resolve()
    if not src.exists():
        raise FileNotFoundError(f"Target path does not exist: {src}")

    v_db = Path(vault_db or DEFAULT_VAULT_DB).expanduser()
    w_db = Path(wiki_db or _default_wiki_db(v_db)).expanduser()
    if not dry_run:
        v_db.parent.mkdir(parents=True, exist_ok=True)
        w_db.parent.mkdir(parents=True, exist_ok=True)

    vault = PrivacyVault(v_db) if not dry_run else None
    raw_tokens_est = 0
    tier_tokens: dict[str, int] = {"light": 0, "medium": 0, "high": 0, "max_security": 0}
    ingested_aliases: list[str] = []
    entities_masked_total = 0
    entities_by_category: dict[str, int] = {}
    files_privatized = 0
    merkle_root = ""

    if src.is_file():
        san = classify_and_sanitize(
            src,
            policy=eff_policy,
            profile=vault_profile,
            custom_terms=terms or None,
            use_local_ner=use_local_ner,
            config=cfg,
        )
        raw_sz = max(1, src.stat().st_size // 4)
        raw_tokens_est += raw_sz
        entities_masked_total += int(san.get("entity_count") or 0)
        for cat, cnt in (san.get("entities_by_category") or {}).items():
            entities_by_category[cat] = entities_by_category.get(cat, 0) + int(cnt)
        files_privatized = 1

        clean_txt = str(san.get("sanitized_text") or "")
        tier_tokens["light"] += max(1, min(len(clean_txt), 220) // 4)
        tier_tokens["medium"] += max(1, min(len(clean_txt), 700) // 4)
        tier_tokens["high"] += max(1, min(len(clean_txt), 2000) // 4)
        tier_tokens["max_security"] += max(1, len(clean_txt) // 4)

        if not dry_run and vault is not None:
            ing = vault.ingest(
                src,
                policy=eff_policy,
                profile=vault_profile,
                custom_terms=terms or None,
                use_local_ner=use_local_ner,
                config=cfg,
                task_tags=task_tags,
            )
            ingested_aliases.append(ing["alias"])
    else:
        # Directory / Drive recursive incremental Merkle crawl & pseudonymization
        kstore = KnowledgeStore(w_db if not dry_run else (Path(v_db.parent) / ".dry_run_wiki.db"))
        root_info = kstore.add_root(src, principal_id="local_owner")
        crawl_res = kstore.crawl_delta(
            root_id=root_info["root_id"],
            principal_id="local_owner",
            sanitize=True,
            privacy_profile="strict" if norm_tier in {"light", "max_security"} else "medium",
            custom_terms=terms or None,
            dry_run=dry_run,
            use_local_ner=use_local_ner,
        )
        files_privatized = int(crawl_res.get("files_sanitized") or crawl_res.get("files_scanned") or 0)
        entities_masked_total = int(crawl_res.get("entities_masked_total") or 0)
        entities_by_category = dict(crawl_res.get("entities_by_category") or {})
        merkle_root = str((crawl_res.get("merkle_roots") or {}).get(root_info["root_id"]) or "")

        if not dry_run and vault is not None:
            with kstore._connect() as conn:
                rows = conn.execute(
                    """SELECT rel_path, title, content, file_size, summaries_json, entities_masked
                       FROM documents WHERE root_id = ? ORDER BY indexed_at DESC LIMIT ?""",
                    (root_info["root_id"], max_vault_sync_files),
                ).fetchall()
            for row in rows:
                rel_path = str(row["rel_path"] or "doc")
                content = str(row["content"] or "")
                fsize = int(row["file_size"] or len(content.encode("utf-8")))
                raw_tokens_est += max(1, fsize // 4)
                try:
                    sums = json.loads(str(row["summaries_json"] or "{}"))
                except Exception:  # noqa: BLE001
                    sums = {}
                tier_tokens["light"] += max(1, len(str(sums.get("light") or content[:220])) // 4)
                tier_tokens["medium"] += max(1, len(str(sums.get("medium") or content[:700])) // 4)
                tier_tokens["high"] += max(1, len(str(sums.get("high") or content[:2000])) // 4)
                tier_tokens["max_security"] += max(1, len(content) // 4)

                alias_seed = f"{src.name}_{Path(rel_path).stem}"
                # Content is already pseudonymized by KnowledgeStore; ingest cleanly into Vault + LocalBrain 3+1 tiers
                ing = vault.ingest(
                    content or f"# {row['title'] or rel_path}",
                    alias=alias_seed,
                    policy="fail_closed" if norm_tier == "max_security" else "auto",
                    profile=vault_profile,
                    custom_terms=terms or None,
                    config=cfg,
                    task_tags=list(task_tags or [src.name.lower()]),
                )
                ingested_aliases.append(ing["alias"])
        else:
            # Dry-run estimate from filesystem sizes
            for fp in list(src.rglob("*"))[:max_vault_sync_files]:
                if fp.is_file() and not any(p.startswith(".") for p in fp.relative_to(src).parts):
                    sz = max(1, min(fp.stat().st_size, 2_000_000) // 4)
                    raw_tokens_est += sz
                    tier_tokens["light"] += max(1, min(sz, 55))
                    tier_tokens["medium"] += max(1, min(sz, 175))
                    tier_tokens["high"] += max(1, min(sz, 500))
                    tier_tokens["max_security"] += sz

    raw_base = max(1, raw_tokens_est)
    selected_tier_tokens = tier_tokens.get(norm_tier, tier_tokens["medium"])
    tier_saving_pct = round(max(0.0, (1.0 - (selected_tier_tokens / raw_base)) * 100.0), 1)

    manifest_obj = {
        "source": src.name,
        "detail_tier": norm_tier,
        "files_privatized": files_privatized,
        "aliases": [f"@private:{a}" for a in ingested_aliases[:25]],
        "entities_masked": entities_masked_total,
    }
    toon_comp = compress_structured(json.dumps(manifest_obj, ensure_ascii=False), fmt="json")
    # Estimated cloud cost saved at ~$3.00 / 1M input tokens
    tokens_saved = max(0, raw_tokens_est - selected_tier_tokens)
    usd_saved_est = round((tokens_saved / 1_000_000.0) * 3.0, 4)

    reconciliation_res: Optional[dict[str, Any]] = None
    if reconcile and not dry_run:
        reconciliation_res = reconcile_second_brain(
            vault_db=v_db,
            wiki_db=w_db if w_db.is_file() else None,
            detail_tier=norm_tier,
            custom_terms=terms or None,
        )

    skill_res: Optional[dict[str, Any]] = None
    if curate_skill and not dry_run:
        skill_res = curate_colleague_skill(
            topic=skill_name or src.name,
            vault_db=v_db,
            discrepancies=(reconciliation_res or {}).get("discrepancies"),
            detail_tier=norm_tier,
            skills_dir=skills_dir,
            config=cfg,
        )

    return {
        "ok": True,
        "target_name": src.name,
        "is_directory": src.is_dir(),
        "detail_tier": norm_tier,
        "local_only": norm_tier == "max_security",
        "dry_run": dry_run,
        "files_privatized": files_privatized,
        "aliases": ingested_aliases,
        "entities_masked_total": entities_masked_total,
        "entities_by_category": entities_by_category,
        "merkle_root": merkle_root,
        "token_economics": {
            "raw_tokens_est": raw_tokens_est,
            "tier_tokens_est": tier_tokens,
            "selected_tier_tokens_est": selected_tier_tokens,
            "tier_saving_pct": tier_saving_pct,
            "toon_saving_pct": toon_comp["saving_pct"],
            "estimated_cloud_usd_saved": usd_saved_est,
        },
        "toon_manifest": toon_comp["compressed"],
        "reconciliation": reconciliation_res,
        "curated_skill": skill_res,
    }


def reconcile_second_brain(
    *,
    vault_db: Optional[Path | str] = None,
    wiki_db: Optional[Path | str] = None,
    qa_notes: Optional[list[str]] = None,
    episode_title: str = "",
    detail_tier: str = "medium",
    custom_terms: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Reconciles concepts, flags cross-document numeric/date discrepancies, and records Q&A answers."""
    norm_tier = normalize_detail_tier(detail_tier)
    allow_local = norm_tier == "max_security"
    v_db = Path(vault_db or DEFAULT_VAULT_DB).expanduser()
    if not v_db.is_file():
        return {
            "concepts_count": 0,
            "merged_clusters": 0,
            "discrepancies": [],
            "qa_recorded": 0,
        }

    vault = PrivacyVault(v_db)
    clean_qa: list[str] = []
    for raw_note in (qa_notes or []):
        txt = str(raw_note or "").strip()
        if not txt:
            continue
        san = classify_and_sanitize(txt, policy="auto", profile="medium", custom_terms=custom_terms)
        clean_qa.append(san["sanitized_text"])

    if clean_qa:
        combined_qa = "\n".join(f"- {n}" for n in clean_qa)
        vault.brain.distill_and_factorize(
            "colleague_qa_memory",
            combined_qa,
            is_public=(norm_tier != "max_security"),
        )
        vault._write_brain_json()
        w_path = Path(wiki_db or _default_wiki_db(v_db)).expanduser()
        if w_path.is_file():
            try:
                ks = KnowledgeStore(w_path)
                ks.record_episode(
                    title=episode_title or "Colleague Q&A Clarification",
                    summary=combined_qa[:1200],
                    tags=["colleague-qa", norm_tier],
                )
            except Exception:  # noqa: BLE001
                pass

    items = vault.list_items(include_local_only=allow_local)
    doc_records: list[dict[str, Any]] = []
    read_tier = _tier_to_brain_read_tier(norm_tier)
    for it in items[:80]:
        alias = str(it.get("alias") or "")
        if not alias:
            continue
        try:
            res = vault.read_resource(
                alias,
                allow_local_only=allow_local,
                tier=read_tier if read_tier != "max" else "high",
                remote_egress=not allow_local,
                custom_terms=custom_terms,
            )
            txt = str(res.get("text") or "")
        except Exception:  # noqa: BLE001
            continue
        kws = set(_extract_keywords(txt, limit=14))
        figs = sorted({m.strip() for m in _AMOUNT_DATE_RE.findall(txt) if len(m.strip()) >= 2})
        doc_records.append({"alias": alias, "keywords": kws, "figures": figs, "text": txt[:600]})

    # Detect cross-document discrepancies where two documents share topic keywords but report different figures/dates
    discrepancies: list[dict[str, Any]] = []
    merged_clusters = 0
    for i in range(len(doc_records)):
        for j in range(i + 1, len(doc_records)):
            a, b = doc_records[i], doc_records[j]
            sim = _jaccard(a["keywords"], b["keywords"])
            shared = sorted(a["keywords"] & b["keywords"])
            if sim >= 0.22 or len(shared) >= 2:
                merged_clusters += 1
                figs_a, figs_b = set(a["figures"]), set(b["figures"])
                if figs_a and figs_b and figs_a != figs_b:
                    diff_a = sorted(figs_a - figs_b)[:3]
                    diff_b = sorted(figs_b - figs_a)[:3]
                    if diff_a and diff_b:
                        discrepancies.append({
                            "doc_a": f"@private:{a['alias']}",
                            "doc_b": f"@private:{b['alias']}",
                            "shared_topics": shared[:5],
                            "values_in_a": diff_a,
                            "values_in_b": diff_b,
                            "summary": (
                                f"@private:{a['alias']} ({', '.join(diff_a)}) vs "
                                f"@private:{b['alias']} ({', '.join(diff_b)}) on topic [{', '.join(shared[:3])}]"
                            ),
                        })

    snap = vault.brain.get_snapshot(include_local_only=allow_local)
    concepts = snap.get("by_concept") or snap.get("concepts") or []
    return {
        "concepts_count": len(concepts),
        "documents_checked": len(doc_records),
        "merged_clusters": merged_clusters,
        "discrepancies": discrepancies[:8],
        "qa_recorded": len(clean_qa),
    }


def curate_colleague_skill(
    *,
    topic: str,
    vault_db: Optional[Path | str] = None,
    qa_summary: str = "",
    discrepancies: Optional[list[dict[str, Any]]] = None,
    detail_tier: str = "medium",
    skills_dir: Optional[Path | str] = None,
    config: Optional[dict[str, Any]] = None,
    use_local_llm: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Generates a reusable, zero-PII domain `SKILL.md` from Second Brain knowledge and Q&A answers."""
    cfg = config if config is not None else load_cortical_config()
    terms = list((cfg.get("privacy") or {}).get("custom_terms") or []) or None
    norm_tier = normalize_detail_tier(detail_tier)
    clean_topic = classify_and_sanitize(str(topic or "colleague-workflow"), policy="auto", profile="low", custom_terms=terms)["sanitized_text"]
    slug = _slugify(clean_topic)[:40] or "colleague-second-brain"
    s_root = Path(skills_dir or (Path.cwd() / ".agents" / "skills")).expanduser()
    target = s_root / f"cortical-{slug}" / "SKILL.md"

    concepts_md: list[str] = []
    v_db = Path(vault_db or DEFAULT_VAULT_DB).expanduser()
    if v_db.is_file():
        vault = PrivacyVault(v_db)
        snap = vault.brain.get_snapshot(include_local_only=False)
        for c in (snap.get("by_concept") or snap.get("concepts") or [])[:8]:
            c_title = str(c.get("title") or c.get("concept") or "").strip()
            c_sum = str(c.get("summary") or "").strip()
            if c_title:
                safe_line = classify_and_sanitize(f"{c_title}: {c_sum}", policy="auto", profile="medium", custom_terms=terms)["sanitized_text"]
                concepts_md.append(f"- {safe_line[:220]}")

    lines = [
        "---",
        f"name: cortical-{slug}",
        f"description: Auto-generated anonymized Second Brain workflow skill for {clean_topic[:80]} (tier={norm_tier}).",
        "---",
        "",
        f"# Second Brain Workflow: {clean_topic[:80]}",
        "",
        "## 1. Privacy & Token-Saving Operating Rules",
        f"- **Default Detail Tier:** `{norm_tier}` (`light` ~85% saved · `medium` ~70% saved · `high` full pseudonymized · `max_security` 100% offline).",
        "- **Zero Raw PII:** Reference privatized documents strictly as `@private:<alias>` via `cortical_vault_read`; never expose raw names, IBANs, emails, or secret keys.",
        "- **Local-First Routing:** Execute first on `@role:daily_coder` / `@role:deep_reasoner` locally ($0 cloud cost). Escalate to a remote LLM only with an anonymized + `TOON`-compressed packet.",
    ]

    if qa_summary.strip():
        safe_qa = classify_and_sanitize(qa_summary.strip(), policy="auto", profile="medium", custom_terms=terms)["sanitized_text"]
        lines.extend(["", "## 2. User Preferences & Colleague Q&A Decisions", safe_qa])

    if concepts_md:
        lines.extend(["", "## 3. Reconciled Second Brain Knowledge", *concepts_md])

    if discrepancies:
        lines.extend(["", "## 4. Flagged Cross-Document Checks"])
        for d in discrepancies[:5]:
            safe_d = classify_and_sanitize(str(d.get("summary") or ""), policy="auto", profile="medium", custom_terms=terms)["sanitized_text"]
            lines.append(f"- Verify discrepancy: {safe_d}")

    content = "\n".join(lines).rstrip() + "\n"
    if use_local_llm and concepts_md:
        try:
            m_id = resolve_role_model("summarizer", cfg)
            refined = invoke_configured_runner(
                f"Polish this reusable Markdown SKILL.md while preserving YAML frontmatter and zero PII:\n\n{content[:3500]}",
                system_prompt="Return clean Markdown starting with --- frontmatter only.",
                config=cfg,
                model_override=m_id,
                max_tokens=600,
                timeout=20.0,
                role="colleague_skill_curator",
            )
            if refined and refined.strip().startswith("---") and not _verify_zero_residual_pii(refined, terms):
                content = refined.strip() + "\n"
        except Exception:  # noqa: BLE001
            pass

    residual = _verify_zero_residual_pii(content, terms)
    if residual:
        raise FailClosedError(f"Refusing to write skill with residual sensitive categories: {residual}")

    old = target.read_text(encoding="utf-8") if target.is_file() else None
    action = "create" if old is None else ("unchanged" if old == content else "update")
    if not dry_run and action != "unchanged":
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    return {
        "path": str(target),
        "skill_name": f"cortical-{slug}",
        "action": action,
        "concepts_included": len(concepts_md),
        "dry_run": dry_run,
    }


def evaluate_local_sufficiency(
    seed: str,
    *,
    context_tokens_est: int = 0,
    doc_count: int = 0,
    discrepancy_count: int = 0,
    detail_tier: str = "medium",
    execution_pref: str = "smart_local_first",
    lang: str = "en",
    config: Optional[dict[str, Any]] = None,
    runner_probe_fn: Optional[Callable[[str], bool]] = None,
) -> dict[str, Any]:
    """Determines if configured local LLM is sufficient or if safe anonymized remote escalation is recommended."""
    cfg = config if config is not None else load_cortical_config()
    norm_tier = normalize_detail_tier(detail_tier)
    is_it = str(lang or "en").lower().startswith("it")

    runner_id, _runner_type, base_url = resolve_active_runner_endpoint(cfg, v1=False)
    probe = runner_probe_fn or _probe_local_endpoint_fast
    runner_online = bool(probe(base_url))

    is_complex = bool(_COMPLEX_TASK_RE.search(seed or "")) or doc_count >= 5 or discrepancy_count >= 1 or context_tokens_est > 12000
    role_needed = "deep_reasoner" if is_complex else "daily_coder"
    model_id = resolve_role_model(role_needed, cfg)
    params_b = _estimate_model_params_b(model_id)

    complexity_score = min(
        1.0,
        round(
            (0.35 if _COMPLEX_TASK_RE.search(seed or "") else 0.1)
            + min(0.3, doc_count * 0.05)
            + min(0.2, discrepancy_count * 0.1)
            + min(0.25, context_tokens_est / 40000.0),
            2,
        ),
    )

    if norm_tier == "max_security" or execution_pref == "strict_local_only":
        reason = (
            f"Livello '{norm_tier}' attivo: i dati restano al 100% sul tuo computer (nessun invio cloud consentito)."
            if is_it
            else f"Tier '{norm_tier}' active: data stays 100% on your machine (remote cloud egress strictly blocked)."
        )
        return {
            "verdict": "local_only_required",
            "local_sufficient": runner_online,
            "remote_allowed": False,
            "runner": runner_id,
            "runner_online": runner_online,
            "recommended_role": f"@role:{role_needed}",
            "model_params_b_est": params_b,
            "complexity_score": complexity_score,
            "explanation": reason,
        }

    if execution_pref == "anonymized_remote_boost":
        reason = (
            "Hai richiesto il boost con AI remota: preparo un pacchetto 100% anonimizzato e compresso con TOON."
            if is_it
            else "Remote AI boost selected: preparing a 100% anonymized, TOON-compressed context packet."
        )
        return {
            "verdict": "escalate_anonymized_remote",
            "local_sufficient": False,
            "remote_allowed": True,
            "runner": runner_id,
            "runner_online": runner_online,
            "recommended_role": f"@role:{role_needed}",
            "model_params_b_est": params_b,
            "complexity_score": complexity_score,
            "explanation": reason,
        }

    # smart_local_first evaluation
    min_b_required = 12.0 if complexity_score >= 0.65 else (6.5 if complexity_score >= 0.35 else 1.5)
    ctx_fits_local = context_tokens_est <= (48000 if params_b >= 7.0 else 16000)

    if runner_online and params_b >= min_b_required and ctx_fits_local:
        reason = (
            f"Il modello locale ({runner_id} · @role:{role_needed}, ~{params_b:g}B) è attivo e sufficiente: costo cloud $0 e privacy totale."
            if is_it
            else f"Local model ({runner_id} · @role:{role_needed}, ~{params_b:g}B) is online and sufficient: $0 cloud cost and full local privacy."
        )
        return {
            "verdict": "local_sufficient",
            "local_sufficient": True,
            "remote_allowed": True,
            "runner": runner_id,
            "runner_online": True,
            "recommended_role": f"@role:{role_needed}",
            "model_params_b_est": params_b,
            "complexity_score": complexity_score,
            "explanation": reason,
        }

    why_gap = (
        f"nessun runner locale attivo su {runner_id}" if not runner_online
        else f"compito complesso (score {complexity_score}) rispetto alla capacità locale (~{params_b:g}B)"
    ) if is_it else (
        f"local runner {runner_id} is offline" if not runner_online
        else f"task complexity ({complexity_score}) exceeds local ~{params_b:g}B capacity"
    )
    reason = (
        f"Escalation sicura consigliata ({why_gap}): ho anonimizzato tutti i dati al livello '{norm_tier}' e compresso il contesto con TOON per usare una LLM remota in totale sicurezza."
        if is_it
        else f"Safe remote escalation recommended ({why_gap}): all context is anonymized at '{norm_tier}' detail and TOON-compressed for zero-PII cloud reasoning."
    )
    return {
        "verdict": "escalate_anonymized_remote",
        "local_sufficient": False,
        "remote_allowed": True,
        "runner": runner_id,
        "runner_online": runner_online,
        "recommended_role": f"@role:{role_needed}",
        "model_params_b_est": params_b,
        "complexity_score": complexity_score,
        "explanation": reason,
    }


def build_anonymized_escalation_packet(
    seed: str,
    *,
    vault_db: Optional[Path | str] = None,
    aliases: Optional[list[str]] = None,
    detail_tier: str = "medium",
    qa_decisions: Optional[list[str]] = None,
    discrepancies: Optional[list[dict[str, Any]]] = None,
    custom_terms: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Builds a `fail_closed`, `_verify_zero_residual_pii`-verified, `TOON`-compressed packet for a remote LLM."""
    norm_tier = normalize_detail_tier(detail_tier)
    if norm_tier == "max_security":
        raise FailClosedError("Cannot build remote escalation packet when detail_tier='max_security' (strictly offline).")

    clean_seed = classify_and_sanitize(str(seed or ""), policy="fail_closed", profile="low", custom_terms=custom_terms)["sanitized_text"]
    v_db = Path(vault_db or DEFAULT_VAULT_DB).expanduser()
    snippets: list[dict[str, Any]] = []
    blocked_max_security = 0
    raw_chars = 0

    if v_db.is_file():
        vault = PrivacyVault(v_db)
        items = vault.list_items(include_local_only=True)
        wanted = {a.replace("@private:", "") for a in (aliases or [])} if aliases else None
        for it in items:
            al = str(it.get("alias") or "")
            if wanted is not None and al not in wanted:
                continue
            if bool(it.get("local_only")) or str(it.get("profile")) == "max_security":
                blocked_max_security += 1
                continue
            try:
                res = vault.read_resource(
                    al,
                    allow_local_only=False,
                    tier=norm_tier,
                    remote_egress=True,
                    custom_terms=custom_terms,
                )
                txt = str(res.get("text") or "")
                raw_chars += max(len(txt), int(it.get("tokens_est") or 0) * 4)
                snippets.append({"ref": f"@private:{al}", "tier": norm_tier, "excerpt": txt[:1800]})
            except FailClosedError:
                blocked_max_security += 1
            if len(snippets) >= 12:
                break

    clean_qa = [
        classify_and_sanitize(str(q), policy="fail_closed", profile="medium", custom_terms=custom_terms)["sanitized_text"]
        for q in (qa_decisions or [])
        if str(q).strip()
    ]
    clean_disc = [
        classify_and_sanitize(str(d.get("summary") or ""), policy="fail_closed", profile="medium", custom_terms=custom_terms)["sanitized_text"]
        for d in (discrepancies or [])[:6]
        if d.get("summary")
    ]

    structured = {
        "objective": clean_seed,
        "detail_tier": norm_tier,
        "clarifications": clean_qa,
        "flagged_discrepancies": clean_disc,
        "anonymized_documents": snippets,
    }
    raw_json = json.dumps(structured, ensure_ascii=False, indent=2)
    comp = compress_structured(raw_json, fmt="json")
    packet_text = comp["compressed"]

    residual = _verify_zero_residual_pii(packet_text, custom_terms)
    if residual:
        raise FailClosedError(f"Blocked remote escalation packet due to residual sensitive markers: {residual}")

    return {
        "detail_tier": norm_tier,
        "documents_included": len(snippets),
        "blocked_max_security": blocked_max_security,
        "format_used": comp["format_used"],
        "saving_pct": comp["saving_pct"],
        "tokens_est": comp["compressed_tokens_est"],
        "packet": packet_text,
        "zero_residual_pii_verified": True,
    }
