import { describe, it, expect } from 'vitest';
import { snapGrid, nearestOnGrid, quickPicksFromGrid } from './betGrid.js';

const MONEY = 1000000;
// a Stake-style grid: $0.10 … $2,000
const LEVELS = [0.1, 0.4, 1, 1.4, 2, 5, 7, 8, 14, 20, 40, 50, 100, 150, 200, 400, 500, 1000, 2000]
	.map((v) => v * MONEY);

describe('snapGrid', () => {
	it('converts to display units, clamps and sorts', () => {
		const grid = snapGrid(LEVELS, 1, 1000, MONEY);
		expect(grid[0]).toBe(1);
		expect(grid[grid.length - 1]).toBe(1000);
		expect(grid).not.toContain(0.1);
		expect(grid).not.toContain(2000);
		expect([...grid].sort((a, b) => a - b)).toEqual(grid);
	});
	it('honors operator limits wider than the demo defaults', () => {
		const grid = snapGrid(LEVELS, 0.1, 2000, MONEY);
		expect(grid).toContain(0.1);
		expect(grid).toContain(2000);
	});
	it('returns empty when nothing fits', () => {
		expect(snapGrid(LEVELS, 5000, 9000, MONEY)).toEqual([]);
	});
});

describe('nearestOnGrid', () => {
	const grid = snapGrid(LEVELS, 1, 1000, MONEY);
	it('snaps to the closest rung', () => {
		expect(nearestOnGrid(grid, 6)).toBe(5);
		expect(nearestOnGrid(grid, 7.6)).toBe(8);
		expect(nearestOnGrid(grid, 99999)).toBe(1000);
		expect(nearestOnGrid(grid, 0)).toBe(1);
	});
});

describe('quickPicksFromGrid', () => {
	it('maps the design chips onto the grid, deduped, order kept', () => {
		const grid = snapGrid(LEVELS, 1, 1000, MONEY);
		expect(quickPicksFromGrid(grid, [1, 2, 5, 20])).toEqual([1, 2, 5, 20]);
	});
	it('dedupes when several chips snap to one rung', () => {
		const coarse = [1, 100, 1000].map((v) => v * MONEY);
		const grid = snapGrid(coarse, 1, 1000, MONEY);
		// 1, 2, 5 and 20 are all nearest to the $1 rung on this coarse grid
		expect(quickPicksFromGrid(grid, [1, 2, 5, 20])).toEqual([1]);
		expect(quickPicksFromGrid(grid, [1, 80, 900])).toEqual([1, 100, 1000]);
	});
});
