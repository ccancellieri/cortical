"""Zero-server static Per-Module Configuration (`html/settings.html`) & Documentation (`html/help.html`).

Uses File System Access API (`showSaveFilePicker`) on Chromium browsers to save
`cortical.config.json` directly to disk, with automatic Download / Import JSON fallback.
Includes Master-Detail module navigation, guided selectors, interactive ⓘ popovers,
custom privacy anonymization terms, sanitizer model selector, and instant IT/EN localization.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Optional

from .config import DEFAULT_CONFIG, load_cortical_config


def _topbar_nav_html(is_help: bool = False, public_docs: bool = False) -> str:
    """Returns shared navigation links for static settings/help pages (excluding gitignored local dashboards when `public_docs=True`)."""
    home = '<a href="./index.html" style="color:var(--accent);">🏠 Home</a>'
    gh = '<a href="https://github.com/ccancellieri/cortical" target="_blank" rel="noopener" style="color:var(--accent);">GitHub</a>'
    if is_help:
        cfg_link = '<a href="./settings.html" style="color:var(--accent);">⚙️ Settings / Config</a>'
        if public_docs:
            return f"{cfg_link} · {home} · {gh}"
        return f'<a href="./token_report.html" style="color:var(--accent);">📊 Token Report</a> · <a href="./wiki.html" style="color:var(--accent);">🧠 Wiki Explorer</a> · {cfg_link} · {home}'
    help_link = '<a href="./help.html" style="color:var(--accent);">❓ Help</a>'
    if public_docs:
        return f"{help_link} · {home} · {gh}"
    return f'<a href="./token_report.html" style="color:var(--accent);">📊 Token Report</a> · <a href="./wiki.html" style="color:var(--accent);">🧠 Wiki</a> · {help_link} · {home}'


def render_static_settings_html(cfg: Optional[dict[str, Any]] = None, public_docs: bool = False) -> str:
    """Renders a zero-server Per-Module Master-Detail Configuration Dashboard."""
    data = copy.deepcopy(cfg) if cfg is not None else (copy.deepcopy(DEFAULT_CONFIG) if public_docs else load_cortical_config())
    safe_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    nav_links = _topbar_nav_html(is_help=False, public_docs=public_docs)
    return f"""<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Cortical Settings · Per-Module Configurator</title>
  <style>
    :root {{ --bg:#0b1120; --card:#131c2e; --card2:#0c1424; --border:#24324a; --text:#e2e8f0; --muted:#94a3b8; --accent:#38bdf8; --emerald:#34d399; --amber:#fbbf24; --danger:#f87171; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; background:var(--bg); color:var(--text); line-height:1.5; }}
    .wrap {{ width:100%; max-width:1320px; margin:0 auto; padding:22px 20px 64px; }}
    .top {{ display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; margin-bottom:16px; }}
    h1 {{ margin:0; font-size:1.5rem; }}
    .desc {{ font-size:0.83rem; color:var(--muted); margin:0 0 12px; }}
    .layout {{ display:grid; grid-template-columns:280px 1fr; gap:16px; align-items:start; }}
    @media (max-width:860px) {{ .layout {{ grid-template-columns:1fr; }} }}
    .sidebar {{ position:sticky; top:16px; background:var(--card); border:1px solid var(--border); border-radius:12px; padding:10px; display:flex; flex-direction:column; gap:6px; }}
    .mod-btn {{ width:100%; text-align:left; background:var(--card2); border:1px solid var(--border); color:var(--text); border-radius:9px; padding:10px 12px; cursor:pointer; display:flex; justify-content:space-between; align-items:center; gap:8px; font-size:0.84rem; font-weight:600; }}
    .mod-btn:hover {{ border-color:var(--accent); }}
    .mod-btn.active {{ background:rgba(56,189,248,0.14); border-color:var(--accent); color:var(--accent); }}
    .badge-on {{ font-size:0.68rem; padding:2px 7px; border-radius:999px; background:rgba(52,211,153,0.15); color:var(--emerald); border:1px solid rgba(52,211,153,0.4); }}
    .badge-off {{ font-size:0.68rem; padding:2px 7px; border-radius:999px; background:rgba(248,113,113,0.12); color:var(--danger); border:1px solid rgba(248,113,113,0.35); }}
    .card {{ background:var(--card); border:1px solid var(--border); border-radius:12px; padding:18px; margin-bottom:16px; }}
    .card h2 {{ margin:0 0 6px; font-size:1.08rem; color:var(--accent); display:flex; align-items:center; gap:8px; flex-wrap:wrap; }}
    .doc-box {{ background:var(--card2); border-left:3px solid var(--accent); border-radius:8px; padding:11px 14px; margin-bottom:14px; font-size:0.84rem; color:#cbd5e1; }}
    .doc-box code {{ color:var(--emerald); background:#060a14; padding:1px 5px; border-radius:4px; font-size:0.78rem; }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:12px; }}
    label {{ display:flex; flex-direction:column; gap:5px; font-size:0.82rem; color:var(--muted); }}
    .lbl-head {{ display:flex; align-items:center; gap:6px; color:var(--text); font-weight:600; }}
    input, select, textarea {{ background:#090e1a; color:var(--text); border:1px solid var(--border); border-radius:8px; padding:8px 10px; font-size:0.85rem; width:100%; font-family:inherit; }}
    textarea {{ min-height:70px; resize:vertical; }}
    .row-chk {{ flex-direction:row; align-items:center; gap:8px; color:var(--text); cursor:pointer; font-weight:500; }}
    .row-chk input {{ width:auto; }}
    .btn {{ padding:8px 14px; border-radius:8px; border:1px solid var(--border); background:var(--card); color:var(--text); cursor:pointer; font-weight:600; font-size:0.84rem; text-decoration:none; display:inline-flex; align-items:center; gap:5px; }}
    .btn-primary {{ background:var(--accent); color:#082f49; border-color:var(--accent); }}
    .btn-emerald {{ background:var(--emerald); color:#052e16; border-color:var(--emerald); }}
    .prof-card {{ border:1px solid var(--border); border-radius:10px; padding:12px; margin-bottom:10px; background:var(--card2); }}
    .chips {{ display:flex; flex-wrap:wrap; gap:6px; margin-top:6px; }}
    .chip {{ display:inline-flex; align-items:center; gap:5px; padding:4px 9px; border-radius:999px; border:1px solid var(--border); background:#090e1a; font-size:0.76rem; cursor:pointer; color:var(--text); }}
    .chip input {{ width:auto; margin:0; }}
    .status {{ font-size:0.84rem; color:var(--emerald); margin-bottom:10px; min-height:1.2em; }}
    .info-tip {{ position:relative; display:inline-flex; align-items:center; justify-content:center; width:18px; height:18px; border-radius:50%; border:1px solid var(--accent); color:var(--accent); font-size:0.72rem; cursor:pointer; user-select:none; flex-shrink:0; }}
    .info-pop {{ display:none; position:absolute; left:0; top:24px; z-index:50; width:290px; padding:9px 11px; border-radius:8px; background:#090e1a; border:1px solid var(--accent); color:var(--text); font-size:0.77rem; font-weight:400; line-height:1.45; box-shadow:0 8px 24px rgba(0,0,0,0.5); }}
    .info-tip:hover .info-pop, .info-tip:focus .info-pop, .info-tip.open .info-pop {{ display:block; }}
  </style>
</head>
<body>
  <div class="wrap" id="app">Loading...</div>
  <script>
    let CFG = {safe_json};
    let LANG = localStorage.getItem('cortical_lang') || 'it';
    let SELECTED_MOD = 'all';
    let SAVE_MSG = '';
    const ALL_CATS = ['SECRET', 'EMAIL', 'PHONE', 'IBAN', 'TAX_ID', 'IP', 'PERSON_NAME', 'CUSTOM', 'NAMES', 'ADDRESSES'];
    const MOD_ORDER = ['all', 'context_window', 'wiki_mcp', 'privacy_sanitizer', 'skills_hub', 'token_analytics', 'permission_gate'];

    const esc = (s) => String(s || '').replace(/[&<>"']/g, (c) => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));

    const I18N = {{
      it: {{
        title: '⚙️ Configurazione Moduli Cortical (Zero-Server)',
        sub: 'Documentazione e parametri modulari salvati in cortical.config.json senza server attivi.',
        import: 'Importa', download: 'Scarica JSON', save: 'Salva su Disco',
        allLabel: '📦 Tutti i Moduli',
        enabledLbl: 'Modulo attivo',
        on: 'ON', off: 'OFF',
        savedDisk: '✅ Configurazione salvata su disco (cortical.config.json).',
        downloaded: '⬇️ File cortical.config.json scaricato.',
        imported: '📂 Configurazione importata.',
        // context_window
        ctxTitle: '🧠 Runner Locale & Auto-Scaler Contesto (200k)',
        ctxDoc: 'Seleziona il runner LLM pluggabile (Ollama, llama.cpp, MLX, OpenAI-compatible) e il tetto massimo di contesto. Cortical rileva la RAM libera reale (<code>vm_stat</code> / <code>/proc/meminfo</code>) e dimensiona <code>num_ctx</code> fino a 200k evitando troncamenti silenti a 4096 token.',
        runnerLbl: 'Runner Attivo', runnerTip: 'Motore locale usato per analisi ROI, sintesi wiki e filtro privacy offline.',
        modelLbl: 'Modello Attivo', modelTip: 'Auto-Discover sceglie il modello già caricato in VRAM; oppure fissane uno specifico.',
        ctxCapLbl: 'Max Context Window (Cap)', ctxCapTip: 'Limite superiore configurabile (fino a 200.000 token); scala automaticamente su RAM libera.',
        urlLbl: 'Base URL Runner', urlTip: 'Endpoint HTTP locale o LAN del runner selezionato.',
        // token_analytics
        tokTitle: '📊 Token Report, Lingua, Retention & ROI Cloud',
        tokDoc: 'Calcola il risparmio reale leggendo i transcript locali (Antigravity, Claude Code, Codex) e le run locali Cortical a 0 token cloud. I report possono seguire automaticamente la lingua della chat corrente (<code>auto</code>).',
        autoRep: 'Genera Token Report a fine turno',
        repLangLbl: 'Lingua Report in Chat', repLangTip: 'Auto adatta la lingua del report in chat al contesto della conversazione (IT/EN/ES).',
        rangeLbl: 'Finestra Temporale Predefinita', rangeTip: 'Intervallo iniziale mostrato nei grafici giornalieri e nella tabella cloud.',
        retLbl: 'Retention Log Puntuali (giorni)', retTip: 'Conserva le metriche granulari per N giorni mantenendo i totali aggregati storici.',
        presetLbl: 'Preset Tariffe Cloud (Stima ROI)', presetTip: 'Tariffa usata per stimare il risparmio economico per token cloud evitato.',
        // skills_hub -> displayed ONLY as Cortical Skill Engine
        skTitle: '⚡ Cortical Skill Engine (Auto-Compilazione & Consolidamento)',
        skDoc: 'Compila ed evolve skill riusabili a partire da concetti ed episodi ricorrenti (<code>learned-*</code>), unificando task simili via Jaccard + LLM locale per evitare proliferazione di micro-skill duplicate.',
        autoSk: 'Abilita auto-compilazione ed evoluzione skill',
        skPresetLbl: 'Profilo Selettività Skill', skPresetTip: 'Bilancia creazione di nuove skill vs fusione con skill già esistenti.',
        // privacy_sanitizer
        prTitle: '🛡️ Local Privacy Sanitizer & GDPR Anonymizer',
        prDoc: 'Pulisce metadati binari (DOCX/PDF/XLSX/OOXML), sostituisce segreti e identificatori con pseudonimi coerenti (<code>[EMAIL_1]</code>, <code>[PERSON_NAME_1]</code>, <code>[CUSTOM_1]</code>), applica termini personalizzati e opzionalmente riscrive quasi-identificatori tramite LLM locale completamente offline.',
        sanModelLbl: 'Modello LLM Sanitizer Offline', sanModelTip: 'Modello locale leggero (es. qwen2.5:1.5b) o evoluto usato per riscrivere quasi-identificatori.',
        personHeur: 'Rileva automaticamente Nomi/Cognomi (euristica [PERSON_NAME_N])',
        customTermsLbl: 'Termini Personalizzati da Anonimizzare (nomi, cognomi, clienti, codename — separati da virgola)',
        customTermsTip: 'Esempio: Carlo Cancellieri, Acme Srl, Progetto Orione → sostituiti da [CUSTOM_N].',
        addTier: '+ Aggiungi Livello Custom',
        catsLbl: 'Categorie da rimuovere / pseudonimizzare:',
        prLocalOnly: 'Solo Locale (0 byte al cloud)',
        prSumOnly: 'Solo Sintesi',
        prStripMeta: 'Rimuovi Metadati File',
        prUseLlm: 'Filtro LLM Locale Offline',
        prRedact: '[REDACTED] (vs pseudonimi)',
        // wiki_mcp
        wkTitle: '🌳 4-Tier Merkle Wiki MCP & Memoria 3+1',
        wkDoc: 'Indicizza solo cartelle/file aggiunti al contesto come albero Merkle a 4 livelli (<code>light</code> ~50 tok, <code>medium</code> ~250 tok, <code>high</code> ~1000 tok, <code>max</code>) su SQLite FTS5 + Macro-Graph degli episodi e regole/insight 3+1. Comando manuale: <code>PYTHONPATH=src python3 -m cortical.cli crawl &lt;dir&gt;</code>.',
        // permission_gate
        pgTitle: '🔒 Adaptive Permission Gate',
        pgDoc: 'Valuta deterministicamente il rischio di comandi bash (<code>safe</code> / <code>ask</code> / <code>deny</code>) in &lt;1 ms senza chiamare alcun LLM remoto, proteggendo da comandi distruttivi o accessi sensibili.',
      }},
      en: {{
        title: '⚙️ Cortical Modular Settings (Zero-Server)',
        sub: 'Per-module documentation and configuration stored in cortical.config.json with zero background servers.',
        import: 'Import', download: 'Download JSON', save: 'Save to Disk',
        allLabel: '📦 All Modules',
        enabledLbl: 'Module Enabled',
        on: 'ON', off: 'OFF',
        savedDisk: '✅ Saved directly to disk (cortical.config.json).',
        downloaded: '⬇️ Downloaded cortical.config.json.',
        imported: '📂 Configuration imported.',
        ctxTitle: '🧠 Local LLM Runner & 200k Context Auto-Scaler',
        ctxDoc: 'Pick the pluggable local runner (Ollama, llama.cpp, MLX, OpenAI-compatible) and upper context ceiling. Cortical probes live free RAM (<code>vm_stat</code> / <code>/proc/meminfo</code>) and scales <code>num_ctx</code> up to 200k to prevent silent 4096 truncation.',
        runnerLbl: 'Active Runner', runnerTip: 'Local engine used for ROI commentary, wiki synthesis, and offline privacy rewriting.',
        modelLbl: 'Active Model', modelTip: 'Auto-Discover picks the resident model in VRAM; or lock a specific ID.',
        ctxCapLbl: 'Max Context Window (Cap)', ctxCapTip: 'Configurable upper limit (up to 200,000 tokens); auto-scales to free RAM.',
        urlLbl: 'Runner Base URL', urlTip: 'Localhost or LAN HTTP endpoint of the selected runner.',
        tokTitle: '📊 Token Report, Language, Retention & Cloud ROI',
        tokDoc: 'Computes real savings from local cloud transcripts (Antigravity, Claude Code, Codex) and Cortical local runs at $0.00 cloud cost. In-chat Markdown reports can auto-match conversation language (<code>auto</code>).',
        autoRep: 'Generate Token Report at turn end',
        repLangLbl: 'In-Chat Report Language', repLangTip: 'Auto matches the chat conversation language (IT/EN/ES).',
        rangeLbl: 'Default Time Window', rangeTip: 'Initial time horizon shown in daily charts and cloud table.',
        retLbl: 'Granular Log Retention (days)', retTip: 'Prunes granular task/chat logs older than N days while keeping cumulative lifetime aggregates.',
        presetLbl: 'Cloud Pricing Preset (ROI Estimate)', presetTip: 'Reference rates used to estimate avoided cloud spend.',
        skTitle: '⚡ Cortical Skill Engine (Auto-Compile & Evolution)',
        skDoc: 'Compiles and evolves reusable <code>learned-*</code> skills from verified episodes and insights, consolidating overlapping skills via Jaccard + local LLM to prevent noisy micro-skill proliferation.',
        autoSk: 'Enable skill auto-compilation & evolution',
        skPresetLbl: 'Skill Selectivity Preset', skPresetTip: 'Balances creating new skills vs merging into existing skills.',
        prTitle: '🛡️ Local Privacy Sanitizer & GDPR Anonymizer',
        prDoc: 'Strips binary file metadata (DOCX/PDF/XLSX/OOXML), pseudonymizes identifiers consistently (<code>[EMAIL_1]</code>, <code>[PERSON_NAME_1]</code>, <code>[CUSTOM_1]</code>), enforces custom terms, and optionally rewrites quasi-identifiers with an offline local LLM.',
        sanModelLbl: 'Offline Sanitizer LLM Model', sanModelTip: 'Lightweight (e.g. qwen2.5:1.5b) or stronger local model used for quasi-identifier rewriting.',
        personHeur: 'Auto-detect Person Names/Surnames ([PERSON_NAME_N] heuristic)',
        customTermsLbl: 'Custom Terms to Anonymize (names, surnames, clients, codenames — comma separated)',
        customTermsTip: 'Example: Carlo Cancellieri, Acme Corp, Project Orion → replaced with [CUSTOM_N].',
        addTier: '+ Add Custom Privacy Tier',
        catsLbl: 'Categories to strip / pseudonymize:',
        prLocalOnly: 'Local Only (0 bytes to cloud)',
        prSumOnly: 'Summary Only',
        prStripMeta: 'Strip File Metadata',
        prUseLlm: 'Offline Local LLM Filter',
        prRedact: '[REDACTED] (vs pseudonyms)',
        wkTitle: '🌳 4-Tier Merkle Wiki MCP & 3+1 Memory',
        wkDoc: 'Indexes only explicitly attached context folders/files into a 4-tier Merkle tree (<code>light</code> ~50 tok, <code>medium</code> ~250 tok, <code>high</code> ~1000 tok, <code>max</code>) in SQLite FTS5 + Episode Macro-Graph + 3+1 Insights. CLI: <code>PYTHONPATH=src python3 -m cortical.cli crawl &lt;dir&gt;</code>.',
        pgTitle: '🔒 Adaptive Permission Gate',
        pgDoc: 'Deterministically scores shell commands (<code>safe</code> / <code>ask</code> / <code>deny</code>) in &lt;1 ms with zero remote LLM calls, protecting workspaces from destructive commands or sensitive reads.',
      }}
    }};

    const tip = (txt) => `<span class="info-tip" tabindex="0" onclick="this.classList.toggle('open')">i<span class="info-pop">${{esc(txt)}}</span></span>`;

    function modMeta(key) {{
      const comps = CFG.components || {{}};
      const c = comps[key] || {{}};
      const L = I18N[LANG] || I18N.it;
      const icons = {{ context_window: '🧠', wiki_mcp: '🌳', privacy_sanitizer: '🛡️', skills_hub: '⚡', token_analytics: '📊', permission_gate: '🔒' }};
      const rawTitle = LANG === 'en' ? (c.title_en || c.title_it || key) : (c.title_it || c.title_en || key);
      const safeTitle = String(rawTitle).replace(/skill\\s*hub/ig, 'Cortical Skill Engine');
      const desc = LANG === 'en' ? (c.desc_en || c.desc_it || '') : (c.desc_it || c.desc_en || '');
      return {{ icon: icons[key] || '🧩', title: safeTitle, desc: desc, enabled: c.enabled !== false, module: c.module || '' }};
    }}

    function toggleComponent(key, val) {{
      CFG.components = CFG.components || {{}};
      CFG.components[key] = CFG.components[key] || {{ enabled: true }};
      CFG.components[key].enabled = Boolean(val);
      renderApp();
    }}

    function setCfgPath(section, key, val) {{
      CFG[section] = CFG[section] || {{}};
      CFG[section][key] = val;
    }}

    function syncRunnerField(field, val) {{
      const name = CFG.active_runner || 'ollama';
      CFG.runners = CFG.runners || {{}};
      CFG.runners[name] = CFG.runners[name] || {{ type: name === 'ollama' ? 'ollama' : 'openai_compatible', enabled: true }};
      CFG.runners[name][field] = val;
    }}

    function onModelSelect(val) {{
      const inp = document.getElementById('active_model');
      if (val === '__custom__') {{
        if (inp) {{ inp.style.display = 'block'; inp.focus(); }}
      }} else {{
        CFG.active_model = val;
        if (inp) {{ inp.style.display = 'none'; inp.value = val; }}
      }}
    }}

    function onSanModelSelect(val) {{
      const inp = document.getElementById('sanitizer_model_custom');
      CFG.privacy_sanitizer = CFG.privacy_sanitizer || {{}};
      if (val === '__custom__') {{
        if (inp) {{ inp.style.display = 'block'; inp.focus(); }}
      }} else {{
        CFG.privacy_sanitizer.sanitizer_model = val;
        if (inp) {{ inp.style.display = 'none'; inp.value = val; }}
      }}
    }}

    function updateCustomTerms(raw) {{
      CFG.privacy_sanitizer = CFG.privacy_sanitizer || {{}};
      CFG.privacy_sanitizer.custom_terms = String(raw || '').split(/[,\\n]+/).map((s) => s.trim()).filter(Boolean);
    }}

    function applySkillPreset(p) {{
      const map = {{
        balanced: {{ min_terms: 4, consolidation_overlap: 3, consolidation_jaccard: 0.30 }},
        strict: {{ min_terms: 6, consolidation_overlap: 2, consolidation_jaccard: 0.25 }},
        permissive: {{ min_terms: 3, consolidation_overlap: 4, consolidation_jaccard: 0.40 }},
      }};
      CFG.skills = {{ ...(CFG.skills || {{}}), ...(map[p] || map.balanced), require_verified_artifact: true }};
      renderApp();
    }}

    function toggleCat(profName, cat, checked) {{
      const arr = new Set(CFG.privacy_profiles[profName].strip_categories || []);
      if (checked) arr.add(cat); else arr.delete(cat);
      CFG.privacy_profiles[profName].strip_categories = Array.from(arr);
    }}

    function addPrivacyProfile() {{
      const name = prompt(LANG === 'en' ? 'New custom privacy tier slug (e.g. finance_analysis):' : 'Nome nuovo livello privacy (es. finance_analysis):');
      if (!name) return;
      const slug = name.trim().toLowerCase().replace(/[^a-z0-9_]+/g, '_');
      CFG.privacy_profiles = CFG.privacy_profiles || {{}};
      CFG.privacy_profiles[slug] = {{
        description: 'Custom user privacy profile',
        local_only: false, allow_local_conclusions: true, summary_only: false,
        strip_metadata: true, use_local_llm: false, redact: false,
        strip_categories: ['EMAIL', 'PHONE', 'TAX_ID', 'IBAN', 'SECRET', 'PERSON_NAME', 'CUSTOM'],
        preserve_categories: ['AMOUNTS'],
      }};
      renderApp();
    }}

    function renderModuleHeader(modKey, docHtml, titleText) {{
      const L = I18N[LANG] || I18N.it;
      const m = modMeta(modKey);
      return `
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; margin-bottom:10px;">
          <h2 style="margin:0;">${{titleText}} <code style="font-size:0.74rem; color:var(--muted);">${{esc(m.module)}}</code></h2>
          <label class="row-chk" style="margin:0;">
            <input type="checkbox" ${{m.enabled ? 'checked' : ''}} onchange="toggleComponent('${{modKey}}', this.checked)" />
            <span>${{L.enabledLbl}}</span>
          </label>
        </div>
        <div class="doc-box">${{m.desc ? esc(m.desc) + '<br/>' : ''}}${{docHtml}}</div>`;
    }}

    function renderContextModule() {{
      const L = I18N[LANG] || I18N.it;
      const rKey = CFG.active_runner || 'ollama';
      const rObj = (CFG.runners || {{}})[rKey] || {{}};
      const curMod = CFG.active_model || '';
      const knownMods = ['', 'qwen3.5:9b-q3_k_xl', 'qwen3.8:27b-iq2_xxs', 'qwen3:8b', 'qwen2.5:1.5b'];
      const isCustom = !knownMods.includes(curMod);
      return `<div class="card">
        ${{renderModuleHeader('context_window', L.ctxDoc, L.ctxTitle)}}
        <div class="grid">
          <label><span class="lbl-head">${{L.runnerLbl}} ${{tip(L.runnerTip)}}</span>
            <select onchange="CFG.active_runner=this.value; renderApp();">
              <option value="ollama" ${{rKey==='ollama'?'selected':''}}>ollama (http://127.0.0.1:11434)</option>
              <option value="llama_cpp" ${{rKey==='llama_cpp'?'selected':''}}>llama_cpp / llama-server (:8080)</option>
              <option value="mlx_lm" ${{rKey==='mlx_lm'?'selected':''}}>mlx_lm (Apple Metal :8080)</option>
              <option value="openai_compatible" ${{rKey==='openai_compatible'?'selected':''}}>openai_compatible / Custom (:8888)</option>
            </select>
          </label>
          <label><span class="lbl-head">${{L.modelLbl}} ${{tip(L.modelTip)}}</span>
            <select onchange="onModelSelect(this.value)">
              <option value="" ${{curMod===''?'selected':''}}>✨ Auto-Discover (VRAM / default)</option>
              <option value="qwen3.5:9b-q3_k_xl" ${{curMod==='qwen3.5:9b-q3_k_xl'?'selected':''}}>qwen3.5:9b-q3_k_xl (5.1 GB · 25 tok/s · 131K)</option>
              <option value="qwen3.8:27b-iq2_xxs" ${{curMod==='qwen3.8:27b-iq2_xxs'?'selected':''}}>qwen3.8:27b-iq2_xxs (7.2 GB · 9.9 tok/s · 32K)</option>
              <option value="qwen3:8b" ${{curMod==='qwen3:8b'?'selected':''}}>qwen3:8b (5.2 GB · 28.6 tok/s · 32K)</option>
              <option value="qwen2.5:1.5b" ${{curMod==='qwen2.5:1.5b'?'selected':''}}>qwen2.5:1.5b (1.0 GB · fast)</option>
              <option value="__custom__" ${{isCustom?'selected':''}}>✏️ Custom...</option>
            </select>
            <input id="active_model" value="${{esc(curMod)}}" placeholder="Custom model ID" oninput="CFG.active_model=this.value.trim()" style="margin-top:4px; display:${{isCustom?'block':'none'}};" />
          </label>
          <label><span class="lbl-head">${{L.ctxCapLbl}} ${{tip(L.ctxCapTip)}}</span>
            <select onchange="CFG.max_context_window=Number(this.value)">
              ${{[32768, 65536, 131072, 200000].map((v) => `<option value="${{v}}" ${{Number(CFG.max_context_window||200000)===v?'selected':''}}>${{v.toLocaleString('en-US')}} tokens</option>`).join('')}}
            </select>
          </label>
          <label><span class="lbl-head">${{L.urlLbl}} ${{tip(L.urlTip)}}</span>
            <input value="${{esc(rObj.base_url || '')}}" oninput="syncRunnerField('base_url', this.value)" />
          </label>
        </div>
      </div>`;
    }}

    function renderTokenModule() {{
      const L = I18N[LANG] || I18N.it;
      const rep = CFG.report || {{}};
      const rLang = rep.language || 'auto';
      return `<div class="card">
        ${{renderModuleHeader('token_analytics', L.tokDoc, L.tokTitle)}}
        <div class="grid">
          <label class="row-chk"><input type="checkbox" ${{rep.auto_report!==false?'checked':''}} onchange="setCfgPath('report','auto_report',this.checked)" /> <span>${{L.autoRep}}</span></label>
          <label><span class="lbl-head">${{L.repLangLbl}} ${{tip(L.repLangTip)}}</span>
            <select onchange="setCfgPath('report','language',this.value)">
              <option value="auto" ${{rLang==='auto'?'selected':''}}>auto (context-aware / task lang)</option>
              <option value="it" ${{rLang==='it'?'selected':''}}>it (Italiano)</option>
              <option value="en" ${{rLang==='en'?'selected':''}}>en (English)</option>
              <option value="es" ${{rLang==='es'?'selected':''}}>es (Español)</option>
            </select>
          </label>
          <label><span class="lbl-head">${{L.rangeLbl}} ${{tip(L.rangeTip)}}</span>
            <select onchange="setCfgPath('report','default_range_days',Number(this.value))">
              <option value="7" ${{Number(rep.default_range_days)==7?'selected':''}}>7 days</option>
              <option value="30" ${{Number(rep.default_range_days??30)==30?'selected':''}}>30 days</option>
              <option value="90" ${{Number(rep.default_range_days)==90?'selected':''}}>90 days</option>
              <option value="0" ${{Number(rep.default_range_days)===0?'selected':''}}>All history</option>
            </select>
          </label>
          <label><span class="lbl-head">${{L.retLbl}} ${{tip(L.retTip)}}</span>
            <input type="number" min="1" max="3650" value="${{Number(rep.retention_days ?? 90)}}" oninput="setCfgPath('report','retention_days',Number(this.value||90))" />
          </label>
          <label><span class="lbl-head">${{L.presetLbl}} ${{tip(L.presetTip)}}</span>
            <select onchange="setCfgPath('report','cloud_preset',this.value)">
              ${{['cloud_standard', 'openai_gpt', 'claude_sonnet', 'gemini_pro', 'deepseek_v3'].map((p) => `<option value="${{p}}" ${{(rep.cloud_preset||'cloud_standard')===p?'selected':''}}>${{p}}</option>`).join('')}}
            </select>
          </label>
        </div>
      </div>`;
    }}

    function renderSkillEngineModule() {{
      const L = I18N[LANG] || I18N.it;
      const sk = CFG.skills || {{}};
      const preset = Number(sk.min_terms || 4) >= 6 ? 'strict' : (Number(sk.min_terms || 4) <= 3 ? 'permissive' : 'balanced');
      return `<div class="card">
        ${{renderModuleHeader('skills_hub', L.skDoc, L.skTitle)}}
        <div class="grid">
          <label class="row-chk"><input type="checkbox" ${{sk.auto_compile!==false?'checked':''}} onchange="setCfgPath('skills','auto_compile',this.checked)" /> <span>${{L.autoSk}}</span></label>
          <label><span class="lbl-head">${{L.skPresetLbl}} ${{tip(L.skPresetTip)}}</span>
            <select onchange="applySkillPreset(this.value)">
              <option value="balanced" ${{preset==='balanced'?'selected':''}}>Balanced (min_terms=4 · overlap=3 · Jaccard=0.30)</option>
              <option value="strict" ${{preset==='strict'?'selected':''}}>Strict (min_terms=6 · overlap=2 · Jaccard=0.25)</option>
              <option value="permissive" ${{preset==='permissive'?'selected':''}}>Permissive (min_terms=3 · overlap=4 · Jaccard=0.40)</option>
            </select>
          </label>
        </div>
      </div>`;
    }}

    function renderPrivacyModule() {{
      const L = I18N[LANG] || I18N.it;
      const ps = CFG.privacy_sanitizer || {{}};
      const sanMod = ps.sanitizer_model || 'qwen2.5:1.5b';
      const sanKnown = ['qwen2.5:1.5b', 'qwen3.5:9b-q3_k_xl', 'qwen3:8b', 'qwen3.8:27b-iq2_xxs'];
      const sanCustom = !sanKnown.includes(sanMod);
      const customTerms = (ps.custom_terms || []).join(', ');
      const profs = CFG.privacy_profiles || {{}};
      const profCards = Object.entries(profs).map(([name, p]) => {{
        const activeCats = new Set(p.strip_categories || []);
        const chips = ALL_CATS.map((cat) =>
          `<label class="chip"><input type="checkbox" ${{activeCats.has(cat) ? 'checked' : ''}} onchange="toggleCat('${{name}}','${{cat}}',this.checked)" />${{cat}}</label>`
        ).join('');
        return `<div class="prof-card">
          <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; margin-bottom:8px; flex-wrap:wrap;">
            <strong style="color:var(--accent);">${{esc(name)}}</strong>
            <span style="font-size:0.78rem; color:var(--muted);">${{esc(p.description || '')}}</span>
          </div>
          <div class="grid">
            <label class="row-chk"><input type="checkbox" ${{p.local_only?'checked':''}} onchange="CFG.privacy_profiles['${{name}}'].local_only=this.checked" /> ${{L.prLocalOnly}}</label>
            <label class="row-chk"><input type="checkbox" ${{p.summary_only?'checked':''}} onchange="CFG.privacy_profiles['${{name}}'].summary_only=this.checked" /> ${{L.prSumOnly}}</label>
            <label class="row-chk"><input type="checkbox" ${{p.strip_metadata?'checked':''}} onchange="CFG.privacy_profiles['${{name}}'].strip_metadata=this.checked" /> ${{L.prStripMeta}}</label>
            <label class="row-chk"><input type="checkbox" ${{p.use_local_llm?'checked':''}} onchange="CFG.privacy_profiles['${{name}}'].use_local_llm=this.checked" /> ${{L.prUseLlm}}</label>
            <label class="row-chk"><input type="checkbox" ${{p.redact?'checked':''}} onchange="CFG.privacy_profiles['${{name}}'].redact=this.checked" /> ${{L.prRedact}}</label>
          </div>
          <div style="font-size:0.76rem; color:var(--muted); margin-top:8px;">${{L.catsLbl}}</div>
          <div class="chips">${{chips}}</div>
        </div>`;
      }}).join('');
      return `<div class="card">
        ${{renderModuleHeader('privacy_sanitizer', L.prDoc, L.prTitle)}}
        <div class="grid" style="margin-bottom:14px;">
          <label><span class="lbl-head">${{L.sanModelLbl}} ${{tip(L.sanModelTip)}}</span>
            <select onchange="onSanModelSelect(this.value)">
              <option value="qwen2.5:1.5b" ${{sanMod==='qwen2.5:1.5b'?'selected':''}}>qwen2.5:1.5b (fast offline filter)</option>
              <option value="qwen3.5:9b-q3_k_xl" ${{sanMod==='qwen3.5:9b-q3_k_xl'?'selected':''}}>qwen3.5:9b-q3_k_xl (high accuracy)</option>
              <option value="qwen3:8b" ${{sanMod==='qwen3:8b'?'selected':''}}>qwen3:8b</option>
              <option value="qwen3.8:27b-iq2_xxs" ${{sanMod==='qwen3.8:27b-iq2_xxs'?'selected':''}}>qwen3.8:27b-iq2_xxs</option>
              <option value="__custom__" ${{sanCustom?'selected':''}}>✏️ Custom...</option>
            </select>
            <input id="sanitizer_model_custom" value="${{esc(sanMod)}}" placeholder="Custom sanitizer model ID" oninput="setCfgPath('privacy_sanitizer','sanitizer_model',this.value.trim())" style="margin-top:4px; display:${{sanCustom?'block':'none'}};" />
          </label>
          <label class="row-chk"><input type="checkbox" ${{ps.enable_person_name_heuristic!==false?'checked':''}} onchange="setCfgPath('privacy_sanitizer','enable_person_name_heuristic',this.checked)" /> <span>${{L.personHeur}}</span></label>
        </div>
        <label style="margin-bottom:14px;"><span class="lbl-head">${{L.customTermsLbl}} ${{tip(L.customTermsTip)}}</span>
          <textarea oninput="updateCustomTerms(this.value)" placeholder="Carlo Cancellieri, Client Corp, Project Phoenix">${{esc(customTerms)}}</textarea>
        </label>
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; flex-wrap:wrap; gap:8px;">
          <strong style="font-size:0.9rem; color:var(--accent);">Privacy Profiles</strong>
          <button class="btn btn-primary" onclick="addPrivacyProfile()">${{L.addTier}}</button>
        </div>
        ${{profCards}}
      </div>`;
    }}

    function renderSimpleModule(modKey, docHtml, titleText) {{
      return `<div class="card">${{renderModuleHeader(modKey, docHtml, titleText)}}</div>`;
    }}

    function renderApp() {{
      const L = I18N[LANG] || I18N.it;
      const sidebar = MOD_ORDER.map((k) => {{
        const active = SELECTED_MOD === k ? 'active' : '';
        if (k === 'all') {{
          return `<button class="mod-btn ${{active}}" onclick="SELECTED_MOD='all'; renderApp();"><span>${{L.allLabel}}</span></button>`;
        }}
        const m = modMeta(k);
        const pill = m.enabled ? `<span class="badge-on">${{L.on}}</span>` : `<span class="badge-off">${{L.off}}</span>`;
        return `<button class="mod-btn ${{active}}" onclick="SELECTED_MOD='${{k}}'; renderApp();"><span>${{m.icon}} ${{esc(m.title)}}</span>${{pill}}</button>`;
      }}).join('');

      const panels = [];
      if (SELECTED_MOD === 'all' || SELECTED_MOD === 'context_window') panels.push(renderContextModule());
      if (SELECTED_MOD === 'all' || SELECTED_MOD === 'wiki_mcp') panels.push(renderSimpleModule('wiki_mcp', L.wkDoc, L.wkTitle));
      if (SELECTED_MOD === 'all' || SELECTED_MOD === 'privacy_sanitizer') panels.push(renderPrivacyModule());
      if (SELECTED_MOD === 'all' || SELECTED_MOD === 'skills_hub') panels.push(renderSkillEngineModule());
      if (SELECTED_MOD === 'all' || SELECTED_MOD === 'token_analytics') panels.push(renderTokenModule());
      if (SELECTED_MOD === 'all' || SELECTED_MOD === 'permission_gate') panels.push(renderSimpleModule('permission_gate', L.pgDoc, L.pgTitle));

      document.getElementById('app').innerHTML = `
        <div class="top">
          <div>
            <h1>${{L.title}}</h1>
            <div class="desc" style="margin:4px 0 0;">
              <span>${{L.sub}}</span> ·
              {nav_links}
            </div>
          </div>
          <div style="display:flex; gap:8px; flex-wrap:wrap; align-items:center;">
            <button class="btn" onclick="toggleLang()">${{LANG === 'it' ? '🇮🇹 IT' : '🇬🇧 EN'}}</button>
            <label class="btn" style="flex-direction:row; cursor:pointer;">📂 <span>${{L.import}}</span><input type="file" accept=".json" onchange="importJson(event)" style="display:none;" /></label>
            <button class="btn" onclick="downloadJson()">⬇️ ${{L.download}}</button>
            <button class="btn btn-emerald" onclick="saveDirectToDisk()">💾 ${{L.save}}</button>
          </div>
        </div>
        <div class="status" id="save-status">${{esc(SAVE_MSG)}}</div>
        <div class="layout">
          <aside class="sidebar">${{sidebar}}</aside>
          <main>${{panels.join('')}}</main>
        </div>`;
    }}

    window.toggleLang = function() {{
      LANG = LANG === 'it' ? 'en' : 'it';
      localStorage.setItem('cortical_lang', LANG);
      renderApp();
    }};
    window.applyLang = renderApp;
    window.populateForm = renderApp;
    window.syncFromForm = function() {{ /* Live-bound to CFG */ }};

    window.saveDirectToDisk = async function() {{
      const L = I18N[LANG] || I18N.it;
      const text = JSON.stringify(CFG, null, 2) + '\\n';
      if (window.showSaveFilePicker) {{
        try {{
          const handle = await window.showSaveFilePicker({{
            suggestedName: 'cortical.config.json',
            types: [{{ description: 'JSON Config', accept: {{ 'application/json': ['.json'] }} }}],
          }});
          const w = await handle.createWritable();
          await w.write(text);
          await w.close();
          SAVE_MSG = L.savedDisk;
          const st = document.getElementById('save-status');
          if (st) st.textContent = SAVE_MSG;
          return;
        }} catch (e) {{
          if (e.name === 'AbortError') return;
        }}
      }}
      downloadJson();
    }};

    window.downloadJson = function() {{
      const L = I18N[LANG] || I18N.it;
      const blob = new Blob([JSON.stringify(CFG, null, 2) + '\\n'], {{ type: 'application/json' }});
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'cortical.config.json';
      a.click();
      SAVE_MSG = L.downloaded;
      const st = document.getElementById('save-status');
      if (st) st.textContent = SAVE_MSG;
    }};

    window.importJson = function(ev) {{
      const L = I18N[LANG] || I18N.it;
      const file = ev.target.files?.[0];
      if (!file) return;
      file.text().then((txt) => {{
        CFG = JSON.parse(txt);
        SAVE_MSG = L.imported;
        renderApp();
      }});
    }};

    renderApp();
  </script>
</body>
</html>
"""


def render_static_help_html(public_docs: bool = False) -> str:
    """Renders a detailed, bilingual (IT/EN) zero-server Module Documentation & Reference page."""
    nav_links = _topbar_nav_html(is_help=True, public_docs=public_docs)
    return f"""<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Cortical Help &amp; Module Documentation (Zero-Server)</title>
  <style>
    :root {{ --bg:#0b1120; --card:#131c2e; --border:#24324a; --text:#e2e8f0; --muted:#94a3b8; --accent:#38bdf8; --emerald:#34d399; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; background:var(--bg); color:var(--text); line-height:1.6; }}
    .wrap {{ width:100%; max-width:1100px; margin:0 auto; padding:24px 20px 64px; }}
    .top {{ display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; margin-bottom:20px; }}
    .btn {{ padding:7px 12px; border-radius:8px; border:1px solid var(--border); background:var(--card); color:var(--text); cursor:pointer; font-weight:600; font-size:0.84rem; text-decoration:none; }}
    .card {{ background:var(--card); border:1px solid var(--border); border-radius:12px; padding:18px; margin-bottom:16px; }}
    .card h2 {{ margin:0 0 8px; font-size:1.1rem; color:var(--accent); }}
    code, pre {{ background:#090e1a; border:1px solid var(--border); border-radius:6px; padding:2px 6px; font-size:0.82rem; color:var(--emerald); }}
    pre {{ padding:12px; overflow-x:auto; color:#cbd5e1; }}
    ul {{ margin:8px 0 0 18px; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="top">
      <div>
        <h1 id="h-title">❓ Cortical Guida Completa Moduli (Zero-Server)</h1>
        <div style="font-size:0.84rem; color:var(--muted);">
          {nav_links}
        </div>
      </div>
      <button class="btn" id="btn-lang" onclick="toggleLang()">🇮🇹 IT</button>
    </div>

    <div id="content-it">
      <div class="card"><h2>1. Architettura Zero-Server &amp; 6 Moduli Indipendenti</h2><p>Cortical non richiede demoni attivi né porte aperte. Ogni modulo è opzionale e isolato (configurabile da <a href="./settings.html">Configurazione</a> via <code>cortical.config.json</code> + <code>cortical.config.d/*.json</code>): <b>Context Auto-Scaler</b> (<code>cortical.config</code>), <b>4-Tier Merkle Wiki MCP</b> (<code>cortical.wiki.mcp_server</code>), <b>Local Privacy Sanitizer</b> (<code>cortical.privacy_sanitizer</code>), <b>Cortical Skill Engine</b> (<code>cortical.skills_hub</code>), <b>Token Analytics &amp; ROI</b> (<code>cortical.token_analytics</code>) e <b>Permission Gate</b> (<code>cortical.permission_gate</code>).</p></div>
      <div class="card"><h2>2. Runner Pluggabili &amp; Contesto Dinamico (200k)</h2><p>Scegli tra <code>ollama</code>, <code>llama_cpp</code>, <code>mlx_lm</code> o server OpenAI-compatible. Il contesto si scala sulla RAM libera reale fino al tetto configurabile (default <code>200,000</code> token), con <code>keep_alive: 90s</code> per non saturare la VRAM.</p></div>
      <div class="card"><h2>3. Token Report, Risparmi Reali &amp; Lingua Adattiva</h2><ul><li><b>[1] Remote:</b> somma di <code>input_tokens</code>, <code>cache_read_tokens</code> e <code>output_tokens</code> dai transcript locali (cached su mtime+size per millisecondi di latenza).</li><li><b>[2] Locale &amp; Memoria 3+1:</b> mostra esplicitamente sia i token che i <b>dollari risparmiati</b> sia dall'offload locale sia dal riuso memoria 3+1 (sintesi, insight, skill).</li><li><b>[3] Lingua:</b> impostando <code>report.language = "auto"</code>, il report si adatta alla lingua del task in chat (oppure usa <code>--lang it|en|es</code>).</li></ul></div>
      <div class="card"><h2>4. Privacy Sanitizer, Custom Terms &amp; Modello Dedicato</h2><p>Puoi personalizzare lista di nomi/cognomi/clienti (<code>custom_terms</code>), abilitare l'euristica automatica <code>[PERSON_NAME_N]</code> e scegliere un modello locale dedicato (es. <code>qwen2.5:1.5b</code>) per riscrivere quasi-identificatori offline prima di qualsiasi invio al cloud.</p><pre>PYTHONPATH=src python3 -m cortical.cli sanitize documento.docx --profile low --json</pre></div>
      <div class="card"><h2>5. Cortical Skill Engine &amp; Token Saver</h2><p><code>cortical-token-saver</code> è la skill utente che istruisce gli agenti cloud a delegare letture e sintesi al livello <code>light/medium</code> del server MCP e alle run locali. <b>Cortical Skill Engine</b> consolida automaticamente le skill <code>learned-*</code> apprese in memoria evitando duplicati.</p></div>
    </div>

    <div id="content-en" style="display:none;">
      <div class="card"><h2>1. Zero-Server &amp; 6 Isolated Modules</h2><p>Cortical runs with zero background servers or open ports. Every module is optional and isolated (configurable in <a href="./settings.html">Settings</a> via <code>cortical.config.json</code> + <code>cortical.config.d/*.json</code>): <b>Context Auto-Scaler</b> (<code>cortical.config</code>), <b>4-Tier Merkle Wiki MCP</b> (<code>cortical.wiki.mcp_server</code>), <b>Local Privacy Sanitizer</b> (<code>cortical.privacy_sanitizer</code>), <b>Cortical Skill Engine</b> (<code>cortical.skills_hub</code>), <b>Token Analytics &amp; ROI</b> (<code>cortical.token_analytics</code>), and <b>Permission Gate</b> (<code>cortical.permission_gate</code>).</p></div>
      <div class="card"><h2>2. Pluggable Runners &amp; 200k Dynamic Context</h2><p>Switch between <code>ollama</code>, <code>llama_cpp</code>, <code>mlx_lm</code>, or OpenAI-compatible endpoints. Context auto-scales to live free RAM up to the configurable cap (default <code>200,000</code> tokens) with <code>keep_alive: 90s</code>.</p></div>
      <div class="card"><h2>3. Token Report, Per-Row Savings &amp; Context-Aware Language</h2><ul><li><b>[1] Remote:</b> sum of <code>input_tokens</code>, <code>cache_read_tokens</code>, and <code>output_tokens</code> from local transcripts (accelerated via mtime+size cache).</li><li><b>[2] Local &amp; 3+1 Memory:</b> displays both token and <b>USD savings</b> explicitly on local offload and 3+1 memory rows.</li><li><b>[3] Language:</b> with <code>report.language = "auto"</code>, in-chat Markdown reports match the task language (or force via <code>--lang it|en|es</code>).</li></ul></div>
      <div class="card"><h2>4. Privacy Sanitizer, Custom Terms &amp; Sanitizer Model</h2><p>Define custom names/surnames/client codenames (<code>custom_terms</code>), toggle automatic <code>[PERSON_NAME_N]</code> name detection, and choose a dedicated local sanitizer model (e.g. <code>qwen2.5:1.5b</code>) for offline GDPR quasi-identifier rewriting.</p><pre>PYTHONPATH=src python3 -m cortical.cli sanitize document.docx --profile low --json</pre></div>
      <div class="card"><h2>5. Cortical Skill Engine &amp; Token Saver</h2><p><code>cortical-token-saver</code> instructs cloud LLMs to offload context exploration to Cortical's 4-tier Merkle MCP and local runners. <b>Cortical Skill Engine</b> consolidates recurring workflows into unified <code>learned-*</code> skills without bloat.</p></div>
    </div>
  </div>
  <script>
    let LANG = localStorage.getItem('cortical_lang') || 'it';
    function applyLang() {{
      document.getElementById('content-it').style.display = LANG === 'it' ? 'block' : 'none';
      document.getElementById('content-en').style.display = LANG === 'en' ? 'block' : 'none';
      document.getElementById('h-title').textContent = LANG === 'it' ? '❓ Cortical Guida Completa Moduli (Zero-Server)' : '❓ Cortical Help & Module Docs (Zero-Server)';
      document.getElementById('btn-lang').textContent = LANG === 'it' ? '🇮🇹 IT' : '🇬🇧 EN';
    }}
    function toggleLang() {{
      LANG = LANG === 'it' ? 'en' : 'it';
      localStorage.setItem('cortical_lang', LANG);
      applyLang();
    }}
    applyLang();
  </script>
</body>
</html>
"""


def export_static_settings_and_help(
    output_dir: Path,
    config: Optional[dict[str, Any]] = None,
    public_docs: bool = False,
) -> tuple[Path, Path]:
    """Writes `settings.html` and `help.html` inside `output_dir` (set `public_docs=True` for sanitized GitHub Pages output)."""
    out_dir = Path(output_dir)
    s_path = export_static_settings_dashboard(out_dir / "settings.html", config=config, public_docs=public_docs)
    return s_path, out_dir / "help.html"


def export_static_settings_dashboard(
    output_path: Path,
    config: Optional[dict[str, Any]] = None,
    public_docs: bool = False,
) -> Path:
    """Writes `settings.html` and sibling `help.html` to disk."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_static_settings_html(config, public_docs=public_docs), encoding="utf-8")
    (out.parent / "help.html").write_text(render_static_help_html(public_docs=public_docs), encoding="utf-8")
    return out
