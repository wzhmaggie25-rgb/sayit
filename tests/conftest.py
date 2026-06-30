"""Pytest-wide fail-closed guard against opening the real SayIt database.

Round 9.5A incident: a test patched the wrong path symbol and connected to the
real ``%APPDATA%/Sayit/sayit.db``, where ``hw.clear()`` wiped the real personal
dictionary. ``tests/db_safety_guard.py`` only protects tests that opt into
``IsolatedDatabase``. This conftest installs an AUTOMATIC, process-wide guard
that survives per-test path patching, because it intercepts the real connection
boundary (``sqlite3.connect``) rather than only the ``database_path`` helper.

COLLECTION-TIME COVERAGE: a session-scoped autouse fixture only runs after
collection, so a test module could reach the real database at import/collection
time before the guard is active. To close that gap, the guard is installed
**immediately when this root conftest is imported** (before any test module is
collected) and again in ``pytest_configure`` (idempotent). It is removed in
``pytest_unconfigure``. The guard machinery lives in ``tests/db_safety_guard`` so
test modules and this conftest share the SAME module object.
"""
from __future__ import annotations

from tests.db_safety_guard import (
    install_global_connect_guard,
    uninstall_global_connect_guard,
)

# Install at conftest import time — this happens before pytest collects/imports
# any test module, so module-import-time Database() access is already guarded.
install_global_connect_guard()


def pytest_configure(config):
    """Re-assert the guard during configuration (idempotent)."""
    install_global_connect_guard()


def pytest_unconfigure(config):
    """Restore the genuine sqlite3.connect at the end of the session."""
    uninstall_global_connect_guard()
