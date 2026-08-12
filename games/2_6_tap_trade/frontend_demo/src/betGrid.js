// Pure bet-grid helpers — no DOM, no game state. The RGS bet grid is
// authoritative in LIVE mode (off-grid /wallet/play amounts are ERR_VAL),
// so every offered amount must come through these.

// RGS integer betLevels (×money scale) → sorted display-dollar grid,
// clamped to [minB, maxB].
function snapGrid(levels, minB, maxB, money) {
	return levels
		.map(function (v) { return v / money; })
		.filter(function (v) { return v >= minB && v <= maxB; })
		.sort(function (a, b) { return a - b; });
}

function nearestOnGrid(grid, target) {
	return grid.reduce(function (a, b) {
		return Math.abs(b - target) < Math.abs(a - target) ? b : a;
	});
}

// Map the design's quick-chip amounts onto the grid (nearest, deduped,
// order-preserving) — e.g. [1, 2, 5, 20] onto a $0.10–$5,000 operator grid.
function quickPicksFromGrid(grid, desired) {
	var picks = [];
	desired.forEach(function (v) {
		var g = nearestOnGrid(grid, v);
		if (picks.indexOf(g) < 0) picks.push(g);
	});
	return picks;
}

export { snapGrid, nearestOnGrid, quickPicksFromGrid };
