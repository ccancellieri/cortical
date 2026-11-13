/**
 * Audio playback, Web Audio GainNode ducking, WebRTC hardware AEC3 monitoring,
 * continuous Web Speech recognition, and global Audio ON/OFF server sync.
 */
import { apiPost } from './api.js';
import { I18N, store } from './state.js';

let assistantAudioCtx = null;
let assistantGainNode = null;
let assistantAnalyser = null;
let assistantAudioEl = null;
let assistantSourceNode = null;
let micMediaStream = null;
let micAnalyser = null;
let acousticMonitorTimer = null;
let duckRestoreTimer = null;
let assistantDucked = false;
let assistantBaselineCentroidHz = 0;

export const audioState = {
  alwaysOnActive: false,
  recognition: null,
  micFinalBuffer: '',
  micInterimBuffer: '',
  micCommitTimer: null,
  micRestartTimer: null,
  micIsRecognizing: false,
  micNetworkErrors: 0,
  acousticUserPriorityDetected: false,
  lastMicRms: 0,
  lastAssistantRms: 0,
  lastSpokenResponseText: '',
  lastSpokenAtMs: 0,
  localTtsShieldUntilMs: 0,
};

let onVoiceTranscriptCb = null;

export function setVoiceTranscriptHandler(cb) {
  onVoiceTranscriptCb = cb;
}

export async function setAudioResponses(enabled, syncServer = true) {
  store.audioResponsesEnabled = Boolean(enabled);
  const chk = document.getElementById('chk-speak');
  const btn = document.getElementById('btn-audio-toggle');
  if (chk) chk.checked = store.audioResponsesEnabled;
  if (btn) {
    btn.textContent = store.audioResponsesEnabled ? '🔊 Audio: ON' : '🔇 Audio: OFF';
    btn.className = store.audioResponsesEnabled ? 'btn btn-sm' : 'btn btn-ghost btn-sm';
  }
  if (!store.audioResponsesEnabled) {
    stopAssistantAudio();
  }
  if (syncServer) {
    await apiPost('/api/voice/config', { speak_enabled: store.audioResponsesEnabled }).catch(() => {});
  }
}

export function toggleAudioResponses() {
  return setAudioResponses(!store.audioResponsesEnabled, true);
}

function updateDuckBadge(ducked) {
  const badge = document.getElementById('acoustic-duck-badge');
  if (!badge) return;
  const t = I18N[store.uiLang] || I18N.it;
  badge.style.display = isAssistantAudioPlaying() || ducked ? 'inline-block' : 'none';
  if (ducked) {
    badge.textContent = t.duckLow;
    badge.style.color = '#fbbf24';
    badge.style.borderColor = 'rgba(251,191,36,0.55)';
  } else {
    badge.textContent = t.duckNormal;
    badge.style.color = 'var(--muted)';
    badge.style.borderColor = 'var(--border)';
  }
}

export function ensureAssistantAudioPipeline() {
  const AC = window.AudioContext || window.webkitAudioContext;
  if (!AC) return false;
  if (!assistantAudioCtx) {
    assistantAudioCtx = new AC();
    assistantGainNode = assistantAudioCtx.createGain();
    assistantGainNode.gain.value = 1.0;
    assistantAnalyser = assistantAudioCtx.createAnalyser();
    assistantAnalyser.fftSize = 1024;
    assistantAudioEl = new Audio();
    assistantAudioEl.crossOrigin = 'anonymous';
    assistantSourceNode = assistantAudioCtx.createMediaElementSource(assistantAudioEl);
    assistantSourceNode.connect(assistantAnalyser);
    assistantAnalyser.connect(assistantGainNode);
    assistantGainNode.connect(assistantAudioCtx.destination);
    assistantAudioEl.onended = () => {
      audioState.localTtsShieldUntilMs = 0;
      restoreAssistantAudio(1.0);
    };
  }
  if (assistantAudioCtx.state === 'suspended') {
    assistantAudioCtx.resume().catch(() => {});
  }
  return true;
}

export function isAssistantAudioPlaying() {
  return Boolean(assistantAudioEl && !assistantAudioEl.paused && !assistantAudioEl.ended);
}

export function duckAssistantAudio(level = 0.14) {
  if (!assistantGainNode || !assistantAudioCtx) return;
  const now = assistantAudioCtx.currentTime;
  assistantGainNode.gain.cancelScheduledValues(now);
  assistantGainNode.gain.setTargetAtTime(level, now, 0.035);
  assistantDucked = true;
  updateDuckBadge(true);
}

export function restoreAssistantAudio(level = 1.0) {
  if (!assistantGainNode || !assistantAudioCtx) return;
  const now = assistantAudioCtx.currentTime;
  assistantGainNode.gain.cancelScheduledValues(now);
  assistantGainNode.gain.setTargetAtTime(level, now, 0.14);
  assistantDucked = false;
  updateDuckBadge(false);
}

export function stopAssistantAudio() {
  if (duckRestoreTimer) {
    clearTimeout(duckRestoreTimer);
    duckRestoreTimer = null;
  }
  if (assistantAudioEl) {
    try {
      assistantAudioEl.pause();
      assistantAudioEl.currentTime = 0;
    } catch (_) {}
  }
  restoreAssistantAudio(1.0);
}

export async function playAssistantAudioUrl(url, fallbackText = '') {
  if (!url && !fallbackText) return;
  if (url && ensureAssistantAudioPipeline()) {
    stopAssistantAudio();
    if (assistantAudioCtx && assistantAudioCtx.state === 'suspended') {
      try { await assistantAudioCtx.resume(); } catch (_) {}
    }
    assistantAudioEl.src = url;
    assistantBaselineCentroidHz = 0;
    restoreAssistantAudio(1.0);
    try {
      await assistantAudioEl.play();
      return;
    } catch (err) {
      console.warn('Web Audio play warning, trying plain Audio fallback:', err);
      try {
        const plain = new Audio(url);
        await plain.play();
        return;
      } catch (err2) {
        console.warn('Plain Audio fallback failed:', err2);
      }
    }
  }
  if (fallbackText && 'speechSynthesis' in window) {
    try {
      window.speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(fallbackText);
      u.lang = store.uiLang === 'en' ? 'en-US' : 'it-IT';
      window.speechSynthesis.speak(u);
    } catch (_) {}
  }
}

function getAnalyserRmsAndCentroid(analyser, sampleRate) {
  if (!analyser) return { rms: 0, centroidHz: 0 };
  const timeData = new Float32Array(analyser.fftSize);
  analyser.getFloatTimeDomainData(timeData);
  let sumSq = 0;
  for (let i = 0; i < timeData.length; i++) sumSq += timeData[i] * timeData[i];
  const rms = Math.sqrt(sumSq / timeData.length);
  const freqData = new Uint8Array(analyser.frequencyBinCount);
  analyser.getByteFrequencyData(freqData);
  const binHz = (sampleRate || 48000) / (analyser.fftSize || 1024);
  let weighted = 0;
  let total = 0;
  for (let i = 1; i < freqData.length; i++) {
    weighted += freqData[i] * (i * binHz);
    total += freqData[i];
  }
  return { rms, centroidHz: total > 0 ? weighted / total : 0 };
}

async function startAcousticMonitor() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return;
  ensureAssistantAudioPipeline();
  try {
    if (!micMediaStream) {
      micMediaStream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
      });
      const micSource = assistantAudioCtx.createMediaStreamSource(micMediaStream);
      micAnalyser = assistantAudioCtx.createAnalyser();
      micAnalyser.fftSize = 1024;
      micSource.connect(micAnalyser);
    }
    if (acousticMonitorTimer) clearInterval(acousticMonitorTimer);
    acousticMonitorTimer = setInterval(() => {
      if (!audioState.alwaysOnActive || !micAnalyser || !assistantAudioCtx) return;
      const sr = assistantAudioCtx.sampleRate || 48000;
      const micStats = getAnalyserRmsAndCentroid(micAnalyser, sr);
      const asstStats = getAnalyserRmsAndCentroid(assistantAnalyser, sr);
      audioState.lastMicRms = Number(micStats.rms.toFixed(4));
      audioState.lastAssistantRms = Number(asstStats.rms.toFixed(4));

      if (isAssistantAudioPlaying() && asstStats.rms > 0.015 && asstStats.centroidHz > 80) {
        assistantBaselineCentroidHz = assistantBaselineCentroidHz
          ? assistantBaselineCentroidHz * 0.85 + asstStats.centroidHz * 0.15
          : asstStats.centroidHz;
      }

      if (isAssistantAudioPlaying()) {
        const pitchDiff = assistantBaselineCentroidHz > 80 && micStats.centroidHz > 80
          ? Math.abs(micStats.centroidHz - assistantBaselineCentroidHz) / assistantBaselineCentroidHz
          : 0;
        const userSpeakingNow = micStats.rms > 0.024 && (micStats.rms > asstStats.rms * 0.9 || pitchDiff > 0.14);
        if (userSpeakingNow) {
          audioState.acousticUserPriorityDetected = true;
          if (!assistantDucked) duckAssistantAudio(0.14);
          if (duckRestoreTimer) clearTimeout(duckRestoreTimer);
          duckRestoreTimer = setTimeout(() => {
            if (!audioState.micInterimBuffer && !audioState.micFinalBuffer && isAssistantAudioPlaying()) {
              restoreAssistantAudio(1.0);
              audioState.acousticUserPriorityDetected = false;
            }
          }, 1600);
        }
      }
    }, 70);
  } catch (err) {
    console.warn('Hardware AEC getUserMedia unavailable:', err);
  }
}

function stopAcousticMonitor() {
  if (acousticMonitorTimer) {
    clearInterval(acousticMonitorTimer);
    acousticMonitorTimer = null;
  }
  if (micMediaStream) {
    micMediaStream.getTracks().forEach((t) => t.stop());
    micMediaStream = null;
  }
  micAnalyser = null;
  audioState.acousticUserPriorityDetected = false;
}

export function hasWakeOrBargeInWord(s) {
  return /\b(cortical|peppe|ferma|fermati|stop|basta|silenzio|zitto|annulla|aspetta|quiet|cancel|nevermind|enough|wait)\b/i.test(s || '');
}

export function detectLangClient(s) {
  if (!s) return store.uiLang || 'it';
  if (/[àèéìòù]/i.test(s)) return 'it';
  const enHits = (s.match(/\b(the|what|when|where|how|weather|tomorrow|open|search|browser|wikipedia|read|summarize|page|hey|create|task)\b/gi) || []).length;
  const itHits = (s.match(/\b(che|cosa|come|meteo|domani|apri|cerca|browser|leggi|riassumi|pagina|ehi|crea|task|ora)\b/gi) || []).length;
  if (enHits > itHits) return 'en';
  if (itHits > enHits) return 'it';
  return store.uiLang || 'it';
}

export function normalizeTokens(s) {
  return (s || '')
    .toLowerCase()
    .replace(/(\d+)[.,](\d+)\s*°c/gi, '$1 virgola $2 gradi')
    .replace(/(\d+)\s*°c/gi, '$1 gradi')
    .replace(/\bmin\s+(\d+)/gi, 'minima $1')
    .replace(/\bmax\s+(\d+)/gi, 'massima $1')
    .replace(/(\d+)\s*%/g, '$1 per cento')
    .replace(/[^\w\sàèéìòù]/g, ' ')
    .split(/\s+/)
    .filter((w) => w.length > 1);
}

export function isSelfEchoClient(candidate) {
  if (!candidate) return false;
  if (hasWakeOrBargeInWord(candidate)) return false;
  const candWords = normalizeTokens(candidate);
  const spokenWords = new Set(normalizeTokens(audioState.lastSpokenResponseText || ''));
  const overlap = candWords.length && spokenWords.size
    ? candWords.filter((w) => spokenWords.has(w)).length / candWords.length
    : 0;
  const shieldActive = isAssistantAudioPlaying() || Date.now() < audioState.localTtsShieldUntilMs;
  if (shieldActive) {
    return candWords.length < 4 || overlap >= 0.35;
  }
  if (!audioState.lastSpokenResponseText) return false;
  if ((Date.now() - audioState.lastSpokenAtMs) / 1000.0 > 25.0) return false;
  if (!candWords.length || !spokenWords.size) return false;
  const candJoined = candWords.join(' ');
  const spokenJoined = normalizeTokens(audioState.lastSpokenResponseText).join(' ');
  if (candJoined.length >= 5 && spokenJoined.includes(candJoined)) return true;
  return overlap >= 0.45;
}

function flushMicTranscriptBuffer() {
  if (audioState.micCommitTimer) {
    clearTimeout(audioState.micCommitTimer);
    audioState.micCommitTimer = null;
  }
  const combined = `${audioState.micFinalBuffer} ${audioState.micInterimBuffer}`.replace(/\s+/g, ' ').trim();
  audioState.micFinalBuffer = '';
  audioState.micInterimBuffer = '';
  const pi = document.getElementById('prompt-input');
  if (pi) pi.placeholder = (I18N[store.uiLang] || I18N.it).promptPlaceholder;
  if (!combined) return;
  if (isSelfEchoClient(combined) && !audioState.acousticUserPriorityDetected) {
    const lt = document.getElementById('live-transcript');
    if (lt) lt.textContent = '🔇 Eco ignorato';
    return;
  }
  const lt = document.getElementById('live-transcript');
  if (lt) {
    lt.textContent = `🗣️ "${combined}"`;
    lt.title = combined;
  }
  if (typeof onVoiceTranscriptCb === 'function') {
    onVoiceTranscriptCb(combined);
  }
}

function scheduleMicCommit(delayMs) {
  if (audioState.micCommitTimer) clearTimeout(audioState.micCommitTimer);
  audioState.micCommitTimer = setTimeout(flushMicTranscriptBuffer, delayMs);
}

function startMicRecognizer() {
  if (!audioState.alwaysOnActive || !audioState.recognition || audioState.micIsRecognizing) return;
  try {
    audioState.recognition.start();
  } catch (_) {}
}

export function toggleAlwaysOnMic() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const micBtn = document.getElementById('btn-always-on');
  const micDot = document.getElementById('mic-dot');
  const lt = document.getElementById('live-transcript');
  if (!SR) {
    if (lt) lt.textContent = 'WebSpeech N/D';
    return;
  }
  if (audioState.alwaysOnActive) {
    audioState.alwaysOnActive = false;
    stopAcousticMonitor();
    if (audioState.micCommitTimer) clearTimeout(audioState.micCommitTimer);
    if (audioState.micRestartTimer) clearTimeout(audioState.micRestartTimer);
    audioState.micFinalBuffer = '';
    audioState.micInterimBuffer = '';
    if (audioState.recognition) {
      try { audioState.recognition.stop(); } catch (_) {}
    }
    audioState.micIsRecognizing = false;
    if (micDot) micDot.classList.remove('listening');
    if (micBtn) micBtn.textContent = (I18N[store.uiLang] || I18N.it).micOff;
    if (lt) lt.textContent = (I18N[store.uiLang] || I18N.it).liveReady;
    return;
  }

  // Start WebSpeech synchronously inside the click gesture without getUserMedia preflight,
  // avoiding macOS CoreAudio device contention and Chrome gesture-expiry issues.
  audioState.alwaysOnActive = true;
  audioState.micFinalBuffer = '';
  audioState.micInterimBuffer = '';
  audioState.micNetworkErrors = 0;
  audioState.micCaptureErrors = 0;
  if (micDot) micDot.classList.add('listening');
  if (micBtn) micBtn.textContent = (I18N[store.uiLang] || I18N.it).micOn;
  if (lt) lt.textContent = store.uiLang === 'en' ? 'Listening...' : 'In ascolto...';

  let useContinuous = true;

  const createAndBindRecognizer = () => {
    const rec = new SR();
    audioState.recognition = rec;
    rec.lang = store.uiLang === 'en' ? 'en-US' : 'it-IT';
    rec.continuous = useContinuous;
    rec.interimResults = true;
    rec.maxAlternatives = 1;

    rec.onstart = () => {
      audioState.micIsRecognizing = true;
      if (!audioState.micFinalBuffer && !audioState.micInterimBuffer && audioState.micNetworkErrors === 0 && lt) {
        lt.textContent = store.uiLang === 'en' ? '🎙️ Listening' : '🎙️ Ascolto';
      }
    };

    rec.onresult = (event) => {
      audioState.micNetworkErrors = 0;
      let currentInterim = '';
      for (let i = event.resultIndex; i < event.results.length; ++i) {
        const chunk = (event.results[i][0]?.transcript || '').trim();
        if (!chunk) continue;
        if (isSelfEchoClient(chunk) && !audioState.micFinalBuffer) continue;
        if (event.results[i].isFinal) {
          audioState.micFinalBuffer = `${audioState.micFinalBuffer} ${chunk}`.replace(/\s+/g, ' ').trim();
          audioState.micInterimBuffer = '';
          if (hasWakeOrBargeInWord(audioState.micFinalBuffer) && audioState.micFinalBuffer.split(/\s+/).length <= 4) {
            flushMicTranscriptBuffer();
            return;
          }
          scheduleMicCommit(1250);
        } else {
          currentInterim += `${chunk} `;
          if (isAssistantAudioPlaying() && !isSelfEchoClient(currentInterim)) {
            audioState.acousticUserPriorityDetected = true;
            duckAssistantAudio(0.14);
          }
          if (hasWakeOrBargeInWord(currentInterim)) {
            audioState.localTtsShieldUntilMs = 0;
            stopAssistantAudio();
            apiPost('/api/voice/duck', { force_stop: true }).catch(() => {});
          }
        }
      }
      if (currentInterim.trim()) {
        audioState.micInterimBuffer = currentInterim.trim();
        scheduleMicCommit(2200);
      }
      const preview = `${audioState.micFinalBuffer} ${audioState.micInterimBuffer}`.replace(/\s+/g, ' ').trim();
      if (preview && lt) {
        lt.textContent = `🎙️ ${preview}`;
        lt.title = preview;
      }
    };

    rec.onerror = (ev) => {
      const err = ev?.error || 'unknown';
      if (err === 'not-allowed' || err === 'service-not-allowed') {
        audioState.alwaysOnActive = false;
        audioState.micIsRecognizing = false;
        if (micDot) micDot.classList.remove('listening');
        if (micBtn) micBtn.textContent = store.uiLang === 'en' ? '🎤 Denied' : '🎤 Negato';
        if (lt) lt.textContent = store.uiLang === 'en' ? '🚫 Mic denied' : '🚫 Mic negato';
      } else if (err === 'network') {
        audioState.micNetworkErrors = (audioState.micNetworkErrors || 0) + 1;
        // Fallback from continuous=true to utterance mode (continuous=false) on retry
        useContinuous = false;
        if (audioState.micNetworkErrors >= 4) {
          audioState.alwaysOnActive = false;
          audioState.micIsRecognizing = false;
          if (micDot) micDot.classList.remove('listening');
          if (micBtn) micBtn.textContent = (I18N[store.uiLang] || I18N.it).micOff;
          if (lt) {
            lt.textContent = store.uiLang === 'en'
              ? '⚠️ WebSpeech offline (use macOS Dictation Fn×2 or Chrome localhost)'
              : '⚠️ WebSpeech offline (usa Dettatura macOS Fn×2 o Chrome su localhost)';
          }
          document.getElementById('prompt-input')?.focus();
        } else if (lt) {
          lt.textContent = store.uiLang === 'en'
            ? `⚠️ WebSpeech network retry (${audioState.micNetworkErrors}/3)`
            : `⚠️ WebSpeech offline/rete (tentativo ${audioState.micNetworkErrors}/3)`;
        }
      } else if (err === 'audio-capture') {
        audioState.micCaptureErrors = (audioState.micCaptureErrors || 0) + 1;
        if (audioState.micCaptureErrors >= 2) {
          audioState.alwaysOnActive = false;
          audioState.micIsRecognizing = false;
          if (micDot) micDot.classList.remove('listening');
          if (micBtn) micBtn.textContent = (I18N[store.uiLang] || I18N.it).micOff;
          if (lt) lt.textContent = store.uiLang === 'en' ? '⚠️ No microphone detected' : '⚠️ Nessun microfono rilevato';
        } else if (lt) {
          lt.textContent = store.uiLang === 'en' ? '⚠️ Mic busy, retrying...' : '⚠️ Microfono occupato, riprovo...';
        }
      } else if (err !== 'no-speech' && err !== 'aborted') {
        if (lt) lt.textContent = `⚠️ Mic: ${err}`;
      }
    };

    rec.onend = () => {
      audioState.micIsRecognizing = false;
      if (audioState.micFinalBuffer || audioState.micInterimBuffer) {
        flushMicTranscriptBuffer();
      }
      if (audioState.alwaysOnActive) {
        if (audioState.micRestartTimer) clearTimeout(audioState.micRestartTimer);
        const delayMs = audioState.micNetworkErrors > 0
          ? Math.min(4000, 900 * audioState.micNetworkErrors)
          : 220;
        audioState.micRestartTimer = setTimeout(() => {
          if (audioState.micNetworkErrors > 0) {
            createAndBindRecognizer();
          }
          startMicRecognizer();
        }, delayMs);
      }
    };
  };

  createAndBindRecognizer();
  startMicRecognizer();
}
