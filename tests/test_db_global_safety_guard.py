"""Proof tests for the pytest-wide real-database guard.

These prove the automatic guard (installed by tests/conftest.py via
tests/db_safety_guard) blocks any test from opening or migrating the real SayIt
database, even when a test patches the wrong path symbol, and that legitimate
temporary databases still work. The real sayit.db is never opened.
"""
from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import infrastructure.paths as paths
import infrastructure.database as dbmod
from tests import db_safety_guard as guard
from tests.db_safety_guard import IsolatedDatabase


class GlobalDatabaseGuardTests(unittest.TestCase):
    """The conftest guard wraps sqlite3.connect for the whole pytest process."""

    def setUp(self):
        dbmod.Database._instance = None

    def tearDown(self):
        dbmod.Database._instance = None

    def test_guard_is_installed(self):
        """sqlite3.connect is the guarded wrapper during the pytest session."""
        self.assertTrue(guard.is_global_guard_installed())
        self.assertIs(sqlite3.connect, guard.guarded_connect)

    def test_real_path_database_fails_before_connect_or_migrate(self):
        """A Database() resolving to the real APPDATA path raises before the
        underlying sqlite3.connect is ever reached (so no migrate/write)."""
        real_db = os.path.join(paths.APP_DATA_DIR, "sayit.db")
        with patch.object(dbmod, "database_path", return_value=real_db):
            with patch.object(guard, "_orig_sqlite_connect") as orig:
                with self.assertRaises(guard.RealDatabaseAccessError):
                    dbmod.Database()
                orig.assert_not_called()

    def test_wrong_symbol_patch_still_blocked(self):
        """Patching only infrastructure.paths.database_path (the original bug)
        does not rebind infrastructure.database.database_path, so Database()
        still resolves the real path — and the connection guard blocks it."""
        with patch.object(paths, "database_path", return_value="/tmp/should-not-be-used.db"):
            with patch.object(guard, "_orig_sqlite_connect") as orig:
                with self.assertRaises(guard.RealDatabaseAccessError):
                    dbmod.Database()
                orig.assert_not_called()

    def test_temp_path_database_succeeds(self):
        """A Database() on a temp path connects and migrates normally."""
        tmpdir = tempfile.mkdtemp(prefix="sayit-guard-ok-")
        tmp_db = os.path.join(tmpdir, "test.db")
        try:
            with patch.object(dbmod, "database_path", return_value=tmp_db):
                db = dbmod.Database()
                self.assertEqual(os.path.abspath(db._db_path), os.path.abspath(tmp_db))
                self.assertTrue(os.path.exists(tmp_db))
                self.assertEqual(db.count_history(), 0)
        finally:
            dbmod.Database._instance = None
            for name in os.listdir(tmpdir):
                try:
                    os.remove(os.path.join(tmpdir, name))
                except OSError:
                    pass
            try:
                os.rmdir(tmpdir)
            except OSError:
                pass

    def test_memory_database_allowed(self):
        """:memory: and file::memory: URIs are never blocked."""
        c1 = sqlite3.connect(":memory:")
        c1.execute("CREATE TABLE t (x)")
        c1.close()
        c2 = sqlite3.connect("file::memory:?cache=shared", uri=True)
        c2.close()

    def test_isolated_database_helper_still_works(self):
        """The opt-in IsolatedDatabase helper continues to work under the guard."""
        with IsolatedDatabase(prefix="sayit-guard-iso-") as iso:
            db = iso.make_database()
            self.assertEqual(os.path.abspath(db._db_path), os.path.abspath(iso.db_path))
            self.assertEqual(db.count_history(), 0)

    def test_direct_real_path_connect_blocked(self):
        """A raw sqlite3.connect to the real db file is blocked outright."""
        real_db = os.path.join(paths.APP_DATA_DIR, "sayit.db")
        with self.assertRaises(guard.RealDatabaseAccessError):
            sqlite3.connect(real_db)
        with self.assertRaises(guard.RealDatabaseAccessError):
            sqlite3.connect("file:" + real_db.replace("\\", "/") + "?mode=ro", uri=True)


if __name__ == "__main__":
    unittest.main()
