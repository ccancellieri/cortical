/**
 * Concept Knowledge Graph (MCP) interactive SVG canvas + configurator,
 * and Studio 3+1 Wiki / Skills / Permission Gate inspectors.
 */
import { apiGet, apiPost } from './api.js';
import { escapeHtml, store } from './state.js';
import { appendStreamCard, openTaskActionModal, refreshAgents } from './workspace.js';

export async function loadMcpKnowledgeGraph() {
  try {
    const mcpRes = await apiPost('/api/mcp', {
      jsonrpc: '2.0',
      id: Date.now(),
      method: 'tools/call',
      params: { name: 'wiki_get_knowledge_graph', arguments: { max_nodes: 60 } },
    });
    const rawText = mcpRes?.result?.content?.[0]?.text || '{}';
    store.cachedGraphData = JSON.parse(rawText);
    const stats = store.cachedGraphData.stats || {};
    const navCount = document.getElementById('nav-graph-count');
    if (navCount) navCount.textContent = `(${stats.node_count || 0})`;
    computeConceptLayout(store.cachedGraphData);
    renderKnowledgeGraphSvg();
  } catch (err) {
    console.error('Errore loadMcpKnowledgeGraph:', err);
  }
}

export async function reindexSecondBrain() {
  const btn = document.getElementById('btn-graph-reindex');
  if (btn) {
    btn.disabled = true;
    btn.textContent = '⏳ Indicizzo...';
  }
  try {
    await apiPost('/api/mcp', {
      jsonrpc: '2.0',
      id: Date.now(),
      method: 'tools/call',
      params: { name: 'wiki_crawl_delta', arguments: { root_dir: '.' } },
    });
    await loadMcpKnowledgeGraph();
  } catch (err) {
    console.error('Errore reindexSecondBrain:', err);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = '⚡ Indicizza 4 Livelli';
    }
  }
}

export function setGraphFilter(filter, el) {
  store.currentGraphFilter = filter;
  document.querySelectorAll('#graph-filter-pills .pill').forEach((p) => p.classList.remove('active'));
  if (el) el.classList.add('active');
  renderKnowledgeGraphSvg();
}

export function zoomGraph(factor) {
  store.graphZoom = Math.max(0.45, Math.min(2.6, store.graphZoom * factor));
  renderKnowledgeGraphSvg();
}

export function resetGraphView() {
  store.graphZoom = 1.0;
  store.graphPanX = 0;
  store.graphPanY = 0;
  computeConceptLayout(store.cachedGraphData, true);
  renderKnowledgeGraphSvg();
}

function computeConceptLayout(graph, forceReset = false) {
  const nodes = graph.nodes || [];
  const cx = 460;
  const cy = 280;
  const primaryConcepts = nodes.filter((n) => n.kind === 'concept');
  const otherNodes = nodes.filter((n) => n.kind !== 'hub' && n.kind !== 'concept');

  nodes.forEach((n) => {
    if (!forceReset && store.nodePositions[n.id]) return;
    if (n.kind === 'hub') {
      store.nodePositions[n.id] = { x: cx, y: cy };
      return;
    }
    const pIdx = primaryConcepts.findIndex((c) => c.id === n.id);
    if (pIdx !== -1) {
      const ring = pIdx % 2 === 0 ? 155 : 210;
      const angle = (2 * Math.PI * pIdx) / Math.max(1, primaryConcepts.length) - Math.PI / 2;
      store.nodePositions[n.id] = {
        x: Math.round(cx + ring * Math.cos(angle)),
        y: Math.round(cy + ring * Math.sin(angle)),
      };
      return;
    }
    const oIdx = Math.max(0, otherNodes.findIndex((o) => o.id === n.id));
    const angle = (2 * Math.PI * oIdx) / Math.max(1, otherNodes.length) + 0.35;
    store.nodePositions[n.id] = {
      x: Math.round(cx + 250 * Math.cos(angle)),
      y: Math.round(cy + 250 * Math.sin(angle)),
    };
  });
}

function nodeMatchesFilter(n, q) {
  if (q) {
    const hay = `${n.label || ''} ${n.summary || ''} ${n.category || ''}`.toLowerCase();
    if (!hay.includes(q)) return false;
  }
  const f = store.currentGraphFilter;
  if (f === 'all' || n.kind === 'hub') return true;
  if (f === 'concept') return n.kind === 'concept';
  if (['memoria', 'agenti', 'voce', 'sicurezza'].includes(f)) return n.category === f;
  if (f === 'insight') return n.kind === 'insight';
  if (f === 'skill') return n.kind === 'skill';
  if (f === 'task') return (n.kind || '').startsWith('task_');
  return n.category === f;
}

export function renderKnowledgeGraphSvg() {
  const svg = document.getElementById('mcp-graph-svg');
  if (!svg) return;
  const q = (document.getElementById('graph-search-input')?.value || '').trim().toLowerCase();
  const allNodes = store.cachedGraphData.nodes || [];
  const allEdges = store.cachedGraphData.edges || [];
  const nodes = allNodes.filter((n) => nodeMatchesFilter(n, q));
  const visibleIds = new Set(nodes.map((n) => n.id));
  const edges = allEdges.filter((e) => visibleIds.has(e.source) && visibleIds.has(e.target));

  if (!nodes.length) {
    svg.innerHTML = '<text x="460" y="280" fill="#94a3b8" text-anchor="middle" font-size="14">Nessun concetto corrispondente</text>';
    return;
  }

  const colorByKind = {
    hub: '#38bdf8',
    concept: '#c084fc',
    insight: '#34d399',
    skill: '#fbbf24',
    task_active: '#fbbf24',
    task_archived: '#818cf8',
  };
  const catColor = {
    memoria: '#38bdf8',
    architettura: '#c084fc',
    agenti: '#fbbf24',
    voce: '#34d399',
    sicurezza: '#f87171',
  };

  let html = `<g transform="translate(${store.graphPanX}, ${store.graphPanY}) scale(${store.graphZoom})">`;
  edges.forEach((e) => {
    const s = store.nodePositions[e.source];
    const t = store.nodePositions[e.target];
    if (!s || !t) return;
    const mx = (s.x + t.x) / 2;
    const my = (s.y + t.y) / 2;
    const stroke = e.kind === 'macro' ? '#fbbf24' : e.kind === 'insight_link' ? '#34d399' : '#2b3f66';
    const dash = e.kind === 'macro' ? 'stroke-dasharray="5,4"' : '';
    html += `
      <line x1="${s.x}" y1="${s.y}" x2="${t.x}" y2="${t.y}" stroke="${stroke}" stroke-width="1.8" ${dash} opacity="0.82" />
      <text x="${mx}" y="${my - 4}" fill="#64748b" font-size="9.5" font-family="monospace" text-anchor="middle">${escapeHtml(e.relation || '')}</text>
    `;
  });

  nodes.forEach((n) => {
    const p = store.nodePositions[n.id];
    if (!p) return;
    const isCore = Boolean(n.is_framework_core);
    const col = n.kind === 'concept' ? (catColor[n.category] || '#c084fc') : (colorByKind[n.kind] || '#38bdf8');
    const r = n.kind === 'hub' ? 18 : n.kind === 'concept' ? 13 : 10;
    const rawLabel = String(n.label || n.key || n.id);
    const shortLabel = rawLabel.length > 26 ? `${rawLabel.slice(0, 23)}…` : rawLabel;
    const coreBorder = isCore ? 'stroke="#38bdf8" stroke-width="3"' : 'stroke="#070b14" stroke-width="2"';
    html += `
      <g class="graph-node" data-node-id="${escapeHtml(n.id)}" style="cursor:pointer;">
        <title>${escapeHtml(rawLabel)}</title>
        <circle cx="${p.x}" cy="${p.y}" r="${r + 5}" fill="${col}" opacity="${isCore ? '0.28' : '0.14'}" />
        <circle cx="${p.x}" cy="${p.y}" r="${r}" fill="${col}" ${coreBorder} />
        ${isCore ? `<circle cx="${p.x}" cy="${p.y}" r="${r + 2.5}" fill="none" stroke="#fff" stroke-width="1" opacity="0.8" />` : ''}
        <rect x="${p.x - Math.min(105, shortLabel.length * 3.7 + 10)}" y="${p.y + r + 5}" width="${Math.min(210, shortLabel.length * 7.4 + 20)}" height="19" rx="5" fill="rgba(7,11,20,0.88)" stroke="${isCore ? 'rgba(56,189,248,0.5)' : 'rgba(192,132,252,0.3)'}" />
        <text x="${p.x}" y="${p.y + r + 18}" fill="#f1f5f9" font-size="11" font-weight="600" text-anchor="middle">${escapeHtml(shortLabel)}</text>
      </g>
    `;
  });

  html += '</g>';
  svg.innerHTML = html;
}

export function initGraphCanvasInteractions() {
  const wrap = document.getElementById('graph-canvas-container');
  const svg = document.getElementById('mcp-graph-svg');
  if (!wrap || !svg) return;

  svg.addEventListener('mousedown', (e) => {
    const nodeG = e.target.closest('.graph-node[data-node-id]');
    if (nodeG) {
      e.stopPropagation();
      const id = nodeG.getAttribute('data-node-id');
      store.draggedNodeId = id;
      inspectConceptById(id);
    }
  });

  wrap.addEventListener('mousedown', (e) => {
    if (store.draggedNodeId) return;
    store.isPanningGraph = true;
    store.panStartX = e.clientX - store.graphPanX;
    store.panStartY = e.clientY - store.graphPanY;
  });

  window.addEventListener('mousemove', (e) => {
    if (store.draggedNodeId && store.nodePositions[store.draggedNodeId]) {
      const rect = svg.getBoundingClientRect();
      const svgX = ((e.clientX - rect.left) * (920 / rect.width) - store.graphPanX) / store.graphZoom;
      const svgY = ((e.clientY - rect.top) * (560 / rect.height) - store.graphPanY) / store.graphZoom;
      store.nodePositions[store.draggedNodeId] = { x: Math.round(svgX), y: Math.round(svgY) };
      renderKnowledgeGraphSvg();
    } else if (store.isPanningGraph) {
      store.graphPanX = e.clientX - store.panStartX;
      store.graphPanY = e.clientY - store.panStartY;
      renderKnowledgeGraphSvg();
    }
  });

  window.addEventListener('mouseup', () => {
    store.draggedNodeId = null;
    store.isPanningGraph = false;
  });
}

export function inspectConceptById(nodeId) {
  const node = (store.cachedGraphData.nodes || []).find((n) => n.id === nodeId);
  if (!node) return;
  store.selectedConceptNode = node;

  const isCore = Boolean(node.is_framework_core);
  const badgeEl = document.getElementById('cd-badge');
  if (badgeEl) {
    badgeEl.textContent = isCore
      ? `🔒 PILASTRO FRAMEWORK (${(node.category || 'core').toUpperCase()})`
      : `✨ CONCETTO UTENTE (${(node.category || 'utente').toUpperCase()})`;
    badgeEl.style.background = isCore ? 'rgba(56,189,248,0.2)' : 'rgba(192,132,252,0.2)';
    badgeEl.style.borderColor = isCore ? 'var(--accent)' : 'var(--violet)';
  }
  document.getElementById('cd-title').textContent = node.label || node.key;
  document.getElementById('cd-summary-l1').textContent = node.summary || 'Nessuna sintesi L1.';
  document.getElementById('cd-summary-l2').textContent = node.summary_medium || node.summary || 'Nessun dettaglio L2.';
  const l3El = document.getElementById('cd-summary-l3');
  if (l3El) l3El.textContent = node.summary_high || node.summary_medium || node.summary || 'Nessun dettaglio tecnico L3.';
  const maxEl = document.getElementById('cd-summary-max');
  if (maxEl) maxEl.textContent = node.raw_content || node.summary_high || node.summary_medium || node.summary || 'Nessun contenuto raw +1.';

  const cfgForm = document.getElementById('cd-config-form');
  const cfg = node.config || {};
  const cfgKeys = Object.keys(cfg);
  if (cfgKeys.length > 0) {
    cfgForm.innerHTML =
      cfgKeys.map((k) => `
        <div class="cfg-row">
          <label>${escapeHtml(k.replace(/_/g, ' ').toUpperCase())}:</label>
          <input id="cfg-input-${escapeHtml(k)}" type="${typeof cfg[k] === 'number' ? 'number' : 'text'}" value="${escapeHtml(cfg[k])}" />
        </div>
      `).join('') +
      `<button type="button" class="btn" style="width:100%; margin-top:6px;" data-concept-save="${escapeHtml(node.id)}">💾 Salva Configurazione</button>`;
  } else {
    cfgForm.innerHTML = `
      <div style="color:var(--muted); font-size:0.75rem; margin-bottom:6px;">Nessun parametro definito.</div>
      <button type="button" class="btn btn-ghost btn-sm" data-concept-add-field="${escapeHtml(node.id)}">+ Aggiungi Parametro</button>
    `;
  }

  const delBox = document.getElementById('cd-delete-box');
  delBox.innerHTML = isCore
    ? `<div style="font-size:0.72rem; color:var(--muted); background:rgba(255,255,255,0.03); border:1px solid var(--border); border-radius:7px; padding:7px 9px;">🔒 Pilastro core configurabile ma protetto da eliminazione.</div>`
    : `<button type="button" class="btn btn-danger" style="width:100%;" data-concept-delete="${escapeHtml(node.id)}">🗑️ Elimina Concetto</button>`;

  const connected = (store.cachedGraphData.edges || [])
    .filter((e) => e.source === node.id || e.target === node.id)
    .map((e) => {
      const otherId = e.source === node.id ? e.target : e.source;
      const other = (store.cachedGraphData.nodes || []).find((n) => n.id === otherId);
      return `• [${e.relation}] → ${other ? other.label : otherId}`;
    });
  document.getElementById('cd-connections').textContent = connected.length ? connected.join('\n') : 'Nessuna connessione diretta.';
  document.getElementById('cd-sources').textContent = (node.sources || ['/']).join(', ');
}

export async function saveSelectedConceptConfig(conceptId) {
  if (!store.selectedConceptNode) return;
  const cfg = store.selectedConceptNode.config || {};
  const updates = {};
  Object.keys(cfg).forEach((k) => {
    const input = document.getElementById(`cfg-input-${k}`);
    if (input) updates[k] = typeof cfg[k] === 'number' ? (parseFloat(input.value) || 0) : input.value;
  });
  await apiPost('/api/graph/concept/config', { concept_id: conceptId, config: updates });
  await loadMcpKnowledgeGraph();
  inspectConceptById(conceptId);
}

export function deleteSelectedConcept(nodeId) {
  openTaskActionModal({
    title: `🗑️ Elimina Concetto ${nodeId}`,
    desc: `Confermi l'eliminazione definitiva di "${nodeId}" dal grafo della memoria?`,
    showInput: false,
    confirmLabel: '🗑️ Elimina Concetto',
    confirmDanger: true,
    onConfirm: async () => {
      const d = await apiPost('/api/graph/concept/delete', { node_id: nodeId });
      if (d.error) {
        appendStreamCard('permission', 'ELIMINAZIONE NEGATA', nodeId, d.error, '');
        return;
      }
      store.selectedConceptNode = null;
      document.getElementById('cd-title').textContent = 'Seleziona un concetto';
      document.getElementById('cd-config-form').innerHTML = 'Clicca su un nodo del grafo.';
      document.getElementById('cd-delete-box').innerHTML = '';
      await refreshAgents();
      await loadMcpKnowledgeGraph();
    },
  });
}

export function addCustomConfigField(conceptId) {
  openTaskActionModal({
    title: `➕ Nuovo Parametro (${conceptId})`,
    desc: 'Formato "chiave=valore" (es: timeout_sec=30):',
    defaultValue: 'timeout_sec=30',
    showInput: true,
    confirmLabel: '💾 Aggiungi',
    onConfirm: async (raw) => {
      const text = String(raw || '').trim();
      if (!text) return;
      const eq = text.indexOf('=');
      const key = (eq >= 0 ? text.slice(0, eq) : text).trim();
      const val = (eq >= 0 ? text.slice(eq + 1) : 'default').trim();
      if (!key) return;
      if (!store.selectedConceptNode.config) store.selectedConceptNode.config = {};
      store.selectedConceptNode.config[key] = val || 'default';
      await saveSelectedConceptConfig(conceptId);
    },
  });
}

function toYamlView(val, indent = 0) {
  const pad = '  '.repeat(indent);
  if (val === null || val === undefined) return 'null';
  if (typeof val === 'string') return val.includes('\n') ? `|\n${val.split('\n').map((l) => `${pad}  ${l}`).join('\n')}` : val;
  if (typeof val !== 'object') return String(val);
  if (Array.isArray(val)) {
    if (!val.length) return '[]';
    return val.map((item) => {
      const rendered = toYamlView(item, indent + 1);
      return (item && typeof item === 'object') ? `${pad}- \n${rendered}` : `${pad}- ${rendered}`;
    }).join('\n');
  }
  const keys = Object.keys(val);
  if (!keys.length) return '{}';
  return keys.map((k) => {
    const v = val[k];
    if (v && typeof v === 'object' && (!Array.isArray(v) || v.length) && (Array.isArray(v) || Object.keys(v).length)) {
      return `${pad}${k}:\n${toYamlView(v, indent + 1)}`;
    }
    return `${pad}${k}: ${toYamlView(v, indent + 1)}`;
  }).join('\n');
}

export async function loadSmartMemory() {
  try {
    const d = await apiGet('/api/memory/state');
    const memView = document.getElementById('memory-state-view');
    if (memView) memView.textContent = toYamlView(d);
  } catch (err) {
    console.error('Errore loadSmartMemory:', err);
  }
}

export async function navigateWiki(path = '/') {
  store.currentWikiPath = path;
  const depth = document.getElementById('wiki-depth')?.value || 'medium';
  try {
    const d = await apiGet(`/api/wiki/navigate?path=${encodeURIComponent(path)}&depth=${depth}`);
    const wikiView = document.getElementById('wiki-node-view');
    if (wikiView) wikiView.textContent = toYamlView(d);
  } catch (err) {
    console.error('Errore navigateWiki:', err);
  }
}

export async function loadSkillsHub() {
  try {
    const d = await apiGet('/api/skills/state');
    const box = document.getElementById('skills-list-view');
    if (!box) return;
    box.innerHTML = (d.skills || [])
      .map((s) => `
        <div class="fs-row" style="flex-direction:column; align-items:stretch;">
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <b style="color:${s.category === 'memory_tier' ? 'var(--accent)' : s.category === 'learned' ? 'var(--emerald)' : 'var(--text)'};">${escapeHtml(s.name)}</b>
            <span class="status-pill">${escapeHtml(s.category)}</span>
          </div>
          <div style="color:var(--muted); font-size:0.72rem; margin-top:2px;">${escapeHtml(s.description)}</div>
        </div>
      `)
      .join('');
    await loadPlatformSources();
  } catch (err) {
    console.error('Errore loadSkillsHub:', err);
  }
}

export async function loadPlatformSources() {
  const box = document.getElementById('platform-sources-view');
  if (!box) return;
  try {
    const d = await apiGet('/api/platform/sources');
    const sources = d.sources || [];
    if (!sources.length) {
      box.innerHTML = `<div style="color:var(--muted); font-size:0.74rem;">Nessuna skill esterna trovata in ~/.gemini, ~/.codex o ~/.claude.</div>`;
      return;
    }
    box.innerHTML = sources.map((s) => `
      <div class="fs-row" style="justify-content:space-between; align-items:center; gap:8px;">
        <div style="min-width:0; flex:1;">
          <div style="display:flex; align-items:center; gap:6px;">
            <span class="status-pill">${escapeHtml(s.platform)}</span>
            <b>${escapeHtml(s.name)}</b>
            ${s.imported ? '<span class="status-pill status-completed">Importata</span>' : ''}
          </div>
          <div style="color:var(--muted); font-size:0.71rem; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${escapeHtml(s.description || s.path)}</div>
        </div>
        <button type="button" class="btn ${s.imported ? 'btn-ghost' : ''} btn-sm" data-platform-import="${escapeHtml(s.name)}">${s.imported ? '↻ Aggiorna 3+1' : '📥 Importa'}</button>
      </div>
    `).join('');
  } catch (err) {
    console.error('Errore loadPlatformSources:', err);
  }
}

export async function importPlatformSkill(name) {
  if (!name) return;
  const d = await apiPost('/api/platform/import', { name });
  if (d.error) {
    appendStreamCard('permission', 'IMPORT FALLITO', name, d.error, '');
    return;
  }
  await loadSkillsHub();
  await loadMcpKnowledgeGraph();
}

export async function loadModelsConfig() {
  const liveBar = document.getElementById('models-ctx-live-bar');
  const roleBox = document.getElementById('role-models-form');
  const winBox = document.getElementById('model-windows-list');
  const newRoleModelSel = document.getElementById('new-role-model');
  const presetsSel = document.getElementById('model-pull-presets');
  if (!roleBox || !winBox) return;
  try {
    const scopeId = store.selectedSessionId || store.activeChatId || 'chat';
    const d = await apiGet(`/api/models/config?scope_id=${encodeURIComponent(scopeId)}`);
    const tel = d.context_telemetry || {};
    if (liveBar) {
      liveBar.innerHTML = `
        <b>📊 Occupazione Contesto Live (${escapeHtml(tel.scope_id || 'chat')}):</b>
        <code>${tel.used_tokens || 0} / ${tel.context_window_tokens || 32768} tok</code>
        (<b>${tel.occupancy_pct ?? 0}%</b>) · Liberi: <code>${tel.remaining_tokens || 0}</code> ·
        Modello attivo: <code>${escapeHtml(tel.active_model || '')}</code> · Strategia: <code>${escapeHtml(tel.strategy || 'direct')}</code>
      `;
    }
    const avail = d.available_models || [];
    const roles = Array.isArray(d.roles) && d.roles.length
      ? d.roles
      : [
          { id: 'coordinator', label: 'Coordinator (Orchestrazione)', model: (d.role_models || {}).coordinator_model || 'qwen3.8:27b-iq2_xxs', context_window: 32768, effort: 'medium', builtin: true },
          { id: 'analyst', label: 'Analyst (Ricerca & Piano)', model: (d.role_models || {}).analyst_model || 'qwen3.8:27b-iq2_xxs', context_window: 32768, effort: 'medium', builtin: true },
          { id: 'implementer', label: 'Implementer (Codice & Azione)', model: (d.role_models || {}).implementer_model || 'qwen3.8:27b-iq2_xxs', context_window: 32768, effort: 'medium', builtin: true },
          { id: 'reviewer', label: 'Reviewer (Verifica & Test)', model: (d.role_models || {}).reviewer_model || 'qwen3.8:27b-iq2_xxs', context_window: 16384, effort: 'medium', builtin: true },
          { id: 'chat', label: 'Chat Generale (Conversazione)', model: (d.role_models || {}).chat_model || 'qwen3.8:27b-iq2_xxs', context_window: 32768, effort: 'medium', builtin: true },
        ];

    if (newRoleModelSel) {
      newRoleModelSel.innerHTML = avail.map((m) => `<option value="${escapeHtml(m)}">${escapeHtml(m)}</option>`).join('');
    }
    if (presetsSel && Array.isArray(d.presets)) {
      presetsSel.innerHTML = '<option value="">Scegli preset consigliato...</option>' + d.presets.map((p) =>
        `<option value="${escapeHtml(p.id)}">${escapeHtml(p.label)}</option>`
      ).join('');
    }

    roleBox.innerHTML = roles.map((r) => {
      const cur = r.model || avail[0] || 'qwen3.8:27b-iq2_xxs';
      const opts = Array.from(new Set([...avail, cur])).map((m) =>
        `<option value="${escapeHtml(m)}" ${m === cur ? 'selected' : ''}>${escapeHtml(m)}</option>`
      ).join('');
      const eff = r.effort || 'medium';
      const toolsStr = Array.isArray(r.tools) && r.tools.length ? r.tools.join(', ') : 'llm';
      return `
        <div class="fs-row" style="flex-direction:column; align-items:stretch; gap:6px; padding:8px 10px; border:1px solid var(--border); border-radius:8px;">
          <div style="display:flex; justify-content:space-between; align-items:center; gap:6px;">
            <span style="font-size:0.78rem; font-weight:700;">${escapeHtml(r.label || r.id)}</span>
            <div style="display:flex; align-items:center; gap:4px;">
              <span class="status-pill" title="Tools: ${escapeHtml(toolsStr)}">${escapeHtml(r.id)}</span>
              ${r.builtin ? '' : `<button type="button" class="btn btn-ghost btn-sm" data-role-delete="${escapeHtml(r.id)}" title="Rimuovi ruolo">🗑️</button>`}
            </div>
          </div>
          ${r.description ? `<div style="font-size:0.7rem; color:var(--muted);">${escapeHtml(r.description)}</div>` : ''}
          <select data-role-model="${escapeHtml(r.id)}_model" style="font-size:0.76rem;">${opts}</select>
          <div style="display:flex; gap:6px; align-items:center;">
            <label style="display:flex; align-items:center; gap:4px; font-size:0.72rem; color:var(--muted); flex:1;">
              Ctx:
              <input type="number" min="2048" max="262144" step="1024" value="${Number(r.context_window || 16384)}" data-role-window="${escapeHtml(r.id)}" style="width:88px; font-family:var(--mono); font-size:0.74rem;" />
            </label>
            <select data-role-effort="${escapeHtml(r.id)}" style="width:92px; font-size:0.72rem;">
              <option value="low" ${eff === 'low' ? 'selected' : ''}>low</option>
              <option value="medium" ${eff === 'medium' ? 'selected' : ''}>medium</option>
              <option value="high" ${eff === 'high' ? 'selected' : ''}>high</option>
            </select>
          </div>
        </div>
      `;
    }).join('');

    const models = d.models || [];
    winBox.innerHTML = models.map((m) => `
      <div class="fs-row" style="justify-content:space-between; align-items:center; gap:8px; margin-bottom:6px; flex-wrap:wrap;">
        <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap;">
          <code>${escapeHtml(m.model)}</code>
          <span class="status-pill">${m.installed ? 'locale' : 'configurato'}</span>
          ${m.size_gb ? `<span class="status-pill">${Number(m.size_gb)} GB</span>` : ''}
          ${m.is_duplicate ? `<span class="status-pill" style="background:rgba(245,158,11,0.2); color:#fbbf24;" title="Variante della stessa famiglia presente">⚠️ variante</span>` : ''}
        </div>
        <div style="display:flex; align-items:center; gap:6px;">
          <input type="number" min="2048" max="262144" step="1024" value="${Number(m.context_window || 32768)}" data-model-window="${escapeHtml(m.model)}" style="width:105px; font-family:var(--mono);" />
          <span style="font-size:0.72rem; color:var(--muted);">tok</span>
          ${m.installed ? `<button type="button" class="btn btn-ghost btn-sm" data-model-delete="${escapeHtml(m.model)}" title="Rimuovi da Ollama">🗑️</button>` : ''}
        </div>
      </div>
    `).join('');
  } catch (err) {
    console.error('Errore loadModelsConfig:', err);
  }
}

export async function saveModelsConfig() {
  const roleModels = {};
  document.querySelectorAll('[data-role-model]').forEach((el) => {
    const k = el.getAttribute('data-role-model');
    if (k && el.value) roleModels[k] = el.value;
  });
  const roleContextWindows = {};
  document.querySelectorAll('[data-role-window]').forEach((el) => {
    const rid = el.getAttribute('data-role-window');
    const v = parseInt(el.value, 10);
    if (rid && Number.isFinite(v) && v >= 2048) roleContextWindows[rid] = v;
  });
  const roleEfforts = {};
  document.querySelectorAll('[data-role-effort]').forEach((el) => {
    const rid = el.getAttribute('data-role-effort');
    if (rid && el.value) roleEfforts[rid] = el.value;
  });
  const modelWindows = {};
  document.querySelectorAll('[data-model-window]').forEach((el) => {
    const m = el.getAttribute('data-model-window');
    const v = parseInt(el.value, 10);
    if (m && Number.isFinite(v) && v >= 2048) modelWindows[m] = v;
  });
  await apiPost('/api/models/config', {
    scope_id: store.selectedSessionId || store.activeChatId || 'chat',
    role_models: roleModels,
    role_context_windows: roleContextWindows,
    role_efforts: roleEfforts,
    model_context_windows: modelWindows,
  });
  await loadModelsConfig();
}

export async function pullOllamaModelAction() {
  const inp = document.getElementById('model-pull-input');
  const statusEl = document.getElementById('model-pull-status');
  const modelName = (inp?.value || '').trim();
  if (!modelName) return;
  if (statusEl) statusEl.textContent = `⏳ Download di ${modelName} in corso...`;
  try {
    const res = await apiPost('/api/models/pull', { model: modelName });
    if (statusEl) statusEl.textContent = res.ok ? `✅ Modello ${modelName} scaricato!` : `❌ ${res.error || 'Errore download'}`;
    if (res.ok && inp) inp.value = '';
    await loadModelsConfig();
  } catch (err) {
    if (statusEl) statusEl.textContent = `❌ ${err.message || err}`;
  }
}

export async function deleteOllamaModelAction(modelName) {
  if (!modelName) return;
  const statusEl = document.getElementById('model-pull-status');
  if (statusEl) statusEl.textContent = `🗑️ Rimozione di ${modelName}...`;
  try {
    const res = await apiPost('/api/models/delete', { model: modelName });
    if (statusEl) statusEl.textContent = res.ok ? `✅ Modello ${modelName} rimosso.` : `❌ ${res.error || 'Errore rimozione'}`;
    await loadModelsConfig();
  } catch (err) {
    if (statusEl) statusEl.textContent = `❌ ${err.message || err}`;
  }
}

export async function addCustomRoleAction() {
  const idEl = document.getElementById('new-role-id');
  const labelEl = document.getElementById('new-role-label');
  const modelEl = document.getElementById('new-role-model');
  const ctxEl = document.getElementById('new-role-ctx');
  const id = (idEl?.value || '').trim();
  if (!id) return;
  await apiPost('/api/roles/add', {
    id,
    label: (labelEl?.value || '').trim() || id,
    model: (modelEl?.value || '').trim() || 'qwen3.8:27b-iq2_xxs',
    context_window: parseInt(ctxEl?.value || '16384', 10) || 16384,
  });
  if (idEl) idEl.value = '';
  if (labelEl) labelEl.value = '';
  await loadModelsConfig();
}

export async function deleteCustomRoleAction(roleId) {
  if (!roleId) return;
  await apiPost('/api/roles/delete', { id: roleId });
  await loadModelsConfig();
}

export async function loadChromeProfiles() {
  const sel = document.getElementById('chrome-profile-select');
  const customInp = document.getElementById('chrome-profile-custom');
  const statusEl = document.getElementById('chrome-profile-status');
  if (!sel) return;
  try {
    const d = await apiGet('/api/chrome/profiles');
    const profiles = Array.isArray(d.profiles) ? d.profiles : [];
    const selected = d.selected || {};
    sel.innerHTML = profiles.map((p) => {
      const isSel = (selected.mode === p.mode && (p.mode !== 'system_chrome' || selected.profile_directory === p.profile_directory));
      return `<option value="${escapeHtml(p.id)}" data-mode="${escapeHtml(p.mode)}" data-dir="${escapeHtml(p.profile_directory || '')}" data-user-data="${escapeHtml(p.user_data_dir || '')}" data-email="${escapeHtml(p.email || '')}" ${isSel ? 'selected' : ''}>${escapeHtml(p.label)}</option>`;
    }).join('');
    if (customInp && selected.profile_directory) customInp.value = selected.profile_directory;
    if (statusEl) {
      statusEl.textContent = d.tcc_restricted
        ? '⚠️ macOS privacy blocca lettura profili locali; usa Attach :9222 o inserisci il nome profilo.'
        : (d.debug_port_active ? '🟢 Chrome debug :9222 attivo' : '⚪ Profilo pronto');
    }
  } catch (err) {
    console.warn('loadChromeProfiles:', err);
  }
}

export async function saveChromeProfile() {
  const sel = document.getElementById('chrome-profile-select');
  const customInp = document.getElementById('chrome-profile-custom');
  const statusEl = document.getElementById('chrome-profile-status');
  const opt = sel?.selectedOptions?.[0];
  const mode = opt?.getAttribute('data-mode') || (sel?.value === 'attach_existing' ? 'attach_existing' : 'cortical_isolated');
  const customVal = (customInp?.value || '').trim();
  const payload = {
    mode,
    profile_directory: customVal || opt?.getAttribute('data-dir') || 'Default',
    user_data_dir: opt?.getAttribute('data-user-data') || '',
    email: opt?.getAttribute('data-email') || (customVal.includes('@') ? customVal : ''),
  };
  const res = await apiPost('/api/chrome/profile', payload);
  if (statusEl && res.ok) statusEl.textContent = `✅ Salvato (${payload.mode}: ${payload.profile_directory || 'auto'})`;
}

export async function testPromptEnhancer() {
  const prompt = (document.getElementById('skill-test-input')?.value || '').trim();
  if (!prompt) return;
  const d = await apiPost('/api/skills/enhance', { prompt });
  document.getElementById('skill-enhance-view').textContent =
    `[Mode]: ${d.mode} | [Livello 3+1]: ${d.recommended_depth}\n` +
    `[Memory Skill]: ${d.memory_tier_skill}\n` +
    `[Procedural Skills]: ${(d.selected_procedural_skills || []).join(', ')}\n` +
    `[Team Roster]: ${(d.team_roster || []).map((x) => x.id).join(' -> ')}\n\n` +
    (d.context_injection || '(Conversazione casual)');
}

export async function evalPerm() {
  const tool = document.getElementById('perm-tool').value;
  const cmd = document.getElementById('perm-cmd').value;
  const d = await apiPost('/api/permissions/evaluate', { tool, args: { command: cmd, path: cmd } });
  document.getElementById('perm-view').textContent = toYamlView(d);
}

export async function feedbackPerm(approved) {
  const tool = document.getElementById('perm-tool').value;
  const cmd = document.getElementById('perm-cmd').value;
  const d = await apiPost('/api/permissions/feedback', { tool, args: { command: cmd, path: cmd }, approved, remember: true });
  document.getElementById('perm-view').textContent = toYamlView(d);
}

export async function refreshEgressAudit() {
  try {
    const d = await apiGet('/api/security/egress?limit=40');
    const pill = document.getElementById('security-egress-pill');
    const count = Number(d.total_blocked || 0);
    if (pill) {
      pill.textContent = count > 0 ? `🛡️ ${count} bloccati` : '🛡️ Isolato';
      pill.style.borderColor = count > 0 ? 'rgba(248,113,113,0.65)' : '';
      pill.style.color = count > 0 ? 'var(--danger, #f87171)' : '';
    }
    const view = document.getElementById('egress-audit-view');
    if (view) {
      const evs = d.events || [];
      if (!evs.length) {
        view.textContent = `Isolamento stretto attivo (proxy :${d.proxy_port || 'auto'}).\nNessun tentativo di esfiltrazione o connessione esterna rilevato.`;
      } else {
        view.textContent = evs
          .map((e) => `[${new Date((e.created_at || 0) * 1000).toLocaleTimeString()}] BLOCKED (${e.source}) ${e.model || 'local'} -> ${e.target_host || e.target_url}\n  Motivo: ${e.reason}\n  Intent: ${e.payload_excerpt || e.target_url || ''}`)
          .join('\n\n');
      }
    }
  } catch (_) {}
}

export async function clearEgressAudit() {
  await apiPost('/api/security/egress', { action: 'clear' });
  await refreshEgressAudit();
}

export function openCenterConceptModal() {
  const node = store.selectedConceptNode;
  if (!node) return;
  const ov = document.getElementById('concept-editor-modal-overlay');
  const titleEl = document.getElementById('ce-title');
  const sumEl = document.getElementById('ce-summary');
  const stEl = document.getElementById('ce-status');
  if (titleEl) titleEl.value = node.config?.custom_label || node.label || node.key || node.id;
  if (sumEl) sumEl.value = node.config?.custom_summary || node.summary_medium || node.summary || '';
  if (stEl) stEl.textContent = node.config?.promoted_skill ? `✅ Già promosso a skill globale: ${node.config.promoted_skill}` : '';
  if (ov) ov.classList.add('open');
}

export function closeCenterConceptModal() {
  document.getElementById('concept-editor-modal-overlay')?.classList.remove('open');
}

export async function saveCenterConceptAndPromote(promote = false) {
  const node = store.selectedConceptNode;
  if (!node) return;
  const title = (document.getElementById('ce-title')?.value || '').trim() || node.label || node.id;
  const summary = (document.getElementById('ce-summary')?.value || '').trim();
  const stEl = document.getElementById('ce-status');
  if (promote) {
    const res = await apiPost('/api/graph/concept/promote', {
      concept_id: node.id,
      title,
      summary,
      category: node.category || 'custom',
      config: node.config || {},
    });
    if (stEl) stEl.textContent = `⚡ Promosso a Skill globale: ${res.skill_name} (${res.skill_path})`;
    await loadSkillsHub();
  } else {
    await apiPost('/api/graph/concept/config', {
      concept_id: node.id,
      config: { custom_label: title, custom_summary: summary },
    });
    if (stEl) stEl.textContent = `💾 Concetto salvato: "${title}"`;
  }
  await loadMcpKnowledgeGraph();
  inspectConceptById(node.id);
}
