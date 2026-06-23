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
