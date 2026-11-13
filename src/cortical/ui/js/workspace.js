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
  const title = chatObj?.title || (store.activeChatId === 'chat' ? 'Chat Generale' : store.activeChatId);
  if (!messages || !messages.length) {
    stream.innerHTML = `
      <div class="empty-state-card">
        <h3>💬 ${escapeHtml(title)}</h3>
        <p>Ogni chat e ogni task ha allegati e memoria isolati. Scrivi qui sotto, trascina file nel box o usa un avvio rapido:</p>
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

  stream.innerHTML = messages
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

export async function spawnAgentSession(goal, depth, speak, effortOverride) {
  const effort = effortOverride || document.getElementById('agent-effort')?.value || store.effort || 'medium';
  const sess = await apiPost('/api/agents/spawn', {
    goal,
    wiki_depth: depth,
    effort,
    speak: Boolean(speak),
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
  if (!chatId || chatId === 'chat') return;
  openTaskActionModal({
    title: '🗑️ Elimina Chat',
    desc: 'Confermi l\'eliminazione definitiva di questa chat, della sua cronologia e dei suoi allegati?',
    showInput: false,
    confirmLabel: '🗑️ Elimina Chat',
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
        <div><b>📊 Contesto (${escapeHtml(scopeLabel)}):</b> ${usedTok} / ${winTok} tok (<b>${occPct}%</b>) · <code>${escapeHtml(contextTelemetry?.active_model || 'qwen3.8:27b-iq2_xs')}</code></div>
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

function renderApprovalCardHtml(pa) {
  if (!pa) return '';
  const isPending = pa.status === 'pending';
  const riskPct = Math.round(Number(pa.risk || 0) * 100);
  const borderCol = isPending ? 'rgba(251,191,36,0.75)' : (pa.status === 'allowed' ? 'rgba(34,197,94,0.45)' : 'rgba(239,68,68,0.45)');
  return `
    <div class="step-card" style="border:1.5px solid ${borderCol}; background:rgba(15,23,42,0.85); margin:8px 0; padding:10px 12px; border-radius:10px;">
      <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; margin-bottom:6px;">
        <span style="font-weight:700; font-size:0.82rem;">🔐 Approvazione Tool: <code>${escapeHtml(pa.tool || 'bash')}</code></span>
        <span class="status-pill">${escapeHtml(pa.pattern || '')} · rischio ${riskPct}%</span>
      </div>
      <pre class="step-detail" style="margin:0 0 8px 0; padding:8px; background:rgba(2,6,23,0.65); border-radius:6px; white-space:pre-wrap;">${escapeHtml(pa.summary || '')}</pre>
      ${pa.reason ? `<div style="font-size:0.72rem; color:var(--muted); margin-bottom:8px;">${escapeHtml(pa.reason)}</div>` : ''}
      ${isPending ? `
        <div style="display:flex; flex-wrap:wrap; gap:6px; align-items:center;">
          <button type="button" class="btn btn-sm" data-apr-id="${escapeHtml(pa.approval_id)}" data-apr-decision="allow_once">✓ Consenti</button>
          <button type="button" class="btn btn-ghost btn-sm" data-apr-id="${escapeHtml(pa.approval_id)}" data-apr-decision="allow_session">✓ Questa sessione</button>
          <button type="button" class="btn btn-ghost btn-sm" data-apr-id="${escapeHtml(pa.approval_id)}" data-apr-decision="allow_always">★ Sempre</button>
          <button type="button" class="btn btn-danger btn-sm" data-apr-id="${escapeHtml(pa.approval_id)}" data-apr-decision="deny">✕ Nega</button>
          <input type="text" id="apr-fb-${escapeHtml(pa.approval_id)}" placeholder="Feedback opzionale se neghi..." style="flex:1; min-width:170px; font-size:0.74rem;" />
        </div>
      ` : `<div style="font-size:0.74rem; color:var(--muted);">Esito: <b>${escapeHtml(pa.decision || pa.status)}</b>${pa.feedback ? ` · ${escapeHtml(pa.feedback)}` : ''}</div>`}
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
          return `
            <div class="final-report-card">
              <div class="step-meta"><span>✅ ${escapeHtml(st.title)}</span><span>${escapeHtml(st.timestamp || '')}</span></div>
              <div class="final-report-prose">${formatProseHtml(st.detail || '')}</div>
            </div>
          `;
        }
        const icon = typ === 'tool_call' ? '🔧' : (typ === 'tool_result' ? '📦' : (typ === 'subagent' ? '🤖' : '🧠'));
        return `
          <details class="tool-trace">
            <summary class="tool-trace-summary">
              <span>${icon} <b>${escapeHtml(typ.toUpperCase())}</b> · ${escapeHtml(st.title)}</span>
              <span style="color:var(--muted); flex-shrink:0;">${escapeHtml(st.timestamp || '')}</span>
            </summary>
            ${st.detail ? `<div class="tool-trace-body"><pre class="step-detail">${escapeHtml(st.detail)}</pre></div>` : ''}
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
      visibleChats.map((c) => [c.chat_id, c.title, c.turn_count || 0]),
      visibleSessions.map((s) => [s.session_id, s.status, s.lifecycle_state, (s.steps || []).length, s.token_summary?.total_tokens || 0]),
    ]);

    const roster = document.getElementById('agent-roster');
    if (roster && rosterSig !== store.lastRosterSig) {
      store.lastRosterSig = rosterSig;
      const chatsHtml = visibleChats
        .map((c) => {
          const cidEsc = escapeHtml(c.chat_id);
          const isActiveChat = !store.selectedSessionId && c.chat_id === store.activeChatId;
          return `
            <div class="roster-card chat-card ${isActiveChat ? 'active' : ''}" data-chat-id="${cidEsc}">
              <div class="roster-card-top">
                <span class="roster-title">💬 ${escapeHtml(c.title || c.chat_id)}</span>
                <span class="status-pill status-open">CHAT</span>
              </div>
              <div class="roster-meta-row">
                <span class="roster-meta">${c.turn_count || 0} messaggi</span>
                ${c.chat_id !== 'chat' ? `
                  <div class="roster-hover-actions">
                    <button type="button" class="mini-action-btn danger" data-action="delete-chat" data-chat-id="${cidEsc}" title="Elimina chat">🗑️</button>
                  </div>
                ` : ''}
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
      const streamSig = `${active.session_id}:${active.status}:${active.lifecycle_state}:${(active.steps || []).length}:${(active.runs || []).length}:${active.token_summary?.total_tokens || 0}:${actSig}:${aprSig}:${active.updated_at || ''}`;
      if (store.forceStreamRender || streamSig !== store.lastStreamSig) {
        store.lastStreamSig = streamSig;
        store.forceStreamRender = false;
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

export async function resolveApprovalAction(approvalId, decision) {
  if (!approvalId) return;
  const fb = (document.getElementById(`apr-fb-${approvalId}`)?.value || '').trim();
  await apiPost('/api/approvals/resolve', { approval_id: approvalId, decision, feedback: fb });
  store.forceStreamRender = true;
  await refreshAgents();
}

export function bindAgentRunsControls() {
  const main = document.getElementById('stage-chat');
  if (main && !main.dataset.runsBound) {
    main.dataset.runsBound = '1';
    main.addEventListener('click', (e) => {
      const stopBtn = e.target.closest('[data-stop-run]');
      if (stopBtn) {
        stopSingleAgentRun(stopBtn.getAttribute('data-stop-run'), stopBtn.getAttribute('data-sid'));
        return;
      }
      const aprBtn = e.target.closest('[data-apr-decision]');
      if (aprBtn) {
        resolveApprovalAction(aprBtn.getAttribute('data-apr-id'), aprBtn.getAttribute('data-apr-decision'));
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
