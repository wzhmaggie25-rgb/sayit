/* ═══════════════════════════════════════════════════════════════
   Sayit Bridge — JS ↔ Python communication layer

   pywebview exposes window.pywebview.api with all methods
   registered from the Python backend. This module provides
   a typed wrapper around those calls with fallback for
   development outside pywebview (HTML prototype testing).

   Development mode: open HTML files directly in browser,
   localStorage-based mock backend is used.
   Production mode: run via pywebview, Python backend is live.
   ═══════════════════════════════════════════════════════════════ */

const Sayit = (() => {
  'use strict';

  const isPyWebView = !!(window.pywebview && window.pywebview.api);
  const dev = !isPyWebView;

  // ── Development fallback ─────────────────────────────────
  function devGet(key, def) {
    try { const v = localStorage.getItem('sayit-' + key); return v !== null ? JSON.parse(v) : def; }
    catch(e) { return def; }
  }
  function devSet(key, val) {
    localStorage.setItem('sayit-' + key, JSON.stringify(val));
  }

  // ── Public API ────────────────────────────────────────────

  /** Get JSON-serializable data from Python backend. Fallback to localStorage. */
  async function get(key, defaultVal) {
    if (isPyWebView) {
      try { return await window.pywebview.api.get(key); }
      catch(e) { console.warn('[Bridge] get failed:', key, e); return defaultVal; }
    }
    return devGet(key, defaultVal);
  }

  /** Set a value in the Python backend. */
  async function set(key, value) {
    if (isPyWebView) {
      try { await window.pywebview.api.set(key, value); }
      catch(e) { console.warn('[Bridge] set failed:', key, e); }
    }
    devSet(key, value);
  }

  /** Call a remote Python function by name. Returns the result. */
  async function call(method, ...args) {
    if (isPyWebView) {
      try { return await window.pywebview.api[method](...args); }
      catch(e) { console.warn('[Bridge] call failed:', method, e); return null; }
    }
    // Dev fallback: simulate some calls
    return _devCall(method, ...args);
  }

  // ── Typed API wrappers ────────────────────────────────────

  const api = {
    // Config
    getConfig: (key, def) => call('get_config_value', key, def),
    setConfig: (key, value) => call('set_config_value', key, value),
    getAllConfig: () => call('get_all_config'),

    // History
    getHistory: (search, limit, offset) => call('get_history', search, limit || 100, offset || 0),
    getHistoryCount: (search) => call('get_history_count', search || ''),
    updateHistoryText: (id, text) => call('update_history_text', id, text),
    deleteHistory: (id) => call('delete_history', id),

    // Dictionary
    getDictionary: () => call('get_dictionary'),
    addWord: (word, pinyin) => call('add_dictionary_word', word, pinyin || ''),
    removeWord: (word) => call('remove_dictionary_word', word),
    clearDictionary: () => call('clear_dictionary'),

    // Correction Rules
    getRules: (activeOnly) => call('get_rules', activeOnly || false),

    // Audio
    detectMics: () => call('detect_microphones'),

    // AI Provider Testing
    testProvider: (providerId) => call('test_ai_provider', providerId),

    // Version & Update
    getVersion: () => call('get_version'),
    checkUpdate: () => call('check_update'),

    // Theme
    getTheme: () => call('get_config_value', 'theme', 'light'),
    setTheme: (theme) => call('set_config_value', 'theme', theme),

    // Recording
    startRecording: () => call('start_recording'),
    stopRecording: () => call('stop_recording'),
    isRecording: () => call('is_recording'),

    // Hotkey
    getHotkey: () => call('get_config_value', 'hotkey', 'RAlt'),
    setHotkey: (hotkey) => call('set_hotkey', hotkey),

    // Onboarding
    isOnboardingDone: () => call('get_config_value', 'onboarding_completed', false),
    finishOnboarding: () => call('set_config_value', 'onboarding_completed', true),
  };

  // ── Dev mock ──────────────────────────────────────────────
  function _devCall(method, ...args) {
    // Simple mock implementations for development testing
    switch(method) {
      case 'get_config_value':
        return devGet('cfg-'+args[0], args[1]);
      case 'set_config_value':
        devSet('cfg-'+args[0], args[1]); return null;
      case 'get_history': {
        const raw = localStorage.getItem('sayit-history-entries');
        let entries = raw ? JSON.parse(raw) : [];
        const kw = (args[0] || '').toLowerCase().trim();
        if (kw) entries = entries.filter(e => e.text.toLowerCase().includes(kw) || e.date.includes(kw));
        return entries.slice(args[2] || 0, (args[2] || 0) + (args[1] || 100));
      }
      case 'get_dictionary': {
        try { return JSON.parse(localStorage.getItem('sayit-dict') || '[]'); } catch(e) { return []; }
      }
      case 'add_dictionary_word': {
        const dict = JSON.parse(localStorage.getItem('sayit-dict') || '[]');
        if (!dict.includes(args[0])) { dict.push(args[0]); localStorage.setItem('sayit-dict', JSON.stringify(dict)); }
        return true;
      }
      case 'remove_dictionary_word': {
        const dict = JSON.parse(localStorage.getItem('sayit-dict') || '[]');
        const idx = dict.indexOf(args[0]); if (idx >= 0) dict.splice(idx, 1);
        localStorage.setItem('sayit-dict', JSON.stringify(dict)); return null;
      }
      case 'get_version': return '1.10.0';
      default: return null;
    }
  }

  return { get, set, call, api };
})();

// ── Theme ───────────────────────────────────────────────────
(function() {
  const html = document.documentElement;
  async function get() {
    try { return await Sayit.api.getTheme(); } catch(e) { return localStorage.getItem('sayit-theme') || 'light'; }
  }
  function apply(mode) {
    if (mode === 'system') html.setAttribute('data-theme', window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    else html.setAttribute('data-theme', mode);
  }
  get().then(apply);
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
    get().then(mode => { if (mode === 'system') apply('system'); });
  });
  window.sayitSetTheme = async function(mode) {
    await Sayit.api.setTheme(mode);
    apply(mode);
  };
  window.sayitGetTheme = get;
  window.sayitApplyTheme = apply;
})();
