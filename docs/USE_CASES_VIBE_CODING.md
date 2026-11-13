# Cortical 100% Local Voice & Vibe-Coding Use Cases

Documentazione progressiva delle capacità agentiche e del flusso **Voice-to-Code 100% locale** di Cortical (`qwen3:8b` / `qwen3.8:27b-iq2_xs` via Ollama + `pi` harness + Second Brain Merkle Wiki).

---

## Architettura del Flusso Audio & Vibe Coding

1. **Cattura & Modalità Microfono (`src/cortical/ui/js/audio.js`)**:
   - **🎙️ Auto (1.4s)**: invio rapido per domande, comandi browser e approvazioni vocali (`"approva"`, `"consenti sempre"`, `"nega, usa Vanilla JS"`).
   - **⚡ Vibe Code (2.8s + live buffer)**: estende la finestra di pausa a 2.8s e scrive la trascrizione in tempo reale dentro `#prompt-input`, evitando tagli a metà frase durante prompt di coding complessi.
   - **📝 Dettatura**: accumula il testo dettato nel composer finché l'utente non preme Invio / `🚀 Task` oppure pronuncia `"invia comando"` / `"esegui adesso"`.
   - **Fallback Dettatura Locale macOS**: se WebSpeech non è raggiungibile offline, focalizza automaticamente `#prompt-input` per dettatura locale (`Fn×2`).

2. **Voice-to-Task & Voice Approval (`src/cortical/memory.py`, `src/cortical/voice/engine.py`, `src/cortical/server.py`)**:
   - `is_vibe_coding_request(cmd)` riconosce intenzioni vocali di sviluppo (`"vibe code..."`, `"crea un gioco..."`, `"costruisci un'app..."`, `"implementa..."`, `"fixa il bug..."`) distinguendole dalle domande teoriche (`"come si..."`, `"spiegami..."`), avviando automaticamente un task `system2_agentic`.
   - **Approvazione Vocale Unificata con `ApprovalBroker`**: quando un agente locale è in `awaiting_approval` (`ask` mode), pronunciare `"approva"`, `"approva questa sessione"`, `"consenti sempre"` o `"nega, <istruzione>"` sblocca immediatamente il tool gate senza toccare il mouse.

---

## Casi d'Uso a Complessità Crescente (100% LLM Locali)

| Livello | Caso d'Uso | Modello / Route | Output Verificato |
| :--- | :--- | :--- | :--- |
| **Livello 1** | **Voice Reflex & Approvazione Vocale** | `qwen2.5:1.5b` / `voice_engine` | `POST /api/voice` `"approva questa sessione"` -> `permission_feedback` (`3.66 ms`), sblocco immediato `ApprovalBroker`. |
| **Livello 2** | **Single-File App: Tic-Tac-Toe** | `pi` + Ollama locale (`pi-935734`, `9.178` tok) | [examples/vibe_games/tic_tac_toe/index.html](../examples/vibe_games/tic_tac_toe/index.html) (`4.676 B`) — griglia 3×3, modalità vs CPU, score, reset. |
| **Livello 3** | **Multi-State Logic: Sliding 15-Puzzle** | `pi` + Ollama locale (`pi-65806`, `9.935` tok) | [examples/vibe_games/sliding_puzzle/index.html](../examples/vibe_games/sliding_puzzle/index.html) (`7.311 B`) — mescolamento risolvibile, contatore mosse, timer, vittoria. |
| **Livello 4** | **Real-Time Arcade: Pac-Man** | `pi` + Ollama locale (`pi-78336`, `10.011` tok) | [examples/vibe_games/pacman/index.html](../examples/vibe_games/pacman/index.html) (`4.680 B`) — HTML5 Canvas, labirinto a griglia, fantasmi, pellet, punteggio, vite. |

### Prompt Vocali Usati

- **Livello 2 (Tic-Tac-Toe)**:
  > *"Vibe code un videogioco Tic-Tac-Toe completo e giocabile in un singolo file HTML dentro `examples/vibe_games/tic_tac_toe/index.html` con modalità 2 giocatori e contro CPU, contatore punteggio, evidenziazione combinazione vincente e pulsante reset."*
- **Livello 3 (Sliding 15-Puzzle)**:
  > *"Vibe code un gioco Puzzle 15 (4x4 sliding puzzle) completo in un singolo file HTML dentro `examples/vibe_games/sliding_puzzle/index.html` con mescolamento garantito risolvibile, contatore mosse, timer, stile moderno dark e rilevamento vittoria."*
- **Livello 4 (Pac-Man)**:
  > *"Vibe code un videogioco Pac-Man arcade giocabile in un singolo file HTML5 Canvas dentro `examples/vibe_games/pacman/index.html` con labirinto a griglia, pallini, power pellet, 4 fantasmi con IA (chase e frightened blu), punteggio, 3 vite, controlli tastiera frecce/WASD, overlay Game Over/Vittoria e pulsante Rigioca."*

---

## Esecuzione Locale dei Giochi Generati

```bash
cd examples/vibe_games
python3 -m http.server 8777 --bind 127.0.0.1
# Apri:
# - http://127.0.0.1:8777/tic_tac_toe/index.html
# - http://127.0.0.1:8777/sliding_puzzle/index.html
# - http://127.0.0.1:8777/pacman/index.html
```
