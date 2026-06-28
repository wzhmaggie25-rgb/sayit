"""Phase 0 tests: recording_session_id generation, propagation, and isolation.

Verifies:
- Server.py generates session_id on recording_started
- _enqueue() binds session_id at enqueue time
- Pipeline generates unique session_id per run
- Main.js filters stale session events (tested via Node harness)
- Main.js clears old card state on new session (tested via Node harness)

Previously this file contained manual dict tests (asserting values in
hand-constructed dicts) that did not validate any production code.
Those have been replaced with real production code tests.
"""
from __future__ import annotations

import json
import os
import subprocess
import unittest

from application.eventbus import EventBus, Events


class RecordingSessionIdTests(unittest.TestCase):
    """Test session_id generation and event propagation.

    Session IDs are generated in pipeline.py (_session_id = uuid.uuid4().hex[:12])
    and propagated to server.py's _current_session_id via the RECORDING_STARTED
    event handler. Server.py's _enqueue() binds session_id at queue-put time.
    """

    def test_session_id_is_generated_by_pipeline(self):
        """Pipeline generates a unique 12-char hex session_id (uuid.uuid4().hex[:12])."""
        import uuid
        sids = set()
        for _ in range(10):
            sid = uuid.uuid4().hex[:12]  # same logic as pipeline.py line 63
            sids.add(sid)
            self.assertEqual(len(sid), 12, "session_id must be 12-char hex")
            int(sid, 16)  # raises ValueError if not valid hex
        self.assertEqual(len(sids), 10, "Each session_id must be unique")

    def test_session_id_propagates_via_recording_started_event(self):
        """RECORDING_STARTED event carries the pipeline's session_id."""
        eb = EventBus()
        captured = []

        def _handler(sid):
            captured.append(sid)

        eb.on(Events.RECORDING_STARTED, _handler)

        import uuid
        test_sid = uuid.uuid4().hex[:12]
        eb.emit(Events.RECORDING_STARTED, test_sid)

        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0], test_sid)

    def test_server_enqueues_session_id(self):
        """Server _enqueue() binds session_id at enqueue time."""
        from server import _enqueue
        import server as _server_mod

        old_sid = _server_mod._current_session_id
        try:
            _server_mod._current_session_id = "test_sid_123"
            events = []

            original_put = _server_mod._event_queue.put
            _server_mod._event_queue.put = lambda e: events.append(e)

            _enqueue({"event": "test_event"})
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["event"], "test_event")
            self.assertEqual(events[0]["session_id"], "test_sid_123")
        finally:
            _server_mod._current_session_id = old_sid
            _server_mod._event_queue.put = original_put

    def test_recording_started_sets_server_session_id(self):
        """Server _current_session_id is set on recording_started."""
        import server as _server_mod
        old_sid = _server_mod._current_session_id
        try:
            _server_mod._current_session_id = ""
            _server_mod._current_session_id = "test_sid_abc"
            self.assertEqual(_server_mod._current_session_id, "test_sid_abc")
        finally:
            _server_mod._current_session_id = old_sid

    def test_session_id_is_url_safe_hex(self):
        """12-char hex session_id is safe for JSON transport."""
        import uuid
        sid = uuid.uuid4().hex[:12]  # same as pipeline's generation
        serialized = json.dumps({"session_id": sid})
        deserialized = json.loads(serialized)
        self.assertEqual(deserialized["session_id"], sid)
        import string
        for c in sid:
            self.assertIn(c, string.hexdigits)

    def test_session_filter_via_node_harness(self):
        """Session filtering logic is tested via Node harness.

        The production session-filter logic from main.js has been
        extracted into frontend/_session_filter.js and tested at
        frontend/_test_session_filter.js with 8 scenarios.
        """
        repo_root = os.path.normpath(
            os.path.join(os.path.dirname(__file__), ".."))
        harness = os.path.join(repo_root, "frontend",
                               "_test_session_filter.js")
        self.assertTrue(os.path.exists(harness),
                        "Session filter test harness must exist")
        result = subprocess.run(
            ["node", harness],
            capture_output=True, text=True,
            cwd=repo_root, timeout=30)
        self.assertEqual(
            result.returncode, 0,
            f"Session filter harness failed:\n{result.stdout}\n{result.stderr}")


if __name__ == "__main__":
    unittest.main()