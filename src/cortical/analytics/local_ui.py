"""On-demand foreground loopback UI (`127.0.0.1` only) for Cortical Privacy Vault, Models & 8 Harnesses."""

from __future__ import annotations

import base64
import json
import os
import re
import threading
import urllib.parse
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional

from ..config import DEFAULT_VAULT_DB, load_cortical_config, save_cortical_config
from ..harnesses.adapters import apply_sync, get_harness_presend_matrix, plan_sync
from ..hardware.models import list_all_models, recommend_models_for_hardware
from ..hardware.probe import probe_hardware
from ..privacy.sanitizer import FailClosedError
from ..privacy.vault import PrivacyVault

MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB limit per file

_LOCAL_UI_HTML = r"""<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Cortical — Privacy Vault &amp; Control Plane</title>
  <style>
    :root {
      --bg:#080d1a; --surface:#0f172a; --card:#151f33; --card2:#0c1322; --border:#24324a;
      --text:#e2e8f0; --muted:#94a3b8; --accent:#38bdf8; --emerald:#34d399; --amber:#fbbf24; --danger:#f87171;
    }
    * { box-sizing:border-box; }
    body { margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; background:var(--bg); color:var(--text); line-height:1.5; }
    .wrap { max-width:1120px; margin:0 auto; padding:20px; }
    .top { display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px; padding-bottom:14px; border-bottom:1px solid var(--border); margin-bottom:16px; }
    h1 { margin:0; font-size:1.35rem; display:flex; align-items:center; gap:8px; }
    h2 { margin:0 0 10px; font-size:1.05rem; color:var(--accent); }
    .tabs { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:16px; }
    .tab { padding:8px 14px; border-radius:8px; border:1px solid var(--border); background:var(--surface); color:var(--muted); cursor:pointer; font-weight:600; font-size:0.88rem; }
    .tab.active { background:var(--accent); color:#082f49; border-color:var(--accent); }
    .card { background:var(--surface); border:1px solid var(--border); border-radius:12px; padding:16px; margin-bottom:14px; }
    .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:12px; }
    label { display:flex; flex-direction:column; gap:5px; font-size:0.82rem; color:var(--muted); }
    input,select,textarea { width:100%; border-radius:8px; border:1px solid var(--border); background:#060a14; color:var(--text); padding:8px 10px; font-size:0.86rem; font-family:inherit; }
    .btn { display:inline-flex; align-items:center; gap:6px; border:1px solid var(--border); background:var(--card); color:var(--text); padding:7px 12px; border-radius:8px; cursor:pointer; font-weight:600; font-size:0.82rem; }
    .btn:hover:not(:disabled) { border-color:var(--accent); }
    .btn:disabled { opacity:0.45; cursor:not-allowed; }
    .btn-primary { background:var(--accent); color:#082f49; border-color:var(--accent); }
    .btn-em { background:rgba(52,211,153,0.16); color:var(--emerald); border-color:rgba(52,211,153,0.45); }
    .btn-danger { border-color:rgba(248,113,113,0.5); color:var(--danger); }
    .pill { display:inline-block; padding:2px 9px; border-radius:999px; font-size:0.74rem; font-weight:700; }
    .pill-lock { background:rgba(251,191,36,0.14); color:var(--amber); border:1px solid rgba(251,191,36,0.4); }
    .pill-safe { background:rgba(52,211,153,0.14); color:var(--emerald); border:1px solid rgba(52,211,153,0.4); }
    .pill-pub { background:rgba(56,189,248,0.14); color:var(--accent); border:1px solid rgba(56,189,248,0.4); }
    .prof-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:10px; margin:10px 0 12px; }
    .prof-opt { border:1px solid var(--border); background:var(--card2); border-radius:10px; padding:10px; cursor:pointer; display:flex; flex-direction:row; align-items:flex-start; gap:8px; color:var(--text); }
    .prof-opt.sel { border-color:var(--accent); background:rgba(56,189,248,0.09); }
    .prof-opt input { width:auto; margin-top:3px; }
    .dropzone { border:2px dashed var(--border); border-radius:10px; padding:16px; text-align:center; background:var(--card2); cursor:pointer; transition:border-color 0.2s; }
    .dropzone.drag { border-color:var(--accent); background:rgba(56,189,248,0.08); }
    .alert { padding:10px 14px; border-radius:8px; margin-bottom:12px; font-size:0.86rem; display:none; }
    .alert.ok { display:block; background:rgba(52,211,153,0.14); border:1px solid rgba(52,211,153,0.4); color:var(--emerald); }
    .alert.err { display:block; background:rgba(248,113,113,0.14); border:1px solid rgba(248,113,113,0.4); color:var(--danger); }
    .stats { display:flex; gap:10px; flex-wrap:wrap; margin-bottom:12px; font-size:0.84rem; }
    .stat-box { background:var(--card2); border:1px solid var(--border); padding:6px 12px; border-radius:8px; }
    table { width:100%; border-collapse:collapse; font-size:0.83rem; }
    th,td { text-align:left; padding:9px 8px; border-bottom:1px solid var(--border); vertical-align:middle; }
    th { color:var(--muted); }
    code { color:var(--emerald); background:#060a14; padding:2px 6px; border-radius:4px; }
    pre { background:#060a14; border:1px solid var(--border); border-radius:8px; padding:12px; white-space:pre-wrap; word-break:break-word; max-height:360px; overflow:auto; font-size:0.82rem; color:#cbd5e1; }
    .row-chk { flex-direction:row; align-items:center; gap:8px; cursor:pointer; color:var(--text); }
    .row-chk input { width:auto; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="top">
      <div>
        <h1>🛡️ Cortical <span style="font-size:0.85rem;color:var(--muted);font-weight:500;">Local Privacy Vault &amp; Control Plane</span></h1>
      </div>
      <div style="display:flex;gap:8px;align-items:center;">
        <button class="btn" id="lang-btn" onclick="toggleLang()"></button>
        <button class="btn" onclick="refreshAll()">↻ Refresh</button>
      </div>
    </div>

    <div class="tabs">
      <button class="tab active" id="tab-btn-vault" onclick="setTab('vault')"></button>
      <button class="tab" id="tab-btn-models" onclick="setTab('models')"></button>
      <button class="tab" id="tab-btn-harnesses" onclick="setTab('harnesses')"></button>
    </div>

    <div id="alert-box" class="alert"></div>
    <div id="main-content"></div>
  </div>

  <script>
    const TEXT = {
      it: {
        tabVault: '🛡️ Privacy Vault', tabModels: '🧠 Hardware & Modelli', tabHarnesses: '🔌 8 Harness',
        uploadTitle: 'Carica & Anonimizza File nel Privacy Vault (PDF, DOCX, XLSX, TXT, JSON, MD)',
        dropHint: 'Trascina un file qui o clicca per sceglierlo dal computer',
        aliasLbl: 'Alias Vault (es. alsa)',
        policyLbl: 'Policy Dinamica',
        termsLbl: 'Termini custom da oscurare (separati da virgola)',
        nerLbl: 'Usa NER Locale (Ollama 1.5B-3B) per nomi di persone e aziende',
        uploadBtn: '⬆️ Carica & Anonimizza',
        uploading: 'Elaborazione locale in corso...',
        profMaxSec: '🔒 Massima Privacy · Solo Locale',
        profMaxSecDesc: 'Salvato e visibile qui nel Vault; utilizzabile SOLO da LLM locali, BLOCCATO verso LLM cloud.',
        profMed: '🛡️ Anonimizzato per Chat',
        profMedDesc: 'Rimuove metadati, email, telefoni, IBAN, CF e termini custom; pronto come @private:<alias>.',
        profLow: '📋 Solo Riassunto Oscurato',
        profLowDesc: 'Sostituisce tutte le entità rilevate con [REDACTED] riducendo il testo esposto.',
        profPub: '🌐 Pubblico / Nessun Filtro',
        profPubDesc: 'Solo per documenti pubblici non sensibili (policy fail_open).',
        vaultTitle: 'Documenti nel Privacy Vault (Include file Solo Locale 🔒)',
        tot: 'Totale', lockOnly: '🔒 Solo Locale', chatReady: '🛡️ Pronti per Chat',
        emptyVault: 'Nessun file nel Privacy Vault. Carica ad es. alsa.pdf qui sopra.',
        previewBtn: '👁️ Anteprima', copyBtn: '📋 Copia @private:', delBtn: '🗑️ Elimina',
        drawerTitle: 'Ispezione & Affinamento Anonimizzazione',
        addTermsLbl: 'Oscura altri termini (nomi, CF, targhe, aziende...)',
        newProfLbl: 'Livello Privacy',
        applyUpdate: '✏️ Applica Anonimizzazione',
        localTip: 'Solo LLM locale: riferimento bloccato per chat cloud',
        copied: 'Copiato negli appunti: ',
      },
      en: {
        tabVault: '🛡️ Privacy Vault', tabModels: '🧠 Hardware & Models', tabHarnesses: '🔌 8 Harnesses',
        uploadTitle: 'Upload & Anonymize Files into Privacy Vault (PDF, DOCX, XLSX, TXT, JSON, MD)',
        dropHint: 'Drag a file here or click to pick from disk',
        aliasLbl: 'Vault Alias (e.g. alsa)',
        policyLbl: 'Dynamic Policy',
        termsLbl: 'Custom terms to mask (comma-separated)',
        nerLbl: 'Run Local JSON NER (Ollama 1.5B-3B) for person & org names',
        uploadBtn: '⬆️ Upload & Sanitize',
        uploading: 'Sanitizing locally...',
        profMaxSec: '🔒 Max Security · Local Only',
        profMaxSecDesc: 'Stored and visible right here in Vault; local LLMs ONLY, BLOCKED from cloud egress.',
        profMed: '🛡️ Anonymized for Chat',
        profMedDesc: 'Strips metadata, emails, phones, IBANs, tax IDs & custom terms; ready as @private:<alias>.',
        profLow: '📋 Redacted Summary',
        profLowDesc: 'Replaces sensitive entities with [REDACTED] markers.',
        profPub: '🌐 Public / No Filter',
        profPubDesc: 'Only for clean public docs (fail_open passthrough).',
        vaultTitle: 'Privacy Vault Items (Includes Local-Only Files 🔒)',
        tot: 'Total', lockOnly: '🔒 Local Only', chatReady: '🛡️ Chat Ready',
        emptyVault: 'Vault is empty. Upload a PDF/DOCX/TXT file above.',
        previewBtn: '👁️ Preview', copyBtn: '📋 Copy @private:', delBtn: '🗑️ Delete',
        drawerTitle: 'Inspect & Refine Sanitization',
        addTermsLbl: 'Mask extra terms (comma-separated)',
        newProfLbl: 'Privacy Profile',
        applyUpdate: '✏️ Apply Sanitization',
        localTip: 'Local LLM only: blocked from remote cloud chat',
        copied: 'Copied reference: ',
      }
    };

    let LANG = localStorage.getItem('cortical_lang') || ((navigator.language || '').toLowerCase().startsWith('it') ? 'it' : 'en');
    let TAB = 'vault';
    let ITEMS = [];
    let STATUS = null;
    let SYNC_PREVIEW = null;
    let SELECTED_FILE = null;
    let SEL_PROFILE = 'max_security';
    let INSPECT = null;

    function esc(s) {
      return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    }
    function L() { return TEXT[LANG] || TEXT.en; }
    function showAlert(msg, kind = 'ok') {
      const box = document.getElementById('alert-box');
      box.className = 'alert ' + kind;
      box.textContent = msg;
    }
    function clearAlert() {
      const box = document.getElementById('alert-box');
      box.className = 'alert';
      box.textContent = '';
    }
    function toggleLang() {
      LANG = LANG === 'it' ? 'en' : 'it';
      localStorage.setItem('cortical_lang', LANG);
      render();
    }
    function setTab(t) {
      TAB = t;
      clearAlert();
      render();
    }

    async function api(path, opts = {}) {
      const res = await fetch(path, opts);
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || ('HTTP ' + res.status));
      return data;
    }

    async function refreshVault() {
      const data = await api('/api/vault');
      ITEMS = data.items || [];
      render();
    }
    async function refreshStatus() {
      STATUS = await api('/api/status');
      render();
    }
    async function refreshAll() {
      clearAlert();
      const [v, s] = await Promise.all([api('/api/vault'), api('/api/status')]);
      ITEMS = v.items || [];
      STATUS = s;
      render();
    }

    function pickFileObj(file) {
      if (!file) return;
      SELECTED_FILE = file;
      const lbl = document.getElementById('drop-label');
      if (lbl) lbl.textContent = `📄 ${file.name} (${Math.max(1, Math.round(file.size / 1024))} KB)`;
      const al = document.getElementById('v-alias');
      if (al && !al.value.trim()) al.value = file.name.replace(/\.[^.]+$/, '');
    }

    function readFileBase64(file) {
      return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => {
          const s = String(reader.result || '');
          const idx = s.indexOf(',');
          resolve(idx >= 0 ? s.slice(idx + 1) : s);
        };
        reader.onerror = () => reject(reader.error || new Error('FileReader error'));
        reader.readAsDataURL(file);
      });
    }

    async function uploadVaultFile() {
      if (!SELECTED_FILE) {
        showAlert('Seleziona prima un file / Pick a file first.', 'err');
        return;
      }
      const btn = document.getElementById('btn-upload');
      const alias = (document.getElementById('v-alias')?.value || '').trim();
      const policy = document.getElementById('v-policy')?.value || 'auto';
      const rawTerms = document.getElementById('v-terms')?.value || '';
      const useNer = Boolean(document.getElementById('v-ner')?.checked);
      const customTerms = rawTerms.split(',').map((s) => s.trim()).filter(Boolean);
      try {
        if (btn) { btn.disabled = true; btn.textContent = L().uploading; }
        const b64 = await readFileBase64(SELECTED_FILE);
        const res = await api('/api/vault/upload', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            filename: SELECTED_FILE.name,
            content_base64: b64,
            alias: alias || null,
            policy,
            profile: SEL_PROFILE,
            custom_terms: customTerms,
            use_local_ner: useNer,
          }),
        });
        SELECTED_FILE = null;
        await refreshVault();
        await inspectItem(res.alias);
        showAlert(`OK: ${res.uri} (${res.profile} · ${res.entity_count} entità mascherate · ${res.tokens_est} tok)`, 'ok');
      } catch (err) {
        showAlert(String(err.message || err), 'err');
      } finally {
        if (btn) { btn.disabled = false; btn.textContent = L().uploadBtn; }
      }
    }

    async function inspectItem(alias) {
      try {
        INSPECT = await api('/api/vault/' + encodeURIComponent(alias));
        render();
      } catch (err) {
        showAlert(String(err.message || err), 'err');
      }
    }

    async function applyResanitize(alias) {
      const prof = document.getElementById('re-profile')?.value || 'medium';
      const rawTerms = document.getElementById('re-terms')?.value || '';
      const useNer = Boolean(document.getElementById('re-ner')?.checked);
      const customTerms = rawTerms.split(',').map((s) => s.trim()).filter(Boolean);
      try {
        const res = await api('/api/vault/' + encodeURIComponent(alias) + '/update', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ profile: prof, custom_terms: customTerms, use_local_ner: useNer }),
        });
        await refreshVault();
        await inspectItem(res.alias);
        showAlert(`Aggiornato @private:${res.alias} (${res.profile}, ${res.entity_count} entità)`, 'ok');
      } catch (err) {
        showAlert(String(err.message || err), 'err');
      }
    }

    async function deleteItem(alias) {
      try {
        await api('/api/vault/' + encodeURIComponent(alias), { method: 'DELETE' });
        if (INSPECT && INSPECT.alias === alias) INSPECT = null;
        await refreshVault();
        showAlert(`Eliminato: @private:${alias}`, 'ok');
      } catch (err) {
        showAlert(String(err.message || err), 'err');
      }
    }

    async function copyRef(alias) {
      const ref = '@private:' + alias;
      if (navigator.clipboard) await navigator.clipboard.writeText(ref).catch(() => {});
      showAlert(L().copied + ref, 'ok');
    }

    async function addCustomModel() {
      if (!STATUS || !STATUS.config) return;
      const cfg = JSON.parse(JSON.stringify(STATUS.config));
      const id = (document.getElementById('m-id')?.value || '').trim();
      if (!id) return showAlert('Inserisci Model ID', 'err');
      const entry = {
        model_id: id,
        runner: document.getElementById('m-runner')?.value || 'ollama',
        memory_gb: Number(document.getElementById('m-mem')?.value || 8.1),
        native_ctx: Number(document.getElementById('m-ctx')?.value || 32768),
        quantization: document.getElementById('m-quant')?.value || 'Variable Quant',
        is_variable_quant: Boolean(document.getElementById('m-var')?.checked),
        roles: (document.getElementById('m-roles')?.value || 'deep_reasoner').split(',').map((x) => x.trim()).filter(Boolean),
        pull_ref: 'ollama pull ' + id,
        notes: 'Configured via Cortical UI',
      };
      cfg.custom_models = (cfg.custom_models || []).filter((m) => m.model_id !== id);
      cfg.custom_models.push(entry);
      try {
        await api('/api/config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(cfg) });
        await refreshStatus();
        showAlert('Salvato modello custom: ' + id, 'ok');
      } catch (err) {
        showAlert(String(err.message || err), 'err');
      }
    }

    async function loadSyncPreview() {
      try {
        SYNC_PREVIEW = await api('/api/sync-preview');
        render();
      } catch (err) {
        showAlert(String(err.message || err), 'err');
      }
    }

    function renderVaultTab() {
      const t = L();
      const total = ITEMS.length;
      const localCount = ITEMS.filter((i) => i.local_only).length;
      const chatCount = total - localCount;
      const profiles = [
        ['max_security', t.profMaxSec, t.profMaxSecDesc],
        ['medium', t.profMed, t.profMedDesc],
        ['low', t.profLow, t.profLowDesc],
        ['max_context', t.profPub, t.profPubDesc],
      ];

      const profCards = profiles.map(([k, title, desc]) => `
        <label class="prof-opt ${SEL_PROFILE === k ? 'sel' : ''}" onclick="SEL_PROFILE='${k}'; render();">
          <input type="radio" name="prof" value="${k}" ${SEL_PROFILE === k ? 'checked' : ''} />
          <span><strong>${esc(title)}</strong><br/><span style="font-size:0.75rem;color:var(--muted);">${esc(desc)}</span></span>
        </label>`).join('');

      const rows = ITEMS.map((it) => {
        const badge = it.local_only
          ? '<span class="pill pill-lock">🔒 SOLO LOCALE</span>'
          : (it.profile === 'max_context' ? '<span class="pill pill-pub">🌐 PUBBLICO</span>' : '<span class="pill pill-safe">🛡️ SICURO PER CHAT</span>');
        const copyDis = it.local_only ? `disabled title="${esc(t.localTip)}"` : '';
        return `
          <tr>
            <td>${badge}</td>
            <td><code>@private:${esc(it.alias)}</code></td>
            <td>${esc(it.source_name)}</td>
            <td>${esc(it.resolved_policy)} / ${esc(it.profile)}</td>
            <td>${it.entity_count}</td>
            <td>${it.tokens_est} (${esc(it.format_used)})</td>
            <td style="display:flex;gap:6px;flex-wrap:wrap;">
              <button class="btn" onclick="inspectItem('${esc(it.alias)}')">${t.previewBtn}</button>
              <button class="btn" ${copyDis} onclick="copyRef('${esc(it.alias)}')">${t.copyBtn}</button>
              <button class="btn btn-danger" onclick="deleteItem('${esc(it.alias)}')">${t.delBtn}</button>
            </td>
          </tr>`;
      }).join('');

      const drawer = INSPECT ? `
        <div class="card" style="border-color:var(--accent);">
          <h2>${t.drawerTitle}: <code>${esc(INSPECT.uri)}</code></h2>
          <p style="font-size:0.82rem;color:var(--muted);margin:0 0 10px;">
            Policy: <b>${esc(INSPECT.resolved_policy)}</b> · Profile: <b>${esc(INSPECT.profile)}</b> ·
            ${INSPECT.tokens_est} tok (${esc(INSPECT.format_used)})
          </p>
          <div class="grid" style="margin-bottom:10px;">
            <label>${t.newProfLbl}
              <select id="re-profile">
                <option value="max_security" ${INSPECT.profile === 'max_security' ? 'selected' : ''}>max_security (Solo Locale 🔒)</option>
                <option value="medium" ${INSPECT.profile === 'medium' ? 'selected' : ''}>medium (Anonimizzato per Chat 🛡️)</option>
                <option value="low" ${INSPECT.profile === 'low' ? 'selected' : ''}>low (Solo Riassunto [REDACTED])</option>
                <option value="max_context" ${INSPECT.profile === 'max_context' ? 'selected' : ''}>max_context (Pubblico)</option>
              </select>
            </label>
            <label>${t.addTermsLbl}<input id="re-terms" placeholder="Nome Cognome, CF, Azienda..." /></label>
          </div>
          <label class="row-chk" style="margin-bottom:10px;"><input type="checkbox" id="re-ner" /> ${t.nerLbl}</label>
          <button class="btn btn-em" onclick="applyResanitize('${esc(INSPECT.alias)}')">${t.applyUpdate}</button>
          <pre style="margin-top:12px;">${esc(INSPECT.text || '')}</pre>
        </div>` : '';

      return `
        <div class="card">
          <h2>${t.uploadTitle}</h2>
          <div class="dropzone" id="dropzone" onclick="document.getElementById('v-file').click()"
               ondragover="event.preventDefault(); this.classList.add('drag');"
               ondragleave="this.classList.remove('drag');"
               ondrop="event.preventDefault(); this.classList.remove('drag'); pickFileObj(event.dataTransfer.files[0]);">
            <div id="drop-label">${SELECTED_FILE ? ('📄 ' + esc(SELECTED_FILE.name)) : esc(t.dropHint)}</div>
            <input type="file" id="v-file" style="display:none;" accept=".pdf,.docx,.xlsx,.pptx,.txt,.md,.json,.csv,.log" onchange="pickFileObj(this.files[0])" />
          </div>
          <div class="prof-grid">${profCards}</div>
          <div class="grid">
            <label>${t.aliasLbl}<input id="v-alias" placeholder="alsa" value="${SELECTED_FILE ? esc(SELECTED_FILE.name.replace(/\.[^.]+$/,'')) : ''}" /></label>
            <label>${t.policyLbl}
              <select id="v-policy">
                <option value="auto">auto (Consigliata)</option>
                <option value="fail_closed">fail_closed (Blocca su errore)</option>
                <option value="fail_open">fail_open (Pubblico)</option>
              </select>
            </label>
            <label>${t.termsLbl}<input id="v-terms" placeholder="Mario Rossi, P.IVA..." /></label>
          </div>
          <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;margin-top:12px;">
            <label class="row-chk"><input type="checkbox" id="v-ner" /> ${t.nerLbl}</label>
            <button id="btn-upload" class="btn btn-primary" onclick="uploadVaultFile()">${t.uploadBtn}</button>
          </div>
        </div>

        <div class="card">
          <h2>${t.vaultTitle}</h2>
          <div class="stats">
            <div class="stat-box">${t.tot}: <b>${total}</b></div>
            <div class="stat-box">${t.lockOnly}: <b>${localCount}</b></div>
            <div class="stat-box">${t.chatReady}: <b>${chatCount}</b></div>
          </div>
          ${ITEMS.length === 0 ? `<p style="color:var(--muted);">${t.emptyVault}</p>` : `
          <div style="overflow-x:auto;">
            <table>
              <thead><tr><th>Privacy</th><th>Alias</th><th>File</th><th>Policy / Profilo</th><th>Entità</th><th>Token</th><th>Azioni</th></tr></thead>
              <tbody>${rows}</tbody>
            </table>
          </div>`}
        </div>
        ${drawer}`;
    }

    function renderModelsTab() {
      if (!STATUS) return '<div class="card">Loading...</div>';
      const hw = STATUS.hardware || {};
      const cls = hw.classification || {};
      const recs = Object.entries((STATUS.recommended_models || {}).recommended_by_role || {}).map(([role, info]) => `
        <tr><td><b>${esc(role)}</b></td><td><code>${esc(info.model_id)}</code></td><td>${info.memory_gb} GB</td><td>${esc(info.quantization)}</td><td>${info.recommended_num_ctx}</td></tr>`).join('');
      return `
        <div class="card">
          <h2>Hardware Rilevato &amp; Modelli Raccomandati</h2>
          <p style="font-size:0.85rem;color:var(--muted);">
            OS: <b>${esc(hw.os)}</b> · Tier: <span class="pill pill-safe">${esc(cls.tier)}</span> · RAM: <b>${hw.total_ram_gb} GB</b> (${hw.free_ram_gb} GB free) · GPU: <b>${esc(hw.gpu_name)}</b> (${hw.vram_gb} GB)
          </p>
          <table><thead><tr><th>Role</th><th>Model</th><th>RAM</th><th>Quantization</th><th>num_ctx</th></tr></thead><tbody>${recs}</tbody></table>
        </div>
        <div class="card">
          <h2>Aggiungi Modello Custom / Variable Quant (es. 27B 4-bit XXS)</h2>
          <div class="grid">
            <label>Model ID<input id="m-id" placeholder="qwen3.8:27b-q4_xxs" /></label>
            <label>Runner<select id="m-runner"><option value="ollama">ollama</option><option value="unsloth">unsloth</option><option value="llama_cpp">llama_cpp</option></select></label>
            <label>RAM (GB)<input id="m-mem" type="number" step="0.1" value="8.1" /></label>
            <label>Native Ctx<input id="m-ctx" type="number" step="1024" value="32768" /></label>
            <label>Quantization<input id="m-quant" value="Unsloth Variable 4-bit XXS" /></label>
            <label>Roles<input id="m-roles" value="deep_reasoner, orchestrator" /></label>
          </div>
          <label class="row-chk" style="margin:10px 0;"><input id="m-var" type="checkbox" checked /> Variable / Dynamic Quantization</label>
          <button class="btn btn-primary" onclick="addCustomModel()">💾 Salva Modello</button>
        </div>`;
    }

    function renderHarnessesTab() {
      const mat = STATUS?.presend_harnesses || {};
      const rows = Object.entries(mat).map(([h, safe]) => `
        <tr><td><b>${esc(h)}</b></td><td>${safe ? '<span class="pill pill-safe">Channel 3 Pre-Send Safe</span>' : '<span class="pill pill-lock">Use Privacy Vault UI / MCP</span>'}</td></tr>`).join('');
      const prev = SYNC_PREVIEW ? `<pre style="margin-top:12px;">${esc(JSON.stringify(SYNC_PREVIEW, null, 2))}</pre>` : '';
      return `
        <div class="card">
          <h2>Matrice Intercettazione Pre-Send (8 Harness)</h2>
          <table><thead><tr><th>Harness</th><th>Garanzia Intercettazione Allegati</th></tr></thead><tbody>${rows}</tbody></table>
          <button class="btn btn-primary" style="margin-top:12px;" onclick="loadSyncPreview()">🔍 Anteprima Sync (Dry-Run)</button>
          ${prev}
        </div>`;
    }

    function render() {
      const t = L();
      document.getElementById('lang-btn').textContent = LANG === 'it' ? '🇮🇹 IT' : '🇬🇧 EN';
      document.getElementById('tab-btn-vault').textContent = t.tabVault;
      document.getElementById('tab-btn-models').textContent = t.tabModels;
      document.getElementById('tab-btn-harnesses').textContent = t.tabHarnesses;
      ['vault', 'models', 'harnesses'].forEach((k) => {
        document.getElementById('tab-btn-' + k).classList.toggle('active', TAB === k);
      });
      const body = TAB === 'vault' ? renderVaultTab() : (TAB === 'models' ? renderModelsTab() : renderHarnessesTab());
      document.getElementById('main-content').innerHTML = body;
    }

    render();
    refreshAll().catch((e) => showAlert(String(e), 'err'));
  </script>
</body>
</html>
"""


def render_local_ui_html() -> str:
    """Returns the clean self-contained HTML for Cortical's on-demand loopback UI."""
    return _LOCAL_UI_HTML


def _is_loopback_host_header(host_header: str) -> bool:
    if not host_header:
        return True
    raw = host_header.strip().lower()
    if raw.startswith("[::1]"):
        return True
    hostname = raw.split(":", 1)[0]
    return hostname in {"127.0.0.1", "localhost"}


def create_local_ui_server(
    *,
    vault_db: Path | str | None = None,
    host: str = "127.0.0.1",
    port: int = 8765,
    config_path: Optional[Path] = None,
) -> ThreadingHTTPServer:
    """Creates a loopback-only HTTP server for Privacy Vault & Control Plane management."""
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError(f"Refusing non-loopback bind host '{host}'; Cortical UI only binds loopback.")
    db_path = Path(vault_db or os.environ.get("CORTICAL_VAULT_DB") or DEFAULT_VAULT_DB)

    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return  # Keep terminal output crisp

        def _send_json(self, code: int, payload: Any) -> None:
            body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_html(self, code: int, html: str) -> None:
            body = html.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json_body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > (MAX_UPLOAD_BYTES * 2):
                raise ValueError(f"Invalid request body size: {length} bytes")
            raw = self.rfile.read(length)
            data = json.loads(raw.decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("JSON object expected")
            return data

        def _guard_host(self) -> bool:
            if not _is_loopback_host_header(self.headers.get("Host", "")):
                self._send_json(HTTPStatus.FORBIDDEN, {"error": "Loopback Host header required"})
                return False
            return True

        def do_GET(self) -> None:  # noqa: N802
            if not self._guard_host():
                return
            path = urllib.parse.urlparse(self.path).path
            if path in {"/", "/index.html"}:
                self._send_html(HTTPStatus.OK, render_local_ui_html())
                return
            vault = PrivacyVault(db_path)
            if path == "/api/vault":
                self._send_json(HTTPStatus.OK, {"items": vault.list_items(include_local_only=True)})
                return
            if path.startswith("/api/vault/"):
                alias = urllib.parse.unquote(path[len("/api/vault/"):])
                try:
                    self._send_json(HTTPStatus.OK, vault.read_resource(alias, allow_local_only=True))
                except KeyError as exc:
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
                return
            if path == "/api/status":
                cfg = load_cortical_config(config_path)
                hw = probe_hardware(runners_probe=False)
                rec = recommend_models_for_hardware(hw, custom_models=cfg.get("custom_models"))
                self._send_json(HTTPStatus.OK, {
                    "hardware": hw,
                    "recommended_models": rec,
                    "config": cfg,
                    "models_catalog": list_all_models(cfg.get("custom_models")),
                    "presend_harnesses": get_harness_presend_matrix(),
                })
                return
            if path == "/api/sync-preview":
                cfg = load_cortical_config(config_path)
                hw = probe_hardware(runners_probe=False)
                rec = recommend_models_for_hardware(hw, custom_models=cfg.get("custom_models"))
                changes = plan_sync(cfg, hw, rec, vault_db_path=db_path)
                self._send_json(HTTPStatus.OK, apply_sync(changes, dry_run=True))
                return
            self._send_json(HTTPStatus.NOT_FOUND, {"error": f"Unknown route: {path}"})

        def do_POST(self) -> None:  # noqa: N802
            if not self._guard_host():
                return
            path = urllib.parse.urlparse(self.path).path
            try:
                body = self._read_json_body()
            except Exception as exc:  # noqa: BLE001
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

            vault = PrivacyVault(db_path)
            if path == "/api/vault/upload":
                filename = Path(str(body.get("filename") or "upload.txt")).name
                b64 = str(body.get("content_base64") or "")
                try:
                    raw_bytes = base64.b64decode(b64, validate=True)
                except Exception as exc:  # noqa: BLE001
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": f"Invalid base64 payload: {exc}"})
                    return
                if not raw_bytes or len(raw_bytes) > MAX_UPLOAD_BYTES:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": "File empty or exceeds 25 MB limit"})
                    return
                cfg = load_cortical_config(config_path)
                terms = body.get("custom_terms") or []
                if isinstance(terms, str):
                    terms = [t.strip() for t in re.split(r"[,\n]+", terms) if t.strip()]
                try:
                    res = vault.ingest_bytes(
                        filename,
                        raw_bytes,
                        alias=body.get("alias") or None,
                        policy=str(body.get("policy") or "auto"),
                        profile=str(body.get("profile") or "medium"),
                        custom_terms=terms or None,
                        use_local_ner=bool(body.get("use_local_ner", False)),
                        config=cfg,
                    )
                    self._send_json(HTTPStatus.OK, res)
                except FailClosedError as exc:
                    self._send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(exc), "fail_closed": True})
                return

            if path.startswith("/api/vault/") and path.endswith("/update"):
                alias = urllib.parse.unquote(path[len("/api/vault/") : -len("/update")])
                terms = body.get("custom_terms") or []
                if isinstance(terms, str):
                    terms = [t.strip() for t in re.split(r"[,\n]+", terms) if t.strip()]
                try:
                    res = vault.re_sanitize(
                        alias,
                        profile=body.get("profile") or None,
                        policy=body.get("policy") or None,
                        custom_terms=terms or None,
                        use_local_ner=bool(body.get("use_local_ner", False)),
                        config=load_cortical_config(config_path),
                    )
                    self._send_json(HTTPStatus.OK, res)
                except KeyError as exc:
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
                except FailClosedError as exc:
                    self._send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(exc), "fail_closed": True})
                return

            if path == "/api/config":
                saved_p = save_cortical_config(body, config_path=config_path)
                self._send_json(HTTPStatus.OK, {"saved": str(saved_p), "config": load_cortical_config(saved_p)})
                return

            self._send_json(HTTPStatus.NOT_FOUND, {"error": f"Unknown route: {path}"})

        def do_DELETE(self) -> None:  # noqa: N802
            if not self._guard_host():
                return
            path = urllib.parse.urlparse(self.path).path
            if path.startswith("/api/vault/"):
                alias = urllib.parse.unquote(path[len("/api/vault/"):])
                deleted = PrivacyVault(db_path).delete_item(alias)
                if not deleted:
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": f"Vault item not found: {alias}"})
                    return
                self._send_json(HTTPStatus.OK, {"deleted": True, "alias": alias})
                return
            self._send_json(HTTPStatus.NOT_FOUND, {"error": f"Unknown route: {path}"})

    return ThreadingHTTPServer((host, int(port)), _Handler)


def serve_local_ui(
    *,
    vault_db: Path | str | None = None,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
    config_path: Optional[Path] = None,
) -> int:
    """Starts the foreground loopback UI server (Zero-Server when not running) until Ctrl+C."""
    srv = create_local_ui_server(vault_db=vault_db, host=host, port=port, config_path=config_path)
    actual_port = srv.server_address[1]
    url = f"http://{host}:{actual_port}/"
    print(f"Cortical Privacy Vault UI listening on {url} (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(0.2, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped Cortical UI.")
    finally:
        srv.server_close()
    return 0
