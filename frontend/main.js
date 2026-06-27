// Typeless ref: Ch_class.js lines 8409-8558
// Architecture: events drive everything — no polling (like Typeless IPC)
// Backend events via WebSocket → main.js forwards to float.html
// Hotkey: WH_KEYBOARD_LL hook lives in Python backend via keyboard_helper DLL
const { app, BrowserWindow, screen, ipcMain } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const WebSocket = require('ws');

let mainWin = null, floatWin = null, resultCardWin = null, backendProcess = null;
let floatReady = false;
let resultCardReady = false;
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

// ── Result card window ──────────────────────────

function createResultCardWindow() {
  if (isUsableWindow(resultCardWin)) return;
  const d = screen.getPrimaryDisplay();
  const { x, y, width, height } = d.workArea;
  const cw = 420, ch = 320;
  const cx = Math.floor(x + (width - cw) / 2);
  const cy = Math.floor(y + (height - ch) / 2);
  resultCardWin = new BrowserWindow({
    x: cx, y: cy, width: cw, height: ch,
    type: 'panel', transparent: true, frame: false, hasShadow: true,
    maximizable: false, resizable: false, minimizable: false,
    focusable: false, skipTaskbar: true,
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, nodeIntegration: false },
  });
  resultCardWin.loadFile(path.join(__dirname, 'ui', 'result-card.html'));
  resultCardWin.webContents.on('did-finish-load', () => { resultCardReady = true; });
  resultCardWin.on('closed', () => {
    resultCardWin = null;
    resultCardReady = false;
  });
  resultCardWin.setAlwaysOnTop(true, 'screen-saver', 1);
  resultCardWin.setVisibleOnAllWorkspaces(true);
  resultCardWin.setIgnoreMouseEvents(false);
  if (typeof resultCardWin.showInactive === 'function') resultCardWin.showInactive();
  else resultCardWin.show();
}

function destroyResultCard() {
  if (isUsableWindow(resultCardWin)) resultCardWin.destroy();
  resultCardWin = null;
  resultCardReady = false;
}

function pushToResultCard(js) {
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
      switch (evt.event) {
        case 'recording_started':
          showFloat();
          keepFloatOnTop();
          pushToFloat('if(window.sayitOnRecordingStarted)sayitOnRecordingStarted()');
          break;
        case 'recording_stopping':
          keepFloatOnTop();
          pushToFloat('if(window.sayitOnRecordingStopping)sayitOnRecordingStopping()');
          break;
        case 'recording_stopped':
          keepFloatOnTop();
          pushToFloat('if(window.sayitOnRecordingStopped)sayitOnRecordingStopped()');
          break;
        case 'pipeline_done':
          keepFloatOnTop();
          pushToFloat('if(window.sayitOnPipelineDone)sayitOnPipelineDone(' + JSON.stringify(evt.text) + ')');
          pushToMain('backend-event', evt);
          break;
        case 'no_editable_target':
          // Result card will be shown via result_card_show event
          pushToMain('backend-event', evt);
          break;
        case 'result_card_show':
          // Show/hide float as needed — this shouldn't show the small bubble
          // Keep float hidden; show result card instead
          hideFloat();
          createResultCardWindow();
          pushToResultCard('if(window.__resultCardShow)__resultCardShow(' +
            JSON.stringify(evt.text) + ',' + JSON.stringify(evt.last_transcription || '') + ')');
          break;
        case 'result_card_close':
          pushToResultCard('if(window.__resultCardClose)__resultCardClose()');
          destroyResultCard();
          break;
        case 'result_card_copy_done':
          pushToResultCard('if(window.__resultCardCopyDone)__resultCardCopyDone()');
          break;
        case 'injection_done':
        case 'silent_learned':
          pushToMain('backend-event', evt);
          break;
        case 'error':
          keepFloatOnTop();
          pushToFloat('if(window.sayitOnError)sayitOnError(' + JSON.stringify(evt.message) + ')');
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
      }
    } catch(e) {}
  });
  ws.on('close', () => {
    console.log('[ws] closed');
    scheduleWSReconnect();
  });
  ws.on('error', () => {
    console.warn('[ws] error');
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

async function waitForServer(retries=20) {
  for (let i=0; i<retries; i++) {
    try { const r = await fetch(BASE+'/api/version'); if (r.ok) return true; } catch(e) {}
    await new Promise(r => setTimeout(r, 1000));
  }
  return false;
}

app.whenReady().then(async () => {
  if (process.env.SAYIT_SKIP_BACKEND !== '1') {
    const backend = getBackendLaunch();
    console.log('[main] spawning backend:', backend.command, backend.args.join(' '));
    backendProcess = spawn(backend.command, backend.args, {
      cwd: backend.cwd,
      stdio: 'pipe',
      windowsHide: app.isPackaged,
    });
    backendProcess.stdout.on('data', d => process.stdout.write('[backend] ' + d.toString()));
    backendProcess.stderr.on('data', d => process.stderr.write('[backend-err] ' + d.toString()));
    backendProcess.on('exit', (code) => {
      console.warn('[main] backend exited with code', code);
      backendProcess = null;
    });
    backendProcess.on('error', (err) => {
      console.error('[main] backend spawn error:', err.message);
      backendProcess = null;
    });
  }
  createMainWindow();
  preCreateFloat();
  await waitForServer();
  connectWS(); poll();
});
app.on('second-instance', (_event, _commandLine, _workingDirectory) => {
  // User clicked shortcut again — focus existing window
  if (mainWin) {
    if (mainWin.isMinimized()) mainWin.restore();
    mainWin.focus();
  }
});
app.on('window-all-closed', () => { if (backendProcess) backendProcess.kill(); app.quit(); });
app.on('before-quit', () => {
  if (backendProcess) backendProcess.kill();
  // Hotkey uninstall is handled by Python backend orchestrator.stop()
});
