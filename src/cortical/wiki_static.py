"""Zero-server static Wiki Explorer, Reconciled Context Tree & Offline Compaction Applier.

Exports Cortical's 4-tier Merkle Second Brain (`merkle_nodes`, `task_episodes`,
`task_discussion_synthesis`, `memory_insights`, `learned_skills_registry`,
`macro_edges`, `scoped_context_attachments`) into a self-contained static HTML
dashboard (`html/wiki.html`) supporting:
  - Reconciled context file systems (`Workspace` vs `Contesto Privato`) with cross-task correlations
  - Multi-perspective tree views (File System, Task & Correlations, Concept/Topic, Date, Token Savings)
  - Lazy-rendered collapsible folders scalable to thousands of files
  - Reactive 4-tier detail selector across both tree and detail panes
  - Group maintenance & knowledge distillation discarding heavy L4 Max blobs
"""

from __future__ import annotations

import datetime
import json
import time
from pathlib import Path
from typing import Any, Optional

from .wiki.db import AccessContext, CorticalWikiDB

_TOPIC_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("🛡️ Privacy & Sanitizer GDPR", ("privacy", "gdpr", "sanitizer", "anonym", "pseudonym", "redact", "private_notes")),
    ("📊 Token ROI & Analytics", ("token", "analytics", "roi", "transcript", "cost", "cache", "report", "savings", "omniroute")),
    ("🌳 Wiki & Compressione Contesto", ("merkle", "wiki", "crawler", "fts5", "subtree", "l1", "l2", "l3", "compression")),
    ("🧠 LLM Locali & Contesto 200k", ("ollama", "runner", "llama", "mlx", "context_window", "num_ctx", "vram", "qwen", "unsloth")),
    ("🔒 Harness, Sicurezza & Test", ("permission", "gate", "rbac", "acl", "test", "unittest", "approval", "sandbox")),
)


def _classify_topic(text: str) -> str:
    low = (text or "").lower()
    for label, kws in _TOPIC_RULES:
        if any(k in low for k in kws):
            return label
    return "⚙️ Architettura & Configurazione"


def _format_date_bucket(ts: float | None) -> tuple[str, str]:
    if not ts:
        return ("", "📅 Storico")
    try:
        dt = datetime.datetime.fromtimestamp(float(ts))
        day = dt.strftime("%Y-%m-%d")
        today = datetime.date.today()
        diff = (today - dt.date()).days
        if diff <= 0:
            return (day, f"📅 Oggi ({day})")
        if diff <= 7:
            return (day, f"📅 Ultimi 7 giorni ({day})")
        return (day, f"📅 {dt.strftime('%Y-%m')}")
    except Exception:  # noqa: BLE001
        return ("", "📅 Storico")


def collect_wiki_snapshot(
    wiki_db: CorticalWikiDB,
    ctx: Optional[AccessContext] = None,
    max_nodes: int = 1200,
) -> dict[str, Any]:
    """Collects a reconciled, multi-perspective JSON snapshot of the Second Brain."""
    access_ctx = ctx or AccessContext()
    nodes: list[dict[str, Any]] = []
    episodes: list[dict[str, Any]] = []
    insights: list[dict[str, Any]] = []
    skills: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    attachments: list[dict[str, Any]] = []

    ws_folder_privacy = "workspace_code"
    node_privacy_map: dict[str, str] = {}
    with wiki_db._connect() as conn:
        try:
            for r in conn.execute(
                """SELECT attachment_id, scope_id, item_type, item_ref, label, depth_tier, summary_preview, metadata_json, created_at
                   FROM scoped_context_attachments
                   WHERE tenant_id = ? AND workspace_id = ? AND item_type IN ('file', 'folder')
                   ORDER BY created_at DESC""",
                (access_ctx.tenant_id, access_ctx.workspace_id),
            ).fetchall():
                d_att = dict(r)
                meta_raw = {}
                try:
                    meta_raw = json.loads(str(d_att.get("metadata_json") or "{}"))
                except Exception:  # noqa: BLE001
                    meta_raw = {}
                prof = str(meta_raw.get("privacy_profile") or "").strip().lower()
                if not prof and str(d_att.get("depth_tier") or "") in {"max_security", "low", "medium", "max_context"}:
                    prof = str(d_att["depth_tier"])
                d_att["privacy_profile"] = prof or "medium"
                attachments.append(d_att)
                iref = str(d_att.get("item_ref") or "")
                if iref:
                    node_privacy_map[iref] = d_att["privacy_profile"]
                    if d_att.get("item_type") == "folder" and d_att["privacy_profile"] in {"max_security", "low", "medium"}:
                        ws_folder_privacy = d_att["privacy_profile"]
        except Exception:  # noqa: BLE001
            pass

        attached_paths = [str(a["item_ref"]) for a in attachments if a.get("item_ref")]

        try:
            for r in conn.execute(
                """SELECT e.episode_id, e.title, e.goal, e.outcome_status, e.learned_summary, e.created_at,
                          COALESCE(s.tier_l1_light, '') AS l1,
                          COALESCE(s.tier_l2_medium, '') AS l2,
                          COALESCE(s.tier_l3_high, '') AS l3,
                          COALESCE(s.tier_max_raw, '') AS l4
                   FROM task_episodes e
                   LEFT JOIN task_discussion_synthesis s
                     ON e.tenant_id = s.tenant_id
                    AND e.workspace_id = s.workspace_id
                    AND e.episode_id = s.episode_id
                   WHERE e.tenant_id = ? AND e.workspace_id = ?
                   ORDER BY e.created_at DESC LIMIT 150""",
                (access_ctx.tenant_id, access_ctx.workspace_id),
            ).fetchall():
                ep = dict(r)
                iso_d, bucket = _format_date_bucket(ep.get("created_at"))
                ep["date_iso"] = iso_d
                ep["date_group"] = bucket
                ep["topic"] = _classify_topic(f"{ep.get('title','')} {ep.get('goal','')} {ep.get('learned_summary','')}")
                episodes.append(ep)
        except Exception:  # noqa: BLE001
            pass

        try:
            for r in conn.execute(
                """SELECT source_id, source_type, target_id, target_type, relation, weight
                   FROM macro_edges
                   WHERE tenant_id = ? AND workspace_id = ?
                   LIMIT 400""",
                (access_ctx.tenant_id, access_ctx.workspace_id),
            ).fetchall():
                edges.append(dict(r))
        except Exception:  # noqa: BLE001
            pass

        # Precompute node -> related_tasks from edges + episode goals
        path_to_tasks: dict[str, set[str]] = {}
        for ed in edges:
            src, tgt = str(ed.get("source_id") or ""), str(ed.get("target_id") or "")
            if ed.get("source_type") == "episode" and tgt.startswith("/"):
                path_to_tasks.setdefault(tgt, set()).add(src)
            if ed.get("target_type") == "episode" and src.startswith("/"):
                path_to_tasks.setdefault(src, set()).add(tgt)

        try:
            for r in conn.execute(
                """SELECT path, node_type, subtree_hash, token_estimate, updated_at,
                          LENGTH(COALESCE(raw_content, '')) AS raw_chars,
                          summary_light AS tier_light,
                          summary_medium AS tier_medium,
                          summary_high AS tier_high,
                          SUBSTR(COALESCE(raw_content, ''), 1, 4000) AS content_preview
                   FROM merkle_nodes
                   WHERE tenant_id = ? AND workspace_id = ?
                   ORDER BY path ASC LIMIT ?""",
                (access_ctx.tenant_id, access_ctx.workspace_id, max_nodes),
            ).fetchall():
                row_d = dict(r)
                p_str = str(row_d.get("path") or "")
                if attached_paths:
                    ws_match = any(
                        Path(ap).name in ("cortical", "src") or ap in p_str or p_str.lstrip("/") in ap
                        for ap in attached_paths
                    )
                    if not ws_match:
                        continue
                l1_txt = str(row_d.get("tier_light") or "")
                l2_txt = str(row_d.get("tier_medium") or "")
                l3_txt = str(row_d.get("tier_high") or "")
                l1_tok = max(1, len(l1_txt) // 4) if l1_txt else 0
                l2_tok = max(1, len(l2_txt) // 4) if l2_txt else 0
                l3_tok = max(1, len(l3_txt) // 4) if l3_txt else 0
                raw_chars = int(row_d.pop("raw_chars", 0) or 0)
                est = int(row_d.get("token_estimate") or 0)
                raw_tok = max(est, raw_chars // 4, l3_tok, 1)
                ctx_root = "root:private_notes" if p_str.startswith("/private_notes") else "root:workspace"
                iso_d, bucket = _format_date_bucket(row_d.get("updated_at"))
                rel_tasks = sorted(path_to_tasks.get(p_str, set()))
                if not rel_tasks and episodes:
                    fname = Path(p_str).name.lower()
                    for ep in episodes[:40]:
                        if len(fname) > 4 and fname in str(ep.get("goal") or "").lower():
                            rel_tasks.append(str(ep["episode_id"]))

                row_d["l1_tokens"] = l1_tok
                row_d["l2_tokens"] = l2_tok
                row_d["l3_tokens"] = l3_tok
                row_d["raw_tokens"] = raw_tok
                row_d["saving_l1_pct"] = round(((raw_tok - l1_tok) / raw_tok) * 100.0, 2) if raw_tok else 0.0
                row_d["saving_l2_pct"] = round(((raw_tok - l2_tok) / raw_tok) * 100.0, 2) if raw_tok else 0.0
                row_d["context_root"] = ctx_root
                row_d["topic"] = _classify_topic(f"{p_str} {l1_txt} {l2_txt}")
                row_d["date_iso"] = iso_d
                row_d["date_group"] = bucket
                row_d["related_tasks"] = rel_tasks[:8]
                explicit_priv = node_privacy_map.get(p_str)
                if explicit_priv:
                    row_d["privacy_profile"] = explicit_priv
                elif ctx_root == "root:private_notes":
                    row_d["privacy_profile"] = "low"
                else:
                    row_d["privacy_profile"] = ws_folder_privacy if ws_folder_privacy != "workspace_code" else "workspace_code"
                nodes.append(row_d)
        except Exception:  # noqa: BLE001
            pass

        try:
            for r in conn.execute(
                """SELECT insight_id, category, insight_text, related_path, created_at
                   FROM memory_insights
                   WHERE tenant_id = ? AND workspace_id = ?
                   ORDER BY created_at DESC LIMIT 200""",
                (access_ctx.tenant_id, access_ctx.workspace_id),
            ).fetchall():
                ins = dict(r)
                txt = str(ins.get("insight_text") or "")
                rp = str(ins.get("related_path") or "")
                iso_d, bucket = _format_date_bucket(ins.get("created_at"))
                ins["topic"] = _classify_topic(f"{rp} {txt}")
                ins["date_iso"] = iso_d
                ins["date_group"] = bucket
                ins["context_root"] = "root:private_notes" if "private_notes" in rp or "omniroute" in txt.lower() else "root:workspace"
                ins["l1"] = txt[:135] + ("…" if len(txt) > 135 else "")
                ins["l2"] = f"[{ins.get('category','insight')}] {txt}" + (f"\nContesto collegato: {rp}" if rp else "")
                ins["l3"] = (
                    f"=== Conoscenza Distillata ({ins.get('category','insight')}) ===\n"
                    f"Regola/Insight: {txt}\n"
                    f"Topic Dominio: {ins['topic']}\n"
                    f"Path / Sorgente: {rp or 'workspace-wide'}\n"
                    f"Contesto Root: {ins['context_root']}"
                )
                insights.append(ins)
        except Exception:  # noqa: BLE001
            pass

        try:
            for r in conn.execute(
                """SELECT skill_id, name, description, skill_path, source_episode_id, use_count, helpful_count, created_at
                   FROM learned_skills_registry
                   WHERE tenant_id = ? AND workspace_id = ?
                   ORDER BY use_count DESC, created_at DESC LIMIT 100""",
                (access_ctx.tenant_id, access_ctx.workspace_id),
            ).fetchall():
                d_row = dict(r)
                sp = Path(str(d_row.get("skill_path") or ""))
                full_md = (
                    sp.read_text(encoding="utf-8", errors="replace")[:6000]
                    if sp.is_file()
                    else str(d_row.get("description") or "")
                )
                d_row["full_markdown"] = full_md
                d_row["topic"] = _classify_topic(f"{d_row.get('name','')} {d_row.get('description','')} {full_md[:600]}")
                iso_d, bucket = _format_date_bucket(d_row.get("created_at"))
                d_row["date_iso"] = iso_d
                d_row["date_group"] = bucket
                d_row["context_root"] = "root:workspace"
                d_row["l1"] = f"{d_row.get('name')} — {str(d_row.get('description') or '')[:150]}"
                med_lines = [ln for ln in full_md.splitlines() if ln.strip() and not ln.strip().startswith("---")][:14]
                d_row["l2"] = "\n".join(med_lines) if med_lines else d_row["l1"]
                d_row["l3"] = full_md
                skills.append(d_row)
        except Exception:  # noqa: BLE001
            pass

    # Reconcile Context File Systems & derive cross-task correlations
    ws_nodes = [n for n in nodes if n.get("context_root") == "root:workspace"]
    priv_nodes = [n for n in nodes if n.get("context_root") == "root:private_notes"]
    ws_folder_atts = [a for a in attachments if a.get("item_type") == "folder"]
    ws_label = Path(ws_folder_atts[0]["item_ref"]).name if ws_folder_atts else "cortical"
    ws_path = ws_folder_atts[0]["item_ref"] if ws_folder_atts else "/"

    # Map tasks referencing workspace vs private notes
    ws_tasks: list[str] = []
    priv_tasks: list[str] = []
    for ep in episodes:
        eid = str(ep["episode_id"])
        blob = f"{ep.get('goal','')} {ep.get('learned_summary','')} {ep.get('l2','')}".lower()
        if any(k in blob for k in ("omniroute", "private_notes", "privacy", "anonym")):
            priv_tasks.append(eid)
        if any(k in blob for k in ("cortical", "src", "cli.py", "token", "readme", "unittest", "wiki", "mcp")):
            ws_tasks.append(eid)
    # Also ensure tasks attached via macro_edges appear
    for p, tset in path_to_tasks.items():
        target_list = priv_tasks if p.startswith("/private_notes") else ws_tasks
        for tid in tset:
            if tid not in target_list:
                target_list.append(tid)

    context_roots: list[dict[str, Any]] = []
    if ws_nodes or ws_folder_atts:
        is_ws_priv = ws_folder_privacy in {"max_security", "low", "medium"}
        priv_tag = f" 🔒 Riservato ({ws_folder_privacy})" if ws_folder_privacy in {"max_security", "low"} else ""
        context_roots.append({
            "root_id": "root:workspace",
            "title_it": f"📁 Workspace Riconciliato: {ws_label}{priv_tag}",
            "title_en": f"📁 Reconciled Workspace: {ws_label}{priv_tag}",
            "mount_path": str(ws_path),
            "privacy_level": ws_folder_privacy if is_ws_priv else "workspace_code",
            "is_private": ws_folder_privacy in {"max_security", "low"},
            "attachment_count": max(1, len(ws_folder_atts)),
            "node_count": len(ws_nodes),
            "correlated_tasks": ws_tasks[:12],
        })
    if priv_nodes:
        context_roots.append({
            "root_id": "root:private_notes",
            "title_it": "🔒 Contesto Privato Sanitizzato (private_notes)",
            "title_en": "🔒 Sanitized Private Context (private_notes)",
            "mount_path": "/private_notes",
            "privacy_level": "low",
            "is_private": True,
            "attachment_count": sum(1 for a in attachments if "private_notes" in str(a.get("item_ref") or "")),
            "node_count": len(priv_nodes),
            "correlated_tasks": priv_tasks[:12],
        })

    # Derived Cross-Task Correlations (groups episodes by shared topic & context root)
    cross_task_correlations: list[dict[str, Any]] = []
    by_topic_eps: dict[str, list[dict[str, Any]]] = {}
    for ep in episodes:
        by_topic_eps.setdefault(ep.get("topic") or "⚙️ Architettura & Configurazione", []).append(ep)
    for topic_name, grp in by_topic_eps.items():
        if len(grp) >= 2:
            cross_task_correlations.append({
                "correlation_id": f"corr:{abs(hash(topic_name)) % 100000}",
                "topic": topic_name,
                "episode_ids": [str(e["episode_id"]) for e in grp[:10]],
                "summary": (
                    f"{len(grp)} task condividono moduli/concetti su '{topic_name}': "
                    + ", ".join(str(e["episode_id"]) for e in grp[:5])
                ),
            })

    aliases: list[dict[str, str]] = []
    seen_alias: set[str] = set()
    for cr in context_roots:
        al = Path(str(cr.get("mount_path") or cr["root_id"])).name or cr["root_id"].split(":")[-1]
        aliases.append({"alias": al, "kind": "root", "ref": cr["root_id"], "privacy": str(cr.get("privacy_level") or "low"), "label": cr["title_it"]})
        seen_alias.add(f"root:{al}")
    for n in nodes:
        if n.get("node_type") == "dir" or not n.get("path"):
            continue
        bname = Path(str(n["path"])).name
        if bname not in seen_alias:
            seen_alias.add(bname)
            p_eff = n.get("privacy_profile") if n.get("privacy_profile") in {"max_security", "low", "medium"} else "low"
            aliases.append({"alias": bname, "kind": "node", "ref": str(n["path"]), "privacy": str(p_eff), "label": str(n["path"])})
    for s in skills:
        aliases.append({"alias": str(s["skill_id"]), "kind": "skill", "ref": str(s["skill_id"]), "privacy": "medium", "label": str(s.get("description") or s["skill_id"])[:70]})

    file_nodes = [n for n in nodes if n.get("node_type") != "dir"] or nodes
    tot_raw = sum(int(n.get("raw_tokens") or 0) for n in file_nodes)
    tot_l1 = sum(int(n.get("l1_tokens") or 0) for n in file_nodes)
    tot_l2 = sum(int(n.get("l2_tokens") or 0) for n in file_nodes)
    tot_l3 = sum(int(n.get("l3_tokens") or 0) for n in file_nodes)
    return {
        "generated_at": time.time(),
        "counts": {
            "nodes": len(nodes),
            "episodes": len(episodes),
            "insights": len(insights),
            "skills": len(skills),
            "edges": len(edges),
            "context_roots": len(context_roots),
        },
        "optimization": {
            "file_nodes": len(file_nodes),
            "total_raw_tokens": tot_raw,
            "total_l1_tokens": tot_l1,
            "total_l2_tokens": tot_l2,
            "total_l3_tokens": tot_l3,
            "avg_l1_saving_pct": round(((tot_raw - tot_l1) / tot_raw) * 100.0, 1) if tot_raw else 0.0,
            "avg_l2_saving_pct": round(((tot_raw - tot_l2) / tot_raw) * 100.0, 1) if tot_raw else 0.0,
            "attached_paths": attached_paths,
        },
        "context_roots": context_roots,
        "cross_task_correlations": cross_task_correlations,
        "aliases": aliases[:250],
        "nodes": nodes,
        "episodes": episodes,
        "insights": insights,
        "skills": skills,
        "edges": edges,
    }


def apply_wiki_maintenance_patch(
    wiki_db: CorticalWikiDB,
    patch_data: dict[str, Any],
    ctx: Optional[AccessContext] = None,
) -> dict[str, int]:
    """Applies edits, hierarchical group deletions, and local-LLM distillation/compaction patches."""
    access_ctx = ctx or AccessContext()
    ops = patch_data.get("operations") or []
    applied = {"updated": 0, "deleted": 0, "compacted": 0, "skipped": 0}
    use_llm = bool(".cortical_data" in str(wiki_db.db_path))

    for op in ops:
        kind = str(op.get("op") or "")
        if kind == "distill_and_compact":
            from .skills_hub import CorticalSkillHub

            hub = CorticalSkillHub(wiki_db)
            t_kind = str(op.get("kind") or "subtree")
            t_id = str(op.get("id") or "/")
            k_tier = str(op.get("keep_tier") or "l2")
            hub.distill_and_compact_knowledge(t_kind, t_id, keep_tier=k_tier, use_local_llm=use_llm, ctx=access_ctx)
            applied["compacted"] += 1
            continue

        if kind == "attach_private_item":
            import hashlib

            wiki_db.ensure_workspace(access_ctx, root_path="/", can_write=True)
            p_path = "/" + str(op.get("path") or op.get("id") or "private_notes/item.txt").lstrip("/")
            s_l1 = str(op.get("summary_light") or p_path)[:280]
            s_l2 = str(op.get("summary_medium") or s_l1)[:1200]
            s_l3 = str(op.get("summary_high") or s_l2)[:3600]
            raw_txt = str(op.get("raw_content") or "")
            priv_prof = str(op.get("privacy_profile") or "low")
            chash = hashlib.sha256((raw_txt or s_l2).encode("utf-8", errors="replace")).hexdigest()
            parent = str(Path(p_path).parent.as_posix())
            if parent != "/":
                with wiki_db._connect() as conn:
                    conn.execute(
                        """INSERT OR IGNORE INTO merkle_nodes(
                               tenant_id, workspace_id, path, parent_path, node_type,
                               content_hash, subtree_hash, summary_light, summary_medium,
                               summary_high, raw_content, token_estimate, updated_at
                           ) VALUES (?, ?, ?, '/', 'dir', ?, ?, ?, ?, ?, '', 0, ?)""",
                        (access_ctx.tenant_id, access_ctx.workspace_id, parent, chash, chash, f"Dir {parent}", f"Private directory {parent}", f"Directory {parent}", time.time()),
                    )
            wiki_db.upsert_merkle_node(
                access_ctx,
                path=p_path,
                parent_path=parent,
                node_type=str(op.get("node_type") or "file"),
                content_hash=chash,
                subtree_hash=chash,
                summary_light=s_l1,
                summary_medium=s_l2,
                summary_high=s_l3,
                raw_content=raw_txt if priv_prof != "max_security" else "",
            )
            att_id = f"att_{hashlib.sha1(f'context:file:{p_path}'.encode('utf-8')).hexdigest()[:10]}"
            with wiki_db._connect() as conn:
                conn.execute(
                    """INSERT OR REPLACE INTO scoped_context_attachments(
                           attachment_id, tenant_id, workspace_id, scope_id,
                           item_type, item_ref, label, depth_tier, summary_preview,
                           metadata_json, created_at
                       ) VALUES (?, ?, ?, 'context', ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        att_id,
                        access_ctx.tenant_id,
                        access_ctx.workspace_id,
                        str(op.get("item_type") or "file"),
                        p_path,
                        Path(p_path).name,
                        priv_prof,
                        s_l1[:240],
                        json.dumps({"wiki_paths": [p_path], "privacy_profile": priv_prof}),
                        time.time(),
                    ),
                )
            applied["updated"] += 1
            continue

        with wiki_db._connect() as conn:
            if kind == "update_insight":
                iid = str(op.get("id") or "")
                txt = str(op.get("text") or "").strip()
                if iid and txt:
                    cur = conn.execute(
                        "UPDATE memory_insights SET insight_text = ? WHERE tenant_id = ? AND workspace_id = ? AND insight_id = ?",
                        (txt, access_ctx.tenant_id, access_ctx.workspace_id, iid),
                    )
                    applied["updated" if cur.rowcount else "skipped"] += 1
            elif kind == "delete_insight":
                iid = str(op.get("id") or "")
                if iid:
                    cur = conn.execute(
                        "DELETE FROM memory_insights WHERE tenant_id = ? AND workspace_id = ? AND insight_id = ?",
                        (access_ctx.tenant_id, access_ctx.workspace_id, iid),
                    )
                    applied["deleted" if cur.rowcount else "skipped"] += 1
            elif kind == "update_node":
                path = str(op.get("id") or "")
                med = str(op.get("text") or "").strip()
                if path and med:
                    cur = conn.execute(
                        "UPDATE merkle_nodes SET summary_medium = ?, summary_light = ? WHERE tenant_id = ? AND workspace_id = ? AND path = ?",
                        (med, med[:140], access_ctx.tenant_id, access_ctx.workspace_id, path),
                    )
                    applied["updated" if cur.rowcount else "skipped"] += 1
            elif kind == "delete_node":
                path = str(op.get("id") or "")
                if path:
                    cur = conn.execute(
                        "DELETE FROM merkle_nodes WHERE tenant_id = ? AND workspace_id = ? AND path = ?",
                        (access_ctx.tenant_id, access_ctx.workspace_id, path),
                    )
                    conn.execute(
                        "DELETE FROM merkle_fts WHERE tenant_id = ? AND workspace_id = ? AND path = ?",
                        (access_ctx.tenant_id, access_ctx.workspace_id, path),
                    )
                    applied["deleted" if cur.rowcount else "skipped"] += 1
            elif kind == "delete_subtree":
                pref = "/" + str(op.get("id") or "").strip("/")
                if pref != "/":
                    cur = conn.execute(
                        "DELETE FROM merkle_nodes WHERE tenant_id = ? AND workspace_id = ? AND (path = ? OR path LIKE ?)",
                        (access_ctx.tenant_id, access_ctx.workspace_id, pref, pref + "/%"),
                    )
                    conn.execute(
                        "DELETE FROM merkle_fts WHERE tenant_id = ? AND workspace_id = ? AND (path = ? OR path LIKE ?)",
                        (access_ctx.tenant_id, access_ctx.workspace_id, pref, pref + "/%"),
                    )
                    applied["deleted"] += int(cur.rowcount or 0)
                else:
                    applied["skipped"] += 1
            elif kind == "delete_skill":
                sid = str(op.get("id") or "")
                if sid:
                    cur = conn.execute(
                        "DELETE FROM learned_skills_registry WHERE tenant_id = ? AND workspace_id = ? AND skill_id = ?",
                        (access_ctx.tenant_id, access_ctx.workspace_id, sid),
                    )
                    applied["deleted" if cur.rowcount else "skipped"] += 1
            elif kind == "update_episode":
                eid = str(op.get("id") or "")
                summary = str(op.get("text") or "").strip()
                if eid and summary:
                    cur = conn.execute(
                        "UPDATE task_episodes SET learned_summary = ? WHERE tenant_id = ? AND workspace_id = ? AND episode_id = ?",
                        (summary, access_ctx.tenant_id, access_ctx.workspace_id, eid),
                    )
                    applied["updated" if cur.rowcount else "skipped"] += 1
            elif kind in {"delete_episode", "delete_related_group"}:
                target_id = str(op.get("id") or "")
                g_kind = str(op.get("kind") or ("episode" if kind == "delete_episode" else ""))
                if g_kind == "context_root":
                    if target_id == "root:private_notes":
                        cur = conn.execute(
                            "DELETE FROM merkle_nodes WHERE tenant_id = ? AND workspace_id = ? AND (path = '/private_notes' OR path LIKE '/private_notes/%')",
                            (access_ctx.tenant_id, access_ctx.workspace_id),
                        )
                    else:
                        cur = conn.execute(
                            "DELETE FROM merkle_nodes WHERE tenant_id = ? AND workspace_id = ? AND path NOT LIKE '/private_notes%'",
                            (access_ctx.tenant_id, access_ctx.workspace_id),
                        )
                    applied["deleted"] += int(cur.rowcount or 0)
                elif g_kind == "episode" and target_id:
                    cur = conn.execute(
                        "DELETE FROM task_episodes WHERE tenant_id = ? AND workspace_id = ? AND episode_id = ?",
                        (access_ctx.tenant_id, access_ctx.workspace_id, target_id),
                    )
                    conn.execute(
                        "DELETE FROM task_discussion_synthesis WHERE tenant_id = ? AND workspace_id = ? AND episode_id = ?",
                        (access_ctx.tenant_id, access_ctx.workspace_id, target_id),
                    )
                    applied["deleted" if cur.rowcount else "skipped"] += 1
                else:
                    applied["skipped"] += 1
            elif kind == "set_privacy_profile":
                target_ref = str(op.get("id") or "")
                priv_prof = str(op.get("privacy_profile") or "low")
                rows = conn.execute(
                    """SELECT attachment_id, metadata_json FROM scoped_context_attachments
                       WHERE tenant_id = ? AND workspace_id = ? AND (item_ref = ? OR label = ? OR ? = 'root:workspace')""",
                    (access_ctx.tenant_id, access_ctx.workspace_id, target_ref, target_ref, target_ref),
                ).fetchall()
                cnt = 0
                for row in rows:
                    try:
                        m = json.loads(str(row["metadata_json"] or "{}"))
                    except Exception:  # noqa: BLE001
                        m = {}
                    m["privacy_profile"] = priv_prof
                    conn.execute(
                        "UPDATE scoped_context_attachments SET depth_tier = ?, metadata_json = ? WHERE attachment_id = ?",
                        (priv_prof, json.dumps(m), row["attachment_id"]),
                    )
                    cnt += 1
                applied["updated" if cnt else "skipped"] += (cnt or 1)
            else:
                applied["skipped"] += 1
    return applied


def auto_apply_pending_wiki_patch(
    wiki_db: CorticalWikiDB,
    repo_root: Optional[Path] = None,
    ctx: Optional[AccessContext] = None,
) -> dict[str, Any]:
    """Automatically applies and consumes pending `wiki_maintenance_patch.json` files if present."""
    candidates: list[Path] = []
    if repo_root is not None:
        candidates.append(Path(repo_root) / "wiki_maintenance_patch.json")
    candidates.append(Path("wiki_maintenance_patch.json"))
    candidates.append(Path(wiki_db.db_path).parent / "wiki_maintenance_patch.json")

    seen: set[Path] = set()
    total = {"applied_files": 0, "updated": 0, "deleted": 0, "compacted": 0, "skipped": 0}
    for cand in candidates:
        try:
            rp = cand.resolve()
        except OSError:
            continue
        if rp in seen or not rp.is_file():
            continue
        seen.add(rp)
        try:
            payload = json.loads(rp.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and payload.get("operations"):
                res = apply_wiki_maintenance_patch(wiki_db, payload, ctx=ctx)
                total["applied_files"] += 1
                for k in ("updated", "deleted", "compacted", "skipped"):
                    total[k] += int(res.get(k, 0))
            rp.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            continue
    return total


def render_static_wiki_dashboard_html(snapshot: dict[str, Any]) -> str:
    """Renders a zero-server static Wiki Explorer with reconciled contexts, multi-views & lazy trees."""
    safe_json = json.dumps(snapshot, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Cortical Second Brain · Static Wiki Explorer</title>
  <style>
    :root {{ --bg:#0b1120; --card:#131c2e; --card2:#090e1a; --border:#24324a; --text:#e2e8f0; --muted:#94a3b8; --accent:#38bdf8; --emerald:#34d399; --amber:#fbbf24; --danger:#f87171; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; background:var(--bg); color:var(--text); }}
    .wrap {{ width:100%; max-width:1380px; margin:0 auto; padding:22px 20px 56px; }}
    .top {{ display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; margin-bottom:14px; }}
    h1 {{ margin:0; font-size:1.45rem; }}
    .kpi-bar {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:10px; margin-bottom:14px; }}
    .kpi {{ background:var(--card); border:1px solid var(--border); border-radius:10px; padding:10px 12px; cursor:pointer; transition:border-color 0.15s; }}
    .kpi:hover {{ border-color:var(--accent); }}
    .kpi .v {{ font-size:1.22rem; font-weight:800; color:var(--emerald); }}
    .kpi .l {{ font-size:0.74rem; color:var(--muted); }}
    .controls {{ display:flex; gap:8px; flex-wrap:wrap; margin-bottom:12px; align-items:center; }}
    input, select, textarea {{ background:var(--card2); color:var(--text); border:1px solid var(--border); border-radius:8px; padding:8px 10px; font-size:0.84rem; max-width:100%; }}
    textarea {{ min-height:110px; width:100%; resize:vertical; line-height:1.45; }}
    .btn {{ padding:6px 11px; border-radius:8px; border:1px solid var(--border); background:var(--card); color:var(--text); cursor:pointer; font-weight:600; font-size:0.8rem; }}
    .btn-sm {{ padding:3px 7px; font-size:0.72rem; border-radius:6px; }}
    .btn-primary {{ background:var(--accent); color:#082f49; border-color:var(--accent); }}
    .btn-emerald {{ background:rgba(52,211,153,0.14); color:var(--emerald); border-color:rgba(52,211,153,0.45); }}
    .btn-danger {{ color:var(--danger); border-color:rgba(248,113,113,0.4); }}
    .layout {{ display:grid; grid-template-columns:minmax(300px, 430px) minmax(0, 1fr); gap:14px; align-items:start; }}
    @media (max-width:900px) {{ .layout {{ grid-template-columns:1fr; }} }}
    .panel {{ background:var(--card); border:1px solid var(--border); border-radius:12px; padding:14px; max-height:78vh; overflow-y:auto; min-width:0; overflow-wrap:anywhere; }}
    .item {{ padding:9px 11px; border:1px solid var(--border); border-radius:8px; margin-bottom:7px; cursor:pointer; background:rgba(9,14,26,0.45); }}
    .item:hover, .item.active {{ border-color:var(--accent); background:rgba(56,189,248,0.1); }}
    .tag {{ font-size:0.7rem; padding:2px 7px; border-radius:999px; border:1px solid var(--border); color:var(--accent); margin-right:6px; }}
    pre {{ white-space:pre-wrap; overflow-wrap:anywhere; background:var(--card2); border:1px solid var(--border); padding:14px; border-radius:8px; font-size:0.84rem; line-height:1.5; }}
    .ctx-mount {{ border:1px solid var(--border); border-radius:10px; padding:8px 10px; margin-bottom:10px; background:rgba(9,14,26,0.55); }}
    .ctx-mount.workspace {{ border-left:4px solid var(--accent); }}
    .ctx-mount.private {{ border-left:4px solid var(--amber); background:rgba(251,191,36,0.04); }}
    .folder-hdr {{ display:flex; align-items:center; justify-content:space-between; gap:6px; padding:5px 7px; border-radius:7px; font-size:0.83rem; font-weight:600; color:var(--accent); cursor:pointer; user-select:none; }}
    .folder-hdr:hover {{ background:rgba(56,189,248,0.08); }}
    .tree-children {{ padding-left:14px; border-left:1px dashed var(--border); margin-left:9px; margin-top:2px; }}
    .tree-leaf {{ padding:5px 8px; border-radius:7px; font-size:0.81rem; cursor:pointer; margin:2px 0; border:1px solid transparent; }}
    .tree-leaf:hover {{ background:rgba(56,189,248,0.08); }}
    .tree-leaf.active {{ background:rgba(56,189,248,0.14); border-color:var(--accent); color:#fff; }}
    .leaf-top {{ display:flex; align-items:center; justify-content:space-between; gap:6px; }}
    .leaf-sub {{ font-size:0.73rem; color:var(--muted); margin-top:2px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
    .rich-box {{ background:var(--card2); border:1px solid var(--border); border-radius:10px; padding:14px 16px; font-size:0.86rem; line-height:1.55; }}
    .rich-h {{ font-size:0.95rem; font-weight:700; color:var(--accent); margin:12px 0 6px; padding-bottom:4px; border-bottom:1px solid var(--border); }}
    .rich-h:first-child {{ margin-top:0; }}
    .rich-note {{ border-left:3px solid var(--emerald); background:rgba(52,211,153,0.08); padding:8px 12px; border-radius:0 8px 8px 0; margin:8px 0; }}
    .rich-kv {{ margin:4px 0; }}
    .rich-code {{ background:#131c2e; border:1px solid var(--border); padding:1px 5px; border-radius:4px; font-family:ui-monospace,monospace; font-size:0.8rem; color:var(--emerald); }}
    .tier-box {{ background:var(--card2); border:1px solid var(--border); border-radius:9px; padding:10px 12px; margin-bottom:12px; font-size:0.78rem; }}
    .tier-pills {{ display:flex; flex-wrap:wrap; gap:6px; margin-bottom:6px; }}
    .tier-pill {{ padding:3px 9px; border-radius:999px; border:1px solid var(--border); color:var(--text); background:#131c2e; cursor:pointer; }}
    .tier-pill.active-tier {{ border-color:var(--accent); background:rgba(56,189,248,0.18); color:var(--accent); font-weight:700; }}
    .tier-bar {{ height:8px; border-radius:999px; background:#1e293b; overflow:hidden; display:flex; }}
    .corr-pill {{ font-size:0.71rem; color:var(--emerald); background:rgba(52,211,153,0.1); border:1px solid rgba(52,211,153,0.3); padding:2px 7px; border-radius:999px; display:inline-block; margin:2px 4px 2px 0; }}
    .toast {{ display:none; padding:9px 13px; border-radius:9px; border:1px solid var(--emerald); background:rgba(52,211,153,0.1); color:var(--text); font-size:0.82rem; margin-bottom:12px; justify-content:space-between; align-items:center; gap:10px; flex-wrap:wrap; }}
    .toast.show {{ display:flex; }}
    .vault-box {{ background:var(--card); border:1px solid var(--border); border-left:4px solid var(--amber); border-radius:10px; padding:11px 14px; margin-bottom:12px; }}
    .auto-list {{ display:none; margin-top:6px; border:1px solid var(--border); border-radius:8px; background:var(--card2); max-height:190px; overflow-y:auto; }}
    .auto-list.show {{ display:block; }}
    .auto-row {{ display:flex; justify-content:space-between; align-items:center; gap:8px; padding:6px 10px; border-bottom:1px solid var(--border); font-size:0.79rem; }}
    .auto-row:last-child {{ border-bottom:none; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="top">
      <div>
        <h1 id="w-title">🧠 Cortical Second Brain · Knowledge &amp; Context Wiki</h1>
        <div style="font-size:0.82rem; color:var(--muted);">
          <span id="w-sub">Zero-server · Contesti riconciliati, viste multi-prospettiva e distillazione autonoma</span> ·
          <a href="./token_report.html" style="color:var(--accent);">📊 Token Report</a> ·
          <a href="./settings.html" style="color:var(--accent);">⚙️ Settings</a> ·
          <a href="./help.html" style="color:var(--accent);">❓ Help</a> ·
          <a href="./index.html" style="color:var(--accent);">🏠 Home</a>
        </div>
      </div>
      <div style="display:flex; gap:8px; flex-wrap:wrap; align-items:center;">
        <button class="btn" id="w-lang-btn" onclick="toggleWikiLang()">🇮🇹 IT</button>
        <span id="patch-count" style="font-size:0.8rem; color:var(--emerald);">0 modifiche locali</span>
        <button class="btn btn-sm" id="btn-undo" onclick="undoLastOp()" style="display:none;">↩️ Annulla</button>
        <button class="btn btn-primary" id="btn-export" onclick="exportPatch()">💾 Salva su Disco &amp; Applica</button>
        <button class="btn" id="btn-reset" onclick="clearPatch()">🧹 Reset</button>
      </div>
    </div>

    <div id="action-toast" class="toast">
      <span id="toast-msg"></span>
      <button class="btn btn-sm" onclick="undoLastOp()">↩️ Annulla Ultima Azione</button>
    </div>

    <div class="kpi-bar" id="kpi-bar"></div>

    <div class="vault-box">
      <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; margin-bottom:8px;">
        <strong style="font-size:0.86rem; color:var(--amber);" id="vault-title">🔒 Vault &amp; Selettore Guidato File/Cartelle Riservati (Zero-Path + Autocompletamento)</strong>
        <div style="display:flex; gap:6px; flex-wrap:wrap; align-items:center;">
          <select id="vault-privacy" style="padding:5px 8px; font-size:0.78rem;">
            <option value="max_security">🔒 Max Security (0 byte al cloud · Solo Locale)</option>
            <option value="low" selected>🛡️ Alta Privacy (Solo Sintesi L1/L2 Anonimizzata)</option>
            <option value="medium">⚖️ Media (Pseudonimi [PERSON_NAME_1])</option>
          </select>
          <input id="pick-files" type="file" multiple style="display:none;" onchange="handlePickedFiles(this.files, false)" />
          <input id="pick-dir" type="file" webkitdirectory directory multiple style="display:none;" onchange="handlePickedFiles(this.files, true)" />
          <button class="btn btn-sm btn-primary" onclick="document.getElementById('pick-files').click()">📄 + File Riservati...</button>
          <button class="btn btn-sm btn-emerald" onclick="document.getElementById('pick-dir').click()">📁 + Cartella Riservata...</button>
        </div>
      </div>
      <input id="ref-auto-input" type="search" placeholder="Cerca nome file, cartella, concetto o skill per ottenere @private:nome o /private senza digitare path..." style="width:100%;" oninput="renderRefAutocomplete()" onfocus="renderRefAutocomplete()" />
      <div id="ref-auto-list" class="auto-list"></div>
    </div>

    <div class="controls">
      <input id="q" type="search" placeholder="Cerca nei file, task, conoscenze, skill..." style="flex:1; min-width:220px;" oninput="renderList()" />
      <select id="view-mode" onchange="onViewModeChange()"></select>
      <select id="kind" onchange="renderList()"></select>
      <select id="depth" onchange="onDepthChange()"></select>
      <button class="btn btn-sm" id="btn-expand-all" onclick="expandAllDirs(true)">➕ Espandi</button>
      <button class="btn btn-sm" id="btn-collapse-all" onclick="expandAllDirs(false)">➖ Comprimi</button>
    </div>

    <div class="layout">
      <div class="panel" id="list"></div>
      <div class="panel" id="detail"></div>
    </div>
  </div>

  <script>
    const SNAP = {safe_json};
    const STORAGE_KEY = 'cortical_wiki_patch_v2';
    let PATCH = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{{"operations":[]}}');
    let WLANG = localStorage.getItem('cortical_lang') || 'it';
    let ACTIVE = null;
    let HISTORY_STACK = [];
    let OPEN_DIRS = new Set(['root:workspace', 'root:private_notes', 'fs:root:workspace:/src', 'fs:root:private_notes:/private_notes', 'corr_box']);

    const esc = (s) => String(s || '').replace(/[&<>"']/g, (c) => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
    const fmt = (n) => Number(n || 0).toLocaleString('en-US');
    const normTokens = (s) => String(s || '').toLowerCase().split(/[^a-z0-9_]+/).filter((t) => t.length > 2);

    let ITEMS = [
      ...(SNAP.nodes || []).map((n) => ({{ kind:'node', id:n.path, title:n.path, sub:n.node_type, context_root:n.context_root || 'root:workspace', privacy_profile:n.privacy_profile || 'workspace_code', topic:n.topic || '', date_group:n.date_group || '', related_tasks:n.related_tasks || [], l1:n.tier_light, l2:n.tier_medium, l3:n.tier_high, l4:n.content_preview || n.tier_high, raw:n }})),
      ...(SNAP.episodes || []).map((e) => ({{ kind:'episode', id:e.episode_id, title:e.title || e.episode_id, sub:e.outcome_status, context_root:'root:workspace', privacy_profile:'workspace_code', topic:e.topic || '', date_group:e.date_group || '', related_tasks:[e.episode_id], l1:e.l1 || e.goal, l2:e.l2 || e.learned_summary || e.goal, l3:e.l3 || e.learned_summary || e.l2, l4:e.l4 || JSON.stringify(e, null, 2), raw:e }})),
      ...(SNAP.insights || []).map((i) => ({{ kind:'insight', id:i.insight_id, title:i.insight_text, sub:i.category, context_root:i.context_root || 'root:workspace', privacy_profile:'low', topic:i.topic || '', date_group:i.date_group || '', related_tasks:[], l1:i.l1 || i.insight_text, l2:i.l2 || i.insight_text, l3:i.l3 || i.insight_text, l4:JSON.stringify(i, null, 2), raw:i }})),
      ...(SNAP.skills || []).map((s) => ({{ kind:'skill', id:s.skill_id, title:s.name, sub:`uses:${{s.use_count}} · ${{s.topic || ''}}`, context_root:s.context_root || 'root:workspace', privacy_profile:'medium', topic:s.topic || '', date_group:s.date_group || '', related_tasks:s.source_episode_id ? [s.source_episode_id] : [], l1:s.l1 || s.description, l2:s.l2 || s.full_markdown || s.description, l3:s.l3 || s.full_markdown || s.description, l4:s.full_markdown + '\\n\\n' + JSON.stringify({{skill_id:s.skill_id, use_count:s.use_count, helpful_count:s.helpful_count}}, null, 2), raw:s }})),
    ];

    const WI18N = {{
      it: {{
        sub: 'Zero-server · Contesti riconciliati, viste multi-prospettiva e distillazione autonoma',
        exportBtn: '💾 Salva su Disco & Applica',
        resetBtn: '🧹 Reset',
        undoBtn: '↩️ Annulla',
        expandBtn: '➕ Espandi',
        collapseBtn: '➖ Comprimi',
        queued: 'modifiche pronte',
        searchPh: 'Cerca nei file, task, conoscenze, skill...',
        vaultTitle: '🔒 Vault & Selettore Guidato File/Cartelle Riservati (Zero-Path + Autocompletamento)',
        autoPh: 'Cerca nome file, cartella, concetto o skill per ottenere @private:nome o /private senza digitare path...',
        k_nodes: 'File & Cartelle Indice',
        k_comp: 'Compressione L1 Media',
        k_ep: 'Task & Sintesi 3+1',
        k_ins: 'Conoscenze Distillate',
        k_sk: 'Cortical Skill Engine',
        k_edge: 'Archi & Correlazioni',
        v_fs: '🌳 Vista: File System & Contesto (Riconciliato)',
        v_task: '🎯 Vista: Per Task & Correlazioni',
        v_topic: '🧠 Vista: Per Concetto / Topic Dominio',
        v_date: '📅 Vista: Per Data / Cronologia',
        v_sav: '📉 Vista: Per Risparmio Contesto',
        optAll: 'Tutti i Contenuti',
        optNode: '📁 File & Cartelle di Contesto',
        optEp: '🗂️ Task & Sintesi Episodi',
        optIns: '💡 Regole & Conoscenze Distillate',
        optSk: '⚡ Skill Procedurali (Cortical Skill Engine)',
        d1: 'Livello 1 · Sintesi Rapida (~50 tok)',
        d2: 'Livello 2 · Sintesi Strutturata (~250 tok)',
        d3: 'Livello 3 · Analisi Estesa (~1000 tok)',
        d4: 'Livello 4 · Integrale (Max)',
        pickPrompt: 'Seleziona un file, cartella, task, conoscenza o skill per ispezionarlo o compattarlo.',
        compTitle: 'Ottimizzazione Contesto 4-Tier (clicca livello per cambiare)',
        linksTitle: 'Connessioni Conoscenza & Macro-Graph',
        corrTitle: '🔗 Correlazioni Cross-Task Derivate',
        maintTitle: 'MANUTENZIONE IMMEDIATA & DISTILLAZIONE CONOSCENZA',
        distillBtn: '🧪 Distilla Conoscenza & Scarta Max (L4)',
        saveOp: '✏️ Salva Modifica',
        delOp: '🗑️ Rimuovi Elemento',
        delGroupBtn: '🗑️ Rimuovi Gruppo',
        openSrc: '🔗 Apri Episodio',
        sharedBy: 'task correlati',
        savedMsg: '✅ Modifica applicata nella vista! Premi "Salva su Disco & Applica" per persisterla in .cortical_data/wiki.db.',
        deletedMsg: '🗑️ Rimosso immediatamente dalla vista!',
        distilledMsg: '🧪 Conoscenza distillata in Insight e livello Max (L4) scartato!',
      }},
      en: {{
        sub: 'Zero-server · Reconciled context trees, multi-perspective views & local distillation',
        exportBtn: '💾 Save to Disk & Apply',
        resetBtn: '🧹 Reset',
        undoBtn: '↩️ Undo',
        expandBtn: '➕ Expand',
        collapseBtn: '➖ Collapse',
        queued: 'edits ready',
        searchPh: 'Search files, episodes, insights, skills...',
        vaultTitle: '🔒 Guided Private File/Folder Picker & Reference Autocomplete (Zero-Path)',
        autoPh: 'Type filename, folder, concept, or skill to copy @private:alias or /private without full paths...',
        k_nodes: 'Indexed Files & Folders',
        k_comp: 'Avg L1 Compression',
        k_ep: 'Tasks & 3+1 Syntheses',
        k_ins: 'Distilled Insights',
        k_sk: 'Cortical Skill Engine',
        k_edge: 'Knowledge Links',
        v_fs: '🌳 View: Reconciled Context File System',
        v_task: '🎯 View: By Task & Cross-Correlations',
        v_topic: '🧠 View: By Domain Concept / Topic',
        v_date: '📅 View: By Timeline / Date',
        v_sav: '📉 View: By Context Token Savings',
        optAll: 'All Knowledge Items',
        optNode: '📁 Context Files & Folders',
        optEp: '🗂️ Tasks & 3+1 Syntheses',
        optIns: '💡 Distilled Rules & Insights',
        optSk: '⚡ Procedural Skills (Cortical Skill Engine)',
        d1: 'Tier 1 · Quick Digest (~50 tok)',
        d2: 'Tier 2 · Structured Summary (~250 tok)',
        d3: 'Tier 3 · Extended Analysis (~1000 tok)',
        d4: 'Tier 4 · Full Content (Max)',
        pickPrompt: 'Select any file, folder, task, insight, or skill to inspect or compact.',
        compTitle: '4-Tier Context Optimization (click tier to switch)',
        linksTitle: 'Knowledge & Macro-Graph Connections',
        corrTitle: '🔗 Derived Cross-Task Correlations',
        maintTitle: 'LIVE MAINTENANCE & KNOWLEDGE DISTILLATION',
        distillBtn: '🧪 Distill Insight & Discard Max (L4)',
        saveOp: '✏️ Save Edit',
        delOp: '🗑️ Delete Item',
        delGroupBtn: '🗑️ Remove Group',
        openSrc: '🔗 Open Episode',
        sharedBy: 'correlated tasks',
        savedMsg: '✅ Edit applied! Click "Save to Disk & Apply" to persist into .cortical_data/wiki.db.',
        deletedMsg: '🗑️ Removed from view immediately!',
        distilledMsg: '🧪 Knowledge distilled to Insight and Max (L4) discarded!',
      }}
    }};

    function curDepth() {{ return document.getElementById('depth')?.value || 'l2'; }}
    function depthTokens(it, d) {{
      const txt = it[d] || it.l2 || it.l1 || '';
      if (it.kind === 'node' && it.raw) {{
        if (d === 'l1') return it.raw.l1_tokens || Math.max(1, Math.round(txt.length / 4));
        if (d === 'l2') return it.raw.l2_tokens || Math.max(1, Math.round(txt.length / 4));
        if (d === 'l3') return it.raw.l3_tokens || Math.max(1, Math.round(txt.length / 4));
        return it.raw.raw_tokens || Math.max(1, Math.round(txt.length / 4));
      }}
      return txt ? Math.max(1, Math.round(txt.length / 4)) : 0;
    }}

    function renderKpis() {{
      const L = WI18N[WLANG] || WI18N.it;
      const c = SNAP.counts || {{}};
      const opt = SNAP.optimization || {{}};
      document.getElementById('kpi-bar').innerHTML = `
        <div class="kpi" onclick="setKindFilter('node')"><div class="v">${{c.nodes || 0}}</div><div class="l">${{L.k_nodes}} (${{c.context_roots || 1}} root)</div></div>
        <div class="kpi" onclick="setKindFilter('node')"><div class="v">${{Number(opt.avg_l1_saving_pct||0).toFixed(1)}}%</div><div class="l">${{L.k_comp}} (${{fmt(opt.total_l1_tokens)}} / ${{fmt(opt.total_raw_tokens)}})</div></div>
        <div class="kpi" onclick="setKindFilter('episode')"><div class="v">${{c.episodes || 0}}</div><div class="l">${{L.k_ep}}</div></div>
        <div class="kpi" onclick="setKindFilter('insight')"><div class="v">${{c.insights || 0}}</div><div class="l">${{L.k_ins}}</div></div>
        <div class="kpi" onclick="setKindFilter('skill')"><div class="v">${{c.skills || 0}}</div><div class="l">${{L.k_sk}}</div></div>
        <div class="kpi" onclick="setViewMode('task')"><div class="v">${{c.edges || 0}}</div><div class="l">${{L.k_edge}}</div></div>`;
    }}

    function syncChromeLang() {{
      const L = WI18N[WLANG] || WI18N.it;
      document.getElementById('w-lang-btn').textContent = WLANG === 'it' ? '🇮🇹 IT' : '🇬🇧 EN';
      document.getElementById('w-sub').textContent = L.sub;
      document.getElementById('btn-export').textContent = L.exportBtn;
      document.getElementById('btn-reset').textContent = L.resetBtn;
      document.getElementById('btn-undo').textContent = L.undoBtn;
      document.getElementById('btn-expand-all').textContent = L.expandBtn;
      document.getElementById('btn-collapse-all').textContent = L.collapseBtn;
      document.getElementById('q').placeholder = L.searchPh;
      document.getElementById('vault-title').textContent = L.vaultTitle;
      document.getElementById('ref-auto-input').placeholder = L.autoPh;
      document.getElementById('patch-count').textContent = `${{PATCH.operations.length}} ${{L.queued}}`;

      const vm = document.getElementById('view-mode');
      const curV = vm.value || 'filesystem';
      vm.innerHTML = `
        <option value="filesystem">${{L.v_fs}}</option>
        <option value="task">${{L.v_task}}</option>
        <option value="topic">${{L.v_topic}}</option>
        <option value="date">${{L.v_date}}</option>
        <option value="savings">${{L.v_sav}}</option>`;
      vm.value = curV;

      const kindSel = document.getElementById('kind');
      const curK = kindSel.value || 'all';
      kindSel.innerHTML = `
        <option value="all">${{L.optAll}}</option>
        <option value="node">${{L.optNode}}</option>
        <option value="episode">${{L.optEp}}</option>
        <option value="insight">${{L.optIns}}</option>
        <option value="skill">${{L.optSk}}</option>`;
      kindSel.value = curK;

      const depthSel = document.getElementById('depth');
      const curD = depthSel.value || 'l2';
      depthSel.innerHTML = `
        <option value="l1">${{L.d1}}</option>
        <option value="l2">${{L.d2}}</option>
        <option value="l3">${{L.d3}}</option>
        <option value="l4">${{L.d4}}</option>`;
      depthSel.value = curD;

      renderKpis();
    }}

    window.setKindFilter = function(val) {{ document.getElementById('kind').value = val; renderList(); }};
    window.setViewMode = function(val) {{ document.getElementById('view-mode').value = val; renderList(); }};
    window.onViewModeChange = function() {{ renderList(); }};
    window.onDepthChange = function() {{ renderList(); renderDetail(); }};
    window.setDepthDirect = function(d) {{ document.getElementById('depth').value = d; onDepthChange(); }};

    window.toggleDir = function(dirId, ev) {{
      if (ev) ev.stopPropagation();
      if (OPEN_DIRS.has(dirId)) OPEN_DIRS.delete(dirId);
      else OPEN_DIRS.add(dirId);
      renderList();
    }};

    window.expandAllDirs = function(openAll) {{
      if (!openAll) {{
        OPEN_DIRS = new Set();
      }} else {{
        (SNAP.context_roots || []).forEach((cr) => OPEN_DIRS.add(cr.root_id));
        (SNAP.nodes || []).forEach((n) => {{
          const parts = String(n.path || '').split('/').filter(Boolean);
          let cur = '';
          const limit = n.node_type === 'dir' ? parts.length : parts.length - 1;
          for (let i = 0; i < limit; i++) {{
            cur += '/' + parts[i];
            OPEN_DIRS.add(`fs:${{n.context_root || 'root:workspace'}}:${{cur}}`);
          }}
        }});
        document.querySelectorAll('[data-group-id]').forEach((el) => OPEN_DIRS.add(el.getAttribute('data-group-id')));
      }}
      renderList();
    }};

    function renderLeafRow(it) {{
      const d = curDepth();
      const snippet = String(it[d] || it.l2 || it.l1 || '').replace(/\\s+/g, ' ').trim().slice(0, 95);
      const tok = depthTokens(it, d);
      const isAct = ACTIVE && ACTIVE.kind === it.kind && ACTIVE.id === it.id;
      const key = `${{it.kind}}::${{it.id}}`;
      const icon = it.kind === 'node' ? '📄' : (it.kind === 'episode' ? '🗂️' : (it.kind === 'insight' ? '💡' : '⚡'));
      const label = it.kind === 'node' ? (String(it.id).split('/').pop() || it.id) : String(it.title || it.id).slice(0, 56);
      const extraBadge = it.kind === 'node' && it.raw?.saving_l1_pct ? `-${{Math.round(it.raw.saving_l1_pct)}}% L1` : `${{tok}} tok`;
      return `
        <div class="tree-leaf ${{isAct ? 'active' : ''}}" data-item-key="${{esc(key)}}" onclick="selectItem('${{esc(it.kind)}}','${{esc(it.id)}}')">
          <div class="leaf-top">
            <span>${{icon}} <b>${{esc(label)}}</b></span>
            <span style="font-size:0.7rem;color:var(--emerald);white-space:nowrap;">${{esc(extraBadge)}} · ${{d.toUpperCase()}}:${{tok}}t</span>
          </div>
          <div class="leaf-sub">${{esc(snippet)}}</div>
        </div>`;
    }}

    function buildBranchTree(nodeItems, rootKey) {{
      const root = {{ path: '', dirs: {{}}, files: [] }};
      for (const it of nodeItems) {{
        const parts = String(it.id || '').split('/').filter(Boolean);
        if (!parts.length) continue;
        let cur = root;
        let acc = '';
        for (let i = 0; i < parts.length - 1; i++) {{
          acc += '/' + parts[i];
          cur.dirs[parts[i]] = cur.dirs[parts[i]] || {{ name: parts[i], fullPath: acc, dirs: {{}}, files: [] }};
          cur = cur.dirs[parts[i]];
        }}
        if (it.raw?.node_type === 'dir') {{
          acc += '/' + parts[parts.length - 1];
          cur.dirs[parts[parts.length - 1]] = cur.dirs[parts[parts.length - 1]] || {{ name: parts[parts.length - 1], fullPath: acc, dirs: {{}}, files: [] }};
          cur.dirs[parts[parts.length - 1]].selfItem = it;
        }} else {{
          cur.files.push(it);
        }}
      }}
      function countNodes(b) {{
        let n = b.files.length;
        Object.values(b.dirs).forEach((d) => {{ n += countNodes(d); }});
        return n;
      }}
      function renderB(b) {{
        let out = '';
        for (const k of Object.keys(b.dirs).sort()) {{
          const child = b.dirs[k];
          const did = `fs:${{rootKey}}:${{child.fullPath}}`;
          const isOpen = OPEN_DIRS.has(did);
          const cnt = countNodes(child);
          const inspectBtn = child.selfItem ? `<button class="btn btn-sm" onclick="event.stopPropagation(); selectItem('node','${{esc(child.selfItem.id)}}')">ℹ️</button>` : '';
          out += `
            <div data-group-id="${{esc(did)}}">
              <div class="folder-hdr" onclick="toggleDir('${{esc(did)}}', event)">
                <span>${{isOpen ? '📂' : '📁'}} ${{esc(k)}} <span style="color:var(--muted);font-weight:400;">(${{cnt}})</span></span>
                <span style="display:flex;gap:4px;">
                  ${{inspectBtn}}
                  <button class="btn btn-sm btn-emerald" title="Distilla & Scarta Max (L4)" onclick="event.stopPropagation(); queueBulkOp('distill_and_compact','subtree','${{esc(child.fullPath)}}')">🧪</button>
                  <button class="btn btn-sm btn-danger" title="Rimuovi cartella" onclick="event.stopPropagation(); queueBulkOp('delete_subtree','subtree','${{esc(child.fullPath)}}')">🗑️</button>
                </span>
              </div>
              ${{isOpen ? `<div class="tree-children">${{renderB(child)}}</div>` : ''}}
            </div>`;
        }}
        for (const f of b.files) out += renderLeafRow(f);
        return out;
      }}
      return renderB(root);
    }}

    function renderGroupCard(groupId, title, badge, items, mountClass = '', kindForBulk = '', idForBulk = '') {{
      const L = WI18N[WLANG] || WI18N.it;
      const isOpen = OPEN_DIRS.has(groupId);
      const bulkBtns = kindForBulk ? `
        <span style="display:flex;gap:4px;" onclick="event.stopPropagation();">
          <button class="btn btn-sm btn-emerald" onclick="queueBulkOp('distill_and_compact','${{esc(kindForBulk)}}','${{esc(idForBulk)}}')">🧪</button>
          <button class="btn btn-sm btn-danger" onclick="queueBulkOp('delete_related_group','${{esc(kindForBulk)}}','${{esc(idForBulk)}}')">🗑️</button>
        </span>` : '';
      return `
        <div class="ctx-mount ${{mountClass}}" data-group-id="${{esc(groupId)}}">
          <div class="folder-hdr" onclick="toggleDir('${{esc(groupId)}}', event)">
            <span>${{isOpen ? '▾' : '▸'}} ${{esc(title)}} <span class="tag">${{items.length}}</span></span>
            ${{bulkBtns}}
          </div>
          ${{badge ? `<div style="font-size:0.73rem;color:var(--muted);margin:2px 0 6px 6px;">${{badge}}</div>` : ''}}
          ${{isOpen ? `<div>${{items.map(renderLeafRow).join('')}}</div>` : ''}}
        </div>`;
    }}

    function renderList() {{
      const L = WI18N[WLANG] || WI18N.it;
      const qRaw = (document.getElementById('q').value || '').trim().toLowerCase();
      const qTerms = normTokens(qRaw);
      const kind = document.getElementById('kind').value || 'all';
      const viewMode = document.getElementById('view-mode').value || 'filesystem';
      const listEl = document.getElementById('list');

      const scoped = ITEMS.filter((it) => kind === 'all' || it.kind === kind);
      if (qRaw) {{
        const scored = scoped.map((it) => {{
          const hay = `${{it.title}} ${{it.sub}} ${{it.topic}} ${{it.l1}} ${{it.l2}} ${{it.l3}}`.toLowerCase();
          let sc = hay.includes(qRaw) ? 6 : 0;
          for (const t of qTerms) if (hay.includes(t)) sc += 2;
          return {{ it, sc }};
        }}).filter((x) => x.sc > 0).sort((a, b) => b.sc - a.sc).slice(0, 120);
        listEl.innerHTML = scored.map((x) => renderLeafRow(x.it)).join('') || `<div style="color:var(--muted);">No results.</div>`;
        if (!ACTIVE && scored.length) ACTIVE = scored[0].it;
        renderDetail();
        return;
      }}

      let html = '';
      if (viewMode === 'filesystem') {{
        const nodeItems = scoped.filter((it) => it.kind === 'node');
        const memItems = scoped.filter((it) => it.kind !== 'node');
        const roots = SNAP.context_roots || [{{ root_id:'root:workspace', title_it:'📁 Workspace', title_en:'📁 Workspace', mount_path:'/', correlated_tasks:[] }}];
        for (const cr of roots) {{
          const rNodes = nodeItems.filter((n) => n.context_root === cr.root_id);
          if (!rNodes.length) continue;
          const isPriv = Boolean(cr.is_private || cr.root_id === 'root:private_notes');
          const isOpen = OPEN_DIRS.has(cr.root_id);
          const title = WLANG === 'en' ? cr.title_en : cr.title_it;
          const corrText = (cr.correlated_tasks || []).length
            ? `<div style="margin:4px 0 6px;">${{(cr.correlated_tasks || []).slice(0, 5).map((t) => `<span class="corr-pill">🔗 ${{esc(t)}}</span>`).join('')}} <span style="font-size:0.71rem;color:var(--muted);">(${{cr.correlated_tasks.length}} ${{L.sharedBy}})</span></div>`
            : '';
          html += `
            <div class="ctx-mount ${{isPriv ? 'private' : 'workspace'}}" data-group-id="${{esc(cr.root_id)}}">
              <div class="folder-hdr" style="color:${{isPriv ? 'var(--amber)' : 'var(--accent)'}};" onclick="toggleDir('${{esc(cr.root_id)}}', event)">
                <span>${{isOpen ? '▾' : '▸'}} ${{esc(title)}} <span class="tag">${{rNodes.length}}</span></span>
                <span style="display:flex;gap:4px;" onclick="event.stopPropagation();">
                  <button class="btn btn-sm btn-emerald" title="${{L.distillBtn}}" onclick="queueBulkOp('distill_and_compact','context_root','${{esc(cr.root_id)}}')">🧪</button>
                  <button class="btn btn-sm btn-danger" title="${{L.delGroupBtn}}" onclick="queueBulkOp('delete_related_group','context_root','${{esc(cr.root_id)}}')">🗑️</button>
                </span>
              </div>
              <div style="font-size:0.72rem;color:var(--muted);padding:0 6px;"><code>${{esc(cr.mount_path)}}</code> · ${{esc(cr.privacy_level)}}</div>
              ${{corrText}}
              ${{isOpen ? buildBranchTree(rNodes, cr.root_id) : ''}}
            </div>`;
        }}
        if (memItems.length) {{
          const epIts = memItems.filter((x) => x.kind === 'episode');
          const insIts = memItems.filter((x) => x.kind === 'insight');
          const skIts = memItems.filter((x) => x.kind === 'skill');
          if (skIts.length) html += renderGroupCard('grp:skills', '⚡ Cortical Skill Engine', '', skIts);
          if (insIts.length) html += renderGroupCard('grp:insights', '💡 Conoscenze & Regole Distillate', '', insIts);
          if (epIts.length) html += renderGroupCard('grp:episodes', '🗂️ Episodi & Sintesi 3+1', '', epIts);
        }}
        if (!ACTIVE && scoped.length) ACTIVE = nodeItems[0] || scoped[0];
      }} else if (viewMode === 'task') {{
        const corrs = SNAP.cross_task_correlations || [];
        if (corrs.length) {{
          const cOpen = OPEN_DIRS.has('corr_box');
          html += `<div class="ctx-mount private"><div class="folder-hdr" style="color:var(--emerald);" onclick="toggleDir('corr_box', event)"><span>${{cOpen ? '▾' : '▸'}} ${{L.corrTitle}} (${{corrs.length}})</span></div>${{cOpen ? corrs.map((c) => `<div style="font-size:0.77rem;padding:4px 6px;border-bottom:1px solid var(--border);"><b>${{esc(c.topic)}}</b>: ${{esc(c.summary)}}</div>`).join('') : ''}}</div>`;
        }}
        for (const ep of (SNAP.episodes || [])) {{
          const relIts = scoped.filter((x) => x.id === ep.episode_id || (x.related_tasks || []).includes(ep.episode_id));
          if (relIts.length) {{
            html += renderGroupCard(`grp:ep:${{ep.episode_id}}`, `${{ep.episode_id}} · ${{String(ep.goal||'').slice(0,42)}}`, `${{ep.topic}} · ${{ep.date_iso}}`, relIts, 'workspace', 'episode', ep.episode_id);
          }}
        }}
        if (!ACTIVE && scoped.length) ACTIVE = scoped[0];
      }} else if (viewMode === 'topic') {{
        const byTop = {{}};
        scoped.forEach((it) => {{ (byTop[it.topic || 'Other'] = byTop[it.topic || 'Other'] || []).push(it); }});
        Object.keys(byTop).sort().forEach((tp) => {{
          html += renderGroupCard(`grp:top:${{tp}}`, tp, '', byTop[tp], 'workspace');
        }});
        if (!ACTIVE && scoped.length) ACTIVE = scoped[0];
      }} else if (viewMode === 'date') {{
        const byDt = {{}};
        scoped.forEach((it) => {{ (byDt[it.date_group || '📅 Storico'] = byDt[it.date_group || '📅 Storico'] || []).push(it); }});
        Object.keys(byDt).sort().reverse().forEach((dg) => {{
          html += renderGroupCard(`grp:dt:${{dg}}`, dg, '', byDt[dg], 'workspace');
        }});
        if (!ACTIVE && scoped.length) ACTIVE = scoped[0];
      }} else if (viewMode === 'savings') {{
        const sorted = [...scoped].sort((a, b) => ((b.raw?.raw_tokens || 0) - (b.raw?.l1_tokens || 0)) - ((a.raw?.raw_tokens || 0) - (a.raw?.l1_tokens || 0)));
        html = sorted.slice(0, 120).map(renderLeafRow).join('');
        if (!ACTIVE && sorted.length) ACTIVE = sorted[0];
      }}

      listEl.innerHTML = html || `<div style="color:var(--muted);">Nessun elemento disponibile.</div>`;
      renderDetail();
    }}

    function renderRichBody(text) {{
      const raw = String(text || '');
      if (raw.trim().startsWith('{{') || raw.trim().startsWith('[')) {{
        return `<pre>${{esc(raw)}}</pre>`;
      }}
      const fmtInline = (s) => esc(s).replace(/`([^`]+)`/g, '<span class="rich-code">$1</span>').replace(/\\*\\*([^*]+)\\*\\*/g, '<b>$1</b>');
      let out = '<div class="rich-box">';
      for (const ln of raw.split(/\\r?\\n/)) {{
        const t = ln.trim();
        if (!t) continue;
        if (/^===.*===$/.test(t) || /^#{{1,3}}\\s+/.test(t)) out += `<div class="rich-h">${{fmtInline(t.replace(/^===\\s*|\\s*===$|^#{{1,3}}\\s+/g, ''))}}</div>`;
        else if (t.startsWith('>') || /^(Nota|Note|Lezione|Regola|Key Summary|Obiettivo):/i.test(t)) out += `<div class="rich-note">${{fmtInline(t.replace(/^>\\s*/, ''))}}</div>`;
        else if (t.startsWith('- ') || t.startsWith('* ')) out += `<div style="padding-left:12px;">• ${{fmtInline(t.slice(2))}}</div>`;
        else out += `<div class="rich-kv">${{fmtInline(t)}}</div>`;
      }}
      return out + '</div>';
    }}

    function selectItem(kind, id) {{
      ACTIVE = ITEMS.find((x) => x.kind === kind && x.id === id) || null;
      const targetKey = `${{kind}}::${{id}}`;
      document.querySelectorAll('[data-item-key]').forEach((el) => {{
        el.classList.toggle('active', el.getAttribute('data-item-key') === targetKey);
      }});
      renderDetail();
    }}

    function renderDetail() {{
      const L = WI18N[WLANG] || WI18N.it;
      const box = document.getElementById('detail');
      if (!ACTIVE) {{
        box.innerHTML = `<div style="color:var(--muted);">${{L.pickPrompt}}</div>`;
        return;
      }}
      const d = curDepth();
      const body = ACTIVE[d] || ACTIVE.l2 || ACTIVE.l1 || '';
      const tierBar = ['l1','l2','l3','l4'].map((t) => {{
        const tok = depthTokens(ACTIVE, t);
        const cls = t === d ? 'tier-pill active-tier' : 'tier-pill';
        const lbl = t === 'l1' ? 'L1 Light' : (t === 'l2' ? 'L2 Medium' : (t === 'l3' ? 'L3 High' : 'L4 Max'));
        return `<button class="${{cls}}" onclick="setDepthDirect('${{t}}')"><b>${{lbl}}:</b> ${{fmt(tok)}} tok</button>`;
      }}).join('');

      let pctBar = '';
      if (ACTIVE.kind === 'node' && ACTIVE.raw) {{
        const r = ACTIVE.raw;
        const rawT = Math.max(1, Number(r.raw_tokens || 1));
        const p1 = Math.max(3, Math.min(100, Math.round((Number(r.l1_tokens||0) / rawT) * 100)));
        const p2 = Math.max(3, Math.min(100, Math.round((Number(r.l2_tokens||0) / rawT) * 100)));
        const p3 = Math.max(3, Math.min(100, Math.round((Number(r.l3_tokens||0) / rawT) * 100)));
        pctBar = `<div class="tier-bar"><div style="width:${{p1}}%;background:var(--emerald);"></div><div style="width:${{Math.max(0,p2-p1)}}%;background:var(--accent);"></div><div style="width:${{Math.max(0,p3-p2)}}%;background:var(--amber);"></div></div>`;
      }}

      const links = (SNAP.edges || []).filter((e) => e.source_id === ACTIVE.id || e.target_id === ACTIVE.id).slice(0, 10);
      const srcEp = ACTIVE.kind === 'skill' && ACTIVE.raw?.source_episode_id && !['consolidated','knowledge_consolidated'].includes(ACTIVE.raw.source_episode_id) ? ACTIVE.raw.source_episode_id : '';
      const linksHtml = (links.length || srcEp) ? `
        <div class="tier-box" style="margin-top:10px;">
          <div style="font-weight:700; color:var(--accent); margin-bottom:6px;">🕸️ ${{L.linksTitle}}</div>
          ${{srcEp ? `<button class="btn btn-sm" style="margin-bottom:6px;" onclick="selectItem('episode','${{esc(srcEp)}}')">${{L.openSrc}}: <code>${{esc(srcEp)}}</code></button>` : ''}}
          ${{links.map((e) => `<div><code>${{esc(e.source_id)}}</code> —[${{esc(e.relation)}}]→ <code>${{esc(e.target_id)}}</code></div>`).join('')}}
        </div>` : '';

      const canEdit = ['insight', 'node', 'episode', 'skill'].includes(ACTIVE.kind);
      const distillKind = ACTIVE.kind === 'node' && ACTIVE.raw?.node_type === 'dir' ? 'subtree' : (ACTIVE.kind === 'episode' ? 'episode' : 'subtree');
      box.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; margin-bottom:10px; flex-wrap:wrap;">
          <div><span class="tag">${{esc(ACTIVE.kind)}}</span><span class="tag">${{esc(ACTIVE.topic || '')}}</span><code>${{esc(ACTIVE.id)}}</code></div>
          <span style="font-size:0.78rem; color:var(--muted);">${{esc(ACTIVE.context_root)}} · ${{esc(ACTIVE.sub)}}</span>
        </div>
        <div class="tier-box">
          <div style="font-weight:700; color:var(--emerald); margin-bottom:6px;">⚡ ${{L.compTitle}}</div>
          <div class="tier-pills">${{tierBar}}</div>
          ${{pctBar}}
        </div>
        ${{renderRichBody(body)}}
        ${{linksHtml}}
        ${{canEdit ? `
          <div style="margin-top:14px; border-top:1px solid var(--border); padding-top:12px;">
            <div style="font-size:0.78rem; font-weight:700; color:var(--muted); margin-bottom:6px;">${{L.maintTitle}}</div>
            <textarea id="edit-txt">${{esc(ACTIVE.l2 || ACTIVE.title)}}</textarea>
            <div style="display:flex; gap:8px; flex-wrap:wrap; margin-top:8px;">
              <button class="btn btn-primary" onclick="queueOp('update')">${{L.saveOp}}</button>
              <button class="btn btn-emerald" onclick="queueBulkOp('distill_and_compact','${{esc(distillKind)}}','${{esc(ACTIVE.id)}}')">${{L.distillBtn}}</button>
              <button class="btn btn-danger" onclick="queueOp('delete')">${{L.delOp}}</button>
            </div>
          </div>` : ''}}
      `;
    }}

    function showToast(msg) {{
      const el = document.getElementById('action-toast');
      const m = document.getElementById('toast-msg');
      if (el && m) {{
        m.textContent = msg;
        el.classList.add('show');
      }}
    }}

    function pushUndoSnapshot() {{
      HISTORY_STACK.push({{
        items: JSON.parse(JSON.stringify(ITEMS)),
        counts: JSON.parse(JSON.stringify(SNAP.counts || {{}})),
        patch: JSON.parse(JSON.stringify(PATCH)),
        activeKey: ACTIVE ? `${{ACTIVE.kind}}::${{ACTIVE.id}}` : null,
      }});
      if (HISTORY_STACK.length > 25) HISTORY_STACK.shift();
      const undoBtn = document.getElementById('btn-undo');
      if (undoBtn) undoBtn.style.display = 'inline-block';
    }}

    window.undoLastOp = function() {{
      if (!HISTORY_STACK.length) return;
      const prev = HISTORY_STACK.pop();
      ITEMS = prev.items;
      SNAP.counts = prev.counts;
      PATCH = prev.patch;
      ACTIVE = prev.activeKey ? (ITEMS.find((x) => `${{x.kind}}::${{x.id}}` === prev.activeKey) || ITEMS[0] || null) : (ITEMS[0] || null);
      if (!HISTORY_STACK.length) {{
        const undoBtn = document.getElementById('btn-undo');
        if (undoBtn) undoBtn.style.display = 'none';
      }}
      savePatch();
      renderKpis();
      renderList();
      showToast('↩️ Ultima azione annullata!');
    }};

    function syncCountsFromItems() {{
      SNAP.counts = SNAP.counts || {{}};
      SNAP.counts.nodes = ITEMS.filter((x) => x.kind === 'node').length;
      SNAP.counts.episodes = ITEMS.filter((x) => x.kind === 'episode').length;
      SNAP.counts.insights = ITEMS.filter((x) => x.kind === 'insight').length;
      SNAP.counts.skills = ITEMS.filter((x) => x.kind === 'skill').length;
      renderKpis();
    }}

    function savePatch() {{
      const L = WI18N[WLANG] || WI18N.it;
      localStorage.setItem(STORAGE_KEY, JSON.stringify(PATCH));
      const el = document.getElementById('patch-count');
      if (el) el.textContent = `${{PATCH.operations.length}} ${{L.queued}}`;
    }}

    window.queueOp = function(action) {{
      if (!ACTIVE) return;
      const L = WI18N[WLANG] || WI18N.it;
      pushUndoSnapshot();
      const opName = `${{action}}_${{ACTIVE.kind}}`;
      const txt = (document.getElementById('edit-txt')?.value || '').trim();
      PATCH.operations.push({{ op: opName, id: ACTIVE.id, text: txt, ts: Date.now() }});
      if (action === 'update') {{
        ACTIVE.l2 = txt;
        ACTIVE.l1 = txt.slice(0, 140);
        if (ACTIVE.kind === 'insight' || ACTIVE.kind === 'episode') ACTIVE.title = txt;
        savePatch();
        renderList();
        showToast(L.savedMsg);
      }} else if (action === 'delete') {{
        const rmId = ACTIVE.id;
        const rmKind = ACTIVE.kind;
        ITEMS = ITEMS.filter((x) => !(x.kind === rmKind && x.id === rmId));
        ACTIVE = ITEMS[0] || null;
        savePatch();
        syncCountsFromItems();
        renderList();
        showToast(`${{L.deletedMsg}} (${{rmId}})`);
      }}
    }};

    window.queueBulkOp = function(opName, kind, id) {{
      const L = WI18N[WLANG] || WI18N.it;
      pushUndoSnapshot();
      const tier = curDepth();
      PATCH.operations.push({{ op: opName, kind: kind, id: id, keep_tier: tier, ts: Date.now() }});
      const matchesTarget = (it) => {{
        if (kind === 'subtree') return it.kind === 'node' && (it.id === id || it.id.startsWith(id.replace(/\\/+$/, '') + '/'));
        if (kind === 'context_root') return it.context_root === id;
        if (kind === 'episode') return (it.kind === 'episode' && it.id === id) || (it.related_tasks || []).includes(id);
        return false;
      }};
      if (opName === 'delete_subtree' || opName === 'delete_related_group') {{
        const before = ITEMS.length;
        ITEMS = ITEMS.filter((x) => !matchesTarget(x));
        if (ACTIVE && !ITEMS.includes(ACTIVE)) ACTIVE = ITEMS[0] || null;
        syncCountsFromItems();
        savePatch();
        renderList();
        showToast(`${{L.deletedMsg}} (${{before - ITEMS.length}} elementi rimossi)`);
      }} else if (opName === 'distill_and_compact') {{
        let cnt = 0;
        const snippets = [];
        ITEMS.forEach((it) => {{
          if (matchesTarget(it)) {{
            cnt++;
            snippets.push(`${{it.title}}: ${{String(it[tier] || it.l2 || it.l1 || '').slice(0, 120)}}`);
            it.l4 = `[COMPATTATO AL LIVELLO ${{tier.toUpperCase()}}: L4 Max scartato dopo distillazione]`;
            if (it.raw) it.raw.raw_tokens = it.raw.l2_tokens || it.raw.l1_tokens || 120;
          }}
        }});
        const insId = 'ins-dist-' + Math.random().toString(36).slice(2, 8);
        const insText = `Conoscenza distillata (${{kind}}:${{id}} · ${{tier.toUpperCase()}}): ` + snippets.slice(0, 3).join(' | ');
        ITEMS.unshift({{
          kind: 'insight',
          id: insId,
          title: insText,
          sub: 'knowledge_distillation',
          context_root: 'root:workspace',
          topic: '🌳 Wiki & Compressione Contesto',
          date_group: '📅 Oggi',
          related_tasks: [],
          l1: insText.slice(0, 135),
          l2: insText,
          l3: insText,
          l4: JSON.stringify({{ insight_id: insId, source: id, compacted_items: cnt }}, null, 2),
          raw: {{ insight_id: insId }},
        }});
        syncCountsFromItems();
        savePatch();
        renderList();
        showToast(`${{L.distilledMsg}} (${{cnt}} nodi compattati → ${{insId}})`);
      }} else {{
        savePatch();
        renderList();
      }}
    }};

    function sanitizeClientText(raw, prof) {{
      if (prof === 'max_context') return raw;
      const rep = (prof === 'max_security' || prof === 'low') ? '[REDACTED]' : null;
      let idx = 0;
      const sub = (lbl) => rep || `[${{lbl}}_${{++idx}}]`;
      let out = String(raw || '');
      out = out.replace(/\\b(?:sk-[A-Za-z0-9_-]{{16,}}|ghp_[A-Za-z0-9]{{20,}}|AKIA[0-9A-Z]{{16}})\\b/g, () => sub('SECRET'));
      out = out.replace(/\\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{{2,}}\\b/g, () => sub('EMAIL'));
      out = out.replace(/\\b[A-Z]{{2}}\\d{{2}}[A-Z0-9]{{11,30}}\\b/g, () => sub('IBAN'));
      out = out.replace(/\\b[A-Z]{{6}}\\d{{2}}[A-Z]\\d{{2}}[A-Z]\\d{{3}}[A-Z]\\b/g, () => sub('TAX_ID'));
      out = out.replace(/(?:\\+?\\d{{1,3}}[\\s.-]?)?(?:\\(?\\d{{2,4}}\\)?[\\s.-]?)\\d{{3,4}}[\\s.-]?\\d{{3,4}}/g, () => sub('PHONE'));
      return out;
    }}

    window.handlePickedFiles = async function(fileList, isFolder) {{
      if (!fileList || !fileList.length) return;
      pushUndoSnapshot();
      const prof = document.getElementById('vault-privacy')?.value || 'low';
      const files = Array.from(fileList).slice(0, 60);
      let added = 0;
      for (const f of files) {{
        const rel = f.webkitRelativePath || f.name;
        const lower = rel.toLowerCase();
        if (!/\\.(md|txt|py|json|ts|js|yaml|yml|toml|sql|sh|csv|rst)$/i.test(lower)) continue;
        const raw = await f.text();
        const san = sanitizeClientText(raw, prof);
        const wpath = '/private_notes/' + rel.replace(/^\\/+/, '');
        const l1 = `[RISERVATO · ${{prof.toUpperCase()}}] ${{f.name}} — ` + san.replace(/\\s+/g, ' ').slice(0, 140);
        const l2 = san.slice(0, 900);
        const l3 = san.slice(0, 2800);
        const tokRaw = Math.max(1, Math.round(raw.length / 4));
        const tokL1 = Math.max(1, Math.round(l1.length / 4));
        ITEMS.unshift({{
          kind: 'node', id: wpath, title: wpath, sub: 'file',
          context_root: 'root:private_notes', privacy_profile: prof,
          topic: '🛡️ Privacy & Sanitizer GDPR', date_group: '📅 Oggi', related_tasks: [],
          l1: l1, l2: l2, l3: l3, l4: prof === 'max_security' ? '[BLOCCATO IN LOCALE · MAX_SECURITY]' : san.slice(0, 4000),
          raw: {{ path: wpath, node_type: 'file', l1_tokens: tokL1, l2_tokens: Math.max(1, Math.round(l2.length/4)), l3_tokens: Math.max(1, Math.round(l3.length/4)), raw_tokens: tokRaw, saving_l1_pct: Math.round(((tokRaw - tokL1)/tokRaw)*100) }},
        }});
        SNAP.aliases = SNAP.aliases || [];
        SNAP.aliases.unshift({{ alias: f.name, kind: 'node', ref: wpath, privacy: prof, label: wpath }});
        PATCH.operations.push({{
          op: 'attach_private_item', path: wpath, privacy_profile: prof,
          summary_light: l1, summary_medium: l2, summary_high: l3,
          raw_content: prof === 'max_security' ? '' : san.slice(0, 12000),
          ts: Date.now(),
        }});
        added++;
      }}
      OPEN_DIRS.add('root:private_notes');
      syncCountsFromItems();
      savePatch();
      renderList();
      renderRefAutocomplete();
      const firstName = files[0].webkitRelativePath ? files[0].webkitRelativePath.split('/')[0] : files[0].name;
      showToast(`🔒 ${{added}} file caricati localmente con profilo '${{prof}}'. Usa in chat/CLI: @private:${{firstName}}:${{prof}}`);
    }};

    window.copyRefToken = function(txt) {{
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(txt);
      showToast(`📋 Copiato negli appunti: ${{txt}}`);
    }};

    window.renderRefAutocomplete = function() {{
      const inp = document.getElementById('ref-auto-input');
      const box = document.getElementById('ref-auto-list');
      if (!inp || !box) return;
      const q = (inp.value || '').trim().toLowerCase();
      const pool = SNAP.aliases || [];
      const matches = (q ? pool.filter((a) => (a.alias + ' ' + a.label + ' ' + a.ref).toLowerCase().includes(q)) : pool).slice(0, 10);
      if (!matches.length) {{
        box.classList.remove('show');
        return;
      }}
      box.classList.add('show');
      box.innerHTML = matches.map((a) => {{
        const prof = a.privacy && a.privacy !== 'workspace_code' ? a.privacy : 'low';
        const atTok = a.kind === 'skill' ? `@skill:${{a.alias}}` : `@private:${{a.alias}}:${{prof}}`;
        const slashTok = `/private ${{a.alias}}`;
        return `<div class="auto-row">
          <span><b>${{esc(a.alias)}}</b> <span class="tag">${{esc(prof)}}</span> <span style="color:var(--muted);">${{esc(a.label)}}</span></span>
          <span style="display:flex;gap:5px;white-space:nowrap;">
            <button class="btn btn-sm btn-primary" onclick="copyRefToken('${{esc(atTok)}}')">📋 ${{esc(atTok)}}</button>
            <button class="btn btn-sm" onclick="copyRefToken('${{esc(slashTok)}}')">📋 ${{esc(slashTok)}}</button>
          </span>
        </div>`;
      }}).join('');
    }};

    window.exportPatch = async function() {{
      const payload = JSON.stringify(PATCH, null, 2) + '\\n';
      if (window.showSaveFilePicker) {{
        try {{
          const handle = await window.showSaveFilePicker({{
            suggestedName: 'wiki_maintenance_patch.json',
            types: [{{ description: 'JSON Patch', accept: {{ 'application/json': ['.json'] }} }}],
          }});
          const w = await handle.createWritable();
          await w.write(payload);
          await w.close();
          showToast('💾 File wiki_maintenance_patch.json salvato su disco! Cortical lo applicherà automaticamente al DB.');
          return;
        }} catch (e) {{
          if (e.name === 'AbortError') return;
        }}
      }}
      const blob = new Blob([payload], {{ type: 'application/json' }});
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'wiki_maintenance_patch.json';
      a.click();
      showToast('⬇️ Patch salvata nei Download! Spostala nella root del repo oppure esegui wiki-apply per applicarla al DB.');
    }};

    window.clearPatch = function() {{ PATCH = {{ operations: [] }}; HISTORY_STACK = []; savePatch(); showToast('🧹 Coda operazioni ripulita.'); }};

    window.toggleWikiLang = function() {{
      WLANG = WLANG === 'it' ? 'en' : 'it';
      localStorage.setItem('cortical_lang', WLANG);
      syncChromeLang();
      renderList();
    }};

    syncChromeLang();
    renderList();
  </script>
</body>
</html>
"""


def export_static_wiki_dashboard(
    wiki_db: CorticalWikiDB,
    output_path: Path,
    ctx: Optional[AccessContext] = None,
) -> dict[str, Any]:
    """Exports the self-contained static Wiki Dashboard HTML to `output_path`."""
    snap = collect_wiki_snapshot(wiki_db, ctx=ctx)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_static_wiki_dashboard_html(snap), encoding="utf-8")
    return {"output_path": str(out), "counts": snap["counts"]}
