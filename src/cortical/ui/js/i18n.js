/**
 * Lightweight, zero-dependency i18n convention for Cortical UI.
 * Loads `/ui/locales/<lang>.json` (it, en, es...) with synchronous fallback,
 * supports `t('dot.path', { param })` interpolation and declarative `[data-i18n*]` DOM binding.
 */

export const SUPPORTED_LANGS = ['it', 'en', 'es'];

const INLINE_FALLBACK = {
  it: {
    meta: { toggleBtn: '🇮🇹 Lingua: IT', nextBtn: '🇬🇧 EN' },
    nav: { workspace: '💬 Workspace', concepts: '🧠 Concetti', studio: '⚙️ Studio & Sicurezza' },
    topbar: {
      close: '✕ Chiudi',
      guideTitle: '📖 Guida Interattiva di Cortical v0.4 (IT / EN / ES)',
      micOff: '🎤 Mic',
      micOn: '🟢 Mic ON',
      liveReady: 'Pronto',
      duckNormal: '🔊 100%',
      duckLow: '🔉 14% Duck',
      tooltipHint: '💡 Clicca per aprire la guida',
    },
    sidebar: { newChat: '+ 💬 Chat', newTask: '+ 🤖 Task' },
    workspace: { promptPlaceholder: 'Scrivi un messaggio, trascina un file o premi ⌘+Invio per avviare un Task...' },
  },
  en: {
    meta: { toggleBtn: '🇬🇧 Lang: EN', nextBtn: '🇪🇸 ES' },
    nav: { workspace: '💬 Workspace', concepts: '🧠 Concepts', studio: '⚙️ Studio & Safety' },
    topbar: {
      close: '✕ Close',
      guideTitle: '📖 Cortical v0.4 Interactive Guide (IT / EN / ES)',
      micOff: '🎤 Mic',
      micOn: '🟢 Mic ON',
      liveReady: 'Ready',
      duckNormal: '🔊 100%',
      duckLow: '🔉 14% Duck',
      tooltipHint: '💡 Click to open the interactive guide',
    },
    sidebar: { newChat: '+ 💬 Chat', newTask: '+ 🤖 Task' },
    workspace: { promptPlaceholder: 'Write a message, drop a file, or press ⌘+Enter to launch a Task...' },
  },
};

const _localeCache = {
  it: INLINE_FALLBACK.it,
  en: INLINE_FALLBACK.en,
};

let _currentLang = SUPPORTED_LANGS.includes(localStorage.getItem('cortical_ui_lang'))
  ? localStorage.getItem('cortical_ui_lang')
  : 'it';

function _getByPath(obj, path) {
  if (!obj || !path) return undefined;
  return path.split('.').reduce((acc, part) => (acc && typeof acc === 'object' ? acc[part] : undefined), obj);
}

export function getLang() {
  return _currentLang;
}

export async function loadLocale(lang) {
  const code = SUPPORTED_LANGS.includes(lang) ? lang : 'it';
  try {
    const resp = await fetch(`/ui/locales/${code}.json?v=20261116`, { cache: 'no-store' });
    if (resp.ok) {
      const json = await resp.json();
      _localeCache[code] = json;
      return json;
    }
  } catch {
    // Fallback to inline cache cleanly
  }
  return _localeCache[code] || _localeCache.en || _localeCache.it;
}

export function t(key, params = {}, langOverride = null) {
  const code = langOverride && SUPPORTED_LANGS.includes(langOverride) ? langOverride : _currentLang;
  let val =
    _getByPath(_localeCache[code], key) ??
    _getByPath(_localeCache.en, key) ??
    _getByPath(_localeCache.it, key) ??
    key;
  if (typeof val !== 'string') return String(val);
  Object.entries(params || {}).forEach(([k, v]) => {
    val = val.replaceAll(`{${k}}`, String(v ?? ''));
  });
  return val;
}

export function applyDomTranslations(root = document) {
  if (!root || typeof root.querySelectorAll !== 'function') return;
  root.querySelectorAll('[data-i18n]').forEach((el) => {
    const key = el.getAttribute('data-i18n');
    if (key) el.textContent = t(key);
  });
  root.querySelectorAll('[data-i18n-placeholder]').forEach((el) => {
    const key = el.getAttribute('data-i18n-placeholder');
    if (key) el.setAttribute('placeholder', t(key));
  });
  root.querySelectorAll('[data-i18n-title]').forEach((el) => {
    const key = el.getAttribute('data-i18n-title');
    if (key) el.setAttribute('title', t(key));
  });
  document.documentElement.lang = _currentLang;
}

export async function setUiLanguage(lang) {
  _currentLang = SUPPORTED_LANGS.includes(lang) ? lang : 'it';
  localStorage.setItem('cortical_ui_lang', _currentLang);
  await loadLocale(_currentLang);
  applyDomTranslations();
  return _currentLang;
}
