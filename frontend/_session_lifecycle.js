// ── Session lifecycle pure functions ───────────────────────────
// Extracted from main.js for deterministic testing.
// These functions decide watchdog actions, terminal outcome mapping,
// and session-terminal event detection based solely on event type + state.
//
// Run tests: node frontend/_test_session_lifecycle.js
'use strict';

const SESSION_WATCHDOUT_MS = 120000; // 2 minute max — shared with main.js

// The 5 canonical terminal outcomes from the backend.
const TERMINAL_OUTCOMES = ['success', 'no_target', 'attempted_unverified', 'failed', 'aborted'];

// Events that indicate a session has ended regardless of outcome.
const SESSION_TERMINAL_EVENTS = ['pipeline_terminal', 'pipeline_done', 'error', 'ws_close', 'ws_error'];

/**
 * Decide what the watchdog timer should do given an incoming event.
 *
 * Returns one of:
 *   'start'  — begin/reset the watchdog timer
 *   'stop'   — cancel the watchdog timer
 *   'reset'  — reset any stale state but do NOT start the timer yet
 *   'ignore' — no action needed
 *
 * Design invariant:
 *   The watchdog timer monitors the STOPPING phase only. It MUST NOT start
 *   at recording_started, because long recordings (>2 min) would false-positive.
 *   Only recording_stopping triggers the watchdog.
 */
function decideWatchdogAction(eventType, state) {
  switch (eventType) {

    // ── Recording lifecycle ──────────────────────────────
    case 'recording_started':
      // Clear stale state from prior session, but DO NOT start watchdog.
      // A multi-minute recording must not false-positive.
      return 'reset';

    case 'recording_stopping':
      // The STOPPING phase is bounded by the watchdog. Start the timer.
      return 'start';

    case 'recording_stopped':
      // Audio capture stopped; ASR/batch may still be processing.
      // The watchdog is already running from recording_stopping — keep it.
      return 'ignore';

    // ── Terminal events (session is done) ─────────────────
    case 'pipeline_terminal':
    case 'pipeline_done':
      // Session completed normally — cancel watchdog.
      return 'stop';

    case 'error':
      // Backend error — session is over, cancel watchdog.
      return 'stop';

    // ── Connection events ────────────────────────────────
    case 'ws_close':
    case 'ws_error':
      // WebSocket disconnect — reset any running watchdog.
      // The session can no longer receive terminal events.
      return 'stop';

    // ── Other event types ────────────────────────────────
    default:
      return 'ignore';
  }
}

/**
 * Map a terminal outcome to the float action string.
 *
 * @param {string} outcome — one of TERMINAL_OUTCOMES
 * @param {boolean} finalTextAvailable — whether the pipeline produced final text
 * @returns {{ command: string, args: string[] }} float command descriptor
 */
function getTerminalFloatAction(outcome, finalTextAvailable) {
  const hasText = !!finalTextAvailable;

  switch (outcome) {
    case 'success':
      return {
        command: 'pipeline_done',
        args: [''],  // empty string = success without error message
      };

    case 'no_target':
      // No editable target found — large card shown, float should just land.
      return {
        command: 'pipeline_done',
        args: [''],
      };

    case 'attempted_unverified':
      // Injection was attempted but target was not verified — if text exists, treat as partial success.
      if (hasText) {
        return {
          command: 'pipeline_done',
          args: [''],
        };
      }
      // No text — show error hint
      return {
        command: 'error',
        args: ['处理异常，请查看历史记录或日志'],
      };

    case 'failed':
      return {
        command: 'error',
        args: ['处理异常，请查看历史记录或日志'],
      };

    case 'aborted':
      return {
        command: 'error',
        args: ['处理异常，请查看历史记录或日志'],
      };

    default:
      // Unknown outcome — treat as error defensively
      return {
        command: 'error',
        args: ['处理异常，请查看历史记录或日志'],
      };
  }
}

/**
 * Check whether an event type signals the end of a session.
 */
function isSessionTerminal(eventType) {
  return SESSION_TERMINAL_EVENTS.includes(eventType);
}

// ── Exports ─────────────────────────────────────────────
module.exports = {
  SESSION_WATCHDOUT_MS,
  TERMINAL_OUTCOMES,
  SESSION_TERMINAL_EVENTS,
  decideWatchdogAction,
  getTerminalFloatAction,
  isSessionTerminal,
};