// Currency-aware money formatting. The launch params carry the wallet
// currency (?currency=EUR etc.) — hardcoding "$" misstates real balances.
// Intl handles fiat; crypto codes (BTC, LTC, …) throw RangeError and fall
// back to a "CODE 1.23" prefix format.

function makeMoneyFormat(lang, currency) {
	try {
		var full = new Intl.NumberFormat(lang, {
			style: 'currency', currency: currency,
		});
		var compact = new Intl.NumberFormat(lang, {
			style: 'currency', currency: currency,
			minimumFractionDigits: 0, maximumFractionDigits: 2,
		});
		return {
			full: function (v) { return full.format(v); },
			// whole amounts drop the decimals ($5); fractional keep both ($1.40, not $1.4)
			compact: function (v) { return v % 1 === 0 ? compact.format(v) : full.format(v); },
		};
	} catch (e) {
		var sym = currency === 'USD' ? '$' : currency + ' ';
		return {
			full: function (v) {
				return sym + v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
			},
			compact: function (v) {
				return sym + (v % 1 === 0 ? v.toLocaleString('en-US') : v.toFixed(2));
			},
		};
	}
}

export { makeMoneyFormat };
