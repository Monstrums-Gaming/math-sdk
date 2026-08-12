import { describe, it, expect } from 'vitest';
import { extractBalance, isFatalRgsError } from './rgs.js';

describe('extractBalance', () => {
	it('reads the documented {amount, currency} shape', () => {
		expect(extractBalance({ balance: { amount: 2000000000, currency: 'USD' } })).toBe(2000000000);
	});
	it('accepts a bare number (mock shape)', () => {
		expect(extractBalance({ balance: 1000000 })).toBe(1000000);
	});
	it('returns null when absent', () => {
		expect(extractBalance({})).toBeNull();
		expect(extractBalance(null)).toBeNull();
	});
});

describe('isFatalRgsError', () => {
	it('flags session-level codes only', () => {
		const is = new Error('x'); is.code = 'ERR_IS';
		const ate = new Error('x'); ate.code = 'ERR_ATE';
		const val = new Error('x'); val.code = 'ERR_VAL';
		expect(isFatalRgsError(is)).toBe(true);
		expect(isFatalRgsError(ate)).toBe(true);
		expect(isFatalRgsError(val)).toBe(false);
		expect(isFatalRgsError(new Error('plain'))).toBe(false);
	});
});
