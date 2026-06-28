/**
 * Session ID filtering unit tests.
 *
 * Tests the pure functions from _session_filter.js, extracted from
 * the session_id guard logic in main.js.
 *
 * Run: node frontend/_test_session_filter.js
 */
'use strict';
const { shouldAcceptSession, shouldClearOnNewSession } = require('./_session_filter');

const failures = [];
function assert(label, condition, detail) {
  if (!condition) failures.push(`FAIL: ${label}${detail ? ' — ' + detail : ''}`);
  else console.log(`PASS: ${label}`);
}

// ── shouldAcceptSession ──

// 1. Matching session → accept
assert('matching session accepted',
  shouldAcceptSession('abc123', 'abc123') === 'accept');

// 2. Non-matching → ignore
assert('mismatched session ignored',
  shouldAcceptSession('old', 'new') === 'ignore');

// 3. No active session → accept everything
assert('no active session accepts event',
  shouldAcceptSession('anything', '') === 'accept');

// 4. No event session_id → accept
assert('no event session_id accepted',
  shouldAcceptSession(null, 'active123') === 'accept');

// 5. Both empty → accept
assert('both empty accepted',
  shouldAcceptSession('', '') === 'accept');

// ── shouldClearOnNewSession ──

// 6. New session different from active → clear
assert('new session triggers clear',
  shouldClearOnNewSession('session_b', 'session_a') === true);

// 7. Same session → no clear
assert('same session does not clear',
  shouldClearOnNewSession('session_a', 'session_a') === false);

// 8. Empty new session → no clear
assert('empty new session does not clear',
  shouldClearOnNewSession('', 'session_a') === false);

if (failures.length) {
  console.error(`\n--- ${failures.length} SESSION FILTER FAILURE(S) ---`);
  for (const f of failures) console.error(f);
  process.exit(1);
}
console.log('\n--- ALL SESSION FILTER TESTS PASSED ---');
process.exit(0);