
// ---------------------------------------------------------------- RGS wiring
// LIVE mode: launch with ?rgs_url=https://...&sessionID=...&currency=USD
// Each chip = ONE /wallet/play at that cell's ladder mode (call_<cents>), exactly
// the 2_9/2_10 per-decision-bet pattern. LOCAL mode replays the published LUT odds.
var qs = new URLSearchParams(typeof location !== 'undefined' ? location.search : '');
var RGS_URL  = qs.get('rgs_url') || qs.get('rgsUrl') || '';
// Stake passes rgs_url as a bare host (e.g. "rgsd.stake-engine.com"), no
// scheme — the consumer must supply it. Without this, fetch(RGS_URL + path)
// resolves as a RELATIVE url against the current page instead of an
// absolute cross-origin request, silently hitting the wrong host/path
// (a 405 whose HTML error body then fails response.json()).
if (RGS_URL && !/^https?:\/\//i.test(RGS_URL)) RGS_URL = 'https://' + RGS_URL;
var SESSION  = qs.get('sessionID') || qs.get('session') || '';
var CURRENCY = qs.get('currency') || 'USD';
var LANG     = qs.get('lang') || 'en';
var IS_LIVE  = Boolean(RGS_URL && SESSION);
// LOCAL play-money mode is a dev/review tool, not a production surface:
// available in dev builds always, in production only behind ?demo=1.
var DEMO_OK  = import.meta.env.DEV || qs.get('demo') === '1';
var MONEY = 1000000; // RGS integer money scale

// docs/rgs_docs/RGS.md "Response Codes" — 400s carry {error, message} bodies
// with one of these codes; a bare code (no message) falls back to this map.
var RGS_ERROR_MESSAGES = {
  ERR_VAL: 'Invalid request.', ERR_IPB: 'Insufficient player balance.',
  ERR_IS: 'Invalid or expired session.', ERR_ATE: 'Authentication failed.',
  ERR_GLE: 'Gambling limit exceeded.', ERR_LOC: 'Invalid player location.',
  ERR_GEN: 'Server error, try again.', ERR_MAINTENANCE: 'RGS under maintenance.'
};

function rgs(path, body) {
  return fetch(RGS_URL + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  }).then(function (r) {
    // RGS.md: errors are real HTTP 400/500s that STILL carry a JSON body
    // ({error, message}) — parse it first so that detail isn't discarded
    // in favor of a bare "HTTP 400".
    return r.json().catch(function () { return {}; }).then(function (json) {
      if (!r.ok || json.error) {
        var detail = json.message || (json.error && RGS_ERROR_MESSAGES[json.error]) || json.error;
        var err = new Error('RGS ' + path + ': ' + (detail || ('HTTP ' + r.status)));
        err.code = json.error || null; // machine-readable for fatal-vs-retryable routing
        throw err;
      }
      return json;
    });
  });
}

// A session-level error means no further wallet call can succeed — the game
// must stop and tell the player to relaunch, not keep toasting.
function isFatalRgsError(err) {
  return !!(err && (err.code === 'ERR_IS' || err.code === 'ERR_ATE'));
}

// RGS.md documents balance as {amount, currency}; some responses (or a
// demo mock) may return a bare number instead — accept either, in API
// integer units (caller divides by MONEY). Returns null if absent.
function extractBalance(payload) {
  if (!payload) return null;
  if (payload.balance && typeof payload.balance.amount === 'number') return payload.balance.amount;
  if (typeof payload.balance === 'number') return payload.balance;
  return null;
}

export { SESSION, CURRENCY, LANG, IS_LIVE, DEMO_OK, MONEY, rgs, isFatalRgsError, extractBalance };
