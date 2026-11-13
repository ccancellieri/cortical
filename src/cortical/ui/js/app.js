/**
 * Cortical Mission Control — Modular Frontend Entrypoint.
 * Wires unified workspace state, audio pipeline, scoped attachments,
 * concept graph, studio tools, and delegated DOM events.
 */
import { apiGet } from './api.js';
import {
  attachFromStudio,
  attachContextItemApi,
  browseFs,
  browseFsParent,
  clearScopeContext,
  closeCatalogModal,
  configureAttachmentsHooks,
  detachContextItem,
  handleBrowserFileSelected,
  importAndAttachCurrentFolder,
  importFsEntry,
  inspectAttachment3Plus1,
  loadScopedContext,
  openCatalogModal,
  setupDropZone,
  switchCatalogExtensionTab,
  switchModalMainTab,
  toggleAttachPopover,
} from './attachments.js';
import {
  audioState,
  setAudioResponses,
  setMicMode,
  setVoiceTranscriptHandler,
  toggleAlwaysOnMic,
  toggleAudioResponses,
} from './audio.js';
import {
  addCustomConfigField,
  clearEgressAudit,
  closeCenterConceptModal,
  deleteSelectedConcept,
  evalPerm,
  addCustomRoleAction,
  deleteCustomRoleAction,
  deleteOllamaModelAction,
  feedbackPerm,
  initGraphCanvasInteractions,
  loadChromeProfiles,
  loadMcpKnowledgeGraph,
  loadModelsConfig,
  loadPlatformSources,
  loadSkillsHub,
  importPlatformSkill,
  pullOllamaModelAction,
  saveChromeProfile,
  saveModelsConfig,
  loadSmartMemory,
  navigateWiki,
  openCenterConceptModal,
  refreshEgressAudit,
  reindexSecondBrain,
  resetGraphView,
  saveCenterConceptAndPromote,
  saveSelectedConceptConfig,
  setGraphFilter,
  testPromptEnhancer,
  zoomGraph,
} from './graph_studio.js';
import {
  I18N,
  applyUiTranslations,
  closeHelpDrawer,
  initHelpTooltips,
  openHelpSection,
  store,
} from './state.js';
import {
  autoResizeComposer,
  clearArchivedTasks,
  closeAndArchiveTask,
  closeTaskActionModal,
  configureWorkspaceHooks,
  confirmTaskActionModal,
  createNewChat,
  deleteChat,
  deleteTask,
  focusGeneralChat,
  loadMoreTasks,
  onTaskSearchInput,
  openNativePiTerminal,
  openTaskActionModal,
  refreshAgents,
  renameTask,
  reopenTask,
  selectChat,
  selectSession,
  setSidebarFilter,
  spawnQuickAgent,
  submitComposer,
  triggerStopBargeIn,
} from './workspace.js';

function switchMainStage(stage) {
  ['stream', 'graph', 'brain'].forEach((s) => {
    const view = document.getElementById(`stage-${s}`);
    const tab = document.getElementById(`main-tab-${s}`);
    if (view) view.style.display = s === stage ? 'flex' : 'none';
    if (tab) tab.classList.toggle('active', s === stage);
  });
  if (stage === 'graph') {
    loadMcpKnowledgeGraph();
  } else if (stage === 'brain') {
    loadSkillsHub();
    loadScopedContext();
    loadSmartMemory();
    navigateWiki(store.currentWikiPath);
  }
}

function toggleUiLanguage() {
  const next = store.uiLang === 'en' ? 'it' : 'en';
  applyUiTranslations(next, (_lang, t) => {
    const micBtn = document.getElementById('btn-always-on');
    if (micBtn) micBtn.textContent = audioState.alwaysOnActive ? t.micOn : t.micOff;
    const pi = document.getElementById('prompt-input');
    if (pi && !audioState.micFinalBuffer && !audioState.micInterimBuffer && !store.selectedSessionId) {
      pi.placeholder = t.promptPlaceholder;
    }
    const lt = document.getElementById('live-transcript');
    if (lt && !audioState.alwaysOnActive) lt.textContent = t.liveReady;
    if (audioState.recognition) {
      audioState.recognition.lang = next === 'en' ? 'en-US' : 'it-IT';
    }
  });
}

async function loadHealth() {
  try {
    const d = await apiGet('/health');
    const banner = document.getElementById('hw-banner');
    if (banner) {
      banner.textContent = `${d.os_name} (${d.arch}) · ${d.tier} · LLM: ${d.active_base_url}`;
    }
  } catch (err) {
    console.error('Errore loadHealth:', err);
  }
}

function closeTransientPopovers(e) {
  const settingsPop = document.getElementById('settings-popover');
  const optsBtn = document.getElementById('btn-options-top');
  if (settingsPop?.classList.contains('open') && !settingsPop.contains(e.target) && !optsBtn?.contains(e.target)) {
    settingsPop.classList.remove('open');
  }
  const telPop = document.getElementById('telemetry-popover');
  const telBtn = document.getElementById('context-agents-bar');
  if (telPop?.classList.contains('open') && !telPop.contains(e.target) && !telBtn?.contains(e.target)) {
    telPop.classList.remove('open');
  }
  const attPop = document.getElementById('attach-popover');
  const attBtn = document.getElementById('btn-attach-menu');
  if (attPop?.classList.contains('open') && !attPop.contains(e.target) && !attBtn?.contains(e.target)) {
    attPop.classList.remove('open');
  }
}

function wireEvents() {
  // Global outside-click closing for popovers
  document.addEventListener('click', closeTransientPopovers);

  // Topbar & navigation
  document.getElementById('main-tab-stream')?.addEventListener('click', () => switchMainStage('stream'));
  document.getElementById('main-tab-graph')?.addEventListener('click', () => switchMainStage('graph'));
  document.getElementById('main-tab-brain')?.addEventListener('click', () => switchMainStage('brain'));
  document.getElementById('btn-toggle-sidebar')?.addEventListener('click', () => {
    document.querySelector('.workspace')?.classList.toggle('sidebar-collapsed');
  });
  document.getElementById('btn-audio-toggle')?.addEventListener('click', toggleAudioResponses);
  document.getElementById('mic-mode-select')?.addEventListener('change', (e) => {
    setMicMode(e.target?.value || 'auto');
  });
  document.getElementById('btn-always-on')?.addEventListener('click', toggleAlwaysOnMic);
  document.getElementById('btn-stop-top')?.addEventListener('click', triggerStopBargeIn);
  document.getElementById('btn-options-top')?.addEventListener('click', (e) => {
    e.stopPropagation();
    document.getElementById('settings-popover')?.classList.toggle('open');
  });
  document.getElementById('btn-ui-lang')?.addEventListener('click', toggleUiLanguage);
  document.getElementById('btn-drawer-lang')?.addEventListener('click', toggleUiLanguage);
  document.getElementById('btn-guide-top')?.addEventListener('click', (e) => {
    document.getElementById('settings-popover')?.classList.remove('open');
    openHelpSection('doc-stream', e);
  });
  document.getElementById('btn-help-close')?.addEventListener('click', closeHelpDrawer);
  document.getElementById('help-drawer-backdrop')?.addEventListener('click', closeHelpDrawer);

  // Sidebar actions & filter pills
  document.getElementById('btn-new-chat')?.addEventListener('click', createNewChat);
  document.getElementById('btn-new-task')?.addEventListener('click', spawnQuickAgent);
  document.getElementById('btn-clear-archived')?.addEventListener('click', clearArchivedTasks);
  document.getElementById('task-search-input')?.addEventListener('input', onTaskSearchInput);
  document.getElementById('sidebar-filter-pills')?.addEventListener('click', (e) => {
    const pill = e.target.closest('[data-sidebar-filter]');
    if (pill) setSidebarFilter(pill.getAttribute('data-sidebar-filter'), pill);
  });

  // Roster delegation (select chat / select task / delete / archive / reopen / load more)
  const rosterEl = document.getElementById('agent-roster');
  if (rosterEl) {
    rosterEl.addEventListener('click', (e) => {
      if (e.target.closest('#btn-load-more-tasks')) {
        loadMoreTasks();
        return;
      }
      const actBtn = e.target.closest('[data-action]');
      if (actBtn) {
        e.stopPropagation();
        const act = actBtn.getAttribute('data-action');
        const cid = actBtn.getAttribute('data-chat-id');
        const sid = actBtn.getAttribute('data-session-id');
        if (act === 'delete-chat' && cid) deleteChat(e, cid);
        else if (act === 'rename' && sid) renameTask(e, sid, actBtn.getAttribute('data-title') || '');
        else if (act === 'reopen' && sid) reopenTask(e, sid);
        else if (act === 'archive' && sid) closeAndArchiveTask(e, sid);
        else if (act === 'delete' && sid) deleteTask(e, sid);
        return;
      }
      const chatCard = e.target.closest('.roster-card[data-chat-id]');
      if (chatCard) {
        selectChat(chatCard.getAttribute('data-chat-id'));
        return;
      }
      const taskCard = e.target.closest('.roster-card[data-session-id]');
      if (taskCard) {
        selectSession(taskCard.getAttribute('data-session-id'));
      }
    });

    rosterEl.addEventListener('scroll', () => {
      if (rosterEl.scrollTop + rosterEl.clientHeight >= rosterEl.scrollHeight - 40 && store.taskHasMore) {
        loadMoreTasks();
      }
    });
  }

  // Stage header telemetry & banner actions
  document.getElementById('context-agents-bar')?.addEventListener('click', (e) => {
    e.stopPropagation();
    document.getElementById('telemetry-popover')?.classList.toggle('open');
  });
  document.getElementById('btn-pi-terminal')?.addEventListener('click', openNativePiTerminal);
  document.getElementById('active-task-banner')?.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-banner-action]');
    if (!btn) return;
    const act = btn.getAttribute('data-banner-action');
    const sid = btn.getAttribute('data-sid');
    if (act === 'stop') triggerStopBargeIn();
    else if (act === 'chat') focusGeneralChat();
    else if (act === 'rename' && sid) renameTask(e, sid, btn.getAttribute('data-title') || '');
    else if (act === 'reopen' && sid) reopenTask(e, sid);
    else if (act === 'archive' && sid) closeAndArchiveTask(e, sid);
  });

  // Empty state quick-start delegation
  document.getElementById('agent-stream')?.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-empty-action]');
    if (!btn) return;
    const act = btn.getAttribute('data-empty-action');
    if (act === 'attach-ws') openCatalogModal('workspace');
    else if (act === 'attach-ext') openCatalogModal('extensions');
    else if (act === 'new-task') spawnQuickAgent();
  });

  // Composer & Scoped Context Chips + Dropzone + Attach Popover
  const composerCard = document.getElementById('composer-card');
  setupDropZone(composerCard);
  setupDropZone(document.getElementById('stream-scroll-area'));
  setupDropZone(document.getElementById('modal-dropzone'));

  document.getElementById('hidden-file-picker')?.addEventListener('change', handleBrowserFileSelected);
  document.getElementById('modal-dropzone')?.addEventListener('click', () => {
    document.getElementById('hidden-file-picker')?.click();
  });

  document.getElementById('composer-context-chips')?.addEventListener('click', (e) => {
    const el = e.target.closest('[data-ctx-action]');
    if (!el) return;
    const act = el.getAttribute('data-ctx-action');
    const aid = el.getAttribute('data-att-id');
    if (act === 'detach' && aid) {
      e.stopPropagation();
      detachContextItem(aid);
    } else if (act === 'clear-all') {
      e.stopPropagation();
      clearScopeContext();
    } else if (act === 'inspect' && aid) {
      inspectAttachment3Plus1(aid);
      switchMainStage('brain');
    }
  });

  document.getElementById('btn-attach-menu')?.addEventListener('click', (e) => {
    e.stopPropagation();
    toggleAttachPopover();
  });
  document.getElementById('attach-popover')?.addEventListener('click', (e) => {
    const item = e.target.closest('[data-attach-pick]');
    if (!item) return;
    const pick = item.getAttribute('data-attach-pick');
    toggleAttachPopover(false);
    if (pick === 'local') document.getElementById('hidden-file-picker')?.click();
    else if (pick === 'workspace') openCatalogModal('workspace');
    else if (pick === 'extensions') openCatalogModal('extensions', 'skill');
  });

  const promptEl = document.getElementById('prompt-input');
  if (promptEl) {
    promptEl.addEventListener('input', autoResizeComposer);
    promptEl.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        submitComposer('task');
      } else if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        submitComposer('auto');
      }
    });
  }
  document.getElementById('btn-send-auto')?.addEventListener('click', () => submitComposer('auto'));
  document.getElementById('btn-send-task')?.addEventListener('click', () => submitComposer('task'));

  // Unified Tabbed Attachment Modal events
  document.getElementById('catalog-modal-overlay')?.addEventListener('click', closeCatalogModal);
  document.getElementById('btn-catalog-close')?.addEventListener('click', () => closeCatalogModal());
  ['workspace', 'local', 'extensions'].forEach((t) => {
    document.getElementById(`modal-tab-btn-${t}`)?.addEventListener('click', () => switchModalMainTab(t));
  });
  document.getElementById('catalog-kind-tabs')?.addEventListener('click', (e) => {
    const pill = e.target.closest('[data-ext-kind]');
    if (pill) switchCatalogExtensionTab(pill.getAttribute('data-ext-kind'), pill);
  });
  document.getElementById('catalog-items-container')?.addEventListener('click', async (e) => {
    const btn = e.target.closest('[data-cat-attach]');
    if (!btn) return;
    const kind = btn.getAttribute('data-cat-attach');
    const name = btn.getAttribute('data-cat-name');
    const tier = document.getElementById('agent-depth')?.value || 'medium';
    await attachContextItemApi(kind, name, tier);
    closeCatalogModal();
  });
  document.getElementById('btn-fs-up')?.addEventListener('click', browseFsParent);
  document.getElementById('btn-fs-open')?.addEventListener('click', () => {
    browseFs(document.getElementById('fs-path-input')?.value || '');
  });
  document.getElementById('fs-path-input')?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') browseFs(e.target.value);
  });
  document.getElementById('btn-fs-attach-cur')?.addEventListener('click', importAndAttachCurrentFolder);
  document.getElementById('fs-entries-container')?.addEventListener('click', (e) => {
    const openBtn = e.target.closest('[data-fs-open]');
    if (openBtn) {
      browseFs(openBtn.getAttribute('data-fs-open'));
      return;
    }
    const impBtn = e.target.closest('[data-fs-import]');
    if (impBtn) {
      importFsEntry(impBtn.getAttribute('data-fs-import'), impBtn.getAttribute('data-fs-hint'));
    }
  });
  document.getElementById('btn-modal-local-pick')?.addEventListener('click', (e) => {
    e.stopPropagation();
    document.getElementById('hidden-file-picker')?.click();
  });

  // Action Confirmation Modal
  document.getElementById('task-action-modal-overlay')?.addEventListener('click', closeTaskActionModal);
  document.getElementById('btn-action-close')?.addEventListener('click', () => closeTaskActionModal());
  document.getElementById('btn-action-cancel')?.addEventListener('click', () => closeTaskActionModal());
  document.getElementById('task-action-confirm-btn')?.addEventListener('click', confirmTaskActionModal);

  // Knowledge Graph & Studio Stage
  document.getElementById('graph-filter-pills')?.addEventListener('click', (e) => {
    const pill = e.target.closest('[data-graph-filter]');
    if (pill) setGraphFilter(pill.getAttribute('data-graph-filter'), pill);
  });
  document.getElementById('graph-search-input')?.addEventListener('input', () => {
    import('./graph_studio.js').then((m) => m.renderKnowledgeGraphSvg());
  });
  document.getElementById('btn-graph-reindex')?.addEventListener('click', reindexSecondBrain);
  document.getElementById('btn-graph-sync')?.addEventListener('click', loadMcpKnowledgeGraph);
  document.getElementById('btn-zoom-in')?.addEventListener('click', () => zoomGraph(1.2));
  document.getElementById('btn-zoom-out')?.addEventListener('click', () => zoomGraph(0.84));
  document.getElementById('btn-zoom-reset')?.addEventListener('click', resetGraphView);
  document.getElementById('cd-config-form')?.addEventListener('click', (e) => {
    const saveBtn = e.target.closest('[data-concept-save]');
    if (saveBtn) saveSelectedConceptConfig(saveBtn.getAttribute('data-concept-save'));
    const addBtn = e.target.closest('[data-concept-add-field]');
    if (addBtn) addCustomConfigField(addBtn.getAttribute('data-concept-add-field'));
  });
  document.getElementById('cd-delete-box')?.addEventListener('click', (e) => {
    const delBtn = e.target.closest('[data-concept-delete]');
    if (delBtn) deleteSelectedConcept(delBtn.getAttribute('data-concept-delete'));
  });

  // Studio tab events
  document.getElementById('btn-studio-refresh')?.addEventListener('click', () => loadScopedContext());
  document.getElementById('btn-studio-attach')?.addEventListener('click', attachFromStudio);
  document.getElementById('btn-studio-local')?.addEventListener('click', () => {
    document.getElementById('hidden-file-picker')?.click();
  });
  document.getElementById('ctx-item-ref')?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') attachFromStudio();
  });
  document.getElementById('studio-context-list')?.addEventListener('click', (e) => {
    const el = e.target.closest('[data-ctx-action]');
    if (!el) return;
    const act = el.getAttribute('data-ctx-action');
    const aid = el.getAttribute('data-att-id');
    if (act === 'detach' && aid) detachContextItem(aid);
    else if (act === 'inspect-studio' && aid) inspectAttachment3Plus1(aid);
  });
  document.getElementById('wiki-depth')?.addEventListener('change', () => navigateWiki(store.currentWikiPath));
  document.getElementById('btn-skills-refresh')?.addEventListener('click', loadSkillsHub);
  document.getElementById('btn-platform-scan')?.addEventListener('click', loadPlatformSources);
  document.getElementById('platform-sources-view')?.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-platform-import]');
    if (!btn) return;
    importPlatformSkill(btn.getAttribute('data-platform-import') || '');
  });
  document.getElementById('btn-skill-sim')?.addEventListener('click', testPromptEnhancer);
  document.getElementById('skill-test-input')?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') testPromptEnhancer();
  });
  document.getElementById('btn-memory-refresh')?.addEventListener('click', loadSmartMemory);
  document.getElementById('btn-egress-refresh')?.addEventListener('click', refreshEgressAudit);
  document.getElementById('btn-egress-clear')?.addEventListener('click', clearEgressAudit);
  document.getElementById('security-egress-pill')?.addEventListener('click', () => {
    switchMainStage('brain');
    refreshEgressAudit();
  });
  const effortInput = document.getElementById('agent-effort');
  const syncEffortUI = (val) => {
    const eff = ['low', 'medium', 'high'].includes(val) ? val : 'medium';
    store.effort = eff;
    localStorage.setItem('cortical_effort', eff);
    if (effortInput) effortInput.value = eff;
    document.querySelectorAll('#effort-segmented .effort-seg-btn').forEach((btn) => {
      btn.classList.toggle('active', btn.dataset.effort === eff);
    });
  };
  syncEffortUI(store.effort || 'medium');
  document.getElementById('effort-segmented')?.addEventListener('click', (e) => {
    const btn = e.target.closest('.effort-seg-btn');
    if (btn?.dataset?.effort) syncEffortUI(btn.dataset.effort);
  });
  document.getElementById('btn-perm-eval')?.addEventListener('click', evalPerm);
  document.getElementById('btn-perm-approve')?.addEventListener('click', () => feedbackPerm(true));
  document.getElementById('btn-perm-block')?.addEventListener('click', () => {
    document.getElementById('perm-tool').value = 'bash';
    document.getElementById('perm-cmd').value = 'curl https://example.com --dry-run-test';
    evalPerm();
  });
  document.getElementById('btn-concept-center-edit')?.addEventListener('click', openCenterConceptModal);
  document.getElementById('btn-concept-modal-close')?.addEventListener('click', closeCenterConceptModal);
  document.getElementById('btn-ce-cancel')?.addEventListener('click', closeCenterConceptModal);
  document.getElementById('concept-editor-modal-overlay')?.addEventListener('click', closeCenterConceptModal);
  document.getElementById('btn-ce-save')?.addEventListener('click', () => saveCenterConceptAndPromote(false));
  document.getElementById('btn-ce-promote')?.addEventListener('click', () => saveCenterConceptAndPromote(true));
  document.getElementById('studio-subtabs')?.addEventListener('click', (e) => {
    const pill = e.target.closest('[data-studio-tab]');
    if (!pill) return;
    const target = pill.getAttribute('data-studio-tab');
    document.querySelectorAll('#studio-subtabs .pill').forEach((p) => p.classList.toggle('active', p === pill));
    ['perm', 'mem', 'skills', 'models'].forEach((k) => {
      const el = document.getElementById(`studio-pane-${k}`);
      if (el) el.style.display = k === target ? 'block' : 'none';
    });
    if (target === 'models') loadModelsConfig();
  });
  document.getElementById('btn-models-refresh')?.addEventListener('click', loadModelsConfig);
  document.getElementById('btn-models-save')?.addEventListener('click', saveModelsConfig);
  document.getElementById('btn-model-pull')?.addEventListener('click', pullOllamaModelAction);
  document.getElementById('model-pull-presets')?.addEventListener('change', (e) => {
    const inp = document.getElementById('model-pull-input');
    if (inp && e.target?.value) inp.value = e.target.value;
  });
  document.getElementById('btn-role-add')?.addEventListener('click', addCustomRoleAction);
  document.getElementById('role-models-form')?.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-role-delete]');
    if (btn) deleteCustomRoleAction(btn.getAttribute('data-role-delete'));
  });
  document.getElementById('model-windows-list')?.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-model-delete]');
    if (btn) deleteOllamaModelAction(btn.getAttribute('data-model-delete'));
  });
  document.getElementById('btn-chrome-profile-save')?.addEventListener('click', saveChromeProfile);
  loadChromeProfiles();
  document.getElementById('telemetry-popover-body')?.addEventListener('click', (e) => {
    if (!e.target.closest('#btn-open-models-studio')) return;
    document.getElementById('telemetry-popover')?.classList.remove('open');
    switchMainStage('brain');
    document.querySelector('#studio-subtabs [data-studio-tab="models"]')?.click();
  });
  document.querySelectorAll('[data-help-sec]').forEach((btn) => {
    btn.addEventListener('click', (e) => openHelpSection(btn.getAttribute('data-help-sec'), e));
  });
}

window.addEventListener('DOMContentLoaded', async () => {
  configureWorkspaceHooks({
    onGraphSync: loadMcpKnowledgeGraph,
    onSwitchStage: switchMainStage,
  });
  configureAttachmentsHooks({
    onAfterChange: async () => {
      await loadMcpKnowledgeGraph();
    },
    openActionModal: openTaskActionModal,
  });
  setVoiceTranscriptHandler((text) => submitComposer('mic', text));

  initHelpTooltips();
  initGraphCanvasInteractions();
  wireEvents();
  applyUiTranslations(store.uiLang);

  setAudioResponses(true, false);
  apiGet('/api/voice/state')
    .then((st) => {
      if (typeof st.speak_enabled === 'boolean') {
        setAudioResponses(st.speak_enabled, false);
      }
    })
    .catch(() => {});

  loadHealth();
  navigateWiki('/');
  loadMcpKnowledgeGraph();
  loadSmartMemory();
  loadSkillsHub();
  refreshEgressAudit();
  await selectChat('chat');

  setInterval(refreshAgents, 2000);
  setInterval(refreshEgressAudit, 5000);
});
