/**
 * Backend supervisor decision logic — pure function, no Electron dependencies.
 *
 * Decides whether to restart the backend based on exit code, signal, and state.
 *
 * Returns: 'ignore' | 'restart' | 'give_up'
 */
'use strict';

/**
 * @param {number|null} code     Exit code (null if signal-only)
 * @param {string|null} signal   Exit signal (null if normal exit)
 * @param {object}      state    Supervisor state snapshot
 * @param {boolean}     state.userInitiatedExit
 * @param {boolean}     state.restartAttempted
 * @returns {string} 'ignore' | 'restart' | 'give_up'
 */
function decideRestart(code, signal, state) {
  if (state.userInitiatedExit) return 'ignore';
  if (code === 0 && signal === null) return 'ignore';
  if (state.restartAttempted) return 'give_up';
  return 'restart';
}

module.exports = { decideRestart };