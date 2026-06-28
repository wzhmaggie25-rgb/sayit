// Typeless ref: Ch_class.js lines 8409-8558
// Architecture: events drive everything — no polling (like Typeless IPC)
// Backend events via WebSocket → main.js forwards to float.html
// Hotkey: WH_KEYBOARD_LL hook lives in Python backend via keyboard_helper DLL
const { app, BrowserWindow, screen, ipcMain, clipboard } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const WebSocket = require('ws');

// Phase B: Pure session lifecycle functions
const {
  SESSION_WATCHDOUT_MS,
  decideWatchdogAction,
  getTerminalFloatAction,
  isSessionTerminal,
} = require('./_session_lifecycle.js');

let mainWin = null, floatWin = null, resultCardWin = null, backendProcess = null;
let floatReady = false;
let resultCardReady = false;
let pendingResultCardPayload = null;  // {finalText, lastTranscription} — replayed on did-finish-load
let pendingResultText = '';           // main-process source-of-truth for clipboard write
let pendingSessionId = '';            // session id for the pending payload — must match activeSessionId to replay
let activeSessionId = '';             // current recording session — stale events are ignored
let autoCloseTimer = null;            // result-card auto-close timer handle
// Phase D: Session watchdog — prevents permanent "thinking" state
let sessionWatchdogTimer = null;

// ── Backend supervisor (Phase 6) ─────────────────
const BACKEND_SUPERVISOR = {
  // Did the user intentionally quit? Set in before-quit, prevents auto-restart.
  userInitiatedExit: false,
  // Has the auto-restart already been attempted? Only one restart per crash.
  restartAttempted: false,
  // The exit code from the last backend exit (null if still running).
  lastExitCode: null,
  // The signal that killed the backend, if any.
  lastExitSignal: null,
  // Monotonic timestamp of the last exit (for backoff calculation).
  lastExitTime: 0,
  // Minimum delay before restart (ms) — avoids crash-loop busy-spin.
  restartBackoffMs: 2000,
  // Maximum delay — caps the backoff.
  maxBackoffMs: 10000,
};

// ── Result card geometry constants (Phase 1) ─────────
const CARD_WIDTH = 360;
const CARD_MIN_HEIGHT = 150;
const CARD_MAX_HEIGHT = 260;
const CARD_GAP = 14;  // px between card bottom edge and float bar top edge
let ws = null;

// ── Single instance lock: prevent multiple Sayit windows ──
const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
  app.quit();
}

let mouseTracker = null;
let currentDisplay = null;
let mouseDetectorInterval = null;
let floatTopInterval = null;
let elementPositions = [];
let lastIsMouseInside = null;
let wsReconnectTimer = null;

const BASE = 'http://127.0.0.1:17890';
const FW = 500;
const FH = 500;

function getBackendLaunch() {
  if (app.isPackaged) {
    const packagedBackend = path.join(process.resourcesPath, 'backend', 'sayit-backend.exe');
    const packagerBackend = path.join(process.resourcesPath, 'sayit-backend', 'sayit-backend.exe');
    const backendPath = require('fs').existsSync(packagedBackend) ? packagedBackend : packagerBackend;
    return {
      command: backendPath,
      args: [],
      cwd: path.dirname(backendPath),
    };
  }
  // Resolve python.exe explicitly — Electron's PATH may differ from shell PATH
  const pythonCandidates = [
    'C:\\Users\\46136\\AppData\\Local\\Programs\\Python\\Python312\\python.exe',
    'C:\\Program Files\\Python312\\python.exe',
    'python',
  ];
  let pythonExe = 'python';
  for (const c of pythonCandidates) {
    if (fs.existsSync(c)) { pythonExe = c; break; }
  }
  return {
    command: pythonExe,
    args: [path.join(__dirname, '..', 'server.py')],
    cwd: path.join(__dirname, '..'),
  };
}

async function api(m,u,b){
  if (u !== '/api/version') await waitForServer(60);
  const o={method:m,headers:{'Content-Type':'application/json'}};
  if(b)o.body=JSON.stringify(b);
  let lastError = '';
  for (let i=0; i<5; i++) {
    try {
      const r = await fetch(BASE+u,o);
      if (r.ok) return await r.json();
      lastError = 'HTTP ' + r.status;
    } catch(e) {
      lastError = e.message;
    }
    await new Promise(r => setTimeout(r, 500));
  }
  return {error:lastError || 'backend not ready'};
}

function createMainWindow() {
  mainWin = new BrowserWindow({ width: 800, height: 600, frame: false, backgroundColor: '#f8f9fa',
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, nodeIntegration: false } });
  mainWin.loadFile(path.join(__dirname, 'ui', 'recorder.html'));
  mainWin.on('closed', () => { mainWin = null; destroyFloat(); if (backendProcess) backendProcess.kill(); app.quit(); });
}

function preCreateFloat() {
  if (isUsableWindow(floatWin)) return;
  const opts = getWindowOptions();
  floatWin = new BrowserWindow(Object.assign(opts, {
    show: false,
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, nodeIntegration: false }
  }));
  floatWin.loadFile(path.join(__dirname, 'ui', 'float.html'));
  floatWin.webContents.on('did-finish-load', () => { floatReady = true; });
  floatWin.on('closed', () => {
    floatWin = null;
    floatReady = false;
    elementPositions = [];
    stopMouseTracking();
    stopMouseDetection();
  });
  floatWin.setIgnoreMouseEvents(true, { forward: false });
  keepFloatOnTop();
  floatWin.setFullScreenable(false);
  setupMouseTracking();
  startMouseDetection();
  startFloatTopGuard();
}

function calculateWindowHeight() { return FH; }

function isUsableWindow(win) {
  return !!win && !win.isDestroyed();
}

function getWindowOptions() {
  const d = screen.getPrimaryDisplay();
  const { x, y } = d.workArea;
  return { x, y, type: 'panel', width: FW, height: FH,
    transparent: true, frame: false, hasShadow: false,
    maximizable: false, resizable: false, minimizable: false,
    focusable: false, fullscreen: false };
}

function moveWindowToDisplay(display) {
  if (!display) return;
  const { x, y, width, height } = display.workArea;
  const wh = calculateWindowHeight();
  const wx = Math.floor(x + (width - FW) / 2);
  const wy = Math.floor(y + height - wh);
  try {
    if (isUsableWindow(floatWin)) {
      floatWin.setBounds({ x: wx, y: wy, width: FW, height: wh });
      keepFloatOnTop();
    }
  } catch(e) {}
}

function keepFloatOnTop() {
  if (!isUsableWindow(floatWin)) return;
  try { floatWin.setAlwaysOnTop(true, 'screen-saver', 1); } catch(e) {}
  try { floatWin.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true, skipTransformProcessType: true }); } catch(e) {}
  try { floatWin.moveTop(); } catch(e) {}
}

function startFloatTopGuard() {
  if (floatTopInterval !== null) clearInterval(floatTopInterval);
  floatTopInterval = setInterval(() => {
    if (isUsableWindow(floatWin) && floatWin.isVisible()) keepFloatOnTop();
  }, 1000);
}

function stopFloatTopGuard() {
  if (floatTopInterval !== null) { clearInterval(floatTopInterval); floatTopInterval = null; }
}

function setupMouseTracking() {
  if (mouseTracker !== null) clearInterval(mouseTracker);
  const pt = screen.getCursorScreenPoint();
  const disp = screen.getDisplayNearestPoint(pt);
  currentDisplay = disp; moveWindowToDisplay(disp);
  mouseTracker = setInterval(() => {
    if (!isUsableWindow(floatWin)) return;
    const p = screen.getCursorScreenPoint();
    const nd = screen.getDisplayNearestPoint(p);
    if (!currentDisplay || currentDisplay.id !== nd.id) {
      currentDisplay = nd; moveWindowToDisplay(nd);
    }
  }, 100);
}

function startMouseDetection() {
  if (mouseDetectorInterval !== null) clearInterval(mouseDetectorInterval);
  mouseDetectorInterval = setInterval(() => {
    if (!isUsableWindow(floatWin)) return;
    if (elementPositions.length === 0) {
      floatWin.setIgnoreMouseEvents(true, { forward: false });
      return;
    }
    const pt = screen.getCursorScreenPoint();
    const bounds = floatWin.getBounds();
    // Typeless line 8528 stores elementPositions; Sayit renderer reports viewport rects.
    const inside = elementPositions.some(el =>
      pt.x >= bounds.x + el.left && pt.x <= bounds.x + el.right &&
      pt.y >= bounds.y + el.top && pt.y <= bounds.y + el.bottom);
    if (inside !== lastIsMouseInside) lastIsMouseInside = inside;
    floatWin.setIgnoreMouseEvents(!inside, { forward: false });
  }, 100);
}

function stopMouseTracking() {
  if (mouseTracker !== null) { clearInterval(mouseTracker); mouseTracker = null; }
  currentDisplay = null;
}

function stopMouseDetection() {
  if (mouseDetectorInterval !== null) { clearInterval(mouseDetectorInterval); mouseDetectorInterval = null; }
  lastIsMouseInside = null;
}

function destroyFloat() {
  stopMouseTracking();
  stopMouseDetection();
  stopFloatTopGuard();
  elementPositions = [];
  if (isUsableWindow(floatWin)) floatWin.destroy();
  floatWin = null;
  floatReady = false;
}

// ── Result card geometry helpers (Phase 1) ──────────

function calcResultCardPosition(cardHeight) {
  // Determine anchor: prefer elementPositions (reported by float renderer),
  // fall back to floatWin.getBounds().
  const display = currentDisplay || screen.getPrimaryDisplay();
  const wa = display.workArea;
  let anchorTop, anchorLeft, anchorWidth;

  if (Array.isArray(elementPositions) && elementPositions.length > 0) {
    // Use the first element position from float renderer (visible bubble area).
    // Float renderer reports getBoundingClientRect() — viewport-relative coords.
    // Convert to screen coordinates by adding the float window's screen origin.
    const fb = floatWin.getBounds();
    const ep = elementPositions[0];
    anchorTop = fb.y + ep.top;
    anchorLeft = fb.x + ep.left;
    anchorWidth = ep.right - ep.left;
  } else if (isUsableWindow(floatWin)) {
    // Fallback: estimate visible bar at bottom of float window
    // Float window is 500x500; visible bubble is ~86px wide, ~34px tall, bottom-center
    const fb = floatWin.getBounds();
    const barHeight = 34;
    const barWidth = 86;
    anchorTop = fb.y + fb.height - barHeight;
    anchorLeft = fb.x + Math.floor((fb.width - barWidth) / 2);
    anchorWidth = barWidth;
  } else {
    // Last resort: center on primary display bottom
    const ww = wa.width;
    return {
      x: Math.floor(wa.x + (ww - CARD_WIDTH) / 2),
      y: Math.floor(wa.y + wa.height - cardHeight - CARD_GAP - 34),
    };
  }

  // Horizontal center on anchor, then clamp to workArea
  let cardX = Math.floor(anchorLeft + (anchorWidth / 2) - (CARD_WIDTH / 2));
  cardX = Math.max(wa.x, Math.min(cardX, wa.x + wa.width - CARD_WIDTH));

  // Vertical: card bottom edge sits CARD_GAP above anchor top, then clamp
  let cardBottom = anchorTop - CARD_GAP;
  let cardY = cardBottom - cardHeight;
  cardY = Math.max(wa.y, Math.min(cardY, wa.y + wa.height - cardHeight));

  return { x: cardX, y: cardY };
}

// ── Result card window ──────────────────────────

function createResultCardWindow(estimatedHeight) {
  if (isUsableWindow(resultCardWin)) return;
  const h = Math.min(CARD_MAX_HEIGHT, Math.max(CARD_MIN_HEIGHT, estimatedHeight || 200));
  const pos = calcResultCardPosition(h);
  resultCardWin = new BrowserWindow({
    x: pos.x, y: pos.y, width: CARD_WIDTH, height: h,
    type: 'panel', transparent: true, frame: false, hasShadow: true,
    maximizable: false, resizable: false, minimizable: false,
    focusable: false, skipTaskbar: true,
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, nodeIntegration: false },
  });
  resultCardWin.loadFile(path.join(__dirname, 'ui', 'result-card.html'));
  resultCardWin.webContents.on('did-finish-load', () => {
    resultCardReady = true;
    // Replay the latest pending payload — covers the first-open race
    // where show was requested before the renderer was ready.
    flushPendingResultCardPayload();
  });
  resultCardWin.on('closed', () => {
    resultCardWin = null;
    resultCardReady = false;
    pendingResultCardPayload = null;
    pendingResultText = '';
    pendingSessionId = '';
  });
  resultCardWin.setAlwaysOnTop(true, 'screen-saver', 1);
  resultCardWin.setVisibleOnAllWorkspaces(true);
  resultCardWin.setIgnoreMouseEvents(false);
  if (typeof resultCardWin.showInactive === 'function') resultCardWin.showInactive();
  else resultCardWin.show();
}

function destroyResultCard() {
  if (autoCloseTimer !== null) { clearTimeout(autoCloseTimer); autoCloseTimer = null; }
  if (isUsableWindow(resultCardWin)) resultCardWin.destroy();
  resultCardWin = null;
  resultCardReady = false;
  pendingResultCardPayload = null;
  pendingResultText = '';
  pendingSessionId = '';
}

// ── Phase D: Session watchdog ───────────────────────
// SESSION_WATCHDOUT_MS imported from _session_lifecycle.js (Round 9.4: no duplicate)

function _applyWatchdogAction(eventType) {
  // Phase F: Single dispatch point via pure function from _session_lifecycle.js
  // This replaces manual stopSessionWatchdog/startSessionWatchdog at each case.
  const action = decideWatchdogAction(eventType);
  switch (action) {
    case 'reset':
      stopSessionWatchdog();
      break;
    case 'start':
      startSessionWatchdog(activeSessionId);
      break;
    case 'stop':
      stopSessionWatchdog();
      break;
    case 'ignore':
      break;
    default:
      break;
  }
}

function startSessionWatchdog(sessionId) {
  stopSessionWatchdog();
  if (!sessionId) return;
  sessionWatchdogTimer = setTimeout(() => {
    console.warn('[watchdog] Session ' + sessionId + ' timed out without terminal event — forcing exit from STOPPING');
    sessionWatchdogTimer = null;
    // Force the float to exit STOPPING state
    try {
      pushToFloat('if(window.sayitOnPipelineDone)sayitOnPipelineDone("")');
      pushToFloat('if(window.sayitOnError)sayitOnError("处理异常，请查看历史记录或日志")');
    } catch(e) {}
    // Clear pending payload since session ended abnormally
    pendingResultCardPayload = null;
    pendingResultText = '';
    pendingSessionId = '';
  }, SESSION_WATCHDOUT_MS);
}

function stopSessionWatchdog() {
  if (sessionWatchdogTimer !== null) {
    clearTimeout(sessionWatchdogTimer);
    sessionWatchdogTimer = null;
  }
}

function flushPendingResultCardPayload() {
  if (!isUsableWindow(resultCardWin) || !resultCardReady) return;
  if (!pendingResultCardPayload) return;
  // Only replay payload from the matching session — prevents cross-session pollution
  if (pendingSessionId && activeSessionId && pendingSessionId !== activeSessionId) return;
  try {
    resultCardWin.webContents.send('result-card:show', pendingResultCardPayload);
  } catch (e) { /* ignore */ }
}

function showResultCard(finalText, lastTranscription, state, message) {
  const payload = {
    finalText: String(finalText || ''),
    lastTranscription: String(lastTranscription || ''),
    state: String(state || ''),
    message: String(message || ''),
  };
  // Estimate card height based on text length
  const textLen = (payload.finalText.length + payload.lastTranscription.length);
  // Rough: ~10 chars per line at 14px font in 360px width, plus padding + header + actions
  const estimatedLines = Math.max(1, Math.ceil(textLen / 45));
  const estimatedHeight = Math.min(CARD_MAX_HEIGHT, Math.max(CARD_MIN_HEIGHT,
    60 + estimatedLines * 20  // base padding + line heights
  ));
  // Always capture as the source of truth — newer payloads win if multiple
  // results arrive while the renderer is still mounting.
  pendingResultCardPayload = payload;
  pendingResultText = payload.finalText;
  pendingSessionId = activeSessionId;  // tag with current session for replay guard
  if (!isUsableWindow(resultCardWin)) {
    createResultCardWindow(estimatedHeight);
  }
  if (resultCardReady && isUsableWindow(resultCardWin)) {
    try {
      resultCardWin.webContents.send('result-card:show', payload);
    } catch (e) { /* ignore */ }
  }
  // If not ready yet, did-finish-load will replay via flushPendingResultCardPayload.
}

function pushToResultCard(js) {
  // Legacy helper kept for any caller that still wants to executeJavaScript.
  if (!isUsableWindow(resultCardWin) || !resultCardReady) return;
  try { resultCardWin.webContents.executeJavaScript(js); } catch(e) {}
}

function sanitizeElementPositions(positions) {
  if (!Array.isArray(positions)) return [];
  return positions
    .map(el => ({
      left: Number(el.left),
      top: Number(el.top),
      right: Number(el.right),
      bottom: Number(el.bottom),
    }))
    .filter(el =>
      Number.isFinite(el.left) && Number.isFinite(el.top) &&
      Number.isFinite(el.right) && Number.isFinite(el.bottom) &&
      el.right >= el.left && el.bottom >= el.top);
}

function showFloat() {
  if (!isUsableWindow(floatWin)) preCreateFloat();
  try {
    moveWindowToDisplay(currentDisplay || screen.getPrimaryDisplay());
    keepFloatOnTop();
    if (typeof floatWin.showInactive === 'function') floatWin.showInactive();
    else floatWin.show();
    keepFloatOnTop();
  } catch(e) {}
}

function hideFloat() {
  try {
    if (isUsableWindow(floatWin)) {
      floatWin.setIgnoreMouseEvents(true, { forward: false });
      floatWin.hide();
    }
  } catch(e) {}
}

function pushToFloat(js) {
  if (!isUsableWindow(floatWin) || !floatReady) return;
  try { floatWin.webContents.executeJavaScript(js); } catch(e) {}
}

function pushToMain(channel, payload) {
  if (!isUsableWindow(mainWin)) return;
  try { mainWin.webContents.send(channel, payload || {}); } catch(e) {}
}

// ── WebSocket: bidirectional — backend events → float; RAlt toggle → backend commands ──
// Note: hotkey (RAlt) is installed by the Python backend via keyboard_helper DLL.
// The WS connection just relays events — no addon loading needed.

function connectWS() {
  if (ws) try { ws.removeAllListeners(); ws.close(); } catch(e) {}
  if (wsReconnectTimer !== null) { clearTimeout(wsReconnectTimer); wsReconnectTimer = null; }
  ws = new WebSocket('ws://127.0.0.1:17890/ws/events');
  ws.on('open', () => {
    console.log('[ws] connected');
    // Hotkey (RAlt) is installed by Python backend via keyboard_helper DLL — no addon needed
  });
  ws.on('message', (data) => {
    try {
      const evt = JSON.parse(data.toString());
      // Phase F: Log terminal events — uses isSessionTerminal pure function
      if (isSessionTerminal(evt.event) || evt.event === 'recording_stopping') {
        // no-op: these are the expected terminal/session boundary events
      }
      switch (evt.event) {
        case 'recording_started':
          // Clear old result card state from previous session
          if (autoCloseTimer !== null) { clearTimeout(autoCloseTimer); autoCloseTimer = null; }
          destroyResultCard();
          activeSessionId = evt.session_id || '';
          // Phase B+F: Single pure-function dispatch — decideWatchdogAction('recording_started')
          // returns 'reset' (clear stale state, DO NOT start timer — long recordings would false-positive)
          _applyWatchdogAction('recording_started');
          showFloat();
          keepFloatOnTop();
          pushToFloat('if(window.sayitOnRecordingStarted)sayitOnRecordingStarted()');
          break;
        case 'recording_stopping':
          // Phase B+F: decideWatchdogAction('recording_stopping') returns 'start'
          _applyWatchdogAction('recording_stopping');
          keepFloatOnTop();
          pushToFloat('if(window.sayitOnRecordingStopping)sayitOnRecordingStopping()');
          break;
        case 'recording_stopped':
          keepFloatOnTop();
          pushToFloat('if(window.sayitOnRecordingStopped)sayitOnRecordingStopped()');
          break;
        case 'pipeline_done':
          // Phase E: pipeline_done/terminal must NOT clear pending card payload.
          // The payload is cleared only by destroyResultCard (user close, new session).
          // This prevents the race: show → done → load producing an empty card.
          // Phase F: decideWatchdogAction('pipeline_done') returns 'stop'
          _applyWatchdogAction('pipeline_done');
          keepFloatOnTop();
          pushToFloat('if(window.sayitOnPipelineDone)sayitOnPipelineDone(' + JSON.stringify(evt.text) + ')');
          pushToMain('backend-event', evt);
          break;
        case 'pipeline_terminal':
          // Phase C+D: terminal event ends the session — stop watchdog, exit STOPPING
          // Phase F: decideWatchdogAction('pipeline_terminal') returns 'stop'
          _applyWatchdogAction('pipeline_terminal');
          keepFloatOnTop();
          // Phase B: use shared pure function to determine float action
          const terminalAction = getTerminalFloatAction(
            evt.outcome,
            !!evt.final_text_available
          );
          if (terminalAction.command === 'pipeline_done') {
            pushToFloat('if(window.sayitOnPipelineDone)sayitOnPipelineDone("")');
          } else {
            pushToFloat('if(window.sayitOnError)sayitOnError(' +
              JSON.stringify(terminalAction.args[0]) + ')');
          }
          pushToMain('backend-event', evt);
          break;
        case 'no_editable_target':
          // Result card will be shown via result_card_show event
          pushToMain('backend-event', evt);
          break;
        case 'result_card_show':
          // Ignore stale events from previous sessions
          if (evt.session_id && activeSessionId && evt.session_id !== activeSessionId) {
            break;
          }
          // Show/hide float as needed — this shouldn't show the small bubble
          // Keep float hidden; show result card instead
          hideFloat();
          showResultCard(evt.text, evt.last_transcription || '',
                         evt.state || '', evt.message || '');
          break;
        case 'result_card_close':
          if (evt.session_id && activeSessionId && evt.session_id !== activeSessionId) {
            break;
          }
          if (isUsableWindow(resultCardWin)) {
            try { resultCardWin.webContents.send('result-card:reset'); } catch(e) {}
          }
          destroyResultCard();
          break;
        case 'result_card_copy_done':
          if (evt.session_id && activeSessionId && evt.session_id !== activeSessionId) {
            break;
          }
          if (isUsableWindow(resultCardWin)) {
            try { resultCardWin.webContents.send('result-card:copy-done'); } catch(e) {}
          }
          // Auto-close shortly after — give renderer time to show ✓.
          if (autoCloseTimer !== null) { clearTimeout(autoCloseTimer); }
          autoCloseTimer = setTimeout(() => { destroyResultCard(); }, 700);
          break;
        case 'injection_done':
        case 'silent_learned':
          pushToMain('backend-event', evt);
          break;
        case 'error':
          // Phase E: error must NOT clear pending card payload (same race as pipeline_done).
          // Payload is only cleared by destroyResultCard or new session.
          // Phase F: decideWatchdogAction('error') returns 'stop'
          _applyWatchdogAction('error');
          keepFloatOnTop();
          pushToFloat('if(window.sayitOnError)sayitOnError(' + JSON.stringify(evt.message) + ')');
          break;
        case 'light_hint':
          // Lightweight hint — show on float bar, not large result card
          keepFloatOnTop();
          pushToFloat('if(window.sayitOnLightHint)sayitOnLightHint(' + JSON.stringify(evt.message || '') + ')');
          break;
        case 'tick':
          pushToFloat('if(window.sayitOnTick)sayitOnTick(' + evt.seconds + ')');
          break;
        case 'rms_level':
          pushToFloat('if(window.sayitOnRmsLevel)sayitOnRmsLevel(' + evt.level.toFixed(3) + ')');
          break;
        case 'asr_result':
          pushToFloat('if(window.sayitOnAsrResult)sayitOnAsrResult(' +
            JSON.stringify(evt.text) + ',' + JSON.stringify(evt.engine || '') + ')');
          break;
        case 'asr_partial':
          pushToFloat('if(window.sayitOnAsrPartial)sayitOnAsrPartial(' +
            JSON.stringify(evt.text) + ',' + JSON.stringify(evt.engine || '') + ')');
          break;
        case 'asr_progress':
          keepFloatOnTop();
          pushToFloat('if(window.sayitOnAsrProgress)sayitOnAsrProgress(' +
            JSON.stringify(evt.stage || '') + ',' + JSON.stringify(evt.message || '') + ',' +
            JSON.stringify(evt.engine || '') + ')');
          break;
        case 'asr_degraded':
          keepFloatOnTop();
          pushToFloat('if(window.sayitOnAsrDegraded)sayitOnAsrDegraded(' +
            JSON.stringify(evt.from || '') + ',' + JSON.stringify(evt.to || '') + ',' +
            JSON.stringify(evt.reason || '') + ')');
          break;
        case 'ai_result':
          pushToFloat('if(window.sayitOnAiResult)sayitOnAiResult(' +
            JSON.stringify(evt.text) + ',' + JSON.stringify(evt.provider || '') + ',' + JSON.stringify(evt.model || '') + ')');
          break;
        case 'ai_degraded':
          // AI deadline exceeded or AI failure — show hint on float bar
          keepFloatOnTop();
          pushToFloat('if(window.sayitOnAiDegraded)sayitOnAiDegraded(' + JSON.stringify(evt.message || '') + ')');
          break;
      }
    } catch(e) {}
  });
  ws.on('close', () => {
    console.log('[ws] closed');
    // Phase B+F: decideWatchdogAction('ws_close') returns 'stop'
    _applyWatchdogAction('ws_close');
    try {
      pushToFloat('if(window.sayitOnError)sayitOnError("连接已断开，请检查后端服务")');
    } catch(e) {}
    scheduleWSReconnect();
  });
  ws.on('error', () => {
    console.warn('[ws] error');
    // Phase B+F: decideWatchdogAction('ws_error') returns 'stop'
    _applyWatchdogAction('ws_error');
    scheduleWSReconnect();
  });
}

function scheduleWSReconnect() {
  if (wsReconnectTimer !== null) return;
  wsReconnectTimer = setTimeout(() => {
    wsReconnectTimer = null;
    connectWS();
  }, 2000);
}

// ── Fallback poll: 500ms backup for WebSocket gaps ──
let wasRecording = false;
async function poll() {
  try {
    const r = await (await fetch(BASE + '/api/is-recording')).json();
    if (r.recording && !wasRecording) { showFloat(); keepFloatOnTop(); pushToFloat('if(window.sayitOnRecordingStarted)sayitOnRecordingStarted()'); }
    if (!r.recording && wasRecording) { keepFloatOnTop(); pushToFloat('if(window.sayitOnRecordingStopped)sayitOnRecordingStopped()'); }
    wasRecording = r.recording;
  } catch(e) {}
  setTimeout(poll, 500);
}

ipcMain.handle('api', async (_e, m, u, b) => api(m, u, b));
ipcMain.handle('show-float', () => showFloat());
ipcMain.handle('hide-float', () => hideFloat());
ipcMain.handle('minimize-main', () => { if (mainWin) mainWin.minimize(); });
ipcMain.handle('close-main', () => { if (mainWin) mainWin.close(); });
ipcMain.on('float-element-positions', (_e, positions) => { elementPositions = sanitizeElementPositions(positions); });
ipcMain.on('float-element-positions-clear', () => { elementPositions = []; });

// Result-card trusted IPC — renderer never supplies arbitrary text. The
// only writable channel is the user clicking "copy" on the card currently
// shown, and main writes `pendingResultText` (which only this process set).
// Phase 8: validate sender — only the resultCardWin renderer may invoke
// these handlers. Other renderers (float.html, devtools) get unauthorized.
ipcMain.handle('result-card:copy-pending', async (event) => {
  if (!isUsableWindow(resultCardWin) ||
      event.sender.id !== resultCardWin.webContents.id) {
    return { ok: false, error: 'unauthorized' };
  }
  const text = pendingResultText || '';
  if (!text) return { ok: false, error: 'no_pending_text' };
  try {
    clipboard.writeText(text);
  } catch (e) {
    return { ok: false, error: String(e && e.message || e) };
  }
  // Tell backend so it can fire RESULT_CARD_COPY for history/observability.
  try { await api('POST', '/api/result-card/copy-confirmed', {}); } catch(e) {}
  // Notify renderer to show the green check.
  if (isUsableWindow(resultCardWin)) {
    try { resultCardWin.webContents.send('result-card:copy-done'); } catch(e) {}
  }
  // Auto-close after a short feedback delay.
  setTimeout(() => { destroyResultCard(); }, 700);
  return { ok: true };
});

ipcMain.handle('result-card:close', (event) => {
  // User cancelled — DO NOT touch clipboard.
  // Phase 8: validate sender — only the resultCardWin renderer.
  if (!isUsableWindow(resultCardWin) ||
      event.sender.id !== resultCardWin.webContents.id) {
    return { ok: false, error: 'unauthorized' };
  }
  try { if (isUsableWindow(resultCardWin)) resultCardWin.webContents.send('result-card:reset'); } catch(e) {}
  // Tell backend to emit RESULT_CARD_CLOSE event for history.
  try { api('POST', '/api/result-card/close', {}); } catch(e) {}
  destroyResultCard();
  return { ok: true };
});

async function waitForServer(retries=20) {
  for (let i=0; i<retries; i++) {
    try { const r = await fetch(BASE+'/api/version'); if (r.ok) return true; } catch(e) {}
    await new Promise(r => setTimeout(r, 1000));
  }
  return false;
}

app.whenReady().then(async () => {
  if (process.env.SAYIT_SKIP_BACKEND !== '1') {
    spawnBackend();
  }
  createMainWindow();
  preCreateFloat();
  await waitForServer();
  connectWS(); poll();
});

function spawnBackend() {
  const backend = getBackendLaunch();
  console.log('[main] spawning backend:', backend.command, backend.args.join(' '));
  backendProcess = spawn(backend.command, backend.args, {
    cwd: backend.cwd,
    stdio: 'pipe',
    windowsHide: app.isPackaged,
  });
  backendProcess.stdout.on('data', d => process.stdout.write('[backend] ' + d.toString()));
  backendProcess.stderr.on('data', d => process.stderr.write('[backend-err] ' + d.toString()));
  backendProcess.on('exit', (code, signal) => {
    const now = Date.now();
    console.warn('[main] backend exited with code', code, 'signal', signal);
    BACKEND_SUPERVISOR.lastExitCode = code;
    BACKEND_SUPERVISOR.lastExitSignal = signal;
    BACKEND_SUPERVISOR.lastExitTime = now;
    backendProcess = null;

    // Distinguish: user-initiated vs abnormal
    if (BACKEND_SUPERVISOR.userInitiatedExit) {
      console.log('[main] backend exit was user-initiated — no restart');
      return;
    }

    // code === 0 and no signal → normal (graceful) shutdown — no restart
    if (code === 0 && signal === null) {
      console.log('[main] backend exited normally — no restart');
      return;
    }

    // Abnormal exit — restart once
    if (BACKEND_SUPERVISOR.restartAttempted) {
      console.error('[main] backend crashed again after restart — giving up');
      pushToFloat('if(window.sayitOnBackendError)sayitOnBackendError("后台恢复失败，请手动重启 SayIt")');
      return;
    }

    BACKEND_SUPERVISOR.restartAttempted = true;
    console.log('[main] backend exited abnormally — scheduling restart with backoff');

    // Backoff: start at 2s, scale by time-since-last (simple linear: min 2s, max 10s)
    const elapsedSinceLastExit = now - BACKEND_SUPERVISOR.lastExitTime;
    const backoff = Math.min(
      BACKEND_SUPERVISOR.maxBackoffMs,
      Math.max(BACKEND_SUPERVISOR.restartBackoffMs, elapsedSinceLastExit * 0.5)
    );
    console.log('[main] restart backoff', backoff, 'ms');

    pushToFloat('if(window.sayitOnBackendError)sayitOnBackendError("后台异常，SayIt 正在恢复")');

    setTimeout(() => {
      console.log('[main] restarting backend');
      spawnBackend();
      waitForServer(60).then(ok => {
        if (ok) {
          console.log('[main] backend restarted successfully');
          // Reset crash episode budget — backend is healthy again
          BACKEND_SUPERVISOR.restartAttempted = false;
          pushToFloat('if(window.sayitOnBackendRestored)sayitOnBackendRestored()');
          destroyResultCard();
          connectWS();
        } else {
          console.error('[main] backend restart failed — server not reachable');
          pushToFloat('if(window.sayitOnBackendError)sayitOnBackendError("后台恢复失败，请手动重启 SayIt")');
        }
      });
    }, backoff);
  });
  backendProcess.on('error', (err) => {
    console.error('[main] backend spawn error:', err.message);
    const now = Date.now();
    BACKEND_SUPERVISOR.lastExitTime = now;

    // Treat spawn error like an abnormal exit (same restart logic)
    if (BACKEND_SUPERVISOR.userInitiatedExit) return;
    if (BACKEND_SUPERVISOR.restartAttempted) {
      pushToFloat('if(window.sayitOnBackendError)sayitOnBackendError("后台恢复失败，请手动重启 SayIt")');
      return;
    }
    BACKEND_SUPERVISOR.restartAttempted = true;
    pushToFloat('if(window.sayitOnBackendError)sayitOnBackendError("后台异常，SayIt 正在恢复")');
    setTimeout(() => {
      spawnBackend();
      waitForServer(60).then(ok => {
        if (ok) {
          BACKEND_SUPERVISOR.restartAttempted = false;
          pushToFloat('if(window.sayitOnBackendRestored)sayitOnBackendRestored()');
          destroyResultCard();
          connectWS();
        }
      });
    }, 3000);  // spawn error gets 3s fixed backoff
  });
}
app.on('second-instance', (_event, _commandLine, _workingDirectory) => {
  // User clicked shortcut again — focus existing window
  if (mainWin) {
    if (mainWin.isMinimized()) mainWin.restore();
    mainWin.focus();
  }
});
app.on('window-all-closed', () => {
  BACKEND_SUPERVISOR.userInitiatedExit = true;
  if (backendProcess) backendProcess.kill();
  app.quit();
});
app.on('before-quit', () => {
  BACKEND_SUPERVISOR.userInitiatedExit = true;
  if (backendProcess) backendProcess.kill();
  // Hotkey uninstall is handled by Python backend orchestrator.stop()
});
