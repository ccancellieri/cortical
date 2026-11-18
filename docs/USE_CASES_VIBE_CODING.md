# Cortical 100% Local Voice & Vibe-Coding Use Cases

Documentazione progressiva delle capacità agentiche e del flusso **Voice-to-Code 100% locale** di Cortical (`qwen3.8:27b-iq2_xs` / `qwen3:8b` via Ollama + `pi` harness + Second Brain Merkle Wiki).

---

## Architettura del Flusso Audio & Vibe Coding

1. **Cattura & Modalità Microfono (`src/cortical/ui/js/audio.js`)**:
   - **🎙️ Auto (1.4s)**: invio rapido per domande, comandi browser e approvazioni vocali (`"approva"`, `"consenti sempre"`, `"nega, usa Vanilla JS"`).
   - **⚡ Vibe Code (2.8s + live buffer)**: estende la finestra di pausa a 2.8s e scrive la trascrizione in tempo reale dentro `#prompt-input`, evitando tagli a metà frase durante prompt di coding complessi.
   - **📝 Dettatura**: accumula il testo dettato nel composer finché l'utente non preme Invio / `🚀 Task` oppure pronuncia `"invia comando"` / `"esegui adesso"`.
   - **Fallback Dettatura Locale macOS**: se WebSpeech non è raggiungibile offline, focalizza automaticamente `#prompt-input` per dettatura locale (`Fn×2`).

2. **Voice-to-Task, Anti-Loop & Approval UX (`src/cortical/agent_runtime.py`, `.pi/extensions/cortical-harness.ts`, `src/cortical/ui/js/workspace.js`)**:
   - `is_vibe_coding_request(cmd)` riconosce intenzioni vocali di sviluppo e avvia automaticamente un task `system2_agentic`.
   - **ApprovalBroker + UI Ottimistica**: cliccare **✓ Consenti** / **✓ Questa sessione** / **★ Sempre** / **✕ Nega** trasforma immediatamente la card in stato confermato (`✅ Comando Autorizzato`), memorizza i comandi esatti già autorizzati (`_session_exact_allow`) ed evita retry infiniti su comandi silenziosi (`open`, `mkdir`) tramite guardia anti-loop e streaming immediato di `tool_result`.

---

## Casi d'Uso a Complessità Crescente (100% LLM Locali)

| Livello | Caso d'Uso | URL Live (`:8765`) | File |
| :--- | :--- | :--- | :--- |
| **Livello 1** | **Voice Reflex & Approvazione Vocale** | `http://127.0.0.1:8765/` | [src/cortical/voice/engine.py](../src/cortical/voice/engine.py) |
| **Livello 2** | **Single-File App: Tic-Tac-Toe (Tris)** | `http://127.0.0.1:8765/examples/vibe_games/tic_tac_toe/index.html` | [examples/vibe_games/tic_tac_toe/index.html](../examples/vibe_games/tic_tac_toe/index.html) |
| **Livello 3** | **Multi-State Logic: Puzzle 15 (4×4)** | `http://127.0.0.1:8765/examples/vibe_games/sliding_puzzle/index.html` | [examples/vibe_games/sliding_puzzle/index.html](../examples/vibe_games/sliding_puzzle/index.html) |
| **Livello 4** | **Real-Time Canvas: Neon Snake** | `http://127.0.0.1:8765/examples/vibe_games/snake/index.html` | [examples/vibe_games/snake/index.html](../examples/vibe_games/snake/index.html) |
| **Livello 5** | **Full Arcade Engine: Pac-Man** | `http://127.0.0.1:8765/examples/vibe_games/pacman/index.html` | [examples/vibe_games/pacman/index.html](../examples/vibe_games/pacman/index.html) |

---

## Esecuzione Live su Cortical Mission Control

Il server Cortical serve direttamente tutti i giochi e l'Arcade Hub:

- **Arcade Hub**: `http://127.0.0.1:8765/examples/vibe_games/index.html`
- **Tic-Tac-Toe**: `http://127.0.0.1:8765/examples/vibe_games/tic_tac_toe/index.html`
- **Puzzle 15**: `http://127.0.0.1:8765/examples/vibe_games/sliding_puzzle/index.html`
- **Neon Snake**: `http://127.0.0.1:8765/examples/vibe_games/snake/index.html`
- **Arcade Pac-Man**: `http://127.0.0.1:8765/examples/vibe_games/pacman/index.html`
