/**
 * Supervisor decision logic tests.
 *
 * Tests the pure function `decideRestart()` from _supervisor_logic.js
 * — no Electron, no event loop, just assert on return values.
 *
 * Run: node frontend/_test_supervisor_logic.js
 */
'use strict';
const { decideRestart } = require('./_supervisor_logic');

const failures = [];

function assert(label, condition, detail) {
  if (!condition) failures.push(`FAIL: ${label}${detail ? ' — ' + detail : ''}`);
  else console.log(`PASS: ${label}`);
}

// ── Scenario 1: Normal exit (code 0, no signal) ───────
assert('normal exit (code=0, signal=null) is ignored',
  decideRestart(0, null, { userInitiatedExit: false, restartAttempted: false }) === 'ignore');

// ── Scenario 2: Abnormal exit triggers restart ───────
assert('non-zero exit triggers restart',
  decideRestart(1, null, { userInitiatedExit: false, restartAttempted: false }) === 'restart');

// ── Scenario 3: Second crash gives up ───────
assert('second crash gives up',
  decideRestart(1, null, { userInitiatedExit: false, restartAttempted: true }) === 'give_up');

// ── Scenario 4: User quit suppresses restart ───────
assert('user quit suppresses restart',
  decideRestart(1, null, { userInitiatedExit: true, restartAttempted: false }) === 'ignore');

// ── Scenario 5: After restart success, normal exit is ignored ───────
assert('restart budget reset, normal exit ignored',
  decideRestart(0, null, { userInitiatedExit: false, restartAttempted: false }) === 'ignore');

// ── Scenario 6: signal-only exit (code=null) triggers restart ───────
assert('signal-only exit triggers restart',
  decideRestart(null, 'SIGTERM', { userInitiatedExit: false, restartAttempted: false }) === 'restart');

// ── Scenario 7: signal-only exit after restart gives up ───────
assert('signal-only exit after restart gives up',
  decideRestart(null, 'SIGTERM', { userInitiatedExit: false, restartAttempted: true }) === 'give_up');

// ── Scenario 8: code=0 with signal (e.g. SIGKILL) is still abnormal ───────
assert('code=0 with signal is abnormal',
  decideRestart(0, 'SIGKILL', { userInitiatedExit: false, restartAttempted: false }) === 'restart');

// ── Scenario 9: All false defaults = restart on non-zero
assert('default state restart on non-zero',
  decideRestart(1, null, { userInitiatedExit: false, restartAttempted: false }) === 'restart');

// ── Scenario 10: user quit + restart attempted = ignore
assert('user quit even after restart attempt is ignore',
  decideRestart(1, null, { userInitiatedExit: true, restartAttempted: true }) === 'ignore');

if (failures.length) {
  console.error(`\n--- ${failures.length} FAILURE(S) ---`);
  for (const f of failures) console.error(f);
  process.exit(1);
}
console.log('\n--- ALL SUPERVISOR LOGIC TESTS PASSED ---');
process.exit(0);