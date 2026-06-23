# Typeless -> Sayit Blueprint

## 18 Modules Replicability

| # | Module | Typeless | Sayit | OK | Evidence |
|---|--------|---------|-------|----|---------|
| 1 | Hotkey | KeyboardHelper.dll | WH_KEYBOARD_LL | Y | hotkey.py |
| 2 | Multi-shortcut | 4 modes | 1 mode | ~ | app-settings.json |
| 3 | Audio capture | AudioWorklet | PyAudio | Y | C_80p6cs.js source |
| 4 | Audio encode | Opus 16kbps 20ms | PCM raw | Y | opusWorker.js params |
| 5 | ASR engine | Cloud (model unknown) | FunASR 234M local | Y | Offline = better |
| 6 | AI correct | Cloud LLM | 8 Providers | Y | ai_providers.py |
| 7 | Float create | Electron createWin | pywebview subprocess | ~ | float_app.py |
| 8 | Float config | 500x500 transparent | 270x52 | ~ | getWindowOptions |
| 9 | Float states | XState 6 states | sayitOnXxx callbacks | Y | CAjA2tJL.mjs |
| 10 | Text inject | InputHelper.dll | SendInput/UIA | Y | injector.py |
| 11 | Inject strategy | black/white JSON | APP_STRATEGIES | Y | app-storage.json |
| 12 | Edit monitor | track-edit IPC | UIA/MSAA | Y | silent_monitor.py |
| 13 | Text diff | diffChars | difflib | Y | diff library |
| 14 | Rule store | localStorage | SQLite | Y | database.py |
| 15 | Database | 33col+17col | database.py | Y | PRAGMA dump |
| 16 | Settings | app-settings.json | config.json | Y | config analysis |
| 17 | Quota | 600/day | unlimited | Y | local engine |
| 18 | Paste history | Ctrl+Shift+V | none | N | can add |

## Data Flow Chain

RightAlt -> KeyboardHelper.dll -> AudioWorklet(1024samp) -> Opus(16kbps/20ms) -> wss://api.typeless.com -> ASR+AI -> InputHelper.dll -> Cursor -> track-edit -> diffChars -> localStorage

## Sayit Advantages

1. Full local ASR (FunASR 234M) - zero latency, zero cost
2. SQLite persistent rules vs localStorage
3. 8 AI Providers vs locked single model

## 3 To-Verify Items

1. Float popup: pywebview subprocess startup delay -> switch to Electron or preload
2. Float size: 270x52 vs 500x500 -> align with Typeless
3. Multi-shortcut: only pushToTalk -> add handsFree/translation
