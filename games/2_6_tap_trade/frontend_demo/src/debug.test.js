import { describe, it, expect } from 'vitest';
import { parseScenario, summarizeLog } from './debug.js';

describe('parseScenario', () => {
	it('parses the sandwich', () => {
		expect(parseScenario('0:+2W 0:0L 0:-2W')).toEqual([
			{ col: 0, row: 2, force: 'W' },
			{ col: 0, row: 0, force: 'L' },
			{ col: 0, row: -2, force: 'W' },
		]);
	});
	it('defaults col to 0 and force to null; accepts commas + lowercase', () => {
		expect(parseScenario('+1, 2:-3l')).toEqual([
			{ col: 0, row: 1, force: null },
			{ col: 2, row: -3, force: 'L' },
		]);
	});
	it('drops garbage tokens', () => {
		expect(parseScenario('xx 0:+1W ::: 5')).toEqual([
			{ col: 0, row: 1, force: 'W' },
			{ col: 0, row: 5, force: null },
		]);
	});
	it('empty input → empty scenario', () => {
		expect(parseScenario('')).toEqual([]);
		expect(parseScenario(null)).toEqual([]);
	});
});

describe('summarizeLog', () => {
	it('counts honesty and teleports', () => {
		const s = summarizeLog({
			reveals: [{ ok: true }, { ok: true }, { ok: false }],
			teleports: [{}],
		});
		expect(s).toEqual({ reveals: 3, honest: 2, violations: 1, teleports: 1 });
	});
});

import { steepestSlope, bandIntervals, detectIncident } from './debug.js';

describe('steepestSlope', () => {
	const tr = [{ t: 0, p: 100, m: 'f' }, { t: 0.1, p: 100.1, m: 'f' }, { t: 0.2, p: 103, m: 'w' }, { t: 0.3, p: 103.1, m: 'w' }];
	it('finds the steepest window and reports its phase', () => {
		const s = steepestSlope(tr, 1);
		expect(s.phase).toBe('w');
		expect(s.slope).toBeCloseTo(29, 0); // 2.9 over 0.1s
	});
	it('null on empty', () => { expect(steepestSlope([], 1)).toBeNull(); });
});

describe('bandIntervals', () => {
	// 2-bet chips are keyed by cell (t1|low), not slot
	const chips = [{ t1: 20, low: 100, high: 100.5 }];
	const trace = [{ t: 19, p: 99 }, { t: 20, p: 100.2 }, { t: 20.5, p: 100.3 }, { t: 21, p: 98 }];
	const reveals = [{ t1: 20, low: 100, price: 100.25, won: true }];
	it('reports enter/exit and inside-at-resolve', () => {
		const rows = bandIntervals(trace, chips, reveals);
		expect(rows[0].enter).toBe(20);
		expect(rows[0].exit).toBe(20.5);
		expect(rows[0].insideAtResolve).toBe(true);
		expect(rows[0].won).toBe(true);
	});
	it('null insideAtResolve when never judged', () => {
		expect(bandIntervals(trace, chips, [])[0].insideAtResolve).toBeNull();
	});
});

describe('detectIncident', () => {
	const steep = [{ t: 0, p: 100, m: 'w' }, { t: 0.1, p: 106, m: 'w' }];
	it('fires above the limit, null below', () => {
		expect(detectIncident(steep, 5, 1)).not.toBeNull();
		expect(detectIncident(steep, 100, 1)).toBeNull();
	});
});
