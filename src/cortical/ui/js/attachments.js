/**
 * Scoped context attachments module (Files, Folders, Skills, Plugins, MCP)
 * supporting per-chat and per-task isolation, Drag & Drop, multi-file upload,
 * unified tabbed attachment modal, and 1-click removal.
 */
import { apiGet, apiPost } from './api.js';
import { activeScopeId, activeScopeLabel, escapeHtml, store } from './state.js';

let modalMainTab = 'workspace'; // 'workspace' | 'local' | 'extensions'
let extensionKind = 'skill'; // 'skill' | 'plugin' | 'mcp'
let currentBrowsePath = '';
let currentBrowseParent = '';

let onAfterAttachmentChangeCb = null;
let openActionModalCb = null;

export function configureAttachmentsHooks({ onAfterChange, openActionModal } = {}) {
  if (onAfterChange) onAfterAttachmentChangeCb = onAfterChange;
  if (openActionModal) openActionModalCb = openActionModal;
}

const ICON_BY_TYPE = {
  file: '📄',
  folder: '📁',
  skill: '⚡',
  plugin: '🔌',
  mcp: '🧩',
};

function notifyAttachmentToast(msg) {
  const container = document.getElementById('agent-stream');
  if (!container) return;
  const div = document.createElement('div');
  div.className = 'msg-toast';
  div.textContent = msg;
  container.appendChild(div);
  const scrollWrap = container.parentElement;
  if (scrollWrap) scrollWrap.scrollTop = scrollWrap.scrollHeight;
}

export async function loadScopedContext(scopeOverride) {
  const scopeId = scopeOverride || activeScopeId();
  try {
    const data = await apiGet(`/api/context?scope_id=${encodeURIComponent(scopeId)}`);
    store.cachedAttachments = data.attachments || [];
    if (data.catalog) store.cachedCatalog = data.catalog;
    renderContextChips(scopeId);
  } catch (err) {
    console.error('Errore caricamento contesto:', err);
  }
}

export function renderContextChips(scopeOverride) {
  const chipsContainer = document.getElementById('composer-context-chips');
  const studioList = document.getElementById('studio-context-list');
  const studioPill = document.getElementById('studio-scope-pill');
  const badgeCount = document.getElementById('stage-attach-count');
  const curScope = scopeOverride || activeScopeId();
  const scopeDesc = curScope.startsWith('pi-') ? `🤖 ${curScope}` : activeScopeLabel();

  if (studioPill) studioPill.textContent = `[${curScope}]`;
  if (badgeCount) {
    const n = store.cachedAttachments.length;
    badgeCount.textContent = n ? `📎 ${n}` : '';
    badgeCount.style.display = n ? 'inline-flex' : 'none';
  }

  if (!store.cachedAttachments.length) {
    if (chipsContainer) {
      chipsContainer.innerHTML = `
        <span class="context-empty-hint">
          <span>📎 Contesto (<b>${escapeHtml(scopeDesc)}</b>):</span>
          <span>trascina file qui o clicca <b>+ Allega</b></span>
        </span>
      `;
    }
    if (studioList) {
      studioList.innerHTML = `<div style="font-size:0.76rem; color:var(--muted); font-style:italic;">Nessun allegato in "${escapeHtml(curScope)}".</div>`;
    }
    return;
  }

  if (chipsContainer) {
    const clearBtn = store.cachedAttachments.length > 1
      ? `<button type="button" class="mini-action-btn danger" data-ctx-action="clear-all" title="Rimuovi tutti gli allegati dallo scope">Svuota (${store.cachedAttachments.length})</button>`
      : '';
    chipsContainer.innerHTML = store.cachedAttachments
      .map((att) => {
        const aid = att.attachment_id || att.id;
        const icon = ICON_BY_TYPE[att.item_type] || '📎';
        const rawName = (att.label || att.item_ref || '').split('/').pop() || att.item_ref;
        const tierBadge = att.depth_tier ? ` · ${att.depth_tier.toUpperCase()}` : '';
        return `
          <span class="ctx-chip" data-att-id="${escapeHtml(aid)}" title="${escapeHtml(att.item_ref)}">
            <span class="ctx-chip-label" data-ctx-action="inspect" data-att-id="${escapeHtml(aid)}">${icon} ${escapeHtml(rawName)}${escapeHtml(tierBadge)}</span>
            <button type="button" class="chip-rm" data-ctx-action="detach" data-att-id="${escapeHtml(aid)}" aria-label="Rimuovi ${escapeHtml(rawName)}" title="Rimuovi dal contesto">×</button>
          </span>
        `;
      })
      .join('') + clearBtn;
  }

  if (studioList) {
    studioList.innerHTML = store.cachedAttachments
      .map((att) => {
        const aid = att.attachment_id || att.id;
        const icon = ICON_BY_TYPE[att.item_type] || '📎';
        return `
          <div class="fs-row">
            <div style="min-width:0; flex:1;">
              <div><b>${icon} ${escapeHtml(att.item_type.toUpperCase())}:</b> <code style="color:var(--accent);">${escapeHtml(att.item_ref)}</code></div>
              <div style="font-size:0.68rem; color:var(--muted); font-family:var(--mono);">Tier: ${escapeHtml(att.depth_tier.toUpperCase())} · Scope: ${escapeHtml(att.scope_id)}</div>
            </div>
            <div style="display:flex; gap:5px; flex-shrink:0;">
              <button type="button" class="btn btn-ghost btn-sm" data-ctx-action="inspect-studio" data-att-id="${escapeHtml(aid)}">🔍 3+1</button>
              <button type="button" class="btn btn-danger btn-sm" data-ctx-action="detach" data-att-id="${escapeHtml(aid)}">×</button>
            </div>
          </div>
        `;
      })
      .join('');
  }
}

export async function attachContextItemApi(itemType, itemRef, depthTier = 'medium', label = null, inlineContent = null) {
  if (!itemRef) return;
  const scopeId = activeScopeId();
  try {
    const d = await apiPost('/api/context/attach', {
      scope_id: scopeId,
      item_type: itemType,
      item_ref: itemRef,
      depth_tier: depthTier,
      label,
      inline_content: inlineContent,
    });
    await loadScopedContext(scopeId);
    if (onAfterAttachmentChangeCb) await onAfterAttachmentChangeCb();
    const shortName = (d.label || d.item_ref || itemRef).split('/').pop();
    notifyAttachmentToast(`📎 Allegato ${shortName} (${(d.depth_tier || depthTier).toUpperCase()})`);
  } catch (err) {
    notifyAttachmentToast(`⚠️ Errore allegato: ${err.message}`);
  }
}

export async function detachContextItem(attachmentId) {
  if (!attachmentId || attachmentId === 'undefined') return;
  const scopeId = activeScopeId();
  const prev = [...store.cachedAttachments];
  store.cachedAttachments = store.cachedAttachments.filter((a) => (a.attachment_id || a.id) !== attachmentId);
  renderContextChips(scopeId);
  try {
    const res = await apiPost('/api/context/detach', { attachment_id: attachmentId });
    await loadScopedContext(scopeId);
    if (onAfterAttachmentChangeCb) await onAfterAttachmentChangeCb();
    if (res?.detached) {
      notifyAttachmentToast('🗑️ Allegato rimosso dal contesto');
    }
  } catch (err) {
    store.cachedAttachments = prev;
    renderContextChips(scopeId);
    notifyAttachmentToast(`⚠️ Impossibile rimuovere: ${err.message}`);
  }
}

export async function clearScopeContext() {
  const ids = store.cachedAttachments.map((a) => a.attachment_id || a.id).filter(Boolean);
  if (!ids.length) return;
  const scopeId = activeScopeId();
  store.cachedAttachments = [];
  renderContextChips(scopeId);
  for (const aid of ids) {
    await apiPost('/api/context/detach', { attachment_id: aid }).catch(() => {});
  }
  await loadScopedContext(scopeId);
  if (onAfterAttachmentChangeCb) await onAfterAttachmentChangeCb();
  notifyAttachmentToast('🧹 Allegati dello scope svuotati');
}

export async function attachLocalFilesList(files) {
  if (!files || !files.length) return;
  const tier = document.getElementById('agent-depth')?.value || 'medium';
  for (const file of Array.from(files)) {
    try {
      const text = await file.text();
      await attachContextItemApi('file', file.name, tier, file.name, text);
    } catch (_) {
      if (openActionModalCb) {
        openActionModalCb({
          title: '📄 Percorso File Locale',
          desc: `Impossibile leggere "${file.name}" dal browser.\nInserisci il percorso relativo o assoluto sul disco:`,
          defaultValue: file.name,
          showInput: true,
          confirmLabel: '📎 Allega File',
          onConfirm: async (fullPath) => {
            if (fullPath && fullPath.trim()) {
              await attachContextItemApi('file', fullPath.trim(), tier);
            }
          },
        });
      }
    }
  }
}

export async function handleBrowserFileSelected(event) {
  const input = event.target;
  if (!input.files || !input.files.length) return;
  await attachLocalFilesList(input.files);
  input.value = '';
  closeCatalogModal();
}

export function toggleAttachPopover(forceState) {
  const pop = document.getElementById('attach-popover');
  if (!pop) return;
  const next = typeof forceState === 'boolean' ? forceState : !pop.classList.contains('open');
  pop.classList.toggle('open', next);
}

export async function openCatalogModal(tab = 'workspace', extKind = 'skill') {
  toggleAttachPopover(false);
  modalMainTab = tab === 'extensions' || tab === 'local' ? tab : 'workspace';
  if (extKind) extensionKind = extKind;

  const scopePill = document.getElementById('catalog-scope-pill');
  if (scopePill) scopePill.textContent = `${activeScopeLabel()}`;
  const overlay = document.getElementById('catalog-modal-overlay');
  if (overlay) overlay.classList.add('open');

  switchModalMainTab(modalMainTab);
  await loadScopedContext();
  if (modalMainTab === 'workspace') {
    await browseFs(currentBrowsePath || '');
  } else if (modalMainTab === 'extensions') {
    renderCatalogItems();
  }
}

export function closeCatalogModal(event) {
  if (event && event.target && event.target.id !== 'catalog-modal-overlay') return;
  const overlay = document.getElementById('catalog-modal-overlay');
  if (overlay) overlay.classList.remove('open');
}

export function switchModalMainTab(tab) {
  modalMainTab = tab;
  ['workspace', 'local', 'extensions'].forEach((t) => {
    document.getElementById(`modal-tab-btn-${t}`)?.classList.toggle('active', t === tab);
    const panel = document.getElementById(`modal-pane-${t}`);
    if (panel) panel.style.display = t === tab ? 'block' : 'none';
  });
  if (tab === 'workspace' && !currentBrowsePath) {
    browseFs('');
  } else if (tab === 'extensions') {
    renderCatalogItems();
  }
}

export function switchCatalogExtensionTab(kind, el) {
  extensionKind = kind || 'skill';
  document.querySelectorAll('#catalog-kind-tabs .pill').forEach((p) => p.classList.remove('active'));
  if (el) el.classList.add('active');
  renderCatalogItems();
}

export function renderCatalogItems() {
  const box = document.getElementById('catalog-items-container');
  if (!box) return;
  const list = extensionKind === 'skill'
    ? (store.cachedCatalog.skills || [])
    : extensionKind === 'mcp'
      ? (store.cachedCatalog.mcp_servers || [])
      : (store.cachedCatalog.plugins || []);
  if (!list.length) {
    box.innerHTML = `<div style="font-size:0.77rem; color:var(--muted);">Nessun elemento disponibile per "${escapeHtml(extensionKind)}".</div>`;
    return;
  }
  box.innerHTML = list
    .map((item) => `
      <div class="fs-row">
        <div style="min-width:0; flex:1;">
          <div style="font-weight:700; color:var(--text);">${escapeHtml(item.name)}</div>
          <div style="font-size:0.72rem; color:var(--muted); overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${escapeHtml(item.description || item.path || '')}</div>
        </div>
        <button type="button" class="btn btn-sm" data-cat-attach="${escapeHtml(extensionKind)}" data-cat-name="${escapeHtml(item.name)}">+ Allega</button>
      </div>
    `)
    .join('');
}

export async function browseFs(pathStr) {
  try {
    const data = await apiGet(`/api/fs/list?path=${encodeURIComponent(pathStr || '')}`);
    currentBrowsePath = data.current_path || '';
    currentBrowseParent = data.parent_path || '';
    const pathInput = document.getElementById('fs-path-input');
    if (pathInput) pathInput.value = currentBrowsePath;
    const container = document.getElementById('fs-entries-container');
    if (!container) return;
    const entries = data.entries || [];
    if (!entries.length) {
      container.innerHTML = `<div style="font-size:0.76rem; color:var(--muted);">Cartella vuota o non accessibile.</div>`;
      return;
    }
    container.innerHTML = entries
      .map((e) => {
        const icon = e.is_dir ? '📁' : '📄';
        const badge = e.hint !== 'folder' && e.hint !== 'file'
          ? `<span class="status-pill status-completed">${escapeHtml(e.hint)}</span>`
          : '';
        const openBtn = e.is_dir
          ? `<button type="button" class="btn btn-ghost btn-sm" data-fs-open="${escapeHtml(e.path)}">Apri</button>`
          : '';
        return `
          <div class="fs-row">
            <div style="display:flex; align-items:center; gap:7px; min-width:0; flex:1;">
              <span>${icon}</span>
              <span style="font-family:var(--mono); overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${escapeHtml(e.name)}</span>
              ${badge}
            </div>
            <div style="display:flex; gap:5px; flex-shrink:0;">
              ${openBtn}
              <button type="button" class="btn btn-sm" data-fs-import="${escapeHtml(e.path)}" data-fs-hint="${escapeHtml(e.hint)}">+ Allega</button>
            </div>
          </div>
        `;
      })
      .join('');
  } catch (err) {
    console.error('Errore browseFs:', err);
  }
}

export function browseFsParent() {
  if (currentBrowseParent) browseFs(currentBrowseParent);
}

export async function importFsEntry(fsPath, hint) {
  const targetType = ['skill', 'mcp', 'plugin', 'file', 'folder'].includes(hint) ? hint : 'folder';
  const tier = document.getElementById('agent-depth')?.value || 'medium';
  try {
    const d = await apiPost('/api/context/import', {
      scope_id: activeScopeId(),
      item_type: targetType,
      item_ref: fsPath,
      depth_tier: tier,
    });
    await loadScopedContext(activeScopeId());
    if (onAfterAttachmentChangeCb) await onAfterAttachmentChangeCb();
    closeCatalogModal();
    notifyAttachmentToast(`📎 Importato e allegato: ${(d.label || d.item_ref || fsPath).split('/').pop()}`);
  } catch (err) {
    notifyAttachmentToast(`⚠️ Errore importazione: ${err.message}`);
  }
}

export function importAndAttachCurrentFolder() {
  if (currentBrowsePath) {
    return importFsEntry(currentBrowsePath, 'folder');
  }
}

export function attachFromStudio() {
  const typeEl = document.getElementById('ctx-item-type');
  const refEl = document.getElementById('ctx-item-ref');
  const tierEl = document.getElementById('ctx-item-tier');
  if (!refEl || !refEl.value.trim()) return;
  attachContextItemApi(typeEl.value, refEl.value.trim(), tierEl.value);
  refEl.value = '';
}

export function inspectAttachment3Plus1(attachmentId) {
  const att = store.cachedAttachments.find((a) => (a.attachment_id || a.id) === attachmentId);
  if (!att) return;
  const view = document.getElementById('wiki-node-view');
  if (view) {
    view.textContent = JSON.stringify(att, null, 2);
  }
}

export function setupDropZone(element) {
  if (!element) return;
  const stop = (e) => {
    e.preventDefault();
    e.stopPropagation();
  };
  ['dragenter', 'dragover'].forEach((evt) => {
    element.addEventListener(evt, (e) => {
      stop(e);
      element.classList.add('drop-active');
    });
  });
  ['dragleave', 'drop'].forEach((evt) => {
    element.addEventListener(evt, (e) => {
      stop(e);
      element.classList.remove('drop-active');
    });
  });
  element.addEventListener('drop', async (e) => {
    const files = e.dataTransfer?.files;
    if (files && files.length) {
      await attachLocalFilesList(files);
      closeCatalogModal();
    }
  });
}
