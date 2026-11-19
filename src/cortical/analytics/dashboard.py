"""Zero-server Static HTML Configurator (`settings.html`) & Documentation (`help.html`).

Includes 4 modular workspaces:
  1. Hardware Tier, Variable-Quant Model Selector & Custom Model Builder (`+ Add Custom Model`)
  2. 8 Harnesses & Tool Composer (`Serena`, `RTK`, `PinchTab/Playwright`, `context-mode`, optional `Router`)
  3. Dynamic Privacy Vault (`auto` / `fail_closed` / `fail_open`, custom terms, File Picker + `@private:` copy)
  4. Compression (`TOON`), Auto-Tuner & ROI
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Optional

from ..config import DEFAULT_CONFIG, load_cortical_config
from ..hardware.models import BUILTIN_MODEL_CATALOG
from ..harnesses.adapters import get_harness_presend_matrix


def _nav_links(is_help: bool, public_docs: bool) -> str:
    home = '<a href="./index.html" style="color:var(--accent);">🏠 Home</a>'
    gh = '<a href="https://github.com/ccancellieri/cortical" target="_blank" rel="noopener" style="color:var(--accent);">GitHub</a>'
    if is_help:
        return f'<a href="./settings.html" style="color:var(--accent);">⚙️ Settings</a> · {home} · {gh}'
    base = f'<a href="./help.html" style="color:var(--accent);">❓ Help</a> · {home} · {gh}'
    return base if public_docs else f'<a href="./roi.html" style="color:var(--accent);">📊 ROI</a> · {base}'


def render_static_settings_html(
    cfg: Optional[dict[str, Any]] = None,
    hw: Optional[dict[str, Any]] = None,
    public_docs: bool = False,
) -> str:
    """Renders Zero-Server Static Settings Dashboard with Model Catalog, Custom Model Builder & Privacy Vault."""
    data = copy.deepcopy(cfg) if cfg is not None else (copy.deepcopy(DEFAULT_CONFIG) if public_docs else load_cortical_config())
    hw_snap = copy.deepcopy(hw) if hw is not None else {
        "os": "cross-platform",
        "total_ram_gb": 16.0,
        "vram_gb": 4.0,
        "unified_memory": False,
        "classification": {"tier": "tier_1a_hybrid_laptop", "label": "Tier 1A · Hybrid / Variable"},
    }
    catalog_json = json.dumps(BUILTIN_MODEL_CATALOG, ensure_ascii=False).replace("</", "<\\/")
    cfg_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    hw_json = json.dumps(hw_snap, ensure_ascii=False).replace("</", "<\\/")
    presend_json = json.dumps(get_harness_presend_matrix(), ensure_ascii=False).replace("</", "<\\/")
    nav = _nav_links(is_help=False, public_docs=public_docs)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Cortical Settings · Models, 8 Harnesses &amp; Privacy Vault</title>
  <style>
    :root {{ --bg:#080d1a; --card:#131c2e; --card2:#0c1424; --border:#24324a; --text:#e2e8f0; --muted:#94a3b8; --accent:#38bdf8; --emerald:#34d399; --amber:#fbbf24; --danger:#f87171; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; background:var(--bg); color:var(--text); line-height:1.5; }}
    .wrap {{ max-width:1280px; margin:0 auto; padding:22px 20px 64px; }}
    .top {{ display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; margin-bottom:14px; }}
    h1 {{ margin:0; font-size:1.5rem; }}
    .layout {{ display:grid; grid-template-columns:250px 1fr; gap:16px; align-items:start; }}
    @media (max-width:860px) {{ .layout {{ grid-template-columns:1fr; }} }}
    .sidebar {{ position:sticky; top:16px; background:var(--card); border:1px solid var(--border); border-radius:12px; padding:10px; display:flex; flex-direction:column; gap:6px; }}
    .tab {{ text-align:left; background:var(--card2); border:1px solid var(--border); color:var(--text); border-radius:9px; padding:10px 12px; cursor:pointer; font-size:0.86rem; font-weight:600; }}
    .tab.active {{ background:rgba(56,189,248,0.14); border-color:var(--accent); color:var(--accent); }}
    .card {{ background:var(--card); border:1px solid var(--border); border-radius:12px; padding:18px; margin-bottom:16px; }}
    .card h2 {{ margin:0 0 8px; font-size:1.08rem; color:var(--accent); }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:12px; }}
    label {{ display:flex; flex-direction:column; gap:4px; font-size:0.82rem; color:var(--muted); }}
    .chk {{ flex-direction:row; align-items:center; gap:8px; color:var(--text); cursor:pointer; font-weight:500; }}
    .chk input {{ width:auto; }}
    input, select, textarea {{ background:#060a14; color:var(--text); border:1px solid var(--border); border-radius:8px; padding:8px 10px; font-size:0.85rem; width:100%; font-family:inherit; }}
    textarea {{ min-height:80px; resize:vertical; }}
    .btn {{ padding:8px 13px; border-radius:8px; border:1px solid var(--border); background:var(--card); color:var(--text); cursor:pointer; font-weight:600; font-size:0.84rem; display:inline-flex; align-items:center; gap:5px; text-decoration:none; }}
    .btn-primary {{ background:var(--accent); color:#082f49; border-color:var(--accent); }}
    .btn-em {{ background:var(--emerald); color:#052e16; border-color:var(--emerald); }}
    .btn-danger {{ background:rgba(248,113,113,0.15); color:var(--danger); border-color:rgba(248,113,113,0.4); }}
    table {{ width:100%; border-collapse:collapse; font-size:0.84rem; margin-top:8px; }}
    th, td {{ text-align:left; padding:8px; border-bottom:1px solid var(--border); vertical-align:top; }}
    th {{ color:var(--muted); }}
    .pill {{ display:inline-block; padding:2px 8px; border-radius:999px; font-size:0.74rem; font-weight:700; border:1px solid var(--border); }}
    .pill-ok {{ color:var(--emerald); border-color:rgba(52,211,153,0.4); background:rgba(52,211,153,0.1); }}
    .pill-warn {{ color:var(--amber); border-color:rgba(251,191,36,0.4); background:rgba(251,191,36,0.1); }}
    pre {{ background:#060a14; border:1px solid var(--border); border-radius:8px; padding:10px; font-size:0.8rem; overflow-x:auto; color:#cbd5e1; }}
    .status {{ font-size:0.84rem; color:var(--emerald); margin-bottom:10px; min-height:1.2em; }}
  </style>
</head>
<body>
  <div class="wrap" id="app">Loading...</div>
  <script>
    let CFG = {cfg_json};
    const CATALOG = {catalog_json};
    const HW = {hw_json};
    const PRESEND = {presend_json};
    let LANG = localStorage.getItem('cortical_lang') || 'en';
    let TAB = 'models';
    let SAVE_MSG = '';
    let PICKED_PRIV_PREVIEW = '';

    const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));

    const T = {{
      en: {{
        title: '⚙️ Cortical Control Plane Settings',
        sub: 'Zero-server declarative configuration (cortical.config.json)',
        save: 'Save to Disk', download: 'Download JSON', import: 'Import JSON',
        tabs: {{ models: '🧠 Hardware & Models', harnesses: '🔌 8 Harnesses & Composer', privacy: '🛡️ Privacy Vault', compression: '🗜️ TOON, Tuner & ROI' }},
        saved: '✅ Saved cortical.config.json directly to disk.', downloaded: '⬇️ Downloaded cortical.config.json.', imported: '📂 Imported configuration.',
        addModelBtn: '+ Add Custom / Variable-Quant Model',
      }},
      it: {{
        title: '⚙️ Configurazione Control Plane Cortical',
        sub: 'Configurazione dichiarativa Zero-Server (cortical.config.json)',
        save: 'Salva su Disco', download: 'Scarica JSON', import: 'Importa JSON',
        tabs: {{ models: '🧠 Hardware & Modelli', harnesses: '🔌 8 Harness & Compositore', privacy: '🛡️ Privacy Vault', compression: '🗜️ TOON, Auto-Tuner & ROI' }},
        saved: '✅ File cortical.config.json salvato su disco.', downloaded: '⬇️ Scaricato cortical.config.json.', imported: '📂 Configurazione importata.',
        addModelBtn: '+ Aggiungi Modello Custom / Quant Variabile',
      }}
    }};

    function allModels() {{
      const map = new Map();
      CATALOG.forEach((m) => map.set(m.model_id, {{...m, custom: false}}));
      (CFG.custom_models || []).forEach((m) => map.set(m.model_id, {{...m, custom: true}}));
      return Array.from(map.values());
    }}

    function addCustomModelFromForm() {{
      const id = document.getElementById('cm-id').value.trim();
      if (!id) return;
      const entry = {{
        model_id: id,
        runner: document.getElementById('cm-runner').value,
        memory_gb: Number(document.getElementById('cm-mem').value || 5.0),
        native_ctx: Number(document.getElementById('cm-ctx').value || 32768),
        quantization: document.getElementById('cm-quant').value.trim() || 'variable-quant',
        is_variable_quant: Boolean(document.getElementById('cm-var').checked),
        roles: document.getElementById('cm-roles').value.split(',').map((s) => s.trim()).filter(Boolean),
        pull_ref: document.getElementById('cm-pull').value.trim() || ('ollama pull ' + id),
        notes: document.getElementById('cm-notes').value.trim() || 'Custom user model',
      }};
      CFG.custom_models = (CFG.custom_models || []).filter((x) => x.model_id !== id);
      CFG.custom_models.push(entry);
      SAVE_MSG = 'Added custom model: ' + id;
      render();
    }}

    function removeCustomModel(id) {{
      CFG.custom_models = (CFG.custom_models || []).filter((x) => x.model_id !== id);
      render();
    }}

    function assignRoleModel(role, modelId) {{
      CFG.models_by_role = CFG.models_by_role || {{}};
      CFG.models_by_role[role] = modelId;
      if (role === 'daily_coder') CFG.active_model = modelId;
      render();
    }}

    function handleVaultPicker(ev) {{
      const f = ev.target.files?.[0];
      if (!f) return;
      f.text().then((txt) => {{
        const masked = txt
          .replace(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{{2,}}/g, '[EMAIL_1]')
          .replace(/\\b[A-Z]{{2}}\\d{{2}}[A-Z0-9]{{11,30}}\\b/g, '[IBAN_1]');
        const alias = f.name.replace(/\\.[^.]+$/, '').toLowerCase().replace(/[^a-z0-9_-]+/g, '_');
        PICKED_PRIV_PREVIEW = `Alias: @private:${{alias}} (cortical://private/${{alias}})\nCLI: PYTHONPATH=src python3 -m cortical.cli ingest "${{f.name}}" --policy ${{CFG.privacy?.default_policy || 'auto'}} --profile ${{CFG.privacy?.default_profile || 'medium'}}\n\nPreview:\n` + masked.slice(0, 600);
        render();
      }});
    }}

    function renderModelsPanel(L) {{
      const models = allModels();
      const cls = HW.classification || {{}};
      const rows = models.map((m) => `
        <tr>
          <td><strong><code>${{esc(m.model_id)}}</code></strong><br/><span style="font-size:0.75rem;color:var(--muted);">${{esc(m.quantization)}} ${{m.is_variable_quant ? '· VarQuant' : ''}}</span></td>
          <td>${{Number(m.memory_gb || 0).toFixed(1)}} GB</td>
          <td>${{Number(m.native_ctx || 32768).toLocaleString()}}</td>
          <td>${{(m.roles || []).join(', ')}}</td>
          <td><code>${{esc(m.pull_ref)}}</code></td>
          <td>
            <button class="btn" onclick="assignRoleModel('daily_coder','${{esc(m.model_id)}}')">Set Daily</button>
            <button class="btn" onclick="assignRoleModel('deep_reasoner','${{esc(m.model_id)}}')">Set Reasoner</button>
            ${{m.custom ? `<button class="btn btn-danger" onclick="removeCustomModel('${{esc(m.model_id)}}')">🗑️</button>` : ''}}
          </td>
        </tr>`).join('');

      return `
        <div class="card">
          <h2>Hardware &amp; Model Selector</h2>
          <p style="margin:0 0 10px;color:var(--muted);font-size:0.86rem;">
            Detected/Profile: <span class="pill pill-ok">${{esc(cls.label || cls.tier || 'Variable Hardware')}}</span> ·
            RAM: <b>${{HW.total_ram_gb}} GB</b> · VRAM: <b>${{HW.vram_gb}} GB</b> (${{HW.unified_memory ? 'Unified' : 'Discrete'}})
          </p>
          <div class="grid" style="margin-bottom:12px;">
            <label>Active Runner
              <select onchange="CFG.active_runner=this.value; render();">
                ${{Object.keys(CFG.runners || {{ollama:{{}}}}).map((r) => `<option value="${{r}}" ${{CFG.active_runner===r?'selected':''}}>${{r}}</option>`).join('')}}
              </select>
            </label>
            <label>Router/NER Model (1.5B-3B)
              <input value="${{esc((CFG.models_by_role||{{}}).router || 'qwen2.5:1.5b')}}" oninput="CFG.models_by_role.router=this.value; CFG.models_by_role.ner=this.value;" />
            </label>
            <label>Daily Coder Model (8B-9B VarQuant)
              <input value="${{esc((CFG.models_by_role||{{}}).daily_coder || 'qwen3.5:9b-q3_k_xl')}}" oninput="CFG.models_by_role.daily_coder=this.value;" />
            </label>
            <label>Deep Reasoner / Orchestrator (27B 4-bit XXS)
              <input value="${{esc((CFG.models_by_role||{{}}).deep_reasoner || 'qwen3.8:27b-q4_xxs')}}" oninput="CFG.models_by_role.deep_reasoner=this.value; CFG.models_by_role.orchestrator=this.value;" />
            </label>
          </div>
          <table>
            <thead><tr><th>Model &amp; Quantization</th><th>Footprint</th><th>Native Ctx</th><th>Roles</th><th>Download Cmd</th><th>Actions</th></tr></thead>
            <tbody>${{rows}}</tbody>
          </table>
        </div>
        <div class="card">
          <h2>${{L.addModelBtn}}</h2>
          <div class="grid">
            <label>Model ID<input id="cm-id" placeholder="e.g. hf.co/unsloth/Qwen3.8-27B-GGUF:UD-Q4_XXS" /></label>
            <label>Runner<select id="cm-runner"><option value="ollama">ollama</option><option value="unsloth">unsloth</option><option value="llama_cpp">llama_cpp</option><option value="mlx_lm">mlx_lm</option></select></label>
            <label>Memory (GB)<input id="cm-mem" type="number" step="0.1" value="8.1" /></label>
            <label>Native Context<input id="cm-ctx" type="number" step="1024" value="32768" /></label>
            <label>Quantization<input id="cm-quant" value="Unsloth Variable 4-bit XXS" /></label>
            <label>Roles (comma-sep)<input id="cm-roles" value="deep_reasoner, orchestrator" /></label>
            <label>Pull Command<input id="cm-pull" placeholder="ollama pull ..." /></label>
            <label>Notes<input id="cm-notes" placeholder="Runs cleanly on 16GB unified RAM" /></label>
          </div>
          <label class="chk" style="margin:10px 0;"><input id="cm-var" type="checkbox" checked /> Variable / Dynamic Unsloth Quantization</label>
          <button class="btn btn-primary" onclick="addCustomModelFromForm()">${{L.addModelBtn}}</button>
        </div>`;
    }}

    function renderHarnessesPanel() {{
      const hKeys = Object.keys(PRESEND);
      const hCards = hKeys.map((h) => `
        <label class="chk" style="justify-content:space-between; padding:8px 10px; border:1px solid var(--border); border-radius:8px; background:var(--card2);">
          <span><input type="checkbox" ${{(CFG.harnesses||{{}})[h]!==false?'checked':''}} onchange="CFG.harnesses=CFG.harnesses||{{}}; CFG.harnesses['${{h}}']=this.checked;" /> <b>${{h}}</b></span>
          <span class="pill ${{PRESEND[h]?'pill-ok':'pill-warn'}}">${{PRESEND[h] ? 'Pre-Send Safe' : 'Dashboard Ingest Only'}}</span>
        </label>`).join('');

      const cKeys = Object.keys(CFG.composers || {{}});
      const cCards = cKeys.map((k) => `
        <label class="chk"><input type="checkbox" ${{CFG.composers[k]?'checked':''}} onchange="CFG.composers['${{k}}']=this.checked;" /> <code>${{k}}</code></label>`).join('');

      const r = CFG.router || {{}};
      return `
        <div class="card">
          <h2>Composed External Tools &amp; Optional HTTP Router</h2>
          <div class="grid" style="margin-bottom:12px;">${{cCards}}</div>
          <div style="border-top:1px solid var(--border); padding-top:12px;" class="grid">
            <label class="chk"><input type="checkbox" ${{r.enabled?'checked':''}} onchange="CFG.router.enabled=this.checked;" /> Enable Optional Local HTTP Router (70-90% API Offload)</label>
            <label>Router Provider<select onchange="CFG.router.provider=this.value;"><option value="litellm" ${{r.provider==='litellm'?'selected':''}}>LiteLLM</option><option value="omniroute" ${{r.provider==='omniroute'?'selected':''}}>OmniRoute</option><option value="ccr" ${{r.provider==='ccr'?'selected':''}}>claude-code-router</option></select></label>
            <label>Router Base URL<input value="${{esc(r.base_url||'http://127.0.0.1:4000/v1')}}" oninput="CFG.router.base_url=this.value;" /></label>
          </div>
        </div>
        <div class="card">
          <h2>8 Harness Sync Targets (macOS · Linux · Windows)</h2>
          <div class="grid">${{hCards}}</div>
          <pre style="margin-top:12px;">PYTHONPATH=src python3 -m cortical.cli sync --dry-run
PYTHONPATH=src python3 -m cortical.cli sync</pre>
        </div>`;
    }}

    function renderPrivacyPanel() {{
      const p = CFG.privacy || {{}};
      return `
        <div class="card">
          <h2>Dynamic Privacy Policy (<code>auto</code> | <code>fail_closed</code> | <code>fail_open</code>)</h2>
          <div class="grid">
            <label>Default Ingestion Policy
              <select onchange="CFG.privacy.default_policy=this.value;">
                <option value="auto" ${{p.default_policy==='auto'?'selected':''}}>auto (Smart content classifier)</option>
                <option value="fail_closed" ${{p.default_policy==='fail_closed'?'selected':''}}>fail_closed (Strict block on failure)</option>
                <option value="fail_open" ${{p.default_policy==='fail_open'?'selected':''}}>fail_open (Public/clean docs)</option>
              </select>
            </label>
            <label>Default Privacy Profile
              <select onchange="CFG.privacy.default_profile=this.value;">
                <option value="max_security" ${{p.default_profile==='max_security'?'selected':''}}>max_security (Local-only)</option>
                <option value="low" ${{p.default_profile==='low'?'selected':''}}>low (Redacted summary)</option>
                <option value="medium" ${{p.default_profile==='medium'?'selected':''}}>medium (Structured pseudonyms)</option>
                <option value="max_context" ${{p.default_profile==='max_context'?'selected':''}}>max_context (Raw public docs)</option>
              </select>
            </label>
            <label>Local JSON NER Model<input value="${{esc(p.ner_model||'qwen2.5:1.5b')}}" oninput="CFG.privacy.ner_model=this.value;" /></label>
            <label class="chk"><input type="checkbox" ${{p.use_local_ner?'checked':''}} onchange="CFG.privacy.use_local_ner=this.checked;" /> Enable Local JSON NER (Zero naive regex false positives)</label>
          </div>
          <label style="margin-top:12px;">Custom Terms (comma-separated)
            <textarea oninput="CFG.privacy.custom_terms=this.value.split(',').map(x=>x.trim()).filter(Boolean);" placeholder="Jane Doe, Client Corp, Project Orion">${{esc((p.custom_terms||[]).join(', '))}}</textarea>
          </label>
        </div>
        <div class="card">
          <h2>Zero-Attachment Vault Preview (Static Config Only)</h2>
          <p style="font-size:0.84rem;color:var(--muted);margin:0 0 10px;">
            Static preview only (plain text). To upload real PDF/DOCX files into SQLite Vault and view <code>max_security</code> items, launch the local Vault UI:
            <code>PYTHONPATH=src .venv/bin/python -m cortical.cli ui</code>
          </p>
          <label class="btn" style="flex-direction:row; cursor:pointer;">📄 Pick Local Text File to Preview @private Alias<input type="file" onchange="handleVaultPicker(event)" style="display:none;" /></label>
          ${{PICKED_PRIV_PREVIEW ? `<pre style="margin-top:10px;">${{esc(PICKED_PRIV_PREVIEW)}}</pre>` : ''}}
        </div>`;
    }}

    function renderCompressionPanel() {{
      const c = CFG.compression || {{}};
      const rep = CFG.report || {{}};
      return `
        <div class="card">
          <h2>Deterministic Compression (TOON) &amp; Auto-Sizing</h2>
          <div class="grid">
            <label class="chk"><input type="checkbox" ${{c.enable_toon!==false?'checked':''}} onchange="CFG.compression.enable_toon=this.checked;" /> Enable Lossless TOON Encoder (w/ compact JSON fallback)</label>
            <label>Minimum TOON Saving Guard (%)<input type="number" step="1" value="${{c.min_toon_saving_pct ?? 10}}" oninput="CFG.compression.min_toon_saving_pct=Number(this.value||10);" /></label>
            <label>Max Memory Context Share (0.05-0.35)<input type="number" step="0.01" value="${{c.max_context_share ?? 0.15}}" oninput="CFG.compression.max_context_share=Number(this.value||0.15);" /></label>
            <label>Report Language<select onchange="CFG.report.language=this.value;"><option value="auto" ${{rep.language==='auto'?'selected':''}}>auto</option><option value="en" ${{rep.language==='en'?'selected':''}}>English</option><option value="it" ${{rep.language==='it'?'selected':''}}>Italiano</option></select></label>
          </div>
          <pre style="margin-top:12px;">PYTHONPATH=src python3 -m cortical.cli tune
PYTHONPATH=src python3 -m cortical.cli bench --compare</pre>
        </div>`;
    }}

    function render() {{
      const L = T[LANG] || T.en;
      const body = TAB === 'models' ? renderModelsPanel(L) : (TAB === 'harnesses' ? renderHarnessesPanel() : (TAB === 'privacy' ? renderPrivacyPanel() : renderCompressionPanel()));
      const sidebar = Object.entries(L.tabs).map(([k, lbl]) => `<button class="tab ${{TAB===k?'active':''}}" onclick="TAB='${{k}}'; render();">${{lbl}}</button>`).join('');
      document.getElementById('app').innerHTML = `
        <div class="top">
          <div>
            <h1>${{L.title}}</h1>
            <div style="font-size:0.84rem;color:var(--muted);">${{L.sub}} · {nav}</div>
          </div>
          <div style="display:flex; gap:8px; flex-wrap:wrap;">
            <button class="btn" onclick="LANG=LANG==='en'?'it':'en'; localStorage.setItem('cortical_lang',LANG); render();">${{LANG==='it'?'🇮🇹 IT':'🇬🇧 EN'}}</button>
            <label class="btn" style="flex-direction:row;cursor:pointer;">📂 <span>${{L.import}}</span><input type="file" accept=".json" onchange="importCfg(event)" style="display:none;" /></label>
            <button class="btn" onclick="downloadCfg()">⬇️ ${{L.download}}</button>
            <button class="btn btn-em" onclick="saveCfg()">💾 ${{L.save}}</button>
          </div>
        </div>
        <div class="status">${{esc(SAVE_MSG)}}</div>
        <div class="layout">
          <aside class="sidebar">${{sidebar}}</aside>
          <main>${{body}}</main>
        </div>`;
    }}

    window.saveCfg = async function() {{
      const L = T[LANG] || T.en;
      const txt = JSON.stringify(CFG, null, 2) + '\\n';
      if (window.showSaveFilePicker) {{
        try {{
          const h = await window.showSaveFilePicker({{suggestedName:'cortical.config.json', types:[{{description:'JSON', accept:{{'application/json':['.json']}}}}]}});
          const w = await h.createWritable();
          await w.write(txt); await w.close();
          SAVE_MSG = L.saved; render(); return;
        }} catch(e) {{ if (e.name==='AbortError') return; }}
      }}
      window.downloadCfg();
    }};
    window.downloadCfg = function() {{
      const L = T[LANG] || T.en;
      const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([JSON.stringify(CFG, null, 2) + '\\n'], {{type:'application/json'}}));
      a.download = 'cortical.config.json'; a.click();
      SAVE_MSG = L.downloaded; render();
    }};
    window.importCfg = function(ev) {{
      const L = T[LANG] || T.en;
      const f = ev.target.files?.[0];
      if (!f) return;
      f.text().then((t) => {{ CFG = JSON.parse(t); SAVE_MSG = L.imported; render(); }});
    }};
    render();
  </script>
</body>
</html>
"""


def render_static_help_html(public_docs: bool = False) -> str:
    """Renders bilingual (EN/IT) documentation for Cortical's Control Plane, Privacy Vault & Compression."""
    nav = _nav_links(is_help=True, public_docs=public_docs)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Cortical Help &amp; Documentation (Zero-Server)</title>
  <style>
    :root {{ --bg:#080d1a; --card:#131c2e; --border:#24324a; --text:#e2e8f0; --muted:#94a3b8; --accent:#38bdf8; --emerald:#34d399; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; background:var(--bg); color:var(--text); line-height:1.6; }}
    .wrap {{ max-width:1040px; margin:0 auto; padding:24px 20px 64px; }}
    .top {{ display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; margin-bottom:20px; }}
    .btn {{ padding:7px 12px; border-radius:8px; border:1px solid var(--border); background:var(--card); color:var(--text); cursor:pointer; font-weight:600; font-size:0.84rem; }}
    .card {{ background:var(--card); border:1px solid var(--border); border-radius:12px; padding:18px; margin-bottom:16px; }}
    .card h2 {{ margin:0 0 8px; font-size:1.08rem; color:var(--accent); }}
    code, pre {{ background:#060a14; border:1px solid var(--border); border-radius:6px; padding:2px 6px; font-size:0.82rem; color:var(--emerald); }}
    pre {{ padding:12px; overflow-x:auto; color:#cbd5e1; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="top">
      <div>
        <h1 id="ht">❓ Cortical Reference &amp; CLI Guide</h1>
        <div style="font-size:0.84rem;color:var(--muted);">{nav}</div>
      </div>
      <button class="btn" id="hl" onclick="LANG=LANG==='en'?'it':'en'; localStorage.setItem('cortical_lang',LANG); applyL();">🇬🇧 EN</button>
    </div>
    <div id="c-en">
      <div class="card"><h2>1. Hardware Preflight &amp; Variable-Quantization Models</h2><p>Run <code>cortical doctor</code> and <code>cortical models recommend</code> to inspect RAM/VRAM across macOS, Linux &amp; Windows (including Tier 1A <code>16 GB RAM + 4 GB VRAM</code> hybrids and Tier 1B <code>16 GB unified</code> running <code>27B</code> dynamic 4-bit XXS at <code>8.1 GB</code>). Add custom models in Settings or via <code>cortical models add</code>.</p></div>
      <div class="card"><h2>2. 8-Harness Sync &amp; Best-of-Breed Composition</h2><p>Run <code>cortical sync --dry-run</code> then <code>cortical sync</code> to configure Serena LSP, RTK shell compression, PinchTab/Playwright snapshots, <code>context-mode</code>, optional HTTP Router, and shared rules across Antigravity, pi, OpenCode, OpenClaw, Codex, Claude Code, DeepSeek Harness (<code>dsh</code>) &amp; Unsloth Studio with timestamped backups and <code>--rollback</code>.</p></div>
      <div class="card"><h2>3. Dynamic Privacy Vault (`auto` | `fail_closed` | `fail_open`) &amp; TOON</h2><p>Ingest sensitive docs via Dashboard or <code>cortical ingest file.docx --policy auto</code>. Sensitive items resolve to <code>fail_closed</code> and expose clean <code>cortical://private/&lt;alias&gt;</code> MCP resources + auto-sized memory without pasting files into cloud chats. Use <code>cortical compress</code> for lossless TOON compression.</p></div>
    </div>
    <div id="c-it" style="display:none;">
      <div class="card"><h2>1. Preflight Hardware &amp; Quantizzazione Variabile</h2><p>Esegui <code>cortical doctor</code> e <code>cortical models recommend</code> su macOS, Linux o Windows (incluso Tier 1A <code>16 GB RAM + 4 GB VRAM</code> e Tier 1B <code>16 GB</code> unificati con <code>27B</code> 4-bit XXS da <code>8.1 GB</code>). Aggiungi nuovi modelli in Configurazione o con <code>cortical models add</code>.</p></div>
      <div class="card"><h2>2. Sync su 8 Harness &amp; Tool Composti</h2><p>Esegui <code>cortical sync --dry-run</code> poi <code>cortical sync</code> per configurare Serena, RTK, PinchTab/Playwright, <code>context-mode</code>, Router HTTP opzionale e regole condivise su Antigravity, pi, OpenCode, OpenClaw, Codex, Claude Code, <code>dsh</code> e Unsloth Studio con backup e <code>--rollback</code>.</p></div>
      <div class="card"><h2>3. Privacy Vault Dinamico (`auto` | `fail_closed` | `fail_open`) &amp; TOON</h2><p>Carica documenti con <code>cortical ingest doc.docx --policy auto</code>: i file sensibili diventano <code>fail_closed</code> e vengono esposti come risorse <code>cortical://private/&lt;alias&gt;</code> o memoria auto-dimensionata senza allegati grezzi in chat. Usa <code>cortical compress</code> per TOON lossless.</p></div>
    </div>
  </div>
  <script>
    let LANG = localStorage.getItem('cortical_lang') || 'en';
    function applyL() {{
      document.getElementById('c-en').style.display = LANG === 'en' ? 'block' : 'none';
      document.getElementById('c-it').style.display = LANG === 'it' ? 'block' : 'none';
      document.getElementById('hl').textContent = LANG === 'it' ? '🇮🇹 IT' : '🇬🇧 EN';
      document.getElementById('ht').textContent = LANG === 'it' ? '❓ Cortical Guida & Riferimento CLI' : '❓ Cortical Reference & CLI Guide';
    }}
    applyL();
  </script>
</body>
</html>
"""


def export_static_dashboard(
    output_dir: Path | str,
    *,
    config: Optional[dict[str, Any]] = None,
    hw: Optional[dict[str, Any]] = None,
    public_docs: bool = False,
) -> tuple[Path, Path]:
    """Exports `settings.html` and `help.html` into `output_dir` (clean & stripped when `public_docs=True`)."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    s_path = out / "settings.html"
    h_path = out / "help.html"
    s_path.write_text(render_static_settings_html(cfg=config, hw=hw, public_docs=public_docs), encoding="utf-8")
    h_path.write_text(render_static_help_html(public_docs=public_docs), encoding="utf-8")
    return (s_path, h_path)
