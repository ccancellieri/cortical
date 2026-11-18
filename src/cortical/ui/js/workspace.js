/**
 * Unified Chat & Multi-Agent Task workspace controller:
 * sidebar list/filters/infinite-scroll, clean message bubbles & task step timeline,
 * action confirmation modal, composer submission, and barge-in stop control.
 */
import { apiGet, apiPost } from './api.js';
import {
  loadScopedContext,
  openCatalogModal,
} from './attachments.js';
import {
  audioState,
  detectLangClient,
  isAssistantAudioPlaying,
  isSelfEchoClient,
  hasWakeOrBargeInWord,
  normalizeTokens,
  playAssistantAudioUrl,
  stopAssistantAudio,
} from './audio.js';
import {
  I18N,
  escapeHtml,
  formatProseHtml,
  store,
} from './state.js';

let pendingTaskModal = null;
let taskSearchTimer = null;
let onGraphSyncCb = null;
let onStageSwitchCb = null;

export function configureWorkspaceHooks({ onGraphSync, onSwitchStage } = {}) {
  if (onGraphSync) onGraphSyncCb = onGraphSync;
  if (onSwitchStage) onStageSwitchCb = onSwitchStage;
}

export function openTaskActionModal({
  title,
  desc,
  defaultValue = '',
  showInput = true,
  confirmLabel = 'Conferma',
  confirmDanger = false,
  onConfirm,
}) {
  const overlay = document.getElementById('task-action-modal-overlay');
  const titleEl = document.getElementById('task-action-title');
  const descEl = document.getElementById('task-action-desc');
  const inputEl = document.getElementById('task-action-input');
  const confirmBtn = document.getElementById('task-action-confirm-btn');
  if (!overlay || !confirmBtn) return;

  pendingTaskModal = { onConfirm, showInput };
  if (titleEl) titleEl.textContent = title || 'Azione';
  if (descEl) descEl.textContent = desc || '';
  if (inputEl) {
    inputEl.value = defaultValue;
    inputEl.style.display = showInput ? 'block' : 'none';
  }
  confirmBtn.textContent = confirmLabel;
  confirmBtn.className = confirmDanger ? 'btn btn-danger' : 'btn';
  overlay.classList.add('open');
  if (showInput && inputEl) {
    setTimeout(() => {
      inputEl.focus();
      inputEl.select();
    }, 30);
  }
}

export function closeTaskActionModal(e) {
  if (e && e.target && e.target.id !== 'task-action-modal-overlay') return;
  document.getElementById('task-action-modal-overlay')?.classList.remove('open');
  pendingTaskModal = null;
}

export async function confirmTaskActionModal() {
  if (!pendingTaskModal) return;
  const inputEl = document.getElementById('task-action-input');
  const val = pendingTaskModal.showInput && inputEl ? inputEl.value : undefined;
  const cb = pendingTaskModal.onConfirm;
  closeTaskActionModal();
  if (cb) await cb(val);
}

function scrollStreamBottom() {
  const scrollWrap = document.getElementById('stream-scroll-area');
  if (scrollWrap) scrollWrap.scrollTop = scrollWrap.scrollHeight;
}

export function appendChatTurnCard(userText, assistantText, metaBadge = '') {
  const stream = document.getElementById('agent-stream');
  if (!stream) return null;
  stream.querySelector('.empty-state-card')?.remove();
  const turn = document.createElement('div');
  turn.className = 'chat-turn';
  turn.innerHTML = `
    <div class="msg-bubble msg-user">
      <div class="msg-meta"><span>Tu</span></div>
      <div class="msg-prose">${formatProseHtml(userText)}</div>
    </div>
    <div class="msg-bubble msg-assistant">
      <div class="msg-meta"><span>Cortical</span><span>${escapeHtml(metaBadge)}</span></div>
      <div class="msg-prose">${formatProseHtml(assistantText)}</div>
    </div>
  `;
  stream.appendChild(turn);
  scrollStreamBottom();
  return turn;
}

export function appendStreamCard(type, metaLeft, metaRight, title, detail) {
  const stream = document.getElementById('agent-stream');
  if (!stream) return null;
  stream.querySelector('.empty-state-card')?.remove();
  const div = document.createElement('div');
  div.className = `step-card ${escapeHtml(type)}`;
  div.innerHTML = `
    <div class="step-meta"><span>${escapeHtml(metaLeft)}</span><span>${escapeHtml(metaRight)}</span></div>
    <div class="step-title">${escapeHtml(title)}</div>
    ${detail ? `<pre class="step-detail">${escapeHtml(detail)}</pre>` : ''}
  `;
  stream.appendChild(div);
  scrollStreamBottom();
  return div;
}

export function renderChatMessages(messages, chatObj) {
  const stream = document.getElementById('agent-stream');
  if (!stream) return;
  const chatId = chatObj?.chat_id || store.activeChatId || 'chat';
  const isGeneral = chatId === 'chat';
  const title = chatObj?.title || (isGeneral ? 'Chat Generale' : store.activeChatId);
  if (!messages || !messages.length) {
    const emptyDesc = isGeneral
      ? 'Spazio informale per discussioni rapide e funzioni di servizio (non registrate nella Wiki o nei task):'
      : 'Ogni chat e ogni task ha allegati e memoria isolati. Scrivi qui sotto, trascina file nel box o usa un avvio rapido:';
    stream.innerHTML = `
      <div class="empty-state-card">
        <h3>💬 ${escapeHtml(title)}</h3>
        <p>${escapeHtml(emptyDesc)}</p>
        <div class="quick-start-grid">
          <button type="button" class="quick-start-btn" data-empty-action="attach-ws">
            <strong>📂 Allega dal Workspace</strong>
            <span>Scegli file o cartelle del progetto per dare contesto mirato.</span>
          </button>
          <button type="button" class="quick-start-btn" data-empty-action="attach-ext">
            <strong>⚡ Skill, Plugin & MCP</strong>
            <span>Attiva competenze o strumenti solo su questa chat o task.</span>
          </button>
          <button type="button" class="quick-start-btn" data-empty-action="new-task">
            <strong>🤖 Avvia un Task</strong>
            <span>Lancia agenti locali (<code>pi</code>) con step tracciati e archiviazione.</span>
          </button>
        </div>
      </div>
    `;
    return;
  }

  const headerBanner = isGeneral
    ? `
      <div class="step-card" style="display:flex; justify-content:space-between; align-items:center; gap:8px; margin-bottom:10px; padding:8px 12px; background:rgba(15,23,42,0.55); border:1px solid var(--border);">
        <span style="font-size:0.77rem; color:var(--muted);">💬 Discussioni e funzionalità informali (non registrate nella Wiki)</span>
        <button type="button" class="btn btn-ghost btn-sm" data-action="delete-chat" data-chat-id="chat">🧹 Pulisci Chat</button>
      </div>
    `
    : '';

  stream.innerHTML = headerBanner + messages
    .map((m) => `
      <div class="chat-turn">
        <div class="msg-bubble msg-user">
          <div class="msg-meta"><span>Tu</span><span>${escapeHtml(m.created_at || '')}</span></div>
          <div class="msg-prose">${formatProseHtml(m.user_text || '')}</div>
        </div>
        ${m.assistant_text ? `
          <div class="msg-bubble msg-assistant">
            <div class="msg-meta"><span>Cortical · ${escapeHtml(title)}</span><span></span></div>
            <div class="msg-prose">${formatProseHtml(m.assistant_text)}</div>
          </div>
        ` : ''}
      </div>
    `)
    .join('');
  scrollStreamBottom();
}

export function autoResizeComposer() {
  const el = document.getElementById('prompt-input');
  if (!el) return;
  el.style.height = 'auto';
  el.style.height = `${Math.min(150, Math.max(28, el.scrollHeight))}px`;
}

export async function submitComposer(actionMode = 'auto', micText = undefined) {
  const input = document.getElementById('prompt-input');
  const fromMic = actionMode === 'mic' && typeof micText === 'string';
  const mode = actionMode === 'task' ? 'task' : 'auto';
  const text = (fromMic ? micText : (typeof micText === 'string' ? micText : input?.value || '')).trim();
  if (!text) return;
  if (!fromMic && input) {
    input.value = '';
    autoResizeComposer();
  }

  if (fromMic && isSelfEchoClient(text) && !audioState.acousticUserPriorityDetected) {
    const lt = document.getElementById('live-transcript');
    if (lt) lt.textContent = '🔇 Eco ignorato';
    return;
  }

  if (store.activeAbortController) {
    store.activeAbortController.abort();
  }
  const wordCount = normalizeTokens(text).length;
  const wasSpeaking = isAssistantAudioPlaying();
  const hadUserPriority =
    audioState.acousticUserPriorityDetected ||
    hasWakeOrBargeInWord(text) ||
    (wordCount >= 3 && !isSelfEchoClient(text));
  if (!fromMic || hadUserPriority) {
    audioState.localTtsShieldUntilMs = 0;
    stopAssistantAudio();
    apiPost('/api/voice/duck', { force_stop: true }).catch(() => {});
  }

  if (onStageSwitchCb) onStageSwitchCb('stream');
  const depth = document.getElementById('agent-depth')?.value || 'medium';
  const effort = document.getElementById('agent-effort')?.value || store.effort || 'medium';
  const speak = store.audioResponsesEnabled;
  const voice = document.getElementById('tts-voice')?.value || 'auto';
  const utteranceLang = detectLangClient(text);

  if (!fromMic && text.startsWith('/')) {
    const handled = await handleSlashCommand(text, depth, speak, effort);
    if (handled) return;
  }

  if (mode === 'task') {
    const spCard = appendStreamCard('system', 'SPAWN TASK', 'avvio...', `🤖 Avvio nuovo task: "${text}"`, 'Inizializzazione agente locale...');
    try {
      await spawnAgentSession(text, depth, speak);
    } finally {
      spCard?.remove();
    }
    return;
  }

  const targetScope = store.selectedSessionId ? undefined : (store.activeChatId || 'chat');
  const pendingCard = appendStreamCard(
    'system',
    store.selectedSessionId ? `TASK ${store.selectedSessionId}` : `CHAT ${(store.activeChatId || 'chat').toUpperCase()}`,
    'elaborazione...',
    `Tu: "${text}"`,
    '⏳ Elaborazione in corso...',
  );

  store.activeAbortController = new AbortController();
  try {
    const d = await apiPost(
      '/api/voice',
      {
        utterance: text,
        session_id: store.selectedSessionId || undefined,
        scope_id: targetScope,
        speak,
        client_audio: true,
        client_tts_speaking: wasSpeaking,
        voice,
        lang: utteranceLang,
        wiki_depth: depth,
        effort,
        from_mic: fromMic,
        discourse_hints: {
          acoustic_user_priority: hadUserPriority,
          mic_rms: audioState.lastMicRms,
          assistant_rms: audioState.lastAssistantRms,
        },
      },
      store.activeAbortController.signal,
    );
    audioState.acousticUserPriorityDetected = false;
    pendingCard?.remove();

    if (d.route === 'ignored_echo') return;

    if (d.spoken_response) {
      audioState.lastSpokenResponseText = d.spoken_response;
      audioState.lastSpokenAtMs = Date.now();
      if (d.audio_url && speak && d.route !== 'stop') {
        await playAssistantAudioUrl(d.audio_url, d.spoken_response);
      } else if (speak && d.route !== 'stop') {
        const estMs = Math.min(7500, Math.max(2500, d.spoken_response.length * 55 + 1100));
        audioState.localTtsShieldUntilMs = Date.now() + estMs;
      } else {
        audioState.localTtsShieldUntilMs = Date.now() + 900;
      }
    }

    if (d.spawned_session_id) {
      await selectSession(d.spawned_session_id);
      if (onGraphSyncCb) await onGraphSyncCb();
    } else if (d.route === 'stop') {
      appendStreamCard('permission', 'STOP', `${d.latency_ms} ms`, `Tu: "${text}"`, d.spoken_response);
      await refreshAgents();
    } else {
      appendChatTurnCard(text, d.spoken_response || '', `${String(d.route || 'reply').toUpperCase()} · ${d.latency_ms} ms`);
      await refreshAgents();
      if (onGraphSyncCb) await onGraphSyncCb();
    }
  } catch (err) {
    pendingCard?.remove();
    if (err.name === 'AbortError') {
      appendStreamCard('system', 'INTERROTTO', 'ABORTED', 'Richiesta precedente interrotta.', '');
    } else {
      appendStreamCard('permission', 'ERRORE', 'ERROR', `Tu: "${text}"`, err.message || String(err));
    }
  } finally {
    store.activeAbortController = null;
  }
}

export async function spawnAgentSession(goal, depth, speak, effortOverride, extraOpts = {}) {
  const effort = effortOverride || document.getElementById('agent-effort')?.value || store.effort || 'medium';
  const chkLoop = document.getElementById('chk-auto-loop');
  const autoLoop = typeof extraOpts.auto_loop === 'boolean' ? extraOpts.auto_loop : (chkLoop ? Boolean(chkLoop.checked) : true);
  const sess = await apiPost('/api/agents/spawn', {
    goal,
    wiki_depth: depth,
    effort,
    speak: Boolean(speak),
    auto_loop: autoLoop,
    parallel: typeof extraOpts.parallel === 'boolean' ? extraOpts.parallel : undefined,
    source_scope_id: store.selectedSessionId || store.activeChatId || 'chat',
  });
  await selectSession(sess.session_id);
  if (onGraphSyncCb) await onGraphSyncCb();
}

export function spawnQuickAgent() {
  openTaskActionModal({
    title: '🤖 Nuovo Task Operativo Locale (pi)',
    desc: 'Descrivi l\'obiettivo del task. Erediterà gli allegati correnti se vuoi o partirà sul contesto attivo.',
    defaultValue: 'Analizza i file allegati e riassumi i punti chiave',
    showInput: true,
    confirmLabel: '🚀 Avvia Task',
    onConfirm: async (rawGoal) => {
      const goal = String(rawGoal || '').trim();
      if (!goal) return;
      if (onStageSwitchCb) onStageSwitchCb('stream');
      await spawnAgentSession(
        goal,
        document.getElementById('agent-depth')?.value || 'medium',
        store.audioResponsesEnabled,
      );
    },
  });
}

export function createNewChat() {
  openTaskActionModal({
    title: '💬 Nuova Chat Contestuale',
    desc: 'Dai un titolo alla nuova chat: avrà cronologia e allegati dedicati e isolati.',
    defaultValue: `Chat ${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`,
    showInput: true,
    confirmLabel: '💬 Crea Chat',
    onConfirm: async (rawTitle) => {
      const title = String(rawTitle || '').trim();
      if (!title) return;
      const d = await apiPost('/api/chats/create', { title });
      if (d.chat?.chat_id) {
        store.lastRosterSig = '';
        await selectChat(d.chat.chat_id);
      }
    },
  });
}

export function deleteChat(event, chatId) {
  if (event) event.stopPropagation();
  if (!chatId) return;
  const isGeneral = chatId === 'chat';
  openTaskActionModal({
    title: isGeneral ? '🧹 Pulisci Chat Generale' : '🗑️ Elimina Chat',
    desc: isGeneral
      ? 'Vuoi svuotare la cronologia informale della Chat Generale?'
      : 'Confermi l\'eliminazione definitiva di questa chat, della sua cronologia e dei suoi allegati?',
    showInput: false,
    confirmLabel: isGeneral ? '🧹 Svuota Chat' : '🗑️ Elimina Chat',
    confirmDanger: true,
    onConfirm: async () => {
      await apiPost('/api/chats/delete', { chat_id: chatId });
      store.lastRosterSig = '';
      if (!store.selectedSessionId && store.activeChatId === chatId) {
        await selectChat('chat');
      } else {
        await refreshAgents();
      }
    },
  });
}

export async function selectChat(chatId = 'chat') {
  store.activeChatId = chatId || 'chat';
  store.selectedSessionId = null;
  store.lastRosterSig = '';
  store.lastStreamSig = '';
  store.forceStreamRender = false;
  if (onStageSwitchCb) onStageSwitchCb('stream');
  renderTaskBanner(null);
  renderTaskMacroPanel(null);

  try {
    const data = await apiGet(`/api/chats?scope_id=${encodeURIComponent(store.activeChatId)}`);
    if (Array.isArray(data.chats)) store.loadedChats = data.chats;
    const cur = (data.active_scope && typeof data.active_scope === 'object')
      ? data.active_scope
      : (store.loadedChats.find((c) => c.chat_id === store.activeChatId) || {
        chat_id: store.activeChatId,
        title: store.activeChatId === 'chat' ? 'Chat Generale' : store.activeChatId,
      });
    const badgeEl = document.getElementById('active-session-badge');
    if (badgeEl) badgeEl.textContent = `💬 ${cur.title}`;
    const promptEl = document.getElementById('prompt-input');
    if (promptEl) promptEl.placeholder = `Scrivi in "${cur.title}" (usa file, skill e MCP allegati a questa chat)...`;
    renderChatMessages(data.messages || [], cur);
  } catch (err) {
    console.error('Errore selectChat:', err);
  }
  await loadScopedContext(store.activeChatId);
  await refreshAgents();
}

export async function selectSession(sid) {
  if (!sid) return;
  store.selectedSessionId = sid;
  store.lastRosterSig = '';
  store.forceStreamRender = true;
  if (onStageSwitchCb) onStageSwitchCb('stream');
  const cached = store.loadedSessions.find((s) => s.session_id === sid) || null;
  renderTaskBanner(cached);
  const badgeEl = document.getElementById('active-session-badge');
  if (badgeEl) badgeEl.textContent = `🤖 ${sid}`;
  const promptEl = document.getElementById('prompt-input');
  if (promptEl) promptEl.placeholder = `Scrivi nel task ${sid} (usa file, skill e MCP allegati a questo task)...`;
  await loadScopedContext(sid);
  await refreshAgents();
}

export function focusGeneralChat() {
  return selectChat(store.activeChatId || 'chat');
}

export function renameTask(event, sessionId, currentTitle = '') {
  if (event) event.stopPropagation();
  openTaskActionModal({
    title: `✏️ Rinomina Task (${sessionId})`,
    desc: 'Inserisci un titolo sintetico L1 (2-4 parole):',
    defaultValue: currentTitle || '',
    showInput: true,
    confirmLabel: '💾 Salva Titolo',
    onConfirm: async (newTitle) => {
      const clean = String(newTitle || '').trim();
      if (!clean) return;
      await apiPost('/api/tasks/rename', { episode_id: sessionId, title: clean });
      store.forceStreamRender = true;
      await refreshAgents();
    },
  });
}

export async function reopenTask(event, sessionId) {
  if (event) event.stopPropagation();
  const d = await apiPost('/api/tasks/reopen', { episode_id: sessionId });
  if (d.reopened) {
    await selectSession(sessionId);
    if (onGraphSyncCb) await onGraphSyncCb();
  }
}

export async function closeAndArchiveTask(event, sessionId) {
  if (event) event.stopPropagation();
  let questionsList = [`Quale lezione o decisione del task '${sessionId}' vuoi salvare?`];
  try {
    const prev = await apiPost('/api/tasks/close-preview', { episode_id: sessionId });
    if (Array.isArray(prev.closing_questions) && prev.closing_questions.length) {
      questionsList = prev.closing_questions;
    }
  } catch (_) {}

  openTaskActionModal({
    title: `📦 Archivia Task ${sessionId}`,
    desc: `Domande di chiusura:\n• ${questionsList.join('\n• ')}\n\nNota di chiusura (il task resterà riprendibile):`,
    defaultValue: 'Sintesi verificata e salvata nei 3+1 livelli.',
    showInput: true,
    confirmLabel: '📦 Archivia Task',
    onConfirm: async (notes) => {
      try {
        const arch = await apiPost('/api/tasks/archive', {
          episode_id: sessionId,
          user_closing_notes: notes,
        });
        store.forceStreamRender = true;
        await refreshAgents();
        appendStreamCard(
          'output',
          `ARCHIVED → ${sessionId}`,
          `Note rimosse: ${arch.purged_working_notes}`,
          `📦 Task ${sessionId} archiviato`,
          `Traccia L1: ${arch.archived_trace}`,
        );
        if (onGraphSyncCb) await onGraphSyncCb();
      } catch (err) {
        appendStreamCard('permission', 'ERRORE ARCHIVIAZIONE', sessionId, err.message, '');
      }
    },
  });
}

export function deleteTask(event, sessionId) {
  if (event) event.stopPropagation();
  openTaskActionModal({
    title: `🗑️ Elimina Task ${sessionId}`,
    desc: `Confermi l'eliminazione definitiva del task "${sessionId}" e dei suoi allegati?`,
    showInput: false,
    confirmLabel: '🗑️ Elimina definitivamente',
    confirmDanger: true,
    onConfirm: async () => {
      await apiPost('/api/tasks/delete', { episode_id: sessionId });
      if (store.selectedSessionId === sessionId) {
        await focusGeneralChat();
      } else {
        await refreshAgents();
      }
      if (onGraphSyncCb) await onGraphSyncCb();
    },
  });
}

export function clearArchivedTasks() {
  openTaskActionModal({
    title: '🧹 Svuota Task Archiviati',
    desc: 'Eliminare definitivamente dalla lista tutti i task archiviati?',
    showInput: false,
    confirmLabel: '🧹 Elimina Archiviati',
    confirmDanger: true,
    onConfirm: async () => {
      await apiPost('/api/tasks/clear-archived', {});
      await refreshAgents();
      if (onGraphSyncCb) await onGraphSyncCb();
    },
  });
}

export function setSidebarFilter(filter, el) {
  store.sidebarFilter = filter || 'all';
  document.querySelectorAll('#sidebar-filter-pills .pill').forEach((p) => p.classList.remove('active'));
  if (el) el.classList.add('active');
  store.lastRosterSig = '';
  refreshAgents();
}

export function onTaskSearchInput() {
  store.taskQuery = (document.getElementById('task-search-input')?.value || '').trim();
  store.taskPageLimit = 15;
  clearTimeout(taskSearchTimer);
  taskSearchTimer = setTimeout(() => refreshAgents(), 220);
}

export function loadMoreTasks() {
  if (!store.taskHasMore) return;
  store.taskPageLimit += 15;
  refreshAgents();
}

function renderContextAgentsBar(activeSess, sessions, globalTokenSummary, contextTelemetry = null, roleModels = null, scopePrefs = null) {
  const pill = document.getElementById('context-agents-bar');
  const popBody = document.getElementById('telemetry-popover-body');
  const scopeId = contextTelemetry?.scope_id || store.selectedSessionId || store.activeChatId || 'chat';
  const scopeLabel = activeSess ? (activeSess.title || activeSess.session_id) : (scopeId === 'chat' ? 'Chat Generale' : scopeId);
  const winTok = Number(contextTelemetry?.context_window_tokens || 32768);
  const usedTok = Number(contextTelemetry?.used_tokens || 0);
  const occPct = Number(contextTelemetry?.occupancy_pct ?? 0);
  const winLabel = winTok >= 1024 ? `${Math.round(winTok / 1024)}k` : `${winTok}`;
  const curStrat = scopePrefs?.context_strategy || 'auto';
  const curThink = scopePrefs?.thinking_mode || contextTelemetry?.thinking_mode || 'auto';
  if (pill) {
    if (activeSess) {
      const runs = activeSess.runs || [];
      const workingRuns = runs.filter((r) => r.status === 'working').length;
      const tok = activeSess.token_summary?.total_tokens || 0;
      pill.textContent = `🤖 ${workingRuns ? `${workingRuns} working · ` : ''}${runs.length} run · ${tok} tok · Ctx ${usedTok}/${winLabel} (${occPct}%)`;
    } else {
      const workingCount = sessions.filter((s) => s.status === 'working').length;
      pill.textContent = `💬 ${scopeLabel} · Ctx ${usedTok}/${winLabel} (${occPct}%) · 🤖 ${workingCount} attivi`;
    }
  }
  if (popBody) {
    const ctxBanner = `
      <div style="margin-bottom:8px; padding:8px; border-radius:6px; background:rgba(56,189,248,0.08); border:1px solid rgba(56,189,248,0.25); font-size:0.74rem;">
        <div><b>📊 Contesto (${escapeHtml(scopeLabel)}):</b> ${usedTok} / ${winTok} tok (<b>${occPct}%</b>) · <code>${escapeHtml(contextTelemetry?.active_model || 'qwen3.8:27b-iq2_xxs')}</code></div>
        <div style="color:var(--muted); margin-top:2px;">Strategia attiva: <code>${escapeHtml(contextTelemetry?.strategy || 'direct')}</code> · Chunk: ${contextTelemetry?.chunks_count || 1} · Thinking: <code>${escapeHtml(curThink)}</code></div>
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:6px; margin-top:6px;">
          <label style="display:flex; flex-direction:column; gap:2px; font-size:0.68rem; color:var(--muted);">
            Strategia Contesto
            <select id="ctx-strategy-select" data-scope-id="${escapeHtml(scopeId)}" style="font-size:0.72rem;">
              <option value="auto" ${curStrat === 'auto' ? 'selected' : ''}>auto (adattiva)</option>
              <option value="direct" ${curStrat === 'direct' ? 'selected' : ''}>direct (blocco unico)</option>
              <option value="multi_message" ${curStrat === 'multi_message' ? 'selected' : ''}>multi_message</option>
              <option value="summarize" ${curStrat === 'summarize' ? 'selected' : ''}>summarize (compatta)</option>
            </select>
          </label>
          <label style="display:flex; flex-direction:column; gap:2px; font-size:0.68rem; color:var(--muted);">
            Thinking (Reasoning)
            <select id="ctx-thinking-select" data-scope-id="${escapeHtml(scopeId)}" style="font-size:0.72rem;">
              <option value="auto" ${curThink === 'auto' ? 'selected' : ''}>auto (da effort)</option>
              <option value="off" ${curThink === 'off' ? 'selected' : ''}>off (veloce)</option>
              <option value="low" ${curThink === 'low' ? 'selected' : ''}>low (leggero)</option>
              <option value="medium" ${curThink === 'medium' ? 'selected' : ''}>medium (bilanciato)</option>
              <option value="high" ${curThink === 'high' ? 'selected' : ''}>high (profondo)</option>
            </select>
          </label>
        </div>
        ${roleModels ? `<div style="color:var(--muted); margin-top:4px;">Coord: <code>${escapeHtml(roleModels.coordinator_model || '')}</code> · Chat: <code>${escapeHtml(roleModels.chat_model || '')}</code></div>` : ''}
        <button type="button" class="btn btn-ghost btn-sm" id="btn-open-models-studio" style="margin-top:6px; width:100%;">🎛️ Configura Modelli &amp; Ruoli</button>
      </div>
    `;
    if (activeSess) {
      const runs = (activeSess.runs || []).slice(0, 8);
      popBody.innerHTML = ctxBanner + (runs.length
        ? runs.map((r) => `
            <div class="fs-row" style="margin-bottom:4px; gap:6px;">
              <div style="min-width:0; flex:1;">
                <span><b>${escapeHtml(r.role)}</b> · <code>${escapeHtml(r.model)}</code></span>
                ${r.goal ? `<div style="font-size:0.66rem; color:var(--muted); overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${escapeHtml(r.goal)}</div>` : ''}
              </div>
              <div style="display:flex; align-items:center; gap:4px;">
                <span class="status-pill status-${escapeHtml(r.status)}">${escapeHtml(r.status)} · ${r.total_tokens || 0} tok</span>
                ${r.status === 'working' ? `<button type="button" class="mini-action-btn" data-stop-run="${escapeHtml(r.run_id)}" data-sid="${escapeHtml(activeSess.session_id)}" title="Termina agente">⏹</button>` : ''}
              </div>
            </div>
          `).join('')
        : `<div style="color:var(--muted);">Nessuna esecuzione registrata su questo task.</div>`);
    } else {
      const models = globalTokenSummary?.by_model || [];
      popBody.innerHTML = ctxBanner + (models.length
        ? models.map((m) => `<div class="fs-row" style="margin-bottom:4px;"><code>${escapeHtml(m.model)}</code><span>${m.total_tokens} tok (${m.runs}x)</span></div>`).join('')
        : `<div style="color:var(--muted);">Nessun token consumato finora sul modello locale.</div>`);
    }
  }
}

function taskStatusMeta(active) {
  if (!active) return { text: 'CARICAMENTO', cls: 'open' };
  const st = active.status || 'open';
  const isArch = active.lifecycle_state === 'archived' || st === 'archived';
  if (isArch) return { text: 'ARCHIVIATO', cls: 'archived' };
  const map = {
    working: { text: 'IN ESECUZIONE', cls: 'working' },
    awaiting_approval: { text: 'ATTESA APPROVAZIONE', cls: 'working' },
    needs_input: { text: 'ATTENDE RISPOSTA', cls: 'open' },
    blocked: { text: 'BLOCCATO', cls: 'error' },
    stalled: { text: 'TIMEOUT', cls: 'error' },
    stopped: { text: 'INTERROTTO', cls: 'open' },
    error: { text: 'ERRORE', cls: 'error' },
    completed: { text: 'COMPLETATO', cls: 'open' },
  };
  return map[st] || { text: 'APERTO', cls: 'open' };
}

export function renderTaskMacroPanel(active) {
  const panel = document.getElementById('task-macro-panel');
  if (!panel) return;
  if (!active || !active.session_id) {
    panel.style.display = 'none';
    panel.innerHTML = '';
    return;
  }
  panel.style.display = 'flex';
  const steps = active.steps || [];
  const counts = { read: 0, write: 0, bash: 0, wiki: 0 };
  const touchedFiles = [];
  const seenFiles = new Set();

  steps.forEach((st) => {
    const title = String(st.title || '').toLowerCase();
    const metaTool = String(st.meta?.tool || '').toLowerCase();
    if (metaTool === 'read' || title.startsWith('pi:read') || title.startsWith('read (')) counts.read += 1;
    if (metaTool === 'write' || metaTool === 'edit' || title.startsWith('pi:write') || title.startsWith('pi:edit')) counts.write += 1;
    if (metaTool === 'bash' || title.startsWith('pi:bash') || title.startsWith('bash (')) counts.bash += 1;
    if (title.includes('wiki_search')) counts.wiki += 1;
    let p = st.meta?.path || '';
    if (!p && title.startsWith('pi:')) {
      const m = String(st.detail || '').match(/"path"\s*:\s*"([^"]+)"/);
      if (m) p = m[1];
    }
    if (p && !seenFiles.has(p)) {
      seenFiles.add(p);
      touchedFiles.push(p);
    }
  });

  const hasVerify = steps.some((st) => String(st.title || '').includes('Verifica') || (counts.write > 0 && counts.bash > 0));
  const stVal = String(active.status || 'open');
  const isDone = stVal === 'completed';
  const isWarn = ['needs_input', 'awaiting_approval', 'blocked', 'stalled', 'stopped'].includes(stVal);
  const isWorking = stVal === 'working';

  const phaseCls = (doneCond, activeCond, warnCond = false) =>
    warnCond ? 'warn' : doneCond ? 'done' : activeCond ? 'active' : '';

  const p1 = phaseCls(counts.wiki > 0 || steps.length > 0, isWorking && steps.length <= 1);
  const p2 = phaseCls(counts.write > 0 || isDone, (isWorking || counts.read > 0) && counts.write === 0 && !isDone);
  const p3 = phaseCls(counts.write > 0 && (hasVerify || isDone), (isWorking && counts.write > 0 && !hasVerify) || stVal === 'awaiting_approval', stVal === 'awaiting_approval');
  const p4 = phaseCls(hasVerify && isDone, isWorking && hasVerify);
  const p5 = phaseCls(isDone, false, isWarn);

  const totTok = active.token_summary?.total_tokens || active.total_tokens || 0;
  const elapsed = active.token_summary?.elapsed_sec ? `${Number(active.token_summary.elapsed_sec).toFixed(1)}s` : (active.elapsed_sec ? `${Number(active.elapsed_sec).toFixed(1)}s` : '—');
  const modelName = active.model || active.token_summary?.model || 'qwen3:8b';
  const attCount = (store.cachedAttachments || []).length;

  panel.innerHTML = `
    <div class="macro-card">
      <div class="macro-card-title">📊 Pipeline Task (Macroblocchi)</div>
      <div class="pipeline-step ${p1}"><span>🧠</span><span>1. Contesto &amp; Skill (${attCount} allegati)</span></div>
      <div class="pipeline-step ${p2}"><span>🔎</span><span>2. Analisi Workspace (${counts.read} read · ${counts.bash} bash)</span></div>
      <div class="pipeline-step ${p3}"><span>✏️</span><span>3. Codice &amp; File (${counts.write} write/edit)</span></div>
      <div class="pipeline-step ${p4}"><span>🔁</span><span>4. Loop Verifica &amp; Test</span></div>
      <div class="pipeline-step ${p5}"><span>${isDone ? '✅' : isWarn ? '⏸️' : '⏳'}</span><span>5. ${escapeHtml(active.status_label || stVal)}</span></div>
    </div>

    <div class="macro-card">
      <div class="macro-card-title">⚡ Telemetria &amp; Risparmio</div>
      <div class="macro-kpi-grid">
        <div class="macro-kpi"><div class="macro-kpi-val">${totTok.toLocaleString()}</div><div class="macro-kpi-lbl">Token Locali (0 cloud)</div></div>
        <div class="macro-kpi"><div class="macro-kpi-val">${escapeHtml(elapsed)}</div><div class="macro-kpi-lbl">Durata</div></div>
        <div class="macro-kpi"><div class="macro-kpi-val">${steps.length}</div><div class="macro-kpi-lbl">Step Totali</div></div>
        <div class="macro-kpi"><div class="macro-kpi-val" style="font-size:0.74rem;">${escapeHtml(modelName)}</div><div class="macro-kpi-lbl">Modello Attivo</div></div>
      </div>
    </div>

    <div class="macro-card">
      <div class="macro-card-title">📁 File Toccati (${touchedFiles.length})</div>
      ${
        touchedFiles.length
          ? touchedFiles.slice(0, 8).map((f) => `<div style="font-family:var(--mono); font-size:0.71rem; color:var(--text-soft); white-space:nowrap; overflow:hidden; text-overflow:ellipsis;" title="${escapeHtml(f)}">• ${escapeHtml(f.split('/').pop())}</div>`).join('')
          : '<div style="font-size:0.74rem; color:var(--muted);">Nessun file toccato finora</div>'
      }
    </div>
  `;
}

export function renderTaskBanner(active) {
  const banner = document.getElementById('active-task-banner');
  if (!banner) return;
  if (!active && !store.selectedSessionId) {
    banner.style.display = 'none';
    banner.innerHTML = '';
    return;
  }
  const sid = active ? active.session_id : store.selectedSessionId;
  const isArch = active ? (active.lifecycle_state === 'archived' || active.status === 'archived') : false;
  const meta = taskStatusMeta(active);
  const badgeText = meta.text;
  const badgeCls = meta.cls;
  const goalTxt = active?.goal ? String(active.goal).split('\n')[0].slice(0, 120) : 'Caricamento dettagli task...';
  const titleTxt = active?.title || sid;
  const effBadge = active?.effort ? `<span class="status-pill">${escapeHtml(String(active.effort).toUpperCase())}</span>` : '';
  const aprMode = active?.approval_mode || 'ask';
  const isRunning = active && (active.status === 'working' || active.status === 'awaiting_approval');
  banner.style.display = 'flex';
  banner.innerHTML = `
    <div style="min-width:0; flex:1; display:flex; align-items:center; gap:8px;">
      <span class="status-pill status-${badgeCls}">${badgeText}</span>
      ${effBadge}
      <b>${escapeHtml(titleTxt)}</b>
      <code style="font-family:var(--mono); color:var(--accent); font-size:0.75rem;">${escapeHtml(sid)}</code>
      <button type="button" class="mini-action-btn" data-banner-action="rename" data-sid="${escapeHtml(sid)}" data-title="${escapeHtml(titleTxt)}" title="Rinomina task">✏️</button>
      <span style="color:var(--muted); overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${escapeHtml(active?.goal || '')}">${escapeHtml(goalTxt)}</span>
    </div>
    <div style="display:flex; gap:6px; align-items:center; flex-shrink:0;">
      <select id="task-approval-mode" data-sid="${escapeHtml(sid)}" title="Modalità approvazione comandi" style="font-size:0.72rem;">
        <option value="ask" ${aprMode === 'ask' ? 'selected' : ''}>🔐 Chiedi conferme</option>
        <option value="auto_edit" ${aprMode === 'auto_edit' ? 'selected' : ''}>⚡ Auto-edit &amp; test</option>
        <option value="full_auto" ${aprMode === 'full_auto' ? 'selected' : ''}>🚀 Full Auto</option>
      </select>
      ${isRunning
        ? `<button type="button" class="btn btn-danger btn-sm" data-banner-action="stop">⏹ Ferma</button>`
        : ''}
      <button type="button" class="btn btn-ghost btn-sm" data-banner-action="chat">💬 Torna alla Chat</button>
      ${active ? (isArch
        ? `<button type="button" class="btn btn-ghost btn-sm" data-banner-action="reopen" data-sid="${escapeHtml(sid)}">🔄 Riprendi</button>`
        : `<button type="button" class="btn btn-ghost btn-sm" data-banner-action="archive" data-sid="${escapeHtml(sid)}">📦 Archivia</button>`) : ''}
    </div>
  `;
}

const agentRunsUiState = {
  episodeId: '',
  status: 'all',
  query: '',
  runs: [],
  offset: 0,
  total: 0,
  hasMore: false,
  loading: false,
};

function renderAgentRunRowsHtml(runs, sessionId) {
  if (!runs.length) {
    return '<div style="padding:10px; font-size:0.74rem; color:var(--muted);">Nessun agente corrisponde al filtro selezionato.</div>';
  }
  return runs.map((r) => `
    <div class="agent-run-row" style="gap:8px;">
      <div style="min-width:0; flex:1;">
        <div style="display:flex; align-items:center; gap:6px;">
          <b>${escapeHtml(r.role)}</b>
          <code>${escapeHtml(r.model)}</code>
        </div>
        ${r.goal ? `<div style="font-size:0.7rem; color:var(--muted); overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${escapeHtml(r.goal)}">${escapeHtml(r.goal)}</div>` : ''}
      </div>
      <div style="display:flex; align-items:center; gap:6px; flex-shrink:0;">
        <div style="text-align:right;">
          <span class="status-pill status-${escapeHtml(r.status)}">${escapeHtml(r.status)}</span>
          <div style="font-family:var(--mono); font-size:0.68rem; color:var(--muted); margin-top:2px;">${r.total_tokens || 0} tok · ${r.elapsed_sec || 0}s</div>
        </div>
        ${r.status === 'working' ? `<button type="button" class="btn btn-danger btn-sm" data-stop-run="${escapeHtml(r.run_id)}" data-sid="${escapeHtml(sessionId)}" title="Termina esecuzione">⏹ Termina</button>` : ''}
      </div>
    </div>
  `).join('');
}

export async function fetchFilteredAgentRuns(episodeId, reset = true) {
  if (agentRunsUiState.loading) return;
  agentRunsUiState.loading = true;
  if (reset) {
    agentRunsUiState.episodeId = episodeId;
    agentRunsUiState.offset = 0;
    agentRunsUiState.runs = [];
  }
  try {
    const qs = new URLSearchParams({
      episode_id: episodeId,
      status: agentRunsUiState.status,
      q: agentRunsUiState.query,
      offset: String(agentRunsUiState.offset),
      limit: '10',
    });
    const d = await apiGet(`/api/agents/runs?${qs.toString()}`);
    const incoming = d.runs || [];
    agentRunsUiState.runs = reset ? incoming : [...agentRunsUiState.runs, ...incoming];
    agentRunsUiState.offset = agentRunsUiState.runs.length;
    agentRunsUiState.total = Number(d.total_count || agentRunsUiState.runs.length);
    agentRunsUiState.hasMore = Boolean(d.has_more);
    const grid = document.getElementById('agent-runs-scroll');
    if (grid) {
      grid.innerHTML = renderAgentRunRowsHtml(agentRunsUiState.runs, episodeId) +
        (agentRunsUiState.hasMore ? '<div style="text-align:center; padding:6px; font-size:0.7rem; color:var(--muted);">⬇️ Scorri per caricare altri run...</div>' : '');
    }
  } finally {
    agentRunsUiState.loading = false;
  }
}

function formatApprovalDecisionLabel(decision, status) {
  const key = String(decision || status || '').trim();
  const labels = {
    allow_once: '✓ Consentito (1 volta)',
    allow_session: '✓ Consentito per questa sessione',
    allow_always: '★ Sempre consentito',
    allowed: '✓ Consentito',
    deny: "✕ Negato dall'utente",
    denied: "✕ Negato dall'utente",
    expired: '⏱️ Scaduto',
  };
  return labels[key] || key || 'Completato';
}

function extractPlayableExampleLinksHtml(text) {
  const raw = String(text || '');
  const matches = raw.match(/examples\/vibe_games\/[A-Za-z0-9_\-/]+\.html|examples\/[A-Za-z0-9_\-/]+\.html/g) || [];
  const unique = [...new Set(matches.map((m) => `/${m.replace(/^\/+/, '')}`))];
  if (!unique.length) return '';
  const links = unique.slice(0, 3).map((href) => {
    const label = href.includes('sliding_puzzle')
      ? 'Puzzle 15'
      : (href.includes('tic_tac_toe') ? 'Tic-Tac-Toe' : (href.includes('pacman') ? 'Pac-Man' : (href.includes('snake') ? 'Snake' : 'Gioco HTML')));
    return `<a href="${escapeHtml(href)}" target="_blank" rel="noopener" class="btn btn-sm" style="text-decoration:none;">🎮 Apri e Gioca (${escapeHtml(label)})</a>`;
  }).join('');
  return `<div style="margin-top:8px; display:flex; gap:8px; flex-wrap:wrap;">${links}<a href="/examples/vibe_games/index.html" target="_blank" rel="noopener" class="btn btn-ghost btn-sm" style="text-decoration:none;">🕹️ Arcade Hub (Tutti i Giochi)</a></div>`;
}

function renderApprovalCardHtml(pa) {
  if (!pa) return '';
  const isPending = pa.status === 'pending';
  const isAllowed = pa.status === 'allowed';
  const riskPct = Math.round(Number(pa.risk || 0) * 100);
  const borderCol = isPending
    ? 'rgba(251,191,36,0.75)'
    : (isAllowed ? 'rgba(34,197,94,0.75)' : 'rgba(239,68,68,0.75)');
  const bgCol = isPending
    ? 'rgba(15,23,42,0.85)'
    : (isAllowed ? 'rgba(20,83,45,0.28)' : 'rgba(127,29,29,0.25)');
  const decLabel = formatApprovalDecisionLabel(pa.decision, pa.status);
  const headerHtml = isPending
    ? `🔐 Richiesta Approvazione Tool: <code>${escapeHtml(pa.tool || 'bash')}</code>`
    : (isAllowed
      ? `✅ Comando Autorizzato: <code>${escapeHtml(pa.tool || 'bash')}</code>`
      : `⛔ Comando Rifiutato: <code>${escapeHtml(pa.tool || 'bash')}</code>`);
  const pillStyle = isPending
    ? ''
    : (isAllowed
      ? 'background:rgba(34,197,94,0.2); border-color:rgba(34,197,94,0.6); color:#86efac;'
      : 'background:rgba(239,68,68,0.2); border-color:rgba(239,68,68,0.6); color:#fca5a5;');
  const pillText = isPending
    ? `⏳ In attesa · ${pa.pattern || ''} (${riskPct}%)`
    : decLabel;
  return `
    <div class="step-card" data-approval-card="${escapeHtml(pa.approval_id)}" style="border:1.5px solid ${borderCol}; background:${bgCol}; margin:8px 0; padding:10px 12px; border-radius:10px; transition:border-color 0.15s, background 0.15s;">
      <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; margin-bottom:6px; flex-wrap:wrap;">
        <span data-apr-header style="font-weight:700; font-size:0.82rem;">${headerHtml}</span>
        <span data-apr-pill class="status-pill" style="${pillStyle}">${escapeHtml(pillText)}</span>
      </div>
      <pre class="step-detail" style="margin:0 0 8px 0; padding:8px; background:rgba(2,6,23,0.65); border-radius:6px; white-space:pre-wrap;">${escapeHtml(pa.summary || '')}</pre>
      ${pa.reason && isPending ? `<div style="font-size:0.72rem; color:var(--muted); margin-bottom:8px;">${escapeHtml(pa.reason)}</div>` : ''}
      ${isPending ? `
        <div data-apr-actions style="display:flex; flex-wrap:wrap; gap:6px; align-items:center;">
          <button type="button" class="btn btn-sm" data-apr-id="${escapeHtml(pa.approval_id)}" data-apr-decision="allow_once">✓ Consenti</button>
          <button type="button" class="btn btn-ghost btn-sm" data-apr-id="${escapeHtml(pa.approval_id)}" data-apr-decision="allow_session">✓ Questa sessione</button>
          <button type="button" class="btn btn-ghost btn-sm" data-apr-id="${escapeHtml(pa.approval_id)}" data-apr-decision="allow_always">★ Sempre</button>
          <button type="button" class="btn btn-danger btn-sm" data-apr-id="${escapeHtml(pa.approval_id)}" data-apr-decision="deny">✕ Nega</button>
          <input type="text" id="apr-fb-${escapeHtml(pa.approval_id)}" placeholder="Feedback opzionale se neghi..." style="flex:1; min-width:170px; font-size:0.74rem;" />
        </div>
      ` : `<div data-apr-actions style="font-size:0.76rem; color:${isAllowed ? '#86efac' : '#fca5a5'}; font-weight:600;">${isAllowed ? `✅ Azione confermata (${escapeHtml(decLabel)}) — il comando è stato sbloccato ed eseguito.` : `⛔ Azione bloccata (${escapeHtml(decLabel)}).`}${pa.feedback ? ` · ${escapeHtml(pa.feedback)}` : ''}</div>`}
    </div>
  `;
}

function renderTaskStreamHtml(active, pendingApprovals = []) {
  const runs = active.runs || [];
  const tok = active.token_summary || {};
  const effortLabel = String(active.effort || 'medium').toUpperCase();
  if (agentRunsUiState.episodeId !== active.session_id) {
    agentRunsUiState.episodeId = active.session_id;
    agentRunsUiState.status = 'all';
    agentRunsUiState.query = '';
    agentRunsUiState.runs = runs.slice(0, 10);
    agentRunsUiState.offset = agentRunsUiState.runs.length;
    agentRunsUiState.total = runs.length;
    agentRunsUiState.hasMore = runs.length >= 10;
  }
  const initialFiltered = (agentRunsUiState.status === 'all' && !agentRunsUiState.query && agentRunsUiState.runs.length)
    ? agentRunsUiState.runs
    : runs.filter((r) => {
        if (agentRunsUiState.status !== 'all' && r.status !== agentRunsUiState.status) return false;
        if (agentRunsUiState.query) {
          const hay = `${r.role} ${r.model} ${r.goal || ''}`.toLowerCase();
          if (!hay.includes(agentRunsUiState.query.toLowerCase())) return false;
        }
        return true;
      }).slice(0, Math.max(10, agentRunsUiState.offset));

  const reportPanel = runs.length
    ? `
      <div class="agent-report-panel" data-runs-sid="${escapeHtml(active.session_id)}">
        <div class="agent-report-head" style="flex-wrap:wrap; gap:6px;">
          <span>REPORT AGENTI LOCALI · EFFORT ${escapeHtml(effortLabel)}</span>
          <span>${runs.length} run recenti · ${tok.total_tokens || 0} tok (${tok.input_tokens || 0} in / ${tok.output_tokens || 0} out)</span>
        </div>
        <div style="display:flex; flex-wrap:wrap; gap:6px; align-items:center; padding:6px 10px; border-bottom:1px solid var(--border);">
          <select id="agent-runs-status-filter" style="font-size:0.72rem;">
            <option value="all" ${agentRunsUiState.status === 'all' ? 'selected' : ''}>Tutti</option>
            <option value="working" ${agentRunsUiState.status === 'working' ? 'selected' : ''}>In corso (working)</option>
            <option value="completed" ${agentRunsUiState.status === 'completed' ? 'selected' : ''}>Completati</option>
            <option value="stopped" ${agentRunsUiState.status === 'stopped' ? 'selected' : ''}>Fermati</option>
          </select>
          <input type="text" id="agent-runs-search" value="${escapeHtml(agentRunsUiState.query)}" placeholder="Filtra ruolo, modello o attività..." style="flex:1; min-width:160px; font-size:0.72rem;" />
        </div>
        <div class="agent-run-grid" id="agent-runs-scroll" style="max-height:240px; overflow-y:auto;">
          ${renderAgentRunRowsHtml(initialFiltered, active.session_id)}
          ${agentRunsUiState.hasMore ? '<div style="text-align:center; padding:6px; font-size:0.7rem; color:var(--muted);">⬇️ Scorri per caricare altri run...</div>' : ''}
        </div>
      </div>
    `
    : '';

  const steps = active.steps || [];
  const stepsHtml = steps.length
    ? steps.map((st) => {
        const typ = String(st.type || 'step').toLowerCase();
        if (typ === 'user_turn') {
          return `
            <div class="msg-row user">
              <div class="msg-bubble user">
                <div class="msg-meta">Tu · ${escapeHtml(st.timestamp || '')}</div>
                <div>${formatProseHtml(st.detail || st.title)}</div>
              </div>
            </div>
          `;
        }
        if (typ === 'approval') {
          return renderApprovalCardHtml(st.meta?.approval);
        }
        if (typ === 'approval_result') {
          return `<div style="font-size:0.74rem; color:var(--muted); padding:2px 6px;">${escapeHtml(st.title)}</div>`;
        }
        if (typ === 'output') {
          const playLinks = extractPlayableExampleLinksHtml(st.detail || '');
          return `
            <div class="final-report-card">
              <div class="step-meta"><span>✅ ${escapeHtml(st.title)}</span><span>${escapeHtml(st.timestamp || '')}</span></div>
              <div class="final-report-prose">${formatProseHtml(st.detail || '')}</div>
              ${playLinks}
            </div>
          `;
        }
        const icon = typ === 'tool_call' ? '🔧' : (typ === 'tool_result' ? '📦' : (typ === 'subagent' ? '🤖' : '🧠'));
        const stepPlayLinks = typ === 'tool_result' ? extractPlayableExampleLinksHtml(st.detail || '') : '';
        return `
          <details class="tool-trace">
            <summary class="tool-trace-summary">
              <span>${icon} <b>${escapeHtml(typ.toUpperCase())}</b> · ${escapeHtml(st.title)}</span>
              <span style="color:var(--muted); flex-shrink:0;">${escapeHtml(st.timestamp || '')}</span>
            </summary>
            ${st.detail ? `<div class="tool-trace-body"><pre class="step-detail">${escapeHtml(st.detail)}</pre>${stepPlayLinks}</div>` : ''}
          </details>
        `;
      }).join('')
    : `<div class="step-card"><div class="step-title">🤖 Task ${escapeHtml(active.session_id)} aperto — scrivi qui sotto per inviare istruzioni.</div></div>`;

  const shownIds = new Set(steps.map((s) => s.meta?.approval?.approval_id).filter(Boolean));
  const extraPendingHtml = (pendingApprovals || [])
    .filter((p) => p.session_id === active.session_id && !shownIds.has(p.approval_id))
    .map((p) => renderApprovalCardHtml(p))
    .join('');

  const act = active.current_activity;
  const actTxt = act ? `<b>${escapeHtml(act.tool || 'working')}</b> ${escapeHtml(act.summary || '')}` : `Agente locale in esecuzione (${escapeHtml(effortLabel)})...`;
  const workingFooter = active.status === 'working'
    ? `<div class="tool-trace" style="border-color:rgba(251,191,36,0.45); padding:8px 12px; display:flex; justify-content:space-between; align-items:center; gap:8px;"><span>⏳ ${actTxt}</span><button type="button" class="btn btn-danger btn-sm" data-banner-action="stop">⏹ Ferma</button></div>`
    : (active.status === 'needs_input'
      ? `<div class="step-card" style="border:1px solid rgba(56,189,248,0.5); padding:10px 12px; margin-top:8px;">💬 <b>Serve una tua risposta</b> — scrivi qui sotto per far continuare l'agente con il contesto attuale.</div>`
      : (active.status === 'stalled' || active.status === 'blocked'
        ? `<div class="step-card" style="border:1px solid rgba(239,68,68,0.5); padding:10px 12px; margin-top:8px;">⚠️ <b>Task ${active.status === 'stalled' ? 'interrotto per timeout' : 'bloccato'}</b> — invia nuove istruzioni qui sotto o cambia la modalità approvazioni in alto.</div>`
        : ''));

  return reportPanel + stepsHtml + extraPendingHtml + workingFooter;
}

export async function refreshAgents() {
  bindAgentRunsControls();
  try {
    const epParam = store.selectedSessionId ? `&episode_id=${encodeURIComponent(store.selectedSessionId)}` : '';
    const scopeParam = `&scope_id=${encodeURIComponent(store.selectedSessionId || store.activeChatId || 'chat')}`;
    const [data, chatData] = await Promise.all([
      apiGet(`/api/agents?q=${encodeURIComponent(store.taskQuery)}&offset=0&limit=${store.taskPageLimit}${epParam}${scopeParam}`),
      apiGet('/api/chats').catch(() => ({ chats: store.loadedChats })),
    ]);
    if (Array.isArray(chatData.chats)) store.loadedChats = chatData.chats;
    const sessions = data.sessions || [];
    store.loadedSessions = sessions;
    store.taskHasMore = Boolean(data.has_more);

    const active = store.selectedSessionId
      ? (data.selected_session || sessions.find((s) => s.session_id === store.selectedSessionId) || null)
      : null;
    renderContextAgentsBar(active, sessions, data.token_summary, data.context_telemetry, data.role_models, data.scope_preferences);
    renderTaskBanner(active);

    const qLower = store.taskQuery.toLowerCase();
    const visibleChats = (store.sidebarFilter === 'all' || store.sidebarFilter === 'chat')
      ? store.loadedChats.filter((c) => !qLower || String(c.title || '').toLowerCase().includes(qLower) || String(c.chat_id || '').toLowerCase().includes(qLower))
      : [];
    const visibleSessions = (store.sidebarFilter === 'all' || store.sidebarFilter === 'task') ? sessions : [];

    const rosterSig = JSON.stringify([
      store.sidebarFilter,
      store.selectedSessionId,
      store.activeChatId,
      store.taskQuery,
      store.taskHasMore,
      data.total,
      visibleChats.map((c) => [c.chat_id, c.title, c.message_count ?? c.turn_count ?? 0]),
      visibleSessions.map((s) => [s.session_id, s.status, s.lifecycle_state, (s.steps || []).length, s.token_summary?.total_tokens || 0]),
    ]);

    const roster = document.getElementById('agent-roster');
    if (roster && rosterSig !== store.lastRosterSig) {
      store.lastRosterSig = rosterSig;
      const chatsHtml = visibleChats
        .map((c) => {
          const cidEsc = escapeHtml(c.chat_id);
          const isActiveChat = !store.selectedSessionId && c.chat_id === store.activeChatId;
          const msgCount = c.message_count ?? c.turn_count ?? 0;
          return `
            <div class="roster-card chat-card ${isActiveChat ? 'active' : ''}" data-chat-id="${cidEsc}">
              <div class="roster-card-top">
                <span class="roster-title">💬 ${escapeHtml(c.title || c.chat_id)}</span>
                <span class="status-pill status-open">CHAT</span>
              </div>
              <div class="roster-meta-row">
                <span class="roster-meta">${msgCount} messaggi</span>
                ${c.chat_id === 'chat' ? (msgCount > 0 ? `
                  <div class="roster-hover-actions">
                    <button type="button" class="mini-action-btn" data-action="delete-chat" data-chat-id="${cidEsc}" title="Pulisci Chat Generale">🧹</button>
                  </div>
                ` : '') : `
                  <div class="roster-hover-actions">
                    <button type="button" class="mini-action-btn danger" data-action="delete-chat" data-chat-id="${cidEsc}" title="Elimina chat">🗑️</button>
                  </div>
                `}
              </div>
            </div>
          `;
        })
        .join('');

      const tasksHtml = visibleSessions
        .map((s) => {
          const sidEsc = escapeHtml(s.session_id);
          const titleRaw = String(s.title || s.session_id);
          const titleEsc = escapeHtml(titleRaw);
          const isArch = s.lifecycle_state === 'archived' || s.status === 'archived';
          const badgeText = s.status === 'working' ? 'WORKING' : (isArch ? 'ARCHIVIATO' : 'APERTO');
          const badgeCls = s.status === 'working' ? 'working' : (isArch ? 'archived' : 'open');
          const shortGoal = String(s.goal || '').split('\n')[0];
          const tokTot = s.token_summary?.total_tokens || 0;
          return `
            <div class="roster-card task-card ${s.session_id === store.selectedSessionId ? 'active' : ''}" data-session-id="${sidEsc}">
              <div class="roster-card-top">
                <span class="roster-title" title="${sidEsc}">🤖 ${titleEsc}</span>
                <span class="status-pill status-${badgeCls}">${badgeText}</span>
              </div>
              <div class="roster-sub">${escapeHtml(shortGoal)}</div>
              <div class="roster-meta-row">
                <span class="roster-meta"><code>${sidEsc}</code> · ${(s.steps || []).length} step · ${tokTot} tok</span>
                <div class="roster-hover-actions">
                  <button type="button" class="mini-action-btn" data-action="rename" data-session-id="${sidEsc}" data-title="${titleEsc}" title="Rinomina">✏️</button>
                  ${isArch
                    ? `<button type="button" class="mini-action-btn" data-action="reopen" data-session-id="${sidEsc}" title="Riprendi">🔄</button>`
                    : `<button type="button" class="mini-action-btn" data-action="archive" data-session-id="${sidEsc}" title="Archivia">📦</button>`}
                  <button type="button" class="mini-action-btn danger" data-action="delete" data-session-id="${sidEsc}" title="Elimina">🗑️</button>
                </div>
              </div>
            </div>
          `;
        })
        .join('') +
        (store.taskHasMore && (store.sidebarFilter === 'all' || store.sidebarFilter === 'task')
          ? `<div style="text-align:center; padding:8px;"><button type="button" class="btn btn-ghost btn-sm" id="btn-load-more-tasks">Carica altri (${data.total - sessions.length})…</button></div>`
          : '');

      if (!chatsHtml && !tasksHtml) {
        roster.innerHTML = `<div style="color:var(--muted); font-size:0.77rem; padding:10px 4px;">${store.taskQuery ? 'Nessun risultato trovato.' : 'Nessuna chat o task. Crea una nuova chat o avvia un task.'}</div>`;
      } else {
        roster.innerHTML = chatsHtml + tasksHtml;
      }
    }

    if (store.selectedSessionId && active) {
      const isArch = active.lifecycle_state === 'archived' || active.status === 'archived';
      const badgeEl = document.getElementById('active-session-badge');
      if (badgeEl) {
        badgeEl.textContent = `🤖 ${active.title || active.session_id} · ${active.session_id} (${active.status === 'working' ? 'WORKING' : (isArch ? 'ARCHIVIATO' : 'APERTO')})`;
      }
      const actSig = active.current_activity ? `${active.current_activity.tool}:${active.current_activity.summary}` : '';
      const aprSig = (data.pending_approvals || []).map((p) => `${p.approval_id}:${p.status}`).join(',');
      const stepAprSig = (active.steps || [])
        .filter((s) => s.type === 'approval' && s.meta?.approval)
        .map((s) => `${s.meta.approval.approval_id}:${s.meta.approval.status}:${s.meta.approval.decision}`)
        .join(',');
      const streamSig = `${active.session_id}:${active.status}:${active.lifecycle_state}:${(active.steps || []).length}:${(active.runs || []).length}:${active.token_summary?.total_tokens || 0}:${actSig}:${aprSig}:${stepAprSig}:${active.updated_at || ''}`;
      if (store.forceStreamRender || streamSig !== store.lastStreamSig) {
        store.lastStreamSig = streamSig;
        store.forceStreamRender = false;
        renderTaskMacroPanel(active);
        const stream = document.getElementById('agent-stream');
        if (stream) {
          stream.innerHTML = renderTaskStreamHtml(active, data.pending_approvals || []);
          scrollStreamBottom();
        }
      }
    }
  } catch (err) {
    console.error('Errore refreshAgents:', err);
  }
}

export async function stopSingleAgentRun(runId, sessionId) {
  if (!runId) return;
  await apiPost('/api/agents/run/stop', { run_id: runId, session_id: sessionId || '' });
  await refreshAgents();
  if (sessionId) await fetchFilteredAgentRuns(sessionId, true);
}

export async function updateScopePreferences(scopeId, patch) {
  if (!scopeId) return;
  await apiPost('/api/chat/preferences', { scope_id: scopeId, ...patch });
  await refreshAgents();
}

export async function resolveApprovalAction(approvalId, decision, triggerBtn = null) {
  if (!approvalId) return;
  const fb = (document.getElementById(`apr-fb-${approvalId}`)?.value || '').trim();
  const isDeny = decision === 'deny';
  const decLabel = formatApprovalDecisionLabel(decision, isDeny ? 'denied' : 'allowed');

  // Optimistic DOM update for instant 0ms user feedback
  const card = triggerBtn?.closest?.('[data-approval-card]') || document.querySelector(`[data-approval-card="${CSS.escape(approvalId)}"]`);
  if (card) {
    card.querySelectorAll('button, input').forEach((el) => { el.disabled = true; });
    card.style.borderColor = isDeny ? 'rgba(239,68,68,0.75)' : 'rgba(34,197,94,0.75)';
    card.style.background = isDeny ? 'rgba(127,29,29,0.25)' : 'rgba(20,83,45,0.28)';
    const hdr = card.querySelector('[data-apr-header]');
    if (hdr) {
      hdr.textContent = isDeny
        ? '⛔ Approvazione Negata — blocco comando in corso...'
        : '✅ Approvazione Confermata — sblocco comando in corso...';
    }
    const pill = card.querySelector('[data-apr-pill]');
    if (pill) {
      pill.textContent = decLabel;
      pill.style.background = isDeny ? 'rgba(239,68,68,0.2)' : 'rgba(34,197,94,0.2)';
      pill.style.borderColor = isDeny ? 'rgba(239,68,68,0.6)' : 'rgba(34,197,94,0.6)';
      pill.style.color = isDeny ? '#fca5a5' : '#86efac';
    }
    const actionsRow = card.querySelector('[data-apr-actions]');
    if (actionsRow) {
      actionsRow.innerHTML = `<span style="font-size:0.76rem; font-weight:600; color:${isDeny ? '#fca5a5' : '#86efac'};">${isDeny ? `⛔ Blocco confermato (${escapeHtml(decLabel)}).` : `✅ Azione confermata (${escapeHtml(decLabel)}) — esecuzione sbloccata.`}</span>`;
    }
  }

  // Optimistically sync in-memory loadedSessions so polling preserves resolved state
  for (const s of (store.loadedSessions || [])) {
    for (const st of (s.steps || [])) {
      if (st.type === 'approval' && st.meta?.approval?.approval_id === approvalId) {
        st.meta.approval.status = isDeny ? 'denied' : 'allowed';
        st.meta.approval.decision = decision;
        if (fb) st.meta.approval.feedback = fb;
      }
    }
  }

  try {
    await apiPost('/api/approvals/resolve', { approval_id: approvalId, decision, feedback: fb });
  } catch (err) {
    console.warn('resolveApprovalAction failed:', err);
  } finally {
    store.forceStreamRender = true;
    await refreshAgents();
  }
}

export function bindAgentRunsControls() {
  const main = document.getElementById('stage-stream');
  if (main && !main.dataset.runsBound) {
    main.dataset.runsBound = '1';
    main.addEventListener('click', (e) => {
      const stopBtn = e.target.closest('[data-stop-run]');
      if (stopBtn) {
        stopSingleAgentRun(stopBtn.getAttribute('data-stop-run'), stopBtn.getAttribute('data-sid'));
        return;
      }
      const delChatBtn = e.target.closest('[data-action="delete-chat"]');
      if (delChatBtn) {
        deleteChat(e, delChatBtn.getAttribute('data-chat-id') || 'chat');
        return;
      }
      const aprBtn = e.target.closest('[data-apr-decision]');
      if (aprBtn) {
        resolveApprovalAction(aprBtn.getAttribute('data-apr-id'), aprBtn.getAttribute('data-apr-decision'), aprBtn);
      }
    });
    main.addEventListener('change', (e) => {
      if (e.target?.id === 'agent-runs-status-filter') {
        agentRunsUiState.status = e.target.value || 'all';
        const sid = e.target.closest('[data-runs-sid]')?.getAttribute('data-runs-sid');
        if (sid) fetchFilteredAgentRuns(sid, true);
      } else if (e.target?.id === 'task-approval-mode') {
        const sid = e.target.getAttribute('data-sid');
        if (sid) {
          apiPost('/api/agents/approval-mode', { session_id: sid, mode: e.target.value }).catch(() => {});
        }
      }
    });
    main.addEventListener('input', (e) => {
      if (e.target?.id === 'agent-runs-search') {
        agentRunsUiState.query = e.target.value || '';
        const sid = e.target.closest('[data-runs-sid]')?.getAttribute('data-runs-sid');
        if (sid) fetchFilteredAgentRuns(sid, true);
      }
    });
    main.addEventListener('scroll', (e) => {
      const scroller = e.target;
      if (scroller?.id === 'agent-runs-scroll' && agentRunsUiState.hasMore && !agentRunsUiState.loading) {
        if (scroller.scrollTop + scroller.clientHeight >= scroller.scrollHeight - 28) {
          fetchFilteredAgentRuns(agentRunsUiState.episodeId, false);
        }
      }
    }, true);
  }
  const pop = document.getElementById('telemetry-popover-body');
  if (pop && !pop.dataset.prefsBound) {
    pop.dataset.prefsBound = '1';
    pop.addEventListener('click', (e) => {
      const stopBtn = e.target.closest('[data-stop-run]');
      if (stopBtn) {
        stopSingleAgentRun(stopBtn.getAttribute('data-stop-run'), stopBtn.getAttribute('data-sid'));
      }
    });
    pop.addEventListener('change', (e) => {
      if (e.target?.id === 'ctx-strategy-select') {
        updateScopePreferences(e.target.getAttribute('data-scope-id'), { context_strategy: e.target.value });
      } else if (e.target?.id === 'ctx-thinking-select') {
        updateScopePreferences(e.target.getAttribute('data-scope-id'), { thinking_mode: e.target.value });
      }
    });
  }
}

export async function triggerStopBargeIn() {
  if (store.activeAbortController) store.activeAbortController.abort();
  stopAssistantAudio();
  if (window.speechSynthesis) window.speechSynthesis.cancel();
  await apiPost('/api/voice', {
    utterance: store.uiLang === 'en' ? 'Hey Cortical stop' : 'Ehi Cortical basta',
    speak: store.audioResponsesEnabled,
    client_audio: true,
    lang: store.uiLang,
    voice: document.getElementById('tts-voice')?.value || 'auto',
  }).catch(() => {});
  refreshAgents();
}

export async function openNativePiTerminal() {
  const d = await apiPost('/api/agents/open-terminal', {});
  appendStreamCard('subagent', 'TERMINAL', d.platform || 'CLI', 'Apertura sessione interattiva `pi`', JSON.stringify(d, null, 2));
}

const HARNESS_SLASH_COMMANDS = [
  { cmd: '/skill', insert: '/skill ', desc: 'Importa/allega una Skill nel contesto attivo' },
  { cmd: '/task', insert: '/task ', desc: 'Avvia un nuovo Task operativo locale' },
  { cmd: '/loop', insert: '/loop ', desc: 'Avvia Task in Swarm Parallelo + Loop Verifica/Test' },
  { cmd: '/plan', insert: '/plan ', desc: 'Pianifica architettura senza modificare file' },
  { cmd: '/review', insert: '/review', desc: 'Esegue verifica e test sulle modifiche correnti' },
  { cmd: '/test', insert: '/test', desc: 'Esegue la suite unitaria (.venv)' },
  { cmd: '/diff', insert: '/diff', desc: 'Mostra git status e diff --stat del workspace' },
  { cmd: '/compact', insert: '/compact', desc: 'Compatta la memoria del contesto attivo' },
  { cmd: '/export', insert: '/export', desc: 'Esporta bundle USB (.tar.gz) di memoria, task e skill' },
  { cmd: '/clear', insert: '/clear', desc: 'Crea una nuova chat pulita' },
  { cmd: '/help', insert: '/help', desc: 'Mostra tutti i comandi / e le menzioni @' },
];

async function handleSlashCommand(rawText, depth, speak, effort) {
  const parts = rawText.trim().split(/\s+/);
  const cmd = (parts[0] || '').toLowerCase();
  const rest = rawText.trim().slice(cmd.length).trim();
  const scopeId = activeScopeId();

  if (cmd === '/skill') {
    const skills = await ensureCatalogLoadedForSuggest();
    if (!rest) {
      const names = skills.map((s) => `\`${s.name || s.id}\``).join(', ');
      appendStreamCard('system', 'HARNESS /skill', 'catalogo', 'Skill disponibili', names || 'Nessuna skill trovata.');
      return true;
    }
    const q = rest.toLowerCase();
    const match = skills.find((s) => String(s.name || s.id).toLowerCase() === q)
      || skills.find((s) => String(s.name || s.id).toLowerCase().includes(q));
    if (!match) {
      appendStreamCard('system', 'HARNESS /skill', 'non trovata', `Skill "${rest}" non trovata`, 'Usa `/` per vedere le skill disponibili.');
      return true;
    }
    await apiPost('/api/context/attach', {
      scope_id: scopeId,
      item_type: 'skill',
      item_ref: match.ref || match.path || match.id || match.name,
      label: match.name || match.id,
      depth_tier: 'medium',
    });
    await loadScopedContext(scopeId);
    appendStreamCard('assistant', 'SKILL IMPORTATA', scopeId, `⚡ ${match.name || match.id}`, `Skill collegata al contesto attivo (\`${scopeId}\`).`);
    return true;
  }
  if (cmd === '/task' && rest) {
    await spawnAgentSession(rest, depth, speak, effort);
    return true;
  }
  if (cmd === '/loop' && rest) {
    await spawnAgentSession(rest, depth, speak, effort, { auto_loop: true, parallel: true });
    return true;
  }
  if (cmd === '/plan' && rest) {
    await spawnAgentSession(`Pianifica in dettaglio senza modificare file: ${rest}`, depth, speak, 'high', { auto_loop: false });
    return true;
  }
  if (cmd === '/review') {
    await spawnAgentSession(rest || 'Verifica il codice, controlla la sintassi/test del workspace e segnala o correggi eventuali errori.', depth, speak, effort, { auto_loop: true });
    return true;
  }
  if (cmd === '/export') {
    const res = await apiPost('/api/portability/export', {});
    appendStreamCard('assistant', 'USB EXPORT', 'OK', `💾 Bundle esportato (${Math.round((res.size_bytes || 0) / 1024)} KB)`, `Percorso: \`${res.archive_path}\` (${res.files_archived} file)`);
    return true;
  }
  if (cmd === '/clear') {
    await createNewChat();
    return true;
  }
  if (['/diff', '/test', '/compact', '/help'].includes(cmd)) {
    const res = await apiPost('/api/harness/command', { command: rawText, scope_id: scopeId });
    appendStreamCard('assistant', `HARNESS ${cmd}`, res.ok ? 'OK' : 'ERR', rawText, res.output || JSON.stringify(res));
    return true;
  }
  return false;
}

async function ensureCatalogLoadedForSuggest() {
  if ((store.cachedCatalog?.skills || []).length > 0) return store.cachedCatalog.skills;
  try {
    const d = await apiGet('/api/catalog');
    store.cachedCatalog = d;
    return d.skills || [];
  } catch {
    return [];
  }
}

export function bindComposerAutocomplete() {
  const input = document.getElementById('prompt-input');
  const pop = document.getElementById('composer-suggest-popover');
  if (!input || !pop || input.dataset.acBound) return;
  input.dataset.acBound = '1';

  let items = [];
  let activeIdx = 0;
  let triggerMode = ''; // '/' | '@'
  let triggerStart = 0;

  const hidePop = () => {
    pop.classList.remove('open');
    pop.innerHTML = '';
    items = [];
    triggerMode = '';
  };

  const renderItems = () => {
    if (!items.length) {
      hidePop();
      return;
    }
    pop.innerHTML = items.slice(0, 12).map((it, idx) => (
      `<div class="suggest-item ${idx === activeIdx ? 'active' : ''}" data-ac-idx="${idx}">`
      + `<span><b>${escapeHtml(it.title)}</b></span>`
      + `<span class="suggest-meta">${escapeHtml(it.subtitle || '')}</span>`
      + `</div>`
    )).join('');
    pop.classList.add('open');
  };

  const applySelection = async (it) => {
    if (!it) return;
    if (it.action === 'attach_skill') {
      input.value = '';
      autoResizeComposer();
      hidePop();
      await handleSlashCommand(`/skill ${it.skillName}`, 'medium', false, 'medium');
      return;
    }
    const before = input.value.slice(0, triggerStart);
    const after = input.value.slice(input.selectionStart || input.value.length);
    input.value = `${before}${it.insert}${after}`;
    const pos = (before + it.insert).length;
    input.setSelectionRange(pos, pos);
    autoResizeComposer();
    hidePop();
    input.focus();
  };

  input.addEventListener('input', async () => {
    const val = input.value;
    const caret = input.selectionStart || val.length;
    const upto = val.slice(0, caret);

    // 1. Slash command or /skill autocomplete
    if (upto.startsWith('/')) {
      triggerMode = '/';
      triggerStart = 0;
      const lower = upto.toLowerCase();
      const skills = await ensureCatalogLoadedForSuggest();
      if (lower.startsWith('/skill ')) {
        const q = lower.slice(7).trim();
        items = skills
          .filter((s) => !q || String(s.name || s.id).toLowerCase().includes(q))
          .map((s) => ({
            title: `⚡ /skill ${s.name || s.id}`,
            subtitle: s.description || 'Allega skill al contesto attivo',
            action: 'attach_skill',
            skillName: s.name || s.id,
          }));
      } else {
        const q = lower.slice(1).trim();
        const cmdMatches = HARNESS_SLASH_COMMANDS
          .filter((c) => !q || c.cmd.slice(1).includes(q) || c.desc.toLowerCase().includes(q))
          .map((c) => ({ title: c.cmd, subtitle: c.desc, insert: c.insert }));
        const skillMatches = q
          ? skills
              .filter((s) => String(s.name || s.id).toLowerCase().includes(q))
              .slice(0, 6)
              .map((s) => ({
                title: `⚡ Importa Skill: ${s.name || s.id}`,
                subtitle: 'Allega subito al contesto',
                action: 'attach_skill',
                skillName: s.name || s.id,
              }))
          : [];
        items = [...cmdMatches, ...skillMatches];
      }
      activeIdx = 0;
      renderItems();
      return;
    }

    // 2. @ mention autocomplete (tasks, chats, skills)
    const m = upto.match(/(^|\s)@([^\s]*)$/);
    if (m) {
      triggerMode = '@';
      triggerStart = upto.length - m[2].length - 1;
      const q = m[2].toLowerCase();
      const taskItems = (store.loadedSessions || [])
        .filter((s) => !q || s.session_id.toLowerCase().includes(q) || String(s.title || s.goal || '').toLowerCase().includes(q))
        .slice(0, 8)
        .map((s) => ({
          title: `🤖 @${s.session_id}`,
          subtitle: s.title || s.goal || s.status,
          insert: `@${s.session_id} `,
        }));
      const chatItems = (store.loadedChats || [])
        .filter((c) => !q || c.chat_id.toLowerCase().includes(q) || String(c.title || '').toLowerCase().includes(q))
        .slice(0, 4)
        .map((c) => ({
          title: `💬 @${c.chat_id}`,
          subtitle: c.title || c.chat_id,
          insert: `@${c.chat_id} `,
        }));
      items = [...taskItems, ...chatItems];
      activeIdx = 0;
      renderItems();
      return;
    }
    hidePop();
  });

  input.addEventListener('keydown', (e) => {
    if (!pop.classList.contains('open') || !items.length) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      activeIdx = (activeIdx + 1) % Math.min(items.length, 12);
      renderItems();
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      const maxLen = Math.min(items.length, 12);
      activeIdx = (activeIdx - 1 + maxLen) % maxLen;
      renderItems();
    } else if (e.key === 'Tab' || (e.key === 'Enter' && !e.shiftKey && !e.metaKey && !e.ctrlKey)) {
      e.preventDefault();
      e.stopImmediatePropagation();
      applySelection(items[activeIdx]);
    } else if (e.key === 'Escape') {
      hidePop();
    }
  });

  pop.addEventListener('click', (e) => {
    const row = e.target.closest('[data-ac-idx]');
    if (!row) return;
    const idx = Number(row.getAttribute('data-ac-idx'));
    applySelection(items[idx]);
  });
}

export function closeTokenReportModal() {
  document.getElementById('token-report-modal-overlay')?.classList.remove('open');
}

export async function openTokenReportModal(withNarrative = false) {
  const overlay = document.getElementById('token-report-modal-overlay');
  const body = document.getElementById('token-report-body');
  if (!overlay || !body) return;
  overlay.classList.add('open');
  body.innerHTML = `<div style="color:var(--muted);">⏳ Calcolo statistiche locali + remote (0 token cloud)${withNarrative ? ' + analisi LLM locale' : ''}...</div>`;
  try {
    const ep = store.activeScopeType === 'task' && store.activeScopeId ? `&episode_id=${encodeURIComponent(store.activeScopeId)}` : '';
    const data = await apiGet(`/api/tokens/report?narrative=${withNarrative ? '1' : '0'}${ep}`);
    const g = data.global_stats || {};
    const rem = g.remote || {};
    const loc = g.local || {};
    const roi = g.roi || {};
    const mem = g.memory_and_skills || {};
    const tasks = (data.per_task || []).slice(0, 8);
    const chats = (data.per_chat || []).slice(0, 8);
    const insight = data.local_llm_insight;
    const exp = data.explanations || {};

    body.innerHTML = `
      <div class="macro-kpi-grid" style="margin-bottom:12px;">
        <div class="macro-kpi" title="${escapeHtml(exp.local_offload || '')} ${escapeHtml(exp.memory_saved || '')}"><div class="macro-kpi-val">${Number(roi.estimated_cloud_tokens_saved || 0).toLocaleString()}</div><div class="macro-kpi-lbl">Token Cloud Risparmiati ⓘ</div></div>
        <div class="macro-kpi" title="${escapeHtml(exp.cloud_savings_usd || '')} | ${escapeHtml(exp.offload_share || '')}"><div class="macro-kpi-val">~$${Number(roi.estimated_usd_saved || 0).toFixed(2)}</div><div class="macro-kpi-lbl">Risparmio (${Number(roi.cloud_offload_share_pct || 0).toFixed(1)}% offload) ⓘ</div></div>
        <div class="macro-kpi" title="${escapeHtml(exp.local_offload || '')}"><div class="macro-kpi-val">${Number(loc.total_tokens || 0).toLocaleString()}</div><div class="macro-kpi-lbl">Token Locali (${loc.run_count || 0} run · ${Number(loc.total_elapsed_sec || 0).toFixed(1)}s) ⓘ</div></div>
        <div class="macro-kpi" title="${escapeHtml(exp.remote_usage || '')}"><div class="macro-kpi-val">${Number(rem.active_tokens || 0).toLocaleString()}</div><div class="macro-kpi-lbl">Cloud Attivi (${rem.chat_count || 0} chat · cache ${Number(rem.cache_hit_pct || 0).toFixed(1)}%) ⓘ</div></div>
      </div>
      <div style="padding:8px 10px; border:1px solid var(--border); border-radius:8px; margin-bottom:12px; background:rgba(15,23,42,0.45);" title="${escapeHtml(exp.memory_saved || '')}">
        <b>Second Brain 3+1 &amp; Skill:</b> ${mem.episodes_total || 0} task (${mem.episodes_archived || 0} archiviati) · ${mem.syntheses_3plus1 || 0} sintesi 3+1 · ${mem.memory_insights || 0} insight · ${mem.learned_skills || 0} skill (${mem.skill_uses || 0} usi) · ~${Number(mem.estimated_memory_tokens_saved || 0).toLocaleString()} token contesto risparmiati.
      </div>
      ${insight && insight.text ? `<div style="padding:8px 10px; border:1px solid var(--accent); border-radius:8px; margin-bottom:12px; white-space:pre-wrap;"><b>🧠 Analista Locale (${escapeHtml(insight.source || 'local')}):</b>\n${escapeHtml(insight.text)}</div>` : ''}
      <div style="font-weight:700; color:var(--muted); margin-bottom:4px;">TOP TASK CORTICAL (LOCALI)</div>
      <div style="margin-bottom:12px; display:flex; flex-direction:column; gap:4px;">
        ${tasks.length ? tasks.map((t) => `<div style="padding:5px 8px; border:1px solid var(--border); border-radius:6px; display:flex; justify-content:space-between; gap:8px;"><span><code>${escapeHtml(t.episode_id)}</code> · ${escapeHtml(t.goal || '')}</span><span style="white-space:nowrap;"><b>${Number(t.local_total_tokens || 0).toLocaleString()}</b> tok (${t.run_count} run · ${Number(t.elapsed_sec || 0).toFixed(1)}s)</span></div>`).join('') : '<div style="color:var(--muted);">Nessun run locale registrato.</div>'}
      </div>
      <div style="font-weight:700; color:var(--muted); margin-bottom:4px;">CHAT REMOTE RECENTI (${rem.measured_chat_count || 0} misurate / ${rem.estimated_chat_count || 0} stimate)</div>
      <div style="display:flex; flex-direction:column; gap:4px; margin-bottom:12px;">
        ${chats.length ? chats.map((c) => `<div style="padding:5px 8px; border:1px solid var(--border); border-radius:6px; display:flex; justify-content:space-between; gap:8px;"><span><code>${escapeHtml((c.conversation_id || '').slice(0, 8))}</code> (${escapeHtml(c.source)}) ${c.uses_cortical ? '⚡' : ''} · ${escapeHtml(c.title || '')}</span><span style="white-space:nowrap;">in ${Number(c.input_tokens || 0).toLocaleString()} · out ${Number(c.output_tokens || 0).toLocaleString()} (~$${Number(c.estimated_cost_usd || 0).toFixed(2)})</span></div>`).join('') : '<div style="color:var(--muted);">Nessun transcript remoto trovato.</div>'}
      </div>
      <details style="border-top:1px solid var(--border); padding-top:8px; color:var(--muted); font-size:0.74rem;">
        <summary style="cursor:pointer; font-weight:700;">📐 Note Metodologiche &amp; Formule (0 token cloud)</summary>
        <ul style="margin:6px 0 0 16px; padding:0; display:flex; flex-direction:column; gap:3px;">
          <li><b>[1] Remote:</b> ${escapeHtml(exp.remote_usage || '')}</li>
          <li><b>[2] Locale &amp; Tempo:</b> ${escapeHtml(exp.local_offload || '')}</li>
          <li><b>[3] Memoria 3+1:</b> ${escapeHtml(exp.memory_saved || '')}</li>
          <li><b>[4] Risparmio USD:</b> ${escapeHtml(exp.cloud_savings_usd || '')}</li>
          <li><b>[5] Quota Offload:</b> ${escapeHtml(exp.offload_share || '')}</li>
        </ul>
      </details>
    `;
  } catch (err) {
    body.innerHTML = `<div style="color:#fca5a5;">Errore caricamento Token Report: ${escapeHtml(err.message)}</div>`;
  }
}
