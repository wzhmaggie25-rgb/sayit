from __future__ import annotations

import tempfile
import unittest

import infrastructure.paths as paths
from infrastructure.database import Database


class HistoryBackfillTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old_app_data_dir = paths.APP_DATA_DIR
        self._old_db_instance = Database._instance
        paths.APP_DATA_DIR = self._tmp.name
        Database._instance = None

    def tearDown(self):
        Database._instance = self._old_db_instance
        paths.APP_DATA_DIR = self._old_app_data_dir
        self._tmp.cleanup()

    def test_manual_history_edit_backfills_typeless_edit_state(self):
        db = Database()
        history_id = db.add_history(
            raw_text="hello wrld",
            refined_text="hello wrld",
            final_text="hello wrld",
        )

        db.update_history_text(history_id, "hello world")
        row = db.get_history(limit=1)[0]

        self.assertEqual(row["final_text"], "hello world")
        self.assertEqual(row["edited_text"], "hello world")
        self.assertEqual(row["edited_text_status"], "MANUAL_EDITED")
        self.assertEqual(row["edited_text_attempts"], 1)


if __name__ == "__main__":
    unittest.main()
