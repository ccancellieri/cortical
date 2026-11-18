/**
 * Modular & Optional Remote Gateway, Key Auth & Account Cap Studio Controller.
 */
import { apiGet, apiPost } from './api.js';
import { escapeHtml } from './state.js';

let cachedGatewayStatus = null;

function setFeedback(text, ok = true) {
  const el = document.getElementById('gw-feedback');
  if (!el) return;
  el.textContent = text;
  el.style.color = ok ? 'var(--emerald, #34d399)' : 'var(--rose, #f87171)';
}

export async function loadGatewayStatus() {
  try {
    const st = await apiGet('/api/gateway/status');
    cachedGatewayStatus = st;
    renderGatewayUi(st);
    return st;
  } catch (err) {
    setFeedback(`Errore caricamento gateway: ${err.message}`, false);
    return null;
  }
}

function renderGatewayUi(st) {
  if (!st) return;
  const pill = document.getElementById('gateway-status-pill');
  if (pill) {
    const online = Boolean(st.tunnel?.running && st.public_url);
    pill.textContent = online
      ? `🌐 Remoto ON (${st.registered_users_count}/${st.max_users})`
      : `🌐 Gateway (${st.registered_users_count}/${st.max_users})`;
    pill.title = online
      ? `Tunnel attivo: ${st.public_url} · Utenti ${st.registered_users_count}/${st.max_users}`
      : 'Configura accesso remoto internet, chiave e account in Studio';
    pill.style.borderColor = online ? 'rgba(52,211,153,0.55)' : 'var(--border)';
    pill.style.color = online ? 'var(--emerald, #34d399)' : 'var(--text-soft)';
  }

  const chkAuth = document.getElementById('gw-auth-enabled');
  if (chkAuth) chkAuth.checked = Boolean(st.auth_enabled);
  const chkLocal = document.getElementById('gw-localhost-bypass');
  if (chkLocal) chkLocal.checked = Boolean(st.allow_localhost_bypass);
  const maxInp = document.getElementById('gw-max-users');
  if (maxInp) maxInp.value = String(st.max_users || 1);
  const keyInp = document.getElementById('gw-api-key');
  if (keyInp) keyInp.value = st.gateway_api_key || st.gateway_key_masked || '';
  const domInp = document.getElementById('gw-duckdns-domain');
  if (domInp) domInp.value = st.duckdns_domain || 'sovereign-ai';
  const smtpH = document.getElementById('gw-smtp-host');
  if (smtpH) smtpH.value = st.smtp_host || '';
  const smtpP = document.getElementById('gw-smtp-port');
  if (smtpP) smtpP.value = String(st.smtp_port || 587);
  const smtpU = document.getElementById('gw-smtp-user');
  if (smtpU) smtpU.value = st.smtp_user || '';

  const pubUrlEl = document.getElementById('gw-public-url');
  if (pubUrlEl) {
    pubUrlEl.textContent = st.public_url || 'Nessun tunnel attivo (solo locale http://127.0.0.1:8765)';
  }
  const portalEl = document.getElementById('gw-portal-url');
  if (portalEl) {
    portalEl.href = st.github_portal_url || 'https://ccancellieri.github.io/cortical/';
    portalEl.textContent = st.github_portal_url || 'https://ccancellieri.github.io/cortical/';
  }

  const usersBox = document.getElementById('gw-users-list');
  if (usersBox) {
    const users = Array.isArray(st.users) ? st.users : [];
    const capBanner = `<div style="font-size:0.76rem; color:var(--muted); margin-bottom:6px;">Posti occupati: <b>${st.registered_users_count} / ${st.max_users}</b> (nuove registrazioni ${st.slots_remaining > 0 ? 'aperte' : 'bloccate'}).</div>`;
    usersBox.innerHTML = capBanner + users
      .map(
        (u) => `
          <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; padding:8px 10px; border:1px solid var(--border); border-radius:8px; margin-bottom:6px; background:rgba(15,23,42,0.5);">
            <div>
              <div style="font-weight:700; font-size:0.82rem;">${escapeHtml(u.email)} <span style="font-size:0.7rem; color:var(--accent);">[${escapeHtml(u.role)}]</span></div>
              <div style="font-size:0.72rem; color:var(--muted);">Password: ${u.has_password ? '✅ Impostata' : '⏳ In attesa di creazione'}</div>
            </div>
            <button type="button" class="btn btn-ghost btn-sm" data-gw-invite="${escapeHtml(u.email)}">📧 Invia Link Password</button>
          </div>
        `
      )
      .join('');
  }
}

export async function saveGatewayConfig({ rotateKey = false } = {}) {
  try {
    const payload = {
      auth_enabled: Boolean(document.getElementById('gw-auth-enabled')?.checked),
      allow_localhost_bypass: Boolean(document.getElementById('gw-localhost-bypass')?.checked),
      max_users: Math.max(1, Number(document.getElementById('gw-max-users')?.value || 1)),
      duckdns_domain: document.getElementById('gw-duckdns-domain')?.value?.trim() || 'sovereign-ai',
      rotate_key: Boolean(rotateKey),
    };
    const duckTok = document.getElementById('gw-duckdns-token')?.value?.trim();
    if (duckTok) payload.duckdns_token = duckTok;
    const smtpHost = document.getElementById('gw-smtp-host')?.value?.trim();
    if (smtpHost !== undefined) payload.smtp_host = smtpHost;
    const smtpPort = Number(document.getElementById('gw-smtp-port')?.value || 587);
    if (smtpPort) payload.smtp_port = smtpPort;
    const smtpUser = document.getElementById('gw-smtp-user')?.value?.trim();
    if (smtpUser !== undefined) payload.smtp_user = smtpUser;
    const smtpPass = document.getElementById('gw-smtp-pass')?.value?.trim();
    if (smtpPass) payload.smtp_pass = smtpPass;
    const res = await apiPost('/api/gateway/configure', payload);
    cachedGatewayStatus = res;
    renderGatewayUi(res);
    setFeedback(rotateKey ? 'Chiave Gateway rigenerata e salvata.' : 'Configurazione Gateway salvata.');
  } catch (err) {
    setFeedback(`Errore salvataggio: ${err.message}`, false);
  }
}

export async function exposeGatewayTunnel(action = 'start') {
  setFeedback(action === 'stop' ? 'Chiusura tunnel in corso...' : 'Avvio tunnel HTTPS pubblico...');
  try {
    const provider = document.getElementById('gw-tunnel-provider')?.value || 'auto';
    const duckTok = document.getElementById('gw-duckdns-token')?.value?.trim();
    const res = await apiPost('/api/gateway/expose', {
      action,
      provider,
      ...(duckTok ? { duckdns_token: duckTok, update_duckdns: true } : {}),
    });
    if (res.status) {
      cachedGatewayStatus = res.status;
      renderGatewayUi(res.status);
    } else {
      await loadGatewayStatus();
    }
    if (action === 'stop') {
      setFeedback('Tunnel pubblico fermato (solo accesso locale).');
    } else if (res.public_url) {
      setFeedback(`Tunnel online (${res.provider}): ${res.public_url}`);
    } else {
      setFeedback(res.error || 'Impossibile aprire il tunnel.', false);
    }
  } catch (err) {
    setFeedback(`Errore tunnel: ${err.message}`, false);
  }
}

export async function sendGatewayInvite(email = 'ccancellieri@hotmail.com') {
  setFeedback(`Preparazione email e link creazione password per ${email}...`);
  try {
    const res = await apiPost('/api/gateway/invite', { email });
    const via = res.sent_via?.length ? `Inviata via ${res.sent_via.join(', ')}` : `Salvata in outbox (${res.outbox_eml})`;
    setFeedback(`Link setup password generato per ${email}. ${via}. URL: ${res.setup_url}`);
    await loadGatewayStatus();
  } catch (err) {
    setFeedback(`Errore invito: ${err.message}`, false);
  }
}

export async function copyGatewaySecret(kind) {
  const st = cachedGatewayStatus || (await loadGatewayStatus());
  if (!st) return;
  const val = kind === 'url' ? (st.public_url ? `${st.public_url}/?key=${st.gateway_api_key || ''}` : 'http://127.0.0.1:8765/') : (st.gateway_api_key || '');
  if (!val) return setFeedback('Valore non disponibile.', false);
  try {
    await navigator.clipboard.writeText(val);
    setFeedback(kind === 'url' ? 'Link accesso rapido con chiave copiato.' : 'Chiave Gateway copiata negli appunti.');
  } catch (_) {
    setFeedback(val);
  }
}

export function bindGatewayEvents(onOpenStudioGateway) {
  document.getElementById('gateway-status-pill')?.addEventListener('click', () => {
    if (onOpenStudioGateway) onOpenStudioGateway();
    loadGatewayStatus();
    loadUsbVolumes();
  });
  document.getElementById('btn-gw-refresh')?.addEventListener('click', loadGatewayStatus);
  document.getElementById('btn-gw-save')?.addEventListener('click', () => saveGatewayConfig({ rotateKey: false }));
  document.getElementById('btn-gw-rotate-key')?.addEventListener('click', () => saveGatewayConfig({ rotateKey: true }));
  document.getElementById('btn-gw-copy-key')?.addEventListener('click', () => copyGatewaySecret('key'));
  document.getElementById('btn-gw-copy-url')?.addEventListener('click', () => copyGatewaySecret('url'));
  document.getElementById('btn-gw-expose-start')?.addEventListener('click', () => exposeGatewayTunnel('start'));
  document.getElementById('btn-gw-expose-stop')?.addEventListener('click', () => exposeGatewayTunnel('stop'));
  document.getElementById('gw-users-list')?.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-gw-invite]');
    if (btn) sendGatewayInvite(btn.getAttribute('data-gw-invite') || 'ccancellieri@hotmail.com');
  });
  document.getElementById('btn-gw-register-user')?.addEventListener('click', async () => {
    const eml = document.getElementById('gw-new-user-email')?.value?.trim() || '';
    if (!eml) return setFeedback('Inserisci un indirizzo email.', false);
    try {
      await apiPost('/api/auth/register', { email: eml });
      setFeedback(`Utente ${eml} registrato.`);
      await loadGatewayStatus();
    } catch (err) {
      setFeedback(err.message, false);
    }
  });
  document.getElementById('btn-usb-refresh')?.addEventListener('click', loadUsbVolumes);
  document.getElementById('btn-usb-export')?.addEventListener('click', exportBundleToPath);
  document.getElementById('btn-usb-download')?.addEventListener('click', () => {
    window.location.href = '/api/portability/download';
  });
  document.getElementById('btn-usb-import')?.addEventListener('click', () => {
    document.getElementById('usb-import-file')?.click();
  });
  document.getElementById('usb-import-file')?.addEventListener('change', async (e) => {
    const file = e.target?.files?.[0];
    if (!file) return;
    await importBundleFile(file);
    e.target.value = '';
  });
}

export async function loadUsbVolumes() {
  try {
    const data = await apiGet('/api/portability/volumes');
    const sel = document.getElementById('usb-volume-select');
    if (!sel) return;
    const vols = data.volumes || [];
    sel.innerHTML = vols.length
      ? vols.map((v) => `<option value="${escapeHtml(v.path)}">💾 ${escapeHtml(v.name)} (${escapeHtml(v.path)})</option>`).join('')
      : '<option value="">📁 Locale (.cortical_data/backups/)</option>';
  } catch (err) {
    setFeedback(err.message, false);
  }
}

async function exportBundleToPath() {
  const custom = document.getElementById('usb-custom-path')?.value?.trim() || '';
  const vol = document.getElementById('usb-volume-select')?.value?.trim() || '';
  const outputPath = custom || vol || '';
  try {
    const res = await apiPost('/api/portability/export', { output_path: outputPath });
    const kb = Math.round((res.size_bytes || 0) / 1024);
    setFeedback(`✅ Bundle esportato: ${res.archive_path} (${kb} KB, ${res.files_archived || 0} file).`);
  } catch (err) {
    setFeedback(err.message, false);
  }
}

async function importBundleFile(file) {
  const mode = document.getElementById('usb-import-mode')?.value || 'merge';
  try {
    const buf = await file.arrayBuffer();
    const bytes = new Uint8Array(buf);
    let bin = '';
    for (let i = 0; i < bytes.length; i += 8192) {
      bin += String.fromCharCode(...bytes.subarray(i, i + 8192));
    }
    const archiveBase64 = btoa(bin);
    const res = await apiPost('/api/portability/import', { mode, archive_base64: archiveBase64 });
    setFeedback(`✅ Import completato (${res.mode}) da ${res.source_host || 'bundle'}.`);
  } catch (err) {
    setFeedback(err.message, false);
  }
}
