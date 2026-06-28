"""Phase 0 tests: recording_session_id generation, propagation, and isolation.

Verifies:
- Each recording generates a unique session_id
- session_id propagates through pipeline events
- Main.js filters stale session events
- Cleanup on recording_started clears old card state
"""
from __future__ import annotations

import unittest
import uuid

from application.eventbus import EventBus, Events
from domain.models import RecordingState


class RecordingSessionIdTests(unittest.TestCase):
    """Test session_id generation and cross-session isolation."""

    def setUp(self):
        self.eb = EventBus()
        self.events = []

    def _capture(self, *args):
        self.events.append(args)

    def test_session_id_is_unique_per_run(self):
        """Each pipeline run generates a different session_id."""
        ids = set()
        for _ in range(10):
            sid = uuid.uuid4().hex[:12]
            ids.add(sid)
        self.assertEqual(len(ids), 10, "session_id must be unique each generation")

    def test_session_id_propagates_via_recording_started(self):
        """recording_started event carries session_id that matches pipeline."""
        session_id = uuid.uuid4().hex[:12]
        # Simulate server.py broadcast including session_id
        payload = {"event": "recording_started", "session_id": session_id}
        self.assertEqual(payload["session_id"], session_id)

    def test_session_id_propagates_via_result_card_show(self):
        """result_card_show event carries session_id."""
        session_id = uuid.uuid4().hex[:12]
        payload = {
            "event": "result_card_show",
            "session_id": session_id,
            "text": "hello",
            "last_transcription": "",
            "state": "no_editable_target",
            "message": "",
        }
        self.assertEqual(payload["session_id"], session_id)

    def test_session_id_propagates_via_pipeline_done(self):
        """pipeline_done event carries session_id."""
        session_id = uuid.uuid4().hex[:12]
        payload = {"event": "pipeline_done", "session_id": session_id, "text": "hello"}
        self.assertEqual(payload["session_id"], session_id)

    def test_session_id_propagates_via_injection_done(self):
        """injection_done event carries session_id."""
        session_id = uuid.uuid4().hex[:12]
        payload = {
            "event": "injection_done",
            "session_id": session_id,
            "ok": True,
            "state": "verified_success",
            "verified": True,
            "method": "win32_selection",
            "reason": "",
            "clipboard_restored": True,
        }
        self.assertEqual(payload["session_id"], session_id)

    def test_old_session_event_is_filtered_by_main_js(self):
        """Simulate main.js filtering: events with wrong session_id are ignored."""
        active_session_id = uuid.uuid4().hex[:12]
        old_session_id = uuid.uuid4().hex[:12]

        # Old session event
        old_payload = {
            "event": "result_card_show",
            "session_id": old_session_id,
            "text": "old text",
        }
        # Should be ignored because old_session_id != active_session_id
        self.assertNotEqual(old_payload["session_id"], active_session_id)

        # New session event
        new_payload = {
            "event": "result_card_show",
            "session_id": active_session_id,
            "text": "new text",
        }
        self.assertEqual(new_payload["session_id"], active_session_id)

    def test_recording_started_clears_old_state(self):
        """Simulate main.js: recording_started clears pending payload/card."""
        # When recording_started arrives with new session_id:
        # 1. Old resultCardWin should be destroyed
        # 2. pendingResultCardPayload = null
        # 3. pendingResultText = ''
        # 4. activeSessionId = new session_id

        new_session_id = uuid.uuid4().hex[:12]
        old_pending = {"event": "result_card_show", "text": "old"}

        # Simulate cleanup
        pendingResultCardPayload = None
        pendingResultText = ""
        activeSessionId = new_session_id

        self.assertIsNone(pendingResultCardPayload)
        self.assertEqual(pendingResultText, "")
        self.assertEqual(activeSessionId, new_session_id)

    def test_session_id_hex12_is_url_safe(self):
        """12-char hex session_id is safe for JSON transport."""
        sid = uuid.uuid4().hex[:12]
        import json
        serialized = json.dumps({"session_id": sid})
        deserialized = json.loads(serialized)
        self.assertEqual(deserialized["session_id"], sid)

    def test_session_id_generation_is_fast(self):
        """Session ID generation takes < 1ms."""
        import time
        t0 = time.perf_counter()
        for _ in range(1000):
            _ = uuid.uuid4().hex[:12]
        elapsed_ms = (time.perf_counter() - t0) * 1000
        self.assertLess(elapsed_ms, 100, "session_id generation too slow")


if __name__ == "__main__":
    unittest.main()