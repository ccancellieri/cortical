"""Self-contained, Offline-Capable, Zero-Server 6-Domain Control Plane UI (`settings.html`).

Zero daemons, zero open ports, zero CDN dependencies.
Hydrates from embedded `window.__CORTICAL_SNAPSHOT__`, supports optional Chromium File System Access API
folder linking + JSON snapshot import, direct client-side local runtime probes (with CORS/offline fallback),
and cross-platform (`macOS` / `Linux` / `Windows` PowerShell) CLI apply scripts.
"""

from __future__ import annotations

import json
from typing import Any


def render_zero_server_settings_html(snapshot: dict[str, Any]) -> str:
    """Renders the complete standalone `settings.html` hydrated with `snapshot`."""
    snap_json = json.dumps(snapshot, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Cortical — Zero-Server Control Plane</title>
  <style>
    :root {{
      --bg: #070b14; --bg-elev: #0d1424; --card: #121c30; --card-hover: #182540;
      --border: #233250; --border-strong: #354b76; --text: #e6eef8; --muted: #93a6c2;
      --accent: #38bdf8; --accent-soft: rgba(56,189,248,0.14);
      --ok: #34d399; --ok-soft: rgba(52,211,153,0.14);
      --warn: #fbbf24; --warn-soft: rgba(251,191,36,0.15);
      --err: #f87171; --err-soft: rgba(248,113,113,0.15);
      --violet: #a78bfa; --violet-soft: rgba(167,139,250,0.15);
      --radius: 10px;
      --mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Inter, sans-serif;
    }}
    * {{ box-sizing: border-box; }}
    html, body {{ height: 100%; margin: 0; background: var(--bg); color: var(--text); font-family: var(--sans); font-size: 14px; line-height: 1.5; }}
    button, input, select, textarea {{ font-family: inherit; font-size: inherit; color: var(--text); }}
    :focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; }}
    .sr-only {{ position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0,0,0,0); }}

    .shell {{ display: grid; grid-template-rows: 58px 1fr; grid-template-columns: 256px 1fr; min-height: 100vh; }}
    .topbar {{
      grid-column: 1 / -1; display: flex; align-items: center; justify-content: space-between; gap: 10px;
      padding: 0 18px; background: var(--bg-elev); border-bottom: 1px solid var(--border); position: sticky; top: 0; z-index: 40;
    }}
    .brand {{ display: flex; align-items: center; gap: 10px; font-weight: 700; font-size: 15px; }}
    .brand-mark {{ width: 28px; height: 28px; border-radius: 8px; background: linear-gradient(135deg,#38bdf8,#818cf8); display: grid; place-items: center; font-weight: 800; color: #070b14; }}
    .topbar-pills {{ display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }}

    .sidebar {{
      background: var(--bg-elev); border-right: 1px solid var(--border); padding: 14px 10px;
      display: flex; flex-direction: column; justify-content: space-between; gap: 14px;
    }}
    .nav-list {{ display: flex; flex-direction: column; gap: 4px; }}
    .nav-sec {{ font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); padding: 6px 10px; font-weight: 700; }}
    .nav-btn {{
      display: flex; align-items: center; gap: 9px; padding: 9px 12px; border-radius: 8px; border: 1px solid transparent;
      background: transparent; color: var(--muted); cursor: pointer; text-align: left; font-weight: 600; transition: 0.12s;
    }}
    .nav-btn:hover {{ background: var(--card); color: var(--text); }}
    .nav-btn.active {{ background: var(--accent-soft); color: var(--accent); border-color: rgba(56,189,248,0.35); }}
    .nav-foot {{ border-top: 1px solid var(--border); padding: 10px 8px 0; font-size: 12px; color: var(--muted); display: flex; flex-direction: column; gap: 6px; }}
    .nav-foot a {{ color: var(--accent); text-decoration: none; }}
    .nav-foot a:hover {{ text-decoration: underline; }}

    .main {{ padding: 22px 26px 96px; overflow-y: auto; max-width: 1320px; width: 100%; }}

    .pill {{
      display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px; border-radius: 999px;
      font-size: 12px; font-weight: 600; border: 1px solid var(--border); background: var(--card); white-space: nowrap;
    }}
    .pill.ok {{ color: var(--ok); background: var(--ok-soft); border-color: rgba(52,211,153,0.35); }}
    .pill.warn {{ color: var(--warn); background: var(--warn-soft); border-color: rgba(251,191,36,0.35); }}
    .pill.err {{ color: var(--err); background: var(--err-soft); border-color: rgba(248,113,113,0.35); }}
    .pill.info {{ color: var(--accent); background: var(--accent-soft); border-color: rgba(56,189,248,0.35); }}
    .pill.violet {{ color: var(--violet); background: var(--violet-soft); border-color: rgba(167,139,250,0.35); }}

    .btn {{
      display: inline-flex; align-items: center; justify-content: center; gap: 6px; padding: 7px 13px; border-radius: 8px;
      border: 1px solid var(--border-strong); background: var(--card); color: var(--text); cursor: pointer; font-weight: 600; font-size: 13px; transition: 0.12s;
    }}
    .btn:hover:not(:disabled) {{ background: var(--card-hover); border-color: var(--accent); }}
    .btn:disabled {{ opacity: 0.45; cursor: not-allowed; }}
    .btn.primary {{ background: #0284c7; border-color: #38bdf8; color: #fff; }}
    .btn.primary:hover:not(:disabled) {{ background: #0369a1; }}
    .btn.sm {{ padding: 4px 9px; font-size: 12px; }}
    .btn.danger {{ background: var(--err-soft); border-color: rgba(248,113,113,0.5); color: #fca5a5; }}

    .input, .select, .textarea {{
      width: 100%; padding: 8px 10px; border-radius: 8px; border: 1px solid var(--border-strong);
      background: #080e1c; color: var(--text); font-size: 13.5px;
    }}
    .input.invalid, .select.invalid {{ border-color: var(--err); }}
    .textarea {{ min-height: 82px; font-family: var(--mono); font-size: 12px; resize: vertical; }}
    .field {{ display: flex; flex-direction: column; gap: 5px; margin-bottom: 13px; }}
    .field label {{ font-weight: 600; font-size: 13px; }}
    .hint {{ font-size: 12px; color: var(--muted); }}
    .err-msg {{ font-size: 12px; color: var(--err); }}

    .page-head {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 18px; flex-wrap: wrap; }}
    .page-head h1 {{ margin: 0; font-size: 20px; }}
    .page-head p {{ margin: 4px 0 0; color: var(--muted); font-size: 13px; }}
    .card {{ background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px 18px; margin-bottom: 16px; }}
    .card-head {{ display: flex; justify-content: space-between; align-items: center; gap: 10px; margin-bottom: 12px; flex-wrap: wrap; }}
    .card-head h2 {{ margin: 0; font-size: 15px; display: flex; align-items: center; gap: 8px; }}
    .grid-2 {{ display: grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap: 14px; }}
    .grid-3 {{ display: grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap: 12px; }}
    .grid-4 {{ display: grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: 12px; }}
    .mono {{ font-family: var(--mono); font-size: 12px; }}
    .muted {{ color: var(--muted); }}
    .kpi {{ background: #0a1120; border: 1px solid var(--border); border-radius: 8px; padding: 12px 14px; }}
    .kpi-val {{ font-size: 22px; font-weight: 800; margin-top: 2px; }}

    .tabs {{ display: flex; gap: 6px; border-bottom: 1px solid var(--border); margin-bottom: 16px; flex-wrap: wrap; }}
    .tab-btn {{ padding: 8px 13px; background: transparent; border: none; border-bottom: 2px solid transparent; color: var(--muted); font-weight: 600; cursor: pointer; }}
    .tab-btn.active {{ color: var(--accent); border-bottom-color: var(--accent); }}

    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ padding: 9px 10px; border-bottom: 1px solid var(--border); text-align: left; vertical-align: middle; }}
    th {{ font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); }}
    tr.clickable {{ cursor: pointer; }}
    tr.clickable:hover td {{ background: var(--card-hover); }}

    .bar-track {{ width: 100%; height: 12px; background: #070c18; border: 1px solid var(--border); border-radius: 999px; overflow: hidden; display: flex; }}
    .bar-seg {{ height: 100%; transition: width 0.25s; }}
    .code-pre {{ background: #060912; border: 1px solid var(--border); border-radius: 8px; padding: 11px; overflow: auto; font-family: var(--mono); font-size: 12px; white-space: pre-wrap; word-break: break-word; margin: 0; }}

    .dock {{
      position: fixed; bottom: 16px; left: 274px; right: 26px; max-width: 1260px; z-index: 50;
      background: #0f1b33; border: 1px solid var(--warn); border-radius: var(--radius); padding: 12px 16px;
      display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap;
      box-shadow: 0 12px 32px rgba(0,0,0,0.55);
    }}
    .backdrop {{ position: fixed; inset: 0; background: rgba(3,6,14,0.72); backdrop-filter: blur(2px); z-index: 80; display: flex; align-items: center; justify-content: center; padding: 16px; }}
    .modal {{ background: var(--bg-elev); border: 1px solid var(--border-strong); border-radius: 12px; width: 100%; max-width: 640px; max-height: 86vh; overflow-y: auto; padding: 20px; }}
    .drawer-bg {{ position: fixed; inset: 0; background: rgba(3,6,14,0.65); z-index: 75; display: flex; justify-content: flex-end; }}
    .drawer {{ width: min(600px, 95vw); height: 100%; background: var(--bg-elev); border-left: 1px solid var(--border-strong); padding: 20px; overflow-y: auto; display: flex; flex-direction: column; gap: 14px; }}
    .cmd-list {{ list-style: none; margin: 10px 0 0; padding: 0; max-height: 320px; overflow-y: auto; }}
    .cmd-item {{ display: flex; justify-content: space-between; align-items: center; padding: 9px 12px; border-radius: 8px; cursor: pointer; border: 1px solid transparent; }}
    .cmd-item:hover, .cmd-item.selected {{ background: var(--accent-soft); border-color: rgba(56,189,248,0.35); }}
    .kbd {{ font-family: var(--mono); font-size: 11px; padding: 2px 6px; border-radius: 5px; border: 1px solid var(--border-strong); background: var(--bg); color: var(--muted); }}
    .toasts {{ position: fixed; bottom: 88px; right: 18px; z-index: 95; display: flex; flex-direction: column; gap: 8px; max-width: 380px; }}
    .toast {{ padding: 10px 14px; border-radius: 8px; border: 1px solid var(--border-strong); background: var(--bg-elev); box-shadow: 0 8px 24px rgba(0,0,0,0.45); display: flex; gap: 8px; font-size: 13px; }}
    .toast.ok {{ border-color: var(--ok); }} .toast.err {{ border-color: var(--err); }} .toast.warn {{ border-color: var(--warn); }}
    .main {{ padding-bottom: 136px; }}
    .sidebar {{ position: sticky; top: 54px; align-self: start; max-height: calc(100vh - 54px); overflow-y: auto; }}
    .kpi, .mono {{ overflow-wrap: anywhere; word-break: break-word; }}
    .pill {{ max-width: 100%; }}

    @media (max-width: 980px) {{
      .shell {{ grid-template-columns: 1fr; }}
      .sidebar {{ flex-direction: row; overflow-x: auto; border-right: none; border-bottom: 1px solid var(--border); padding: 8px; }}
      .nav-list {{ flex-direction: row; }}
      .nav-foot, .nav-sec {{ display: none; }}
      .grid-2, .grid-3, .grid-4 {{ grid-template-columns: 1fr; }}
      .dock {{ left: 16px; right: 16px; }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <!-- Persistent Top Context Bar -->
    <header class="topbar" role="banner">
      <div class="brand">
        <div class="brand-mark" aria-hidden="true">C</div>
        <span>Cortical</span>
        <span class="pill info">Zero-Server</span>
      </div>
      <div class="topbar-pills">
        <span id="pill-hw" class="pill info">💻 Detecting...</span>
        <button class="btn sm" onclick="openBridgeModal()" title="Link local Cortical folder or load JSON snapshot">📂 Load Snapshot / Link Folder</button>
        <button id="pill-harnesses" class="pill ok" onclick="setView('harnesses')">🔗 0/8 Harnesses</button>
        <button id="pill-vault" class="pill violet" onclick="setView('vault')">🛡️ Vault</button>
        <button class="btn sm" onclick="openCmdPalette()" aria-label="Open Command Palette">⌘K <span class="kbd">Ctrl+K</span></button>
      </div>
    </header>

    <!-- 6-Domain Navigation Sidebar -->
    <aside class="sidebar" aria-label="Primary Navigation">
      <nav class="nav-list">
        <div class="nav-sec">Control Plane</div>
        <button class="nav-btn active" data-view="overview" onclick="setView('overview')">🏠 Overview &amp; Quick Setup</button>
        <button class="nav-btn" data-view="harnesses" onclick="setView('harnesses')">🔌 Services &amp; Harnesses</button>
        <button class="nav-btn" data-view="models" onclick="setView('models')">🧠 Models &amp; Hardware Tuner</button>
        <button class="nav-btn" data-view="vault" onclick="setView('vault')">🛡️ Memory &amp; Privacy Vault</button>
        <button class="nav-btn" data-view="settings" onclick="setView('settings')">⚙️ Settings &amp; Config Composer</button>
        <button class="nav-btn" data-view="reports" onclick="setView('reports')">📊 Usage, ROI &amp; Reports</button>
      </nav>
      <div class="nav-foot">
        <div><strong>Zero-Server · Stdlib Only</strong></div>
        <div><a href="./index.html">🌐 Project Home</a> · <a href="./help.html">❓ Help</a></div>
        <div><a href="https://github.com/ccancellieri/cortical/issues" target="_blank" rel="noopener">📌 GitHub ADRs &amp; Issues</a></div>
      </div>
    </aside>

    <main id="main" class="main" tabindex="-1"></main>
  </div>

  <!-- Sticky Unsaved Changes Dock -->
  <div id="dirty-dock" class="dock" style="display:none;" role="status" aria-live="polite">
    <div><strong>⚠ Unsaved Config Changes</strong> <span id="dirty-info" class="muted" style="margin-left:8px;"></span></div>
    <div style="display:flex;gap:8px;flex-wrap:wrap;">
      <button class="btn sm" onclick="discardConfig()">Discard</button>
      <button class="btn sm" onclick="openDiffModal()">View Diff</button>
      <button class="btn sm" onclick="downloadPlan()" title="Atomic bundle for: cortical apply cortical-plan.json">⬇️ cortical-plan.json</button>
      <button class="btn sm" onclick="copyPlanForClipboardApply()" title="Copies plan JSON; then run: cortical apply --from-clipboard">📋 Copy Plan → apply --from-clipboard</button>
      <button class="btn sm primary" id="btn-save-fs" onclick="saveToLinkedFolder()">💾 Save to Linked Folder</button>
    </div>
  </div>

  <div id="modal-root"></div>
  <div id="drawer-root"></div>
  <div id="cmd-root"></div>
  <div id="toasts" class="toasts" aria-live="polite"></div>
  <input id="snap-file-input" type="file" accept=".json" style="display:none;" />

<script>
window.__CORTICAL_SNAPSHOT__ = {snap_json};

const ST = {{
  snap: JSON.parse(JSON.stringify(window.__CORTICAL_SNAPSHOT__)),
  view: 'overview',
  settingsTab: 'general',
  targetOs: window.__CORTICAL_SNAPSHOT__?.meta?.os || 'macos',
  savedCfg: JSON.parse(JSON.stringify(window.__CORTICAL_SNAPSHOT__?.config || {{}})),
  draftCfg: JSON.parse(JSON.stringify(window.__CORTICAL_SNAPSHOT__?.config || {{}})),
  cfgErrors: {{}},
  dirHandle: null,
  probeResults: {{}},
  drawerItem: null,
  pendingModels: [],
  planHarnesses: [],
  privacySampleText: '',
  lastFocus: null,
  cmdOpen: false,
  cmdQuery: '',
  cmdIdx: 0,
}};

const esc = (s) => String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
const deepClone = (x) => JSON.parse(JSON.stringify(x));

function toast(kind, msg) {{
  const box = document.getElementById('toasts');
  const el = document.createElement('div');
  el.className = 'toast ' + kind;
  el.innerHTML = `<span aria-hidden="true">${{kind==='ok'?'✓':(kind==='err'?'⚠':(kind==='warn'?'⚡':'ℹ'))}}</span><div>${{esc(msg)}}</div>`;
  box.appendChild(el);
  setTimeout(() => el.remove(), 4200);
}}

function copyText(txt, label) {{
  if (navigator.clipboard) navigator.clipboard.writeText(txt).catch(() => {{}});
  toast('ok', 'Copied: ' + (label || 'command'));
}}

function downloadFile(name, content, mime='text/plain') {{
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([content], {{ type: mime }}));
  a.download = name;
  a.click();
}}

function cliPrefix() {{
  return ST.targetOs === 'windows' ? 'cortical' : 'cortical';
}}

function setView(v, opts={{}}) {{
  ST.view = v;
  if (opts.settingsTab) ST.settingsTab = opts.settingsTab;
  document.querySelectorAll('.nav-btn').forEach((b) => b.classList.toggle('active', b.dataset.view === v));
  renderAll();
}}

// ---- Persistent Top Context Bar ----
function renderTopBar() {{
  const s = ST.snap;
  const hw = s.hardware || {{}};
  const cls = hw.classification || {{}};
  const isDemo = s.meta?.mode === 'demo' && !ST.dirHandle;
  const hwEl = document.getElementById('pill-hw');
  hwEl.className = 'pill ' + (isDemo ? 'warn' : 'info');
  hwEl.innerHTML = isDemo
    ? `<span>⚡ Demo / Unlinked Mode (${{esc(cls.tier || 'tier_1b')}})</span>`
    : `<span>💻 ${{esc((s.meta?.os||'macos').toUpperCase())}} • ${{esc(cls.label || cls.tier || 'Tier 1B')}} (${{hw.total_ram_gb || 16}} GB)</span>`;

  const hs = s.harnesses || [];
  const linked = hs.filter((h) => h.linked).length;
  const drift = hs.filter((h) => h.drift).length;
  const hEl = document.getElementById('pill-harnesses');
  hEl.className = 'pill ' + (drift > 0 ? 'warn' : (linked > 0 ? 'ok' : 'info'));
  hEl.innerHTML = `<span>${{drift > 0 ? '⚡' : '✓'}} ${{linked}}/8 Harnesses Linked${{drift > 0 ? ' • ' + drift + ' Drift' : ''}}</span>`;

  const v = s.vault || {{}};
  const vEl = document.getElementById('pill-vault');
  vEl.className = 'pill ' + (v.watch_queue_count > 0 ? 'warn' : 'violet');
  vEl.innerHTML = `<span>🛡️ Vault: ${{esc(v.default_policy || 'auto')}} • ${{(v.aliases||[]).length}} Aliases • Watch: ${{v.watch_queue_count || 0}}</span>`;
}}

function renderAll() {{
  renderTopBar();
  const m = document.getElementById('main');
  if (ST.view === 'overview') m.innerHTML = renderOverview();
  else if (ST.view === 'harnesses') m.innerHTML = renderHarnesses();
  else if (ST.view === 'models') m.innerHTML = renderModels();
  else if (ST.view === 'vault') m.innerHTML = renderVault();
  else if (ST.view === 'settings') m.innerHTML = renderSettings();
  else if (ST.view === 'reports') m.innerHTML = renderReports();
  renderDirtyDock();
}}

function applyDemoPreset(presetId) {{
  const hw = ST.snap.hardware || {{}};
  const c = ST.draftCfg;
  if (!c.orchestrator) c.orchestrator = {{}};
  if (!c.models_by_role) c.models_by_role = {{}};
  if (presetId === 'tier_1a_hybrid') {{
    hw.total_ram_gb = 16.0;
    hw.free_ram_gb = 9.5;
    hw.unified_memory = false;
    hw.vram_gb = 4.0;
    hw.gpu_name = 'Hybrid Laptop GPU (4 GB VRAM)';
    hw.dynamic_num_ctx = 32768;
    hw.classification = {{ tier: 'tier_1a_hybrid_4gb', label: 'Tier 1A · Hybrid 16 GB RAM + 4 GB VRAM' }};
    c.models_by_role.router = 'qwen2.5:3b';
    c.models_by_role.daily_coder = 'qwen3.5:9b-q3_k_xl';
    c.models_by_role.deep_reasoner = 'qwen3.5:9b-q3_k_xl';
    c.orchestrator.mode = 'local';
    c.orchestrator.provider = 'router';
    c.orchestrator.model = 'cortical-fast';
    c.orchestrator.api_key_env = '';
    toast('ok', 'Loaded Preset A: Tier 1A Hybrid Laptop (16 GB RAM + 4 GB VRAM, swap-free 32K ctx)');
  }} else if (presetId === 'tier_1b_unified') {{
    hw.total_ram_gb = 16.0;
    hw.free_ram_gb = 10.5;
    hw.unified_memory = true;
    hw.vram_gb = 11.2;
    hw.gpu_name = 'Apple Silicon Unified (16 GB)';
    hw.dynamic_num_ctx = 65536;
    hw.classification = {{ tier: 'tier_1b_unified_16_24', label: 'Tier 1B · Unified 16 GB (27B Variable-Quant)' }};
    c.models_by_role.router = 'qwen2.5:1.5b';
    c.models_by_role.daily_coder = 'qwen3.5:9b-q3_k_xl';
    c.models_by_role.deep_reasoner = 'qwen3.8:27b-iq2_xxs';
    c.orchestrator.mode = 'local';
    c.orchestrator.provider = 'router';
    c.orchestrator.model = 'cortical-deep';
    c.orchestrator.api_key_env = '';
    if (ST.snap.orchestration?.context_profile) {{
      ST.snap.orchestration.context_profile.auto_max_num_ctx = 65536;
      ST.snap.orchestration.context_profile.adaptive_timeout_sec = 600;
    }}
    toast('ok', 'Loaded Preset B: Tier 1B Unified 16 GB (27B UD-IQ2_XXS @ 65,536 ctx, 600s timeout)');
  }} else if (presetId === 'hybrid_remote_guard') {{
    c.orchestrator.mode = 'remote';
    c.orchestrator.provider = 'gemini';
    c.orchestrator.model = 'gemini-2.5-pro';
    c.orchestrator.api_key_env = 'GEMINI_API_KEY';
    c.orchestrator.endpoint = 'https://generativelanguage.googleapis.com/v1beta/openai/';
    c.orchestrator.local_first_delegation = true;
    c.orchestrator.strict_remote_privacy = true;
    toast('ok', 'Loaded Preset C: Hybrid Remote Supervisor (GEMINI_API_KEY env only) + fail_closed Local Workers');
  }}
  ST.snap.hardware = hw;
  validateCfg();
  renderAll();
}}

// =========================================================================
// VIEW 1: OVERVIEW & QUICK SETUP
// =========================================================================
function renderOverview() {{
  const s = ST.snap;
  const hs = s.harnesses || [];
  const linked = hs.filter((h) => h.linked).length;
  const driftList = hs.filter((h) => h.drift);
  const v = s.vault || {{}};
  const bench = s.bench || {{}};
  const toonSave = bench.compression_before_vs_after?.saving_vs_compact_pct ?? 64.2;

  return `
    <div class="page-head">
      <div>
        <h1>🏠 Overview &amp; Quick Setup</h1>
        <p>Zero-server Control Plane for 8 coding harnesses, variable-quant local models, dynamic Privacy Vault, and lossless TOON compression.</p>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;">
        <select class="select" style="width:auto;" onchange="ST.targetOs=this.value;renderAll()" aria-label="Target OS for CLI commands">
          <option value="macos" ${{ST.targetOs==='macos'?'selected':''}}>🍎 macOS</option>
          <option value="linux" ${{ST.targetOs==='linux'?'selected':''}}>🐧 Linux</option>
          <option value="windows" ${{ST.targetOs==='windows'?'selected':''}}>🪟 Windows (PowerShell)</option>
        </select>
        <button class="btn primary" onclick="copyText('cortical doctor && cortical sync --dry-run', 'doctor + dry-run')">📋 Copy Preflight Command</button>
      </div>
    </div>

    ${{driftList.length ? `
    <div class="card" style="border-color:var(--warn);background:rgba(251,191,36,0.06);">
      <div class="card-head" style="margin-bottom:6px;">
        <h2>⚡ Drift Alert — ${{driftList.length}} Installed Harness(es) Out of Sync</h2>
        <button class="btn sm primary" onclick="copyText('cortical sync', 'cortical sync')">📋 Copy cortical sync</button>
      </div>
      <div class="hint">Detected unlinked/drifted harnesses: <strong>${{driftList.map((d)=>esc(d.id)).join(', ')}}</strong>. Open <em>Services &amp; Harnesses</em> to inspect diffs and apply cleanly.</div>
    </div>` : ''}}

    <div class="grid-4" style="margin-bottom:16px;">
      <div class="kpi"><div class="hint">Hardware Tier</div><div class="kpi-val">${{esc(s.hardware?.classification?.tier || 'tier_1b')}}</div><div class="hint">${{s.hardware?.total_ram_gb}} GB RAM · num_ctx ${{s.hardware?.dynamic_num_ctx}}</div></div>
      <div class="kpi"><div class="hint">Harnesses Linked</div><div class="kpi-val">${{linked}} / 8</div><div class="hint">${{driftList.length}} drift · ${{(s.backups||[]).length}} rollback snapshots</div></div>
      <div class="kpi"><div class="hint">Privacy Vault</div><div class="kpi-val">${{(v.aliases||[]).length}} Aliases</div><div class="hint">${{v.memory_budget_pct}}% of ≤${{v.max_context_share_pct}}% ctx budget</div></div>
      <div class="kpi"><div class="hint">TOON Compression</div><div class="kpi-val" style="color:var(--ok);">-${{toonSave}}%</div><div class="hint">vs compact JSON · 0 cloud tokens</div></div>
    </div>

    <div class="card">
      <div class="card-head">
        <h2>⚡ 1-Click Interactive Browser Demo Presets (Zero Install)</h2>
        <span class="pill ok">100% Client-Side · 0 CDNs</span>
      </div>
      <div class="grid-3">
        <div class="kpi">
          <span class="pill info">Preset A · Tier 1A Hybrid</span>
          <h3 style="margin:8px 0 4px;">16 GB RAM + 4 GB VRAM Laptop</h3>
          <p class="hint"><code>qwen2.5:3b</code> in VRAM + <code>qwen3.5:9b-q3_k_xl</code> hybrid offload @ <code>32,768</code> ctx.</p>
          <button class="btn sm" onclick="applyDemoPreset('tier_1a_hybrid'); setView('models')">▶ Load Tier 1A Preset</button>
        </div>
        <div class="kpi">
          <span class="pill ok">Preset B · Tier 1B Unified</span>
          <h3 style="margin:8px 0 4px;">16 GB Apple Silicon + 27B XXS</h3>
          <p class="hint"><code>qwen3.8:27b-iq2_xxs</code> @ <code>65,536</code> ctx (<code>9.08 GB</code> Metal) preventing <code>4096</code> clipping.</p>
          <button class="btn sm primary" onclick="applyDemoPreset('tier_1b_unified'); setView('models')">▶ Load Tier 1B 27B Preset</button>
        </div>
        <div class="kpi">
          <span class="pill warn">Preset C · Hybrid Remote Guard</span>
          <h3 style="margin:8px 0 4px;">Remote Supervisor + fail_closed Vault</h3>
          <p class="hint"><code>GEMINI_API_KEY</code> env-only remote orchestrator + local offload + <code>-78.12%</code> TOON savings.</p>
          <button class="btn sm" onclick="applyDemoPreset('hybrid_remote_guard'); setView('vault')">▶ Load Hybrid Guard Preset</button>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-head"><h2>🚀 Guided 3-Step Zero-Server Launchpad</h2></div>
      <div class="grid-3">
        <div class="kpi">
          <span class="pill info">Step 1 · Hardware</span>
          <h3 style="margin:8px 0 4px;">Inspect Tier &amp; Models</h3>
          <p class="hint">Verify swap-free RAM/VRAM headroom and dynamic <code>num_ctx</code> without silent Ollama 4096 clipping.</p>
          <button class="btn sm" onclick="setView('models')">Open Models &amp; Tuner →</button>
        </div>
        <div class="kpi">
          <span class="pill ok">Step 2 · 8 Harnesses</span>
          <h3 style="margin:8px 0 4px;">Link Harnesses &amp; OSS Tools</h3>
          <p class="hint">Sync Antigravity, pi, Claude Code, Codex, OpenCode, OpenClaw, dsh &amp; Unsloth with timestamped rollback.</p>
          <button class="btn sm primary" onclick="setView('harnesses')">Open Services &amp; Harnesses →</button>
        </div>
        <div class="kpi">
          <span class="pill violet">Step 3 · Zero-PII</span>
          <h3 style="margin:8px 0 4px;">Protect Private Docs</h3>
          <p class="hint">Ingest files into <code>@private:&lt;alias&gt;</code> with 3-channel egress protection and offline <code>cortical watch</code>.</p>
          <button class="btn sm" onclick="setView('vault')">Open Privacy Vault →</button>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <h2>📚 Synchronized Architecture Decision Records (docs/adr ↔ GitHub)</h2>
        <span class="pill info">${{(s.adrs||[]).length}} ADRs indexed</span>
      </div>
      <table>
        <thead><tr><th>ADR</th><th>Title</th><th>Status</th><th>GitHub</th></tr></thead>
        <tbody>
          ${{(s.adrs||[]).map((a) => `
            <tr>
              <td class="mono"><strong>${{esc(a.id)}}</strong></td>
              <td>${{esc(a.title)}}<div class="hint">${{esc(a.summary)}}</div></td>
              <td><span class="pill ok">✓ ${{esc(a.status)}}</span></td>
              <td class="mono">${{esc(a.issue || '—')}}</td>
            </tr>
          `).join('') || '<tr><td colspan="4" class="muted">No ADRs found in docs/adr/.</td></tr>'}}
        </tbody>
      </table>
    </div>
  `;
}}

// =========================================================================
// VIEW 2: SERVICES & HARNESSES (8 Harnesses + Composed OSS Tools + Drawer)
// =========================================================================
function lifecycleBadge(lc) {{
  const map = {{
    linked_in_sync: ['ok', '✓ Linked & In-Sync'],
    config_drift: ['warn', '⚡ Config Drift'],
    installed_unlinked: ['info', '○ Installed (Unlinked)'],
    not_detected: ['err', '— Not Detected'],
  }};
  const [c, lbl] = map[lc] || map.not_detected;
  return `<span class="pill ${{c}}">${{lbl}}</span>`;
}}

function renderHarnesses() {{
  const hs = ST.snap.harnesses || [];
  const comps = ST.snap.composers || [];
  const backups = ST.snap.backups || [];

  return `
    <div class="page-head">
      <div>
        <h1>🔌 Services &amp; 8 Coding Harnesses</h1>
        <p>Install, configure, preview idempotent diffs, and maintain linked state across all 8 harnesses and composed OSS tools.</p>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;">
        <button class="btn" onclick="copyText('cortical sync --dry-run', 'sync --dry-run')">👁 Copy Dry-Run</button>
        <button class="btn" onclick="ST.planHarnesses = (ST.snap.harnesses||[]).filter((h)=>h.drift||h.lifecycle==='installed_unlinked').map((h)=>h.id); renderAll(); toast('ok', ST.planHarnesses.length + ' harness(es) needing repair added to apply plan')">🩹 Plan Repair for All Drift</button>
        <button class="btn" onclick="copyText(VERIFY_REFRESH_CMD, 'verify & refresh')">✅ Verify &amp; Refresh Snapshot</button>
        <button class="btn primary" onclick="copyText('cortical sync', 'cortical sync')">⟳ Copy Sync All</button>
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <h2>8 Coding Harnesses Matrix</h2>
        ${{backups.length ? `
          <div style="display:flex;gap:6px;align-items:center;">
            <select id="rb-select" class="select" style="width:auto;" aria-label="Select backup snapshot for rollback">
              ${{backups.map((b) => `<option value="${{esc(b)}}">${{esc(b)}}</option>`).join('')}}
            </select>
            <button class="btn sm danger" onclick="copyText('cortical sync --rollback ' + document.getElementById('rb-select').value, 'rollback command')">↺ Copy Rollback</button>
          </div>` : '<span class="hint">Run <code>cortical sync</code> locally to create rollback snapshots.</span>'}}
      </div>
      <div style="overflow-x:auto;">
        <table>
          <thead><tr><th>Harness</th><th>Lifecycle State</th><th>Channel 3 Pre-Send</th><th>Primary Config Path</th><th>Action</th></tr></thead>
          <tbody>
            ${{hs.map((h) => `
              <tr class="clickable" onclick="openServiceDrawer('harness','${{esc(h.id)}}')">
                <td><strong>${{esc(h.id)}}</strong></td>
                <td>${{lifecycleBadge(h.lifecycle)}}</td>
                <td>${{h.presend_verified ? '<span class="pill ok">✓ 100% Verified</span>' : '<span class="pill info">○ Channels 1 &amp; 2</span>'}}</td>
                <td class="mono muted">${{esc(h.config_path)}}</td>
                <td><button class="btn sm" onclick="event.stopPropagation();openServiceDrawer('harness','${{esc(h.id)}}')">Inspect &amp; Link →</button></td>
              </tr>
            `).join('')}}
          </tbody>
        </table>
      </div>
    </div>

    <div class="card">
      <div class="card-head"><h2>Composed Best-of-Breed OSS Tools</h2></div>
      <div class="grid-3">
        ${{comps.map((c) => `
          <div class="kpi" style="display:flex;flex-direction:column;justify-content:space-between;gap:10px;">
            <div>
              <div style="display:flex;justify-content:space-between;align-items:center;gap:6px;">
                <strong>${{esc(c.name)}}</strong>
                <span class="pill ${{c.installed ? 'ok' : 'warn'}}">${{c.installed ? '✓ Installed' : '○ Not Installed'}}</span>
              </div>
              <div class="hint" style="margin-top:6px;">${{esc(c.role)}}</div>
            </div>
            <button class="btn sm" onclick="openServiceDrawer('composer','${{esc(c.id)}}')">Install / Verify Recipe →</button>
          </div>
        `).join('')}}
      </div>
    </div>
  `;
}}

function openServiceDrawer(kind, id) {{
  const item = kind === 'harness'
    ? (ST.snap.harnesses || []).find((x) => x.id === id)
    : (ST.snap.composers || []).find((x) => x.id === id);
  if (!item) return;
  ST.drawerItem = {{ kind, item }};
  renderServiceDrawer();
}}

function renderServiceDrawer() {{
  const root = document.getElementById('drawer-root');
  if (!ST.drawerItem) {{ root.innerHTML = ''; return; }}
  const {{ kind, item }} = ST.drawerItem;
  const recipe = (item.recipes || {{}})[ST.targetOs] || (item.recipes || {{}}).macos || '';
  const syncDry = kind === 'harness' ? `cortical sync --harness ${{item.id}} --dry-run` : recipe;
  const syncApply = kind === 'harness' ? `cortical sync --harness ${{item.id}}` : recipe;
  const diffPreview = kind === 'harness'
    ? `// Target: ${{item.config_path}}\n// Idempotent merge (preserves all existing user keys):\n{{\n  "mcpServers": {{\n    "cortical": {{\n      "command": "python3",\n      "args": ["-m", "cortical.mcp_server"]\n    }}\n  }}\n}}`
    : `// Verification & Install (${{ST.targetOs}}):\n${{recipe}}`;

  const realChanges = (kind === 'harness' && Array.isArray(item.planned_changes) && item.planned_changes.length)
    ? item.planned_changes.map((c) => `
        <div style="border:1px solid var(--border);border-radius:8px;padding:10px;margin-top:8px;background:#09101f;">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:6px;flex-wrap:wrap;">
            <span class="mono"><strong>${{esc(c.path)}}</strong></span>
            <span class="pill ${{c.action==='unchanged'?'ok':'warn'}}">${{esc(c.action.toUpperCase())}} · ${{esc(c.kind)}}</span>
          </div>
          <div class="hint" style="margin:4px 0 6px;">${{esc(c.detail)}}</div>
          <details><summary style="cursor:pointer;color:var(--accent);font-size:12px;">Preview planned content</summary><pre class="code-pre" style="margin-top:6px;">${{esc(c.preview)}}</pre></details>
        </div>`).join('')
    : `<pre class="code-pre" style="margin-top:6px;">${{esc(diffPreview)}}</pre>`;

  root.innerHTML = `
    <div class="drawer-bg" onclick="if(event.target===this)closeDrawer()">
      <div class="drawer" role="dialog" aria-modal="true" aria-label="Service Install & Link Drawer">
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <h2 style="margin:0;">🔌 ${{esc(item.name || item.id)}}</h2>
          <button class="btn sm" onclick="closeDrawer()">✕ Close</button>
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;">
          ${{kind === 'harness' ? lifecycleBadge(item.lifecycle) : `<span class="pill ${{item.installed ? 'ok' : 'warn'}}">${{item.installed ? '✓ Installed' : '○ Not Installed'}}</span>`}}
          <span class="pill info">OS: ${{esc(ST.targetOs)}}</span>
        </div>
        <div>
          <strong>OS-Aware Install / Verify Recipe (${{esc(ST.targetOs)}})</strong>
          <pre class="code-pre" style="margin-top:6px;">${{esc(recipe)}}</pre>
          <button class="btn sm" style="margin-top:6px;" data-copy="${{esc(recipe)}}" onclick="copyText(this.dataset.copy, 'install recipe')">📋 Copy Recipe</button>
        </div>
        <div>
          <strong>Idempotent Config Diff Preview (${{kind === 'harness' && (item.planned_changes||[]).length ? 'Live plan_sync dry-run' : 'Template'}})</strong>
          ${{realChanges}}
        </div>
        ${{kind === 'harness' ? `
        <div style="display:flex;gap:8px;flex-wrap:wrap;">
          <button class="btn sm" data-copy="${{esc(syncDry)}}" onclick="copyText(this.dataset.copy, 'dry-run')">📋 Copy Dry-Run</button>
          <button class="btn sm primary" data-copy="${{esc(syncApply)}}" onclick="copyText(this.dataset.copy, 'sync apply')">📋 Copy Sync Apply</button>
          <button class="btn sm" onclick="togglePlanHarness('${{esc(item.id)}}')">${{ST.planHarnesses.includes(item.id) ? '✓ In Apply Plan (remove)' : '＋ Add to Apply Plan'}}</button>
        </div>` : ''}}
        <div>
          <strong>Guided ${{kind === 'harness' ? lifecycleTitle(item.lifecycle) : (item.installed ? 'Verify' : 'Install')}} Playbook</strong>
          <ol style="margin:8px 0 0;padding-left:20px;display:flex;flex-direction:column;gap:8px;">
            ${{repairSteps(kind, item, recipe).map((s) => `
              <li><div>${{esc(s.label)}}</div>
                <div style="display:flex;gap:6px;align-items:flex-start;margin-top:4px;">
                  <pre class="code-pre" style="flex:1;">${{esc(s.cmd)}}</pre>
                  <button class="btn sm" aria-label="Copy step command" data-copy="${{esc(s.cmd)}}" onclick="copyText(this.dataset.copy, 'step')">📋</button>
                </div></li>`).join('')}}
          </ol>
        </div>
        <div class="kpi">
          <strong>✅ Verify &amp; Refresh Snapshot</strong>
          <div class="hint" style="margin:4px 0 6px;">Confirms recovery and re-hydrates this dashboard with fresh state.</div>
          <button class="btn sm primary" onclick="copyText(VERIFY_REFRESH_CMD, 'verify & refresh')">📋 Copy Verify &amp; Refresh</button>
        </div>
      </div>
    </div>
  `;
}}
function lifecycleTitle(lc) {{
  return {{ not_detected: 'Install', installed_unlinked: 'Link', config_drift: 'Repair', linked_in_sync: 'Verify' }}[lc] || 'Install';
}}
function repairSteps(kind, item, recipe) {{
  const win = ST.targetOs === 'windows';
  const which = (bin) => win ? `Get-Command ${{bin}} -ErrorAction SilentlyContinue` : `command -v ${{bin}}`;
  if (kind !== 'harness') {{
    const bin = {{ serena: 'uvx', rtk: 'rtk', pinchtab: 'npx', context_mode: 'npx', router: 'litellm' }}[item.id] || item.id;
    return [
      {{ label: 'Check whether the binary is already on PATH', cmd: which(bin) }},
      {{ label: item.installed ? 'Re-run the verify recipe' : 'Install with the OS-specific recipe', cmd: recipe }},
      {{ label: 'Confirm Cortical detects it', cmd: 'cortical tools status' }},
    ];
  }}
  const id = item.id;
  const steps = [];
  if (item.lifecycle === 'not_detected') steps.push({{ label: 'Install the harness', cmd: recipe.split(/ && |; /)[0] }});
  if (item.lifecycle === 'config_drift') steps.push({{ label: 'Preview exactly what drifted (no writes)', cmd: `cortical sync --harness ${{id}} --dry-run` }});
  steps.push({{ label: item.lifecycle === 'linked_in_sync' ? 'Re-verify (idempotent, no-op if in sync)' : 'Link / repair with a timestamped backup', cmd: `cortical sync --harness ${{id}}` }});
  steps.push({{ label: 'If anything looks wrong, restore the snapshot printed by the previous step', cmd: 'cortical sync --rollback <backup_id>' }});
  return steps;
}}

function closeDrawer() {{ ST.drawerItem = null; document.getElementById('drawer-root').innerHTML = ''; }}

// =========================================================================
// VIEW 3: MODELS & HARDWARE AUTO-TUNER (Tier Bar, Role Slots, Local Probes)
// =========================================================================
function setOrchMode(mode) {{
  const c = ST.draftCfg;
  if (!c.orchestrator) c.orchestrator = {{}};
  c.orchestrator.mode = mode;
  if (mode === 'local') {{
    const p = (ST.snap.orchestration?.presets || {{}}).local_deep || {{}};
    c.orchestrator.provider = p.provider || 'router';
    c.orchestrator.model = p.model || 'cortical-deep';
    c.orchestrator.api_key_env = '';
    c.orchestrator.endpoint = p.endpoint || '';
  }} else if (!['gemini','anthropic','openai','deepseek','openrouter','custom'].includes(c.orchestrator.provider)) {{
    setOrchPreset('gemini');
    return;
  }}
  validateCfg();
  renderAll();
}}

function setOrchPreset(key) {{
  const presets = ST.snap.orchestration?.presets || {{}};
  const p = presets[key];
  if (!p) return;
  const c = ST.draftCfg;
  if (!c.orchestrator) c.orchestrator = {{}};
  c.orchestrator.mode = p.mode || 'local';
  c.orchestrator.provider = p.provider || 'router';
  c.orchestrator.model = p.model || 'cortical-deep';
  c.orchestrator.api_key_env = p.api_key_env || '';
  c.orchestrator.endpoint = p.endpoint || '';
  if (p.mode === 'remote') {{
    c.orchestrator.local_first_delegation = true;
    c.orchestrator.strict_remote_privacy = true;
  }}
  validateCfg();
  renderAll();
}}

function syncAllHarnessesInPlan() {{
  const allIds = (ST.snap.harnesses || []).map((h) => h.id);
  ST.planHarnesses = allIds.length ? allIds : ['antigravity','pi','opencode','openclaw','codex','claude-code','dsh','unsloth-studio'];
  toast('ok', 'Added all ' + ST.planHarnesses.length + ' harnesses to Apply Plan.');
  renderAll();
}}

function renderOrchestrationCard() {{
  const c = ST.draftCfg;
  const o = c.orchestrator || {{}};
  const snapOrch = ST.snap.orchestration || {{}};
  const presets = snapOrch.presets || {{}};
  const cp = snapOrch.context_profile || {{}};
  const isRemote = o.mode === 'remote' || ['gemini','anthropic','openai','deepseek','openrouter','custom'].includes(o.provider);
  const autoCtx = cp.auto_max_num_ctx || ST.snap.hardware?.dynamic_num_ctx || 65536;
  const effCtx = (o.context_strategy === 'fixed' && o.fixed_num_ctx) ? o.fixed_num_ctx : autoCtx;
  const effTimeout = (o.timeout_sec && o.timeout_sec > 0) ? o.timeout_sec : (cp.adaptive_timeout_sec || (isRemote ? 180 : 600));
  const curPresetKey = Object.keys(presets).find((k) => presets[k].provider === o.provider && (presets[k].mode || 'local') === (isRemote ? 'remote' : 'local')) || (isRemote ? 'custom' : 'local_deep');
  const errMsg = (k) => ST.cfgErrors[k] ? `<div class="err-msg">⚠ ${{esc(ST.cfgErrors[k])}}</div>` : '';
  const matrix = snapOrch.harness_matrix || [];

  return `
    <div class="card">
      <div class="card-head">
        <div>
          <h2>🧭 Hybrid Orchestrator, Auto-Context Ceiling &amp; 8-Harness Matrix</h2>
          <div class="hint">Select a Local or Remote Orchestrator while keeping worker offload local and private vault data fail-closed.</div>
        </div>
        <span class="pill ${{isRemote ? 'warn' : 'ok'}}">${{isRemote ? '🛡️ Remote Orchestrator • Strict Zero-Leakage fail_closed Guard Active' : '🔒 100% Local Air-Gapped • Zero Cloud Egress'}}</span>
      </div>

      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px;">
        <button class="btn sm ${{!isRemote ? 'primary' : ''}}" onclick="setOrchMode('local')">🔒 100% Local Air-Gapped</button>
        <button class="btn sm ${{isRemote ? 'primary' : ''}}" onclick="setOrchMode('remote')">🌐 Hybrid Remote Orchestrator + Local Workers</button>
        <button class="btn sm" style="margin-left:auto;" onclick="syncAllHarnessesInPlan()">＋ Sync All 8 Harnesses in Apply Plan</button>
      </div>

      <div class="grid-3" style="margin-bottom:12px;">
        <div class="field">
          <label for="orch-preset">Orchestrator Provider Preset</label>
          <select id="orch-preset" class="select" onchange="setOrchPreset(this.value)">
            ${{Object.entries(presets).map(([k, p]) => `<option value="${{esc(k)}}" ${{curPresetKey===k?'selected':''}}>${{esc(p.label || k)}}</option>`).join('')}}
          </select>
          <div class="hint">Presets never store keys — remote providers reference env var names only.</div>
        </div>
        <div class="field">
          <label for="orch-model">Orchestrator Model</label>
          <input id="orch-model" class="input mono" value="${{esc(o.model || 'cortical-deep')}}" oninput="setCfg('orchestrator.model', this.value)" />
          <div class="hint">e.g. <code>cortical-deep</code>, <code>gemini-2.5-pro</code>, <code>claude-sonnet-4-5</code>, <code>gpt-5</code>, <code>deepseek-chat</code>.</div>
        </div>
        <div class="field">
          <label for="orch-ctx-strat">Context Window &amp; Timeout Strategy</label>
          <select id="orch-ctx-strat" class="select" onchange="setCfg('orchestrator.context_strategy', this.value); renderAll()">
            <option value="auto_max" ${{o.context_strategy!=='fixed'?'selected':''}}>Auto Max Safe (${{autoCtx}} tok)</option>
            <option value="fixed" ${{o.context_strategy==='fixed'?'selected':''}}>Fixed Context Limit</option>
          </select>
          <div class="hint">Hardware ceiling avoids Ollama 4096 clipping &amp; prevents 300s stream timeouts.</div>
        </div>
      </div>

      <div class="grid-3" style="margin-bottom:12px;">
        ${{isRemote ? `
          <div class="field">
            <label for="orch-env">API Key Environment Variable (Name Only)</label>
            <input id="orch-env" class="input mono ${{ST.cfgErrors.orch_api_key_env?'invalid':''}}" placeholder="GEMINI_API_KEY" value="${{esc(o.api_key_env || '')}}" oninput="setCfg('orchestrator.api_key_env', this.value)" />
            <div class="hint">Only env var names (e.g. <code>GEMINI_API_KEY</code>); never paste raw tokens.</div>
            ${{errMsg('orch_api_key_env')}}
          </div>
          <div class="field">
            <label for="orch-ep">Remote OpenAI-Compatible / Provider Endpoint</label>
            <input id="orch-ep" class="input mono" value="${{esc(o.endpoint || '')}}" oninput="setCfg('orchestrator.endpoint', this.value)" />
          </div>
        ` : `
          <div class="field">
            <label>Active Local Workers</label>
            <div class="hint" style="padding-top:6px;">
              Fast: <code>${{esc(snapOrch.active?.local_workers?.fast || 'qwen3.5:9b-q3_k_xl')}}</code><br/>
              Deep: <code>${{esc(snapOrch.active?.local_workers?.deep || 'qwen3.8:27b-iq2_xxs')}}</code>
            </div>
          </div>
          <div class="field">
            <label>Metal / Unified / VRAM KV Budget</label>
            <div class="hint" style="padding-top:6px;">
              Safe budget: <strong>${{cp.metal_workset_gb ?? '?'}} GB</strong> · Weights: <strong>${{cp.weights_gb ?? '?'}} GB</strong> · KV: <strong>${{cp.kv_budget_gb ?? '?'}} GB</strong>
            </div>
          </div>
        `}}
        <div class="field">
          <label for="orch-timeout">Fixed <code>num_ctx</code> / Timeout Override (sec, 0=Auto)</label>
          <div style="display:flex;gap:8px;">
            <input id="orch-fixed-ctx" type="number" class="input mono ${{ST.cfgErrors.orch_fixed_num_ctx?'invalid':''}}" ${{o.context_strategy==='fixed'?'':'disabled'}} value="${{o.fixed_num_ctx || autoCtx}}" oninput="setCfg('orchestrator.fixed_num_ctx', Number(this.value))" />
            <input id="orch-timeout" type="number" class="input mono ${{ST.cfgErrors.orch_timeout_sec?'invalid':''}}" value="${{o.timeout_sec ?? 0}}" oninput="setCfg('orchestrator.timeout_sec', Number(this.value))" title="Timeout seconds (0 = adaptive ${{effTimeout}}s)" />
          </div>
          <div class="hint">Effective: <code>num_ctx=${{effCtx}}</code> · <code>timeout=${{effTimeout}}s</code> · <code>pressure=${{ST.snap.hardware?.memory_pressure_level ?? 1}}</code></div>
          ${{errMsg('orch_fixed_num_ctx')}}${{errMsg('orch_timeout_sec')}}
        </div>
      </div>

      <div class="grid-2" style="margin-bottom:14px;">
        <label><input type="checkbox" ${{o.local_first_delegation!==false?'checked':''}} onchange="setCfg('orchestrator.local_first_delegation', this.checked)" /> <strong>Local-First Delegation:</strong> Route repo scans, Serena lookups, RTK/TOON compaction, NER &amp; workers to local models</label>
        <label><input type="checkbox" ${{o.strict_remote_privacy!==false?'checked':''}} onchange="setCfg('orchestrator.strict_remote_privacy', this.checked); renderAll()" /> <strong>Zero-Leakage Remote Guard:</strong> Enforce <code>fail_closed</code> across MCP Vault, Sync Rules &amp; Pre-Send Intercept</label>
      </div>

      <div style="overflow-x:auto;">
        <table class="tbl">
          <thead>
            <tr><th>Harness</th><th>Binding</th><th>Effective <code>num_ctx</code></th><th>Timeout</th><th>Delegation</th><th>Privacy Guard</th><th>Targets</th></tr>
          </thead>
          <tbody>
            ${{matrix.map((row) => {{
              const liveBind = (isRemote ? 'Remote (' : 'Local (') + (o.provider || 'router') + ')';
              const liveModel = o.model || row.orchestrator_model || 'cortical-deep';
              const liveDeleg = o.local_first_delegation !== false ? 'local_first_offload' : 'direct';
              const liveGuard = !isRemote
                ? 'Air-Gapped Local Only (zero cloud egress)'
                : (row.privacy_guard.includes('verified pre-send') ? 'fail_closed + verified pre-send hook + MCP vault block' : 'fail_closed MCP & sync guard');
              return `
              <tr>
                <td><strong>${{esc(row.harness)}}</strong></td>
                <td class="mono" style="font-size:12px;">${{esc(liveBind)}} · ${{esc(liveModel)}}</td>
                <td class="mono">${{effCtx}}</td>
                <td class="mono">${{effTimeout}}s</td>
                <td><span class="pill info">${{esc(liveDeleg)}}</span></td>
                <td><span class="pill ${{isRemote ? 'warn' : 'ok'}}">${{esc(liveGuard)}}</span></td>
                <td class="hint mono" style="font-size:11px;">${{esc(row.target_files)}}</td>
              </tr>`;
            }}).join('')}}
          </tbody>
        </table>
      </div>
    </div>`;
}}

function renderModels() {{
  const hw = ST.snap.hardware || {{}};
  const cfg = ST.draftCfg;
  const roles = cfg.models_by_role || {{}};
  const cat = ST.snap.models?.catalog || [];
  const totalRam = hw.total_ram_gb || 16;
  const usedRam = Math.max(0, totalRam - (hw.free_ram_gb || 8));
  const usedPct = Math.round((usedRam / totalRam) * 100);
  const vramPct = Math.min(100 - usedPct, Math.round(((hw.vram_gb || 0) / totalRam) * 100));

  const probes = ST.probeResults || {{}};
  const probeRow = (key, label, url) => {{
    const p = probes[key];
    return `
      <div class="kpi">
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <strong>${{label}}</strong>
          ${{!p ? '<span class="pill info">○ Not Probed</span>' : (p.ok ? `<span class="pill ok">✓ Online (${{p.ms}} ms)</span>` : `<span class="pill warn">⚡ ${{esc(p.status)}}</span>`)}}
        </div>
        <div class="mono hint" style="margin-top:4px;">${{esc(url)}}</div>
        ${{p ? `<div class="hint" style="margin-top:4px;">${{esc(p.detail)}}</div>` : ''}}
      </div>`;
  }};

  return `
    <div class="page-head">
      <div>
        <h1>🧠 Models &amp; Hardware Auto-Tuner</h1>
        <p>Hardware tier memory budgeting (Tier 0..3, Tier 1A Hybrid 4–6GB VRAM, Tier 1B Unified 27B variable-quant), role slots, and live browser probes.</p>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;">
        <button class="btn primary" id="btn-probe-all" onclick="probeLocalRuntimes()">🧪 Probe Local Services</button>
        <button class="btn" onclick="copyText('cortical tune --apply', 'cortical tune --apply')">⚡ Copy Auto-Tune CLI</button>
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <h2>Hardware Tier &amp; Swap-Free Memory Budget</h2>
        <span class="pill ok">${{esc(hw.classification?.label || hw.classification?.tier || 'Tier 1B Unified')}}</span>
      </div>
      <div class="bar-track" aria-label="Memory budget bar">
        <div class="bar-seg" style="width:${{usedPct}}%;background:#64748b;" title="OS & Active Apps"></div>
        <div class="bar-seg" style="width:${{vramPct}}%;background:#38bdf8;" title="Safe GPU/Unified Model Budget"></div>
        <div class="bar-seg" style="width:${{Math.max(0, 100 - usedPct - vramPct)}}%;background:#34d399;" title="Free Headroom"></div>
      </div>
      <div style="display:flex;justify-content:space-between;margin-top:8px;flex-wrap:wrap;gap:8px;" class="hint">
        <span>Total RAM: <strong>${{totalRam}} GB</strong> · Free: <strong>${{hw.free_ram_gb}} GB</strong> · ${{hw.unified_memory ? 'Unified Memory' : 'Discrete VRAM'}}: <strong>${{hw.vram_gb}} GB</strong></span>
        <span>Dynamic <code>num_ctx</code>: <strong>${{hw.dynamic_num_ctx}}</strong> (prevents silent 4096 Ollama clipping)</span>
      </div>
    </div>

    <div class="card">
      <div class="card-head"><h2>Direct Client-Side Local Runtime Probes</h2><span class="hint">Direct browser <code>fetch()</code> · falls back cleanly to <code>cortical doctor</code> on CORS/offline</span></div>
      <div class="grid-3">
        ${{probeRow('ollama', 'Ollama Native', 'http://127.0.0.1:11434/api/tags')}}
        ${{probeRow('litellm', 'Local Router (LiteLLM)', 'http://127.0.0.1:4000/v1/models')}}
        ${{probeRow('unsloth', 'Unsloth Studio', 'http://127.0.0.1:8888/v1/models')}}
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <h2>🎭 Reusable Model Role Registry (Abstracted Across All 8 Harnesses)</h2>
        <span class="pill info">10 Semantic Roles · Never Hardcode Model Tags</span>
      </div>
      <div class="grid-3">
        ${{Object.values(ST.snap.models?.roles || {{}}).map((rm) => {{
          const curVal = (rm.role === 'vision' ? (cfg.privacy?.vision_model || rm.model_id) : (roles[rm.role] || rm.model_id)) || '';
          const targetPath = rm.role === 'vision' ? 'privacy.vision_model' : ('models_by_role.' + rm.role);
          return `
            <div class="kpi">
              <div style="display:flex;justify-content:space-between;align-items:center;gap:6px;">
                <strong>${{esc(rm.label)}}</strong>
                <span class="pill violet mono">@role:${{esc(rm.role)}}</span>
              </div>
              <div class="hint" style="margin:4px 0 8px;">Alias: <code>${{esc(rm.alias)}}</code> · ${{esc(rm.description)}}</div>
              <input class="input mono" value="${{esc(curVal)}}" oninput="setCfg('${{targetPath}}', this.value)" aria-label="${{esc(rm.label)}} model" />
            </div>`;
        }}).join('')}}
      </div>
    </div>

    <div class="card">
      <div class="card-head"><h2>＋ Custom / Variable-Quant Model Builder</h2></div>
      <div class="grid-4">
        <div class="field"><label for="mb-id">Model ID</label><input id="mb-id" class="input mono" placeholder="qwen3.8:27b-iq2_xxs" value="qwen3.8:27b-iq2_xxs" /></div>
        <div class="field"><label for="mb-mem">Memory (GB)</label><input id="mb-mem" type="number" step="0.1" class="input mono" value="7.2" /></div>
        <div class="field"><label for="mb-ctx">Native num_ctx</label><input id="mb-ctx" type="number" class="input mono" value="32768" /></div>
        <div class="field"><label for="mb-quant">Quantization Label</label><input id="mb-quant" class="input" value="Unsloth Dynamic UD-IQ2_XXS" /></div>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;">
        <label><input id="mb-var" type="checkbox" checked /> Variable-Quantization (Unsloth Dynamic)</label>
        <button class="btn primary sm" onclick="copyModelAddCmd()">📋 Copy cortical models add + pull</button>
        <button class="btn sm" onclick="addModelToPlan()">＋ Add to Apply Plan</button>
        ${{ST.pendingModels.length ? `<span class="pill warn">${{ST.pendingModels.length}} model(s) pending in plan</span>` : ''}}
      </div>
    </div>
    ${{renderOrchestrationCard()}}
  `;
}}

function addModelToPlan() {{
  const id = document.getElementById('mb-id').value.trim();
  const mem = Number(document.getElementById('mb-mem').value);
  const ctx = Number(document.getElementById('mb-ctx').value);
  if (!id || !(mem >= 0.1 && mem <= 512) || !(ctx >= 512 && ctx <= 2000000)) {{
    toast('err', 'Invalid model: id required, memory 0.1–512 GB, num_ctx 512–2,000,000.');
    return;
  }}
  ST.pendingModels = ST.pendingModels.filter((m) => m.model_id !== id).concat([{{
    model_id: id, memory_gb: mem, native_ctx: ctx,
    quantization: document.getElementById('mb-quant').value.trim() || 'custom',
    is_variable_quant: document.getElementById('mb-var').checked,
    roles: ['deep_reasoner'], pull_ref: 'ollama pull ' + id,
  }}]);
  toast('ok', 'Added ' + id + ' to apply plan');
  renderAll();
}}

function copyModelAddCmd() {{
  const id = document.getElementById('mb-id').value.trim();
  const mem = document.getElementById('mb-mem').value.trim();
  const ctx = document.getElementById('mb-ctx').value.trim();
  const q = document.getElementById('mb-quant').value.trim();
  const v = document.getElementById('mb-var').checked ? ' --variable' : '';
  const cmd = `cortical models add ${{id}} --mem ${{mem}} --ctx ${{ctx}} --quant "${{q}}"${{v}} && ollama pull ${{id}}`;
  copyText(cmd, 'models add command');
}}

async function probeLocalRuntimes() {{
  const targets = [
    ['ollama', 'http://127.0.0.1:11434/api/tags'],
    ['litellm', 'http://127.0.0.1:4000/v1/models'],
    ['unsloth', 'http://127.0.0.1:8888/v1/models'],
  ];
  toast('info', 'Probing local services from browser...');
  for (const [k, url] of targets) {{
    const t0 = performance.now();
    try {{
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), 2200);
      const r = await fetch(url, {{ signal: ctrl.signal }});
      clearTimeout(timer);
      const ms = Math.round(performance.now() - t0);
      const data = await r.json().catch(() => ({{}}));
      const cnt = (data.models || data.data || []).length;
      ST.probeResults[k] = {{ ok: r.ok, ms, status: r.ok ? 'Online' : ('HTTP ' + r.status), detail: r.ok ? `Reachable (${{cnt}} model(s) exposed)` : `HTTP ${{r.status}}` }};
    }} catch (e) {{
      const ms = Math.round(performance.now() - t0);
      ST.probeResults[k] = {{
        ok: false, ms, status: 'Offline / CORS',
        detail: 'Blocked by CORS or service stopped. Fallback: run `cortical doctor` (or set OLLAMA_ORIGINS=*).',
      }};
    }}
  }}
  renderAll();
}}

// =========================================================================
// VIEW 4: MEMORY & DYNAMIC PRIVACY VAULT
// =========================================================================
function renderVault() {{
  const v = ST.snap.vault || {{}};
  const aliases = v.aliases || [];
  const audit = v.audit_ledger || {{ ok: true, total_entries: 0, blocked_egress_count: 0, head_hash: '' }};
  const liveShare = Number(ST.draftCfg.compression?.max_context_share ?? ((v.max_context_share_pct || 15) / 100));
  const liveCtx = Number(ST.snap.hardware?.dynamic_num_ctx || 65536);
  const liveBudgetTok = Math.max(256, Math.round(liveCtx * liveShare));
  const usedTok = Number(v.memory_used_tokens || 0);
  const pct = Math.round(Math.min(100, (usedTok / Math.max(1, liveBudgetTok)) * 100) * 10) / 10;
  const barColor = pct > 90 ? 'var(--err)' : (pct > 70 ? 'var(--warn)' : 'var(--ok)');
  const auditEntries = Number(audit.total_entries || 0);
  const auditPillCls = audit.ok === false ? 'err' : (auditEntries > 0 ? 'ok' : 'info');
  const auditPillTxt = audit.ok === false ? ('⚠ Tamper at seq #' + audit.broken_at_seq) : (auditEntries > 0 ? '✓ Hash Chain Verified' : '○ Empty / Ready (0 entries)');

  return `
    <div class="page-head">
      <div>
        <h1>🛡️ Memory &amp; Dynamic Privacy Vault</h1>
        <p>Inspect sanitized <code>@private:&lt;alias&gt;</code> entries, monitor the <code>&le; ${{Math.round(liveShare * 100)}}% num_ctx</code> memory budget, and audit 3-channel egress protection.</p>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;">
        <button class="btn" onclick="copyText('cortical vault audit --verify', 'cortical vault audit --verify')">🔐 Verify Audit Ledger</button>
        <button class="btn" onclick="copyText('cortical watch', 'cortical watch')">👁 Copy Watch Queue CLI</button>
        <button class="btn primary" onclick="copyText('cortical ingest /path/to/file.pdf --policy auto --profile medium', 'cortical ingest')">📋 Copy Ingest CLI</button>
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <h2>🔐 Cryptographic SHA-256 Privacy &amp; Fail-Closed Egress Audit Ledger</h2>
        <span class="pill ${{auditPillCls}}">${{auditPillTxt}}</span>
      </div>
      <div class="hint">
        Entries: <strong>${{auditEntries}}</strong> · Blocked Remote Egress Events: <strong>${{audit.blocked_egress_count || 0}}</strong> ·
        Head Hash: <code class="mono">${{esc(String(audit.head_hash || '').slice(0, 16) || 'genesis')}}</code> · Never stores raw PII.
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <h2>Context Budget Gauge (&le; ${{Math.round(liveShare * 100)}}% of ${{liveCtx.toLocaleString()}} num_ctx)</h2>
        <span class="pill ${{pct > 90 ? 'err' : (pct > 70 ? 'warn' : 'ok')}}">${{usedTok}} / ${{liveBudgetTok}} tokens (${{pct}}%)</span>
      </div>
      <div class="bar-track"><div class="bar-seg" style="width:${{Math.min(100, pct)}}%;background:${{barColor}};"></div></div>
      <div class="hint" style="margin-top:8px;">
        ${{pct > 85 ? '⚠️ Approaching budget cap: older aliases will be compacted to light tier during cortical sync.' : '✓ Healthy headroom for sanitized memory blocks injected during cortical sync.'}}
        · Offline Watch Queue: <strong>${{v.watch_queue_count || 0}}</strong> pending job(s).
      </div>
    </div>

    <div class="grid-3" style="margin-bottom:16px;">
      ${{(v.channels || []).map((ch) => `
        <div class="kpi">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <strong>${{esc(ch.name)}}</strong>
            <span class="pill ok">✓ ${{esc(ch.status)}}</span>
          </div>
          <div class="hint" style="margin-top:6px;">${{esc(ch.detail)}}</div>
        </div>
      `).join('')}}
    </div>

    <div class="card">
      <div class="card-head">
        <h2>⬆️ Interactive Zero-Server Upload &amp; Redaction Studio</h2>
        <span class="pill ${{ST.dirHandle ? 'ok' : 'info'}}">${{ST.dirHandle ? '✓ Linked to ' + esc(ST.dirHandle.name) + '/vault_inbox' : 'Browser Preview + CLI Fallback'}}</span>
      </div>
      <div class="grid-4">
        <div class="field"><label for="vu-tags">Task Tags (comma-separated)</label><input id="vu-tags" class="input mono" placeholder="cv, finance, architecture" /></div>
        <div class="field"><label for="vu-terms">Custom Redact Terms</label><input id="vu-terms" class="input" placeholder="ProjectX, SecretCorp" /></div>
        <div class="field"><label for="vu-policy">Policy</label><select id="vu-policy" class="select"><option value="auto">auto</option><option value="fail_closed">fail_closed</option><option value="fail_open">fail_open</option></select></div>
        <div class="field"><label for="vu-profile">Profile</label><select id="vu-profile" class="select"><option value="medium">medium (Chat-Safe)</option><option value="max_security">max_security (Local-Only)</option><option value="low">low</option><option value="max_context">max_context</option></select></div>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;">
        <button class="btn primary sm" onclick="document.getElementById('vu-files').click()">📄 Select Files (Multi-File)</button>
        <button class="btn sm" onclick="document.getElementById('vu-dir').click()">📁 Select Directory (Recursive)</button>
        <input id="vu-files" type="file" multiple style="display:none;" onchange="handleVaultUpload(this.files)" />
        <input id="vu-dir" type="file" webkitdirectory directory multiple style="display:none;" onchange="handleVaultUpload(this.files)" />
        <span class="hint">Masks Email, Phone, IBAN, API keys &amp; custom terms 100% locally in-browser; queues to <code>vault_inbox/</code> when linked.</span>
      </div>
    </div>

    <div class="card">
      <div class="card-head"><h2>Vaulted Aliases (${{aliases.length}})</h2><span class="hint">Raw unmasked secrets are never embedded in static HTML.</span></div>
      <table>
        <thead><tr><th>Alias / URI</th><th>Policy &amp; Profile</th><th>Masked</th><th>Tokens</th><th>Sanitized Preview</th></tr></thead>
        <tbody>
          ${{aliases.map((a) => `
            <tr>
              <td class="mono"><strong>@private:${{esc(a.alias)}}</strong><div class="hint">${{esc(a.source_name)}}</div></td>
              <td>
                <span class="pill ${{a.local_only ? 'err' : 'ok'}}">${{a.local_only ? '🔒 Local-Only' : '🛡️ Chat-Safe'}}</span>
                <span class="pill info">${{esc(a.resolved_policy)}} / ${{esc(a.profile)}}</span>
              </td>
              <td>${{a.entity_count}}</td>
              <td class="mono">${{a.tokens_est}} (${{esc(a.format_used)}})</td>
              <td class="hint" style="max-width:360px;">${{esc(a.sanitized_preview)}}</td>
            </tr>
          `).join('') || '<tr><td colspan="5" class="muted">No aliases in snapshot. Run <code>cortical ingest &lt;file&gt;</code> or link your Cortical folder.</td></tr>'}}
        </tbody>
      </table>
    </div>
  `;
}}

function sanitizeClientSide(text, customTerms) {{
  let out = String(text || '');
  let cnt = 0;
  const rules = [
    [/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{{2,}}/g, '[EMAIL]'],
    [/\\b[A-Z]{{2}}\\d{{2}}[A-Z0-9]{{11,30}}\\b/g, '[IBAN]'],
    [/\\b(?:sk-[a-zA-Z0-9]{{16,}}|ghp_[a-zA-Z0-9]{{20,}}|AIza[0-9A-Za-z_-]{{20,}})\\b/g, '[SECRET]'],
    [/\\+?\\d[\\d\\s().-]{{8,16}}\\d/g, '[PHONE]'],
  ];
  for (const [rx, rep] of rules) {{
    out = out.replace(rx, () => {{ cnt += 1; return rep; }});
  }}
  for (const term of (customTerms || [])) {{
    if (!term) continue;
    const escRx = term.replace(/[.*+?^${{}}()|[\\]\\\\]/g, '\\\\$&');
    out = out.replace(new RegExp(escRx, 'gi'), () => {{ cnt += 1; return '[REDACTED]'; }});
  }}
  return {{ text: out, count: cnt }};
}}

async function handleVaultUpload(fileList) {{
  const files = Array.from(fileList || []).filter((f) => !f.name.startsWith('.'));
  if (!files.length) return;
  const tags = (document.getElementById('vu-tags')?.value || '').split(',').map((s) => s.trim()).filter(Boolean);
  const terms = (document.getElementById('vu-terms')?.value || '').split(',').map((s) => s.trim()).filter(Boolean);
  const policy = document.getElementById('vu-policy')?.value || 'auto';
  const profile = document.getElementById('vu-profile')?.value || 'medium';
  let queued = 0;
  for (const f of files) {{
    const alias = (f.webkitRelativePath || f.name).replace(/\\.[^.]+$/, '').toLowerCase().replace(/[^a-z0-9._-]+/g, '_').replace(/^_+|_+$/g, '') || 'doc';
    const isImg = /\\.(png|jpg|jpeg|webp|pdf)$/i.test(f.name);
    let preview = '[Queued for local OCR/extractor via cortical watch]';
    let entityCount = 0;
    if (!isImg) {{
      const raw = await f.text().catch(() => '');
      const san = sanitizeClientSide(raw, terms);
      entityCount = san.count;
      preview = profile === 'max_security' ? '[LOCAL-ONLY max_security — masked from cloud & static preview]' : san.text.slice(0, 320);
    }}
    if (ST.dirHandle) {{
      try {{
        const inbox = await ST.dirHandle.getDirectoryHandle('vault_inbox', {{ create: true }});
        const fh = await inbox.getFileHandle(f.name, {{ create: true }});
        const w = await fh.createWritable();
        await w.write(await f.arrayBuffer());
        await w.close();
        const mh = await inbox.getFileHandle(f.name + '.meta.json', {{ create: true }});
        const mw = await mh.createWritable();
        await mw.write(JSON.stringify({{ alias, policy, profile, custom_terms: terms, task_tags: tags, source_name: f.webkitRelativePath || f.name }}, null, 2));
        await mw.close();
        queued += 1;
      }} catch {{}}
    }}
    ST.snap.vault.aliases = (ST.snap.vault.aliases || []).filter((a) => a.alias !== alias);
    ST.snap.vault.aliases.unshift({{
      alias, uri: 'cortical://private/' + alias, source_name: f.webkitRelativePath || f.name,
      profile, resolved_policy: policy === 'auto' ? (entityCount > 0 || profile === 'max_security' ? 'fail_closed' : 'fail_open') : policy,
      local_only: profile === 'max_security', entity_count: entityCount,
      tokens_est: Math.max(1, Math.round(preview.length / 4)), format_used: isImg ? 'inbox' : 'text',
      task_tags: tags, sanitized_preview: preview,
    }});
  }}
  if (queued > 0) ST.snap.vault.watch_queue_count = (ST.snap.vault.watch_queue_count || 0) + queued;
  toast('ok', queued > 0 ? `Queued ${{queued}} file(s) into linked vault_inbox/ (run cortical watch).` : `Masked ${{files.length}} file(s) locally in-browser.`);
  renderAll();
}}

// =========================================================================
// VIEW 5: SETTINGS & DECLARATIVE CONFIG COMPOSER (5 Tabs + Sticky Dock)
// =========================================================================
function renderSettings() {{
  const c = ST.draftCfg;
  const tab = ST.settingsTab;
  const err = (k) => ST.cfgErrors[k] ? `<div class="err-msg">⚠ ${{esc(ST.cfgErrors[k])}}</div>` : '';

  let body = '';
  if (tab === 'general') {{
    body = `
      <div class="card">
        <div class="grid-2">
          <div class="field">
            <label for="s-runner">Active Local Runner</label>
            <select id="s-runner" class="select" onchange="setCfg('active_runner', this.value)">
              ${{['ollama','unsloth','llama_cpp','mlx_lm','openai_compatible'].map((r)=>`<option value="${{r}}" ${{c.active_runner===r?'selected':''}}>${{r}}</option>`).join('')}}
            </select>
            <div class="hint">Primary local inference backend used for <code>cortical_local_offload</code> and offline NER.</div>
          </div>
          <div class="field">
            <label for="s-ctx">Max Context Window (tokens)</label>
            <input id="s-ctx" type="number" class="input mono ${{ST.cfgErrors.max_context_window?'invalid':''}}" value="${{c.max_context_window || 200000}}" oninput="setCfg('max_context_window', Number(this.value))" />
            <div class="hint">Upper bound for cloud/local context budgeting (4096–1000000).</div>
            ${{err('max_context_window')}}
          </div>
        </div>
      </div>
      <div class="card">
        <div class="card-head">
          <h2>📦 Portable Zero-Secret Team Profile &amp; Offline Snapshot Diff</h2>
          <button class="btn sm primary" onclick="exportPortableProfile()">⬇️ Export Portable Profile</button>
        </div>
        <div class="field">
          <label for="s-prof-diff">Paste Peer <code>cortical-profile/v1</code> JSON to Compare Offline</label>
          <textarea id="s-prof-diff" class="input mono" rows="3" placeholder='{{"schema":"cortical-profile/v1","hardware_tier":"tier_2_desktop","config_patch":{{"routing":{{"mode":"auto"}}}}}}'></textarea>
        </div>
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
          <button class="btn sm" onclick="comparePortableProfile()">🔍 Compare Profile Diff</button>
          <span class="hint">CLI: <code>cortical profile export team.json</code> · <code>cortical profile diff team.json</code> · <code>cortical profile import team.json --dry-run</code></span>
        </div>
        <pre id="s-prof-diff-out" class="code-pre" style="margin-top:8px;min-height:42px;">Paste a peer profile JSON above and click Compare Profile Diff.</pre>
      </div>`;
  }} else if (tab === 'routing') {{
    const rt = c.routing || {{}};
    const budgetOn = Boolean(rt.enforce_cloud_budget);
    body = `
      <div class="card">
        <div class="grid-2" style="margin-bottom:14px;">
          <div class="field">
            <label><input id="s-rlocal" type="checkbox" ${{rt.prefer_local_offload!==false?'checked':''}} onchange="setCfg('routing.prefer_local_offload', this.checked)" /> Prefer Local LLM Offload (minimize cloud tokens)</label>
            <div class="hint">Offloads code reviews, summarization, OCR, NER, and sub-tasks to local models whenever possible.</div>
          </div>
          <div class="field">
            <label><input id="s-renforce" type="checkbox" ${{budgetOn?'checked':''}} onchange="setCfg('routing.enforce_cloud_budget', this.checked); renderAll()" /> Enforce Cloud Token Budget Threshold (optional)</label>
            <div class="hint">Disabled by default. Enable to automatically recommend/switch to local handoff when remaining cloud tokens drop below the threshold.</div>
          </div>
        </div>
        <div class="grid-3">
          <div class="field">
            <label for="s-rmode">LLM Routing Mode</label>
            <select id="s-rmode" class="select" onchange="setCfg('routing.mode', this.value)">
              ${{['auto','full_local','cloud_first'].map((m)=>`<option value="${{m}}" ${{rt.mode===m?'selected':''}}>${{m}}</option>`).join('')}}
            </select>
            <div class="hint"><code>auto</code> maximizes local offload; <code>full_local</code> enforces 0 cloud tokens.</div>
          </div>
          <div class="field">
            <label for="s-cthr">Cloud Fallback Threshold (tokens)</label>
            <input id="s-cthr" type="number" class="input mono" ${{budgetOn?'':'disabled'}} value="${{rt.cloud_token_threshold || 50000}}" oninput="setCfg('routing.cloud_token_threshold', Number(this.value))" />
            <div class="hint">Triggers local handoff recommendation when remaining cloud tokens drop below this value (requires Enforcement enabled).</div>
          </div>
          <div class="field">
            <label for="s-cbud">Cloud Budget Window (tokens)</label>
            <input id="s-cbud" type="number" class="input mono" ${{budgetOn?'':'disabled'}} value="${{rt.cloud_budget_tokens || 1000000}}" oninput="setCfg('routing.cloud_budget_tokens', Number(this.value))" />
          </div>
        </div>
      </div>
      ${{renderOrchestrationCard()}}`;
  }} else if (tab === 'privacy') {{
    const pv = c.privacy || {{}};
    const cp = c.compression || {{}};
    const prof = pv.default_profile || 'medium';
    const termsCsv = Array.isArray(pv.custom_terms) ? pv.custom_terms.join(', ') : (pv.custom_terms || '');
    const ignTxt = Array.isArray(pv.folder_ignore_rules) ? pv.folder_ignore_rules.join('\\n') : (pv.folder_ignore_rules || '.cortical_data/\\n.env*\\n*.key\\n*.pem\\n*secret*');
    const folderTarget = pv.crawl_folder || '~/Dropbox';
    body = `
      <div class="card">
        <div class="grid-3">
          <div class="field">
            <label for="s-ppol">Default Privacy Policy</label>
            <select id="s-ppol" class="select" onchange="setCfg('privacy.default_policy', this.value)">
              ${{['auto','fail_closed','fail_open'].map((p)=>`<option value="${{p}}" ${{pv.default_policy===p?'selected':''}}>${{p}}</option>`).join('')}}
            </select>
            <div class="hint"><code>fail_closed</code> blocks egress whenever redaction cannot be verified.</div>
          </div>
          <div class="field">
            <label for="s-pprof">Default Sensitivity Profile</label>
            <select id="s-pprof" class="select" onchange="setCfg('privacy.default_profile', this.value);renderPrivacySample()">
              ${{['max_security','low','medium','max_context'].map((p)=>`<option value="${{p}}" ${{prof===p?'selected':''}}>${{p}}</option>`).join('')}}
            </select>
          </div>
          <div class="field">
            <label for="s-mshare">Max Memory Context Share (0.05–0.30)</label>
            <input id="s-mshare" type="number" step="0.01" class="input mono ${{ST.cfgErrors.max_context_share?'invalid':''}}" value="${{cp.max_context_share ?? 0.15}}" oninput="setCfg('compression.max_context_share', Number(this.value))" />
            <div class="hint">Caps sanitized memory injection during <code>cortical sync</code> (default 15%).</div>
            ${{err('max_context_share')}}
          </div>
        </div>
      </div>
      <div class="card" style="margin-top:14px;">
        <div class="card-head">
          <h2>📂 Folder Ingestion &amp; Privacy Policy Presets</h2>
          <div style="display:flex;gap:8px;flex-wrap:wrap;">
            <button class="btn sm primary" onclick="applyFolderPrivacyPreset('dropbox')">☁️ Cloud Drive / Dropbox Vault (<code>medium</code>)</button>
            <button class="btn sm" onclick="applyFolderPrivacyPreset('strict')">🔒 Strict Local-Only Vault (<code>max_security</code>)</button>
          </div>
        </div>
        <div class="grid-2" style="margin-bottom:12px;">
          <div class="field">
            <label for="s-cfolder">Target Folder Path</label>
            <input id="s-cfolder" class="input mono" value="${{esc(folderTarget)}}" oninput="setCfg('privacy.crawl_folder', this.value);renderPrivacySample()" />
            <div class="hint">Used for generated <code>cortical crawl --sanitize</code> and <code>cortical sanitize --recursive</code> commands.</div>
          </div>
          <div class="field">
            <label for="s-cterms">Custom Redaction Terms (comma-separated)</label>
            <input id="s-cterms" class="input" placeholder="Project Orion, Client Alpha, InternalTaxID" value="${{esc(termsCsv)}}" oninput="setCfg('privacy.custom_terms', this.value.split(',').map(s=>s.trim()).filter(Boolean));renderPrivacySample()" />
            <div class="hint">Masked deterministically before any 4-tier summary or FTS5 indexing runs.</div>
          </div>
        </div>
        <div class="grid-2">
          <div class="field">
            <label for="s-cign">Auto-Ignore Rules (<code>.corticalignore</code> / <code>.geminiignore</code> / <code>.cursorignore</code> / <code>.claudeignore</code>)</label>
            <textarea id="s-cign" class="input mono" rows="5" oninput="setCfg('privacy.folder_ignore_rules', this.value.split('\\n').map(s=>s.trim()).filter(Boolean))">${{esc(ignTxt)}}</textarea>
          </div>
          <div class="field">
            <label for="s-csamp">Live Sample Text Preview (Real-Time PII Masking)</label>
            <textarea id="s-csamp" class="input mono" rows="3" oninput="ST.privacySampleText=this.value;renderPrivacySample()">${{esc(ST.privacySampleText || 'Contract with alice@acme.example, IBAN IT60X0542811101000000123456, phone +39 347 555 0199, Project Orion.')}}</textarea>
            <pre id="s-csamp-out" class="code-pre" style="margin-top:8px;min-height:66px;"></pre>
            <div style="display:flex;gap:8px;align-items:center;justify-content:space-between;flex-wrap:wrap;margin-top:6px;">
              <code id="s-ccmd" class="mono" style="font-size:11.5px;color:var(--ok);"></code>
              <button class="btn sm" onclick="copyText(document.getElementById('s-ccmd')?.textContent||'', 'crawl command')">📋 Copy Crawl Command</button>
            </div>
          </div>
        </div>
      </div>`;
    setTimeout(renderPrivacySample, 0);
  }} else if (tab === 'compression') {{
    const cp = c.compression || {{}};
    body = `
      <div class="card">
        <div class="grid-2">
          <div class="field">
            <label><input type="checkbox" ${{cp.enable_toon!==false?'checked':''}} onchange="setCfg('compression.enable_toon', this.checked)" /> Enable Lossless TOON Compression</label>
            <div class="hint">Converts repetitive JSON arrays into compact tabular TOON format with deterministic roundtrip.</div>
          </div>
          <div class="field">
            <label for="s-msav">Minimum TOON Saving Guard (%)</label>
            <input id="s-msav" type="number" step="1" class="input mono ${{ST.cfgErrors.min_toon_saving_pct?'invalid':''}}" value="${{cp.min_toon_saving_pct ?? 10}}" oninput="setCfg('compression.min_toon_saving_pct', Number(this.value))" />
            <div class="hint">Falls back to compact JSON if TOON saves less than this threshold (default 10%).</div>
            ${{err('min_toon_saving_pct')}}
          </div>
        </div>
      </div>`;
  }} else {{
    body = `
      <div class="card">
        <div class="card-head"><h2>Validated Raw Declarative JSON (<code>cortical.config.json</code>)</h2><button class="btn sm" onclick="downloadFile('cortical.config.json', JSON.stringify(ST.draftCfg, null, 2)+'\\n', 'application/json')">⬇️ Download JSON</button></div>
        <pre class="code-pre">${{esc(JSON.stringify(c, null, 2))}}</pre>
      </div>`;
  }}

  return `
    <div class="page-head">
      <div>
        <h1>⚙️ Settings &amp; Declarative Config Composer</h1>
        <p>Edit declarative configuration with inline validation, live diffs, copyable CLI apply scripts, and optional File System Access saves.</p>
      </div>
    </div>
    <div class="tabs" role="tablist">
      <button class="tab-btn ${{tab==='general'?'active':''}}" onclick="ST.settingsTab='general';renderAll()">General &amp; Workspace</button>
      <button class="tab-btn ${{tab==='routing'?'active':''}}" onclick="ST.settingsTab='routing';renderAll()">Harnesses &amp; Routing</button>
      <button class="tab-btn ${{tab==='privacy'?'active':''}}" onclick="ST.settingsTab='privacy';renderAll()">Privacy &amp; Context Budgets</button>
      <button class="tab-btn ${{tab==='compression'?'active':''}}" onclick="ST.settingsTab='compression';renderAll()">Compression &amp; TOON</button>
      <button class="tab-btn ${{tab==='raw'?'active':''}}" onclick="ST.settingsTab='raw';renderAll()">Advanced / Raw JSON</button>
    </div>
    ${{body}}
  `;
}}

function setCfg(path, val) {{
  const parts = path.split('.');
  let cur = ST.draftCfg;
  for (let i = 0; i < parts.length - 1; i++) {{ if (!cur[parts[i]]) cur[parts[i]] = {{}}; cur = cur[parts[i]]; }}
  cur[parts[parts.length - 1]] = val;
  validateCfg();
  renderDirtyDock();
}}

function applyFolderPrivacyPreset(kind) {{
  if (kind === 'dropbox') {{
    setCfg('privacy.default_policy', 'auto');
    setCfg('privacy.default_profile', 'medium');
    setCfg('privacy.crawl_folder', '~/Dropbox');
    setCfg('privacy.folder_ignore_rules', ['.cortical_data/', '.env*', '*.key', '*.pem', '*secret*', '*.dmg', '*.zip']);
  }} else {{
    setCfg('privacy.default_policy', 'fail_closed');
    setCfg('privacy.default_profile', 'max_security');
    setCfg('privacy.crawl_folder', '~/Documents/PrivateVault');
    setCfg('privacy.folder_ignore_rules', ['.cortical_data/', '.env*', '*.key', '*.pem', '*secret*']);
  }}
  renderAll();
  toast('ok', 'Applied preset: ' + (kind === 'dropbox' ? 'Cloud Drive / Dropbox Vault' : 'Strict Local-Only Vault'));
}}

function renderPrivacySample() {{
  const out = document.getElementById('s-csamp-out');
  const cmdEl = document.getElementById('s-ccmd');
  if (!out) return;
  const pv = ST.draftCfg?.privacy || {{}};
  const prof = pv.default_profile || 'medium';
  let txt = document.getElementById('s-csamp')?.value || 'Contract with alice@acme.example, IBAN IT60X0542811101000000123456.';
  const cnt = {{}};
  const tok = (cat) => {{ cnt[cat] = (cnt[cat] || 0) + 1; return `[${{cat}}_${{cnt[cat]}}]`; }};
  const rawTerms = Array.isArray(pv.custom_terms) ? pv.custom_terms : [];
  rawTerms.slice().sort((a,b) => b.length - a.length).forEach((t) => {{
    if (!t) return;
    const re = new RegExp(t.replace(/[.*+?^${{}}()|[\\]\\\\]/g, '\\\\$&'), 'gi');
    txt = txt.replace(re, () => tok('CUSTOM'));
  }});
  txt = txt.replace(/\\b(?:sk-[a-zA-Z0-9_-]{{16,}}|gh[pous]_[a-zA-Z0-9]{{20,}}|AKIA[0-9A-Z]{{16}})\\b/g, () => tok('SECRET'));
  txt = txt.replace(/\\b[A-Z]{{2}}\\d{{2}}[A-Z0-9]{{11,30}}\\b/g, () => tok('IBAN'));
  txt = txt.replace(/\\b[A-Z]{{6}}\\d{{2}}[A-Z]\\d{{2}}[A-Z]\\d{{3}}[A-Z]\\b/g, () => tok('TAX_ID'));
  txt = txt.replace(/\\b[A-Za-z0-9._%+\\-]+@[A-Za-z0-9.\\-]+\\.[A-Za-z]{{2,}}\\b/g, () => tok('EMAIL'));
  txt = txt.replace(/(?<!\\w)(?:\\+?\\d{{1,3}}[\\s.-]?)?(?:\\(?\\d{{2,4}}\\)?[\\s.-]?)?\\d{{3,4}}[\\s.-]\\d{{3,4}}(?!\\w)/g, () => tok('PHONE'));
  txt = txt.replace(/\\b(?:(?:25[0-5]|2[0-4]\\d|1?\\d?\\d)\\.){{3}}(?:25[0-5]|2[0-4]\\d|1?\\d?\\d)\\b/g, () => tok('IP'));
  out.innerHTML = esc(txt).replace(/(\\[[A-Z0-9_]+_\\d+\\])/g, '<span class="pill ok" style="padding:1px 5px;font-size:11px;">$1</span>');
  if (cmdEl) {{
    const p = (pv.crawl_folder || '~/Dropbox').replace(/"/g, '\\\\"');
    const tFlag = rawTerms.length ? ` --custom-terms "${{rawTerms.join(',').replace(/"/g, '\\\\"')}}"` : '';
    cmdEl.textContent = `cortical crawl "${{p}}" --sanitize --privacy-profile ${{prof}}${{tFlag}} --dry-run`;
  }}
}}

function exportPortableProfile() {{
  const c = deepClone(ST.draftCfg);
  if (c.orchestrator && /^(?:sk-|AIza|gh[pous]_|AKIA|pplx-|xox)/i.test(String(c.orchestrator.api_key_env || ''))) {{
    c.orchestrator.api_key_env = '';
  }}
  const bundle = {{
    schema: 'cortical-profile/v1',
    hardware_tier: ST.snap.hardware?.classification?.tier || 'portable',
    config_patch: c,
    custom_models: c.custom_models || [],
  }};
  downloadFile('cortical-profile.json', JSON.stringify(bundle, null, 2) + '\\n', 'application/json');
  toast('ok', 'Exported secret-free cortical-profile.json');
}}

function comparePortableProfile() {{
  const out = document.getElementById('s-prof-diff-out');
  const raw = document.getElementById('s-prof-diff')?.value || '';
  if (!out) return;
  try {{
    const peer = JSON.parse(raw);
    const peerPatch = peer.config_patch || peer || {{}};
    const cur = ST.draftCfg || {{}};
    const keys = Object.keys(peerPatch).sort();
    const diffs = [];
    for (const k of keys) {{
      if (JSON.stringify(cur[k]) !== JSON.stringify(peerPatch[k])) {{
        diffs.push(k + ': local=' + JSON.stringify(cur[k]) + ' vs peer=' + JSON.stringify(peerPatch[k]));
      }}
    }}
    out.textContent = diffs.length ? diffs.join('\\n') : 'Identical portable configuration (0 section differences).';
  }} catch (err) {{
    out.textContent = 'Invalid JSON: ' + err.message;
  }}
}}

function validateCfg() {{
  const e = {{}};
  const c = ST.draftCfg;
  if ((c.max_context_window || 0) < 4096 || (c.max_context_window || 0) > 1000000) e.max_context_window = 'Must be between 4,096 and 1,000,000.';
  const sh = c.compression?.max_context_share ?? 0.15;
  if (sh < 0.05 || sh > 0.30) e.max_context_share = 'Must be between 0.05 (5%) and 0.30 (30%).';
  const sv = c.compression?.min_toon_saving_pct ?? 10;
  if (sv < 0 || sv > 80) e.min_toon_saving_pct = 'Must be between 0% and 80%.';
  const o = c.orchestrator || {{}};
  const ake = String(o.api_key_env || '').trim();
  if (ake && (/^(?:sk-|AIza|gh[pous]_|AKIA|pplx-|xox)/i.test(ake) || ake.length > 64 || !/^[A-Za-z0-9_]+$/.test(ake))) {{
    e.orch_api_key_env = 'Must be an env var name (e.g. GEMINI_API_KEY), never a raw secret.';
  }}
  if (o.fixed_num_ctx !== undefined && ((o.fixed_num_ctx || 0) < 4096 || (o.fixed_num_ctx || 0) > 1000000)) {{
    e.orch_fixed_num_ctx = 'Must be between 4,096 and 1,000,000.';
  }}
  if (o.timeout_sec !== undefined && ((o.timeout_sec || 0) < 0 || (o.timeout_sec || 0) > 3600)) {{
    e.orch_timeout_sec = 'Must be between 0 and 3600 seconds.';
  }}
  ST.cfgErrors = e;
}}

function isDirty() {{ return JSON.stringify(ST.savedCfg) !== JSON.stringify(ST.draftCfg) || ST.pendingModels.length > 0 || ST.planHarnesses.length > 0; }}
function renderDirtyDock() {{
  const dock = document.getElementById('dirty-dock');
  if (!isDirty()) {{ dock.style.display = 'none'; return; }}
  const errCnt = Object.keys(ST.cfgErrors).length;
  dock.style.display = 'flex';
  const parts = [];
  const cfgKeys = Object.keys(buildPlan().config_patch).length;
  if (cfgKeys) parts.push(cfgKeys + ' config section(s)');
  if (ST.pendingModels.length) parts.push(ST.pendingModels.length + ' model(s)');
  if (ST.planHarnesses.length) parts.push(ST.planHarnesses.length + ' harness sync(s)');
  document.getElementById('dirty-info').textContent = errCnt ? `Fix ${{errCnt}} validation error(s)` : ('Plan: ' + parts.join(' · '));
  document.getElementById('btn-save-fs').disabled = errCnt > 0;
  dock.querySelectorAll('button[onclick^="downloadPlan"],button[onclick^="copyPlan"]').forEach((b) => b.disabled = errCnt > 0);
}}
function discardConfig() {{ ST.draftCfg = deepClone(ST.savedCfg); ST.cfgErrors = {{}}; ST.pendingModels = []; ST.planHarnesses = []; renderAll(); toast('info', 'Changes discarded.'); }}

function buildPlan() {{
  const patch = {{}};
  for (const k of Object.keys(ST.draftCfg)) {{
    if (JSON.stringify(ST.savedCfg[k]) !== JSON.stringify(ST.draftCfg[k])) patch[k] = ST.draftCfg[k];
  }}
  return {{
    schema: 'cortical-plan/v1',
    generated_at: new Date().toISOString(),
    config_patch: patch,
    custom_models: ST.pendingModels,
    vault_updates: [],
    sync_harnesses: ST.planHarnesses,
    regenerate_dashboard: 'html',
  }};
}}
function downloadPlan() {{
  downloadFile('cortical-plan.json', JSON.stringify(buildPlan(), null, 2) + '\\n', 'application/json');
  toast('ok', 'Saved cortical-plan.json → run: cortical apply cortical-plan.json --dry-run, then without --dry-run');
}}
function copyPlanForClipboardApply() {{
  copyText(JSON.stringify(buildPlan(), null, 2), 'plan JSON');
  toast('info', 'Now run in a terminal: cortical apply --from-clipboard --dry-run  (then drop --dry-run)');
}}
function togglePlanHarness(id) {{
  ST.planHarnesses = ST.planHarnesses.includes(id) ? ST.planHarnesses.filter((h) => h !== id) : ST.planHarnesses.concat([id]);
  toast('ok', (ST.planHarnesses.includes(id) ? 'Added ' : 'Removed ') + id + ' to apply plan');
  renderAll();
  if (ST.drawerItem) renderServiceDrawer();
}}
const VERIFY_REFRESH_CMD = 'cortical doctor && cortical sync --dry-run && cortical dashboard --out-dir html --open';

function buildCliApplyScript() {{
  const b64 = btoa(unescape(encodeURIComponent(JSON.stringify(ST.draftCfg, null, 2) + '\\n')));
  if (ST.targetOs === 'windows') {{
    return `[System.IO.File]::WriteAllBytes("$HOME\\Documents\\Cortical\\cortical.config.json", [Convert]::FromBase64String("${{b64}}")); cortical sync`;
  }}
  return `mkdir -p "$HOME/Documents/Cortical" && printf '%s' '${{b64}}' | base64 -d > "$HOME/Documents/Cortical/cortical.config.json" && cortical sync`;
}}
function copyCliApplyScript() {{ copyText(buildCliApplyScript(), 'CLI Apply Script'); }}

async function saveToLinkedFolder() {{
  if (!ST.dirHandle) {{ openBridgeModal(); return; }}
  try {{
    const fh = await ST.dirHandle.getFileHandle('cortical.config.json', {{ create: true }});
    const w = await fh.createWritable();
    await w.write(JSON.stringify(ST.draftCfg, null, 2) + '\\n');
    await w.close();
    ST.savedCfg = deepClone(ST.draftCfg);
    renderDirtyDock();
    toast('ok', 'Saved cortical.config.json directly to linked folder!');
  }} catch (err) {{
    toast('err', 'Write failed: ' + err.message);
  }}
}}

function openDiffModal() {{
  const changed = [];
  for (const k of new Set([...Object.keys(ST.savedCfg), ...Object.keys(ST.draftCfg)])) {{
    if (JSON.stringify(ST.savedCfg[k]) !== JSON.stringify(ST.draftCfg[k])) {{
      changed.push(`- ${{k}}: ${{JSON.stringify(ST.savedCfg[k])}}\\n+ ${{k}}: ${{JSON.stringify(ST.draftCfg[k])}}`);
    }}
  }}
  document.getElementById('modal-root').innerHTML = `
    <div class="backdrop" onclick="if(event.target===this)closeModal()">
      <div class="modal" role="dialog" aria-modal="true" aria-label="Config Diff Preview">
        <h2 style="margin-top:0;">Declarative Config Diff</h2>
        <pre class="code-pre">${{esc(changed.join('\\n\\n') || 'No differences.')}}</pre>
        <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:14px;">
          <button class="btn" onclick="copyCliApplyScript()">📋 Copy CLI Apply Script</button>
          <button class="btn primary" onclick="closeModal()">Close</button>
        </div>
      </div>
    </div>`;
}}

// =========================================================================
// VIEW 6: USAGE, ROI & COMPARATIVE REPORTS (Zero-Lib SVG/CSS Charts)
// =========================================================================
function renderReports() {{
  const roi = ST.snap.roi || {{}};
  const bench = ST.snap.bench || {{}};
  const comp = bench.compression_before_vs_after || {{ raw_pretty_tokens_est: 900, raw_compact_tokens_est: 620, compressed_tokens_est: 210, saving_vs_pretty_pct: 76.6, saving_vs_compact_pct: 66.1 }};
  const maxTok = Math.max(1, comp.raw_pretty_tokens_est || 900);
  const wPretty = 100;
  const wCompact = Math.round(((comp.raw_compact_tokens_est || 620) / maxTok) * 100);
  const wToon = Math.round(((comp.compressed_tokens_est || 210) / maxTok) * 100);

  return `
    <div class="page-head">
      <div>
        <h1>📊 Usage, ROI &amp; Comparative Reports</h1>
        <p>Zero-token local ROI analytics, lossless TOON compression benchmarks, and exportable Markdown/JSON audit summaries.</p>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;">
        <button class="btn" onclick="exportAuditMarkdown()">⬇️ Export Markdown Audit</button>
        <button class="btn primary" onclick="downloadFile('cortical-snapshot.json', JSON.stringify(ST.snap, null, 2)+'\\n', 'application/json')">⬇️ Export JSON Snapshot</button>
      </div>
    </div>

    <div class="grid-4" style="margin-bottom:16px;">
      <div class="kpi"><div class="hint">Local Offload Runs</div><div class="kpi-val">${{roi.local_runs || 0}}</div><div class="hint">${{(roi.local_tokens||0).toLocaleString()}} local tokens</div></div>
      <div class="kpi"><div class="hint">Estimated Cloud Saved</div><div class="kpi-val" style="color:var(--ok);">$${{Number(roi.estimated_usd_saved||0).toFixed(2)}}</div><div class="hint">${{roi.offload_pct || 0}}% local offload share</div></div>
      <div class="kpi"><div class="hint">TOON vs Pretty JSON</div><div class="kpi-val" style="color:var(--accent);">-${{comp.saving_vs_pretty_pct || 76.6}}%</div><div class="hint">-${{comp.saving_vs_compact_pct || 66.1}}% vs compact JSON</div></div>
      <div class="kpi"><div class="hint">Privacy Precision</div><div class="kpi-val" style="color:var(--ok);">${{bench.privacy_before_vs_after?.technical_terms_preserved_pct ?? 100}}%</div><div class="hint">Zero Title-Case false positives</div></div>
    </div>

    <div class="card">
      <div class="card-head"><h2>Comparative Token Compression (<code>cortical bench --compare</code>)</h2></div>
      <div style="display:flex;flex-direction:column;gap:12px;">
        <div>
          <div style="display:flex;justify-content:space-between;" class="hint"><span>Raw Pretty JSON</span><span class="mono">${{comp.raw_pretty_tokens_est}} tokens (100%)</span></div>
          <div class="bar-track"><div class="bar-seg" style="width:${{wPretty}}%;background:#64748b;"></div></div>
        </div>
        <div>
          <div style="display:flex;justify-content:space-between;" class="hint"><span>Compact JSON</span><span class="mono">${{comp.raw_compact_tokens_est}} tokens (${{wCompact}}%)</span></div>
          <div class="bar-track"><div class="bar-seg" style="width:${{wCompact}}%;background:#38bdf8;"></div></div>
        </div>
        <div>
          <div style="display:flex;justify-content:space-between;" class="hint"><span><strong>Cortical Lossless TOON</strong></span><span class="mono" style="color:var(--ok);"><strong>${{comp.compressed_tokens_est}} tokens (${{wToon}}%)</strong></span></div>
          <div class="bar-track"><div class="bar-seg" style="width:${{wToon}}%;background:#34d399;"></div></div>
        </div>
      </div>
    </div>
  `;
}}

function exportAuditMarkdown() {{
  const s = ST.snap;
  const md = [
    `# Cortical Zero-Server Audit Report`,
    `- **Mode:** ${{s.meta?.mode}} | **OS:** ${{s.meta?.os}} | **Hardware:** ${{s.hardware?.classification?.label || s.hardware?.classification?.tier}} (${{s.hardware?.total_ram_gb}} GB RAM)`,
    `- **Harnesses Linked:** ${{(s.harnesses||[]).filter(h=>h.linked).length}}/8`,
    `- **Privacy Vault:** ${{(s.vault?.aliases||[]).length}} aliases (${{s.vault?.memory_budget_pct}}% of ≤15% num_ctx budget)`,
    `- **ROI Saved:** $${{Number(s.roi?.estimated_usd_saved||0).toFixed(2)}} (${{s.roi?.local_runs||0}} local runs)`,
    ``,
    `## Synchronized ADRs`,
    ...(s.adrs || []).map((a) => `- **${{a.id}}** (${{a.status}}, ${{a.issue}}): ${{a.title}}`),
  ].join('\\n') + '\\n';
  downloadFile('cortical-audit-report.md', md, 'text/markdown');
  toast('ok', 'Exported cortical-audit-report.md');
}}

// =========================================================================
// LOCAL FOLDER BRIDGE & COMMAND PALETTE (Cmd/Ctrl + K)
// =========================================================================
function openBridgeModal() {{
  document.getElementById('modal-root').innerHTML = `
    <div class="backdrop" onclick="if(event.target===this)closeModal()">
      <div class="modal" role="dialog" aria-modal="true" aria-label="Link Folder or Load Snapshot">
        <h2 style="margin-top:0;">📂 Zero-Server Client-Machine Bridge</h2>
        <p class="hint">Connect your local <code>~/Documents/Cortical</code> folder directly via Chromium's File System Access API, or import a JSON snapshot exported by <code>cortical dashboard</code>.</p>
        <div style="display:flex;gap:10px;flex-wrap:wrap;margin:16px 0;">
          <button class="btn primary" onclick="pickLocalFolder()">📁 Link Local Cortical Folder</button>
          <button class="btn" onclick="document.getElementById('snap-file-input').click()">📄 Import Snapshot JSON</button>
        </div>
        <div class="hint">No Chromium? Generate a fresh hydrated dashboard anytime with: <code class="mono">cortical dashboard --open</code></div>
        <div style="display:flex;justify-content:flex-end;margin-top:14px;"><button class="btn" onclick="closeModal()">Close</button></div>
      </div>
    </div>`;
}}

async function pickLocalFolder() {{
  if (!window.showDirectoryPicker) {{
    toast('warn', 'File System Access API is available in Chromium browsers. Use Copy CLI Apply Script or Import Snapshot JSON.');
    return;
  }}
  try {{
    ST.dirHandle = await window.showDirectoryPicker({{ mode: 'readwrite' }});
    try {{
      const fh = await ST.dirHandle.getFileHandle('cortical.config.json');
      const txt = await (await fh.getFile()).text();
      const parsed = JSON.parse(txt);
      ST.savedCfg = deepClone(parsed);
      ST.draftCfg = deepClone(parsed);
    }} catch {{}}
    closeModal();
    toast('ok', 'Linked local folder: ' + ST.dirHandle.name);
    renderAll();
  }} catch (err) {{
    if (err.name !== 'AbortError') toast('err', err.message);
  }}
}}

document.getElementById('snap-file-input').addEventListener('change', async (e) => {{
  const f = e.target.files?.[0];
  if (!f) return;
  try {{
    const data = JSON.parse(await f.text());
    if (data.config) {{ ST.snap = data; ST.savedCfg = deepClone(data.config); ST.draftCfg = deepClone(data.config); }}
    closeModal();
    toast('ok', 'Loaded snapshot: ' + f.name);
    renderAll();
  }} catch (err) {{ toast('err', 'Invalid JSON snapshot: ' + err.message); }}
}});

function closeModal() {{ document.getElementById('modal-root').innerHTML = ''; }}

function cmdItems() {{
  const items = [
    {{ label: 'View: Overview & Quick Setup', g: 'Nav', run: () => setView('overview') }},
    {{ label: 'View: Services & 8 Harnesses', g: 'Nav', run: () => setView('harnesses') }},
    {{ label: 'View: Models & Hardware Tuner', g: 'Nav', run: () => setView('models') }},
    {{ label: 'View: Memory & Privacy Vault', g: 'Nav', run: () => setView('vault') }},
    {{ label: 'View: Settings & Config Composer', g: 'Nav', run: () => setView('settings') }},
    {{ label: 'View: Usage, ROI & Reports', g: 'Nav', run: () => setView('reports') }},
    {{ label: 'CLI: Copy cortical sync --dry-run', g: 'CLI', run: () => copyText('cortical sync --dry-run', 'sync --dry-run') }},
    {{ label: 'CLI: Copy cortical doctor', g: 'CLI', run: () => copyText('cortical doctor', 'cortical doctor') }},
    {{ label: 'CLI: Copy cortical tune --apply', g: 'CLI', run: () => copyText('cortical tune --apply', 'cortical tune') }},
    {{ label: 'CLI: Copy cortical watch', g: 'CLI', run: () => copyText('cortical watch', 'cortical watch') }},
    {{ label: 'CLI: Copy Verify & Refresh Snapshot', g: 'CLI', run: () => copyText(VERIFY_REFRESH_CMD, 'verify & refresh') }},
    {{ label: 'Plan: Download cortical-plan.json', g: 'Apply', run: () => downloadPlan() }},
    {{ label: 'Plan: Copy plan → cortical apply --from-clipboard', g: 'Apply', run: () => copyPlanForClipboardApply() }},
    {{ label: 'Action: Probe Local Services (Ollama/Router)', g: 'Probe', run: () => {{ setView('models'); probeLocalRuntimes(); }} }},
    {{ label: 'Action: Link Local Folder / Load Snapshot', g: 'Bridge', run: () => openBridgeModal() }},
  ];
  (ST.snap.adrs || []).forEach((a) => items.push({{ label: `${{a.id}}: ${{a.title}}`, g: 'ADR', run: () => setView('overview') }}));
  const q = ST.cmdQuery.trim().toLowerCase();
  return q ? items.filter((i) => i.label.toLowerCase().includes(q) || i.g.toLowerCase().includes(q)) : items;
}}

function openCmdPalette() {{ ST.cmdOpen = true; ST.cmdQuery = ''; ST.cmdIdx = 0; renderCmd(); setTimeout(() => document.getElementById('cmd-inp')?.focus(), 10); }}
function closeCmdPalette() {{ ST.cmdOpen = false; document.getElementById('cmd-root').innerHTML = ''; }}
function renderCmd() {{
  const root = document.getElementById('cmd-root');
  if (!ST.cmdOpen) {{ root.innerHTML = ''; return; }}
  const items = cmdItems();
  root.innerHTML = `
    <div class="backdrop" onclick="if(event.target===this)closeCmdPalette()">
      <div class="modal" role="dialog" aria-modal="true" aria-label="Command Palette">
        <input id="cmd-inp" class="input" placeholder="Jump to view, CLI command, or ADR..." value="${{esc(ST.cmdQuery)}}"
          oninput="ST.cmdQuery=this.value;ST.cmdIdx=0;renderCmdList()" onkeydown="cmdKey(event)" />
        <ul id="cmd-ul" class="cmd-list">${{cmdListHtml(items)}}</ul>
      </div>
    </div>`;
}}
function cmdListHtml(items) {{
  return items.length ? items.map((it, i) => `<li class="cmd-item ${{i===ST.cmdIdx?'selected':''}}" onclick="execCmd(${{i}})"><span>${{esc(it.label)}}</span><span class="kbd">${{esc(it.g)}}</span></li>`).join('') : '<li class="muted" style="padding:10px;">No matches.</li>';
}}
function renderCmdList() {{ const ul = document.getElementById('cmd-ul'); if (ul) ul.innerHTML = cmdListHtml(cmdItems()); }}
function execCmd(i) {{ const it = cmdItems()[i]; closeCmdPalette(); if (it) it.run(); }}
function cmdKey(e) {{
  const n = Math.max(1, cmdItems().length);
  if (e.key === 'ArrowDown') {{ e.preventDefault(); ST.cmdIdx = (ST.cmdIdx + 1) % n; renderCmdList(); }}
  else if (e.key === 'ArrowUp') {{ e.preventDefault(); ST.cmdIdx = (ST.cmdIdx - 1 + n) % n; renderCmdList(); }}
  else if (e.key === 'Enter') {{ e.preventDefault(); execCmd(ST.cmdIdx); }}
  else if (e.key === 'Escape') {{ e.preventDefault(); closeCmdPalette(); }}
}}

document.addEventListener('keydown', (e) => {{
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {{ e.preventDefault(); ST.cmdOpen ? closeCmdPalette() : openCmdPalette(); }}
  else if (e.key === 'Escape') {{ if (ST.cmdOpen) closeCmdPalette(); else if (ST.drawerItem) closeDrawer(); else closeModal(); restoreFocus(); }}
  else if (e.key === 'Tab') {{
    const dlg = document.querySelector('#cmd-root [role="dialog"], #drawer-root [role="dialog"], #modal-root [role="dialog"]');
    if (!dlg) return;
    const f = Array.from(dlg.querySelectorAll('button, [href], input, select, textarea, summary, [tabindex]:not([tabindex="-1"])')).filter((el) => !el.disabled && el.offsetParent !== null);
    if (!f.length) return;
    const first = f[0], last = f[f.length - 1];
    if (!dlg.contains(document.activeElement)) {{ e.preventDefault(); first.focus(); }}
    else if (e.shiftKey && document.activeElement === first) {{ e.preventDefault(); last.focus(); }}
    else if (!e.shiftKey && document.activeElement === last) {{ e.preventDefault(); first.focus(); }}
  }}
}});
function restoreFocus() {{ if (ST.lastFocus && document.body.contains(ST.lastFocus)) ST.lastFocus.focus(); ST.lastFocus = null; }}
// Remember the trigger and move focus into any dialog that opens (modal, drawer, palette).
new MutationObserver(() => {{
  const dlg = document.querySelector('#cmd-root [role="dialog"], #drawer-root [role="dialog"], #modal-root [role="dialog"]');
  if (dlg && !dlg.contains(document.activeElement)) {{
    if (!ST.lastFocus) ST.lastFocus = document.activeElement;
    const t = dlg.querySelector('input, button');
    if (t) t.focus();
  }}
}}).observe(document.body, {{ childList: true, subtree: true }});

renderAll();
</script>
</body>
</html>
"""
