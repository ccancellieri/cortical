/**
 * HTTP client helpers for Cortical Mission Control endpoints (with optional Gateway Key / Session Auth).
 */

function syncUrlGatewayKey() {
  try {
    const params = new URLSearchParams(window.location.search);
    const qKey = params.get('key');
    if (qKey && qKey.trim()) {
      localStorage.setItem('cortical_gateway_key', qKey.trim());
    }
  } catch (_) {}
}
syncUrlGatewayKey();

export function buildAuthHeaders(extra = {}) {
  const headers = { ...extra };
  try {
    const key = localStorage.getItem('cortical_gateway_key');
    if (key) headers['X-Cortical-Key'] = key;
    const sess = localStorage.getItem('cortical_session_token');
    if (sess && !headers['Authorization']) {
      headers['Authorization'] = `Bearer ${sess}`;
    }
  } catch (_) {}
  return headers;
}

function handleUnauthorized(status, errPayload) {
  if (status === 401 && errPayload?.login_url) {
    try {
      if (!window.location.pathname.startsWith('/auth/')) {
        window.location.href = errPayload.login_url;
      }
    } catch (_) {}
  }
}

export async function apiGet(url, signal) {
  const r = await fetch(url, {
    headers: buildAuthHeaders(),
    ...(signal ? { signal } : {}),
  });
  if (!r.ok) {
    let msg = `HTTP ${r.status}`;
    let err = {};
    try {
      err = await r.json();
      if (err?.error) msg = err.error;
    } catch (_) {}
    handleUnauthorized(r.status, err);
    throw new Error(msg);
  }
  return r.json();
}

export async function apiPost(url, body = {}, signal) {
  const r = await fetch(url, {
    method: 'POST',
    headers: buildAuthHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(body),
    ...(signal ? { signal } : {}),
  });
  let payload = {};
  try {
    payload = await r.json();
  } catch (_) {}
  if (!r.ok) {
    handleUnauthorized(r.status, payload);
    throw new Error(payload?.error || `HTTP ${r.status}`);
  }
  return payload;
}
