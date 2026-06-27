"""Run the frontend result-card offline smoke test via Node.

The smoke test (frontend/_smoke_result_card.js) verifies:
- result-card.html is self-contained (no React/CDN/remote scripts);
- required DOM elements exist;
- the inline script runs without ReferenceError in a sandbox;
- legacy show/close/copyDone globals are wired;
- rapid double-show keeps the latest payload (first-payload-not-lost
  invariant — the same one main.js enforces with did-finish-load replay).
"""
from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SMOKE_JS = PROJECT_ROOT / "frontend" / "_smoke_result_card.js"


class ResultCardSmokeTest(unittest.TestCase):
    def test_smoke_runs_clean(self):
        if not SMOKE_JS.exists():
            self.fail(f"smoke script missing: {SMOKE_JS}")
        node = shutil.which("node")
        if not node:
            self.skipTest("node not available on PATH")
        proc = subprocess.run(
            [node, str(SMOKE_JS)],
            capture_output=True, text=True, timeout=20,
        )
        if proc.returncode != 0:
            self.fail(
                f"result-card smoke test failed (exit {proc.returncode})\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
        self.assertIn("SMOKE TEST PASSED", proc.stdout)


class ResultCardStaticChecks(unittest.TestCase):
    """Backup static checks — run even without Node installed."""

    def setUp(self):
        self.html = (PROJECT_ROOT / "frontend" / "ui" / "result-card.html").read_text(
            encoding="utf-8")

    def test_no_react_dependency(self):
        self.assertNotIn("ReactDOM", self.html)
        self.assertNotIn(" React ", " " + self.html + " ")

    def test_no_external_script(self):
        self.assertNotIn("cdn.jsdelivr.net", self.html)
        self.assertNotIn("unpkg.com", self.html)
        self.assertFalse(
            "<script src=" in self.html.replace(" ", ""),
            "result-card.html must not load any external <script src=...>",
        )

    def test_no_renderer_fetch_to_copy_endpoint(self):
        # Renderer must not POST arbitrary text to the open REST endpoint.
        self.assertNotIn("/api/result-card/copy", self.html)
        self.assertNotIn("/api/result-card/close", self.html)

    def test_required_dom_ids(self):
        for fragment in ('id="copy-btn"', 'id="close-btn"',
                         'id="final-text"', 'id="last-tx"', 'id="check"'):
            self.assertIn(fragment, self.html, fragment)


if __name__ == "__main__":
    unittest.main()
