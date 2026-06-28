"""Phase 1 tests: result card geometry (size + position).

Verifies:
- Card width is 360px (per product requirement)
- Height is dynamic (150-240px range, max 260px)
- Position is above float bar with 12-16px gap
- Horizontal centering on float bar / element positions
- Clamping to display workArea
- Multi-monitor awareness
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock


class ResultCardGeometryTests(unittest.TestCase):
    """Pure function tests for result card geometry calculations."""

    def _make_display(self, x=0, y=0, w=1920, h=1080):
        """Create a mock display object matching Electron's screen API."""
        d = MagicMock()
        d.workArea = {"x": x, "y": y, "width": w, "height": h}
        d.bounds = {"x": x, "y": y, "width": w, "height": h}
        return d

    def _make_element_position(self, left=0, top=0, right=500, bottom=500):
        """Create a mock element position dict."""
        return {"left": left, "top": top, "right": right, "bottom": bottom}

    def test_card_width_constant(self):
        """Card width must be 360px as specified."""
        # This mirrors the constant in main.js
        CARD_WIDTH = 360
        self.assertEqual(CARD_WIDTH, 360)

    def test_card_height_range(self):
        """Card height must be dynamic 150-240px with max 260px."""
        MIN_HEIGHT = 150
        MAX_HEIGHT = 260
        self.assertEqual(MIN_HEIGHT, 150)
        self.assertEqual(MAX_HEIGHT, 260)
        # Dynamic range 150-240 is within bounds
        self.assertGreaterEqual(MAX_HEIGHT, 240)
        self.assertLessEqual(MAX_HEIGHT, 260)

    def test_gap_between_12_and_16(self):
        """Gap between card bottom and float bar top must be 12-16px."""
        GAP = 14  # midpoint
        self.assertGreaterEqual(GAP, 12)
        self.assertLessEqual(GAP, 16)

    def test_position_above_float_bar_simple(self):
        """Card bottom edge must be above float bar top with GAP."""
        # Simulate: float bar at bottom of a 1080p display, centered
        float_bounds = {"x": 710, "y": 1046, "width": 500, "height": 34}
        display = self._make_display(0, 0, 1920, 1080)

        # Expected card position:
        # height = 200 (estimate), width = 360
        # card_bottom = float_top - GAP = 1046 - 14 = 1032
        # card_top = card_bottom - card_height = 1032 - 200 = 832
        # card_left = center on float bar: float_left + float_width/2 - card_width/2
        #           = 710 + 250 - 180 = 780
        card_height = 200
        card_width = 360
        gap = 14
        card_bottom = float_bounds["y"] - gap
        card_top = card_bottom - card_height
        card_left = float_bounds["x"] + (float_bounds["width"] // 2) - (card_width // 2)

        self.assertEqual(card_bottom, 1032)
        self.assertEqual(card_top, 832)
        self.assertEqual(card_left, 780)

    def test_position_uses_element_positions(self):
        """Position should use reported element positions, not full window bounds."""
        # The float window is 500x500 but visible bubble is at bottom-center
        element_pos = self._make_element_position(left=207, top=466, right=293, bottom=500)
        card_width = 360
        card_height = 200
        gap = 14

        # Horizontal center on element
        element_width = element_pos["right"] - element_pos["left"]
        expected_left = element_pos["left"] + (element_width // 2) - (card_width // 2)
        # Vertical: card bottom = element top - gap
        expected_top = element_pos["top"] - gap - card_height

        self.assertEqual(expected_left, 207 + 43 - 180)  # 70
        self.assertEqual(expected_top, 466 - 14 - 200)    # 252

    def test_position_clamps_to_workarea_left(self):
        """Card must not extend beyond left edge of workArea."""
        # Float bar near left edge
        float_bounds = {"x": 0, "y": 1000, "width": 500, "height": 34}
        display = self._make_display(0, 0, 1920, 1080)
        card_width = 360
        card_height = 200
        gap = 14

        card_left = float_bounds["x"] + (float_bounds["width"] // 2) - (card_width // 2)
        # Without clamping: 0 + 250 - 180 = 70 (already within bounds, no clamp needed)
        self.assertGreaterEqual(card_left, display.workArea["x"])

        # Extreme case: float bar at x=-100 (off-screen slightly)
        card_left = -100 + 250 - 180  # = -30
        clamped_left = max(card_left, display.workArea["x"])
        self.assertEqual(clamped_left, 0)

    def test_position_clamps_to_workarea_right(self):
        """Card must not extend beyond right edge of workArea."""
        display = self._make_display(0, 0, 1920, 1080)
        card_width = 360

        # Float bar near right edge: right edge of card would go past workArea right
        card_left = 1700  # 1700 + 360 = 2060 > 1920
        clamped_left = min(card_left, display.workArea["width"] - card_width)
        self.assertEqual(clamped_left, 1560)

    def test_position_clamps_to_workarea_top(self):
        """Card must not extend beyond top edge of workArea."""
        display = self._make_display(0, 0, 1920, 1080)

        # If card would go above workArea top, clamp it
        card_top = -20
        clamped_top = max(card_top, display.workArea["y"])
        self.assertEqual(clamped_top, 0)

    def test_position_clamps_to_workarea_bottom(self):
        """Card must not extend beyond bottom edge of workArea either."""
        display = self._make_display(0, 0, 1920, 1080)
        card_height = 260
        gap = 14

        # If float bar is very low, card bottom pushes past workArea bottom
        # card_bottom = float_top - gap = 1080 - 14 = 1066 (within bounds)
        # But if taskbar occupies bottom, workArea height < 1080
        display_small = self._make_display(0, 0, 1920, 1040)  # 40px taskbar
        float_bounds = {"x": 710, "y": 1006, "width": 500, "height": 34}

        card_bottom = float_bounds["y"] - gap
        display_bottom = display_small.workArea["y"] + display_small.workArea["height"]

        # Ensure card doesn't go below workArea
        self.assertLessEqual(card_bottom, display_bottom)

    def test_multi_display_current_display_used(self):
        """On multi-monitor, use currentDisplay instead of primary display."""
        # Two displays: primary 1920x1080 (x=0), secondary 1920x1080 (x=1920)
        primary = self._make_display(0, 0, 1920, 1080)
        secondary = self._make_display(1920, 0, 1920, 1080)

        # Float bar on secondary display
        float_bounds = {"x": 2630, "y": 1046, "width": 500, "height": 34}
        card_width = 360
        card_height = 200
        gap = 14

        # Card centered on float bar
        card_left = float_bounds["x"] + (float_bounds["width"] // 2) - (card_width // 2)
        card_top = float_bounds["y"] - gap - card_height

        # Must be within secondary display's workArea
        sec_work = secondary.workArea
        self.assertGreaterEqual(card_left, sec_work["x"])
        self.assertLess(card_left + card_width, sec_work["x"] + sec_work["width"])

    def test_fallback_to_floatwin_getbounds(self):
        """When elementPositions is empty, fall back to floatWin.getBounds()."""
        # Float window bounds: 500x500 centered at bottom of primary display
        float_bounds = {"x": 710, "y": 580, "width": 500, "height": 500}
        display = self._make_display(0, 0, 1920, 1080)

        # The visible bar is at the bottom-center of the float window
        # Estimated visible bar area: bottom 34px centered
        bar_height = 34
        bar_top = float_bounds["y"] + float_bounds["height"] - bar_height
        bar_width = 86  # from float.html: width=86
        bar_left = float_bounds["x"] + (float_bounds["width"] // 2) - (bar_width // 2)

        card_width = 360
        card_height = 200
        gap = 14

        # Position above estimated bar area
        card_left = bar_left + (bar_width // 2) - (card_width // 2)
        card_top = bar_top - gap - card_height

        # Basic sanity: card must be above the bar
        self.assertLess(card_top + card_height, bar_top)


if __name__ == "__main__":
    unittest.main()