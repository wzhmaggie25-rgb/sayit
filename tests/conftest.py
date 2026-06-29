"""Pytest-wide fail-closed guard against opening the real SayIt database.

Round 9.5A incident: a test patched the wrong path symbol and connected to the
real ``%APPDATA%/Sayit/sayit.db``, where ``hw.clear()`` wiped the real personal
dictionary. ``tests/db_safety_guard.py`` only protects tests that opt into
``IsolatedDatabase``. This conftest installs an AUTOMATIC, process-wide guard
that survives per-test path patching, because it intercepts the real connection
boundary (``sqlite3.connect``) rather than only the ``database_path`` helper.

The guard machinery lives in ``tests/db_safety_guard`` so that test modules and
this conftest share the SAME module object (importing conftest directly would
otherwise create a second, divergent copy). Before any real connection — and
therefore before schema migration, CREATE TABLE, INSERT/UPDATE/DELETE, or
``PRAGMA journal_mode`` — the resolved path is checked; any path inside the real
SayIt directory raises ``RealDatabaseAccessError``. ``:memory:`` and temp-dir
databases are allowed. Production code is untouched; the wrap is removed at
session end.
"""
from __future__ import annotations

import pytest

from tests.db_safety_guard import (
    install_global_connect_guard,
    uninstall_global_connect_guard,
)


@pytest.fixture(autouse=True, scope="session")
def _global_real_db_guard():
    """Install the process-wide real-database connection guard for all tests."""
    install_global_connect_guard()
    try:
        yield
    finally:
        uninstall_global_connect_guard()
