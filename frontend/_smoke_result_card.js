// Offline smoke test for frontend/ui/result-card.html
// Runs as a plain Node script (no jsdom, no Electron) and verifies the
// page is self-contained and structurally correct.
//
// Run: node frontend/_smoke_result_card.js
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const HTML_PATH = path.join(__dirname, 'ui', 'result-card.html');
const html = fs.readFileSync(HTML_PATH, 'utf8');

const failures = [];
function check(label, cond, detail) {
  if (!cond) failures.push(`FAIL: ${label}` + (detail ? ` — ${detail}` : ''));
  else console.log(`PASS: ${label}`);
}

// 1. No remote/CDN <script> tags — page must be 100% offline.
const externalScript = /<script[^>]+src\s*=\s*['"][^'"]+['"][^>]*>/i.test(html);
check('no external <script src> tags', !externalScript);

// 2. No `<link rel="stylesheet" href="http...">` to remote stylesheets.
const externalCss = /<link[^>]+rel\s*=\s*['"]stylesheet['"][^>]+href\s*=\s*['"]https?:[^'"]+['"]/i.test(html);
check('no remote <link> stylesheets', !externalCss);

// 3. No React / ReactDOM references at all.
check('no React global reference', !/\bReact\b/.test(html));
check('no ReactDOM global reference', !/\bReactDOM\b/.test(html));

// 4. Required DOM IDs/buttons.
check('copy button id present', /id\s*=\s*['"]copy-btn['"]/.test(html));
check('close button id present', /id\s*=\s*['"]close-btn['"]/.test(html));
check('final text container present', /id\s*=\s*['"]final-text['"]/.test(html));
check('last transcription container present', /id\s*=\s*['"]last-tx['"]/.test(html));
check('check (green) element present', /id\s*=\s*['"]check['"]/.test(html));

// 5. JS contains the handlers and global show/close/copyDone bindings.
check('has onCopyClick handler', /onCopyClick/.test(html));
check('has onCloseClick handler', /onCloseClick/.test(html));
check('binds copyBtn click', /copyBtn\.addEventListener\(['"]click['"]/.test(html));
check('binds closeBtn click', /closeBtn\.addEventListener\(['"]click['"]/.test(html));
check('legacy window.__resultCardShow', /window\.__resultCardShow\s*=/.test(html));
check('legacy window.__resultCardClose', /window\.__resultCardClose\s*=/.test(html));
check('legacy window.__resultCardCopyDone', /window\.__resultCardCopyDone\s*=/.test(html));

// 6. Subscribes to trusted IPC channels (preload-exposed sayitResultCard).
check('uses sayitResultCard.copyPending', /sayitResultCard\.copyPending/.test(html));
check('uses sayitResultCard.close', /sayitResultCard\.close/.test(html));
check('uses sayitResultCard.onShow', /sayitResultCard\.onShow/.test(html));

// 7. Does NOT call fetch() for clipboard — the renderer must never round-trip
// text through an open REST endpoint.
check('no fetch() to /api/result-card/copy', !/fetch\([^)]*\/api\/result-card\/copy/.test(html));
check('no fetch() to /api/result-card/close', !/fetch\([^)]*\/api\/result-card\/close/.test(html));

// 8. Execute the inline script in a sandbox to confirm no undefined globals
// and that calling the legacy show/copyDone/close globals does not throw.
const scriptMatches = [...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/gi)]
  .filter(m => !/src\s*=/i.test(m[0]));
check('exactly one inline <script> block', scriptMatches.length === 1,
  `found ${scriptMatches.length}`);

if (scriptMatches.length === 1) {
  // Build a minimal DOM stub so the IIFE can attach event listeners.
  const elements = {};
  function makeEl(id) {
    if (elements[id]) return elements[id];
    const el = {
      id,
      textContent: '',
      style: {},
      disabled: false,
      classList: {
        _set: new Set(),
        add(c) { this._set.add(c); },
        remove(c) { this._set.delete(c); },
        contains(c) { return this._set.has(c); },
        toggle(c) { if (this._set.has(c)) this._set.delete(c); else this._set.add(c); },
      },
      _listeners: {},
      addEventListener(type, handler) {
        (this._listeners[type] = this._listeners[type] || []).push(handler);
      },
      removeEventListener() {},
    };
    elements[id] = el;
    return el;
  }
  const sandbox = {
    document: {
      getElementById: (id) => makeEl(id),
      addEventListener: () => {},
    },
    window: {},
    console,
  };
  sandbox.window.sayitResultCard = undefined;  // simulate no preload (smoke only)
  sandbox.globalThis = sandbox;
  try {
    vm.runInNewContext(scriptMatches[0][1], sandbox, { timeout: 1000 });
    check('inline script executes without ReferenceError', true);
  } catch (e) {
    check('inline script executes without ReferenceError', false, e.message);
  }

  // 9. Verify legacy globals are wired (the IIFE assigns them onto window).
  check('window.__resultCardShow assigned', typeof sandbox.window.__resultCardShow === 'function');
  check('window.__resultCardCopyDone assigned', typeof sandbox.window.__resultCardCopyDone === 'function');
  check('window.__resultCardClose assigned', typeof sandbox.window.__resultCardClose === 'function');

  // 10. Drive the renderer through a complete show → copyDone → close cycle
  // and assert state transitions appear in the DOM stubs.
  if (typeof sandbox.window.__resultCardShow === 'function') {
    try {
      sandbox.window.__resultCardShow('hello world', '前一句转录');
      const finalEl = elements['final-text'];
      const lastEl = elements['last-tx'];
      const checkEl = elements['check'];
      const copyEl = elements['copy-btn'];
      check('final text rendered after show', finalEl && finalEl.textContent === 'hello world',
        `got ${finalEl && finalEl.textContent}`);
      check('last transcription rendered', lastEl && lastEl.textContent === '前一句转录',
        `got ${lastEl && lastEl.textContent}`);
      check('check element starts hidden', checkEl && !checkEl.classList.contains('visible'));
      check('copy button enabled when text present', copyEl && copyEl.disabled === false);

      sandbox.window.__resultCardCopyDone();
      check('check element shows after copyDone', checkEl && checkEl.classList.contains('visible'));

      sandbox.window.__resultCardClose();
      check('final text cleared after close', finalEl && finalEl.textContent === '');
      check('check element hidden after close', checkEl && !checkEl.classList.contains('visible'));
    } catch (e) {
      check('render lifecycle did not throw', false, e.message);
    }
  }

  // 11. First-payload-while-not-ready scenario: the renderer must accept a
  // payload pushed BEFORE any subscription was made (main resends on
  // did-finish-load, but the script itself must not crash on legacy globals).
  if (typeof sandbox.window.__resultCardShow === 'function') {
    try {
      // Simulate a sequence of two shows landing back-to-back before any
      // copy/close — the second must win.
      sandbox.window.__resultCardShow('first', '');
      sandbox.window.__resultCardShow('second wins', '');
      const finalEl = elements['final-text'];
      check('latest payload wins on rapid double show', finalEl.textContent === 'second wins',
        `got ${finalEl.textContent}`);
    } catch (e) {
      check('rapid double show did not throw', false, e.message);
    }
  }
}

if (failures.length) {
  console.error('\n--- SMOKE TEST FAILED ---');
  for (const f of failures) console.error(f);
  process.exit(1);
}
console.log('\n--- SMOKE TEST PASSED ---');
process.exit(0);
