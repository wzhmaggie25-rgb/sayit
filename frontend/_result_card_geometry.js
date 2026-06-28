/**
 * Result card geometry logic — pure function, no Electron dependencies.
 *
 * Extracted from main.js calcResultCardPosition() so it can be unit-tested
 * without launching Electron.
 *
 * Run: node frontend/_test_result_card_geometry.js
 */
'use strict';

const CARD_WIDTH = 360;
const CARD_GAP = 14;

/**
 * Compute result card position — pure function.
 *
 * @param {number} cardHeight  Estimated card height (150-260)
 * @param {object} workArea    { x, y, width, height } — display work area
 * @param {object|null} floatWinBounds { x, y, width, height } — float window bounds (may be unusable)
 * @param {Array|null} elementPositions  Array of { left, top, right, bottom } from float renderer
 * @returns {{ x: number, y: number }}
 */
function calcResultCardPosition(cardHeight, workArea, floatWinBounds, elementPositions) {
  if (!workArea) throw new Error('workArea is required');

  let anchorTop, anchorLeft, anchorWidth;

  if (Array.isArray(elementPositions) && elementPositions.length > 0) {
    // Use first element position (viewport-relative) + float window screen origin
    const fb = floatWinBounds;
    const ep = elementPositions[0];
    anchorTop  = fb.y + ep.top;
    anchorLeft = fb.x + ep.left;
    anchorWidth = ep.right - ep.left;
  } else if (floatWinBounds && floatWinBounds.width > 0 && floatWinBounds.height > 0) {
    // Fallback: estimate visible bar at bottom of float window
    const fb = floatWinBounds;
    const barHeight = 34;
    const barWidth = 86;
    anchorTop   = fb.y + fb.height - barHeight;
    anchorLeft  = fb.x + Math.floor((fb.width - barWidth) / 2);
    anchorWidth = barWidth;
  } else {
    // Last resort: center on primary display bottom
    const wa = workArea;
    return {
      x: Math.floor(wa.x + (wa.width - CARD_WIDTH) / 2),
      y: Math.floor(wa.y + wa.height - cardHeight - CARD_GAP - 34),
    };
  }

  // Horizontal center on anchor, clamp to workArea
  let cardX = Math.floor(anchorLeft + (anchorWidth / 2) - (CARD_WIDTH / 2));
  cardX = Math.max(workArea.x, Math.min(cardX, workArea.x + workArea.width - CARD_WIDTH));

  // Vertical: card bottom edge CARD_GAP above anchor top, clamp
  const cardBottom = anchorTop - CARD_GAP;
  let cardY = cardBottom - cardHeight;
  cardY = Math.max(workArea.y, Math.min(cardY, workArea.y + workArea.height - cardHeight));

  return { x: cardX, y: cardY };
}

module.exports = { calcResultCardPosition, CARD_WIDTH, CARD_GAP };