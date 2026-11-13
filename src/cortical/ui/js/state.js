/**
 * Shared frontend state, safe HTML/prose formatting, bilingual IT/EN dictionary, and interactive docs.
 */

export const store = {
  uiLang: localStorage.getItem('cortical_ui_lang') || 'it',
  effort: localStorage.getItem('cortical_effort') || 'medium',
  audioResponsesEnabled: true,
  activeChatId: 'chat',
  selectedSessionId: null,
  sidebarFilter: 'all',
  taskQuery: '',
  taskPageLimit: 15,
  taskHasMore: false,
  loadedChats: [],
  loadedSessions: [],
  cachedAttachments: [],
  cachedCatalog: { skills: [], plugins: [], mcp_servers: [] },
  lastRosterSig: '',
  lastStreamSig: '',
  forceStreamRender: false,
  currentWikiPath: '/',
  cachedGraphData: { nodes: [], edges: [], stats: {} },
  currentGraphFilter: 'all',
  selectedConceptNode: null,
  graphZoom: 1.0,
  graphPanX: 0,
  graphPanY: 0,
  nodePositions: {},
  draggedNodeId: null,
  isPanningGraph: false,
  panStartX: 0,
  panStartY: 0,
  activeAbortController: null,
};

export function escapeHtml(val) {
  return String(val ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/**
 * Formats escaped prose cleanly into paragraphs and inline code spans without unsafe raw HTML.
 */
export function formatProseHtml(rawText) {
  const text = String(rawText ?? '').trim();
  if (!text) return '';
  const paragraphs = text.split(/\n{2,}/);
  return paragraphs
    .map((p) => {
      const escaped = escapeHtml(p)
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
        .replace(/\n/g, '<br/>');
      return `<p>${escaped}</p>`;
    })
    .join('');
}

export function activeScopeId() {
  return store.selectedSessionId || store.activeChatId || 'chat';
}

export function activeScopeLabel() {
  if (store.selectedSessionId) return `🤖 ${store.selectedSessionId}`;
  const found = store.loadedChats.find((c) => c.chat_id === store.activeChatId);
  return `💬 ${found ? found.title : store.activeChatId === 'chat' ? 'Chat Generale' : store.activeChatId}`;
}

export const I18N = {
  it: {
    guideTitle: '📖 Guida Interattiva di Cortical v0.4 (IT / EN)',
    close: '✕ Chiudi',
    toggleLangBtn: '🇮🇹 Lingua: IT',
    drawerLangBtn: '🇬🇧 EN',
    tabStream: '💬 Workspace',
    tabGraph: '🧠 Concetti',
    tabBrain: '⚙️ Studio & Sicurezza',
    micOff: '🎤 Mic',
    micOn: '🟢 Mic ON',
    promptPlaceholder: 'Scrivi un messaggio, trascina un file o premi ⌘+Invio per avviare un Task...',
    liveReady: 'Pronto',
    duckNormal: '🔊 100%',
    duckLow: '🔉 14% Duck',
    newChatBtn: '+ 💬 Chat',
    newTaskBtn: '+ 🤖 Task',
    tooltipHint: '💡 Clicca per aprire la guida',
  },
  en: {
    guideTitle: '📖 Cortical v0.4 Interactive Guide (EN / IT)',
    close: '✕ Close',
    toggleLangBtn: '🇬🇧 Lang: EN',
    drawerLangBtn: '🇮🇹 IT',
    tabStream: '💬 Workspace',
    tabGraph: '🧠 Concepts',
    tabBrain: '⚙️ Studio & Safety',
    micOff: '🎤 Mic',
    micOn: '🟢 Mic ON',
    promptPlaceholder: 'Write a message, drop a file, or press ⌘+Enter to launch a Task...',
    liveReady: 'Ready',
    duckNormal: '🔊 100%',
    duckLow: '🔉 14% Duck',
    newChatBtn: '+ 💬 Chat',
    newTaskBtn: '+ 🤖 Task',
    tooltipHint: '💡 Click to open the interactive guide',
  },
};

export const GUIDE_DOCS = {
  it: {
    'doc-stream': ['⚡ Stream Operativo, Audio Ducking & Coordinatore Unico', 'Mostra in tempo reale la conversazione e i task multi-agente. Quando l\'audio è attivo, Cortical usa <b>Web Audio GainNode</b> + cancellazione eco WebRTC (<code>echoCancellation</code>), e fa parlare <b>solo il Coordinatore</b> una sola volta a fine team.'],
    'doc-attachments': ['📎 Contesto Isolato per Ogni Chat e Task', 'Ogni chat e ogni task ha allegati indipendenti. Puoi aggiungere file dal computer (anche con <b>Drag & Drop</b>), cartelle o file dal workspace, e <b>Skill / Plugin / MCP</b>. Clicca <b>×</b> su qualsiasi chip per rimuoverlo subito.'],
    'doc-graph': ['🧠 Grafo Semantico dei Concetti (MCP)', 'Visualizza i pilastri configurabili del framework (🔒) insieme a concetti utente, insight, skill e task. Trascina i nodi o cliccane uno per modificarne i parametri.'],
    'doc-concept-config': ['⚙️ Configurazione Parametri & Eliminazione Concetti', 'I pilastri core sono protetti da eliminazione ma configurabili dal vivo (es. loop massimi e modelli degli agenti). I concetti utente sono liberamente configurabili ed eliminabili.'],
    'doc-studio': ['🧭 Studio 3+1, Skill Router & Permission Gate', 'Ispeziona le sintesi nei 4 livelli (Light, Medium, High, Max), simula l\'arricchimento del prompt e verifica le regole dell\'Adaptive Permission Gate.'],
    'doc-tasks': ['🤖 Chat vs Task Multi-Agente', 'Le chat restano leggere e conversazionali; i task eseguono team di agenti locali (<code>pi</code>) con step tracciati, archiviazione nei 3+1 livelli e ripresa anche dopo archiviazione.'],
  },
  en: {
    'doc-stream': ['⚡ Live Workspace Stream, Ducking & Coordinator-Only Speech', 'Displays real-time chats and multi-agent tasks. With Audio ON, Cortical pairs <b>Web Audio GainNode</b> with hardware WebRTC <code>echoCancellation</code>, and speaks <b>only once from the Coordinator</b> after all working agents finish.'],
    'doc-attachments': ['📎 Scoped Context Attachments per Chat & Task', 'Every chat and task owns isolated attachments. Attach local files (via picker or <b>Drag & Drop</b>), workspace files/folders, and <b>Skills / Plugins / MCPs</b>. Click <b>×</b> on any chip to detach immediately.'],
    'doc-graph': ['🧠 Semantic Concept Knowledge Graph (MCP)', 'Displays core configurable pillars (🔒) connected to user concepts, insights, skills, and tasks. Drag nodes or click one to tune parameters.'],
    'doc-concept-config': ['⚙️ Concept Parameter Tuning & Deletion', 'Core framework pillars stay protected while allowing live tuning of loops and local models; user concepts can be configured or removed cleanly.'],
    'doc-studio': ['🧭 3+1 Context Studio, Skill Router & Safety Gate', 'Inspect L1–Max synthesis, simulate harness prompt enrichment, and evaluate Adaptive Permission Gate guardrails.'],
    'doc-tasks': ['🤖 Chats vs Multi-Agent Tasks', 'Chats stay fast and conversational; tasks run local <code>pi</code> agents with step telemetry, 3+1 archival, and post-archival reopening.'],
  },
};

export function applyUiTranslations(lang, onLanguageUpdated) {
  store.uiLang = lang === 'en' ? 'en' : 'it';
  localStorage.setItem('cortical_ui_lang', store.uiLang);
  const t = I18N[store.uiLang];
  const setTxt = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
  };
  setTxt('help-drawer-title', t.guideTitle);
  setTxt('btn-help-close', t.close);
  setTxt('btn-ui-lang', t.toggleLangBtn);
  setTxt('btn-drawer-lang', t.drawerLangBtn);
  setTxt('lbl-tab-stream', t.tabStream);
  setTxt('lbl-tab-graph', t.tabGraph);
  setTxt('lbl-tab-brain', t.tabBrain);
  setTxt('btn-new-chat', t.newChatBtn);
  setTxt('btn-new-task', t.newTaskBtn);
  const guideSet = GUIDE_DOCS[store.uiLang] || GUIDE_DOCS.it;
  Object.entries(guideSet).forEach(([secId, [title, body]]) => {
    const sec = document.getElementById(secId);
    if (sec) {
      const h4 = sec.querySelector('h4');
      const p = sec.querySelector('p');
      if (h4) h4.innerHTML = title;
      if (p) p.innerHTML = body;
    }
  });
  if (typeof onLanguageUpdated === 'function') {
    onLanguageUpdated(store.uiLang, t);
  }
}

export function openHelpSection(sectionId, event) {
  if (event) event.stopPropagation();
  const tooltip = document.getElementById('global-tooltip');
  if (tooltip) tooltip.style.display = 'none';
  const backdrop = document.getElementById('help-drawer-backdrop');
  if (backdrop) backdrop.style.display = 'flex';
  document.querySelectorAll('.doc-section').forEach((s) => s.classList.remove('highlight'));
  if (sectionId) {
    const target = document.getElementById(sectionId);
    if (target) {
      target.classList.add('highlight');
      setTimeout(() => target.scrollIntoView({ behavior: 'smooth', block: 'center' }), 50);
    }
  }
}

export function closeHelpDrawer(event) {
  if (event) event.stopPropagation();
  const backdrop = document.getElementById('help-drawer-backdrop');
  if (backdrop) backdrop.style.display = 'none';
}

export function initHelpTooltips() {
  const tooltip = document.getElementById('global-tooltip');
  if (!tooltip) return;
  const position = (e) => {
    let x = e.clientX + 12;
    let y = e.clientY + 12;
    if (x + 315 > window.innerWidth) x = Math.max(10, window.innerWidth - 325);
    if (y + 115 > window.innerHeight) y = Math.max(10, e.clientY - 88);
    tooltip.style.left = `${x}px`;
    tooltip.style.top = `${y}px`;
  };
  document.body.addEventListener('mouseover', (e) => {
    const target = e.target.closest('[data-tip]');
    if (!target) return;
    const tip = (store.uiLang === 'en' && target.getAttribute('data-tip-en'))
      ? target.getAttribute('data-tip-en')
      : target.getAttribute('data-tip');
    if (!tip) return;
    const hint = (I18N[store.uiLang] || I18N.it).tooltipHint;
    tooltip.innerHTML = `${escapeHtml(tip)}<span class="tt-hint">${escapeHtml(hint)}</span>`;
    tooltip.style.display = 'block';
    position(e);
  });
  document.body.addEventListener('mousemove', (e) => {
    if (tooltip.style.display === 'block') position(e);
  });
  document.body.addEventListener('mouseout', (e) => {
    if (e.target.closest('[data-tip]')) tooltip.style.display = 'none';
  });
  document.body.addEventListener('click', (e) => {
    if (e.target.closest('.help-btn')) tooltip.style.display = 'none';
  });
}
