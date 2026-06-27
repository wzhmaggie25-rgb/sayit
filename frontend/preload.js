const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('sayit', {
  api: (m, u, b) => ipcRenderer.invoke('api', m, u, b),
  getConfig: () => ipcRenderer.invoke('api', 'GET', '/api/config'),
  setConfig: (d) => ipcRenderer.invoke('api', 'POST', '/api/config', d),
  getHistory: (s,l,o) => ipcRenderer.invoke('api', 'GET', '/api/history?search='+(s||'')+'&limit='+(l||100)+'&offset='+(o||0)),
  getDictionary: () => ipcRenderer.invoke('api', 'GET', '/api/dictionary'),
  getRules: (ao) => ipcRenderer.invoke('api', 'GET', '/api/rules?active_only='+(ao||false)),
  detectMics: () => ipcRenderer.invoke('api', 'GET', '/api/microphones'),
  engineStatus: () => ipcRenderer.invoke('api', 'GET', '/api/engine-status'),
  testProvider: (id) => ipcRenderer.invoke('api', 'POST', '/api/test-provider/'+id),
  startRecording: () => ipcRenderer.invoke('api', 'POST', '/api/start-recording'),
  stopRecording: () => ipcRenderer.invoke('api', 'POST', '/api/stop-recording'),
  getConfigValue: (key) => ipcRenderer.invoke('api', 'GET', '/api/config-value?key='+(key||'')),
  setHotkey: (hk) => ipcRenderer.invoke('api', 'POST', '/api/hotkey/set', {hotkey:hk}),
  pauseHotkey: () => ipcRenderer.invoke('api', 'POST', '/api/hotkey/pause'),
  resumeHotkey: () => ipcRenderer.invoke('api', 'POST', '/api/hotkey/resume'),
  showFloat: () => ipcRenderer.invoke('show-float'),
  hideFloat: () => ipcRenderer.invoke('hide-float'),
  minimize: () => ipcRenderer.invoke('minimize-main'),
  close: () => ipcRenderer.invoke('close-main'),
  sendElementPositions: (positions) => ipcRenderer.send('float-element-positions', positions),
  clearElementPositions: () => ipcRenderer.send('float-element-positions-clear'),
  onBackendEvent: (handler) => {
    if (typeof handler !== 'function') return () => {};
    const listener = (_event, payload) => handler(payload || {});
    ipcRenderer.on('backend-event', listener);
    return () => ipcRenderer.removeListener('backend-event', listener);
  },
});

// ── Result-card trusted IPC ────────────────────────────────────
// The renderer never holds the final text on its own — main process
// keeps `pendingResultText` and writes it via Electron's clipboard
// module when the user clicks copy. This prevents any local-origin
// page (or stray fetch) from overwriting the user's clipboard via
// an open REST endpoint.
contextBridge.exposeInMainWorld('sayitResultCard', {
  // Renderer subscribes to "show" pushes — payload {finalText, lastTranscription}
  onShow: (handler) => {
    if (typeof handler !== 'function') return () => {};
    const listener = (_e, payload) => handler(payload || {});
    ipcRenderer.on('result-card:show', listener);
    return () => ipcRenderer.removeListener('result-card:show', listener);
  },
  // Renderer subscribes to "copy done" — main confirms write succeeded
  onCopyDone: (handler) => {
    if (typeof handler !== 'function') return () => {};
    const listener = () => handler();
    ipcRenderer.on('result-card:copy-done', listener);
    return () => ipcRenderer.removeListener('result-card:copy-done', listener);
  },
  // Renderer subscribes to "reset" — clears local state on close
  onReset: (handler) => {
    if (typeof handler !== 'function') return () => {};
    const listener = () => handler();
    ipcRenderer.on('result-card:reset', listener);
    return () => ipcRenderer.removeListener('result-card:reset', listener);
  },
  // Trusted user-action signals — renderer cannot supply arbitrary text.
  copyPending: () => ipcRenderer.invoke('result-card:copy-pending'),
  close: () => ipcRenderer.invoke('result-card:close'),
});
