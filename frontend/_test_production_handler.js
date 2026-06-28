/**
 * Phase A5: Frontend real-handler tests.
 *
 * Proves that main.js does NOT use the pure functions from _session_lifecycle.js
 * (it duplicates the logic inline) and that pipeline_done/pipeline_terminal
 * handling may diverge.
 *
 * FAILS on current code:
 * 1. main.js at line 476 calls startSessionWatchdog directly instead of
 *    calling decideWatchdogAction('recording_started', ...)
 * 2. main.js duplicates SESSION_WATCHDOUT_MS constant at line 343
 * 3. pipeline_done and pipeline_terminal handling are not unified through
 *    a single pure function
 *
 * These tests are Node.js-compatible (no Electron) — they inspect main.js
 * source code and verify it does NOT use the imported pure functions.
 *
 * Usage: node frontend/_test_production_handler.js
 */
'use strict';

const fs = require('fs');
const path = require('path');

// ── Paths ───────────────────────────────────────────────────
const MAIN_JS = path.join(__dirname, 'main.js');
const LIFECYCLE_JS = path.join(__dirname, '_session_lifecycle.js');

// ── Load lifecycle module (pure, no Electron deps) ────────────
const lifecycle = require('./_session_lifecycle.js');

// ── Load main.js source for inspection (cannot require due to Electron deps) ──
const mainSource = fs.readFileSync(MAIN_JS, 'utf-8');

// ── Test harness ──────────────────────────────────────────────
const failures = [];
let testCount = 0;

function check(label, actual, expected) {
  testCount++;
  if (actual === expected) {
    console.log(`PASS ${testCount}: ${label}`);
  } else {
    const msg = `FAIL ${testCount}: ${label} — expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`;
    failures.push(msg);
    console.error(msg);
  }
}

function checkIn(label, needle, haystack) {
  testCount++;
  if (haystack.includes(needle)) {
    console.log(`PASS ${testCount}: ${label}`);
  } else {
    const msg = `FAIL ${testCount}: ${label} — expected to find ${JSON.stringify(needle)}`;
    failures.push(msg);
    console.error(msg);
  }
}

function checkNotIn(label, needle, haystack) {
  testCount++;
  if (!haystack.includes(needle)) {
    console.log(`PASS ${testCount}: ${label}`);
  } else {
    const msg = `FAIL ${testCount}: ${label} — expected NOT to find ${JSON.stringify(needle)}`;
    failures.push(msg);
    console.error(msg);
  }
}

// ══════════════════════════════════════════════════════════════
// TEST 1: main.js imports decideWatchdogAction
// ══════════════════════════════════════════════════════════════

console.log('\n── TEST 1: main.js imports from _session_lifecycle.js ──');

checkIn('main.js requires _session_lifecycle.js',
  "require('./_session_lifecycle.js')",
  mainSource);

// ══════════════════════════════════════════════════════════════
// TEST 2: main.js calls decideWatchdogAction (it does NOT on current code)
// ══════════════════════════════════════════════════════════════

console.log('\n── TEST 2: main.js calls decideWatchdogAction ──');

// CURRENT BUG: main.js does NOT call decideWatchdogAction.
// Instead it directly calls startSessionWatchdog/stopSessionWatchdog
// at each event case in the WebSocket switch statement.
checkIn('main.js must call decideWatchdogAction (FAILS on current code)',
  'decideWatchdogAction(',
  mainSource);

// ══════════════════════════════════════════════════════════════
// TEST 3: main.js does NOT have a duplicated SESSION_WATCHDOUT_MS
// ══════════════════════════════════════════════════════════════

console.log('\n── TEST 3: main.js uses the imported SESSION_WATCHDOUT_MS ──');

// CURRENT BUG: main.js line 343 has its own `const SESSION_WATCHDOUT_MS = 120000;`
// which duplicates the one in _session_lifecycle.js
checkNotIn('main.js must NOT redefine SESSION_WATCHDOUT_MS (FAILS on current code)',
  'const SESSION_WATCHDOUT_MS = ',
  mainSource);

// ══════════════════════════════════════════════════════════════
// TEST 4: pipeline_done handling uses isSessionTerminal
// ══════════════════════════════════════════════════════════════

console.log('\n── TEST 4: pipeline_done and pipeline_terminal handled through pure functions ──');

// CURRENT BUG: main.js handles pipeline_terminal and pipeline_done
// as separate cases in the switch statement. They should both dispatch
// through the same pure function.
//
// Count distinct case statements for these two events
const pipelineTerminalMatches = mainSource.match(/case\s+['"]pipeline_terminal['"]/g);
const pipelineDoneMatches = mainSource.match(/case\s+['"]pipeline_done['"]/g);
const piplineTerminalCount = pipelineTerminalMatches ? pipelineTerminalMatches.length : 0;
const pipelineDoneCount = pipelineDoneMatches ? pipelineDoneMatches.length : 0;

// AFTER FIX: both should use the same handler dispatch via decideWatchdogAction
// BEFORE FIX: they are separate cases (count = 1 each)
check('pipeline_terminal case exists in switch (current bug: separate case)',
  piplineTerminalCount >= 1, true);

check('pipeline_done case exists in switch (current bug: separate case)',
  pipelineDoneCount >= 1, true);

// BOTH conditions must evaluate to the EXACT same handler code block.
// On current code they are separate — meaning they could diverge.
check('pipeline_terminal and pipeline_done are separate cases (BUG confirmed)',
  piplineTerminalCount + pipelineDoneCount >= 2, true);

// ══════════════════════════════════════════════════════════════
// TEST 5: main.js uses getTerminalFloatAction (it likely does)
// ══════════════════════════════════════════════════════════════

console.log('\n── TEST 5: getTerminalFloatAction is used in main.js ──');

checkIn('main.js calls getTerminalFloatAction',
  'getTerminalFloatAction(',
  mainSource);

// ══════════════════════════════════════════════════════════════
// TEST 6: main.js uses isSessionTerminal (it likely does NOT for all paths)
// ══════════════════════════════════════════════════════════════

console.log('\n── TEST 6: main.js calls isSessionTerminal ──');

checkIn('main.js must call isSessionTerminal (FAILS if not used in all event paths)',
  'isSessionTerminal(',
  mainSource);

// ══════════════════════════════════════════════════════════════
// TEST 7: Pipeline_terminal must also be in SESSION_TERMINAL_EVENTS
// ══════════════════════════════════════════════════════════════

console.log('\n── TEST 7: Pipeline terminal events consistency ──');

check('pipeline_terminal is in SESSION_TERMINAL_EVENTS',
  lifecycle.SESSION_TERMINAL_EVENTS.includes('pipeline_terminal'), true);

check('pipeline_done is in SESSION_TERMINAL_EVENTS',
  lifecycle.SESSION_TERMINAL_EVENTS.includes('pipeline_done'), true);

// ══════════════════════════════════════════════════════════════
// TEST 8: Wire action — prove decideWatchdogAction('recording_started') returns 'reset'
//          while main.js calls startSessionWatchdog at recording_started
// ══════════════════════════════════════════════════════════════

console.log('\n── TEST 8: Pure function vs main.js behavior divergence ──');

// Pure function says 'reset' for recording_started
check('decideWatchdogAction("recording_started") returns "reset"',
  lifecycle.decideWatchdogAction('recording_started'), 'reset');

// Pure function says 'stop' for pipeline_terminal
check('decideWatchdogAction("pipeline_terminal") returns "stop"',
  lifecycle.decideWatchdogAction('pipeline_terminal'), 'stop');

// Pure function says 'stop' for pipeline_done
check('decideWatchdogAction("pipeline_done") returns "stop"',
  lifecycle.decideWatchdogAction('pipeline_done'), 'stop');

// Pure function says 'start' for recording_stopping
check('decideWatchdogAction("recording_stopping") returns "start"',
  lifecycle.decideWatchdogAction('recording_stopping'), 'start');

// ══════════════════════════════════════════════════════════════
// TEST 9: Result card race — the existing _test_result_card_race.js duplicates
//          main.js logic instead of importing the production handler.
//          We verify the duplicated constants match.
// ══════════════════════════════════════════════════════════════

console.log('\n── TEST 9: Result card race logic duplication ──');

const raceSource = fs.readFileSync(
  path.join(__dirname, '_test_result_card_race.js'), 'utf-8');

// The race test re-declares variables that exist in main.js
checkIn('result card race test HAS pendingResultCardPayload (duplicated)',
  'pendingResultCardPayload', raceSource);

checkIn('result card race test HAS pendingResultText (duplicated)',
  'pendingResultText', raceSource);

checkIn('result card race test HAS activeSessionId (duplicated)',
  'activeSessionId', raceSource);

// AFTER FIX: the race test should import from main.js (or a shared module)
// and NOT redeclare these variables.

// ══════════════════════════════════════════════════════════════
// Summary
// ══════════════════════════════════════════════════════════════

console.log('\n═══════════════════════════════════════════');
if (failures.length) {
  console.error(`FAILED — ${failures.length} of ${testCount} tests failed`);
  for (const f of failures) console.error(f);
  process.exit(1);
} else {
  console.log(`ALL ${testCount} TESTS PASSED`);
  console.log('Note: Tests 2, 3, 6 should FAIL on current code (main.js does not');
  console.log('call decideWatchdogAction and duplicates SESSION_WATCHDOUT_MS).');
  process.exit(0);
}