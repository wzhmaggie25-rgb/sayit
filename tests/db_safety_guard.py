"""Reusable hard guard for tests that write to the SQLite Database.

Round 9.5A incident: ``tests/test_silent_learning_integration.py`` patched
``infrastructure.paths.database_path`` instead of the symbol actually bound in
``infrastructure.database`` (``from infrastructure.paths import database_path``).
The real personal dictionary was therefore opened and cleared by ``hw.clear()``.

This module provides a single helper that:

* patches the CORRECT production binding ``infrastructure.database.database_path``
  (and the source ``infrastructure.paths.database_path`` for completeness) so a
  freshly constructed ``Database`` resolves to a per-test temporary file;
* isolates ``ConfigStore`` onto a temporary config path so no real config /
  API key is read;
* resets the ``Database`` and ``ConfigStore`` singletons on enter and exit;
* FAILS CLOSED: if the resolved database path is ever under the real
  ``%APPDATA%/Sayit`` directory, it raises immediately — before any write.

Production code is untouched; only the test process environment is affected.
"""
from __future__ import annotations

import os
import sqlite3
import tempfile
from unittest.mock import patch
from urllib.parse import urlparse, parse_qs

import infrastructure.paths as _paths
import infrastructure.database as _database
import infrastructure.config_store as _config_store


class RealDatabasePathError(AssertionError):
    """Raised when a test would resolve the real application database path."""


class RealDatabaseAccessError(AssertionError):
    """Raised when a test would actually open the real SayIt database."""


# Snapshotted once at import; tests cannot move this by patching a variable.
def _canon(path: str) -> str:
    """Canonicalize a path: abspath + realpath + normcase.

    Defeats Windows case variants, short (8.3) names, symlinks, and junctions
    that could otherwise sneak a real-directory path past the directory check.
    """
    return os.path.normcase(os.path.realpath(os.path.abspath(path)))


REAL_SAYIT_DIR = os.path.abspath(_paths.APP_DATA_DIR)
REAL_SAYIT_DIR_CANON = _canon(_paths.APP_DATA_DIR)
_TEMP_DIR = os.path.abspath(tempfile.gettempdir())

# The genuine sqlite3.connect, captured before any wrapping.
_orig_sqlite_connect = sqlite3.connect


def _resolve_db_filename(database) -> str | None:
    """Return a filesystem path for a sqlite3.connect target, or None for memory."""
    if isinstance(database, bytes):
        try:
            database = database.decode("utf-8", "surrogateescape")
        except Exception:
            return None
    database = os.fspath(database) if hasattr(database, "__fspath__") else database
    if not isinstance(database, str):
        return None
    name = database
    if name.startswith("file:"):
        parsed = urlparse(name)
        q = parse_qs(parsed.query)
        if "mode" in q and "memory" in q["mode"]:
            return None  # in-memory URI
        p = parsed.path
        if os.name == "nt" and p.startswith("/") and len(p) > 2 and p[2] == ":":
            p = p[1:]
        if p in (":memory:", ""):
            return None
        name = p
    if name in (":memory:", ""):
        return None
    return _canon(name)


def _is_under(path: str, directory: str) -> bool:
    """True if canonical ``path`` is inside canonical ``directory``."""
    path = _canon(path)
    directory = _canon(directory)
    try:
        return os.path.commonpath([path, directory]) == directory
    except ValueError:
        return False  # different drives on Windows


def guarded_connect(database, *args, **kwargs):
    """sqlite3.connect wrapper that blocks the real SayIt database directory."""
    resolved = _resolve_db_filename(database)
    if resolved is not None and _is_under(resolved, REAL_SAYIT_DIR_CANON):
        raise RealDatabaseAccessError(
            "Blocked sqlite3.connect to the real SayIt database directory "
            f"{REAL_SAYIT_DIR!r} (resolved path {resolved!r}). Tests must use a "
            "temporary database -- see tests/db_safety_guard.IsolatedDatabase.")
    return _orig_sqlite_connect(database, *args, **kwargs)


def install_global_connect_guard() -> None:
    """Wrap sqlite3.connect process-wide (pytest only). Idempotent."""
    if sqlite3.connect is not guarded_connect:
        sqlite3.connect = guarded_connect


def uninstall_global_connect_guard() -> None:
    """Restore the genuine sqlite3.connect."""
    sqlite3.connect = _orig_sqlite_connect


def is_global_guard_installed() -> bool:
    return sqlite3.connect is guarded_connect


def _real_appdata_dir() -> str:
    return REAL_SAYIT_DIR


def assert_temp_db_path(db_path: str, tmp_root: str) -> None:
    """Fail closed unless ``db_path`` lives inside ``tmp_root`` and not APPDATA."""
    resolved = os.path.abspath(db_path)
    tmp_root = os.path.abspath(tmp_root)
    real_dir = _real_appdata_dir()
    if os.path.commonpath([resolved, real_dir]) == real_dir:
        raise RealDatabasePathError(
            f"Refusing to run: database path {resolved!r} is under the real "
            f"application data directory {real_dir!r}.")
    if os.path.commonpath([resolved, tmp_root]) != tmp_root:
        raise RealDatabasePathError(
            f"Database path {resolved!r} is not inside the test temp dir "
            f"{tmp_root!r}.")


class IsolatedDatabase:
    """Context manager giving a fresh temp Database + isolated ConfigStore.

    Usage::

        with IsolatedDatabase() as iso:
            db = Database()            # resolves to iso.db_path
            ...
    """

    def __init__(self, prefix: str = "sayit-test-db-"):
        self._prefix = prefix
        self._tmpdir = ""
        self.db_path = ""
        self.config_path = ""
        self._patchers: list = []

    def __enter__(self) -> "IsolatedDatabase":
        self._tmpdir = tempfile.mkdtemp(prefix=self._prefix)
        self.db_path = os.path.join(self._tmpdir, "test.db")
        self.config_path = os.path.join(self._tmpdir, "config.json")

        # Reset singletons so the next construction re-reads the patched paths.
        _database.Database._instance = None
        _config_store.ConfigStore._instance = None

        # Patch the CORRECT production binding (the bug was patching only paths).
        self._patchers = [
            patch.object(_database, "database_path", return_value=self.db_path),
            patch.object(_paths, "database_path", return_value=self.db_path),
            patch.object(_config_store, "config_path", return_value=self.config_path),
        ]
        for p in self._patchers:
            p.start()

        # Fail closed BEFORE any write: prove the path is the temp path.
        assert_temp_db_path(_database.database_path(), self._tmpdir)
        return self

    def make_database(self):
        """Construct a Database and assert its real bound path is the temp path."""
        db = _database.Database()
        assert_temp_db_path(db._db_path, self._tmpdir)
        return db

    def __exit__(self, exc_type, exc, tb) -> bool:
        for p in reversed(self._patchers):
            try:
                p.stop()
            except RuntimeError:
                pass
        self._patchers = []
        _database.Database._instance = None
        _config_store.ConfigStore._instance = None
        # Best-effort cleanup of the temp tree (incl. -wal/-shm sidecars).
        try:
            for name in os.listdir(self._tmpdir):
                try:
                    os.remove(os.path.join(self._tmpdir, name))
                except OSError:
                    pass
            os.rmdir(self._tmpdir)
        except OSError:
            pass
        return False
