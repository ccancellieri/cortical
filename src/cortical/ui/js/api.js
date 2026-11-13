/**
 * HTTP client helpers for Cortical Mission Control endpoints.
 */

export async function apiGet(url, signal) {
  const r = await fetch(url, signal ? { signal } : undefined);
  if (!r.ok) {
    let msg = `HTTP ${r.status}`;
    try {
      const err = await r.json();
      if (err?.error) msg = err.error;
    } catch (_) {}
    throw new Error(msg);
  }
  return r.json();
}

export async function apiPost(url, body = {}, signal) {
  const r = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    ...(signal ? { signal } : {}),
  });
  let payload = {};
  try {
    payload = await r.json();
  } catch (_) {}
  if (!r.ok) {
    throw new Error(payload?.error || `HTTP ${r.status}`);
  }
  return payload;
}
