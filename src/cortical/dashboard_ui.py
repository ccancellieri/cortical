"""Accessible, Zero-Build 4-Domain Control Plane Dashboard UI for Cortical.

Renders a complete single-file HTML/CSS/JS SPA (no external CDN dependencies, Python stdlib only)
featuring:
- Persistent Top Context Bar (principal_id switcher, Runtime Model Status pill, Knowledge Index pill, Cmd/Ctrl+K)
- 4-Domain Navigation Sidebar (Knowledge & Files, Models & Runtime, Memory & Inspector, Settings)
- Guided Onboarding 3-step interactive checklist
- Categorized 4-Tab Settings with inline validation, sticky Unsaved Changes bar, and Reset confirmation modal
- Two-Tier Knowledge View, Interactive Merkle File Explorer, Async Crawl Progress, Drag-and-Drop Upload & File Drawer
- Embedding vs LLM Role Separation, Live Health Probes & Blocking Embedding Compatibility Guardrail
- RAG Search Playground, Citation Verifier (with deep-links to File Drawer) & Episode Timeline
"""

from __future__ import annotations


def render_control_plane_html() -> str:
    """Returns the full standalone HTML for Cortical Control Plane Dashboard."""
    return r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Cortical — Multi-Tenant Knowledge &amp; Control Plane</title>
  <style>
    :root {
      --bg: #070b14;
      --bg-elev: #0d1424;
      --card: #121b2e;
      --card-hover: #17223a;
      --border: #22304d;
      --border-strong: #32466e;
      --text: #e6edf7;
      --muted: #93a4be;
      --accent: #38bdf8;
      --accent-soft: rgba(56, 189, 248, 0.14);
      --ok: #34d399;
      --ok-soft: rgba(52, 211, 153, 0.14);
      --warn: #fbbf24;
      --warn-soft: rgba(251, 191, 36, 0.15);
      --err: #f87171;
      --err-soft: rgba(248, 113, 113, 0.15);
      --tenant: #a78bfa;
      --tenant-soft: rgba(167, 139, 250, 0.16);
      --radius: 10px;
      --mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Inter, sans-serif;
    }
    * { box-sizing: border-box; }
    html, body { height: 100%; margin: 0; background: var(--bg); color: var(--text); font-family: var(--sans); font-size: 14px; line-height: 1.5; }
    button, input, select, textarea { font-family: inherit; font-size: inherit; color: var(--text); }
    :focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
    .sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; }

    /* Shell Layout */
    .app-shell { display: grid; grid-template-rows: 58px 1fr; grid-template-columns: 248px 1fr; min-height: 100vh; }
    .topbar {
      grid-column: 1 / -1; display: flex; align-items: center; justify-content: space-between; gap: 12px;
      padding: 0 18px; background: var(--bg-elev); border-bottom: 1px solid var(--border); position: sticky; top: 0; z-index: 40;
    }
    .brand { display: flex; align-items: center; gap: 10px; font-weight: 700; font-size: 15px; letter-spacing: 0.2px; }
    .brand-mark { width: 28px; height: 28px; border-radius: 8px; background: linear-gradient(135deg, #38bdf8, #818cf8); display: grid; place-items: center; font-weight: 800; color: #070b14; }
    .topbar-controls { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }

    .sidebar {
      background: var(--bg-elev); border-right: 1px solid var(--border); padding: 16px 12px;
      display: flex; flex-direction: column; justify-content: space-between; gap: 16px;
    }
    .nav-group { display: flex; flex-direction: column; gap: 4px; }
    .nav-label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); padding: 6px 10px; font-weight: 600; }
    .nav-item {
      display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 8px; border: 1px solid transparent;
      background: transparent; color: var(--muted); cursor: pointer; text-align: left; font-weight: 600; transition: 0.12s;
    }
    .nav-item:hover { background: var(--card); color: var(--text); }
    .nav-item.active { background: var(--accent-soft); color: var(--accent); border-color: rgba(56, 189, 248, 0.32); }
    .nav-footer { border-top: 1px solid var(--border); padding-top: 12px; font-size: 12px; color: var(--muted); display: flex; flex-direction: column; gap: 6px; }
    .nav-footer a { color: var(--accent); text-decoration: none; }
    .nav-footer a:hover { text-decoration: underline; }

    .main { padding: 22px 26px 88px; overflow-y: auto; max-width: 1320px; width: 100%; }

    /* Pills & Badges (never color-only: icon + label) */
    .pill {
      display: inline-flex; align-items: center; gap: 6px; padding: 5px 10px; border-radius: 999px;
      font-size: 12px; font-weight: 600; border: 1px solid var(--border); background: var(--card); white-space: nowrap;
    }
    .pill.ok { color: var(--ok); background: var(--ok-soft); border-color: rgba(52, 211, 153, 0.35); }
    .pill.warn { color: var(--warn); background: var(--warn-soft); border-color: rgba(251, 191, 36, 0.35); }
    .pill.err { color: var(--err); background: var(--err-soft); border-color: rgba(248, 113, 113, 0.35); }
    .pill.info { color: var(--accent); background: var(--accent-soft); border-color: rgba(56, 189, 248, 0.35); }
    .pill.owner { color: #fde68a; background: rgba(245, 158, 11, 0.16); border-color: rgba(245, 158, 11, 0.42); }
    .pill.tenant { color: var(--tenant); background: var(--tenant-soft); border-color: rgba(167, 139, 250, 0.42); }

    .tenant-switch { display: inline-flex; align-items: center; gap: 6px; padding: 3px 8px; border-radius: 999px; border: 1px solid var(--border-strong); background: var(--card); }
    .tenant-switch.is-owner { border-color: rgba(245, 158, 11, 0.5); background: rgba(245, 158, 11, 0.08); }
    .tenant-switch.is-tenant { border-color: rgba(167, 139, 250, 0.55); background: rgba(167, 139, 250, 0.10); }
    .tenant-switch select { background: transparent; border: none; color: var(--text); font-weight: 600; font-size: 12.5px; cursor: pointer; padding: 2px 4px; }
    .tenant-switch select option { background: var(--bg-elev); color: var(--text); }

    /* Buttons & Inputs */
    .btn {
      display: inline-flex; align-items: center; justify-content: center; gap: 6px; padding: 7px 13px; border-radius: 8px;
      border: 1px solid var(--border-strong); background: var(--card); color: var(--text); cursor: pointer; font-weight: 600; font-size: 13px; transition: 0.12s;
    }
    .btn:hover:not(:disabled) { background: var(--card-hover); border-color: var(--accent); }
    .btn:disabled { opacity: 0.48; cursor: not-allowed; }
    .btn.primary { background: #0284c7; border-color: #38bdf8; color: #fff; }
    .btn.primary:hover:not(:disabled) { background: #0369a1; }
    .btn.danger { background: rgba(239, 68, 68, 0.14); border-color: rgba(248, 113, 113, 0.5); color: #fca5a5; }
    .btn.danger:hover:not(:disabled) { background: rgba(239, 68, 68, 0.25); }
    .btn.sm { padding: 4px 9px; font-size: 12px; }
    .btn.ghost { background: transparent; border-color: transparent; color: var(--muted); }
    .btn.ghost:hover:not(:disabled) { background: var(--card); color: var(--text); }

    .input, .select, .textarea {
      width: 100%; padding: 8px 11px; border-radius: 8px; border: 1px solid var(--border-strong);
      background: #080e1c; color: var(--text); font-size: 13.5px;
    }
    .input.invalid, .select.invalid, .textarea.invalid { border-color: var(--err); box-shadow: 0 0 0 2px rgba(248, 113, 113, 0.2); }
    .textarea { min-height: 86px; resize: vertical; font-family: var(--mono); font-size: 12.5px; }
    .field { display: flex; flex-direction: column; gap: 5px; margin-bottom: 14px; }
    .field label { font-weight: 600; font-size: 13px; display: flex; justify-content: space-between; align-items: center; }
    .hint { font-size: 12px; color: var(--muted); }
    .err-msg { font-size: 12px; color: var(--err); font-weight: 500; }
    .ok-msg { font-size: 12px; color: var(--ok); font-weight: 500; }

    /* Cards & Grids */
    .page-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 18px; flex-wrap: wrap; }
    .page-head h1 { margin: 0; font-size: 20px; }
    .page-head p { margin: 4px 0 0; color: var(--muted); font-size: 13px; }
    .card { background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px 18px; margin-bottom: 16px; }
    .card-head { display: flex; justify-content: space-between; align-items: center; gap: 10px; margin-bottom: 12px; flex-wrap: wrap; }
    .card-head h2 { margin: 0; font-size: 15px; display: flex; align-items: center; gap: 8px; }
    .grid-2 { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
    .grid-3 { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
    .mono { font-family: var(--mono); font-size: 12px; }
    .muted { color: var(--muted); }

    /* Tabs */
    .tabs { display: flex; gap: 6px; border-bottom: 1px solid var(--border); margin-bottom: 16px; flex-wrap: wrap; }
    .tab-btn {
      padding: 8px 14px; background: transparent; border: none; border-bottom: 2px solid transparent;
      color: var(--muted); font-weight: 600; cursor: pointer; font-size: 13.5px;
    }
    .tab-btn:hover { color: var(--text); }
    .tab-btn.active { color: var(--accent); border-bottom-color: var(--accent); }

    /* Onboarding Banner */
    .onboarding {
      background: linear-gradient(135deg, rgba(56, 189, 248, 0.11), rgba(167, 139, 250, 0.10));
      border: 1px solid rgba(56, 189, 248, 0.38); border-radius: var(--radius); padding: 16px 18px; margin-bottom: 18px;
    }
    .steps-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin-top: 12px; }
    .step-card { background: rgba(7, 11, 20, 0.65); border: 1px solid var(--border); border-radius: 8px; padding: 12px; display: flex; flex-direction: column; justify-content: space-between; gap: 8px; }
    .step-card.done { border-color: rgba(52, 211, 153, 0.45); }

    /* Tables & Explorer */
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td { padding: 9px 10px; border-bottom: 1px solid var(--border); text-align: left; vertical-align: middle; }
    th { font-size: 11.5px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); font-weight: 600; }
    tr.clickable { cursor: pointer; }
    tr.clickable:hover td { background: var(--card-hover); }

    .dropzone {
      border: 2px dashed var(--border-strong); border-radius: var(--radius); padding: 18px; text-align: center;
      background: rgba(8, 14, 28, 0.6); transition: 0.15s; cursor: pointer;
    }
    .dropzone.dragover { border-color: var(--accent); background: var(--accent-soft); }

    .progress-bar { width: 100%; height: 8px; background: #080e1c; border-radius: 999px; overflow: hidden; border: 1px solid var(--border); }
    .progress-fill { height: 100%; background: linear-gradient(90deg, #38bdf8, #34d399); transition: width 0.2s; }
    .log-box { background: #060912; border: 1px solid var(--border); border-radius: 8px; padding: 10px; max-height: 150px; overflow-y: auto; font-family: var(--mono); font-size: 11.5px; color: #a7f3d0; }

    /* Sticky Unsaved Bar */
    .unsaved-bar {
      position: fixed; bottom: 16px; left: 268px; right: 26px; max-width: 1260px; z-index: 50;
      background: #0f1b33; border: 1px solid var(--warn); border-radius: var(--radius); padding: 12px 18px;
      display: flex; align-items: center; justify-content: space-between; gap: 12px;
      box-shadow: 0 12px 32px rgba(0, 0, 0, 0.55);
    }

    /* Modals & Drawer */
    .backdrop {
      position: fixed; inset: 0; background: rgba(3, 6, 14, 0.72); backdrop-filter: blur(2px);
      z-index: 80; display: flex; align-items: center; justify-content: center; padding: 16px;
    }
    .modal {
      background: var(--bg-elev); border: 1px solid var(--border-strong); border-radius: 12px;
      width: 100%; max-width: 560px; max-height: 85vh; overflow-y: auto; padding: 20px; box-shadow: 0 20px 60px rgba(0,0,0,0.6);
    }
    .drawer-backdrop { position: fixed; inset: 0; background: rgba(3, 6, 14, 0.65); z-index: 75; display: flex; justify-content: flex-end; }
    .drawer {
      width: min(620px, 95vw); height: 100%; background: var(--bg-elev); border-left: 1px solid var(--border-strong);
      padding: 20px; overflow-y: auto; display: flex; flex-direction: column; gap: 14px;
    }
    .code-pre { background: #060912; border: 1px solid var(--border); border-radius: 8px; padding: 12px; overflow: auto; max-height: 280px; font-family: var(--mono); font-size: 12px; white-space: pre-wrap; word-break: break-word; }

    /* Command Palette */
    .cmd-list { list-style: none; margin: 10px 0 0; padding: 0; max-height: 320px; overflow-y: auto; }
    .cmd-item {
      display: flex; justify-content: space-between; align-items: center; padding: 9px 12px; border-radius: 8px;
      cursor: pointer; border: 1px solid transparent;
    }
    .cmd-item:hover, .cmd-item.selected { background: var(--accent-soft); border-color: rgba(56,189,248,0.35); }
    .kbd { font-family: var(--mono); font-size: 11px; padding: 2px 6px; border-radius: 5px; border: 1px solid var(--border-strong); background: var(--bg); color: var(--muted); }

    /* Toasts & Skeleton */
    .toasts { position: fixed; top: 70px; right: 18px; z-index: 95; display: flex; flex-direction: column; gap: 8px; max-width: 380px; }
    .toast { padding: 10px 14px; border-radius: 8px; border: 1px solid var(--border-strong); background: var(--bg-elev); box-shadow: 0 8px 24px rgba(0,0,0,0.45); display: flex; gap: 8px; align-items: flex-start; font-size: 13px; }
    .toast.ok { border-color: var(--ok); }
    .toast.err { border-color: var(--err); }
    .toast.warn { border-color: var(--warn); }
    .skeleton { background: linear-gradient(90deg, #121b2e 25%, #1c2944 50%, #121b2e 75%); background-size: 200% 100%; animation: shimmer 1.2s infinite; border-radius: 6px; height: 18px; }
    @keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }

    @media (max-width: 960px) {
      .app-shell { grid-template-columns: 1fr; }
      .sidebar { flex-direction: row; overflow-x: auto; border-right: none; border-bottom: 1px solid var(--border); padding: 8px; }
      .nav-group { flex-direction: row; }
      .nav-footer, .nav-label { display: none; }
      .grid-2, .grid-3, .steps-grid { grid-template-columns: 1fr; }
      .unsaved-bar { left: 16px; right: 16px; }
    }
  </style>
</head>
<body>
  <div id="app" class="app-shell">
    <!-- Persistent Top Context Bar -->
    <header class="topbar" role="banner">
      <div class="brand">
        <div class="brand-mark" aria-hidden="true">C</div>
        <span>Cortical</span>
        <span class="pill info" style="font-size:11px;">v0.3 Control Plane</span>
      </div>
      <div class="topbar-controls">
        <div id="tenant-switcher-wrap" class="tenant-switch is-owner" title="Active RBAC Tenant / principal_id">
          <span id="tenant-icon" aria-hidden="true">👑</span>
          <label for="principal-select" class="sr-only">Active principal_id</label>
          <select id="principal-select" aria-label="Active tenant principal_id"></select>
          <button class="btn sm ghost" id="btn-new-tenant" title="Create scoped tenant" aria-label="Create scoped tenant">＋</button>
        </div>
        <button id="runtime-pill" class="pill ok" title="Runtime model health — click to open Models" onclick="setDomain('models')">
          <span aria-hidden="true">●</span><span>Embed: Ready | LLM: Ready</span>
        </button>
        <div style="display:inline-flex;align-items:center;gap:6px;">
          <span id="index-pill" class="pill info"><span aria-hidden="true">○</span><span>Index: Loading...</span></span>
          <button id="btn-quick-sync" class="btn sm" onclick="triggerCrawl(null, false)" title="Run Merkle Delta Sync for active tenant">⟳ Delta Sync</button>
        </div>
        <button class="btn sm" onclick="openCmdPalette()" aria-label="Open Command Palette">⌘K <span class="kbd">Ctrl+K</span></button>
      </div>
    </header>

    <!-- 4-Domain Navigation Sidebar -->
    <aside class="sidebar" aria-label="Primary Navigation">
      <nav class="nav-group">
        <div class="nav-label">Control Plane</div>
        <button class="nav-item active" data-domain="files" onclick="setDomain('files')">📁 Knowledge &amp; Files</button>
        <button class="nav-item" data-domain="models" onclick="setDomain('models')">🧠 Models &amp; Runtime</button>
        <button class="nav-item" data-domain="memory" onclick="setDomain('memory')">🔎 Memory &amp; Inspector</button>
        <button class="nav-item" data-domain="settings" onclick="setDomain('settings')">⚙️ Settings</button>
      </nav>
      <div class="nav-footer">
        <div>Zero-dependency stdlib UI</div>
        <div><a href="./settings.html">🛡️ Privacy Vault (Zero-Server)</a></div>
        <div><a href="./help.html">❓ Reference &amp; Docs</a></div>
      </div>
    </aside>

    <!-- Main Workspace -->
    <main class="main" id="main-view" tabindex="-1"></main>
  </div>

  <!-- Sticky Unsaved Changes Bar -->
  <div id="unsaved-bar" class="unsaved-bar" style="display:none;" role="status" aria-live="polite">
    <div>
      <strong>⚠ Unsaved Changes</strong>
      <span id="unsaved-count" class="muted" style="margin-left:8px;"></span>
    </div>
    <div style="display:flex;gap:8px;">
      <button class="btn" onclick="discardSettings()">Discard</button>
      <button class="btn primary" id="btn-save-settings" onclick="saveSettings()">Save &amp; Apply</button>
    </div>
  </div>

  <!-- Overlays: Modal, File Drawer, Command Palette, Toasts -->
  <div id="modal-root"></div>
  <div id="drawer-root"></div>
  <div id="cmd-root"></div>
  <div id="toasts" class="toasts" aria-live="polite" aria-atomic="true"></div>

<script>
const STATE = {
  domain: 'files',
  settingsTab: 'general_rbac',
  memoryTab: 'search',
  principalId: localStorage.getItem('cortical_principal_id') || 'local_owner',
  context: null,
  roots: [],
  filesData: { files: [], counts: { indexed: 0, modified: 0, ignored: 0, error: 0 }, total: 0 },
  fileFilterStatus: 'all',
  fileFilterPrivacy: 'all',
  fileFilterRoot: '',
  fileFilterQuery: '',
  drawerTier: 'light',
  crawlJob: null,
  crawlPollTimer: null,
  modelsStatus: null,
  settingsSaved: null,
  settingsDraft: null,
  settingsErrors: {},
  pathCheck: null,
  searchResults: [],
  searchQuery: '',
  searchDepth: 1,
  searchLimit: 10,
  episodes: [],
  citationResult: null,
  citationClaim: '',
  drawerDoc: null,
  cmdOpen: false,
  cmdQuery: '',
  cmdIdx: 0,
  loading: true,
};

function esc(s) {
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function fmtBytes(n) {
  const b = Number(n || 0);
  if (b < 1024) return b + ' B';
  if (b < 1048576) return (b / 1024).toFixed(1) + ' KB';
  return (b / 1048576).toFixed(2) + ' MB';
}
function fmtTime(ts) {
  if (!ts) return 'Never';
  try { return new Date(ts * 1000).toLocaleString(); } catch { return '—'; }
}
function shortHash(h) { return h ? String(h).slice(0, 12) : '—'; }
function deepClone(obj) { return JSON.parse(JSON.stringify(obj)); }

function toast(kind, msg) {
  const box = document.getElementById('toasts');
  const el = document.createElement('div');
  el.className = 'toast ' + kind;
  const icon = kind === 'ok' ? '✓' : (kind === 'err' ? '⚠' : (kind === 'warn' ? '⚡' : 'ℹ'));
  el.innerHTML = `<span aria-hidden="true">${icon}</span><div>${esc(msg)}</div>`;
  box.appendChild(el);
  setTimeout(() => { el.remove(); }, 4500);
}

async function api(method, path, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const resp = await fetch(path, opts);
  const data = await resp.json().catch(() => ({ ok: false, error: 'Invalid JSON response' }));
  if (!resp.ok && resp.status !== 409) {
    throw Object.assign(new Error(data.error || ('HTTP ' + resp.status)), { status: resp.status, data });
  }
  return { status: resp.status, data };
}

// ---- Global Data Sync ----
async function refreshContext() {
  const { data } = await api('GET', '/api/context?principal_id=' + encodeURIComponent(STATE.principalId));
  STATE.context = data;
  if (data.active_job && data.active_job.status === 'running') {
    STATE.crawlJob = data.active_job;
    ensureCrawlPolling(data.active_job.job_id);
  }
  renderTopBar();
}

async function refreshDomainData() {
  STATE.loading = true;
  renderMain();
  try {
    await refreshContext();
    if (STATE.domain === 'files') {
      const [rRes, fRes] = await Promise.all([
        api('GET', '/api/roots?principal_id=' + encodeURIComponent(STATE.principalId)),
        api('GET', `/api/files/tree?principal_id=${encodeURIComponent(STATE.principalId)}&root_id=${encodeURIComponent(STATE.fileFilterRoot)}&status=${encodeURIComponent(STATE.fileFilterStatus)}&q=${encodeURIComponent(STATE.fileFilterQuery)}`),
      ]);
      STATE.roots = rRes.data.roots || [];
      STATE.filesData = fRes.data;
    } else if (STATE.domain === 'models') {
      const mRes = await api('GET', '/api/models/status');
      STATE.modelsStatus = mRes.data;
    } else if (STATE.domain === 'memory') {
      const epRes = await api('GET', '/api/episodes?principal_id=' + encodeURIComponent(STATE.principalId));
      STATE.episodes = epRes.data.episodes || [];
    } else if (STATE.domain === 'settings') {
      const sRes = await api('GET', '/api/settings');
      STATE.settingsSaved = sRes.data.settings;
      if (!STATE.settingsDraft) STATE.settingsDraft = deepClone(sRes.data.settings);
      validateDraftInline();
    }
  } catch (err) {
    toast('err', 'Failed to load data: ' + err.message);
  } finally {
    STATE.loading = false;
    renderMain();
    renderUnsavedBar();
  }
}

function setDomain(dom, opts = {}) {
  STATE.domain = dom;
  if (opts.settingsTab) STATE.settingsTab = opts.settingsTab;
  if (opts.memoryTab) STATE.memoryTab = opts.memoryTab;
  document.querySelectorAll('.nav-item').forEach((b) => b.classList.toggle('active', b.dataset.domain === dom));
  refreshDomainData();
}

function switchPrincipal(pid) {
  STATE.principalId = pid || 'local_owner';
  localStorage.setItem('cortical_principal_id', STATE.principalId);
  STATE.fileFilterRoot = '';
  STATE.searchResults = [];
  STATE.citationResult = null;
  toast('info', 'Switched active tenant to ' + STATE.principalId);
  refreshDomainData();
}

// ---- Top Context Bar ----
function renderTopBar() {
  const ctx = STATE.context;
  if (!ctx) return;
  const sel = document.getElementById('principal-select');
  const wrap = document.getElementById('tenant-switcher-wrap');
  const icon = document.getElementById('tenant-icon');
  const isOwner = STATE.principalId === 'local_owner';
  wrap.className = 'tenant-switch ' + (isOwner ? 'is-owner' : 'is-tenant');
  icon.textContent = isOwner ? '👑' : '🔒';
  sel.innerHTML = (ctx.principals || []).map((p) =>
    `<option value="${esc(p.principal_id)}" ${p.principal_id === STATE.principalId ? 'selected' : ''}>${esc(p.principal_id)}${p.role === 'owner' ? ' (Owner)' : ' (Tenant)'}</option>`
  ).join('');

  // Runtime pill
  const emb = ctx.runtime?.embedding || {};
  const llm = ctx.runtime?.llm || {};
  const embLbl = emb.status === 'online' ? 'Online' : (emb.status === 'offline' ? 'Offline' : 'Ready');
  const llmLbl = llm.status === 'online' ? 'Online' : (llm.status === 'offline' ? 'Offline' : 'Ready');
  const rtPill = document.getElementById('runtime-pill');
  const hasOffline = emb.status === 'offline' || llm.status === 'offline';
  rtPill.className = 'pill ' + (hasOffline ? 'err' : 'ok');
  rtPill.innerHTML = `<span aria-hidden="true">${hasOffline ? '⚠' : '✓'}</span><span>Embed: ${esc(embLbl)} | LLM: ${esc(llmLbl)}</span>`;

  // Index pill
  const idx = ctx.index || {};
  const idxPill = document.getElementById('index-pill');
  const stMap = {
    synced: ['ok', '✓', `Synced (${idx.doc_count || 0} docs)`],
    syncing: ['info', '⟳', 'Syncing...'],
    changes_detected: ['warn', '⚡', 'Changes Detected'],
    error: ['err', '⚠', 'Index Error'],
    empty: ['warn', '○', 'No Sources'],
  };
  const [cls, sym, label] = stMap[idx.status] || stMap.empty;
  idxPill.className = 'pill ' + cls;
  idxPill.innerHTML = `<span aria-hidden="true">${sym}</span><span>${esc(label)}</span>`;
}

document.getElementById('principal-select').addEventListener('change', (e) => switchPrincipal(e.target.value));
document.getElementById('btn-new-tenant').addEventListener('click', () => openCreateTenantModal());

// ---- Guided Onboarding ----
function renderOnboardingBanner() {
  const ob = STATE.context?.onboarding;
  if (!ob || !ob.show_onboarding) return '';
  return `
    <section class="onboarding" aria-label="Guided Setup Checklist">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;">
        <div>
          <strong>🚀 Guided Setup — Get your Knowledge Base running in 3 steps</strong>
          <div class="hint">Complete these steps to enable FTS5 search, Merkle delta sync, and citation verification for <span class="mono">${esc(STATE.principalId)}</span>.</div>
        </div>
      </div>
      <div class="steps-grid">
        <div class="step-card ${ob.step_models_configured ? 'done' : ''}">
          <div><span class="pill ${ob.step_models_configured ? 'ok' : 'info'}">${ob.step_models_configured ? '✓ Done' : 'Step 1'}</span></div>
          <div><strong>Configure Models</strong><div class="hint">Verify Embedding &amp; Reasoning LLM runtimes.</div></div>
          <button class="btn sm" onclick="setDomain('models')">Open Models →</button>
        </div>
        <div class="step-card ${ob.step_root_registered ? 'done' : ''}">
          <div><span class="pill ${ob.step_root_registered ? 'ok' : 'warn'}">${ob.step_root_registered ? '✓ Done' : 'Step 2'}</span></div>
          <div><strong>Register Knowledge Source</strong><div class="hint">Add a local directory to track with Merkle hashes.</div></div>
          <button class="btn sm primary" onclick="setDomain('files'); setTimeout(()=>document.getElementById('new-root-path')?.focus(), 120)">Add Root Directory</button>
        </div>
        <div class="step-card ${ob.step_first_crawl_done ? 'done' : ''}">
          <div><span class="pill ${ob.step_first_crawl_done ? 'ok' : 'info'}">${ob.step_first_crawl_done ? '✓ Done' : 'Step 3'}</span></div>
          <div><strong>Run First Merkle Crawl</strong><div class="hint">Index files into SQLite WAL + FTS5.</div></div>
          <button class="btn sm" ${ob.step_root_registered ? '' : 'disabled'} onclick="triggerCrawl(null, false)">Run First Crawl</button>
        </div>
      </div>
    </section>
  `;
}

// ---- Main Router ----
function renderMain() {
  const el = document.getElementById('main-view');
  if (STATE.loading && !STATE.context) {
    el.innerHTML = `<div class="card"><div class="skeleton" style="width:40%;margin-bottom:12px;"></div><div class="skeleton" style="width:85%;margin-bottom:8px;"></div><div class="skeleton" style="width:65%;"></div></div>`;
    return;
  }
  if (STATE.domain === 'files') el.innerHTML = renderOnboardingBanner() + renderFilesDomain();
  else if (STATE.domain === 'models') el.innerHTML = renderModelsDomain();
  else if (STATE.domain === 'memory') el.innerHTML = renderMemoryDomain();
  else if (STATE.domain === 'settings') el.innerHTML = renderSettingsDomain();
  bindDynamicHandlers();
}

// =========================================================================
// DOMAIN 1: KNOWLEDGE & FILES (Merkle Explorer, Crawl Progress, Upload)
// =========================================================================
function renderFilesDomain() {
  const roots = STATE.roots || [];
  const fdata = STATE.filesData || { files: [], counts: {} };
  const job = STATE.crawlJob;
  const statusPill = (st) => {
    const m = {
      synced: ['ok', '✓ Synced'], indexed: ['ok', '✓ Indexed'],
      syncing: ['info', '⟳ Syncing'], modified: ['warn', '⚡ Modified'],
      changes_detected: ['warn', '⚡ Changes Detected'], ignored: ['info', '⊘ Ignored'],
      error: ['err', '⚠ Error'],
    };
    const [c, lbl] = m[st] || ['info', st];
    return `<span class="pill ${c}">${esc(lbl)}</span>`;
  };

  const progressHtml = job ? `
    <div class="card" aria-live="polite">
      <div class="card-head">
        <h2>⟳ Async Crawl Job <span class="mono muted">${esc(job.job_id)}</span> ${statusPill(job.status === 'completed' ? 'synced' : (job.status === 'running' ? 'syncing' : 'error'))}</h2>
        <span class="mono">${job.processed || 0} / ${job.total || 0} files (${job.percent || 0}%)</span>
      </div>
      <div class="progress-bar" role="progressbar" aria-valuenow="${job.percent || 0}" aria-valuemin="0" aria-valuemax="100">
        <div class="progress-fill" style="width:${job.percent || 0}%"></div>
      </div>
      <div class="log-box" style="margin-top:10px;">${(job.logs || []).map((l) => `<div>${esc(l)}</div>`).join('')}</div>
    </div>
  ` : '';

  const rootsHtml = roots.length === 0
    ? `<div class="muted" style="padding:10px 0;">No root directories registered for <strong>${esc(STATE.principalId)}</strong>. Add a directory above to begin Merkle-tree tracking.</div>`
    : `<div style="display:flex;flex-direction:column;gap:10px;">
        ${roots.map((r) => `
          <div style="border:1px solid var(--border);border-radius:8px;padding:12px 14px;display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;background:#0a1120;">
            <div>
              <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
                <strong class="mono">${esc(r.path)}</strong>
                ${statusPill(r.status)}
                <span class="pill ${r.principal_id === 'local_owner' ? 'owner' : 'tenant'}">${r.principal_id === 'local_owner' ? '👑' : '🔒'} ${esc(r.principal_id)}</span>
              </div>
              <div class="hint" style="margin-top:4px;">
                Docs: <strong>${r.doc_count || 0}</strong> · Chunks: <strong>${r.chunk_count || 0}</strong> ·
                Merkle: <span class="mono">${esc(shortHash(r.merkle_root_hash))}</span> ·
                Last Crawl: ${esc(fmtTime(r.last_crawl_at))}
              </div>
              ${r.error_message ? `<div class="err-msg">${esc(r.error_message)}</div>` : ''}
            </div>
            <div style="display:flex;gap:6px;flex-wrap:wrap;">
              <button class="btn sm primary" onclick="triggerCrawl('${esc(r.root_id)}', false)">⟳ Delta Sync</button>
              <button class="btn sm" onclick="triggerSanitizedCrawl('${esc(r.root_id)}')">🛡 Sanitized Crawl</button>
              <button class="btn sm" onclick="confirmFullReindex('${esc(r.root_id)}', '${esc(r.path)}')">↻ Full Re-index</button>
              <button class="btn sm danger" onclick="confirmRemoveRoot('${esc(r.root_id)}', '${esc(r.path)}')">✕ Remove</button>
            </div>
          </div>
        `).join('')}
      </div>`;

  const counts = fdata.counts || {};
  const privSum = fdata.privacy_summary || { sanitized: 0, raw: 0, private_gated: 0, entities_masked_total: 0, entities_by_category: {} };
  const files = fdata.files || [];
  const privBadge = (f) => {
    if (f.private_gated) return `<span class="pill err">🔒 PRIVATE-GATED</span> <span class="pill info">${esc(f.privacy_profile || 'max_security')}</span>`;
    if (f.sanitized) return `<span class="pill ok">🛡 SANITIZED</span> <span class="pill info">${esc(f.privacy_profile || 'medium')}</span>`;
    return `<span class="pill warn">⚠ RAW</span>`;
  };
  const highlightTok = (txt) => esc(txt || '(empty)').replace(/(\[(?:PERSON|PERSON_NAME|EMAIL|IBAN|TAX_ID|SECRET|PHONE|IP|CUSTOM|ORG|METADATA)_\d+\]|\[REDACTED\])/g, '<mark style="background:rgba(52,211,153,0.22);color:#6ee7b7;padding:1px 4px;border-radius:4px;">$1</mark>');

  return `
    <div class="page-head">
      <div>
        <h1>📁 Knowledge &amp; Files</h1>
        <p>Manage tenant-scoped root directories, run deterministic Merkle-tree delta crawls, and inspect indexed files.</p>
      </div>
    </div>

    ${progressHtml}

    <div class="card">
      <div class="card-head"><h2>1. Registered Root Directories</h2></div>
      <div style="display:flex;gap:8px;margin-bottom:10px;flex-wrap:wrap;">
        <div style="flex:1;min-width:260px;">
          <label for="new-root-path" class="sr-only">Directory path to register</label>
          <input id="new-root-path" class="input mono" placeholder="/path/to/knowledge/folder" oninput="debounceValidateRootPath(this.value)" />
        </div>
        <button class="btn primary" id="btn-add-root" onclick="registerRoot()">＋ Register Root</button>
      </div>
      <div id="root-path-feedback" style="margin-bottom:10px;"></div>
      ${rootsHtml}
    </div>

    ${roots.length > 0 ? `
    <div class="card">
      <div class="card-head">
        <h2>⬆️ Direct File Upload (Auto Delta Sync)</h2>
        <select id="upload-root-select" class="select" style="width:auto;min-width:220px;" aria-label="Target root directory for upload">
          ${roots.map((r) => `<option value="${esc(r.root_id)}">${esc(r.path)} (${esc(r.principal_id)})</option>`).join('')}
        </select>
      </div>
      <div id="file-dropzone" class="dropzone" tabindex="0" role="button" aria-label="Drop files here or click to upload">
        <div><strong>Drop files here</strong> or click to select — saved into the target root and indexed automatically via Delta Sync.</div>
        <input id="file-upload-input" type="file" multiple style="display:none;" />
      </div>
    </div>` : ''}

    <div class="card">
      <div class="card-head">
        <h2>2. Interactive Merkle File Explorer (${files.length})</h2>
        <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;">
          ${['all','indexed','modified','ignored','error'].map((st) => `
            <button class="btn sm ${STATE.fileFilterStatus === st ? 'primary' : ''}" onclick="setFileFilter('status','${st}')">
              ${st === 'all' ? 'All' : st.charAt(0).toUpperCase() + st.slice(1)} ${st !== 'all' ? '(' + (counts[st] || 0) + ')' : ''}
            </button>
          `).join('')}
        </div>
      </div>
      <div style="display:flex;gap:8px;margin-bottom:10px;flex-wrap:wrap;align-items:center;">
        <span class="hint"><strong>Privacy Audit:</strong> ${privSum.sanitized || 0} sanitized · ${privSum.raw || 0} raw · ${privSum.private_gated || 0} private-gated · <strong>${privSum.entities_masked_total || 0}</strong> PII entities masked</span>
        <div style="display:flex;gap:6px;flex-wrap:wrap;">
          ${[['all','All Privacy'],['sanitized','🛡 Sanitized'],['private_gated','🔒 Private-Gated'],['raw','⚠ Raw']].map(([pv,lbl]) => `
            <button class="btn sm ${STATE.fileFilterPrivacy === pv ? 'primary' : ''}" onclick="setFileFilter('privacy','${pv}')">${lbl}</button>
          `).join('')}
        </div>
      </div>
      <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;">
        <input class="input" style="max-width:340px;" placeholder="Filter by relative path..." value="${esc(STATE.fileFilterQuery)}" oninput="setFileFilter('q', this.value)" aria-label="Filter files by path" />
        <select class="select" style="max-width:280px;" onchange="setFileFilter('root', this.value)" aria-label="Filter by root directory">
          <option value="">All Registered Roots</option>
          ${roots.map((r) => `<option value="${esc(r.root_id)}" ${STATE.fileFilterRoot === r.root_id ? 'selected' : ''}>${esc(r.path)}</option>`).join('')}
        </select>
      </div>
      ${files.length === 0 ? `<div class="muted" style="padding:14px 0;">No files match the current filter. Run <strong>Delta Sync</strong> or <strong>Sanitized Crawl</strong> to index your registered roots.</div>` : `
      <div style="overflow-x:auto;">
        <table>
          <thead><tr><th>File Path</th><th>Status</th><th>Privacy</th><th>PII Masked</th><th>Size</th><th>Merkle Hash</th><th>RBAC</th></tr></thead>
          <tbody>
            ${files.map((f) => `
              <tr class="clickable" tabindex="0" onclick="openFileDrawer('${esc(f.doc_id)}')" onkeydown="if(event.key==='Enter')openFileDrawer('${esc(f.doc_id)}')">
                <td class="mono"><strong>${esc(f.rel_path)}</strong></td>
                <td>${statusPill(f.status)}</td>
                <td>${privBadge(f)}</td>
                <td>${f.entities_masked || 0}</td>
                <td>${esc(fmtBytes(f.file_size))}</td>
                <td class="mono muted">${esc(shortHash(f.merkle_hash))}</td>
                <td><span class="pill ${f.principal_id === 'local_owner' ? 'owner' : 'tenant'}">${esc(f.principal_id)}</span></td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>`}
    </div>
  `;
}

let _pathTimer = null;
function debounceValidateRootPath(val) {
  clearTimeout(_pathTimer);
  const fb = document.getElementById('root-path-feedback');
  if (!val.trim()) { if (fb) fb.innerHTML = ''; return; }
  _pathTimer = setTimeout(async () => {
    try {
      const { data } = await api('POST', '/api/validate/path', { path: val, require_dir: true });
      if (fb) fb.innerHTML = data.valid
        ? `<span class="ok-msg">✓ Valid readable directory: <span class="mono">${esc(data.resolved)}</span></span>`
        : `<span class="err-msg">⚠ ${esc(data.error)}</span>`;
    } catch {}
  }, 220);
}

async function registerRoot() {
  const inp = document.getElementById('new-root-path');
  const p = (inp?.value || '').trim();
  if (!p) { toast('warn', 'Enter a directory path first.'); return; }
  try {
    await api('POST', '/api/roots', { path: p, principal_id: STATE.principalId });
    toast('ok', 'Registered root directory: ' + p);
    await refreshDomainData();
  } catch (err) {
    toast('err', err.message);
  }
}

async function triggerCrawl(rootId, fullReindex) {
  try {
    const { data } = await api('POST', '/api/crawl/start', {
      root_id: rootId,
      principal_id: STATE.principalId,
      full_reindex: Boolean(fullReindex),
    });
    STATE.crawlJob = data.job;
    toast('info', (fullReindex ? 'Full Re-index' : 'Delta Sync') + ' started.');
    if (STATE.domain === 'files') renderMain();
    ensureCrawlPolling(data.job.job_id);
  } catch (err) {
    toast('err', 'Failed to start crawl: ' + err.message);
  }
}

function ensureCrawlPolling(jobId) {
  clearInterval(STATE.crawlPollTimer);
  STATE.crawlPollTimer = setInterval(async () => {
    try {
      const { data } = await api('GET', '/api/crawl/status?job_id=' + encodeURIComponent(jobId));
      STATE.crawlJob = data.job;
      if (STATE.domain === 'files') renderMain();
      if (!data.job || data.job.status !== 'running') {
        clearInterval(STATE.crawlPollTimer);
        STATE.crawlPollTimer = null;
        if (data.job?.status === 'completed') toast('ok', 'Crawl completed successfully.');
        else if (data.job?.status === 'error') toast('err', 'Crawl failed: ' + data.job.error);
        refreshDomainData();
      }
    } catch {
      clearInterval(STATE.crawlPollTimer);
    }
  }, 450);
}

function confirmFullReindex(rootId, path) {
  openConfirmModal({
    title: 'Confirm Full Re-index',
    body: `Re-read, re-chunk, and recompute all Merkle hashes for <code class="mono">${esc(path)}</code>? This is more expensive than Delta Sync and will overwrite existing chunk metadata.`,
    confirmLabel: 'Run Full Re-index',
    danger: false,
    onConfirm: () => triggerCrawl(rootId, true),
  });
}

function confirmRemoveRoot(rootId, path) {
  openConfirmModal({
    title: 'Remove Knowledge Source',
    body: `Remove <code class="mono">${esc(path)}</code> from Cortical? Indexed documents, chunks, and FTS5 entries for this source will be deleted from SQLite (your files on disk will NOT be touched).`,
    confirmLabel: 'Remove Source',
    danger: true,
    onConfirm: async () => {
      await api('DELETE', `/api/roots?root_id=${encodeURIComponent(rootId)}&principal_id=${encodeURIComponent(STATE.principalId)}`);
      toast('ok', 'Knowledge source removed.');
      await refreshDomainData();
    },
  });
}

async function triggerSanitizedCrawl(rootId) {
  try {
    const { data } = await api('POST', '/api/crawl/start', {
      root_id: rootId,
      principal_id: STATE.principalId,
      full_reindex: false,
      sanitize: true,
      privacy_profile: 'medium',
    });
    STATE.crawlJob = data.job;
    toast('info', 'Sanitized Crawl started (medium profile).');
    if (STATE.domain === 'files') renderMain();
    ensureCrawlPolling(data.job.job_id);
  } catch (err) {
    toast('err', 'Failed to start sanitized crawl: ' + err.message);
  }
}

function setFileFilter(kind, val) {
  if (kind === 'status') STATE.fileFilterStatus = val;
  if (kind === 'privacy') STATE.fileFilterPrivacy = val;
  if (kind === 'root') STATE.fileFilterRoot = val;
  if (kind === 'q') STATE.fileFilterQuery = val;
  api('GET', `/api/files/tree?principal_id=${encodeURIComponent(STATE.principalId)}&root_id=${encodeURIComponent(STATE.fileFilterRoot)}&status=${encodeURIComponent(STATE.fileFilterStatus)}&privacy=${encodeURIComponent(STATE.fileFilterPrivacy)}&q=${encodeURIComponent(STATE.fileFilterQuery)}`)
    .then(({ data }) => { STATE.filesData = data; renderMain(); })
    .catch((e) => toast('err', e.message));
}

async function handleFileUploadList(fileList) {
  const rid = document.getElementById('upload-root-select')?.value || STATE.roots[0]?.root_id;
  if (!rid) { toast('warn', 'Register a root directory first.'); return; }
  let lastJob = null;
  for (const file of Array.from(fileList || [])) {
    const buf = await file.arrayBuffer();
    const bytes = new Uint8Array(buf);
    let bin = '';
    for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
    const b64 = btoa(bin);
    const { data } = await api('POST', '/api/files/upload', {
      root_id: rid, principal_id: STATE.principalId, filename: file.name, content_base64: b64, auto_crawl: true,
    });
    if (data.job) lastJob = data.job;
  }
  toast('ok', `Uploaded ${fileList.length} file(s) and triggered Delta Sync.`);
  if (lastJob) { STATE.crawlJob = lastJob; ensureCrawlPolling(lastJob.job_id); }
  refreshDomainData();
}

async function openFileDrawer(docId) {
  try {
    const { data } = await api('GET', `/api/files/inspect?doc_id=${encodeURIComponent(docId)}&principal_id=${encodeURIComponent(STATE.principalId)}`);
    STATE.drawerDoc = data.document;
    renderFileDrawer();
  } catch (err) {
    toast('err', err.message);
  }
}

function renderFileDrawer() {
  const root = document.getElementById('drawer-root');
  const d = STATE.drawerDoc;
  if (!d) { root.innerHTML = ''; return; }
  root.innerHTML = `
    <div class="drawer-backdrop" onclick="if(event.target===this)closeFileDrawer()">
      <div class="drawer" role="dialog" aria-modal="true" aria-label="File Inspection Drawer">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px;">
          <div>
            <h2 style="margin:0;font-size:17px;">📄 ${esc(d.title || d.rel_path)}</h2>
            <div class="mono muted" style="margin-top:4px;">${esc(d.rel_path)}</div>
          </div>
          <button class="btn sm" onclick="closeFileDrawer()" aria-label="Close file inspector">✕ Close</button>
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;">
          <span class="pill ${d.principal_id === 'local_owner' ? 'owner' : 'tenant'}">${esc(d.principal_id)}</span>
          <span class="pill ok">✓ ${esc(d.status)}</span>
          ${d.private_gated ? '<span class="pill err">🔒 PRIVATE-GATED</span>' : (d.sanitized ? `<span class="pill ok">🛡 SANITIZED (${esc(d.privacy_profile)})</span>` : '<span class="pill warn">⚠ RAW</span>')}
          <span class="pill info">${esc(fmtBytes(d.file_size))}</span>
          <span class="pill info">${(d.chunks || []).length} chunks</span>
          <span class="pill info">${d.entities_masked || 0} PII masked</span>
        </div>
        <div class="card" style="margin:0;">
          <div class="hint"><strong>Merkle Node Hash:</strong> <span class="mono">${esc(d.merkle_hash)}</span></div>
          <div class="hint"><strong>Content SHA-256:</strong> <span class="mono">${esc(d.content_hash)}</span></div>
          <div class="hint"><strong>Indexed At:</strong> ${esc(fmtTime(d.indexed_at))}</div>
        </div>
        ${(d.warnings || []).length ? `<div class="card" style="margin:0;border-color:var(--warn);"><strong>⚠ Indexing Warnings</strong><ul>${d.warnings.map((w) => `<li>${esc(w)}</li>`).join('')}</ul></div>` : ''}
        <div>
          <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px;">
            <strong>4-Tier Summary / Sanitized Preview</strong>
            <div style="display:flex;gap:4px;">
              ${['light','medium','high','max'].map((t) => `<button class="btn sm ${STATE.drawerTier===t?'primary':''}" onclick="STATE.drawerTier='${t}';renderFileDrawer()">${t.toUpperCase()}</button>`).join('')}
            </div>
          </div>
          <pre class="code-pre">${esc((d.summaries && d.summaries[STATE.drawerTier]) || d.preview || '(empty)').replace(/(\[(?:PERSON|PERSON_NAME|EMAIL|IBAN|TAX_ID|SECRET|PHONE|IP|CUSTOM|ORG|METADATA)_\d+\]|\[REDACTED\])/g, '<mark style="background:rgba(52,211,153,0.22);color:#6ee7b7;padding:1px 4px;border-radius:4px;">$1</mark>')}</pre>
        </div>
        <div>
          <strong>Chunk Metadata (${(d.chunks || []).length})</strong>
          <table>
            <thead><tr><th>#</th><th>Offsets</th><th>Tokens</th><th>Embed Model</th></tr></thead>
            <tbody>
              ${(d.chunks || []).map((c) => `
                <tr>
                  <td>${c.chunk_index}</td>
                  <td class="mono">${c.char_start}–${c.char_end}</td>
                  <td>${c.token_est}</td>
                  <td class="mono muted">${esc(c.embedding_model || 'fts5-only')} ${c.embedding_dim ? '(' + c.embedding_dim + 'd)' : ''}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;
}
function closeFileDrawer() { STATE.drawerDoc = null; renderFileDrawer(); }

// =========================================================================
// DOMAIN 2: MODELS & RUNTIME (Role Separation, Probes, Embed Guardrail)
// =========================================================================
function renderModelsDomain() {
  const ms = STATE.modelsStatus;
  if (!ms) return `<div class="card"><div class="skeleton" style="width:60%;"></div></div>`;
  const emb = ms.models.embedding || {};
  const llm = ms.models.llm || {};
  const embProbe = ms.probes?.embedding;
  const llmProbe = ms.probes?.llm;

  const probeBadge = (p) => {
    if (!p) return `<span class="pill info">○ Untested</span>`;
    if (p.status === 'online') return `<span class="pill ok">✓ Online (${p.latency_ms} ms)</span>`;
    return `<span class="pill err">⚠ Offline (${p.latency_ms} ms)</span>`;
  };

  return `
    <div class="page-head">
      <div>
        <h1>🧠 Models &amp; Runtime</h1>
        <p>Separate Embedding (vector indexing) and Chat/Reasoning LLM runtimes with live health probes and compatibility guardrails.</p>
      </div>
    </div>

    <div class="grid-2">
      <!-- Embedding Model Card -->
      <div class="card">
        <div class="card-head">
          <h2>📐 Embedding Model</h2>
          <div style="display:flex;gap:6px;">
            <span class="pill ${emb.provider_type === 'local' ? 'ok' : 'info'}">${emb.provider_type === 'local' ? '💻 Local' : '☁️ Remote API'}</span>
            ${probeBadge(embProbe)}
          </div>
        </div>
        <p class="hint" style="margin-top:0;">Used exclusively for vector indexing and semantic retrieval. Changing model family or vector dimensions requires a Full Re-index.</p>
        <div class="field">
          <label for="m-emb-type">Provider Type</label>
          <select id="m-emb-type" class="select">
            <option value="local" ${emb.provider_type === 'local' ? 'selected' : ''}>Local Runtime (Ollama / Local OpenAI-compat)</option>
            <option value="remote" ${emb.provider_type === 'remote' ? 'selected' : ''}>Remote API (OpenAI / Hosted)</option>
          </select>
        </div>
        <div class="field">
          <label for="m-emb-endpoint">Endpoint URL</label>
          <input id="m-emb-endpoint" class="input mono" value="${esc(emb.endpoint)}" />
        </div>
        <div class="field">
          <label for="m-emb-id">Embedding Model ID</label>
          <input id="m-emb-id" class="input mono" list="emb-catalog-list" value="${esc(emb.model_id)}" onchange="syncEmbMetaFromCatalog(this.value)" />
          <datalist id="emb-catalog-list">${Object.keys(ms.embedding_catalog || {}).map((k) => `<option value="${esc(k)}">`).join('')}</datalist>
        </div>
        <div class="grid-3">
          <div class="field"><label for="m-emb-dim">Vector Dim</label><input id="m-emb-dim" type="number" class="input mono" value="${esc(emb.dimensions)}" /></div>
          <div class="field"><label for="m-emb-tok">Tokenizer</label><input id="m-emb-tok" class="input mono" value="${esc(emb.tokenizer_family)}" /></div>
          <div class="field"><label for="m-emb-ram">Est. RAM (GB)</label><input id="m-emb-ram" type="number" step="0.1" class="input mono" value="${esc(emb.ram_gb)}" /></div>
        </div>
        ${embProbe ? `<div class="${embProbe.ok ? 'ok-msg' : 'err-msg'}" style="margin-bottom:10px;">${esc(embProbe.detail)}</div>` : ''}
        <div style="display:flex;gap:8px;flex-wrap:wrap;">
          <button class="btn" id="btn-probe-emb" onclick="probeModel('embedding')">🧪 Test Model</button>
          <button class="btn primary" onclick="saveModelRole('embedding')">Save Embedding Config</button>
        </div>
      </div>

      <!-- Chat / Reasoning LLM Card -->
      <div class="card">
        <div class="card-head">
          <h2>💬 Chat / Reasoning LLM</h2>
          <div style="display:flex;gap:6px;">
            <span class="pill ${llm.provider_type === 'local' ? 'ok' : 'info'}">${llm.provider_type === 'local' ? '💻 Local' : '☁️ Remote API'}</span>
            ${probeBadge(llmProbe)}
          </div>
        </div>
        <p class="hint" style="margin-top:0;">Used for RAG synthesis, agent reasoning, and local offload. Can be changed anytime without re-indexing your knowledge base.</p>
        <div class="field">
          <label for="m-llm-type">Provider Type</label>
          <select id="m-llm-type" class="select">
            <option value="local" ${llm.provider_type === 'local' ? 'selected' : ''}>Local Runtime (Ollama / LiteLLM)</option>
            <option value="remote" ${llm.provider_type === 'remote' ? 'selected' : ''}>Remote API</option>
          </select>
        </div>
        <div class="field">
          <label for="m-llm-endpoint">Endpoint URL</label>
          <input id="m-llm-endpoint" class="input mono" value="${esc(llm.endpoint)}" />
        </div>
        <div class="field">
          <label for="m-llm-id">LLM Model ID</label>
          <input id="m-llm-id" class="input mono" list="llm-catalog-list" value="${esc(llm.model_id)}" onchange="syncLlmMetaFromCatalog(this.value)" />
          <datalist id="llm-catalog-list">${Object.keys(ms.llm_catalog || {}).map((k) => `<option value="${esc(k)}">`).join('')}</datalist>
        </div>
        <div class="grid-2">
          <div class="field"><label for="m-llm-ctx">Max Context Window</label><input id="m-llm-ctx" type="number" class="input mono" value="${esc(llm.max_context_window)}" /></div>
          <div class="field"><label for="m-llm-ram">Est. RAM/VRAM (GB)</label><input id="m-llm-ram" type="number" step="0.1" class="input mono" value="${esc(llm.ram_gb)}" /></div>
        </div>
        ${llmProbe ? `<div class="${llmProbe.ok ? 'ok-msg' : 'err-msg'}" style="margin-bottom:10px;">${esc(llmProbe.detail)}</div>` : ''}
        <div style="display:flex;gap:8px;flex-wrap:wrap;">
          <button class="btn" id="btn-probe-llm" onclick="probeModel('llm')">🧪 Test Model</button>
          <button class="btn primary" onclick="saveModelRole('llm')">Save LLM Config</button>
        </div>
      </div>
    </div>
  `;
}

function syncEmbMetaFromCatalog(mid) {
  const cat = STATE.modelsStatus?.embedding_catalog?.[mid];
  if (!cat) return;
  document.getElementById('m-emb-dim').value = cat.dimensions;
  document.getElementById('m-emb-tok').value = cat.tokenizer_family;
  document.getElementById('m-emb-ram').value = cat.ram_gb;
  document.getElementById('m-emb-type').value = cat.provider_type;
}
function syncLlmMetaFromCatalog(mid) {
  const cat = STATE.modelsStatus?.llm_catalog?.[mid];
  if (!cat) return;
  document.getElementById('m-llm-ctx').value = cat.max_context_window;
  document.getElementById('m-llm-ram').value = cat.ram_gb;
  document.getElementById('m-llm-type').value = cat.provider_type;
}

function readModelForm(role) {
  if (role === 'embedding') {
    return {
      provider_type: document.getElementById('m-emb-type').value,
      endpoint: document.getElementById('m-emb-endpoint').value.trim(),
      model_id: document.getElementById('m-emb-id').value.trim(),
      dimensions: Number(document.getElementById('m-emb-dim').value || 768),
      tokenizer_family: document.getElementById('m-emb-tok').value.trim(),
      ram_gb: Number(document.getElementById('m-emb-ram').value || 0),
    };
  }
  return {
    provider_type: document.getElementById('m-llm-type').value,
    endpoint: document.getElementById('m-llm-endpoint').value.trim(),
    model_id: document.getElementById('m-llm-id').value.trim(),
    max_context_window: Number(document.getElementById('m-llm-ctx').value || 32768),
    ram_gb: Number(document.getElementById('m-llm-ram').value || 0),
  };
}

async function probeModel(role) {
  const btn = document.getElementById(role === 'embedding' ? 'btn-probe-emb' : 'btn-probe-llm');
  if (btn) { btn.disabled = true; btn.setAttribute('aria-busy', 'true'); btn.textContent = '⟳ Probing...'; }
  try {
    const cfg = readModelForm(role);
    const { data } = await api('POST', '/api/models/probe', { role, config: cfg });
    if (!STATE.modelsStatus.probes) STATE.modelsStatus.probes = {};
    STATE.modelsStatus.probes[role] = data;
    toast(data.ok ? 'ok' : 'err', `${role.toUpperCase()}: ${data.detail}`);
    await refreshContext();
    renderMain();
  } catch (err) {
    toast('err', err.message);
  } finally {
    if (btn) { btn.disabled = false; btn.removeAttribute('aria-busy'); btn.textContent = '🧪 Test Model'; }
  }
}

async function saveModelRole(role, extra = {}) {
  const cfg = readModelForm(role);
  try {
    const res = await api('POST', '/api/models/config', {
      models: { [role]: cfg },
      principal_id: STATE.principalId,
      ...extra,
    });
    if (res.status === 409 && res.data.error === 'embedding_incompatible') {
      const c = res.data.compatibility;
      openEmbeddingGuardrailModal(c, cfg);
      return;
    }
    toast('ok', (role === 'embedding' ? 'Embedding' : 'LLM') + ' model configuration saved.');
    if (res.data.job) {
      STATE.crawlJob = res.data.job;
      toast('info', 'Triggered Full Re-index with new embedding model.');
      ensureCrawlPolling(res.data.job.job_id);
    }
    await refreshDomainData();
  } catch (err) {
    toast('err', err.message);
  }
}

function openEmbeddingGuardrailModal(compat, nextCfg) {
  openConfirmModal({
    title: '⚠️ Embedding Compatibility Warning',
    body: `
      <p>Changing the Embedding Model makes existing vector embeddings incompatible:</p>
      <ul>
        <li><strong>Previous:</strong> <code class="mono">${esc(compat.previous.model_id)}</code> (${compat.previous.dimensions}d, ${esc(compat.previous.tokenizer_family)})</li>
        <li><strong>New:</strong> <code class="mono">${esc(compat.next.model_id)}</code> (${compat.next.dimensions}d, ${esc(compat.next.tokenizer_family)})</li>
      </ul>
      <p class="hint">To prevent corrupted semantic retrieval, Cortical recommends running a <strong>Full Re-index</strong> immediately.</p>
    `,
    confirmLabel: 'Save & Trigger Full Re-index',
    danger: true,
    onConfirm: () => saveModelRole('embedding', { confirm_reindex_ack: true, trigger_reindex: true }),
  });
}

// =========================================================================
// DOMAIN 3: MEMORY & INSPECTOR (Search, Citation Verifier, Episode Timeline)
// =========================================================================
function renderMemoryDomain() {
  const tab = STATE.memoryTab;
  return `
    <div class="page-head">
      <div>
        <h1>🔎 Memory &amp; Inspector</h1>
        <p>Test tenant-scoped FTS5 retrieval, verify citations with deep-links, and audit episodic memory for <span class="mono">${esc(STATE.principalId)}</span>.</p>
      </div>
    </div>
    <div class="tabs" role="tablist">
      <button class="tab-btn ${tab === 'search' ? 'active' : ''}" role="tab" onclick="STATE.memoryTab='search';renderMain()">🔍 Search Playground</button>
      <button class="tab-btn ${tab === 'citations' ? 'active' : ''}" role="tab" onclick="STATE.memoryTab='citations';renderMain()">✅ Citation Verifier</button>
      <button class="tab-btn ${tab === 'episodes' ? 'active' : ''}" role="tab" onclick="STATE.memoryTab='episodes';renderMain()">🕒 Episode Timeline (${STATE.episodes.length})</button>
    </div>
    ${tab === 'search' ? renderSearchPlayground() : (tab === 'citations' ? renderCitationVerifier() : renderEpisodeTimeline())}
  `;
}

function renderSearchPlayground() {
  return `
    <div class="card">
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;">
        <input id="rag-search-q" class="input" style="flex:1;min-width:240px;" placeholder="Query indexed knowledge (FTS5 BM25)..." value="${esc(STATE.searchQuery)}" onkeydown="if(event.key==='Enter')runSearch()" />
        <select id="rag-search-depth" class="select" style="width:140px;" aria-label="Projection depth">
          <option value="0" ${STATE.searchDepth === 0 ? 'selected' : ''}>Depth 0 (Titles)</option>
          <option value="1" ${STATE.searchDepth === 1 ? 'selected' : ''}>Depth 1 (Snippet)</option>
          <option value="2" ${STATE.searchDepth === 2 ? 'selected' : ''}>Depth 2 (Excerpt)</option>
        </select>
        <input id="rag-search-limit" type="number" min="1" max="50" class="input" style="width:90px;" value="${STATE.searchLimit}" aria-label="Result limit" />
        <button class="btn primary" onclick="runSearch()">Search</button>
      </div>
      ${STATE.searchResults.length === 0 ? `<div class="muted">Enter a query and press Search to test <code class="mono">wiki_search</code> for <strong>${esc(STATE.principalId)}</strong>.</div>` :
        STATE.searchResults.map((r) => `
          <div style="border:1px solid var(--border);border-radius:8px;padding:12px;margin-bottom:10px;background:#0a1120;">
            <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;">
              <div><strong>${esc(r.title)}</strong> <span class="mono muted">${esc(r.rel_path)}</span></div>
              <div style="display:flex;gap:6px;align-items:center;">
                <span class="pill ${r.principal_id === 'local_owner' ? 'owner' : 'tenant'}">${esc(r.principal_id)}</span>
                <span class="pill info">BM25: ${r.score}</span>
                <button class="btn sm" onclick="openFileDrawer('${esc(r.doc_id)}')">Inspect File →</button>
              </div>
            </div>
            ${r.snippet ? `<div class="hint" style="margin-top:6px;">${esc(r.snippet)}</div>` : ''}
            ${r.excerpt ? `<pre class="code-pre" style="margin-top:8px;max-height:140px;">${esc(r.excerpt)}</pre>` : ''}
          </div>
        `).join('')
      }
    </div>
  `;
}

async function runSearch() {
  STATE.searchQuery = document.getElementById('rag-search-q')?.value || '';
  STATE.searchDepth = Number(document.getElementById('rag-search-depth')?.value || 1);
  STATE.searchLimit = Number(document.getElementById('rag-search-limit')?.value || 10);
  try {
    const { data } = await api('POST', '/api/search', {
      query: STATE.searchQuery, principal_id: STATE.principalId, depth: STATE.searchDepth, limit: STATE.searchLimit,
    });
    STATE.searchResults = data.results || [];
    renderMain();
  } catch (err) { toast('err', err.message); }
}

function renderCitationVerifier() {
  const res = STATE.citationResult;
  const badgeMap = {
    verified: ['ok', '✓ Verified'],
    partial: ['warn', '◐ Partial'],
    not_found: ['err', '✕ Not Found'],
  };
  return `
    <div class="card">
      <div class="field">
        <label for="cit-claim">Claim or Quoted Text to Verify (<code class="mono">wiki_verify_citation</code>)</label>
        <textarea id="cit-claim" class="textarea" placeholder="Paste an agent claim or exact quote to verify against indexed sources...">${esc(STATE.citationClaim)}</textarea>
      </div>
      <button class="btn primary" onclick="runVerifyCitation()">✅ Verify Citation</button>
      ${res ? `
        <div style="margin-top:16px;padding-top:14px;border-top:1px solid var(--border);">
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px;">
            <span class="pill ${(badgeMap[res.status] || badgeMap.not_found)[0]}">${(badgeMap[res.status] || badgeMap.not_found)[1]}</span>
            <span>Confidence: <strong>${Math.round((res.confidence || 0) * 100)}%</strong> (threshold ${Math.round((res.threshold || 0.45) * 100)}%)</span>
          </div>
          ${(res.matches || []).length === 0 ? `<div class="muted">No supporting passages found for tenant <strong>${esc(STATE.principalId)}</strong>.</div>` :
            res.matches.map((m) => `
              <div style="border:1px solid var(--border);border-radius:8px;padding:12px;margin-bottom:8px;background:#0a1120;">
                <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;">
                  <div><strong class="mono">${esc(m.rel_path)}</strong> <span class="pill info">${Math.round(m.confidence * 100)}% (${esc(m.match_type)})</span></div>
                  <button class="btn sm primary" onclick="openFileDrawer('${esc(m.doc_id)}')">Deep-Link to File →</button>
                </div>
                <div class="hint" style="margin-top:6px;">…${esc(m.snippet)}…</div>
              </div>
            `).join('')
          }
        </div>
      ` : ''}
    </div>
  `;
}

async function runVerifyCitation() {
  STATE.citationClaim = document.getElementById('cit-claim')?.value || '';
  if (!STATE.citationClaim.trim()) { toast('warn', 'Enter a claim to verify.'); return; }
  try {
    const { data } = await api('POST', '/api/citations/verify', { claim: STATE.citationClaim, principal_id: STATE.principalId });
    STATE.citationResult = data;
    renderMain();
  } catch (err) { toast('err', err.message); }
}

function renderEpisodeTimeline() {
  const eps = STATE.episodes || [];
  return `
    <div class="card">
      <div class="card-head"><h2>＋ Record Episode (<code class="mono">wiki_record_episode</code>)</h2></div>
      <div class="grid-2">
        <div class="field"><label for="ep-title">Title</label><input id="ep-title" class="input" placeholder="e.g. Verified Merkle crawler isolation" /></div>
        <div class="field"><label for="ep-tags">Tags (comma-separated)</label><input id="ep-tags" class="input" placeholder="rbac, architecture, milestone" /></div>
      </div>
      <div class="field"><label for="ep-summary">Summary</label><textarea id="ep-summary" class="textarea" placeholder="Key decision, outcome, or memory trace..."></textarea></div>
      <button class="btn primary" onclick="recordEpisode()">Record Episode</button>
    </div>
    <div class="card">
      <div class="card-head"><h2>🕒 Chronological Timeline (${eps.length})</h2></div>
      ${eps.length === 0 ? `<div class="muted">No episodes recorded yet for <strong>${esc(STATE.principalId)}</strong>.</div>` :
        eps.map((e) => `
          <div style="border-left:3px solid var(--accent);padding:8px 14px;margin-bottom:12px;background:#0a1120;border-radius:0 8px 8px 0;">
            <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;">
              <strong>${esc(e.title)}</strong>
              <div style="display:flex;gap:6px;align-items:center;">
                <span class="pill ${e.principal_id === 'local_owner' ? 'owner' : 'tenant'}">${esc(e.principal_id)}</span>
                <span class="hint">${esc(fmtTime(e.created_at))}</span>
              </div>
            </div>
            <p style="margin:6px 0;">${esc(e.summary)}</p>
            <div style="display:flex;gap:6px;flex-wrap:wrap;">${(e.tags || []).map((t) => `<span class="pill info">#${esc(t)}</span>`).join('')}</div>
          </div>
        `).join('')
      }
    </div>
  `;
}

async function recordEpisode() {
  const title = document.getElementById('ep-title')?.value.trim();
  const summary = document.getElementById('ep-summary')?.value.trim();
  const tags = (document.getElementById('ep-tags')?.value || '').split(',').map((s) => s.trim()).filter(Boolean);
  if (!title || !summary) { toast('warn', 'Title and summary are required.'); return; }
  try {
    await api('POST', '/api/episodes', { title, summary, tags, principal_id: STATE.principalId });
    toast('ok', 'Episode recorded.');
    await refreshDomainData();
  } catch (err) { toast('err', err.message); }
}

// =========================================================================
// DOMAIN 4: SETTINGS (4 Semantic Tabs, Inline Validation, Dirty Bar, Reset)
// =========================================================================
function renderSettingsDomain() {
  const d = STATE.settingsDraft;
  if (!d) return `<div class="card"><div class="skeleton" style="width:50%;"></div></div>`;
  const tab = STATE.settingsTab;
  const err = (k) => STATE.settingsErrors[k] ? `<div class="err-msg">⚠ ${esc(STATE.settingsErrors[k])}</div>` : '';

  const tabsHtml = `
    <div class="tabs" role="tablist">
      <button class="tab-btn ${tab === 'general_rbac' ? 'active' : ''}" role="tab" onclick="STATE.settingsTab='general_rbac';renderMain()">🛡️ General &amp; RBAC</button>
      <button class="tab-btn ${tab === 'search_rag' ? 'active' : ''}" role="tab" onclick="STATE.settingsTab='search_rag';renderMain()">🔍 Search &amp; RAG</button>
      <button class="tab-btn ${tab === 'storage_crawler' ? 'active' : ''}" role="tab" onclick="STATE.settingsTab='storage_crawler';renderMain()">💾 Storage &amp; Crawler</button>
      <button class="tab-btn ${tab === 'advanced' ? 'active' : ''}" role="tab" onclick="STATE.settingsTab='advanced';renderMain()">🔧 Advanced</button>
    </div>
  `;

  let panel = '';
  if (tab === 'general_rbac') {
    const g = d.general_rbac;
    panel = `
      <div class="card">
        <div class="card-head">
          <h2>🛡️ General &amp; Multi-Tenant RBAC</h2>
          <button class="btn sm danger" onclick="confirmResetSection('general_rbac', 'General & RBAC')">↺ Reset to Defaults</button>
        </div>
        <div class="field">
          <label for="s-def-pid">Default principal_id</label>
          <input id="s-def-pid" class="input mono ${STATE.settingsErrors['general_rbac.default_principal_id'] ? 'invalid' : ''}" value="${esc(g.default_principal_id)}" oninput="updateDraft('general_rbac.default_principal_id', this.value)" />
          <div class="hint">Tenant context selected on startup. Use <code>local_owner</code> for full cross-tenant visibility.</div>
          ${err('general_rbac.default_principal_id')}
        </div>
        <div class="field">
          <label for="s-iso">Tenant Isolation Policy</label>
          <select id="s-iso" class="select" onchange="updateDraft('general_rbac.isolation_policy', this.value)">
            <option value="strict" ${g.isolation_policy === 'strict' ? 'selected' : ''}>Strict (Recommended — zero cross-tenant reads)</option>
            <option value="shared_read" ${g.isolation_policy === 'shared_read' ? 'selected' : ''}>Shared Read (Scoped principals may read shared docs)</option>
          </select>
          <div class="hint">Controls SQLite query scoping for FTS5 search, file explorer, and citation verification.</div>
        </div>
        <div class="field">
          <label><input type="checkbox" ${g.allow_tenant_creation ? 'checked' : ''} onchange="updateDraft('general_rbac.allow_tenant_creation', this.checked)" /> Allow creating new scoped tenants from the UI</label>
        </div>
        <div class="field">
          <label><input type="checkbox" ${g.require_citation_rbac ? 'checked' : ''} onchange="updateDraft('general_rbac.require_citation_rbac', this.checked)" /> Enforce strict RBAC on Citation Verifier queries</label>
        </div>
      </div>`;
  } else if (tab === 'search_rag') {
    const s = d.search_rag;
    panel = `
      <div class="card">
        <div class="card-head">
          <h2>🔍 Search &amp; RAG Parameters</h2>
          <button class="btn sm danger" onclick="confirmResetSection('search_rag', 'Search & RAG')">↺ Reset to Defaults</button>
        </div>
        <div class="grid-2">
          <div class="field">
            <label for="s-tok">FTS5 Tokenizer</label>
            <select id="s-tok" class="select" onchange="updateDraft('search_rag.fts5_tokenizer', this.value)">
              <option value="unicode61" ${s.fts5_tokenizer === 'unicode61' ? 'selected' : ''}>unicode61 (Balanced multilingual recall)</option>
              <option value="porter" ${s.fts5_tokenizer === 'porter' ? 'selected' : ''}>porter (English stemming — higher recall)</option>
              <option value="ascii" ${s.fts5_tokenizer === 'ascii' ? 'selected' : ''}>ascii (Fastest exact ASCII matching)</option>
            </select>
            <div class="hint">Trade-off: <code>porter</code> increases recall on inflected English words; <code>unicode61</code> is safest for code and multilingual text.</div>
          </div>
          <div class="field">
            <label for="s-depth">Default Depth Projection (0–2)</label>
            <input id="s-depth" type="number" min="0" max="2" class="input ${STATE.settingsErrors['search_rag.default_depth'] ? 'invalid' : ''}" value="${s.default_depth}" oninput="updateDraft('search_rag.default_depth', Number(this.value))" />
            <div class="hint">0 = titles only (lowest tokens), 1 = BM25 snippets (balanced), 2 = full excerpts (highest context cost).</div>
            ${err('search_rag.default_depth')}
          </div>
          <div class="field">
            <label for="s-limit">Default Result Limit (1–100)</label>
            <input id="s-limit" type="number" min="1" max="100" class="input ${STATE.settingsErrors['search_rag.default_limit'] ? 'invalid' : ''}" value="${s.default_limit}" oninput="updateDraft('search_rag.default_limit', Number(this.value))" />
            <div class="hint">Maximum documents returned per <code>wiki_search</code> call. Higher limits increase recall and prompt tokens.</div>
            ${err('search_rag.default_limit')}
          </div>
          <div class="field">
            <label for="s-cit">Citation Verification Threshold (0.10–1.00)</label>
            <input id="s-cit" type="number" step="0.05" min="0.1" max="1.0" class="input ${STATE.settingsErrors['search_rag.citation_threshold'] ? 'invalid' : ''}" value="${s.citation_threshold}" oninput="updateDraft('search_rag.citation_threshold', Number(this.value))" />
            <div class="hint">Minimum lexical overlap ratio to classify a citation as <strong>Verified</strong> vs <strong>Partial</strong>.</div>
            ${err('search_rag.citation_threshold')}
          </div>
        </div>
      </div>`;
  } else if (tab === 'storage_crawler') {
    const c = d.storage_crawler;
    panel = `
      <div class="card">
        <div class="card-head">
          <h2>💾 Storage &amp; Merkle Crawler</h2>
          <button class="btn sm danger" onclick="confirmResetSection('storage_crawler', 'Storage & Crawler')">↺ Reset to Defaults</button>
        </div>
        <div class="field">
          <label for="s-db">SQLite Index Path (<code>wiki.db</code>)</label>
          <input id="s-db" class="input mono ${STATE.settingsErrors['storage_crawler.db_path'] ? 'invalid' : ''}" value="${esc(c.db_path)}" oninput="updateDraft('storage_crawler.db_path', this.value)" />
          <div class="hint">SQLite WAL + FTS5 database storing roots, Merkle hashes, chunks, and episodes.</div>
          ${err('storage_crawler.db_path')}
        </div>
        <div class="grid-2">
          <div class="field">
            <label for="s-cs">Chunk Size (256–8192 chars)</label>
            <input id="s-cs" type="number" class="input ${STATE.settingsErrors['storage_crawler.chunk_size'] ? 'invalid' : ''}" value="${c.chunk_size}" oninput="updateDraft('storage_crawler.chunk_size', Number(this.value))" />
            <div class="hint">Smaller chunks improve precision; larger chunks preserve surrounding paragraph context.</div>
            ${err('storage_crawler.chunk_size')}
          </div>
          <div class="field">
            <label for="s-co">Chunk Overlap (chars)</label>
            <input id="s-co" type="number" class="input ${STATE.settingsErrors['storage_crawler.chunk_overlap'] ? 'invalid' : ''}" value="${c.chunk_overlap}" oninput="updateDraft('storage_crawler.chunk_overlap', Number(this.value))" />
            <div class="hint">Overlap prevents sentences from being split across chunk boundaries.</div>
            ${err('storage_crawler.chunk_overlap')}
          </div>
        </div>
        <div class="field">
          <label for="s-ign">Ignore Patterns (<code>.gitignore</code>-style, one per line)</label>
          <textarea id="s-ign" class="textarea" oninput="updateDraft('storage_crawler.ignore_patterns', this.value.split('\\n').map(x=>x.trim()).filter(Boolean))">${esc((c.ignore_patterns || []).join('\n'))}</textarea>
          <div class="hint">Files matching these patterns are skipped during Merkle crawling and marked as <code>Ignored</code>.</div>
        </div>
        <div class="field">
          <label><input type="checkbox" ${c.auto_crawl_on_upload ? 'checked' : ''} onchange="updateDraft('storage_crawler.auto_crawl_on_upload', this.checked)" /> Automatically trigger Delta Sync after drag-and-drop uploads</label>
        </div>
      </div>`;
  } else {
    const a = d.advanced;
    panel = `
      <div class="card">
        <div class="card-head">
          <h2>🔧 Advanced Runtime Tuning</h2>
          <button class="btn sm danger" onclick="confirmResetSection('advanced', 'Advanced')">↺ Reset to Defaults</button>
        </div>
        <div class="grid-2">
          <div class="field">
            <label for="s-log">Log Level</label>
            <select id="s-log" class="select" onchange="updateDraft('advanced.log_level', this.value)">
              ${['DEBUG','INFO','WARN','ERROR'].map((l) => `<option value="${l}" ${a.log_level === l ? 'selected' : ''}>${l}</option>`).join('')}
            </select>
          </div>
          <div class="field">
            <label for="s-to">Model Probe Timeout (2–120s)</label>
            <input id="s-to" type="number" min="2" max="120" class="input ${STATE.settingsErrors['advanced.request_timeout_sec'] ? 'invalid' : ''}" value="${a.request_timeout_sec}" oninput="updateDraft('advanced.request_timeout_sec', Number(this.value))" />
            ${err('advanced.request_timeout_sec')}
          </div>
        </div>
        <details style="margin-top:12px;">
          <summary style="cursor:pointer;font-weight:600;color:var(--accent);">Inspect Validated Raw JSON Configuration</summary>
          <pre class="code-pre" style="margin-top:8px;">${esc(JSON.stringify(d, null, 2))}</pre>
        </details>
      </div>`;
  }

  return `
    <div class="page-head">
      <div>
        <h1>⚙️ Settings</h1>
        <p>Categorized system, search, storage, and RBAC configuration with inline validation and safe persistence.</p>
      </div>
    </div>
    ${tabsHtml}
    ${panel}
  `;
}

function updateDraft(path, value) {
  const parts = path.split('.');
  let cur = STATE.settingsDraft;
  for (let i = 0; i < parts.length - 1; i++) cur = cur[parts[i]];
  cur[parts[parts.length - 1]] = value;
  validateDraftInline();
  renderUnsavedBar();
}

function validateDraftInline() {
  const d = STATE.settingsDraft;
  const e = {};
  if (!d) return e;
  if (!String(d.general_rbac.default_principal_id || '').trim()) e['general_rbac.default_principal_id'] = 'Default principal_id is required.';
  if (d.search_rag.default_depth < 0 || d.search_rag.default_depth > 2) e['search_rag.default_depth'] = 'Depth must be between 0 and 2.';
  if (d.search_rag.default_limit < 1 || d.search_rag.default_limit > 100) e['search_rag.default_limit'] = 'Limit must be between 1 and 100.';
  if (d.search_rag.citation_threshold < 0.1 || d.search_rag.citation_threshold > 1.0) e['search_rag.citation_threshold'] = 'Threshold must be between 0.10 and 1.00.';
  if (!String(d.storage_crawler.db_path || '').trim()) e['storage_crawler.db_path'] = 'Database path is required.';
  if (d.storage_crawler.chunk_size < 256 || d.storage_crawler.chunk_size > 8192) e['storage_crawler.chunk_size'] = 'Chunk size must be 256–8192.';
  if (d.storage_crawler.chunk_overlap < 0 || d.storage_crawler.chunk_overlap >= d.storage_crawler.chunk_size) e['storage_crawler.chunk_overlap'] = 'Overlap must be >= 0 and < chunk size.';
  if (d.advanced.request_timeout_sec < 2 || d.advanced.request_timeout_sec > 120) e['advanced.request_timeout_sec'] = 'Timeout must be 2–120 seconds.';
  STATE.settingsErrors = e;
  return e;
}

function countDirtyFields(a, b) {
  if (!a || !b) return 0;
  let n = 0;
  for (const k of Object.keys(a)) {
    if (JSON.stringify(a[k]) !== JSON.stringify(b[k])) n++;
  }
  return n;
}

function renderUnsavedBar() {
  const bar = document.getElementById('unsaved-bar');
  const dirty = STATE.domain === 'settings' ? countDirtyFields(STATE.settingsSaved, STATE.settingsDraft) : 0;
  if (dirty === 0) { bar.style.display = 'none'; return; }
  const errCount = Object.keys(STATE.settingsErrors || {}).length;
  bar.style.display = 'flex';
  document.getElementById('unsaved-count').textContent = errCount > 0
    ? `${dirty} section(s) modified — fix ${errCount} validation error(s) before saving`
    : `${dirty} section(s) modified`;
  document.getElementById('btn-save-settings').disabled = errCount > 0;
}

function discardSettings() {
  STATE.settingsDraft = deepClone(STATE.settingsSaved);
  validateDraftInline();
  renderMain();
  renderUnsavedBar();
  toast('info', 'Unsaved changes discarded.');
}

async function saveSettings() {
  try {
    const { data } = await api('POST', '/api/settings', STATE.settingsDraft);
    STATE.settingsSaved = data.settings;
    STATE.settingsDraft = deepClone(data.settings);
    validateDraftInline();
    renderUnsavedBar();
    renderMain();
    toast('ok', 'Settings validated, saved, and applied.');
  } catch (err) {
    toast('err', 'Save failed: ' + err.message);
  }
}

function confirmResetSection(section, label) {
  openConfirmModal({
    title: `Reset "${label}" to Defaults`,
    body: `Restore all settings in <strong>${esc(label)}</strong> back to factory defaults? Any custom values in this section will be overwritten.`,
    confirmLabel: 'Reset Section',
    danger: true,
    onConfirm: async () => {
      const { data } = await api('POST', '/api/settings/reset', { section });
      STATE.settingsSaved = data.settings;
      STATE.settingsDraft = deepClone(data.settings);
      validateDraftInline();
      renderMain();
      renderUnsavedBar();
      toast('ok', `Reset ${label} to defaults.`);
    },
  });
}

// =========================================================================
// MODALS, CREATE TENANT & COMMAND PALETTE (Cmd/Ctrl + K)
// =========================================================================
function openConfirmModal({ title, body, confirmLabel, danger, onConfirm }) {
  const root = document.getElementById('modal-root');
  root.innerHTML = `
    <div class="backdrop" onclick="if(event.target===this)closeModal()">
      <div class="modal" role="dialog" aria-modal="true" aria-label="${esc(title)}">
        <h2 style="margin-top:0;">${esc(title)}</h2>
        <div style="margin:12px 0 18px;">${body}</div>
        <div style="display:flex;justify-content:flex-end;gap:8px;">
          <button class="btn" id="modal-cancel" onclick="closeModal()">Cancel</button>
          <button class="btn ${danger ? 'danger' : 'primary'}" id="modal-ok">${esc(confirmLabel)}</button>
        </div>
      </div>
    </div>
  `;
  document.getElementById('modal-ok').onclick = async () => { closeModal(); await onConfirm(); };
  document.getElementById('modal-cancel').focus();
}
function closeModal() { document.getElementById('modal-root').innerHTML = ''; }

function openCreateTenantModal() {
  const root = document.getElementById('modal-root');
  root.innerHTML = `
    <div class="backdrop" onclick="if(event.target===this)closeModal()">
      <div class="modal" role="dialog" aria-modal="true" aria-label="Create Scoped Tenant">
        <h2 style="margin-top:0;">🔒 Create Scoped Tenant (principal_id)</h2>
        <div class="field">
          <label for="nt-id">principal_id</label>
          <input id="nt-id" class="input mono" placeholder="e.g. team_eng or tenant_alpha" />
        </div>
        <div class="field">
          <label for="nt-name">Display Name</label>
          <input id="nt-name" class="input" placeholder="e.g. Engineering Team" />
        </div>
        <div style="display:flex;justify-content:flex-end;gap:8px;">
          <button class="btn" onclick="closeModal()">Cancel</button>
          <button class="btn primary" onclick="submitNewTenant()">Create &amp; Switch</button>
        </div>
      </div>
    </div>
  `;
  document.getElementById('nt-id').focus();
}

async function submitNewTenant() {
  const pid = document.getElementById('nt-id')?.value.trim();
  const name = document.getElementById('nt-name')?.value.trim() || pid;
  if (!pid) { toast('warn', 'Enter a principal_id.'); return; }
  try {
    await api('POST', '/api/principals', { principal_id: pid, display_name: name });
    closeModal();
    switchPrincipal(pid);
  } catch (err) { toast('err', err.message); }
}

function getCommandItems() {
  const items = [
    { label: 'Navigate: Knowledge & Files', group: 'View', run: () => setDomain('files') },
    { label: 'Navigate: Models & Runtime', group: 'View', run: () => setDomain('models') },
    { label: 'Navigate: Memory & Inspector (Search)', group: 'View', run: () => setDomain('memory', { memoryTab: 'search' }) },
    { label: 'Navigate: Citation Verifier', group: 'View', run: () => setDomain('memory', { memoryTab: 'citations' }) },
    { label: 'Navigate: Episode Timeline', group: 'View', run: () => setDomain('memory', { memoryTab: 'episodes' }) },
    { label: 'Settings: General & RBAC', group: 'Settings', run: () => setDomain('settings', { settingsTab: 'general_rbac' }) },
    { label: 'Settings: Search & RAG', group: 'Settings', run: () => setDomain('settings', { settingsTab: 'search_rag' }) },
    { label: 'Settings: Storage & Crawler', group: 'Settings', run: () => setDomain('settings', { settingsTab: 'storage_crawler' }) },
    { label: 'Settings: Advanced', group: 'Settings', run: () => setDomain('settings', { settingsTab: 'advanced' }) },
    { label: 'Action: Trigger Merkle Delta Sync', group: 'Action', run: () => triggerCrawl(null, false) },
    { label: 'Action: Create New Scoped Tenant', group: 'Tenant', run: () => openCreateTenantModal() },
  ];
  (STATE.context?.principals || []).forEach((p) => {
    items.push({ label: `Switch Tenant → ${p.principal_id}`, group: 'Tenant', run: () => switchPrincipal(p.principal_id) });
  });
  const q = STATE.cmdQuery.trim().toLowerCase();
  return q ? items.filter((i) => i.label.toLowerCase().includes(q) || i.group.toLowerCase().includes(q)) : items;
}

function openCmdPalette() {
  STATE.cmdOpen = true; STATE.cmdQuery = ''; STATE.cmdIdx = 0;
  renderCmdPalette();
  setTimeout(() => document.getElementById('cmd-input')?.focus(), 10);
}
function closeCmdPalette() { STATE.cmdOpen = false; document.getElementById('cmd-root').innerHTML = ''; }

function renderCmdPalette() {
  const root = document.getElementById('cmd-root');
  if (!STATE.cmdOpen) { root.innerHTML = ''; return; }
  const items = getCommandItems();
  STATE.cmdIdx = Math.min(STATE.cmdIdx, Math.max(0, items.length - 1));
  root.innerHTML = `
    <div class="backdrop" onclick="if(event.target===this)closeCmdPalette()">
      <div class="modal" role="dialog" aria-modal="true" aria-label="Command Palette">
        <input id="cmd-input" class="input" placeholder="Type a command, setting, or principal_id..." value="${esc(STATE.cmdQuery)}"
          oninput="STATE.cmdQuery=this.value;STATE.cmdIdx=0;renderCmdListOnly()"
          onkeydown="handleCmdKey(event)" />
        <ul id="cmd-list" class="cmd-list">${renderCmdListHtml(items)}</ul>
      </div>
    </div>
  `;
}
function renderCmdListHtml(items) {
  if (!items.length) return `<li class="muted" style="padding:10px;">No matching commands.</li>`;
  return items.map((it, idx) => `
    <li class="cmd-item ${idx === STATE.cmdIdx ? 'selected' : ''}" onclick="execCmd(${idx})">
      <span>${esc(it.label)}</span>
      <span class="kbd">${esc(it.group)}</span>
    </li>
  `).join('');
}
function renderCmdListOnly() {
  const ul = document.getElementById('cmd-list');
  if (ul) ul.innerHTML = renderCmdListHtml(getCommandItems());
}
function execCmd(idx) {
  const items = getCommandItems();
  const it = items[idx];
  closeCmdPalette();
  if (it) it.run();
}
function handleCmdKey(e) {
  const items = getCommandItems();
  if (e.key === 'ArrowDown') { e.preventDefault(); STATE.cmdIdx = (STATE.cmdIdx + 1) % Math.max(1, items.length); renderCmdListOnly(); }
  else if (e.key === 'ArrowUp') { e.preventDefault(); STATE.cmdIdx = (STATE.cmdIdx - 1 + Math.max(1, items.length)) % Math.max(1, items.length); renderCmdListOnly(); }
  else if (e.key === 'Enter') { e.preventDefault(); execCmd(STATE.cmdIdx); }
  else if (e.key === 'Escape') { e.preventDefault(); closeCmdPalette(); }
}

document.addEventListener('keydown', (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault();
    STATE.cmdOpen ? closeCmdPalette() : openCmdPalette();
  } else if (e.key === 'Escape') {
    if (STATE.cmdOpen) closeCmdPalette();
    else if (STATE.drawerDoc) closeFileDrawer();
    else closeModal();
  }
});

function bindDynamicHandlers() {
  const dz = document.getElementById('file-dropzone');
  const inp = document.getElementById('file-upload-input');
  if (dz && inp) {
    dz.onclick = () => inp.click();
    dz.onkeydown = (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); inp.click(); } };
    dz.ondragover = (e) => { e.preventDefault(); dz.classList.add('dragover'); };
    dz.ondragleave = () => dz.classList.remove('dragover');
    dz.ondrop = (e) => { e.preventDefault(); dz.classList.remove('dragover'); handleFileUploadList(e.dataTransfer.files); };
    inp.onchange = () => { if (inp.files.length) handleFileUploadList(inp.files); inp.value = ''; };
  }
}

refreshDomainData();
</script>
</body>
</html>
"""
