"""Phase 1 tests: result card geometry (size + position).

Verifies the real production function calcResultCardPosition() extracted from
main.js into frontend/_result_card_geometry.js.

Test approach
-------------
The pure function is tested in two ways:
1. Node harness (_test_result_card_geometry.js) — exercises all position
   scenarios (float bar fallback, element positions, clamping, multi-display).
2. Python smoke tests — run existing Node smoke + verify syntax.

Previously this file contained constant-only tests (assert CARD_WIDTH==360)
that did not validate any production code. Those have been replaced.
"""
from __future__ import annotations

import os
import subprocess
import unittest


class ResultCardGeometryTests(unittest.TestCase):
    """Result card geometry is production code in frontend/main.js.

    The real calcResultCardPosition() function has been extracted into
    a pure-function module frontend/_result_card_geometry.js and tested
    via Node harness at frontend/_test_result_card_geometry.js.

    These Python tests verify the harness passes and run smoke checks.
    """

    REPO_ROOT = os.path.normpath(
        os.path.join(os.path.dirname(__file__), ".."))

    def test_geometry_via_node_harness(self):
        """Run Node harness for result card geometry.

        The harness tests all 9 scenarios:
        - card width/gap constants
        - float bar fallback positioning
        - element positions (viewport→screen coord)
        - workArea clamping (left, right, top)
        - last-resort center-bottom fallback
        - multi-display positioning
        - min/max card height
        """
        harness = os.path.join(self.REPO_ROOT, "frontend",
                               "_test_result_card_geometry.js")
        self.assertTrue(os.path.exists(harness),
                        "Geometry test harness must exist")
        result = subprocess.run(
            ["node", harness],
            capture_output=True, text=True,
            cwd=self.REPO_ROOT, timeout=30)
        self.assertEqual(
            result.returncode, 0,
            f"Geometry harness failed:\n{result.stdout}\n{result.stderr}")

    def test_main_js_calc_result_card_position_exists(self):
        """main.js must define calcResultCardPosition."""
        main_js = os.path.join(self.REPO_ROOT, "frontend", "main.js")
        self.assertTrue(os.path.exists(main_js))
        with open(main_js, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("function calcResultCardPosition", content,
                      "main.js must define calcResultCardPosition")

    def test_main_js_syntax(self):
        """frontend/main.js must pass Node syntax check."""
        result = subprocess.run(
            ["node", "--check", "frontend/main.js"],
            capture_output=True, text=True,
            cwd=self.REPO_ROOT)
        self.assertEqual(
            result.returncode, 0,
            f"main.js syntax error: {result.stderr}")

    def test_smoke_result_card(self):
        """frontend/_smoke_result_card.js must pass."""
        harness = os.path.join(self.REPO_ROOT, "frontend",
                               "_smoke_result_card.js")
        result = subprocess.run(
            ["node", harness],
            capture_output=True, text=True,
            cwd=self.REPO_ROOT, timeout=30)
        self.assertEqual(
            result.returncode, 0,
            f"Smoke result card failed:\n{result.stdout}\n{result.stderr}")


if __name__ == "__main__":
    unittest.main()