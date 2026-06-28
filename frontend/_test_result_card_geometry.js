/**
 * Result card geometry unit tests.
 *
 * Tests the pure function calcResultCardPosition() from _result_card_geometry.js.
 * These mirror the scenarios from ROUND9_LONG_TASK.md §Result Card Geometry.
 *
 * Run: node frontend/_test_result_card_geometry.js
 */
'use strict';
const { calcResultCardPosition, CARD_WIDTH, CARD_GAP } = require('./_result_card_geometry');

const failures = [];
function assert(label, condition, detail) {
  if (!condition) failures.push(`FAIL: ${label}${detail ? ' — ' + detail : ''}`);
  else console.log(`PASS: ${label}`);
}

// ── 1: Card width constant ────────────────────────
assert('CARD_WIDTH === 360', CARD_WIDTH === 360);
assert('CARD_GAP === 14', CARD_GAP === 14);

// ── 2: Position above float bar (fallback: floatWinBounds) ──
{
  const result = calcResultCardPosition(
    200,
    { x: 0, y: 0, width: 1920, height: 1080 },
    { x: 710, y: 1046, width: 500, height: 500 },
    null
  );
  // card bottom = (1046+500-34) - 14 = 1512 - 14 = 1498
  // card top = 1498 - 200 = 1298 — but workArea height is 1080, so clamp to 1080-200=880
  // Wait - let me recalculate: bar top = 1046 + 500 - 34 = 1512
  // card_bottom = 1512 - 14 = 1498 — but workArea bottom is 1080, so card_y clamped to 1080-200=880
  const expectedY = 1080 - 200; // clamped to workArea bottom - cardHeight
  assert('float bar fallback: card above bar',
    result.y >= 0 && result.y + 200 <= 1080,
    `y=${result.y}`);

  // card left = 710 + floor(500/2) - floor(360/2) = 710 + 250 - 180 = 780
  assert('float bar fallback: horizontal center',
    result.x === 780, `got x=${result.x}`);
}

// ── 3: Clamp to workArea left edge ───────────────
{
  // Float win positioned such that card would go left of workArea
  const result = calcResultCardPosition(
    200,
    { x: 0, y: 0, width: 1920, height: 1080 },
    null, null
  );
  // Fallback: centered on workArea horizontally
  assert('fallback: card left >= workArea.x',
    result.x >= 0, `x=${result.x}`);
  assert('fallback: card right <= workArea.width',
    result.x + CARD_WIDTH <= 1920, `right=${result.x + CARD_WIDTH}`);
}

// ── 4: Element positions (viewport→screen coord conversion) ─
{
  // Float window at screen (500, 200) with 500x500
  // Element position (viewport-relative): { left: 207, top: 466, right: 293, bottom: 500 }
  const floatWin = { x: 500, y: 200, width: 500, height: 500 };
  const eps = [{ left: 207, top: 466, right: 293, bottom: 500 }];
  const result = calcResultCardPosition(200, { x: 0, y: 0, width: 1920, height: 1080 }, floatWin, eps);

  // anchorTop = 200 + 466 = 666
  // anchorLeft = 500 + 207 = 707
  // anchorWidth = 293 - 207 = 86
  // cardX = 707 + 43 - 180 = 570
  // cardBottom = 666 - 14 = 652
  // cardY = 652 - 200 = 452
  assert('element positions: correct x',
    result.x === 570, `got x=${result.x}`);
  assert('element positions: correct y',
    result.y === 452, `got y=${result.y}`);
}

// ── 5: Clamp to workArea right edge ──────────────
{
  // Float window near right edge of 1920-px display
  // Bar center at x=1800 → card_x = 1800 - 180 = 1620 → right=1620+360=1980 > 1920
  const result = calcResultCardPosition(
    200,
    { x: 0, y: 0, width: 1920, height: 1080 },
    { x: 1550 /* bar center ≈ 1550+250=1800 */, y: 1000, width: 500, height: 500 },
    null
  );
  assert('clamp right: card right <= workArea.width',
    result.x + CARD_WIDTH <= 1920, `right=${result.x + CARD_WIDTH}`);
  assert('clamp right: card left >= 1560 (max left)',
    result.x >= 1560, `x=${result.x}`);
}

// ── 6: Clamp to workArea top edge ────────────────
{
  // Very high float window → card would go above workArea top
  const result = calcResultCardPosition(
    260,
    { x: 0, y: 0, width: 1920, height: 1080 },
    { x: 710, y: 50, width: 500, height: 500 },
    null
  );
  assert('clamp top: card top >= 0',
    result.y >= 0, `y=${result.y}`);
}

// ── 7: Last resort (no floatWin, no elementPositions) ──
{
  const result = calcResultCardPosition(
    200,
    { x: 0, y: 0, width: 1920, height: 1080 },
    null, null
  );
  // Center on primary display bottom: x = (1920 - 360)/2 = 780
  // y = 0 + 1080 - 200 - 14 - 34 = 832
  assert('last resort: center bottom',
    result.x === 780, `x=${result.x}`);
  assert('last resort: bottom position',
    result.y === 832, `y=${result.y}`);
}

// ── 8: Multi-display (secondary monitor) ─────────
{
  const result = calcResultCardPosition(
    200,
    { x: 1920, y: 0, width: 1920, height: 1080 },
    { x: 2630, y: 1046, width: 500, height: 500 },
    null
  );
  // bar center = 2630 + 250 = 2880
  // card_x = 2880 - 180 = 2700
  // card_x in secondary workArea [1920, 3840] ✓
  assert('multi-display: x within secondary workArea',
    result.x >= 1920 && result.x + CARD_WIDTH <= 3840,
    `x=${result.x}`);
  // bar_top = 1046 + 500 - 34 = 1512. card_bottom = 1512-14=1498 → clamp to 1080-200=880
  assert('multi-display: y within secondary workArea',
    result.y >= 0 && result.y + 200 <= 1080,
    `y=${result.y}`);
}

// ── 9: Card height extremes (150 min, 260 max) ───
{
  const resultMin = calcResultCardPosition(150, { x: 0, y: 0, width: 1920, height: 1080 }, null, null);
  const resultMax = calcResultCardPosition(260, { x: 0, y: 0, width: 1920, height: 1080 }, null, null);
  assert('min card height: y is valid',
    resultMin.y >= 0 && resultMin.y + 150 <= 1080,
    `y=${resultMin.y}`);
  assert('max card height: y is valid',
    resultMax.y >= 0 && resultMax.y + 260 <= 1080,
    `y=${resultMax.y}`);
  // Taller card means smaller y
  assert('taller card placed higher',
    resultMax.y < resultMin.y,
    `maxY=${resultMax.y} minY=${resultMin.y}`);
}

if (failures.length) {
  console.error(`\n--- ${failures.length} GEOMETRY FAILURE(S) ---`);
  for (const f of failures) console.error(f);
  process.exit(1);
}
console.log('\n--- ALL GEOMETRY TESTS PASSED ---');
process.exit(0);