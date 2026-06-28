/**
 * Session ID filtering logic — pure function extracted from main.js.
 *
 * Determines whether an event should be filtered based on session ID comparison.
 *
 * Run: node frontend/_test_session_filter.js
 */
'use strict';

/**
 * @param {string|null} eventSessionId  session_id from event payload
 * @param {string}      activeSessionId current active session
 * @returns {string} 'accept' | 'ignore' | 'clear_and_accept'
 */
function shouldAcceptSession(eventSessionId, activeSessionId) {
  if (!activeSessionId) return 'accept';
  if (!eventSessionId) return 'accept';
  if (eventSessionId === activeSessionId) return 'accept';
  return 'ignore';
}

/**
 * Determine if a recording_started event should clear old state.
 * Always clears if session is new/different.
 */
function shouldClearOnNewSession(newSessionId, activeSessionId) {
  if (!newSessionId) return false;
  return newSessionId !== activeSessionId;
}

module.exports = { shouldAcceptSession, shouldClearOnNewSession };