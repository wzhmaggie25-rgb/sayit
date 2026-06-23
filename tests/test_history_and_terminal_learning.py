from __future__ import annotations

import tempfile
import unittest
import sqlite3
from pathlib import Path
from unittest import mock

from infrastructure.focus_context import (
    includes_terminal_inserted_text,
    normalize_terminal_track_text,
)


class TerminalLearningTests(unittest.TestCase):
    def test_terminal_text_normalization_ignores_spacing_and_newlines(self):
        inserted = "hello world\nfrom Sayit"
        buffer = "PS C:\\code> hello   world\r\nfrom   Sayit"

        self.assertEqual(
            normalize_terminal_track_text(inserted),
            "helloworldfromSayit",
        )
        self.assertTrue(includes_terminal_inserted_text(buffer, inserted))


class HistoryIdTests(unittest.TestCase):
    def test_legacy_integer_history_id_table_is_migrated_to_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "sayit.db")
            conn = sqlite3.connect(db_path)
            try:
                conn.execute("CREATE TABLE schema_version (version INTEGER PRIMARY KEY)")
                conn.execute("INSERT INTO schema_version (version) VALUES (4)")
                conn.execute(
                    """CREATE TABLE history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        raw_text TEXT NOT NULL DEFAULT '',
                        final_text TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL DEFAULT ''
                    )"""
                )
                conn.execute(
                    "INSERT INTO history (raw_text, final_text, created_at) VALUES (?,?,?)",
                    ("old raw", "old final", "2026-06-21 12:00:00"),
                )
                conn.commit()
            finally:
                conn.close()

            from infrastructure import database as database_module

            with mock.patch.object(database_module, "database_path", return_value=db_path):
                database_module.Database._instance = None
                db = database_module.Database()
                history_id = db.add_history(raw_text="new raw", final_text="new final", pasted=True)

                self.assertIsInstance(history_id, str)
                self.assertEqual(len(history_id), 32)

                conn = sqlite3.connect(db_path)
                try:
                    id_col = [
                        row for row in conn.execute("PRAGMA table_info(history)").fetchall()
                        if row[1] == "id"
                    ][0]
                    rows = conn.execute("SELECT id, raw_text FROM history ORDER BY created_at").fetchall()
                finally:
                    conn.close()

                self.assertIn("TEXT", id_col[2].upper())
                self.assertEqual(rows[0][0], "1")
                self.assertEqual(rows[0][1], "old raw")

            database_module.Database._instance = None

    def test_text_history_id_can_be_updated_by_silent_learning_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "sayit.db")
            from infrastructure import database as database_module

            with mock.patch.object(database_module, "database_path", return_value=db_path):
                database_module.Database._instance = None
                db = database_module.Database()
                history_id = db.add_history(raw_text="raw", final_text="final", pasted=True)

                self.assertTrue(history_id)
                self.assertIsInstance(history_id, str)

                db.update_history_edit(history_id, edited_text=None, status="TRACKING", attempts_delta=0)
                row = db.get_history_entry(history_id)

                self.assertEqual(row["edited_text_status"], "TRACKING")

            database_module.Database._instance = None


if __name__ == "__main__":
    unittest.main()
