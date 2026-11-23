"""Zero-Server Static Wiki & Sanitization Audit Dashboard Generator (`wiki.html`)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

from ..wiki.store import KnowledgeStore
from ..workspace import resolve_default_db


def collect_wiki_dashboard_payload(
    db_path: Path | str,
    *,
    principal_id: str = "local_owner",
    max_inspect: int = 250,
) -> dict[str, Any]:
    """Collects bounded, sanitized-safe knowledge explorer & privacy audit data from `wiki.db`."""
    store = KnowledgeStore(db_path)
    roots = store.list_roots(principal_id=principal_id)
    nav = store.navigate(principal_id=principal_id)
    files_out: list[dict[str, Any]] = []
    for f in nav["files"][:max_inspect]:
        entry = dict(f)
        insp = store.inspect_file(f["doc_id"], principal_id=principal_id)
        if insp:
            entry["summaries"] = insp.get("summaries") or {}
            entry["chunks_meta"] = [
                {
                    "chunk_index": c.get("chunk_index"),
                    "char_start": c.get("char_start"),
                    "char_end": c.get("char_end"),
                    "token_est": c.get("token_est"),
                }
                for c in (insp.get("chunks") or [])
            ]
        else:
            entry["summaries"] = {}
            entry["chunks_meta"] = []
        entry.pop("abs_path", None)
        files_out.append(entry)

    # Compute per-folder privacy aggregation for the Merkle audit panel
    folders: dict[str, dict[str, Any]] = {}
    for f in files_out:
        rel = str(f.get("rel_path") or "")
        folder = rel.rsplit("/", 1)[0] if "/" in rel else "."
        agg = folders.setdefault(folder, {
            "folder": folder,
            "total": 0,
            "sanitized": 0,
            "raw": 0,
            "private_gated": 0,
            "entities_masked": 0,
            "metadata_stripped": 0,
        })
        agg["total"] += 1
        if f.get("sanitized"):
            agg["sanitized"] += 1
        else:
            agg["raw"] += 1
        if f.get("private_gated"):
            agg["private_gated"] += 1
        agg["entities_masked"] += int(f.get("entities_masked") or 0)
        agg["metadata_stripped"] += len(f.get("stripped_meta") or [])

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "db_path": str(Path(db_path)),
        "principal_id": principal_id,
        "roots": roots,
        "counts": nav["counts"],
        "privacy_summary": nav.get("privacy_summary") or {},
        "folders": sorted(folders.values(), key=lambda x: x["folder"]),
        "files": files_out,
    }


def render_wiki_dashboard_html(payload: dict[str, Any]) -> str:
    """Renders self-contained zero-CDN static `wiki.html` Explorer & Privacy Audit dashboard."""
    data_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Cortical Wiki Explorer &amp; Privacy Audit</title>
  <style>
    :root {{
      --bg:#070b14; --panel:#0e1526; --card:#131d33; --border:#253350; --text:#e2e8f0;
      --muted:#94a3b8; --accent:#38bdf8; --ok:#34d399; --warn:#fbbf24; --err:#f87171; --priv:#c084fc;
      --mono:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;
    }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; background:var(--bg); color:var(--text); font-size:14px; line-height:1.5; }}
    .wrap {{ max-width:1280px; margin:0 auto; padding:20px 18px 64px; }}
    .topbar {{ display:flex; justify-content:space-between; align-items:center; gap:12px; flex-wrap:wrap; margin-bottom:18px; padding-bottom:14px; border-bottom:1px solid var(--border); }}
    .brand {{ font-size:19px; font-weight:800; display:flex; align-items:center; gap:10px; }}
    .sub {{ color:var(--muted); font-size:12px; }}
    .grid-4 {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:12px; margin-bottom:16px; }}
    .kpi {{ background:var(--panel); border:1px solid var(--border); border-radius:12px; padding:14px 16px; }}
    .kpi-lbl {{ color:var(--muted); font-size:12px; font-weight:600; }}
    .kpi-val {{ font-size:24px; font-weight:800; margin-top:4px; }}
    .card {{ background:var(--panel); border:1px solid var(--border); border-radius:12px; padding:16px; margin-bottom:16px; }}
    .card-head {{ display:flex; justify-content:space-between; align-items:center; gap:10px; flex-wrap:wrap; margin-bottom:12px; }}
    .card-head h2 {{ margin:0; font-size:15px; }}
    .pill {{ display:inline-flex; align-items:center; gap:4px; padding:2px 9px; border-radius:999px; font-size:11px; font-weight:700; border:1px solid transparent; }}
    .pill.san {{ background:rgba(52,211,153,0.14); color:var(--ok); border-color:rgba(52,211,153,0.4); }}
    .pill.raw {{ background:rgba(251,191,36,0.14); color:var(--warn); border-color:rgba(251,191,36,0.4); }}
    .pill.gated {{ background:rgba(192,132,252,0.16); color:var(--priv); border-color:rgba(192,132,252,0.45); }}
    .pill.info {{ background:rgba(56,189,248,0.14); color:var(--accent); border-color:rgba(56,189,248,0.4); }}
    .btn {{ border:1px solid var(--border); background:var(--card); color:var(--text); padding:7px 12px; border-radius:8px; cursor:pointer; font-weight:600; font-size:12px; }}
    .btn:hover {{ border-color:var(--accent); }}
    .btn.primary {{ background:var(--accent); color:#071324; border-color:var(--accent); }}
    .btn.active {{ background:rgba(56,189,248,0.2); border-color:var(--accent); color:var(--accent); }}
    .input,.select {{ background:#060a13; color:var(--text); border:1px solid var(--border); border-radius:8px; padding:8px 10px; font-size:13px; }}
    .mono {{ font-family:var(--mono); font-size:12px; }}
    table {{ width:100%; border-collapse:collapse; }}
    th,td {{ text-align:left; padding:9px 8px; border-bottom:1px solid var(--border); }}
    th {{ color:var(--muted); font-size:12px; }}
    tr.row {{ cursor:pointer; }}
    tr.row:hover {{ background:rgba(56,189,248,0.06); }}
    .split {{ display:grid; grid-template-columns:1.25fr 1fr; gap:16px; align-items:start; }}
    @media (max-width:960px) {{ .split {{ grid-template-columns:1fr; }} }}
    .tabs {{ display:flex; gap:6px; flex-wrap:wrap; margin-bottom:10px; }}
    pre.preview {{ background:#050912; border:1px solid var(--border); border-radius:10px; padding:12px; white-space:pre-wrap; word-break:break-word; max-height:420px; overflow:auto; font-family:var(--mono); font-size:12px; line-height:1.55; }}
    mark.pii-tok {{ background:rgba(52,211,153,0.22); color:#6ee7b7; border:1px solid rgba(52,211,153,0.5); padding:1px 4px; border-radius:4px; font-weight:700; }}
    .backdrop {{ position:fixed; inset:0; background:rgba(3,7,18,0.78); display:flex; align-items:center; justify-content:center; padding:16px; z-index:50; }}
    .modal {{ background:var(--panel); border:1px solid var(--border); border-radius:14px; max-width:680px; width:100%; padding:18px; box-shadow:0 20px 60px rgba(0,0,0,0.55); }}
    .grid-2 {{ display:grid; grid-template-columns:1fr 1fr; gap:10px; }}
    @media (max-width:640px) {{ .grid-2 {{ grid-template-columns:1fr; }} }}
    .toast {{ position:fixed; bottom:18px; right:18px; background:var(--card); border:1px solid var(--ok); color:var(--ok); padding:9px 14px; border-radius:9px; font-weight:600; z-index:90; display:none; }}
  </style>
</head>
<body>
  <div class="wrap">
    <header class="topbar">
      <div>
        <div class="brand">🧠 Cortical Wiki Explorer &amp; Sanitization Audit</div>
        <div class="sub">Zero-Server Offline Audit · Principal: <span class="mono" id="hdr-principal"></span> · Snapshot: <span class="mono" id="hdr-time"></span></div>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;">
        <button class="btn primary" onclick="openCmdBuilder()">⚡ Re-index &amp; Sanitize Command Builder</button>
      </div>
    </header>

    <section class="grid-4" id="kpi-grid"></section>

    <section class="card" id="audit-panel"></section>

    <section class="split">
      <div class="card">
        <div class="card-head">
          <h2>📂 Merkle Tree &amp; Privacy Explorer</h2>
          <div style="display:flex;gap:6px;flex-wrap:wrap;" id="priv-filters"></div>
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px;">
          <input id="q-search" class="input" style="flex:1;min-width:190px;" placeholder="Filter folder or file path..." oninput="ST.query=this.value;renderFiles()" />
          <select id="q-folder" class="select" onchange="ST.folder=this.value;renderFiles()">
            <option value="">All Folders</option>
          </select>
        </div>
        <div style="overflow-x:auto;">
          <table>
            <thead><tr><th>Path</th><th>Privacy Badge</th><th>PII Masked</th><th>Merkle</th></tr></thead>
            <tbody id="files-tbody"></tbody>
          </table>
        </div>
      </div>

      <div class="card" id="inspector-card">
        <div class="card-head">
          <h2>🔍 4-Tier Sanitized Summary Inspector</h2>
          <span class="sub" id="sel-meta">Select a file row</span>
        </div>
        <div class="tabs" id="tier-tabs"></div>
        <pre class="preview" id="tier-preview">Click any file in the Merkle explorer to verify zero raw PII and inspect light → medium → high → max summaries.</pre>
      </div>
    </section>
  </div>

  <div id="modal-root"></div>
  <div id="toast" class="toast"></div>

  <script>
  const DATA = {data_json};
  const ST = {{
    privacyFilter: 'all',
    query: '',
    folder: '',
    selectedDocId: (DATA.files && DATA.files[0]) ? DATA.files[0].doc_id : null,
    tier: 'light',
    cmdFolder: (DATA.roots && DATA.roots[0]) ? DATA.roots[0].path : '~/Dropbox',
    cmdProfile: 'medium',
    cmdTerms: '',
    cmdDryRun: true,
    cmdFull: false,
  }};

  function esc(s) {{
    return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }}
  function highlightPseudonyms(raw) {{
    const safe = esc(raw || '(empty)');
    return safe.replace(/(\\[(?:PERSON|PERSON_NAME|EMAIL|IBAN|TAX_ID|SECRET|PHONE|IP|CUSTOM|ORG|METADATA)_\\d+\\]|\\[REDACTED\\])/g,
      '<mark class="pii-tok">$1</mark>');
  }}
  function toast(msg) {{
    const t = document.getElementById('toast');
    t.textContent = msg; t.style.display = 'block';
    setTimeout(() => {{ t.style.display = 'none'; }}, 2400);
  }}
  function privacyBadge(f) {{
    const out = [];
    if (f.private_gated) out.push('<span class="pill gated">🔒 PRIVATE-GATED</span>');
    else if (f.sanitized) out.push('<span class="pill san">🛡 SANITIZED</span>');
    else out.push('<span class="pill raw">⚠ RAW</span>');
    if (f.privacy_profile && f.privacy_profile !== 'raw') out.push(`<span class="pill info">${{esc(f.privacy_profile)}}</span>`);
    return out.join(' ');
  }}

  function renderTop() {{
    document.getElementById('hdr-principal').textContent = DATA.principal_id || 'local_owner';
    document.getElementById('hdr-time').textContent = DATA.generated_at || '';
    const ps = DATA.privacy_summary || {{}};
    const total = (DATA.files || []).length;
    document.getElementById('kpi-grid').innerHTML = `
      <div class="kpi"><div class="kpi-lbl">Indexed &amp; Tracked Nodes</div><div class="kpi-val">${{total}}</div><div class="sub">${{(DATA.roots||[]).length}} root(s)</div></div>
      <div class="kpi"><div class="kpi-lbl">Sanitized vs Raw</div><div class="kpi-val" style="color:var(--ok);">${{ps.sanitized || 0}} <span style="font-size:14px;color:var(--muted);">/ ${{ps.raw || 0}} raw</span></div><div class="sub">${{ps.private_gated || 0}} private-gated (max_security)</div></div>
      <div class="kpi"><div class="kpi-lbl">PII Entities Masked</div><div class="kpi-val" style="color:var(--accent);">${{ps.entities_masked_total || 0}}</div><div class="sub">Zero raw PII in FTS5 / summaries</div></div>
      <div class="kpi"><div class="kpi-lbl">Merkle Delta Sync</div><div class="kpi-val">${{DATA.counts?.indexed || 0}}</div><div class="sub">${{DATA.counts?.ignored || 0}} ignored · ${{DATA.counts?.error || 0}} errors</div></div>
    `;

    const cats = ps.entities_by_category || {{}};
    const catHtml = Object.keys(cats).length
      ? Object.entries(cats).map(([k,v]) => `<span class="pill san">${{esc(k)}}: ${{v}}</span>`).join(' ')
      : '<span class="sub">No masked entities recorded yet.</span>';

    const folderRows = (DATA.folders || []).map((fd) => `
      <tr>
        <td class="mono">${{esc(fd.folder)}}</td>
        <td><span class="pill san">${{fd.sanitized}} sanitized</span> ${{fd.raw ? `<span class="pill raw">${{fd.raw}} raw</span>` : ''}} ${{fd.private_gated ? `<span class="pill gated">${{fd.private_gated}} gated</span>` : ''}}</td>
        <td><strong>${{fd.entities_masked}}</strong> (${{fd.metadata_stripped}} meta stripped)</td>
      </tr>
    `).join('');

    document.getElementById('audit-panel').innerHTML = `
      <div class="card-head">
        <h2>🛡 Sanitization Audit Panel</h2>
        <div style="display:flex;gap:6px;flex-wrap:wrap;">${{catHtml}}</div>
      </div>
      ${{(DATA.folders||[]).length ? `<div style="overflow-x:auto;"><table><thead><tr><th>Folder</th><th>Privacy Coverage</th><th>Entities Redacted</th></tr></thead><tbody>${{folderRows}}</tbody></table></div>` : '<div class="sub">No folders crawled yet. Use the Re-index &amp; Sanitize Command Builder to scan a folder.</div>'}}
    `;

    const sel = document.getElementById('q-folder');
    sel.innerHTML = '<option value="">All Folders</option>' + (DATA.folders || []).map((fd) => `<option value="${{esc(fd.folder)}}">${{esc(fd.folder)}} (${{fd.total}})</option>`).join('');
  }}

  function renderFilters() {{
    const opts = [
      ['all', 'All'],
      ['sanitized', '🛡 Sanitized'],
      ['private_gated', '🔒 Private-Gated'],
      ['raw', '⚠ Raw'],
    ];
    document.getElementById('priv-filters').innerHTML = opts.map(([id, lbl]) => `
      <button class="btn ${{ST.privacyFilter===id?'active':''}}" onclick="ST.privacyFilter='${{id}}';renderFilters();renderFiles()">${{lbl}}</button>
    `).join('');
  }}

  function renderFiles() {{
    const q = ST.query.trim().toLowerCase();
    const filtered = (DATA.files || []).filter((f) => {{
      if (ST.privacyFilter === 'sanitized' && !f.sanitized) return false;
      if (ST.privacyFilter === 'raw' && f.sanitized) return false;
      if (ST.privacyFilter === 'private_gated' && !f.private_gated) return false;
      if (q && !String(f.rel_path || '').toLowerCase().includes(q)) return false;
      if (ST.folder) {{
        const rel = String(f.rel_path || '');
        const fd = rel.includes('/') ? rel.slice(0, rel.lastIndexOf('/')) : '.';
        if (fd !== ST.folder) return false;
      }}
      return true;
    }});
    const tb = document.getElementById('files-tbody');
    if (!filtered.length) {{
      tb.innerHTML = '<tr><td colspan="4" class="sub">No files match the current privacy or path filter.</td></tr>';
      return;
    }}
    tb.innerHTML = filtered.map((f) => `
      <tr class="row" onclick="selectFile('${{esc(f.doc_id)}}')">
        <td class="mono"><strong>${{esc(f.rel_path)}}</strong></td>
        <td>${{privacyBadge(f)}}</td>
        <td>${{f.entities_masked || 0}} ${{(f.stripped_meta||[]).length ? `<span class="sub">(+${{f.stripped_meta.length}} meta)</span>` : ''}}</td>
        <td class="mono sub">${{esc((f.merkle_hash || '').slice(0, 12))}}</td>
      </tr>
    `).join('');
  }}

  function selectFile(docId) {{
    ST.selectedDocId = docId;
    renderInspector();
  }}

  function renderInspector() {{
    const f = (DATA.files || []).find((x) => x.doc_id === ST.selectedDocId);
    const tabs = document.getElementById('tier-tabs');
    const pre = document.getElementById('tier-preview');
    const meta = document.getElementById('sel-meta');
    if (!f) {{
      tabs.innerHTML = ''; meta.textContent = 'Select a file row';
      pre.textContent = 'No document selected.';
      return;
    }}
    meta.innerHTML = `${{esc(f.rel_path)}} · ${{privacyBadge(f)}}`;
    tabs.innerHTML = ['light', 'medium', 'high', 'max'].map((t) => `
      <button class="btn ${{ST.tier===t?'active':''}}" onclick="ST.tier='${{t}}';renderInspector()">${{t.toUpperCase()}}</button>
    `).join('');
    const txt = (f.summaries && f.summaries[ST.tier]) ? f.summaries[ST.tier] : '(no summary available)';
    pre.innerHTML = highlightPseudonyms(txt);
  }}

  function buildCrawlCommand() {{
    const p = (ST.cmdFolder || '~/Dropbox').replace(/"/g, '\\"');
    let cmd = `cortical crawl "${{p}}" --sanitize --privacy-profile ${{ST.cmdProfile}}`;
    if (ST.cmdTerms.trim()) cmd += ` --custom-terms "${{ST.cmdTerms.trim().replace(/"/g, '\\"')}}"`;
    if (ST.cmdDryRun) cmd += ' --dry-run';
    if (ST.cmdFull) cmd += ' --full-reindex';
    return cmd;
  }}

  function openCmdBuilder() {{
    document.getElementById('modal-root').innerHTML = `
      <div class="backdrop" onclick="if(event.target===this)closeCmdBuilder()">
        <div class="modal" role="dialog" aria-modal="true" aria-label="Re-index &amp; Sanitize Command Builder">
          <div class="card-head">
            <h2>⚡ Re-index &amp; Sanitize Command Builder</h2>
            <button class="btn" onclick="closeCmdBuilder()">✕ Close</button>
          </div>
          <div class="grid-2" style="margin-bottom:10px;">
            <div>
              <label class="sub">Target Folder</label>
              <input class="input mono" style="width:100%;" value="${{esc(ST.cmdFolder)}}" oninput="ST.cmdFolder=this.value;refreshCmdOut()" />
            </div>
            <div>
              <label class="sub">Privacy Profile</label>
              <select class="select" style="width:100%;" onchange="ST.cmdProfile=this.value;refreshCmdOut()">
                ${{['max_security','low','medium','max_context'].map((pr) => `<option value="${{pr}}" ${{ST.cmdProfile===pr?'selected':''}}>${{pr}}</option>`).join('')}}
              </select>
            </div>
          </div>
          <div style="margin-bottom:10px;">
            <label class="sub">Custom Redaction Terms (comma-separated)</label>
            <input class="input" style="width:100%;" placeholder="Project Apollo, Client Example" value="${{esc(ST.cmdTerms)}}" oninput="ST.cmdTerms=this.value;refreshCmdOut()" />
          </div>
          <div style="display:flex;gap:16px;margin-bottom:12px;">
            <label><input type="checkbox" ${{ST.cmdDryRun?'checked':''}} onchange="ST.cmdDryRun=this.checked;refreshCmdOut()" /> Preview first (<code>--dry-run</code>)</label>
            <label><input type="checkbox" ${{ST.cmdFull?'checked':''}} onchange="ST.cmdFull=this.checked;refreshCmdOut()" /> Force full re-index</label>
          </div>
          <pre class="preview" id="cmd-out" style="max-height:110px;">${{esc(buildCrawlCommand())}}</pre>
          <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:12px;">
            <button class="btn" onclick="copyCmd(buildCrawlCommand())">📋 Copy Crawl Command</button>
            <button class="btn primary" onclick="copyCmd('cortical wiki-dashboard --open')">📊 Copy Open Wiki Dashboard</button>
          </div>
        </div>
      </div>
    `;
  }}
  function refreshCmdOut() {{
    const el = document.getElementById('cmd-out');
    if (el) el.textContent = buildCrawlCommand();
  }}
  function closeCmdBuilder() {{ document.getElementById('modal-root').innerHTML = ''; }}
  function copyCmd(txt) {{
    if (navigator.clipboard && navigator.clipboard.writeText) {{
      navigator.clipboard.writeText(txt).then(() => toast('Copied command to clipboard!'));
    }} else {{
      toast('Command ready to copy.');
    }}
  }}

  renderTop();
  renderFilters();
  renderFiles();
  renderInspector();
  </script>
</body>
</html>
"""


def export_wiki_dashboard(
    out_dir: Path | str,
    *,
    db_path: Optional[Path | str] = None,
    principal_id: str = "local_owner",
) -> Path:
    """Exports self-contained static `wiki.html` Explorer & Privacy Audit dashboard."""
    resolved_db = resolve_default_db(db_path)
    payload = collect_wiki_dashboard_payload(resolved_db, principal_id=principal_id)
    out = Path(out_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    target = out / "wiki.html"
    target.write_text(render_wiki_dashboard_html(payload), encoding="utf-8")
    return target
