import { describe, it, expect } from 'vitest';
import { makeMoneyFormat } from './money.js';

describe('makeMoneyFormat', () => {
	it('formats USD', () => {
		const f = makeMoneyFormat('en', 'USD');
		expect(f.full(1234.5)).toBe('$1,234.50');
		expect(f.compact(5)).toBe('$5');
		expect(f.compact(1.4)).toBe('$1.40');
	});
	it('formats EUR', () => {
		const f = makeMoneyFormat('en', 'EUR');
		expect(f.full(20)).toContain('€');
	});
	it('falls back for crypto codes Intl rejects', () => {
		const f = makeMoneyFormat('en', 'BTC1'); // invalid ISO code → RangeError path
		expect(f.compact(2)).toBe('BTC1 2');
		expect(f.full(2)).toBe('BTC1 2.00');
	});
});
