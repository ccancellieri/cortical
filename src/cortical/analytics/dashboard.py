"""Zero-Server Static HTML App (`settings.html`) & Documentation (`help.html`).

Zero daemons, zero open ports: runs 100% client-side in browser with optional direct
File System Access sync to `.cortical_data/vault/*.json` & `.cortical_data/vault_inbox/`.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Optional

from ..config import DEFAULT_CONFIG, load_cortical_config
from ..harnesses.adapters import ALL_HARNESSES, get_harness_presend_matrix, resolve_user_paths
from ..hardware.models import BUILTIN_MODEL_CATALOG


def _tilde(p: Path) -> str:
    raw, home = str(p), str(Path.home())
    return "~" + raw[len(home):] if raw.startswith(home) else raw


def _installed_model_caps() -> list[dict[str, Any]]:
    try:
        from ..hardware.probe import _probe_ollama_tags
        _on, tags = _probe_ollama_tags()
        return [
            {
                "name": str(t.get("name") if isinstance(t, dict) else t),
                "capabilities": list(t.get("capabilities") or ["completion"]) if isinstance(t, dict) else ["completion"],
            }
            for t in tags
        ]
    except Exception:  # noqa: BLE001
        return []


_CLI_POSIX = "PYTHONPATH=src .venv/bin/python -m cortical.cli"
_CLI_WIN = "set PYTHONPATH=src && .venv\\Scripts\\python -m cortical.cli"


def build_dashboard_env(repo_root: Optional[Path] = None, os_name: Optional[str] = None, public: bool = False) -> dict[str, Any]:
    """Describes local setup (folder to link, harness detection/link status) for the guided Setup tab."""
    base_cmd = "PYTHONPATH=src .venv/bin/python -m cortical.cli sync"
    if public:
        return {
            "public": True,
            "repo_display": "<cartella-cortical>",
            "data_display": "Documents/Cortical",
            "harness_status": {},
            "sync_cmd_base": f"cd /path/to/cortical && {base_cmd}",
            "setup_cmd": {"posix": f"cd /path/to/cortical && {_CLI_POSIX} setup", "win": f"cd C:\\path\\to\\cortical && {_CLI_WIN} setup"},
            "watch_cmd": {"posix": f"{_CLI_POSIX} watch", "win": f"{_CLI_WIN} watch"},
            "installed_models": [],
            "installed_model_caps": [],
            "vision_suggestions": ["qwen2.5vl:3b", "qwen2.5vl:7b"],
            "initial_brain": None,
            "initial_roi": None,
        }
    root = Path(repo_root or Path.cwd()).resolve()
    paths = resolve_user_paths(os_name=os_name)
    primary = {"antigravity": "mcp", "pi": "mcp", "opencode": "opencode", "openclaw": "config",
               "codex": "config", "claude-code": "mcp", "dsh": "settings", "unsloth-studio": "manifest"}
    home = Path.home()
    status: dict[str, Any] = {}
    for h in ALL_HARNESSES:
        cfg_p = paths[h][primary[h]]
        exists = cfg_p.is_file()
        linked = False
        if exists:
            try:
                linked = "cortical" in cfg_p.read_text(encoding="utf-8", errors="ignore").lower()
            except OSError:
                linked = False
        detected = exists or (cfg_p.parent != home and cfg_p.parent.is_dir())
        status[h] = {"detected": detected, "linked": linked, "config": _tilde(cfg_p)}
    rd = _tilde(root)
    cd = rd if " " not in rd else f'"{rd}"'
    caps = _installed_model_caps()

    init_brain: Optional[dict[str, Any]] = None
    init_roi: Optional[dict[str, Any]] = None
    try:
        from ..config import default_data_dir
        from ..privacy.vault import PrivacyVault
        from .roi import evaluate_routing_state

        dd = default_data_dir()
        if (dd / "vault.db").is_file():
            init_brain = PrivacyVault(dd / "vault.db").brain.get_snapshot(include_local_only=True)
        init_roi = evaluate_routing_state(db_path=dd / "telemetry.db")
    except Exception:  # noqa: BLE001
        pass

    return {
        "public": False,
        "repo_display": rd,
        "data_display": "Documents/Cortical",
        "harness_status": status,
        "sync_cmd_base": f"cd {cd} && {base_cmd}",
        "setup_cmd": {"posix": f"cd {cd} && {_CLI_POSIX} setup", "win": f"cd {cd} && {_CLI_WIN} setup"},
        "watch_cmd": {"posix": f"cd {cd} && {_CLI_POSIX} watch", "win": f"cd {cd} && {_CLI_WIN} watch"},
        "installed_models": [c["name"] for c in caps],
        "installed_model_caps": caps,
        "vision_suggestions": ["qwen2.5vl:3b", "qwen2.5vl:7b"],
        "initial_brain": init_brain,
        "initial_roi": init_roi,
    }


def _nav_links(is_help: bool, public_docs: bool) -> str:
    home = '<a href="./index.html" style="color:var(--accent);">🏠 Home</a>'
    gh = '<a href="https://github.com/ccancellieri/cortical" target="_blank" rel="noopener" style="color:var(--accent);">GitHub</a>'
    if is_help:
        return f'{home} · {gh}' if public_docs else f'<a href="./settings.html" style="color:var(--accent);">🛡️ Privacy Vault &amp; Settings</a> · {home} · {gh}'
    base = f'<a href="./help.html" style="color:var(--accent);">❓ Help</a> · {home} · {gh}'
    return base if public_docs else f'{home} · {base}'


_SETTINGS_TEMPLATE = r"""<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Cortical — Zero-Server Privacy Vault &amp; Configurator</title>
  <style>
    :root {
      --bg:#080d1a; --surface:#0f172a; --card:#141e33; --card2:#0b1222; --border:#24324a;
      --text:#e2e8f0; --muted:#94a3b8; --accent:#38bdf8; --emerald:#34d399; --amber:#fbbf24; --danger:#f87171;
    }
    * { box-sizing:border-box; }
    body { margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; background:var(--bg); color:var(--text); line-height:1.5; }
    .wrap { max-width:1180px; margin:0 auto; padding:20px 18px 64px; }
    .top { display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px; border-bottom:1px solid var(--border); padding-bottom:14px; margin-bottom:14px; }
    .layout { display:grid; grid-template-columns:230px 1fr; gap:16px; }
    @media (max-width:860px) { .layout { grid-template-columns:1fr; } }
    .sidebar { display:flex; flex-direction:column; gap:8px; }
    .tab { text-align:left; padding:10px 12px; border-radius:9px; border:1px solid var(--border); background:var(--surface); color:var(--text); cursor:pointer; font-weight:600; font-size:0.88rem; }
    .tab.active { border-color:var(--accent); background:rgba(56,189,248,0.13); color:var(--accent); }
    .card { background:var(--surface); border:1px solid var(--border); border-radius:12px; padding:16px; margin-bottom:14px; }
    .sync-bar { display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; background:var(--card); border:1px solid var(--border); border-radius:10px; padding:11px 14px; margin-bottom:14px; font-size:0.84rem; }
    h1 { margin:0; font-size:1.3rem; }
    h2 { margin:0 0 10px; font-size:1.05rem; color:var(--accent); }
    label { display:flex; flex-direction:column; gap:5px; font-size:0.82rem; color:var(--muted); }
    input,select,textarea { border-radius:8px; border:1px solid var(--border); background:#060a14; color:var(--text); padding:8px 10px; font-family:inherit; font-size:0.86rem; width:100%; }
    textarea { min-height:76px; resize:vertical; }
    .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(215px,1fr)); gap:12px; }
    .btn { display:inline-flex; align-items:center; gap:6px; border:1px solid var(--border); background:var(--card); color:var(--text); padding:7px 12px; border-radius:8px; cursor:pointer; font-weight:600; font-size:0.82rem; text-decoration:none; }
    .btn:hover:not(:disabled) { border-color:var(--accent); }
    .btn:disabled { opacity:0.45; cursor:not-allowed; }
    .btn-primary { background:var(--accent); color:#082f49; border-color:var(--accent); }
    .btn-em { background:rgba(52,211,153,0.16); color:var(--emerald); border-color:rgba(52,211,153,0.45); }
    .btn-danger { border-color:rgba(248,113,113,0.45); color:var(--danger); }
    .pill { display:inline-block; padding:2px 9px; border-radius:999px; font-size:0.74rem; font-weight:700; }
    .pill-ok { background:rgba(52,211,153,0.14); color:var(--emerald); border:1px solid rgba(52,211,153,0.4); }
    .pill-warn { background:rgba(251,191,36,0.14); color:var(--amber); border:1px solid rgba(251,191,36,0.4); }
    .pill-pub { background:rgba(56,189,248,0.14); color:var(--accent); border:1px solid rgba(56,189,248,0.4); }
    .prof-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:10px; margin:12px 0; }
    .prof-opt { border:1px solid var(--border); background:var(--card2); border-radius:10px; padding:10px; cursor:pointer; display:flex; flex-direction:row; align-items:flex-start; gap:8px; color:var(--text); }
    .prof-opt.sel { border-color:var(--accent); background:rgba(56,189,248,0.09); }
    .prof-opt input { width:auto; margin-top:3px; }
    .dropzone { border:2px dashed var(--border); border-radius:10px; padding:16px; text-align:center; background:var(--card2); cursor:pointer; }
    .dropzone.drag { border-color:var(--accent); background:rgba(56,189,248,0.08); }
    .alert { padding:10px 14px; border-radius:8px; margin-bottom:12px; font-size:0.85rem; display:none; }
    .alert.ok { display:block; background:rgba(52,211,153,0.14); border:1px solid rgba(52,211,153,0.4); color:var(--emerald); }
    .alert.err { display:block; background:rgba(248,113,113,0.14); border:1px solid rgba(248,113,113,0.4); color:var(--danger); }
    .alert.info { display:block; background:rgba(56,189,248,0.12); border:1px solid rgba(56,189,248,0.35); color:var(--accent); }
    .stats { display:flex; gap:10px; flex-wrap:wrap; margin-bottom:10px; font-size:0.83rem; }
    .stat-box { background:var(--card2); border:1px solid var(--border); padding:6px 12px; border-radius:8px; }
    table { width:100%; border-collapse:collapse; font-size:0.83rem; }
    th,td { text-align:left; padding:8px; border-bottom:1px solid var(--border); vertical-align:middle; }
    th { color:var(--muted); font-weight:600; }
    code { color:var(--emerald); background:#060a14; padding:2px 6px; border-radius:5px; }
    pre { background:#060a14; border:1px solid var(--border); border-radius:8px; padding:12px; overflow:auto; max-height:360px; font-size:0.82rem; color:#cbd5e1; white-space:pre-wrap; word-break:break-word; }
    .rv { white-space:pre-wrap; word-break:break-word; background:#060a14; border:1px solid var(--border); border-radius:8px; padding:12px; max-height:340px; overflow:auto; font-size:0.84rem; user-select:text; }
    mark.hit { background:rgba(248,113,113,0.35); color:var(--text); border-radius:3px; cursor:pointer; }
    mark.kept { background:transparent; color:var(--text); border-bottom:2px dotted var(--emerald); cursor:pointer; }
    .chk { flex-direction:row; align-items:center; gap:8px; cursor:pointer; color:var(--text); }
    .chk input { width:auto; }
  </style>
</head>
<body>
  <div class="wrap" id="app"></div>
  <script>
    let CFG = __CFG_JSON__;
    const HW = __HW_JSON__;
    const CATALOG = __CATALOG_JSON__;
    const PRESEND = __PRESEND_JSON__;
    const ENV = __ENV_JSON__;

    const I18N = {
      en: {
        title: 'Cortical Zero-Server Workspace',
        sub: '100% client-side (zero ports, zero daemons) · __NAV__',
        save: 'Save Config', download: 'Export Config JSON', import: 'Import Config',
        tabs: {
          setup: '🚀 Guided Setup',
          vault: '🛡️ Privacy Vault',
          brain: '🧠 Local Brain (3+1)',
          models: '⚙️ Hardware & Models',
          harnesses: '🔌 8 Harnesses & Composer',
          compression: '📊 ROI, Routing & TOON',
        },
        syncUnset: 'Zero-Server Mode: Vault stored in browser IndexedDB. Click to link local .cortical_data folder for auto-sync with MCP & CLI.',
        syncLinked: 'Linked to folder: ',
        connectBtn: '📂 Link .cortical_data Folder',
        reconnectBtn: '🔓 Re-authorize Linked Folder',
        uploadTitle: 'Upload & Anonymize Files Locally (PDF, DOCX, XLSX, PPTX, TXT, JSON, MD)',
        dropHint: 'Drag a file here or click to pick from disk (processed 100% locally in your browser)',
        aliasLbl: 'Vault Alias (e.g. alsa)',
        policyLbl: 'Dynamic Policy',
        termsLbl: 'Custom sensitive terms (comma-separated)',
        uploadBtn: '🛡️ Process & Save in Vault',
        profMaxSec: '🔒 Max Security · Local Only',
        profMaxSecDesc: 'Visible here in Vault; local LLMs ONLY, BLOCKED from cloud chat egress.',
        profMed: '🛡️ Anonymized for Chat',
        profMedDesc: 'Strips metadata, emails, phones, IBANs, tax IDs & custom terms; ready as @private:<alias>.',
        profLow: '📋 Redacted Summary',
        profLowDesc: 'Replaces sensitive entities with [REDACTED] markers.',
        profPub: '🌐 Public / fail_open',
        profPubDesc: 'Non-sensitive public documentation.',
        vaultListTitle: 'Privacy Vault Items (Includes 🔒 Local-Only Max Security)',
        tot: 'Total', lockOnly: '🔒 Local Only', chatReady: '🛡️ Chat Ready',
        emptyVault: 'Vault is empty. Drop alsa.pdf or any document above.',
        inspectBtn: '👁️ Preview / Edit', copyBtn: '📋 Copy @private:', exportOneBtn: '⬇️ JSON', delBtn: '🗑️ Delete',
        localTip: 'Local LLM only: cloud egress blocked',
        drawerTitle: 'Inspect & Refine Sanitization',
        addTermsLbl: 'Mask extra terms (comma-separated)',
        applyUpdate: '✏️ Re-Sanitize & Save',
        addModelBtn: '+ Add Custom / Variable-Quant Model',
      },
      it: {
        title: 'Cortical Zero-Server Workspace',
        sub: '100% client-side (zero porte, zero demoni) · __NAV__',
        save: 'Salva Config', download: 'Esporta Config', import: 'Importa Config',
        tabs: {
          setup: '🚀 Setup guidato',
          vault: '🛡️ Privacy Vault',
          brain: '🧠 Local Brain (3+1)',
          models: '⚙️ Hardware & Modelli',
          harnesses: '🔌 8 Harness & Compositore',
          compression: '📊 ROI, Routing & TOON',
        },
        syncUnset: 'Modalità Zero-Server: Vault salvato nel browser (IndexedDB). Collega la cartella locale .cortical_data per sincronizzare con MCP/CLI.',
        syncLinked: 'Cartella collegata: ',
        connectBtn: '📂 Collega Cartella .cortical_data',
        reconnectBtn: '🔓 Ri-autorizza Cartella Collegata',
        uploadTitle: 'Carica & Anonimizza File in Locale (PDF, DOCX, XLSX, PPTX, TXT, JSON, MD)',
        dropHint: 'Trascina un file qui o clicca per sceglierlo (elaborazione 100% locale nel browser)',
        aliasLbl: 'Alias Vault (es. alsa)',
        policyLbl: 'Policy Dinamica',
        termsLbl: 'Termini custom da oscurare (separati da virgola)',
        uploadBtn: '🛡️ Elabora & Salva nel Vault',
        profMaxSec: '🔒 Massima Privacy · Solo Locale',
        profMaxSecDesc: 'Visibile qui nel Vault; utilizzabile SOLO da LLM locali, BLOCCATO verso LLM cloud.',
        profMed: '🛡️ Anonimizzato per Chat',
        profMedDesc: 'Rimuove metadati, email, telefoni, IBAN, CF e termini custom; pronto come @private:<alias>.',
        profLow: '📋 Solo Riassunto [REDACTED]',
        profLowDesc: 'Sostituisce tutte le entità sensibili con [REDACTED].',
        profPub: '🌐 Pubblico / fail_open',
        profPubDesc: 'Solo per documenti pubblici non sensibili.',
        vaultListTitle: 'Elenco Documenti Privacy Vault (Include file Solo Locale 🔒)',
        tot: 'Totale', lockOnly: '🔒 Solo Locale', chatReady: '🛡️ Pronti per Chat',
        emptyVault: 'Nessun file nel Vault. Carica alsa.pdf o un altro documento qui sopra.',
        inspectBtn: '👁️ Anteprima / Modifica', copyBtn: '📋 Copia @private:', exportOneBtn: '⬇️ JSON', delBtn: '🗑️ Elimina',
        localTip: 'Solo LLM locale: riferimento bloccato per chat cloud',
        drawerTitle: 'Ispezione & Affinamento Anonimizzazione',
        addTermsLbl: 'Oscura altri termini (nomi, aziende, CF...)',
        applyUpdate: '✏️ Riapplica & Salva',
        addModelBtn: '+ Aggiungi Modello Custom / Quant Variabile',
      }
    };

    let LANG = localStorage.getItem('cortical_lang') || ((navigator.language || '').toLowerCase().startsWith('it') ? 'it' : 'en');
    let TAB = localStorage.getItem('cortical_setup_done') ? 'vault' : 'setup';
    let SETUP_SEL = null;
    let FOLDER_WARN = '';
    let QUEUE = [];
    let IMGST = null;
    let ORIG = null;
    let BRAIN_DATA = ENV.initial_brain || null;
    let ROI_DATA = ENV.initial_roi || null;
    let BRAIN_VIEW = 'concept';
    let BRAIN_FILE_TIER = 'l1';
    const T = (it, en) => (LANG === 'it' ? it : en);
    const IS_WIN = /win/i.test(navigator.platform || '') && !/darwin|mac/i.test(navigator.platform || '');
    const IMG_RX = /\.(png|jpe?g|webp|gif|bmp)$/i;
    let ITEMS = [];
    let SELECTED_FILE = null;
    let SEL_PROFILE = 'max_security';
    let DRAFT = { alias: '', policy: 'auto', terms: '' };
    let LAST_SIG = '';
    let INSPECT = null;
    let DIR_HANDLE = null;
    let NEEDS_REAUTH = false;
    let BANNER = { kind: '', text: '' };

    function esc(s) {
      return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    }
    function setBanner(kind, text) {
      BANNER = { kind, text };
      render();
    }

    // --- Pure-JS IndexedDB store (works offline with zero servers) ---
    function openDb() {
      return new Promise((resolve, reject) => {
        const req = indexedDB.open('cortical_vault_db', 3);
        req.onupgradeneeded = () => {
          const db = req.result;
          if (!db.objectStoreNames.contains('items')) db.createObjectStore('items', { keyPath: 'alias' });
          if (!db.objectStoreNames.contains('handles')) db.createObjectStore('handles');
          if (!db.objectStoreNames.contains('originals')) db.createObjectStore('originals', { keyPath: 'alias' });
        };
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
      });
    }
    async function idbGetAllItems() {
      const db = await openDb();
      return new Promise((resolve, reject) => {
        const tx = db.transaction('items', 'readonly');
        const req = tx.objectStore('items').getAll();
        req.onsuccess = () => resolve((req.result || []).filter((x) => !x.deleted).sort((a, b) => (b.updated_at || 0) - (a.updated_at || 0)));
        req.onerror = () => reject(req.error);
      });
    }
    async function idbPutItem(rec) {
      const db = await openDb();
      return new Promise((resolve, reject) => {
        const tx = db.transaction('items', 'readwrite');
        tx.objectStore('items').put(rec);
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
      });
    }
    async function idbDeleteItem(alias) {
      const db = await openDb();
      return new Promise((resolve, reject) => {
        const tx = db.transaction('items', 'readwrite');
        tx.objectStore('items').delete(alias);
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
      });
    }
    async function idbOrig(mode, alias, rec) {
      const db = await openDb();
      return new Promise((resolve, reject) => {
        const tx = db.transaction('originals', mode === 'get' ? 'readonly' : 'readwrite');
        const st = tx.objectStore('originals');
        const req = mode === 'get' ? st.get(alias) : (mode === 'put' ? st.put(rec) : st.delete(alias));
        tx.oncomplete = () => resolve(mode === 'get' ? (req.result || null) : undefined);
        tx.onerror = () => reject(tx.error);
      });
    }
    async function idbSaveHandle(h) {
      const db = await openDb();
      return new Promise((resolve, reject) => {
        const tx = db.transaction('handles', 'readwrite');
        tx.objectStore('handles').put(h, 'cortical_dir');
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
      });
    }
    async function idbLoadHandle() {
      const db = await openDb();
      return new Promise((resolve, reject) => {
        const tx = db.transaction('handles', 'readonly');
        const req = tx.objectStore('handles').get('cortical_dir');
        req.onsuccess = () => resolve(req.result || null);
        req.onerror = () => reject(req.error);
      });
    }

    // --- File System Access API folder sync (.cortical_data/vault/*.json) ---
    async function resolveVaultParent(handle) {
      if (handle.name === 'Cortical' || handle.name === '.cortical_data') return handle;
      for (const n of ['vault', 'vault_inbox']) { try { await handle.getDirectoryHandle(n); return handle; } catch {} }
      try { return await handle.getDirectoryHandle('.cortical_data', { create: true }); } catch { return handle; }
    }

    async function writeJsonToFolder(subdirName, filename, dataObj) {
      if (!DIR_HANDLE) return false;
      const root = await resolveVaultParent(DIR_HANDLE);
      const sub = subdirName ? await root.getDirectoryHandle(subdirName, { create: true }) : root;
      const fh = await sub.getFileHandle(filename, { create: true });
      const w = await fh.createWritable();
      await w.write(JSON.stringify(dataObj, null, 2) + '\n');
      await w.close();
      return true;
    }

    async function writeBytesToFolder(subdirName, filename, bytes) {
      if (!DIR_HANDLE) return false;
      const root = await resolveVaultParent(DIR_HANDLE);
      const sub = await root.getDirectoryHandle(subdirName, { create: true });
      const fh = await sub.getFileHandle(filename, { create: true });
      const w = await fh.createWritable();
      await w.write(bytes);
      await w.close();
      return true;
    }

    async function syncFolderAndDb(fromPoll = false) {
      if (fromPoll) {
        const ae = document.activeElement;
        if (ae && /^(INPUT|TEXTAREA|SELECT)$/.test(ae.tagName)) return;
      }
      const merged = new Map();
      (await idbGetAllItems()).forEach((it) => merged.set(it.alias, it));

      if (DIR_HANDLE && !NEEDS_REAUTH) {
        try {
          const root = await resolveVaultParent(DIR_HANDLE);
          const sub = await root.getDirectoryHandle('vault', { create: true });
          for await (const [name, entry] of sub.entries()) {
            if (entry.kind !== 'file' || !name.endsWith('.json')) continue;
            const file = await entry.getFile();
            const txt = await file.text();
            try {
              const obj = JSON.parse(txt);
              if (!obj || !obj.alias) continue;
              if (obj.deleted) {
                merged.delete(obj.alias);
                await idbDeleteItem(obj.alias);
                continue;
              }
              const cur = merged.get(obj.alias);
              if (!cur || (obj.updated_at || 0) >= (cur.updated_at || 0)) {
                merged.set(obj.alias, obj);
                await idbPutItem(obj);
              }
            } catch {}
          }
          QUEUE = [];
          try {
            const ib = await root.getDirectoryHandle('vault_inbox');
            const errs = new Map();
            const raws = [];
            for await (const [name, entry] of ib.entries()) {
              if (entry.kind !== 'file' || name.startsWith('.') || name.endsWith('.meta.json')) continue;
              if (name.endsWith('.error.json')) {
                let m = ''; try { m = JSON.parse(await (await entry.getFile()).text()).error; } catch {}
                errs.set(name.replace(/\.error\.json$/, ''), m);
              } else raws.push(name);
            }
            raws.forEach((n) => QUEUE.push({ name: n, error: errs.get(n) || '' }));
          } catch {}
          try {
            const bf = await (await root.getFileHandle('brain.json')).getFile();
            BRAIN_DATA = JSON.parse(await bf.text());
          } catch {}
          try {
            const rf = await (await root.getFileHandle('roi.json')).getFile();
            ROI_DATA = JSON.parse(await rf.text());
          } catch {}
        } catch (err) {
          NEEDS_REAUTH = true;
        }
      }
      const nextItems = Array.from(merged.values()).sort((a, b) => (b.updated_at || 0) - (a.updated_at || 0));
      const sig = JSON.stringify({ i: nextItems.map((x) => [x.alias, x.updated_at, x.profile]), q: QUEUE });
      ITEMS = nextItems;
      if (fromPoll && sig === LAST_SIG) return;
      LAST_SIG = sig;
      render();
    }

    async function linkCorticalFolder() {
      if (typeof window.showDirectoryPicker !== 'function') {
        setBanner('info', 'Browser senza File System Access API (es. Safari/Firefox). Puoi comunque usare il Vault in locale via IndexedDB e scaricare il JSON in .cortical_data/vault/, oppure aprire https://ccancellieri.github.io/cortical/settings.html in Chrome/Edge.');
        return;
      }
      try {
        const h = await window.showDirectoryPicker({ mode: 'readwrite', id: 'cortical', startIn: 'documents' });
        let valid = h.name === '.cortical_data' || h.name === 'Cortical';
        if (!valid) { try { await h.getFileHandle('vault.db'); valid = true; } catch {} }
        if (!valid) { try { await h.getDirectoryHandle('vault'); valid = true; } catch {} }
        if (!valid) { try { await h.getDirectoryHandle('vault_inbox'); valid = true; } catch {} }
        if (!valid) { try { await h.getDirectoryHandle('.cortical_data'); valid = true; } catch {} }
        if (!valid) { try { await h.getFileHandle('pyproject.toml'); valid = true; } catch {} }
        if (!valid) {
          FOLDER_WARN = (LANG === 'it' ? 'La cartella scelta ("' + h.name + '") non sembra quella di Cortical. Scegli: ' : 'Chosen folder ("' + h.name + '") does not look like Cortical. Choose: ') + ENV.data_display;
          setBanner('err', FOLDER_WARN);
          return;
        }
        FOLDER_WARN = '';
        localStorage.setItem('cortical_setup_done', '1');
        DIR_HANDLE = h;
        NEEDS_REAUTH = false;
        await idbSaveHandle(h);
        // Push any already uploaded IndexedDB items into `.cortical_data/vault/`
        for (const it of ITEMS) {
          await writeJsonToFolder('vault', it.alias + '.json', it);
        }
        await syncFolderAndDb();
        setBanner('ok', 'Cartella collegata con successo! I file vengono sincronizzati in .cortical_data/vault/*.json senza servizi attivi.');
      } catch (err) {
        if (err && err.name === 'AbortError') return;
        setBanner('info', 'Accesso diretto cartella non consentito in questo contesto (' + (err?.message || err) + '). Salvo nel Vault locale del browser (IndexedDB) + pulsante Esporta JSON per .cortical_data/vault/.');
      }
    }

    async function reauthorizeFolder() {
      if (!DIR_HANDLE) return linkCorticalFolder();
      try {
        const perm = await DIR_HANDLE.requestPermission({ mode: 'readwrite' });
        if (perm === 'granted') {
          NEEDS_REAUTH = false;
          await syncFolderAndDb();
          setBanner('ok', 'Permesso cartella rinnovato.');
        }
      } catch (err) {
        await linkCorticalFolder();
      }
    }

    // --- Pure-JS Decompressors & PDF/DOCX/Text Extractors (Zero External Deps) ---
    async function inflateBytes(u8, format) {
      if (typeof DecompressionStream !== 'function') throw new Error('DecompressionStream unavailable');
      const ds = new DecompressionStream(format);
      const stream = new Blob([u8]).stream().pipeThrough(ds);
      return new Uint8Array(await new Response(stream).arrayBuffer());
    }

    function readU16LE(b, o) { return b[o] | (b[o + 1] << 8); }
    function readU32LE(b, o) { return (b[o] | (b[o + 1] << 8) | (b[o + 2] << 16) | (b[o + 3] << 24)) >>> 0; }

    async function extractOoxmlText(u8) {
      const stripped = [];
      const texts = [];
      let eocd = -1;
      for (let i = Math.max(0, u8.length - 65558); i >= 0; i--) {
        if (u8[i] === 0x50 && u8[i + 1] === 0x4b && u8[i + 2] === 0x05 && u8[i + 3] === 0x06) { eocd = i; break; }
      }
      if (eocd < 0) throw new Error('Invalid ZIP/OOXML container');
      const cdCount = readU16LE(u8, eocd + 10);
      let off = readU32LE(u8, eocd + 16);
      const td = new TextDecoder('utf-8');
      for (let idx = 0; idx < cdCount && off + 46 <= u8.length; idx++) {
        if (readU32LE(u8, off) !== 0x02014b50) break;
        const method = readU16LE(u8, off + 10);
        const compSz = readU32LE(u8, off + 20);
        const nLen = readU16LE(u8, off + 28);
        const exLen = readU16LE(u8, off + 30);
        const cmLen = readU16LE(u8, off + 32);
        const lOff = readU32LE(u8, off + 42);
        const fname = td.decode(u8.subarray(off + 46, off + 46 + nLen));
        off += 46 + nLen + exLen + cmLen;

        if (fname === 'docProps/core.xml' || fname === 'docProps/app.xml' || fname === 'docProps/custom.xml') {
          stripped.push(fname);
          continue;
        }
        if (fname.endsWith('.xml') && (fname.startsWith('word/document') || fname.startsWith('xl/sharedStrings') || fname.startsWith('ppt/slides/slide'))) {
          const ln = readU16LE(u8, lOff + 26);
          const le = readU16LE(u8, lOff + 28);
          const start = lOff + 30 + ln + le;
          const slice = u8.subarray(start, start + compSz);
          const rawXml = method === 0 ? slice : await inflateBytes(slice, 'deflate-raw');
          const xmlText = td.decode(rawXml).replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
          if (xmlText) texts.push(xmlText);
        }
      }
      return { text: texts.join('\n'), stripped };
    }

    function unescapePdfStr(s) {
      return s
        .replace(/\\\\/g, '\x00')
        .replace(/\\\(/g, '(')
        .replace(/\\\)/g, ')')
        .replace(/\\n/g, '\n')
        .replace(/\\r/g, '\n')
        .replace(/\\t/g, '\t')
        .replace(/\\([0-7]{1,3})/g, (_m, oct) => String.fromCharCode(parseInt(oct, 8)))
        .replace(/\x00/g, '\\');
    }

    function buildCmapFromStreams(decodedStreams) {
      const cmap = new Map();
      const hexToUtf = (hex) => {
        const clean = hex.replace(/\s+/g, '');
        let out = '';
        if (clean.length % 4 === 0) {
          for (let i = 0; i < clean.length; i += 4) out += String.fromCharCode(parseInt(clean.slice(i, i + 4), 16));
        } else {
          for (let i = 0; i < clean.length; i += 2) out += String.fromCharCode(parseInt(clean.slice(i, i + 2), 16));
        }
        return out;
      };
      for (const s of decodedStreams) {
        if (!s.includes('beginbfchar') && !s.includes('beginbfrange')) continue;
        for (const m of s.matchAll(/<([0-9a-fA-F]+)>\s*<([0-9a-fA-F]+)>/g)) {
          cmap.set(m[1].toUpperCase(), hexToUtf(m[2]));
        }
      }
      return cmap;
    }

    function decodeHexPdf(hex, cmap) {
      const c = hex.replace(/\s+/g, '').toUpperCase();
      if (cmap.size > 0) {
        const keyLen = Array.from(cmap.keys())[0].length || 4;
        let mapped = '';
        let hits = 0;
        for (let i = 0; i + keyLen <= c.length; i += keyLen) {
          const k = c.slice(i, i + keyLen);
          if (cmap.has(k)) { mapped += cmap.get(k); hits++; }
        }
        if (hits > 0) return mapped;
      }
      let out = '';
      for (let i = 0; i + 1 < c.length; i += 2) {
        const code = parseInt(c.slice(i, i + 2), 16);
        if (code >= 32 || code === 10) out += String.fromCharCode(code);
      }
      return out;
    }

    async function extractPdfTextJS(u8) {
      const latin = new TextDecoder('latin1').decode(u8);
      const stripped = [];
      ['Author', 'Creator', 'Producer', 'Company', 'Title', 'Subject'].forEach((tag) => {
        if (new RegExp('/' + tag + '\\s*\\(').test(latin)) stripped.push('pdf:/' + tag);
      });

      const streams = [];
      const streamRe = /stream\r?\n([\s\S]*?)\r?\n?endstream/g;
      let sm;
      while ((sm = streamRe.exec(latin)) !== null) {
        const start = sm.index + sm[0].indexOf(sm[1]);
        const end = start + sm[1].length;
        const slice = u8.subarray(start, end);
        let decoded = sm[1];
        try {
          const inf = await inflateBytes(slice, 'deflate');
          decoded = new TextDecoder('latin1').decode(inf);
        } catch {
          try {
            const infRaw = await inflateBytes(slice, 'deflate-raw');
            decoded = new TextDecoder('latin1').decode(infRaw);
          } catch {}
        }
        streams.push(decoded);
      }

      const cmap = buildCmapFromStreams(streams);
      const chunks = [];
      for (const ds of streams) {
        if (ds.includes('beginbfchar') || ds.includes('beginbfrange')) continue;
        const tjRe = /\(((?:\\.|[^\\()])*)\)\s*Tj|<([0-9a-fA-F\s]+)>\s*Tj|\[([\s\S]*?)\]\s*TJ/g;
        let tm;
        while ((tm = tjRe.exec(ds)) !== null) {
          if (tm[1]) chunks.push(unescapePdfStr(tm[1]));
          else if (tm[2]) chunks.push(decodeHexPdf(tm[2], cmap));
          else if (tm[3]) {
            let line = '';
            for (const part of tm[3].matchAll(/\(((?:\\.|[^\\()])*)\)|<([0-9a-fA-F\s]+)>/g)) {
              line += part[1] ? unescapePdfStr(part[1]) : decodeHexPdf(part[2], cmap);
            }
            if (line.trim()) chunks.push(line);
          }
        }
      }

      if (chunks.length === 0) {
        const cleaned = latin.replace(/\/(Author|Creator|Producer|Company|Title|Subject)\s*\([^)]*\)/g, '');
        for (const lit of cleaned.matchAll(/\(((?:\\.|[^\\()]){3,300})\)/g)) {
          const v = unescapePdfStr(lit[1]).trim();
          if (v && !v.startsWith('/')) chunks.push(v);
        }
      }

      const rawText = chunks.join('\n').replace(/[^\S\r\n]+/g, ' ').replace(/\n{3,}/g, '\n\n').trim();
      const nonSpace = rawText.replace(/\s+/g, '');
      const printable = rawText.replace(/[^\x20-\x7E\xA0-\xFF\n\t]/g, '');
      const ratio = rawText.length ? (printable.length / rawText.length) : 0;
      return { text: rawText, stripped, readable: nonSpace.length >= 5 && ratio >= 0.65 };
    }

    // --- Client-Side Sanitizer (mirrors Python sanitizer.py without Title-Case false positives) ---
    function sanitizeTextClient(text, profile, customTerms, keepTerms) {
      const keep = new Set((keepTerms || []).map((k) => String(k).trim().toLowerCase()).filter(Boolean));
      const mapping = {};
      const rev = new Map();
      const counts = {};
      const redact = profile === 'max_security' || profile === 'low';
      const tokFor = (cat, val) => {
        if (keep.has(val.trim().toLowerCase())) return val;
        if (rev.has(val)) return rev.get(val);
        if (redact) {
          rev.set(val, '[REDACTED]');
          mapping[cat + '_' + (Object.keys(mapping).length + 1)] = val;
          return '[REDACTED]';
        }
        counts[cat] = (counts[cat] || 0) + 1;
        const tok = `[${cat}_${counts[cat]}]`;
        rev.set(val, tok);
        mapping[tok] = val;
        return tok;
      };

      if (profile === 'max_context') {
        return { text, entityCount: 0, sensitiveDetected: false, mapping: {} };
      }

      let out = String(text || '');
      const sortedTerms = (customTerms || []).map((s) => s.trim()).filter(Boolean).sort((a, b) => b.length - a.length);
      for (const term of sortedTerms) {
        const rx = new RegExp('(?<!\\w)' + term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '(?!\\w)', 'gi');
        out = out.replace(rx, (m) => tokFor('CUSTOM', m));
      }

      const patterns = [
        ['SECRET', /\b(?:sk-[a-zA-Z0-9_-]{16,}|gh[pous]_[a-zA-Z0-9]{20,}|AKIA[0-9A-Z]{16}|Bearer\s+[A-Za-z0-9._-]{16,}|pplx-[A-Za-z0-9]{20,})\b/g],
        ['IBAN', /\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b/g],
        ['TAX_ID', /\b[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]\b/g],
        ['EMAIL', /\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b/g],
        ['PHONE', /(?<!\w)(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?)\d{3,4}[\s.-]?\d{3,4}(?!\w)/g],
        ['IP', /\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b/g],
      ];
      for (const [cat, rx] of patterns) {
        out = out.replace(rx, (m) => tokFor(cat, m));
      }
      const entityCount = Object.keys(mapping).length;
      return { text: out, entityCount, sensitiveDetected: entityCount > 0, mapping };
    }

    function setPriv(k, v) {
      CFG.privacy = CFG.privacy || {};
      CFG.privacy[k] = v;
      persistConfigToFolder();
      render();
    }
    async function persistConfigToFolder() {
      if (!DIR_HANDLE || NEEDS_REAUTH) return;
      try { await writeJsonToFolder('', 'cortical.config.json', CFG); } catch {}
    }
    function aliasFrom(name) {
      const raw = (document.getElementById('v-alias')?.value || name.replace(/\.[^.]+$/, '')).trim();
      return raw.toLowerCase().replace(/[^a-z0-9._-]+/g, '_').replace(/^_+|_+$/g, '') || ('item_' + Math.floor(Date.now() / 1000));
    }
    function useModel() { return (CFG.privacy || {}).use_local_ner !== false; }
    function linkedOk() { return !!DIR_HANDLE && !NEEDS_REAUTH; }

    async function submitJob(filename, bytesOrBlob, meta) {
      await writeBytesToFolder('vault_inbox', filename, bytesOrBlob);
      await writeJsonToFolder('vault_inbox', filename + '.meta.json', meta);
      await syncFolderAndDb();
    }
    function jobMeta(alias, extra) {
      const pv = CFG.privacy || {};
      return Object.assign({
        alias, policy: document.getElementById('v-policy')?.value || 'auto', profile: SEL_PROFILE,
        custom_terms: [], keep_terms: [], use_local_ner: useModel(),
        ner_model: pv.ner_model || '', vision_model: pv.vision_model || '',
      }, extra || {});
    }

    // ---- image editor (manual black boxes, 100% in browser) ----
    async function loadImageEditor(file) {
      IMGST = { file, bmp: await createImageBitmap(file), rects: [], drag: null };
      render();
    }
    function drawImg() {
      const c = document.getElementById('img-canvas');
      if (!c || !IMGST) return;
      const sc = Math.min(1, 720 / IMGST.bmp.width);
      c.width = Math.round(IMGST.bmp.width * sc); c.height = Math.round(IMGST.bmp.height * sc);
      const g = c.getContext('2d');
      g.drawImage(IMGST.bmp, 0, 0, c.width, c.height);
      g.fillStyle = '#000';
      const all = IMGST.drag ? IMGST.rects.concat([IMGST.drag]) : IMGST.rects;
      all.forEach((r) => g.fillRect(r.x * c.width, r.y * c.height, r.w * c.width, r.h * c.height));
    }
    function imgPos(ev) {
      const c = document.getElementById('img-canvas'); const b = c.getBoundingClientRect();
      return { x: Math.min(1, Math.max(0, (ev.clientX - b.left) / b.width)), y: Math.min(1, Math.max(0, (ev.clientY - b.top) / b.height)) };
    }
    function imgDown(ev) { const p = imgPos(ev); IMGST.start = p; IMGST.drag = { x: p.x, y: p.y, w: 0, h: 0 }; }
    function imgMove(ev) {
      if (!IMGST || !IMGST.drag) return;
      const p = imgPos(ev), s0 = IMGST.start;
      IMGST.drag = { x: Math.min(s0.x, p.x), y: Math.min(s0.y, p.y), w: Math.abs(p.x - s0.x), h: Math.abs(p.y - s0.y) };
      drawImg();
    }
    function imgUp() {
      if (!IMGST || !IMGST.drag) return;
      if (IMGST.drag.w > 0.004 && IMGST.drag.h > 0.004) IMGST.rects.push(IMGST.drag);
      IMGST.drag = null; render();
    }
    function imgUndo() { if (IMGST) { IMGST.rects.pop(); render(); } }
    async function redactedPngBlob() {
      const c = document.createElement('canvas'); c.width = IMGST.bmp.width; c.height = IMGST.bmp.height;
      const g = c.getContext('2d'); g.drawImage(IMGST.bmp, 0, 0); g.fillStyle = '#000';
      IMGST.rects.forEach((r) => g.fillRect(r.x * c.width, r.y * c.height, r.w * c.width, r.h * c.height));
      return await new Promise((res) => c.toBlob(res, 'image/png'));
    }

    async function processSelectedFile() {
      if (!SELECTED_FILE) { setBanner('err', T('Seleziona prima un file.', 'Pick a file first.')); return; }
      const file = SELECTED_FILE;
      const alias = aliasFrom(file.name);
      const customTerms = (document.getElementById('v-terms')?.value || '').split(',').map((s) => s.trim()).filter(Boolean);
      const pv = CFG.privacy || {};

      if (IMG_RX.test(file.name)) {
        if (!linkedOk()) { setBanner('err', T('Per le immagini serve il modello locale: collega prima la cartella Cortical (scheda Setup guidato).', 'Images need the local model: link the Cortical folder first (Guided Setup tab).')); return; }
        if (!pv.vision_model) { setBanner('err', T('Scegli un modello con visione (es. qwen2.5vl:3b) nella sezione Modelli locali.', 'Pick a vision model (e.g. qwen2.5vl:3b) in Local models.')); return; }
        const blob = await redactedPngBlob();
        await submitJob(alias + '.png', blob, jobMeta(alias, { custom_terms: customTerms, source_name: file.name, use_local_ner: true }));
        await idbOrig('put', alias, { alias, kind: 'image', text: '', marks: customTerms, keep: [], rects: IMGST ? IMGST.rects.length : 0 });
        SELECTED_FILE = null; IMGST = null; DRAFT.alias = ''; DRAFT.terms = '';
        setBanner('info', T('Immagine in coda: i riquadri neri sono già applicati; il modello locale legge il testo residuo.', 'Image queued: black boxes are applied; the local model reads remaining text.'));
        return;
      }

      const buf = await file.arrayBuffer();
      const u8 = new Uint8Array(buf);
      const nameLower = file.name.toLowerCase();
      const reqPolicy = DRAFT.policy || document.getElementById('v-policy')?.value || 'auto';
      let extracted = ''; let strippedMeta = []; let needsPy = false;
      if (/\.(docx|xlsx|pptx)$/.test(nameLower)) { const r = await extractOoxmlText(u8); extracted = r.text; strippedMeta = r.stripped; }
      else if (nameLower.endsWith('.pdf')) { const r = await extractPdfTextJS(u8); extracted = r.text; strippedMeta = r.stripped; needsPy = !r.readable; }
      else extracted = new TextDecoder('utf-8', { fatal: false }).decode(u8);

      await idbOrig('put', alias, { alias, kind: 'text', text: extracted, marks: customTerms, keep: [] });

      if (linkedOk() && (useModel() || needsPy)) {
        await submitJob(file.name, u8, jobMeta(alias, { custom_terms: customTerms, source_name: file.name }));
        SELECTED_FILE = null; DRAFT.alias = ''; DRAFT.terms = '';
        setBanner('info', T('In coda per l\'anonimizzazione con il modello locale (' + (pv.ner_model || 'default') + ').', 'Queued for anonymization with the local model (' + (pv.ner_model || 'default') + ').'));
        return;
      }
      if (needsPy) { setBanner('err', T('Questo PDF richiede il modello/estrattore locale: collega la cartella Cortical.', 'This PDF needs the local model/extractor: link the Cortical folder.')); return; }

      const san = sanitizeTextClient(extracted, SEL_PROFILE, customTerms, []);
      const resolvedPolicy = reqPolicy === 'auto' ? ((san.sensitiveDetected || strippedMeta.length > 0 || SEL_PROFILE === 'max_security') ? 'fail_closed' : 'fail_open') : reqPolicy;
      const record = {
        alias, uri: 'cortical://private/' + alias, source_name: file.name, resolved_policy: resolvedPolicy, profile: SEL_PROFILE,
        local_only: SEL_PROFILE === 'max_security', format_used: 'text', sanitized_content: san.text,
        entity_count: san.entityCount + strippedMeta.length, tokens_est: Math.max(1, Math.round(san.text.length / 4)),
        sha256_hash: 'ui_' + Math.random().toString(16).slice(2, 14), updated_at: Date.now() / 1000, ner_used: false,
      };
      await idbPutItem(record);
      const synced = linkedOk() ? await writeJsonToFolder('vault', alias + '.json', record) : false;
      SELECTED_FILE = null; INSPECT = record; ORIG = await idbOrig('get', alias);
      await syncFolderAndDb();
      setBanner('ok', T('Anteprima rapida (solo regole, nessun modello): @private:', 'Quick preview (rules only, no model): @private:') + alias + (synced ? '' : T(' — salvata solo nel browser', ' — browser only')));
    }

    async function openInspect(alias) {
      INSPECT = ITEMS.find((x) => x.alias === alias) || null;
      ORIG = INSPECT ? await idbOrig('get', alias) : null;
      render();
    }
    function selectedTextIn(id) {
      const sel = window.getSelection(); if (!sel || sel.isCollapsed) return '';
      const node = document.getElementById(id);
      return node && node.contains(sel.anchorNode) ? sel.toString().trim() : '';
    }
    async function addMarkFromSelection() {
      const t = selectedTextIn('rv-orig') || selectedTextIn('rv-san');
      if (!t) { setBanner('info', T('Seleziona con il mouse una parte di testo da oscurare.', 'Select a piece of text with the mouse first.')); return; }
      if (ORIG) { ORIG.marks = Array.from(new Set((ORIG.marks || []).concat([t]))); ORIG.keep = (ORIG.keep || []).filter((k) => k.toLowerCase() !== t.toLowerCase()); }
      else { INSPECT.__extra = Array.from(new Set((INSPECT.__extra || []).concat([t]))); }
      await applyCorrections();
    }
    async function toggleKeep(raw) {
      if (!ORIG) return;
      const lo = raw.toLowerCase(); const has = (ORIG.keep || []).some((k) => k.toLowerCase() === lo);
      ORIG.keep = has ? ORIG.keep.filter((k) => k.toLowerCase() !== lo) : (ORIG.keep || []).concat([raw]);
      if (!has) ORIG.marks = (ORIG.marks || []).filter((m) => m.toLowerCase() !== lo);
      await applyCorrections();
    }
    async function applyCorrections() {
      if (!INSPECT) return;
      const prof = document.getElementById('re-profile')?.value || INSPECT.profile;
      const typed = (document.getElementById('re-terms')?.value || '').split(',').map((s) => s.trim()).filter(Boolean);
      if (ORIG && typed.length) ORIG.marks = Array.from(new Set((ORIG.marks || []).concat(typed)));
      const extra = (INSPECT.__extra || []).concat(ORIG ? [] : typed);
      if (ORIG) await idbOrig('put', ORIG.alias, ORIG);
      if (ORIG && ORIG.text && linkedOk() && useModel()) {
        await submitJob(INSPECT.alias + '.txt', new TextEncoder().encode(ORIG.text), jobMeta(INSPECT.alias, {
          profile: prof, custom_terms: ORIG.marks || [], keep_terms: ORIG.keep || [], source_name: INSPECT.source_name,
        }));
        setBanner('info', T('Correzioni inviate in coda: il modello locale rielabora il documento dall\'originale. Esegui "watch" o attendi.', 'Corrections queued: the local model re-processes from the original. Run "watch" or wait.'));
        return;
      }
      const base = ORIG && ORIG.text ? ORIG.text : (INSPECT.sanitized_content || '');
      const san = sanitizeTextClient(base, prof, ORIG ? (ORIG.marks || []) : extra, ORIG ? (ORIG.keep || []) : []);
      const updated = Object.assign({}, INSPECT, {
        profile: prof, local_only: prof === 'max_security',
        resolved_policy: prof === 'max_security' ? 'fail_closed' : (prof === 'max_context' ? 'fail_open' : 'auto'),
        sanitized_content: san.text, entity_count: ORIG ? san.entityCount : Number(INSPECT.entity_count || 0) + san.entityCount,
        tokens_est: Math.max(1, Math.round(san.text.length / 4)), updated_at: Date.now() / 1000, __extra: undefined,
      });
      delete updated.__extra;
      await idbPutItem(updated);
      if (linkedOk()) await writeJsonToFolder('vault', updated.alias + '.json', updated);
      INSPECT = updated;
      await syncFolderAndDb();
      INSPECT = ITEMS.find((x) => x.alias === updated.alias) || updated;
      setBanner('ok', T('Aggiornato @private:', 'Updated @private:') + updated.alias);
    }
    async function dismissQueue(name) {
      try {
        const root = await resolveVaultParent(DIR_HANDLE); const ib = await root.getDirectoryHandle('vault_inbox');
        for (const n of [name, name + '.meta.json', name + '.error.json']) { try { await ib.removeEntry(n); } catch {} }
      } catch {}
      await syncFolderAndDb();
    }

    async function removeVaultItem(alias) {
      await idbDeleteItem(alias);
      await idbOrig('del', alias);
      if (DIR_HANDLE && !NEEDS_REAUTH) {
        await writeJsonToFolder('vault', alias + '.json', { alias, deleted: true, updated_at: Date.now() / 1000 });
      }
      if (INSPECT && INSPECT.alias === alias) INSPECT = null;
      await syncFolderAndDb();
      setBanner('ok', `Eliminato @private:${alias}`);
    }

    function downloadOneVaultJson(alias) {
      const it = ITEMS.find((x) => x.alias === alias);
      if (!it) return;
      const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([JSON.stringify(it, null, 2) + '\n'], { type: 'application/json' }));
      a.download = alias + '.json';
      a.click();
    }

    function copyAliasRef(alias) {
      if (navigator.clipboard) navigator.clipboard.writeText('@private:' + alias).catch(() => {});
      setBanner('ok', 'Copiato: @private:' + alias);
    }

    async function pickFileObj(f) {
      if (!f) return;
      SELECTED_FILE = f; IMGST = null;
      DRAFT.alias = f.name.replace(/\.[^.]+$/, '');
      if (IMG_RX.test(f.name)) { try { await loadImageEditor(f); return; } catch {} }
      render();
    }

    // --- Tab 2: Hardware & Custom Variable-Quant Model Builder ---
    function allModels() {
      const map = new Map();
      CATALOG.forEach((m) => map.set(m.model_id, { ...m, custom: false }));
      (CFG.custom_models || []).forEach((m) => map.set(m.model_id, { ...m, custom: true }));
      return Array.from(map.values());
    }
    function addCustomModelFromForm() {
      const id = (document.getElementById('cm-id')?.value || '').trim();
      if (!id) return;
      const entry = {
        model_id: id,
        runner: document.getElementById('cm-runner')?.value || 'ollama',
        memory_gb: Number(document.getElementById('cm-mem')?.value || 8.1),
        native_ctx: Number(document.getElementById('cm-ctx')?.value || 32768),
        quantization: document.getElementById('cm-quant')?.value.trim() || 'Variable Quant',
        is_variable_quant: Boolean(document.getElementById('cm-var')?.checked),
        roles: (document.getElementById('cm-roles')?.value || 'deep_reasoner').split(',').map((s) => s.trim()).filter(Boolean),
        pull_ref: document.getElementById('cm-pull')?.value.trim() || ('ollama pull ' + id),
        notes: document.getElementById('cm-notes')?.value.trim() || 'Custom user model',
      };
      CFG.custom_models = (CFG.custom_models || []).filter((x) => x.model_id !== id);
      CFG.custom_models.push(entry);
      setBanner('ok', 'Modello aggiunto alla configurazione: ' + id);
    }
    function removeCustomModel(id) {
      CFG.custom_models = (CFG.custom_models || []).filter((x) => x.model_id !== id);
      render();
    }
    function assignRoleModel(role, modelId) {
      CFG.models_by_role = CFG.models_by_role || {};
      CFG.models_by_role[role] = modelId;
      if (role === 'daily_coder') CFG.active_model = modelId;
      render();
    }


    function copyText(t, msg) {
      if (navigator.clipboard) navigator.clipboard.writeText(t).catch(() => {});
      setBanner('ok', msg || T('Copiato negli appunti.', 'Copied to clipboard.'));
    }
    function cliCmd(kind) { const c = (ENV[kind] || {}); return IS_WIN ? c.win : c.posix; }

    function copyLocalUse(alias) {
      const cmd = `Usa cortical_local_offload(vault_alias="${alias}") sul modello Ollama locale (solo locale, zero invio cloud).`;
      copyText(cmd, T('Copiato comando locale per Ollama: ', 'Copied local Ollama prompt: ') + alias);
    }

    function modelCard() {
      const pv = CFG.privacy || {};
      const capsList = ENV.installed_model_caps || [];
      const inst = ENV.installed_models || [];
      const catIds = CATALOG.map((m) => m.model_id);
      const allOpts = Array.from(new Set(inst.concat(catIds).concat(ENV.vision_suggestions || [])));
      const capLabel = (name) => {
        const found = capsList.find((x) => x.name === name);
        const isInst = inst.includes(name);
        const caps = found && found.capabilities ? found.capabilities.join(', ') : '';
        return `${name}${isInst ? ' ✓' : ' (pull)'}${caps ? ' [' + caps + ']' : ''}`;
      };
      const curNer = pv.ner_model || 'qwen2.5:1.5b';
      const nerSet = Array.from(new Set([curNer].concat(allOpts)));
      const nerOptions = nerSet.map((m) => `<option value="${esc(m)}" ${m === curNer ? 'selected' : ''}>${esc(capLabel(m))}</option>`).join('');

      const visInstalled = capsList.filter((c) => (c.capabilities || []).includes('vision')).map((c) => c.name);
      const curVis = pv.vision_model || (visInstalled[0] || '');
      const visSet = Array.from(new Set([''].concat(visInstalled, ENV.vision_suggestions || [], inst)));
      const visOptions = visSet.map((m) => `<option value="${esc(m)}" ${m === curVis ? 'selected' : ''}>${m ? esc(capLabel(m)) : T('-- Nessuno (solo riquadri neri) --', '-- None (black boxes only) --')}</option>`).join('');

      const vmMissing = curVis && inst.length && !inst.includes(curVis);
      const vmNoProj = curVis && inst.includes(curVis) && !visInstalled.includes(curVis);
      const pullName = (curVis && !vmNoProj) ? curVis : (ENV.vision_suggestions || ['qwen2.5vl:3b'])[0];
      const visBanner = vmNoProj
        ? `<div class="alert err" style="display:block;">⚠️ <code>${esc(curVis)}</code> ${T('è solo testuale (senza proiettore immagini mmproj). Scarica un modello con visione reale:', 'is text-only (no multimodal mmproj). Pull a real vision model:')} <button class="btn" onclick="copyText('ollama pull ${esc(pullName)}')">📋 ollama pull ${esc(pullName)}</button></div>`
        : ((!curVis || vmMissing) ? `<div class="alert info" style="display:block;">${curVis ? T('Il modello visione selezionato non è ancora scaricato:', 'Selected vision model is not pulled yet:') : T('Per leggere testo dalle immagini scarica un modello visione:', 'To OCR images, pull a vision model:')} <button class="btn" onclick="copyText('ollama pull ${esc(pullName)}')">📋 ollama pull ${esc(pullName)}</button></div>` : '');
      return `
        <div class="card">
          <h2>🧠 ${T('Modelli locali per l\'anonimizzazione (tutti i modelli installati)', 'Local anonymization models (all installed models)')}</h2>
          <div class="grid">
            <label>${T('Modello Testo / NER (scegli tra tutti)', 'Text / NER Model (pick any)')}
              <select onchange="setPriv('ner_model', this.value)">${nerOptions}</select></label>
            <label>${T('Modello Immagini / Visione', 'Image / Vision Model')}
              <select onchange="setPriv('vision_model', this.value)">${visOptions}</select></label>
          </div>
          <label class="chk" style="margin:10px 0;"><input type="checkbox" ${useModel() ? 'checked' : ''} onchange="setPriv('use_local_ner', this.checked)" />
            ${T('Usa il modello locale per anonimizzare (consigliato).', 'Use the local model to anonymize (recommended).')}</label>
          ${visBanner}
          <p style="font-size:0.78rem;color:var(--muted);margin:0;">${T('✓ = già installato in Ollama con capacità verificate. I job in coda partono con "watch" o aprendo un harness MCP.', '✓ = already installed in Ollama with verified capabilities.')}</p>
        </div>`;
    }

    function queueCard() {
      if (!QUEUE.length) return '';
      const rows = QUEUE.map((q) => `<tr><td>${q.error ? '❌' : '⏳'} <b>${esc(q.name)}</b></td><td style="color:${q.error ? 'var(--danger)' : 'var(--muted)'};">${esc(q.error || T('in attesa di elaborazione locale', 'waiting for local processing'))}</td>
        <td><button class="btn btn-danger" onclick="dismissQueue('${esc(q.name)}')">${T('Rimuovi', 'Remove')}</button></td></tr>`).join('');
      return `<div class="card"><h2>⏳ ${T('In coda (elaborazione con modello locale)', 'Queued (local model processing)')}</h2>
        <table><tbody>${rows}</tbody></table>
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:10px;align-items:center;">
          <button class="btn btn-em" onclick="copyText(cliCmd('watch_cmd'))">📋 ${T('Copia comando "watch" (elabora la coda)', 'Copy "watch" command (processes the queue)')}</button>
          <button class="btn" onclick="syncFolderAndDb()">↻ ${T('Aggiorna', 'Refresh')}</button>
          <span style="font-size:0.78rem;color:var(--muted);">${T('Si elabora anche da solo quando un agente usa cortical-mcp.', 'Also runs by itself when an agent uses cortical-mcp.')}</span>
        </div></div>`;
    }

    function renderSetupPanel(L) {
      const linked = linkedOk();
      const hs = ENV.harness_status || {};
      const names = Object.keys(PRESEND);
      const rows = names.map((h) => {
        const st = hs[h] || {};
        const badge = ENV.public ? '' : (st.linked ? '<span class="pill pill-ok">✅ ' + T('collegato', 'linked') + '</span>'
          : (st.detected ? '<span class="pill pill-warn">⚠️ ' + T('rilevato, esegui il comando', 'detected, run the command') + '</span>' : '<span class="pill pill-pub">➖ ' + T('non rilevato', 'not detected') + '</span>'));
        return `<div class="chk" style="justify-content:space-between;padding:8px 10px;border:1px solid var(--border);border-radius:8px;background:var(--card2);"><b>${h}</b>${badge}</div>`;
      }).join('');
      const stepN = (n, ok) => `<span class="pill ${ok ? 'pill-ok' : 'pill-warn'}" style="margin-right:6px;">${ok ? '✅' : n}</span>`;
      const allLinked = !ENV.public && names.filter((h) => (hs[h] || {}).detected).every((h) => (hs[h] || {}).linked);
      return `
        <div class="card">
          <h2>${stepN(1, allLinked)}${T('Un solo comando prepara tutto', 'One command sets everything up')}</h2>
          <p style="font-size:0.88rem;color:var(--muted);margin:0 0 10px;">${T('Incollalo nel terminale (Terminale su Mac/Linux, PowerShell o Prompt dei comandi su Windows). Crea la cartella <b>Documenti/Cortical</b>, collega gli harness che usi (con backup) e apre questa pagina.', 'Paste it in a terminal (Terminal on Mac/Linux, PowerShell or Command Prompt on Windows). It creates the <b>Documents/Cortical</b> folder, links the harnesses you use (with backup) and opens this page.')}</p>
          <pre style="margin:0 0 8px;">${esc(cliCmd('setup_cmd'))}</pre>
          <button class="btn btn-em" onclick="copyText(cliCmd('setup_cmd'))">📋 ${T('Copia comando', 'Copy command')}</button>
          <div class="grid" style="margin-top:12px;">${rows}</div>
        </div>
        <div class="card">
          <h2>${stepN(2, linked)}${T('Collega la cartella (1 clic)', 'Link the folder (1 click)')}</h2>
          <p style="font-size:0.88rem;color:var(--muted);margin:0 0 10px;">${T('Premi il pulsante: il selettore si apre già su <b>Documenti</b>. Scegli la cartella <b>Cortical</b> e conferma. Funziona uguale su Mac, Windows e Linux.', 'Press the button: the picker opens already on <b>Documents</b>. Choose the <b>Cortical</b> folder and confirm. Same on Mac, Windows and Linux.')}</p>
          ${FOLDER_WARN ? `<div class="alert err" style="display:block;">${esc(FOLDER_WARN)}</div>` : ''}
          ${linked ? `<div class="alert ok" style="display:block;">✅ ${T('Collegata', 'Linked')}: <b>${esc(DIR_HANDLE.name)}</b></div>`
            : `<button class="btn btn-primary" onclick="linkCorticalFolder()">📂 ${T('Scegli la cartella Cortical', 'Choose the Cortical folder')}</button>
               ${typeof window.showDirectoryPicker !== 'function' ? `<p style="font-size:0.82rem;color:var(--amber);">${T('Questo browser non può collegare cartelle (usa Chrome, Edge o Arc).', 'This browser cannot link folders (use Chrome, Edge or Arc).')}</p>` : ''}`}
        </div>
        ${modelCard()}
        <div class="card">
          <h2>${stepN(4, ITEMS.length > 0)}${T('Carica il primo file', 'Add your first file')}</h2>
          <button class="btn btn-primary" onclick="TAB='vault'; render();">🛡️ ${T('Apri Privacy Vault', 'Open Privacy Vault')}</button>
        </div>`;
    }

    function highlightOriginal(text, raws, kept) {
      const keepLo = new Set((kept || []).map((k) => k.toLowerCase()));
      const list = Array.from(new Set(raws)).filter((r) => r && r.length > 1).sort((a, b) => b.length - a.length);
      let html = esc(text);
      if (!list.length) return html;
      const rx = new RegExp(list.map((r) => esc(r).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|'), 'gi');
      return html.replace(rx, (m) => {
        const raw = m.replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"');
        const k = keepLo.has(raw.toLowerCase());
        return `<mark class="${k ? 'kept' : 'hit'}" data-raw="${esc(raw)}" onclick="toggleKeep(this.dataset.raw)" title="${T('Clic: ' + (k ? 'oscura di nuovo' : 'non oscurare'), 'Click: ' + (k ? 'mask again' : 'do not mask'))}">${m}</mark>`;
      });
    }

    function renderReview(L) {
      if (!INSPECT) return '';
      let origBlock = '';
      if (ORIG && ORIG.text) {
        const all = sanitizeTextClient(ORIG.text, INSPECT.profile, ORIG.marks || [], []);
        const raws = Object.values(all.mapping || {}).concat(ORIG.marks || []);
        origBlock = `<div style="font-size:0.8rem;color:var(--muted);margin:10px 0 4px;">${T('Originale (resta solo in questo browser). Evidenziato = verrà oscurato; clic su un evidenziato per NON oscurarlo; seleziona del testo per oscurarlo.', 'Original (stays in this browser only). Highlighted = will be masked; click a highlight to NOT mask it; select text to mask it.')}</div>
          <div id="rv-orig" class="rv">${highlightOriginal(ORIG.text, raws, ORIG.keep || [])}</div>`;
      } else if (ORIG && ORIG.kind === 'image') {
        origBlock = `<div style="font-size:0.8rem;color:var(--muted);margin:10px 0 4px;">${T('Immagine: per correggere i riquadri ricaricala dall\'inizio; qui puoi oscurare altre parole del testo estratto selezionandole.', 'Image: to fix boxes, upload it again; here you can mask more words of the extracted text by selecting them.')}</div>`;
      }
      return `
        <div class="card" style="border-color:var(--accent);">
          <h2>${L.drawerTitle}: <code>${esc(INSPECT.uri)}</code></h2>
          <p style="font-size:0.82rem;color:var(--muted);margin:0 0 10px;">File: <b>${esc(INSPECT.source_name)}</b> · ${esc(INSPECT.resolved_policy)} · ${INSPECT.local_only ? '🔒 SOLO LOCALE' : '🛡️ PRONTO PER CHAT'} · ${INSPECT.tokens_est || 0} tok</p>
          <div class="grid" style="margin-bottom:10px;">
            <label>${T('Livello privacy', 'Privacy level')}
              <select id="re-profile">
                <option value="max_security" ${INSPECT.profile === 'max_security' ? 'selected' : ''}>max_security (🔒)</option>
                <option value="medium" ${INSPECT.profile === 'medium' ? 'selected' : ''}>medium (🛡️)</option>
                <option value="low" ${INSPECT.profile === 'low' ? 'selected' : ''}>low ([REDACTED])</option>
                <option value="max_context" ${INSPECT.profile === 'max_context' ? 'selected' : ''}>max_context (🌐)</option>
              </select></label>
            <label>${L.addTermsLbl}<input id="re-terms" placeholder="Nome Cognome, CF, Azienda..." /></label>
          </div>
          <div style="display:flex;gap:8px;flex-wrap:wrap;">
            <button class="btn" onmousedown="event.preventDefault()" onclick="addMarkFromSelection()">➕ ${T('Oscura la selezione', 'Mask selection')}</button>
            <button class="btn btn-em" onclick="applyCorrections()">✏️ ${L.applyUpdate}</button>
          </div>
          ${origBlock}
          <div style="font-size:0.8rem;color:var(--muted);margin:10px 0 4px;">${T('Risultato anonimizzato (seleziona per oscurare altro):', 'Anonymized result (select to mask more):')}</div>
          <div id="rv-san" class="rv">${esc(INSPECT.sanitized_content || '')}</div>
        </div>`;
    }

    function renderVaultPanel(L) {
      const total = ITEMS.length;
      const localCount = ITEMS.filter((i) => i.local_only).length;
      const chatCount = total - localCount;
      const profiles = [
        ['max_security', L.profMaxSec, L.profMaxSecDesc], ['medium', L.profMed, L.profMedDesc],
        ['low', L.profLow, L.profLowDesc], ['max_context', L.profPub, L.profPubDesc],
      ];
      const profCards = profiles.map(([k, tit, desc]) => `
        <label class="prof-opt ${SEL_PROFILE === k ? 'sel' : ''}" onclick="SEL_PROFILE='${k}'; render();">
          <input type="radio" name="prof" value="${k}" ${SEL_PROFILE === k ? 'checked' : ''} />
          <span><strong>${esc(tit)}</strong><br/><span style="font-size:0.75rem;color:var(--muted);">${esc(desc)}</span></span></label>`).join('');
      const rows = ITEMS.map((it) => {
        const badge = it.local_only ? '<span class="pill pill-warn">🔒 SOLO LOCALE</span>'
          : (it.profile === 'max_context' ? '<span class="pill pill-pub">🌐 PUBBLICO</span>' : '<span class="pill pill-ok">🛡️ SICURO PER CHAT</span>');
        const copyBtn = it.local_only
          ? `<button class="btn" disabled title="${esc(L.localTip)}">${L.copyBtn}</button><button class="btn btn-em" onclick="copyLocalUse('${esc(it.alias)}')">🤖 ${T('Usa in Locale', 'Run Locally')}</button>`
          : `<button class="btn" onclick="copyAliasRef('${esc(it.alias)}')">${L.copyBtn}</button>`;
        return `<tr><td>${badge}</td><td><code>@private:${esc(it.alias)}</code></td><td>${esc(it.source_name)}</td><td>${esc(it.resolved_policy)} / ${esc(it.profile)}</td><td>${it.entity_count || 0}</td><td>${it.tokens_est || 0}</td>
          <td style="display:flex;gap:6px;flex-wrap:wrap;"><button class="btn" onclick="openInspect('${esc(it.alias)}')">${L.inspectBtn}</button>${copyBtn}
          <button class="btn" onclick="downloadOneVaultJson('${esc(it.alias)}')">${L.exportOneBtn}</button><button class="btn btn-danger" onclick="removeVaultItem('${esc(it.alias)}')">${L.delBtn}</button></td></tr>`;
      }).join('');
      const imgEd = IMGST ? `
        <div style="margin:12px 0;">
          <div style="font-size:0.84rem;color:var(--muted);margin-bottom:6px;">${T('Trascina sull\'immagine per coprire con un riquadro nero ciò che va nascosto (nomi, volti, targhe...). Il testo residuo lo anonimizza il modello locale.', 'Drag on the image to cover what must be hidden (names, faces, plates...). Remaining text is anonymized by the local model.')}</div>
          <canvas id="img-canvas" style="max-width:100%;border:1px solid var(--border);border-radius:8px;cursor:crosshair;"
            onmousedown="imgDown(event)" onmousemove="imgMove(event)" onmouseup="imgUp()" onmouseleave="imgUp()"></canvas>
          <div style="margin-top:6px;display:flex;gap:8px;align-items:center;"><button class="btn" onclick="imgUndo()">↩️ ${T('Annulla ultimo riquadro', 'Undo last box')}</button><span style="font-size:0.8rem;color:var(--muted);">${IMGST.rects.length} ${T('riquadri', 'boxes')}</span></div>
        </div>` : '';
      return `
        ${queueCard()}
        <div class="card">
          <h2>${L.uploadTitle}</h2>
          <div class="dropzone" onclick="document.getElementById('v-file').click()"
               ondragover="event.preventDefault(); this.classList.add('drag');" ondragleave="this.classList.remove('drag');"
               ondrop="event.preventDefault(); this.classList.remove('drag'); pickFileObj(event.dataTransfer.files[0]);">
            <div>${SELECTED_FILE ? ('📄 ' + esc(SELECTED_FILE.name) + ' (' + Math.max(1, Math.round(SELECTED_FILE.size / 1024)) + ' KB)') : esc(L.dropHint)}</div>
            <input type="file" id="v-file" style="display:none;" accept=".pdf,.docx,.xlsx,.pptx,.txt,.md,.json,.csv,.log,.png,.jpg,.jpeg,.webp" onchange="pickFileObj(this.files[0])" />
          </div>
          ${imgEd}
          <div class="prof-grid">${profCards}</div>
          <div class="grid">
            <label>${L.aliasLbl}<input id="v-alias" placeholder="alsa" value="${esc(DRAFT.alias)}" oninput="DRAFT.alias=this.value;" /></label>
            <label>${L.policyLbl}<select id="v-policy" onchange="DRAFT.policy=this.value;"><option value="auto" ${DRAFT.policy==='auto'?'selected':''}>auto</option><option value="fail_closed" ${DRAFT.policy==='fail_closed'?'selected':''}>fail_closed</option><option value="fail_open" ${DRAFT.policy==='fail_open'?'selected':''}>fail_open</option></select></label>
            <label>${L.termsLbl}<input id="v-terms" placeholder="Mario Rossi, Azienda Srl..." value="${esc(DRAFT.terms)}" oninput="DRAFT.terms=this.value;" /></label>
          </div>
          <div style="margin-top:12px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;">
            <span style="font-size:0.8rem;color:var(--muted);">${useModel() ? '🧠 ' + T('Modello locale attivo: ', 'Local model on: ') + esc((CFG.privacy || {}).ner_model || 'default') : '⚡ ' + T('Solo regole veloci nel browser', 'Quick browser rules only')}</span>
            <button class="btn btn-primary" onclick="processSelectedFile()">${L.uploadBtn}</button>
          </div>
        </div>
        ${modelCard()}
        <div class="card">
          <h2>${L.vaultListTitle}</h2>
          <div class="stats"><div class="stat-box">${L.tot}: <b>${total}</b></div><div class="stat-box">${L.lockOnly}: <b>${localCount}</b></div><div class="stat-box">${L.chatReady}: <b>${chatCount}</b></div></div>
          ${ITEMS.length === 0 ? `<p style="color:var(--muted);">${L.emptyVault}</p>` : `<div style="overflow-x:auto;"><table>
            <thead><tr><th>Privacy</th><th>Alias</th><th>File</th><th>Policy / Profilo</th><th>Entità</th><th>Tok</th><th>Azioni</th></tr></thead><tbody>${rows}</tbody></table></div>`}
        </div>
        ${renderReview(L)}`;
    }

    function renderModelsPanel(L) {
      const models = allModels();
      const cls = HW.classification || {};
      const rows = models.map((m) => `
        <tr>
          <td><strong><code>${esc(m.model_id)}</code></strong><br/><span style="font-size:0.75rem;color:var(--muted);">${esc(m.quantization)} ${m.is_variable_quant ? '· VarQuant' : ''}</span></td>
          <td>${Number(m.memory_gb || 0).toFixed(1)} GB</td>
          <td>${Number(m.native_ctx || 32768).toLocaleString()}</td>
          <td>${(m.roles || []).join(', ')}</td>
          <td><code>${esc(m.pull_ref)}</code></td>
          <td>
            <button class="btn" onclick="assignRoleModel('daily_coder','${esc(m.model_id)}')">Set Daily</button>
            <button class="btn" onclick="assignRoleModel('deep_reasoner','${esc(m.model_id)}')">Set Reasoner</button>
            ${m.custom ? `<button class="btn btn-danger" onclick="removeCustomModel('${esc(m.model_id)}')">🗑️</button>` : ''}
          </td>
        </tr>`).join('');

      return `
        <div class="card">
          <h2>Hardware &amp; Model Selector</h2>
          <p style="margin:0 0 10px;color:var(--muted);font-size:0.86rem;">
            Profile: <span class="pill pill-ok">${esc(cls.label || cls.tier || 'Variable Hardware')}</span> ·
            RAM: <b>${HW.total_ram_gb} GB</b> · VRAM: <b>${HW.vram_gb} GB</b> (${HW.unified_memory ? 'Unified' : 'Discrete'})
          </p>
          <div class="grid" style="margin-bottom:12px;">
            <label>Active Runner
              <select onchange="CFG.active_runner=this.value; render();">
                ${Object.keys(CFG.runners || {ollama:{}}).map((r) => `<option value="${r}" ${CFG.active_runner===r?'selected':''}>${r}</option>`).join('')}
              </select>
            </label>
            <label>Router/NER Model (1.5B-3B)
              <input value="${esc((CFG.models_by_role||{}).router || 'qwen2.5:1.5b')}" oninput="CFG.models_by_role.router=this.value; CFG.models_by_role.ner=this.value;" />
            </label>
            <label>Daily Coder Model
              <input value="${esc((CFG.models_by_role||{}).daily_coder || 'qwen3.5:9b-q3_k_xl')}" oninput="CFG.models_by_role.daily_coder=this.value;" />
            </label>
            <label>Deep Reasoner (27B 4-bit XXS)
              <input value="${esc((CFG.models_by_role||{}).deep_reasoner || 'qwen3.8:27b-q4_xxs')}" oninput="CFG.models_by_role.deep_reasoner=this.value; CFG.models_by_role.orchestrator=this.value;" />
            </label>
          </div>
          <table>
            <thead><tr><th>Model &amp; Quantization</th><th>Footprint</th><th>Native Ctx</th><th>Roles</th><th>Download Cmd</th><th>Actions</th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
        <div class="card">
          <h2>${L.addModelBtn}</h2>
          <div class="grid">
            <label>Model ID<input id="cm-id" placeholder="e.g. qwen3.8:27b-q4_xxs" /></label>
            <label>Runner<select id="cm-runner"><option value="ollama">ollama</option><option value="unsloth">unsloth</option><option value="llama_cpp">llama_cpp</option><option value="mlx_lm">mlx_lm</option></select></label>
            <label>Memory (GB)<input id="cm-mem" type="number" step="0.1" value="8.1" /></label>
            <label>Native Context<input id="cm-ctx" type="number" step="1024" value="32768" /></label>
            <label>Quantization<input id="cm-quant" value="Unsloth Variable 4-bit XXS" /></label>
            <label>Roles (comma-sep)<input id="cm-roles" value="deep_reasoner, orchestrator" /></label>
            <label>Pull Command<input id="cm-pull" placeholder="ollama pull ..." /></label>
            <label>Notes<input id="cm-notes" placeholder="Runs cleanly on 16GB unified RAM" /></label>
          </div>
          <label class="chk" style="margin:10px 0;"><input id="cm-var" type="checkbox" checked /> Variable / Dynamic Unsloth Quantization</label>
          <button class="btn btn-primary" onclick="addCustomModelFromForm()">${L.addModelBtn}</button>
        </div>`;
    }

    function renderHarnessesPanel() {
      const hKeys = Object.keys(PRESEND);
      const hCards = hKeys.map((h) => `
        <label class="chk" style="justify-content:space-between; padding:8px 10px; border:1px solid var(--border); border-radius:8px; background:var(--card2);">
          <span><input type="checkbox" ${(CFG.harnesses||{})[h]!==false?'checked':''} onchange="CFG.harnesses=CFG.harnesses||{}; CFG.harnesses['${h}']=this.checked;" /> <b>${h}</b></span>
          <span class="pill ${PRESEND[h]?'pill-ok':'pill-warn'}">${PRESEND[h] ? 'Pre-Send Safe' : 'Vault UI Only'}</span>
        </label>`).join('');
      const cCards = Object.keys(CFG.composers || {}).map((k) => `
        <label class="chk"><input type="checkbox" ${CFG.composers[k]?'checked':''} onchange="CFG.composers['${k}']=this.checked;" /> <code>${k}</code></label>`).join('');
      const r = CFG.router || {};
      return `
        <div class="card">
          <h2>Composed External Tools &amp; Optional Router</h2>
          <div class="grid" style="margin-bottom:12px;">${cCards}</div>
          <div style="border-top:1px solid var(--border); padding-top:12px;" class="grid">
            <label class="chk"><input type="checkbox" ${r.enabled?'checked':''} onchange="CFG.router.enabled=this.checked;" /> Enable Optional Router (70-90% API Offload)</label>
            <label>Provider<select onchange="CFG.router.provider=this.value;"><option value="litellm" ${r.provider==='litellm'?'selected':''}>LiteLLM</option><option value="omniroute" ${r.provider==='omniroute'?'selected':''}>OmniRoute</option><option value="ccr" ${r.provider==='ccr'?'selected':''}>claude-code-router</option></select></label>
            <label>Base URL<input value="${esc(r.base_url||'http://127.0.0.1:4000/v1')}" oninput="CFG.router.base_url=this.value;" /></label>
          </div>
        </div>
        <div class="card">
          <h2>8 Harness Sync Targets (macOS · Linux · Windows)</h2>
          <div class="grid">${hCards}</div>
          <pre style="margin-top:12px;">PYTHONPATH=src .venv/bin/python -m cortical.cli sync --dry-run
PYTHONPATH=src .venv/bin/python -m cortical.cli sync</pre>
        </div>`;
    }

    function renderBrainPanel() {
      const b = BRAIN_DATA || { stats: { files: 0, concepts: 0, skills: 0, tasks: 0 }, by_concept: [], by_task: [], by_file: [], by_skill: [] };
      const st = b.stats || {};
      const views = [
        ['concept', T('📚 Per Argomento / Concetto', '📚 By Topic / Concept')],
        ['task', T('📌 Per Task', '📌 By Task')],
        ['file', T('📄 Per File (3+1)', '📄 By File (3+1)')],
        ['skill', T('⚡ Skill Fattorizzate', '⚡ Factorized Skills')],
      ];
      const nav = views.map(([k, lbl]) => `<button class="btn ${BRAIN_VIEW===k?'btn-primary':''}" onclick="BRAIN_VIEW='${k}'; render();">${lbl}</button>`).join('');
      let content = '';
      if (BRAIN_VIEW === 'concept') {
        content = (b.by_concept || []).length === 0 ? `<p style="color:var(--muted);">${T('Nessun concetto distillato ancora. Carica un file nel Vault.', 'No concepts distilled yet. Upload a file to Vault.')}</p>` :
          (b.by_concept || []).map((c) => `<div style="border-bottom:1px solid var(--border);padding:10px 0;">
            <b>${esc(c.title)}</b> <span style="font-size:0.76rem;color:var(--muted);">(${(c.sources||[]).map(s=>'@private:'+s).join(', ')})</span>
            <div style="font-size:0.84rem;color:var(--muted);margin-top:4px;">${esc(c.summary)}</div>
            <div style="margin-top:4px;">${(c.keywords||[]).map(k=>`<span class="pill pill-pub" style="margin-right:4px;">${esc(k)}</span>`).join('')}</div>
          </div>`).join('');
      } else if (BRAIN_VIEW === 'task') {
        content = (b.by_task || []).length === 0 ? `<p style="color:var(--muted);">${T('Nessun task associato.', 'No tasks linked yet.')}</p>` :
          (b.by_task || []).map((t) => `<div style="border-bottom:1px solid var(--border);padding:10px 0;"><b>📌 ${esc(t.task)}</b>
            <ul>${(t.concepts||[]).map(c=>`<li><b>${esc(c.title)}</b> (${(c.sources||[]).join(', ')})</li>`).join('')}</ul></div>`).join('');
      } else if (BRAIN_VIEW === 'file') {
        const tierBtns = [['l1','L1 Light'],['l2','L2 Medium'],['l3','L3 High'],['max','Max (Raw/Anon)']].map(([tk,tl])=>`<button class="btn ${BRAIN_FILE_TIER===tk?'btn-primary':''}" onclick="BRAIN_FILE_TIER='${tk}'; render();">${tl}</button>`).join('');
        content = `<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px;">${tierBtns}</div>` +
          ((b.by_file || []).map((f) => {
            const tr = f.tiers || {};
            let snippet = BRAIN_FILE_TIER === 'l1' ? tr.tier_light : (BRAIN_FILE_TIER === 'l2' ? tr.tier_medium : (BRAIN_FILE_TIER === 'l3' ? tr.tier_high : ((ITEMS.find(x=>x.alias===f.alias)||{}).sanitized_content || '')));
            return `<div style="border-bottom:1px solid var(--border);padding:10px 0;">
              <b>@private:${esc(f.alias)}</b> · <span>${esc(f.source_name)}</span> · <span class="pill ${f.profile==='max_context'?'pill-pub':'pill-ok'}">${f.profile==='max_context'?'Max = RAW':'Max = ANONIMIZZATO'}</span>
              <pre style="margin-top:6px;">${esc(snippet || T('(carica/sincronizza per vedere)', '(load/sync to view)'))}</pre>
            </div>`;
          }).join('') || `<p style="color:var(--muted);">${T('Nessun file.', 'No files.')}</p>`);
      } else {
        content = (b.by_skill || []).length === 0 ? `<p style="color:var(--muted);">${T('Nessuna skill procedurale estratta dai file ancora.', 'No procedural skills extracted yet.')}</p>` :
          (b.by_skill || []).map((sk) => `<div style="border-bottom:1px solid var(--border);padding:10px 0;"><b>⚡ ${esc(sk.title)}</b> <span style="font-size:0.76rem;color:var(--muted);">(${(sk.sources||[]).join(', ')})</span>
            <pre style="margin-top:6px;">${esc(sk.procedure_md)}</pre></div>`).join('');
      }
      return `
        <div class="card">
          <h2>🧠 ${T('Local Brain (3+1 & Conoscenza Fattorizzata)', 'Local Brain (3+1 & Factorized Knowledge)')}</h2>
          <div class="stats">
            <div class="stat-box">File: <b>${st.files||0}</b></div><div class="stat-box">${T('Concetti','Concepts')}: <b>${st.concepts||0}</b></div>
            <div class="stat-box">Skill: <b>${st.skills||0}</b></div><div class="stat-box">Task: <b>${st.tasks||0}</b></div>
          </div>
          <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;">${nav}</div>
          ${content}
        </div>`;
    }

    function renderCompressionPanel() {
      const c = CFG.compression || {};
      const rep = CFG.report || {};
      const rt = CFG.routing || { mode: 'auto', cloud_token_threshold: 50000, cloud_budget_tokens: 200000 };
      const rState = ROI_DATA || {};
      const ct = (rState.roi || {}).current_turn || {};
      const loc = ct.local || {};
      const rem = ct.remote || {};
      return `
        <div class="card">
          <h2>🔀 ${T('Switch Modello LLM & Soglia Token Cloud', 'LLM Routing Switch & Cloud Token Threshold')}</h2>
          <p style="font-size:0.84rem;color:var(--muted);margin:0 0 10px;">
            ${T('Gli harness con hook/baseURL (pi, OpenCode, OpenClaw, Codex, Claude Code, dsh) instradano in automatico verso Ollama sotto soglia; su Antigravity le regole condivise indicano di delegare a cortical_local_offload.', 'Harnesses with hooks/baseURL (pi, OpenCode, OpenClaw, Codex, Claude Code, dsh) route automatically to Ollama below threshold; on Antigravity shared rules trigger cortical_local_offload.')}
          </p>
          <div class="grid">
            <label>${T('Modalità LLM', 'LLM Mode')}
              <select onchange="CFG.routing=CFG.routing||{}; CFG.routing.mode=this.value; persistConfigToFolder(); render();">
                <option value="auto" ${rt.mode==='auto'?'selected':''}>Auto / Misto (Local sotto soglia)</option>
                <option value="full_local" ${rt.mode==='full_local'?'selected':''}>Full Local (Sempre Ollama)</option>
                <option value="cloud_first" ${rt.mode==='cloud_first'?'selected':''}>Cloud First</option>
              </select>
            </label>
            <label>${T('Soglia Token Cloud Residui (passa a Locale sotto)', 'Remaining Cloud Token Threshold')}
              <input type="number" step="5000" value="${rt.cloud_token_threshold ?? 50000}" oninput="CFG.routing=CFG.routing||{}; CFG.routing.cloud_token_threshold=Number(this.value||50000); persistConfigToFolder();" />
            </label>
            <label>${T('Budget Sessione Cloud (Token)', 'Cloud Session Budget (Tokens)')}
              <input type="number" step="10000" value="${rt.cloud_budget_tokens ?? 200000}" oninput="CFG.routing=CFG.routing||{}; CFG.routing.cloud_budget_tokens=Number(this.value||200000); persistConfigToFolder();" />
            </label>
          </div>
          ${rState.effective_mode ? `<div class="alert info" style="display:block;margin-top:10px;">Stato attuale: <b>${esc(rState.effective_mode)}</b> — ${esc(rState.reason)}</div>` : ''}
        </div>
        <div class="card">
          <h2>📊 ${T('Report Uso Local LLM vs Remote Cloud (0 Token Cloud)', 'Local LLM vs Remote Cloud Usage Report')}</h2>
          <div class="stats">
            <div class="stat-box">Local Runs: <b>${loc.run_count||0}</b></div>
            <div class="stat-box">Local Tokens: <b>${(loc.total_tokens||0).toLocaleString()}</b></div>
            <div class="stat-box">Offload Share: <b>${ct.offload_share_pct||0}%</b></div>
            <div class="stat-box">USD Saved Est: <b>$${Number(loc.usd_saved_est||0).toFixed(2)}</b></div>
            <div class="stat-box">Remote Turn Active: <b>${(rem.active_tokens||0).toLocaleString()}</b></div>
          </div>
          <p style="font-size:0.78rem;color:var(--muted);margin:0;">${T('Aggiornato da roi.json in ~/Documents/Cortical/ quando esegui cortical-mcp o setup.', 'Updated from roi.json in ~/Documents/Cortical/ when cortical-mcp or setup runs.')}</p>
        </div>
        <div class="card">
          <h2>🗜️ Deterministic Compression (TOON) &amp; Auto-Sizing</h2>
          <div class="grid">
            <label class="chk"><input type="checkbox" ${c.enable_toon!==false?'checked':''} onchange="CFG.compression.enable_toon=this.checked;" /> Enable Lossless TOON Encoder</label>
            <label>Minimum TOON Saving Guard (%)<input type="number" step="1" value="${c.min_toon_saving_pct ?? 10}" oninput="CFG.compression.min_toon_saving_pct=Number(this.value||10);" /></label>
            <label>Max Memory Context Share<input type="number" step="0.01" value="${c.max_context_share ?? 0.15}" oninput="CFG.compression.max_context_share=Number(this.value||0.15);" /></label>
            <label>Report Language<select onchange="CFG.report.language=this.value;"><option value="auto" ${rep.language==='auto'?'selected':''}>auto</option><option value="en" ${rep.language==='en'?'selected':''}>English</option><option value="it" ${rep.language==='it'?'selected':''}>Italiano</option></select></label>
          </div>
        </div>`;
    }

    function render() {
      const L = I18N[LANG] || I18N.en;
      const body = TAB === 'setup' ? renderSetupPanel(L) : TAB === 'vault' ? renderVaultPanel(L) : TAB === 'brain' ? renderBrainPanel() : (TAB === 'models' ? renderModelsPanel(L) : (TAB === 'harnesses' ? renderHarnessesPanel() : renderCompressionPanel()));
      const sidebar = Object.entries(L.tabs).map(([k, lbl]) => `<button class="tab ${TAB===k?'active':''}" onclick="TAB='${k}'; render();">${lbl}</button>`).join('');
      const syncStatus = DIR_HANDLE
        ? (NEEDS_REAUTH
            ? `<span>${esc(L.syncLinked)}<b>${esc(DIR_HANDLE.name)}</b></span><button class="btn btn-primary" onclick="reauthorizeFolder()">${L.reconnectBtn}</button>`
            : `<span style="color:var(--emerald);">✅ ${esc(L.syncLinked)}<b>${esc(DIR_HANDLE.name)}</b></span><button class="btn" onclick="syncFolderAndDb()">↻ Sync Vault</button>`)
        : `<span style="color:var(--muted);">${esc(L.syncUnset)}</span><button class="btn btn-primary" onclick="TAB='setup'; render();">🚀 ${LANG==='it'?'Guida al collegamento':'Linking guide'}</button>`;

      document.getElementById('app').innerHTML = `
        <div class="top">
          <div>
            <h1>${L.title}</h1>
            <div style="font-size:0.84rem;color:var(--muted);">${L.sub}</div>
          </div>
          <div style="display:flex; gap:8px; flex-wrap:wrap;">
            <button class="btn" onclick="LANG=LANG==='en'?'it':'en'; localStorage.setItem('cortical_lang',LANG); render();">${LANG==='it'?'🇮🇹 IT':'🇬🇧 EN'}</button>
            <label class="btn" style="flex-direction:row;cursor:pointer;">📂 <span>${L.import}</span><input type="file" accept=".json" onchange="importCfg(event)" style="display:none;" /></label>
            <button class="btn" onclick="downloadCfg()">⬇️ ${L.download}</button>
            <button class="btn btn-em" onclick="saveCfg()">💾 ${L.save}</button>
          </div>
        </div>
        <div class="sync-bar">${syncStatus}</div>
        <div class="alert ${BANNER.kind}" style="${BANNER.text ? 'display:block;' : 'display:none;'}">${esc(BANNER.text)}</div>
        <div class="layout">
          <aside class="sidebar">${sidebar}</aside>
          <main>${body}</main>
        </div>`;
      if (IMGST) drawImg();
    }
    setInterval(() => { if (QUEUE.some((q) => !q.error) && linkedOk() && !document.hidden) { const prev = ITEMS.length; syncFolderAndDb(true).then(() => { if (ITEMS.length !== prev) setBanner('ok', T('Elaborazione locale completata.', 'Local processing completed.')); }); } }, 4000);

    window.saveCfg = async function() {
      const txt = JSON.stringify(CFG, null, 2) + '\n';
      if (window.showSaveFilePicker) {
        try {
          const h = await window.showSaveFilePicker({ suggestedName: 'cortical.config.json', types: [{ description: 'JSON', accept: { 'application/json': ['.json'] } }] });
          const w = await h.createWritable();
          await w.write(txt);
          await w.close();
          setBanner('ok', 'Configurazione salvata su disco.');
          return;
        } catch (e) { if (e.name === 'AbortError') return; }
      }
      window.downloadCfg();
    };
    window.downloadCfg = function() {
      const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([JSON.stringify(CFG, null, 2) + '\n'], { type: 'application/json' }));
      a.download = 'cortical.config.json';
      a.click();
    };
    window.importCfg = function(ev) {
      const f = ev.target.files?.[0];
      if (!f) return;
      f.text().then((t) => { CFG = JSON.parse(t); setBanner('ok', 'Configurazione importata.'); });
    };

    (async function boot() {
      try {
        const saved = await idbLoadHandle();
        if (saved) {
          DIR_HANDLE = saved;
          const p = await saved.queryPermission({ mode: 'readwrite' });
          NEEDS_REAUTH = (p !== 'granted');
        }
      } catch {}
      await syncFolderAndDb();
    })();
  </script>
</body>
</html>
"""


def render_static_settings_html(
    cfg: Optional[dict[str, Any]] = None,
    hw: Optional[dict[str, Any]] = None,
    public_docs: bool = False,
    env: Optional[dict[str, Any]] = None,
) -> str:
    """Renders Zero-Server Static Privacy Vault + Model/Harness Configurator HTML."""
    data = copy.deepcopy(cfg) if cfg is not None else (copy.deepcopy(DEFAULT_CONFIG) if public_docs else load_cortical_config())
    hw_snap = copy.deepcopy(hw) if hw is not None else {
        "os": "cross-platform",
        "total_ram_gb": 16.0,
        "vram_gb": 4.0,
        "unified_memory": False,
        "classification": {"tier": "tier_1a_hybrid_laptop", "label": "Tier 1A · Hybrid / Variable"},
    }
    html = _SETTINGS_TEMPLATE
    html = html.replace("__NAV__", _nav_links(is_help=False, public_docs=public_docs))
    html = html.replace("__CFG_JSON__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    html = html.replace("__HW_JSON__", json.dumps(hw_snap, ensure_ascii=False).replace("</", "<\\/"))
    html = html.replace("__CATALOG_JSON__", json.dumps(BUILTIN_MODEL_CATALOG, ensure_ascii=False).replace("</", "<\\/"))
    env_data = env if env is not None else build_dashboard_env(public=public_docs)
    html = html.replace("__ENV_JSON__", json.dumps(env_data, ensure_ascii=False).replace("</", "<\\/"))
    html = html.replace("__PRESEND_JSON__", json.dumps(get_harness_presend_matrix(), ensure_ascii=False).replace("</", "<\\/"))
    return html


def render_static_help_html(public_docs: bool = False) -> str:
    """Renders bilingual (EN/IT) documentation for Cortical's Zero-Server Privacy Vault, Models & Compression."""
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
  </style>
</head>
<body>
  <div class="wrap">
    <div class="top">
      <div>
        <h1 id="ht">❓ Cortical Reference &amp; Zero-Server Guide</h1>
        <div style="font-size:0.84rem;color:var(--muted);">{nav}</div>
      </div>
      <button class="btn" id="hl" onclick="LANG=LANG==='en'?'it':'en'; localStorage.setItem('cortical_lang',LANG); applyL();">🇬🇧 EN</button>
    </div>
    <div id="c-en">
      <div class="card"><h2>1. 100% Zero-Server Privacy Vault (settings.html)</h2><p>Open <code>settings.html</code> with zero background daemons or open ports. Drop PDF, DOCX, XLSX, PPTX, TXT or JSON files to anonymize them client-side, manage both <code>🔒 Local-Only (max_security)</code> and <code>🛡️ Chat-Ready (@private:&lt;alias&gt;)</code> items, and link your <code>.cortical_data</code> folder via File System Access API for automatic sync with MCP/CLI.</p></div>
      <div class="card"><h2>2. Hardware Preflight &amp; Variable-Quantization Models</h2><p>Supports macOS, Linux &amp; Windows across Tier 1A (<code>16 GB RAM + 4 GB VRAM</code>) and Tier 1B (<code>16 GB unified</code> with Unsloth variable <code>27B 4-bit XXS 8.1 GB</code>). Configure custom models directly inside <code>settings.html</code> or via <code>cortical models add</code>.</p></div>
      <div class="card"><h2>3. 8-Harness Sync &amp; Lossless TOON Compression</h2><p>Syncs Serena, RTK, PinchTab/Playwright, <code>context-mode</code>, optional Router, and auto-sized sanitized memory across Antigravity, pi, OpenCode, OpenClaw, Codex, Claude Code, DeepSeek Harness (<code>dsh</code>) &amp; Unsloth Studio.</p></div>
    </div>
    <div id="c-it" style="display:none;">
      <div class="card"><h2>1. Privacy Vault 100% Zero-Server (settings.html)</h2><p>Apri <code>settings.html</code> senza alcun servizio o porta aperta. Carica PDF, DOCX, XLSX, PPTX, TXT o JSON in locale nel browser, visualizza sempre sia i file <code>🔒 Solo Locale (max_security)</code> sia quelli pronti come <code>@private:&lt;alias&gt;</code>, e collega la cartella <code>.cortical_data</code> per sincronizzare automaticamente con gli agenti MCP.</p></div>
      <div class="card"><h2>2. Hardware Preflight &amp; Quantizzazione Variabile</h2><p>Supporta macOS, Linux e Windows inclusi laptop ibridi Tier 1A (<code>16 GB RAM + 4 GB VRAM</code>) e Tier 1B (<code>16 GB unificati</code> con <code>27B 4-bit XXS 8.1 GB</code>). Aggiungi nuovi modelli direttamente da <code>settings.html</code>.</p></div>
      <div class="card"><h2>3. Sync su 8 Harness &amp; Compressione TOON Lossless</h2><p>Configura Serena, RTK, PinchTab/Playwright, router opzionale e memoria anonimizzata sotto budget su Antigravity, pi, OpenCode, OpenClaw, Codex, Claude Code, <code>dsh</code> e Unsloth Studio.</p></div>
    </div>
  </div>
  <script>
    let LANG = localStorage.getItem('cortical_lang') || ((navigator.language || '').toLowerCase().startsWith('it') ? 'it' : 'en');
    function applyL() {{
      document.getElementById('c-en').style.display = LANG === 'en' ? 'block' : 'none';
      document.getElementById('c-it').style.display = LANG === 'it' ? 'block' : 'none';
      document.getElementById('hl').textContent = LANG === 'it' ? '🇮🇹 IT' : '🇬🇧 EN';
      document.getElementById('ht').textContent = LANG === 'it' ? '❓ Cortical Guida Zero-Server' : '❓ Cortical Reference & Zero-Server Guide';
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
    s_path.write_text(render_static_settings_html(cfg=config, hw=hw, public_docs=public_docs, env=build_dashboard_env(public=public_docs)), encoding="utf-8")
    h_path.write_text(render_static_help_html(public_docs=public_docs), encoding="utf-8")
    return (s_path, h_path)
