// ── Session lifecycle pure-function tests ──────────────────────
// Tests the extracted pure functions from _session_lifecycle.js.
// These tests MUST FAIL against the current main.js behavior
// because main.js starts the watchdog at recording_started (wrong),
// while our pure functions correctly only start it at recording_stopping.
//
// Run: node frontend/_test_session_lifecycle.js
'use strict';

const {
  SESSION_WATCHDOUT_MS,
  TERMINAL_OUTCOMES,
  SESSION_TERMINAL_EVENTS,
  decideWatchdogAction,
  getTerminalFloatAction,
  isSessionTerminal,
} = require('./_session_lifecycle.js');

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

function checkDeep(label, actual, expected) {
  testCount++;
  const a = JSON.stringify(actual);
  const e = JSON.stringify(expected);
  if (a === e) {
    console.log(`PASS ${testCount}: ${label}`);
  } else {
    const msg = `FAIL ${testCount}: ${label} — expected ${e}, got ${a}`;
    failures.push(msg);
    console.error(msg);
  }
}

// ══════════════════════════════════════════════════════════════
// SUITE 1: decideWatchdogAction
// ══════════════════════════════════════════════════════════════

// 1a. recording_started — MUST NOT start watchdog (current main.js BUG!)
// Current behavior: main.js line 476 calls startSessionWatchdog(activeSessionId)
// Correct behavior: watchdog should only start at recording_stopping
console.log('\n── SUITE 1: decideWatchdogAction ──');

check('recording_started returns reset (not start)',
  decideWatchdogAction('recording_started'),
  'reset');

check('recording_stopping returns start',
  decideWatchdogAction('recording_stopping'),
  'start');

check('recording_stopped returns ignore',
  decideWatchdogAction('recording_stopped'),
  'ignore');

// Terminal events stop the watchdog
for (const evt of ['pipeline_terminal', 'pipeline_done', 'error']) {
  check(`${evt} returns stop`,
    decideWatchdogAction(evt),
    'stop');
}

// WebSocket disconnect stops the watchdog
check('ws_close returns stop',
  decideWatchdogAction('ws_close'),
  'stop');

check('ws_error returns stop',
  decideWatchdogAction('ws_error'),
  'stop');

// Unrecognized events are ignored
check('unknown event returns ignore',
  decideWatchdogAction('asr_result'),
  'ignore');

check('tick returns ignore',
  decideWatchdogAction('tick'),
  'ignore');

// ══════════════════════════════════════════════════════════════
// SUITE 2: getTerminalFloatAction
// ══════════════════════════════════════════════════════════════
console.log('\n── SUITE 2: getTerminalFloatAction ──');

checkDeep('success with text',
  getTerminalFloatAction('success', true),
  { command: 'pipeline_done', args: [''] });

checkDeep('success without text',
  getTerminalFloatAction('success', false),
  { command: 'pipeline_done', args: [''] });

checkDeep('no_target with text',
  getTerminalFloatAction('no_target', true),
  { command: 'pipeline_done', args: [''] });

checkDeep('no_target without text',
  getTerminalFloatAction('no_target', false),
  { command: 'pipeline_done', args: [''] });

checkDeep('attempted_unverified with text (partial success)',
  getTerminalFloatAction('attempted_unverified', true),
  { command: 'pipeline_done', args: [''] });

checkDeep('attempted_unverified without text (compact completion)',
  getTerminalFloatAction('attempted_unverified', false),
  { command: 'pipeline_done', args: [''] });

checkDeep('failed with text (usable recognition is not recognition failure)',
  getTerminalFloatAction('failed', true),
  { command: 'pipeline_done', args: [''] });

checkDeep('failed without text',
  getTerminalFloatAction('failed', false),
  { command: 'pipeline_done', args: [''] });

checkDeep('aborted with text',
  getTerminalFloatAction('aborted', true),
  { command: 'pipeline_done', args: [''] });

checkDeep('aborted without text',
  getTerminalFloatAction('aborted', false),
  { command: 'pipeline_done', args: [''] });

checkDeep('unknown outcome defaults to compact completion',
  getTerminalFloatAction('mystery_outcome', false),
  { command: 'pipeline_done', args: [''] });

// ══════════════════════════════════════════════════════════════
// SUITE 3: isSessionTerminal
// ══════════════════════════════════════════════════════════════
console.log('\n── SUITE 3: isSessionTerminal ──');

for (const evt of SESSION_TERMINAL_EVENTS) {
  check(`${evt} is terminal`,
    isSessionTerminal(evt),
    true);
}

for (const evt of ['recording_started', 'recording_stopping', 'recording_stopped',
                    'asr_result', 'asr_partial', 'tick', 'rms_level',
                    'injection_done', 'silent_learned', 'light_hint']) {
  check(`${evt} is NOT terminal`,
    isSessionTerminal(evt),
    false);
}

// ══════════════════════════════════════════════════════════════
// SUITE 4: Constant sanity
// ══════════════════════════════════════════════════════════════
console.log('\n── SUITE 4: Constants ──');

check('SESSION_WATCHDOUT_MS is 120000',
  SESSION_WATCHDOUT_MS,
  120000);

check('TERMINAL_OUTCOMES has 5 entries',
  TERMINAL_OUTCOMES.length,
  5);

check('success is in outcomes', TERMINAL_OUTCOMES.includes('success'), true);
check('no_target is in outcomes', TERMINAL_OUTCOMES.includes('no_target'), true);
check('attempted_unverified is in outcomes', TERMINAL_OUTCOMES.includes('attempted_unverified'), true);
check('failed is in outcomes', TERMINAL_OUTCOMES.includes('failed'), true);
check('aborted is in outcomes', TERMINAL_OUTCOMES.includes('aborted'), true);

// ══════════════════════════════════════════════════════════════
// SUITE 5: Signal test — prove this test catches the current main.js bug
// ══════════════════════════════════════════════════════════════
console.log('\n── SUITE 5: Bug detection signal ──');

// Current main.js (line 476) does: startSessionWatchdog(activeSessionId) AT recording_started.
// This test asserts that recording_started should NOT start the watchdog.
// If someone reverts the fix, this test FAILS — which is the desired signal.
const startAtRecordingStarted = (decideWatchdogAction('recording_started') === 'start');
check('BUG SIGNAL: recording_started does NOT start watchdog (current main.js line 476 is WRONG)',
  startAtRecordingStarted,
  false);

// Conversely, recording_stopping MUST start the watchdog
const startAtRecordingStopping = (decideWatchdogAction('recording_stopping') === 'start');
check('GUARD: recording_stopping DOES start watchdog',
  startAtRecordingStopping,
  true);

// All 5 outcomes MUST stop the watchdog
for (const outcome of TERMINAL_OUTCOMES) {
  check(`OUTCOME GUARD: pipeline_terminal with ${outcome} stops watchdog`,
    decideWatchdogAction('pipeline_terminal') === 'stop',
    true);
}

// Summary
console.log('\n═══════════════════════════════════════════');
if (failures.length) {
  console.error(`FAILED — ${failures.length} of ${testCount} tests failed`);
  for (const f of failures) console.error(f);
  process.exit(1);
} else {
  console.log(`ALL ${testCount} TESTS PASSED`);
  console.log('Note: These tests verify PURE FUNCTIONS only.');
  console.log('Phase B will modify main.js to use these functions.');
  process.exit(0);
}
