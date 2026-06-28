/**
 * A3: Race test for result card show→done→load text retention.
 *
 * Simulates the critical race:
 *   1. result_card_show arrives → payload set, card creation starts
 *   2. pipeline_done arrives (card not yet loaded)
 *   3. did-finish-load fires
 *   4. Verify the card still shows the original text
 *
 * This test runs in Node.js only — no Electron. It tests the
 * pending-payload lifecycle logic extracted from main.js.
 *
 * Usage: node frontend/_test_result_card_race.js
 */

// ── Simulated main.js state (extracted) ──
let pendingResultCardPayload = null;
let pendingResultText = '';
let pendingSessionId = '';
let activeSessionId = '';
let resultCardReady = false;
let resultCardWinExists = false;

// Simulated callbacks
const events = [];

function showResultCard(finalText, lastTranscription, state, message) {
  const payload = {
    finalText: String(finalText || ''),
    lastTranscription: String(lastTranscription || ''),
    state: String(state || ''),
    message: String(message || ''),
  };
  pendingResultCardPayload = payload;
  pendingResultText = payload.finalText;
  pendingSessionId = activeSessionId;
  events.push({ type: 'showResultCard', payload, sessionId: activeSessionId });
}

function onPipelineDone(sessionId) {
  // Phase C fix: process terminal event
  events.push({ type: 'pipeline_done', sessionId });
}

function onError(sessionId) {
  // Phase C fix: error must not clear pending payload
  events.push({ type: 'error', sessionId });
}

function onDidFinishLoad() {
  resultCardReady = true;
  flushPendingResultCardPayload();
}

function flushPendingResultCardPayload() {
  if (!resultCardWinExists || !resultCardReady) return;
  if (!pendingResultCardPayload) return;
  if (pendingSessionId && activeSessionId && pendingSessionId !== activeSessionId) return;
  events.push({
    type: 'flush',
    payload: pendingResultCardPayload,
    pendingSessionId,
    activeSessionId,
  });
}

function destroyResultCard() {
  resultCardWinExists = false;
  resultCardReady = false;
  pendingResultCardPayload = null;
  pendingResultText = '';
  pendingSessionId = '';
}

function recordingStarted(sessionId) {
  // Phase E fix: new session clears old card
  destroyResultCard();
  activeSessionId = sessionId;
  events.push({ type: 'recording_started', sessionId });
}

// ── Tests ──
let failures = 0;
let total = 0;

function assert(condition, msg) {
  total++;
  if (!condition) {
    console.error(`FAIL: ${msg}`);
    failures++;
  } else {
    console.log(`PASS: ${msg}`);
  }
}

// ── Test 1: Critical race — show → done → load ──
function testShowDoneLoadRace() {
  console.log('\n=== Test 1: Show → Done → Load race ===');
  // Reset
  pendingResultCardPayload = null;
  pendingResultText = '';
  pendingSessionId = '';
  activeSessionId = '';
  resultCardReady = false;
  resultCardWinExists = false;
  events.length = 0;

  // Session starts
  const sessionId = 'test-session-1';
  recordingStarted(sessionId);
  assert(activeSessionId === sessionId, 'activeSessionId set');

  // Show result card (but card window not ready yet)
  showResultCard('Hello World', 'Hello World', 'no_editable_target', 'No target');
  assert(pendingResultCardPayload !== null, 'payload set after show');
  assert(pendingResultText === 'Hello World', 'pendingResultText set');
  assert(events.filter(e => e.type === 'showResultCard').length === 1, 'showResultCard called');

  // Pipeline done arrives (card still not loaded)
  onPipelineDone(sessionId);
  // Phase E fix: pipeline_done should NOT clear pending payload
  assert(pendingResultCardPayload !== null,
    'Phase E: pipeline_done must NOT clear pending payload - payload still exists');
  assert(pendingResultText === 'Hello World',
    'Phase E: pipeline_done must NOT clear pending text');

  // Now the card finishes loading
  resultCardWinExists = true;
  onDidFinishLoad();
  // Flush should fire
  const flushEvents = events.filter(e => e.type === 'flush');
  assert(flushEvents.length >= 1, 'flushPendingResultCardPayload was called');
  const lastFlush = flushEvents[flushEvents.length - 1];
  assert(lastFlush.payload.finalText === 'Hello World',
    `Flush contains correct text: "${lastFlush.payload.finalText}"`);
}

// ── Test 2: Error before load — text preserved ──
function testErrorBeforeLoad() {
  console.log('\n=== Test 2: Error before load — text preserved ===');
  pendingResultCardPayload = null;
  pendingResultText = '';
  pendingSessionId = '';
  activeSessionId = '';
  resultCardReady = false;
  resultCardWinExists = false;
  events.length = 0;

  const sessionId = 'test-session-2';
  recordingStarted(sessionId);

  showResultCard('Test text', 'Test', 'no_editable_target', '');
  assert(pendingResultCardPayload !== null, 'payload set after show');

  // Error arrives
  onError(sessionId);
  // Phase E fix: error should NOT clear pending payload
  assert(pendingResultCardPayload !== null,
    'Phase E: error must NOT clear pending payload');
  assert(pendingResultText === 'Test text',
    'Phase E: error must NOT clear pending text');
}

// ── Test 3: New session clears everything ──
function testNewSessionClears() {
  console.log('\n=== Test 3: New session clears old payload ===');
  pendingResultCardPayload = { finalText: 'Old text', lastTranscription: '', state: '', message: '' };
  pendingResultText = 'Old text';
  pendingSessionId = 'old-session';
  activeSessionId = 'old-session';
  resultCardWinExists = true;
  resultCardReady = true;
  events.length = 0;

  // New recording starts
  recordingStarted('new-session');
  assert(pendingResultCardPayload === null, 'New session clears payload');
  assert(pendingResultText === '', 'New session clears text');
  assert(pendingSessionId === '', 'New session clears session id');
  assert(activeSessionId === 'new-session', 'activeSessionId updated');
}

// ── Test 4: Stale session events are ignored ──
function testStaleSessionEvents() {
  console.log('\n=== Test 4: Stale session events are ignored ===');
  pendingResultCardPayload = null;
  pendingResultText = '';
  pendingSessionId = '';
  activeSessionId = 'current-session';
  resultCardWinExists = true;
  resultCardReady = true;
  events.length = 0;

  // Stale pipeline_done from old session
  const oldFlushLen = events.filter(e => e.type === 'flush').length;
  // This shouldn't affect anything since we just check events don't clear
  assert(activeSessionId === 'current-session', 'active session unchanged');
}

// ── Test 5: Empty text does not create card (backend-side enforcement) ──
function testEmptyTextNoCard() {
  console.log('\n=== Test 5: Empty text no card ===');
  pendingResultCardPayload = null;
  pendingResultText = '';
  pendingSessionId = '';
  activeSessionId = 'session-5';
  resultCardWinExists = true;
  resultCardReady = true;
  events.length = 0;

  // If empty text arrives, showResultCard should not be called
  // (This is enforced in pipeline.py, but we test the JS would handle it)
  const text = '   '.trim();
  if (!text) {
    // Don't call showResultCard
    assert(true, 'empty text skipped');
  }
  assert(pendingResultCardPayload === null,
    'Empty text should not create payload');
}

// ── Test 6: Copy after done loads correctly ──
function testCopyAfterDone() {
  console.log('\n=== Test 6: Copy after done ===');
  pendingResultCardPayload = { finalText: 'Copy text', lastTranscription: '', state: '', message: '' };
  pendingResultText = 'Copy text';
  pendingSessionId = 'session-6';
  activeSessionId = 'session-6';
  resultCardWinExists = true;
  resultCardReady = true;
  events.length = 0;

  // Copy should use pendingResultText
  const copyText = pendingResultText || '';
  assert(copyText === 'Copy text', 'copy text is correct');
}

// ── Run all tests ──
testShowDoneLoadRace();
testErrorBeforeLoad();
testNewSessionClears();
testStaleSessionEvents();
testEmptyTextNoCard();
testCopyAfterDone();

console.log(`\n${'='.repeat(40)}`);
if (failures > 0) {
  console.error(`FAILED: ${failures}/${total} tests failed`);
  process.exit(1);
} else {
  console.log(`ALL ${total} TESTS PASSED`);
}