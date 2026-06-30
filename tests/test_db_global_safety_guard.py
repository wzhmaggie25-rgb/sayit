"""Proof tests for the pytest-wide real-database guard.

These prove the automatic guard (installed by tests/conftest.py via
tests/db_safety_guard) blocks any test from opening or migrating the real SayIt
database, even when a test patches the wrong path symbol, and that legitimate
temporary databases still work. The real sayit.db is never opened.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sqlite3
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch

import infrastructure.paths as paths
import infrastructure.database as dbmod
from tests import db_safety_guard as guard
from tests.db_safety_guard import IsolatedDatabase


def _real_db_fingerprint():
    """Filesystem-only fingerprint of the real DB (never opened via SQLite)."""
    real_db = os.path.join(paths.APP_DATA_DIR, "sayit.db")
    if not os.path.exists(real_db):
        return None
    st = os.stat(real_db)
    with open(real_db, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    return (digest, st.st_size, int(st.st_mtime_ns))


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

    def test_windows_case_variant_real_path_blocked(self):
        """Case-variant / non-canonical real paths are still blocked because the
        guard canonicalizes with abspath+realpath+normcase before comparing."""
        real_db = os.path.join(paths.APP_DATA_DIR, "sayit.db")
        variants = [real_db.upper(), real_db.lower()]
        if "\\" in real_db:
            variants.append(real_db.replace("\\", "/"))
        # Also exercise a redundant-separator variant.
        variants.append(os.path.join(paths.APP_DATA_DIR, ".", "sayit.db"))
        for v in variants:
            with self.subTest(variant=v):
                with self.assertRaises(guard.RealDatabaseAccessError):
                    sqlite3.connect(v)

    def test_collection_time_real_db_access_blocked_in_subprocess(self):
        """A test module that opens the real DB at IMPORT/collection time must
        be blocked during collection, before the genuine sqlite3.connect runs,
        and the real DB file must remain unchanged.

        Runs a child pytest so the failure happens at collection time in a clean
        process (the parent's guard is already installed)."""
        before = _real_db_fingerprint()
        real_db = os.path.join(paths.APP_DATA_DIR, "sayit.db")
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        tmpdir = tempfile.mkdtemp(prefix="sayit-collect-", dir=os.path.join(repo_root, "tests"))
        mod_path = os.path.join(tmpdir, "test_collection_time_real_db_probe.py")
        # Module-level (import-time) real-DB access — happens during collection.
        module_src = textwrap.dedent(f"""
            import sqlite3
            # Executed at import/collection time, before any fixture runs.
            sqlite3.connect(r{real_db!r})

            def test_placeholder():
                assert True
        """)
        with open(mod_path, "w", encoding="utf-8") as f:
            f.write(module_src)
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", os.path.relpath(mod_path, repo_root),
                 "-p", "no:cacheprovider", "--co", "-q"],
                cwd=repo_root, capture_output=True, text=True, timeout=120)
            combined = proc.stdout + proc.stderr
            self.assertNotEqual(proc.returncode, 0,
                                f"Collection should fail. Output:\n{combined}")
            self.assertIn("RealDatabaseAccessError", combined,
                          f"Expected guard error during collection. Output:\n{combined}")
        finally:
            try:
                os.remove(mod_path)
            except OSError:
                pass
            for name in os.listdir(tmpdir):
                try:
                    os.remove(os.path.join(tmpdir, name))
                except OSError:
                    pass
            try:
                os.rmdir(tmpdir)
            except OSError:
                pass
        after = _real_db_fingerprint()
        self.assertEqual(before, after,
                         "Real DB fingerprint changed during collection-time probe")


if __name__ == "__main__":
    unittest.main()
