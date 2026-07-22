import './style.css';
import './splash.js';
import { SESSION, CURRENCY, LANG, IS_LIVE, DEMO_OK, MONEY, rgs, isFatalRgsError, extractBalance } from './rgs.js';
import { CFG, MONO } from './config.js';
import { THEMES, THEME_ORDER, COLOR, applyTheme } from './themes.js';
import { snapGrid, nearestOnGrid, quickPicksFromGrid } from './betGrid.js';
import { makeMoneyFormat } from './money.js';

var REDUCED = matchMedia('(prefers-reduced-motion: reduce)').matches;

// ---------------------------------------------------------------- state

var canvas = document.getElementById('game');
var ctx = canvas.getContext('2d');
var W = 0, H = 0, DPR = 1;

var LADDER = null;
var simTime = 0, viewTime = 0;
var startEpochMs = Date.now();
var price = CFG.startPrice, vel = 0, volEst = 0.5, dispPrice = CFG.startPrice;
var anchor = CFG.startPrice;
var history = [];
var camPrice = CFG.startPrice;

var balance = CFG.startBalance;
var betSize = 5;
var bets = [];                // {t1,t2,low,high,stake,mult,modeKey,outcome,state,stateAge,missTarget}
var floats = [];              // {x,y,text,kind:'win'|'loss',age}
var rejects = [];             // {t1,low,age} — red flash on an invalid tap
var mouse = { x: -1, y: -1, inside: false };
var betChain = Promise.resolve();  // serializes RGS rounds (one active round per session)
var rgsBalance = null;             // LIVE: latest AUTHORITATIVE server balance (display units).
                                   // Updated as each round settles through betChain (serialized,
                                   // so the last-settled round carries the current server truth);
                                   // the pill reconciles to it only when no chips are in flight.
var gaussSpare = null;

var COARSE = matchMedia('(pointer: coarse)').matches;
var armed = null;                 // touch flow: first tap arms a cell, second confirms
var zoom = 1;                     // chart zoom — scales pixels-per-unit only, never the odds
var speedMult = 1;                // settings: game-speed multiplier over CFG.timeScale (1 / 1.5 / 2)
var tapConfirm = COARSE;          // settings: two-tap confirm (any pointer; defaults on for touch)
try {
  var storedSpeed = parseFloat(localStorage.getItem('taptrade.speed'));
  if (storedSpeed === 1 || storedSpeed === 1.5 || storedSpeed === 2) speedMult = storedSpeed;
  var storedTap = localStorage.getItem('taptrade.tapConfirm');
  if (storedTap !== null) tapConfirm = storedTap === '1';
} catch (e) { /* ignore */ }
var pinch = null;                 // {dist, zoom} — an active two-finger pinch
var pinchGuard = 0;               // timestamp of the last pinch end (swallows the ghost tap)
var histEntries = [];             // resolved bets, newest first: {ts, stake, mult, won, payout, shot, cell, line}
var HIST_CAP = 24;                // in-memory only — the JPEG landing shots are too big for localStorage
var shotCanvas = null, shotCtx = null;   // lazy offscreen canvas for landing-shot capture
var vignette = null;              // {age} — screen-edge flash for epic (>=20x) wins
var sessionPL = 0;                // net profit/loss since load
var results = [];                 // last 8 resolutions, newest first: {w, amt}

// ---------------------------------------------------------------- utils

function gauss() {
  if (gaussSpare !== null) { var s = gaussSpare; gaussSpare = null; return s; }
  var u = 0, v = 0;
  while (u === 0) u = Math.random();
  while (v === 0) v = Math.random();
  var r = Math.sqrt(-2 * Math.log(u));
  gaussSpare = r * Math.sin(2 * Math.PI * v);
  return r * Math.cos(2 * Math.PI * v);
}

function phi(x) {
  var sign = x < 0 ? -1 : 1;
  x = Math.abs(x) / Math.SQRT2;
  var t = 1 / (1 + 0.3275911 * x);
  var y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-x * x);
  return 0.5 * (1 + sign * y);
}

var MONEYFMT = makeMoneyFormat(LANG, CURRENCY);
function fmtMoney(v) { return MONEYFMT.full(v); }
function fmtAmt(v) { return MONEYFMT.compact(v); }
function fmtMult(m) { return (m >= 10 ? m.toFixed(0) : m.toFixed(1)) + 'x'; }
function fmtClock(t) {
  var d = new Date(startEpochMs + t * 1000);
  var h = d.getHours(), mi = d.getMinutes(), s = d.getSeconds();
  var ap = h >= 12 ? 'PM' : 'AM'; h = h % 12 || 12;
  var two = function (n) { return (n < 10 ? '0' : '') + n; };
  return two(h) + ':' + two(mi) + ':' + two(s) + ' ' + ap;
}

function setBalance(v) {
  balance = v;
  document.getElementById('balanceValue').textContent = fmtMoney(balance);
}

// Inline stroke icons (no emoji) — currentColor so they inherit theme + toast tint.
var ICON_CHECK = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>';
var ICON_WARN = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>';

function toast(text, kind, ttlSec) {
  var el = document.createElement('div');
  el.className = 'toast ' + (kind || '');
  var iconHtml = kind === 'win' ? ICON_CHECK : kind === 'warn' ? ICON_WARN : '';
  el.innerHTML = (iconHtml ? '<span class="icon">' + iconHtml + '</span>' : '') +
    '<span>' + text.replace(/&/g, '&amp;').replace(/</g, '&lt;') + '</span>';
  el.style.setProperty('--ttl', (ttlSec || 2.2) + 's');
  document.getElementById('toastContainer').appendChild(el);
  setTimeout(function () { el.remove(); }, ((ttlSec || 2.2) + 0.4) * 1000);
}

// ---------------------------------------------------------------- sound (synth, no assets)

var muted = false;
try { muted = localStorage.getItem('taptrade.muted') === '1'; } catch (e) { /* ignore */ }
var audioCtx = null;

function synthNote(freq, t0, dur, type, gain) {
  var o = audioCtx.createOscillator(), g = audioCtx.createGain();
  o.type = type; o.frequency.value = freq;
  var at = audioCtx.currentTime + t0;
  g.gain.setValueAtTime(gain, at);
  g.gain.exponentialRampToValueAtTime(0.0001, at + dur);
  o.connect(g).connect(audioCtx.destination);
  o.start(at); o.stop(at + dur + 0.02);
}

function sound(kind, tier) {
  if (muted) return;
  try {
    // lazily created — first call always follows a user gesture (a click)
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    if (audioCtx.state === 'suspended') audioCtx.resume();
    if (kind === 'place') synthNote(2500, 0, 0.04, 'square', 0.05);
    else if (kind === 'loss') synthNote(120, 0, 0.14, 'sine', 0.12);
    else if (kind === 'win') {
      var notes = tier >= 2 ? [660, 990, 1320, 1760]
                : tier === 1 ? [660, 990, 1320] : [660, 990];
      for (var i = 0; i < notes.length; i++) synthNote(notes[i], i * 0.09, 0.18, 'triangle', 0.08);
    }
  } catch (e) { /* audio unavailable — stay silent */ }
}

// ---------------------------------------------------------------- session strip + hint

var stripShown = false;
function updateStrip() {
  var strip = document.getElementById('sessionStrip');
  if (!stripShown) {
    if (!results.length && !bets.length) return;
    stripShown = true;
    strip.classList.add('show');
  }
  var pl = document.getElementById('plValue');
  pl.textContent = (sessionPL >= 0 ? '+' : '−') + fmtMoney(Math.abs(sessionPL));
  pl.className = 'pl ' + (sessionPL >= 0 ? 'up' : 'down');
  var live = bets.filter(function (b) {
    return b.state === 'pending' || b.state === 'active' || b.state === 'hot';
  });
  var risk = live.reduce(function (a, b) { return a + b.stake; }, 0);
  document.getElementById('riskValue').textContent = live.length
    ? fmtAmt(risk) + ' in play · ' + live.length + (live.length === 1 ? ' chip' : ' chips')
    : 'nothing in play';
  document.getElementById('tickerPips').innerHTML = results.map(function (r) {
    return '<span class="pip ' + (r.w ? 'w' : 'l') + '">' + (r.w ? '+' : '−') + fmtAmt(r.amt) + '</span>';
  }).join('');
}

function recordResult(won, amt) {
  results.unshift({ w: won, amt: amt });
  if (results.length > 8) results.pop();
  updateStrip();
}

var hintEl = document.getElementById('hint');
try { if (localStorage.getItem('taptrade.seenHint') === '1') hintEl.style.display = 'none'; } catch (e) { /* ignore */ }
function dismissHint() {
  if (!hintEl) return;
  hintEl.classList.add('gone');
  try { localStorage.setItem('taptrade.seenHint', '1'); } catch (e) { /* ignore */ }
  var el = hintEl; hintEl = null;
  setTimeout(function () { el.remove(); }, 900);
}

// ---------------------------------------------------------------- odds bundle + session

var authReady = !IS_LIVE;   // LIVE: no bets until the session is validated
var fatal = false;          // a blocking failure — the wallet path is stopped

// Blocking error overlay: unlike a toast, the game cannot look playable when
// no wallet call can succeed. Reload is the default recovery; a retry callback
// replaces it for transient asset failures.
function fatalError(message, opts) {
  opts = opts || {};
  if (fatal) return; // first failure wins
  fatal = true;
  authReady = false;
  var modal = document.getElementById('fatalModal');
  document.getElementById('fatalMsg').textContent = message;
  var retryBtn = document.getElementById('fatalRetry');
  retryBtn.style.display = opts.retry ? '' : 'none';
  retryBtn.onclick = opts.retry ? function () {
    modal.classList.remove('open');
    modal.setAttribute('aria-hidden', 'true');
    fatal = false;
    opts.retry();
  } : null;
  document.getElementById('fatalReload').style.display = opts.reload === false ? 'none' : '';
  modal.classList.add('open');
  modal.setAttribute('aria-hidden', 'false');
}
document.getElementById('fatalReload').addEventListener('click', function () { location.reload(); });

// /wallet/end-round with backoff — a failed release leaves the round open
// server-side, and rounds are serial: an open round blocks the whole session.
function endRoundWithRetry(attempts) {
  return rgs('/wallet/end-round', { sessionID: SESSION }).catch(function (err) {
    if (isFatalRgsError(err) || attempts <= 1) throw err;
    return new Promise(function (r) { setTimeout(r, 900); })
      .then(function () { return endRoundWithRetry(attempts - 1); });
  });
}

function startSession() {
  var bd = document.getElementById('modeBadge');
  bd.textContent = 'LIVE'; bd.classList.add('live');
  rgs('/wallet/authenticate', { sessionID: SESSION }).then(function (res) {
    var bal = extractBalance(res);
    if (bal !== null) { rgsBalance = bal / MONEY; setBalance(rgsBalance); }
    // config is authoritative: bet grid (off-grid /wallet/play is ERR_VAL),
    // min/max/default, and jurisdiction flags.
    if (res.config) applyBetConfig(res.config);
    if (res.config && res.config.jurisdiction) applyJurisdiction(res.config.jurisdiction);
    // Resume: an unfinished round from a previous visit blocks every future
    // /wallet/play. Books are position-neutral — no cell to repaint — so
    // settle silently and report the recovered outcome.
    if (res.round && res.round.active) {
      return endRoundWithRetry(3).then(function (end) {
        var b2 = extractBalance(end);
        if (b2 !== null) { rgsBalance = b2 / MONEY; setBalance(rgsBalance); }
        var payout = typeof res.round.payout === 'number' ? res.round.payout / MONEY : 0;
        toast(payout > 0 ? 'Last round settled: +' + fmtAmt(payout) : 'Last round settled',
              payout > 0 ? 'win' : '', 3.2);
      });
    }
  }).then(function () {
    authReady = true;
  }).catch(function (err) {
    var detail = err && err.message ? ' — ' + err.message.replace(/\.$/, '') : '';
    fatalError('Could not start the game session' + detail + '. Relaunch the game from the casino.');
  });
}

function loadOdds() {
  fetch('tap_trade_rgs.json').then(function (r) {
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  }).then(function (b) {
    LADDER = Object.keys(b.modes).map(function (k) {
      var m = b.modes[k];
      return { modeKey: k, multiplier: m.multiplier, cents: m.multiplierCents,
               winChance: m.winChance, outcomes: m.outcomes };
    }).sort(function (a, c) { return a.cents - c.cents; });
    if (IS_LIVE) startSession();
  }).catch(function () {
    fatalError('Could not load the game odds.', { retry: loadOdds });
  });
}
// LOCAL play-money is a dev/review surface only — in a production build it
// must be explicit (?demo=1), never a silent fallback for a broken launch.
if (!IS_LIVE && !DEMO_OK) {
  fatalError('This game must be launched from the casino.', { reload: false });
}
loadOdds();

// Brand art, inlined so its classed paths take the theme's CSS vars and
// recolor on theme change for free. Purely decorative — skip silently on error.
function inlineSvg(url, elId) {
  fetch(url).then(function (r) { return r.ok ? r.text() : ''; }).then(function (svg) {
    if (svg.indexOf('<svg') === 0) document.getElementById(elId).innerHTML = svg;
  }).catch(function () { /* decorative only */ });
}
inlineSvg('juice_logo.svg', 'brand');       // .lf face → --accent, .ls extrusion → --loss
inlineSvg('tap_trade_logo.svg', 'gameTitle'); // plate → --panel, TAP → --text, TRADE → --accent, marks → --gain

// The cell's displayed multiplier: fair pricing from the local vol model, snapped
// to the nearest ladder rung (log space) so every offered value is a real,
// published bet mode. True odds always come from the mode, never from this model.
function cellRung(low, high, t1, t2) {
  if (!LADDER) return null;
  var tMid = Math.max(0.5, (t1 + t2) / 2 - simTime);
  var s = volEst * Math.sqrt(tMid);
  var p = (phi((high - price) / s) - phi((low - price) / s)) * 1.55;
  p = Math.min(0.95, Math.max(0.0098, p));
  var fair = (1 - CFG.houseEdge) / p;
  var best = LADDER[0], bestD = Infinity;
  for (var i = 0; i < LADDER.length; i++) {
    var d = Math.abs(Math.log(LADDER[i].multiplier) - Math.log(fair));
    if (d < bestD) { bestD = d; best = LADDER[i]; }
  }
  return best;
}

// ---------------------------------------------------------------- outcome resolution

// Balance display is deferred to the REVEAL (the line reaching the cell) so the
// wallet movement never spoils the outcome early — even though the true result is
// frozen the moment the bet is drawn/settled.

// LOCAL: weighted pick over the published outcomes — the exact certified odds.
function localPlay(rung, stake) {
  var total = 0, i;
  for (i = 0; i < rung.outcomes.length; i++) total += rung.outcomes[i].weight;
  var r = Math.random() * total, pick = rung.outcomes[rung.outcomes.length - 1];
  for (i = 0; i < rung.outcomes.length; i++) {
    if ((r -= rung.outcomes[i].weight) < 0) { pick = rung.outcomes[i]; break; }
  }
  var isWin = pick.payoutCents > 0;
  return Promise.resolve({
    isWin: isWin, payoutMult: rung.multiplier,
    payoutAmount: isWin ? stake * rung.multiplier : 0
  });
}

// LIVE: play at this rung's mode → a win releases via end-round; a loss is
// already fully settled by the play response (see below).
function livePlay(rung, stake) {
  return rgs('/wallet/play', {
    sessionID: SESSION, mode: rung.modeKey, currency: CURRENCY,
    amount: Math.round(stake * MONEY)
  }).then(function (res) {
    // rgs() already rejects on a {error,...} body, so a failed play never
    // reaches here. Still worth guarding against a genuinely empty event
    // list (a "successful" but useless response); field name has varied
    // across games (state vs events, see 2_4_dice_kong_climb).
    var events = (res && res.round && (res.round.state || res.round.events)) || [];
    if (!events.length) throw new Error('Empty round state in play response: ' + JSON.stringify(res));
    // round.payoutMultiplier is a PLAIN multiplier (e.g. 4.5 for a 4.5x win) —
    // unlike the nested state[] events (cellCall.payoutMultiplier, wincap/
    // finalWin.amount), which ARE ×100 cents. Confirmed against a live
    // response: {round:{payoutMultiplier:4.5, payout:22500000, amount:5000000}}
    // for a $5 bet at 4.5x ($22.50). Dividing this field by 100 (as the ×100
    // convention would suggest) silently pays 1/100th of the real amount.
    var mult = (res && res.round && res.round.payoutMultiplier) ||
               (res && res.payoutMultiplier) || 0;
    var isWin = mult > 0;
    var playBal = extractBalance(res);
    // round.payout is the authoritative payout in the standard RGS money
    // scale (same ×1,000,000 scale as round.amount) — prefer it outright
    // over recomputing stake × mult client-side.
    var playPayout = (res && res.round && typeof res.round.payout === 'number')
      ? res.round.payout : null;

    // A losing round has no payout to release, so the RGS already settles
    // and closes it inside THIS play response (round.active:false) — no
    // active round remains for /wallet/end-round to end. Calling it anyway
    // is exactly what throws "player does not have active round". Only a
    // win leaves a payout pending, so only a win calls end-round (mirrors
    // the production noWin/singleRoundWin split in monstrums-web-sdk's
    // packages/utils-xstate/createPrimaryMachines.ts).
    if (!isWin) {
      // Record the authoritative server balance (this round is fully settled here).
      // The pill is NOT set from this snapshot — it is a per-round value taken before
      // any still-in-flight chips are staked server-side, so assigning it to the pill
      // when chips reveal out of settlement order drifts the display by whole stakes
      // (the "double-deducted" bug). Reconciliation happens only when nothing is in
      // play; see the optimistic ledger in stepSim.
      if (playBal !== null) rgsBalance = playBal / MONEY;
      return { isWin: false, payoutMult: rung.multiplier, payoutAmount: 0 };
    }

    return endRoundWithRetry(3).then(function (end) {
      // RGS.md documents balance as { amount, currency }, not a bare number.
      var bal = extractBalance(end) !== null ? extractBalance(end) : playBal;
      if (bal !== null) rgsBalance = bal / MONEY;
      return { isWin: true, payoutMult: mult || rung.multiplier,
               payoutAmount: playPayout !== null ? playPayout / MONEY : stake * mult };
    }).catch(function (err) {
      err.pendingWin = true; // round played and WON server-side; only the release failed
      throw err;
    });
  });
}

// ---------------------------------------------------------------- betting

// Up to TWO chips per time-column, on distinct cells. With at most two outcomes a
// single steered line can always render the combination (enter on the safe side,
// sweep between two winners); a third chip can create an impossible
// win-lose-win sandwich the line cannot draw. The cap is static so a rejection
// never leaks anything about outcomes already drawn.
function columnBlocked(c) {
  var live = bets.filter(function (b) {
    return b.t1 === c.t1 && b.state !== 'won' && b.state !== 'lost';
  });
  if (live.length >= 2) return true;
  return live.some(function (b) { return Math.abs(b.low - c.low) < 1e-9; });
}

function cellAt(clientX, clientY) {
  var t = timeForX(clientX), p = priceForY(clientY);
  var t1 = Math.floor(t / CFG.cellSeconds) * CFG.cellSeconds;
  var low = Math.floor(p / CFG.cellDollars) * CFG.cellDollars;
  return { t1: t1, t2: t1 + CFG.cellSeconds, low: low, high: low + CFG.cellDollars };
}

function cellValid(c) {
  return c.t1 >= simTime + CFG.minLeadSec && !columnBlocked(c);
}

function rejectCell(c, why) {
  rejects.push({ t1: c.t1, low: c.low, age: 0 });
  toast(why, 'warn');
}

function placeBet(clientX, clientY) {
  if (fatal) return;
  if (IS_LIVE && !authReady) { toast('Connecting to the casino…', 'warn'); return; }
  if (!LADDER) { toast('Odds not loaded yet', 'warn'); return; }
  var c = cellAt(clientX, clientY);

  // Up to two chips per time-column (distinct cells): a single steered line must
  // be able to render every outcome without contradiction (see readme.txt). Chips
  // in OTHER columns are unrestricted — RGS rounds are serialized through
  // betChain, not rejected.
  if (c.t1 < simTime + CFG.minLeadSec) { rejectCell(c, 'Too close to the line'); return; }
  var colLive = bets.filter(function (b) {
    return b.t1 === c.t1 && b.state !== 'won' && b.state !== 'lost';
  });
  if (colLive.some(function (b) { return Math.abs(b.low - c.low) < 1e-9; })) {
    rejectCell(c, 'Chip already there'); return;
  }
  if (colLive.length >= 2) { rejectCell(c, 'Column full — max 2 chips'); return; }
  var stake = betSize;
  if (stake > balance) { toast('Insufficient balance', 'warn'); return; }

  var rung = cellRung(c.low, c.high, c.t1, c.t2);
  var bet = {
    t1: c.t1, t2: c.t2, low: c.low, high: c.high,
    stake: stake, mult: rung.multiplier, modeKey: rung.modeKey,
    outcome: null, state: 'pending', stateAge: 0,
    missTarget: null
  };
  bets.push(bet);
  setBalance(balance - stake); // stake leaves the display immediately, win credit at reveal
  sessionPL -= stake;
  sound('place');
  dismissHint();
  updateStrip();

  // queue this chip's round behind any still-settling ones (RGS: one active
  // round per session) — the chip pulses as "pending" until its turn settles
  betChain = betChain.then(function () {
    return (IS_LIVE ? livePlay(rung, stake) : localPlay(rung, stake)).then(function (out) {
      bet.outcome = out;
      bet.state = 'active';
    });
  }).catch(function (err) {
    bets = bets.filter(function (b) { return b !== bet; });
    setBalance(balance + stake); // refund the display — the bet never happened
    sessionPL += stake;
    updateStrip();
    if (isFatalRgsError(err)) {
      fatalError('Your session has expired. Relaunch the game from the casino.');
    } else if (err && err.pendingWin) {
      // the win exists server-side but its release kept failing — reload
      // re-authenticates and the resume path settles it
      fatalError('Connection lost while collecting a win. Reload to settle it.');
    } else {
      toast('RGS error: ' + (err && err.message ? err.message : 'bet rejected'), 'warn', 3);
    }
  });
}

// ---------------------------------------------------------------- feed + steering

function stepFeed(dt) {
  anchor += CFG.anchorVol * Math.sqrt(dt) * gauss();
  vel += (-CFG.velDamping * vel + CFG.meanRevert * (anchor - price)) * dt
       + CFG.velNoise * Math.sqrt(dt) * gauss();

  // Steer for the nearest column that has unresolved chips (up to two). The books'
  // isWin flags decide the line's fate — the cells are presentation, the drawn
  // books are the truth. Winners: converge on one, then sweep to the other.
  // Losers: hold a miss lane clear of every losing band.
  var colT1 = null;
  for (var i = 0; i < bets.length; i++) {
    var b = bets[i];
    if (!b.outcome || simTime > b.t1 + CFG.resolveSec) continue;
    if (b.state !== 'active' && b.state !== 'hot') continue;
    if (colT1 === null || b.t1 < colT1) colT1 = b.t1;
  }
  if (colT1 !== null) {
    var col = bets.filter(function (b) {
      return b.t1 === colT1 && b.outcome &&
             (b.state === 'active' || b.state === 'hot' || b.state === 'won');
    });
    var center = function (b) { return (b.low + b.high) / 2; };
    var nearest = function (list) {
      return list.reduce(function (a, b) {
        return Math.abs(center(a) - price) <= Math.abs(center(b) - price) ? a : b;
      });
    };
    var winners = col.filter(function (b) { return b.outcome.isWin; });
    var losers = col.filter(function (b) { return !b.outcome.isWin; });
    var goal = null;
    if (winners.length) {
      // aim at the closest not-yet-revealed winner; once it fills, the goal
      // switches to the other one and the line sweeps over
      var pendingW = winners.filter(function (b) { return b.state !== 'won'; });
      goal = center(nearest(pendingW.length ? pendingW : winners));
    } else if (losers.length) {
      if (losers[0].missTarget === null) {
        // a miss lane clear of EVERY losing band, on the side the price favours
        var hiEdge = Math.max.apply(null, losers.map(function (b) { return b.high; }));
        var loEdge = Math.min.apply(null, losers.map(function (b) { return b.low; }));
        var up = hiEdge + CFG.cellDollars * 1.5, down = loEdge - CFG.cellDollars * 1.5;
        losers[0].missTarget = Math.abs(price - up) <= Math.abs(price - down) ? up : down;
      }
      goal = losers[0].missTarget;
    }
    if (goal !== null) {
      var tau = colT1 - simTime;
      if (tau < CFG.guideLeadSec) {
        var w = 1 - Math.max(0, tau) / CFG.guideLeadSec;   // 0 → 1 as the column nears
        // critically-damped pull: converge on a proportional approach velocity
        // instead of accumulating raw force (no overshoot dive past the goal)
        var desiredVel = (goal - price) * (0.6 + 1.6 * w);
        vel += (desiredVel - vel) * w * w * 5 * dt;
      }
      // inside the reveal window: hard-guarantee the outcome before resolveSec
      if (simTime >= colT1) {
        var prog = Math.min(1, (simTime - colT1) / (CFG.resolveSec * 0.5));
        price += (goal - price) * prog * 0.35;
        // never let any losing chip's cell be touched
        var margin = CFG.cellDollars * 0.12;
        for (var li = 0; li < losers.length; li++) {
          var L = losers[li];
          if (price > L.low - margin && price < L.high + margin) {
            price = goal >= center(L) ? L.high + margin : L.low - margin;
            vel = 0;
          }
        }
      }
    }
  }
  price += vel * dt;
}

function updateVolEst() {
  var samples = [], nextT = history.length ? history[0].t : 0;
  for (var i = 0; i < history.length; i++) {
    if (history[i].t >= nextT) { samples.push(history[i].p); nextT += 1; }
  }
  if (samples.length < 8) return;
  var sum = 0, sum2 = 0, n = samples.length - 1;
  for (var j = 1; j < samples.length; j++) {
    var d = samples[j] - samples[j - 1];
    sum += d; sum2 += d * d;
  }
  var varr = Math.max(0, sum2 / n - (sum / n) * (sum / n));
  volEst = Math.min(1.5, Math.max(0.15, Math.sqrt(varr)));
}

var volEstCountdown = 0;

function stepSim(dt) {
  stepFeed(dt);
  simTime += dt;
  history.push({ t: simTime, p: price });
  while (history.length && history[0].t < simTime - CFG.historySeconds) history.shift();
  volEstCountdown -= dt;
  if (volEstCountdown <= 0) { updateVolEst(); volEstCountdown = 1; }

  for (var i = 0; i < bets.length; i++) {
    var b = bets[i];
    if (b.state === 'won' || b.state === 'lost' || b.state === 'pending') continue;
    var resolveT = b.t1 + CFG.resolveSec;
    var touched = simTime >= b.t1 && simTime < resolveT && price >= b.low && price < b.high;
    // A won book always reveals as a win: normally when the steered line enters the
    // cell, or at the reveal window's end as a fallback (e.g. the outcome arrived late).
    if (b.outcome.isWin && (touched || simTime >= resolveT)) {
      b.state = 'won'; b.stateAge = 0;
      // Prefer the RGS's authoritative payout amount (LIVE) over recomputing
      // stake × payoutMult client-side — sidesteps any mult-scale mismatch.
      var payout = (typeof b.outcome.payoutAmount === 'number')
        ? b.outcome.payoutAmount : b.stake * b.outcome.payoutMult;
      // celebration scales with rarity: <5x normal, 5–20x big, >=20x epic
      b.tier = b.outcome.payoutMult >= 20 ? 2 : b.outcome.payoutMult >= 5 ? 1 : 0;
      // Optimistic ledger: stake already left at placement, so credit the full
      // return here (both modes). NOT the RGS per-round balance snapshot — that
      // drifts when chips reveal out of settlement order; LIVE re-syncs to the
      // authoritative balance only when nothing is in play (reconcile below).
      setBalance(balance + payout);
      sessionPL += payout;
      floats.push({ x: (b.t1 + b.t2) / 2, y: (b.low + b.high) / 2,
                    text: '+' + fmtAmt(payout), kind: 'win', tier: b.tier, age: 0 });
      toast((b.tier === 2 ? 'Big win ' : 'You won ') + fmtMoney(payout), 'win', b.tier ? 3.2 : 2.6);
      if (b.tier === 2 && !REDUCED) vignette = { age: 0 };
      sound('win', b.tier);
      recordResult(true, payout);
      pushHist(b, true, payout);
    } else if (simTime >= resolveT) {
      b.state = 'lost'; b.stateAge = 0;
      // No balance change: the stake already left at placement (optimistic ledger,
      // both modes). The float below is the chip's OUTCOME marker, not a second debit.
      floats.push({ x: (b.t1 + b.t2) / 2, y: (b.low + b.high) / 2,
                    text: 'Missed', kind: 'loss', age: 0 });
      sound('loss');
      recordResult(false, b.stake);
      pushHist(b, false, 0);
    } else {
      b.state = (b.t1 - simTime) < CFG.guideLeadSec * 0.8 ? 'hot' : 'active';
    }
  }

  // LIVE reconcile: when nothing is in play, snap the pill to the authoritative RGS
  // balance. At quiescence the optimistic ledger already equals it, so this is normally
  // a silent no-op — it only corrects residual drift, never a mid-flight jump.
  if (IS_LIVE && rgsBalance !== null && Math.abs(rgsBalance - balance) > 0.005) {
    var anyLive = false;
    for (var q = 0; q < bets.length; q++) {
      var s = bets[q].state;
      if (s === 'pending' || s === 'active' || s === 'hot') { anyLive = true; break; }
    }
    if (!anyLive) setBalance(rgsBalance);
  }
}

function stepVisuals(dt) {
  viewTime = simTime + acc;
  dispPrice += (price - dispPrice) * Math.min(1, dt * 12);
  // frame the line AND the nearest chip (through its resolution beat), so a
  // resolving bet never slides off-screen while the camera chases the price
  var frameT1 = null;
  var isFramable = function (b) {
    var live = b.state === 'active' || b.state === 'hot' || b.state === 'pending';
    var justResolved = (b.state === 'won' || b.state === 'lost') && b.stateAge < 1.0;
    return (live || justResolved) && b.t1 - simTime <= 9;
  };
  for (var fb = 0; fb < bets.length; fb++) {
    if (!isFramable(bets[fb])) continue;
    if (frameT1 === null || bets[fb].t1 < frameT1) frameT1 = bets[fb].t1;
  }
  var camTarget = price;
  if (frameT1 !== null) {
    var mids = bets.filter(function (b) { return b.t1 === frameT1 && isFramable(b); })
                   .map(function (b) { return (b.low + b.high) / 2; });
    var colMid = mids.reduce(function (a, v) { return a + v; }, 0) / mids.length;
    camTarget = (price + colMid) / 2;
  }
  camPrice += (camTarget - camPrice) * Math.min(1, dt * 2.5);
  for (var i = 0; i < bets.length; i++) {
    if (bets[i].state === 'won' || bets[i].state === 'lost') bets[i].stateAge += dt;
  }
  bets = bets.filter(function (b) {
    return !((b.state === 'won' || b.state === 'lost') && b.stateAge > 1.3);
  });
  for (var j = 0; j < floats.length; j++) floats[j].age += dt;
  floats = floats.filter(function (f) { return f.age < 1.8; });
  for (var k = 0; k < rejects.length; k++) rejects[k].age += dt;
  rejects = rejects.filter(function (r) { return r.age < 0.5; });
  if (vignette) {
    vignette.age += dt;
    if (vignette.age > 0.8) vignette = null;
  }
}

// ---------------------------------------------------------------- coords

function nowX() { return W * CFG.nowFrac; }
function pxSec() { return CFG.pxPerSec * zoom; }
function pxDol() { return CFG.pxPerDollar * zoom; }
function xForTime(t) { return nowX() + (t - viewTime) * pxSec(); }
function yForPrice(p) { return H / 2 - (p - camPrice) * pxDol(); }
function timeForX(x) { return viewTime + (x - nowX()) / pxSec(); }
function priceForY(y) { return camPrice + (H / 2 - y) / pxDol(); }

// ---------------------------------------------------------------- render

function roundRect(x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

function chipRect(b) {
  return {
    x: xForTime(b.t1) + 3,
    y: yForPrice(b.high) + 3,
    w: CFG.cellSeconds * pxSec() - 6,
    h: CFG.cellDollars * pxDol() - 6
  };
}

function drawChip(b, tSec) {
  var r = chipRect(b), bx = r.x, by = r.y, bw = r.w, bh = r.h;
  var age = b.stateAge;
  var alpha = 1, shakeX = 0, dropY = 0;

  if (b.state === 'won') {
    alpha = age < 0.45 ? 1 : Math.max(0, 1 - (age - 0.45) / 0.7);
  } else if (b.state === 'lost') {
    // the loss beat: red flash + shake (0–0.35s), then the chip drops away
    alpha = age < 0.35 ? 1 : Math.max(0, 1 - (age - 0.35) / 0.8);
    if (!REDUCED) {
      if (age < 0.35) shakeX = Math.sin(age * 55) * 3.5 * (1 - age / 0.35);
      else dropY = (age - 0.35) * (age - 0.35) * 90;
    }
  }
  if (alpha <= 0) return;

  ctx.save();
  ctx.translate(shakeX, dropY);
  ctx.globalAlpha = b.state === 'pending'
    ? alpha * (REDUCED ? 0.6 : 0.45 + 0.2 * Math.sin(tSec * 5))
    : alpha;

  var grad = ctx.createLinearGradient(bx, by, bx, by + bh);
  if (b.state === 'lost') {
    grad.addColorStop(0, COLOR.lossFill1); grad.addColorStop(1, COLOR.lossFill2);
    ctx.shadowColor = age < 0.35 ? COLOR.lossGlow : 'transparent';
  } else if (b.state === 'hot') {
    grad.addColorStop(0, COLOR.hot1); grad.addColorStop(1, COLOR.hot2);
    ctx.shadowColor = 'rgba(' + COLOR.hotGlowRGB + ',' + (REDUCED ? 0.8 : (0.6 + 0.3 * Math.sin(tSec * 6))) + ')';
  } else {
    grad.addColorStop(0, COLOR.chip1); grad.addColorStop(1, COLOR.chip2);
    ctx.shadowColor = COLOR.chipGlow;
  }
  ctx.shadowBlur = 16;
  ctx.fillStyle = grad;
  roundRect(bx, by, bw, bh, 7);
  ctx.fill();
  ctx.shadowBlur = 0;

  // hot chip: a thin depleting bar — empties exactly at the resolution beat
  if (b.state === 'hot') {
    var frac = Math.max(0, Math.min(1,
      (b.t1 + CFG.resolveSec - simTime) / (CFG.guideLeadSec * 0.8 + CFG.resolveSec)));
    ctx.fillStyle = COLOR.countTrack;
    ctx.fillRect(bx + 4, by + bh - 7, bw - 8, 3);
    ctx.fillStyle = COLOR.countFill;
    ctx.fillRect(bx + 4, by + bh - 7, (bw - 8) * frac, 3);
  }

  // win ring pulse — an expanding stroke marking the exact fill moment,
  // wider for rarer wins
  if (b.state === 'won' && !REDUCED && age < 0.6) {
    var ringT = age / 0.6;
    var ext = 18 + (b.tier || 0) * 14;
    ctx.globalAlpha = (1 - ringT) * 0.9;
    ctx.strokeStyle = COLOR.ring;
    ctx.lineWidth = 2 + (b.tier || 0);
    roundRect(bx - ringT * ext, by - ringT * ext, bw + ringT * ext * 2, bh + ringT * ext * 2, 7 + ringT * 12);
    ctx.stroke();
    ctx.globalAlpha = alpha;
  }

  // the label scales down with the chip so a placed bet is always readable;
  // below two-line height it collapses to just the stake
  var ts = Math.min(bw / 64, bh / 49, 1);
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillStyle = b.state === 'lost' ? COLOR.lossText : COLOR.betText;
  if (bh >= 28) {
    ctx.font = 'bold ' + Math.max(8, Math.round(13 * ts)) + 'px ' + MONO;
    ctx.fillText((b.state === 'lost' ? '−' : '') + fmtAmt(b.stake), bx + bw / 2, by + bh / 2 - 7 * ts);
    ctx.font = Math.max(7, Math.round(10 * ts)) + 'px ' + MONO;
    ctx.fillText(b.state === 'lost' ? 'MISS' : fmtMult(b.mult), bx + bw / 2, by + bh / 2 + 8 * ts);
  } else {
    ctx.font = 'bold ' + Math.max(8, Math.round(12 * ts)) + 'px ' + MONO;
    ctx.fillText((b.state === 'lost' ? '−' : '') + fmtAmt(b.stake), bx + bw / 2, by + bh / 2);
  }
  ctx.restore();
}

function render(tSec) {
  ctx.fillStyle = COLOR.bg;
  ctx.fillRect(0, 0, W, H);

  var pTop = priceForY(0), pBot = priceForY(H);
  var tLeft = timeForX(0), tRight = timeForX(W);
  var nx = nowX();

  ctx.lineWidth = 1;
  var row0 = Math.floor(pBot / CFG.cellDollars) * CFG.cellDollars;
  for (var pr = row0; pr <= pTop + CFG.cellDollars; pr += CFG.cellDollars) {
    var gy = Math.round(yForPrice(pr)) + 0.5;
    ctx.strokeStyle = COLOR.gridLine;
    ctx.beginPath(); ctx.moveTo(0, gy); ctx.lineTo(W, gy); ctx.stroke();
  }
  var col0 = Math.floor(tLeft / CFG.cellSeconds) * CFG.cellSeconds;
  for (var tc = col0; tc <= tRight + CFG.cellSeconds; tc += CFG.cellSeconds) {
    var gx = Math.round(xForTime(tc)) + 0.5;
    ctx.strokeStyle = Math.round(tc) % 15 === 0 ? COLOR.gridLineMajor : COLOR.gridLine;
    ctx.beginPath(); ctx.moveTo(gx, 0); ctx.lineTo(gx, H); ctx.stroke();
  }

  // the "now" line + the too-late zone (cells there can't be bet)
  var firstValidT1 = Math.ceil((simTime + CFG.minLeadSec) / CFG.cellSeconds) * CFG.cellSeconds;
  var deadRight = xForTime(firstValidT1);
  if (deadRight > nx) {
    ctx.fillStyle = COLOR.deadZone;
    ctx.fillRect(nx, 0, deadRight - nx, H);
  }
  ctx.strokeStyle = COLOR.nowLine;
  ctx.setLineDash([3, 5]);
  ctx.beginPath(); ctx.moveTo(Math.round(nx) + 0.5, 0); ctx.lineTo(Math.round(nx) + 0.5, H); ctx.stroke();
  ctx.setLineDash([]);

  // hovered cell — where the tap would land, with the exact offer. On touch,
  // the armed cell (first tap) plays the hover role until the confirming tap.
  var hover = null, armedMode = false;
  if (LADDER) {
    if (armed) {
      if (cellValid(armed)) { hover = armed; armedMode = true; }
      else armed = null; // slid into the dead zone or got taken — disarm
    } else if (mouse.inside && mouse.x > deadRight) {
      var hc = cellAt(mouse.x, mouse.y);
      if (cellValid(hc)) hover = hc;
    }
  }

  // cell multipliers (ladder-snapped) — future zone only; skipped when zoomed
  // out far enough that the labels would collide
  if (LADDER && CFG.cellSeconds * pxSec() >= 34 && CFG.cellDollars * pxDol() >= 22) {
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.font = '11px ' + MONO;
    var firstCol = Math.max(col0, Math.ceil(simTime / CFG.cellSeconds) * CFG.cellSeconds);
    for (var ct = firstCol; ct < tRight; ct += CFG.cellSeconds) {
      var cx = xForTime(ct + CFG.cellSeconds / 2);
      if (cx < nx) continue;
      var dead = ct < firstValidT1;
      for (var cp = row0; cp <= pTop; cp += CFG.cellDollars) {
        var cy = yForPrice(cp + CFG.cellDollars / 2);
        if (cy < 14 || cy > H - 30) continue;
        var rung = cellRung(cp, cp + CFG.cellDollars, ct, ct + CFG.cellSeconds);
        var bright = dead ? 0.12 : 0.32 + 0.35 * Math.min(1, rung.multiplier / 100);
        ctx.fillStyle = 'rgba(' + COLOR.multRGB + ',' + bright.toFixed(2) + ')';
        ctx.fillText(fmtMult(rung.multiplier), cx, cy);
      }
    }
  }

  // hover highlight: cell outline + concrete payout preview
  if (hover) {
    var hx = xForTime(hover.t1), hy = yForPrice(hover.high);
    var hw = CFG.cellSeconds * pxSec(), hh = CFG.cellDollars * pxDol();
    var hRung = cellRung(hover.low, hover.high, hover.t1, hover.t2);
    ctx.save();
    ctx.strokeStyle = COLOR.hover;
    ctx.lineWidth = 1.5;
    roundRect(hx + 2, hy + 2, hw - 4, hh - 4, 6);
    ctx.stroke();
    ctx.fillStyle = COLOR.hoverFill;
    ctx.fill();
    ctx.textAlign = 'center';
    ctx.fillStyle = COLOR.hoverText;
    ctx.font = 'bold 11px ' + MONO;
    ctx.fillText(fmtMult(hRung.multiplier) + ' · win ' + fmtAmt(betSize * hRung.multiplier)
                 + (armedMode ? ' · tap again to confirm' : ''),
                 hx + hw / 2, hy - 9);
    ctx.restore();
  }

  // rejected-tap flashes
  for (var ri = 0; ri < rejects.length; ri++) {
    var rj = rejects[ri];
    var rx = xForTime(rj.t1), ry = yForPrice(rj.low + CFG.cellDollars);
    ctx.save();
    ctx.globalAlpha = Math.max(0, 1 - rj.age / 0.5);
    ctx.strokeStyle = COLOR.reject;
    ctx.lineWidth = 1.5;
    roundRect(rx + 2, ry + 2, CFG.cellSeconds * pxSec() - 4, CFG.cellDollars * pxDol() - 4, 6);
    ctx.stroke();
    ctx.restore();
  }

  // axis labels (skip the ones the current-price tag would cover)
  var tagYv = yForPrice(dispPrice);
  ctx.fillStyle = COLOR.axisText;
  ctx.font = '11px ' + MONO;
  ctx.textAlign = 'right';
  // label every other row when zoomed out enough that rows crowd
  var lStep = CFG.cellDollars * (CFG.cellDollars * pxDol() < 34 ? 2 : 1);
  for (var lp = Math.floor(pBot / lStep) * lStep; lp <= pTop + lStep; lp += lStep) {
    var ly = yForPrice(lp);
    if (ly < 54 || ly > H - 24) continue; // top band is the session strip's
    if (Math.abs((ly - 7) - tagYv) < 17) continue;
    ctx.fillText('$' + lp.toFixed(1), W - 8, ly - 7);
  }
  ctx.textAlign = 'center';
  for (var lt = col0; lt <= tRight; lt += CFG.cellSeconds) {
    if (Math.round(lt) % 15 !== 0) continue;
    ctx.fillText(fmtClock(lt), xForTime(lt), H - 12);
  }

  // bet chips
  for (var bi = 0; bi < bets.length; bi++) drawChip(bets[bi], tSec);

  // hovering a live chip shows what it pays
  if (!COARSE && mouse.inside) {
    for (var hb = 0; hb < bets.length; hb++) {
      var cb = bets[hb];
      if (cb.state === 'won' || cb.state === 'lost') continue;
      var cr = chipRect(cb);
      if (mouse.x >= cr.x && mouse.x <= cr.x + cr.w && mouse.y >= cr.y && mouse.y <= cr.y + cr.h) {
        ctx.save();
        ctx.textAlign = 'center';
        ctx.fillStyle = COLOR.hoverText;
        ctx.font = 'bold 11px ' + MONO;
        ctx.shadowColor = 'rgba(0,0,0,0.7)'; ctx.shadowBlur = 4;
        ctx.fillText('pays ' + fmtAmt(cb.stake * cb.mult), cr.x + cr.w / 2, cr.y - 9);
        ctx.restore();
        break;
      }
    }
  }

  // price line
  if (history.length > 1) {
    ctx.save();
    ctx.strokeStyle = COLOR.line;
    ctx.lineWidth = 1.6; ctx.lineJoin = 'round';
    ctx.shadowColor = COLOR.lineGlow; ctx.shadowBlur = 8;
    ctx.beginPath();
    var started = false;
    for (var hi = 0; hi < history.length; hi++) {
      var hxp = xForTime(history[hi].t);
      if (hxp < -10) continue;
      var hyp = yForPrice(history[hi].p);
      if (!started) { ctx.moveTo(hxp, hyp); started = true; } else ctx.lineTo(hxp, hyp);
    }
    var dx = nowX(), dy = yForPrice(dispPrice);
    ctx.lineTo(dx, dy);
    ctx.stroke();
    ctx.fillStyle = COLOR.dot; ctx.shadowBlur = 12;
    ctx.beginPath(); ctx.arc(dx, dy, 3.2, 0, Math.PI * 2); ctx.fill();
    ctx.restore();
  }

  // current price tag
  var tagY = yForPrice(dispPrice);
  var tagText = '$' + price.toFixed(1);
  ctx.font = 'bold 12px ' + MONO;
  var tw = ctx.measureText(tagText).width + 16;
  ctx.fillStyle = COLOR.priceTagBg;
  roundRect(W - tw - 4, tagY - 11, tw, 22, 5);
  ctx.fill();
  ctx.fillStyle = COLOR.priceTagText; ctx.textAlign = 'center';
  ctx.fillText(tagText, W - tw / 2 - 4, tagY);

  // floating payout texts: wins rise in gold (bigger for rarer wins), losses sink in red
  for (var fi = 0; fi < floats.length; fi++) {
    var f = floats[fi];
    var isLoss = f.kind === 'loss';
    var drift = REDUCED ? 0 : f.age * 26 * (isLoss ? -0.8 : 1);
    var size = isLoss ? 15 : f.tier === 2 ? 26 : f.tier === 1 ? 22 : 17;
    ctx.save();
    ctx.globalAlpha = Math.max(0, 1 - f.age / (isLoss ? 1.4 : 1.5));
    ctx.fillStyle = isLoss ? COLOR.lossFloat : COLOR.winFloat;
    ctx.font = 'bold ' + size + 'px ' + MONO;
    ctx.textAlign = 'center';
    ctx.shadowColor = 'rgba(0,0,0,0.6)'; ctx.shadowBlur = 4;
    ctx.fillText(f.text, xForTime(f.x), yForPrice(f.y) - 24 - drift);
    ctx.restore();
  }

  // epic-win vignette: a brief golden flush from the screen edges
  if (vignette) {
    var vT = vignette.age / 0.8;
    var vAlpha = (vT < 0.25 ? vT / 0.25 : 1 - (vT - 0.25) / 0.75) * 0.5;
    var vg = ctx.createRadialGradient(W / 2, H / 2, Math.min(W, H) * 0.35,
                                      W / 2, H / 2, Math.max(W, H) * 0.75);
    vg.addColorStop(0, 'rgba(' + COLOR.vigRGB + ',0)');
    vg.addColorStop(1, 'rgba(' + COLOR.vigRGB + ',' + vAlpha.toFixed(3) + ')');
    ctx.fillStyle = vg;
    ctx.fillRect(0, 0, W, H);
  }
}

// ---------------------------------------------------------------- loop

// Console/debug handle (read-only peek at sim pacing; not used by the game).
if (import.meta.env.DEV) {
  window.__cpg = {
    simTime: function () { return simTime; },
    cfg: CFG,
    speedMult: function () { return speedMult; },
    tapConfirm: function () { return tapConfirm; }
  };
}

var lastFrame = performance.now();
var acc = 0;

function frame(nowMs) {
  var dt = (nowMs - lastFrame) / 1000;
  lastFrame = nowMs;
  acc += Math.min(dt, 2) * CFG.timeScale * speedMult;
  while (acc >= CFG.tick) { stepSim(CFG.tick); acc -= CFG.tick; }
  stepVisuals(Math.min(dt, 0.1));
  render(nowMs / 1000);
  captureShots(); // grab landing shots off the freshly-rendered frame
  requestAnimationFrame(frame);
}

// ---------------------------------------------------------------- wiring

function resize() {
  DPR = window.devicePixelRatio || 1;
  W = window.innerWidth; H = window.innerHeight;
  canvas.width = Math.round(W * DPR);
  canvas.height = Math.round(H * DPR);
  ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
}
window.addEventListener('resize', resize);
resize();

// A hidden tab pauses rAF; on return the accumulator would replay up to
// 2s×speed of sim in one frame — chips could resolve invisibly. Drop the
// backlog instead (LIVE outcomes are already settled server-side; only
// presentation time is discarded).
document.addEventListener('visibilitychange', function () {
  if (!document.hidden) { lastFrame = performance.now(); acc = 0; }
});

function setZoom(z) {
  zoom = Math.min(2.5, Math.max(0.5, z));
}
canvas.addEventListener('wheel', function (e) {
  e.preventDefault();
  setZoom(zoom * Math.exp(-e.deltaY * 0.0012));
}, { passive: false });
canvas.addEventListener('touchstart', function (e) {
  if (e.touches.length === 2) {
    pinch = { dist: Math.hypot(e.touches[0].clientX - e.touches[1].clientX,
                               e.touches[0].clientY - e.touches[1].clientY), zoom: zoom };
    armed = null; // a pinch is not a tap
  }
}, { passive: true });
canvas.addEventListener('touchmove', function (e) {
  if (pinch && e.touches.length === 2) {
    e.preventDefault();
    var d = Math.hypot(e.touches[0].clientX - e.touches[1].clientX,
                       e.touches[0].clientY - e.touches[1].clientY);
    if (pinch.dist > 0) setZoom(pinch.zoom * d / pinch.dist);
  }
}, { passive: false });
canvas.addEventListener('touchend', function () {
  if (pinch) pinchGuard = performance.now();
  pinch = null;
});
document.getElementById('zoomIn').addEventListener('click', function () { setZoom(zoom * 1.25); });
document.getElementById('zoomOut').addEventListener('click', function () { setZoom(zoom / 1.25); });

canvas.addEventListener('click', function (e) {
  if (performance.now() - pinchGuard < 400) return; // ghost tap right after a pinch
  if (tapConfirm) {
    // first tap/click arms the cell (shows the offer), the second confirms
    var c = cellAt(e.clientX, e.clientY);
    if (armed && armed.t1 === c.t1 && Math.abs(armed.low - c.low) < 1e-9) {
      armed = null;
      placeBet(e.clientX, e.clientY);
    } else {
      armed = cellValid(c) ? c : null;
      if (!armed) placeBet(e.clientX, e.clientY); // invalid cell → the usual rejection
    }
    return;
  }
  placeBet(e.clientX, e.clientY);
});
canvas.addEventListener('mousemove', function (e) {
  mouse.x = e.clientX; mouse.y = e.clientY; mouse.inside = true;
});
canvas.addEventListener('mouseleave', function () { mouse.inside = false; });


// ---- theme picker: an explicit select-from-menu, not a cycling button ----
var themeKey = 'rose';
try {
  var storedTheme = localStorage.getItem('taptrade.theme');
  if (storedTheme && THEMES[storedTheme]) themeKey = storedTheme;
} catch (e) { /* ignore */ }

var themeBtn = document.getElementById('themeBtn');
var themeSwatch = document.getElementById('themeSwatch');
var themeMenu = document.getElementById('themeMenu');

// one swatch + label + check row per theme, built once
THEME_ORDER.forEach(function (key) {
  var t = THEMES[key];
  var opt = document.createElement('button');
  opt.type = 'button';
  opt.className = 'themeOption';
  opt.setAttribute('role', 'menuitemradio');
  opt.dataset.key = key;
  opt.innerHTML =
    '<span class="swatch" style="background:linear-gradient(135deg, ' + t.css.bg + ' 50%, ' + t.css.accent + ' 50%)"></span>' +
    '<span class="themeOption-label">' + t.label + '</span>' +
    '<span class="themeOption-check">' + ICON_CHECK + '</span>';
  opt.addEventListener('click', function () { selectTheme(key); closeThemeMenu(); });
  themeMenu.appendChild(opt);
});

function renderThemeSelection() {
  var t = THEMES[themeKey];
  themeSwatch.style.background = 'linear-gradient(135deg, ' + t.css.bg + ' 50%, ' + t.css.accent + ' 50%)';
  themeBtn.title = 'Theme: ' + t.label;
  themeMenu.querySelectorAll('.themeOption').forEach(function (opt) {
    opt.setAttribute('aria-checked', String(opt.dataset.key === themeKey));
  });
}

function selectTheme(key) {
  themeKey = key;
  applyTheme(themeKey);
  renderThemeSelection();
  try { localStorage.setItem('taptrade.theme', themeKey); } catch (e) { /* ignore */ }
  toast('Theme: ' + THEMES[themeKey].label, '', 1.6);
}

function openThemeMenu() {
  closeBetMenu(); closeHistPanel(); closeSettingsPanel(); // only one menu open at a time
  themeMenu.classList.add('open');
  themeMenu.setAttribute('aria-hidden', 'false');
  themeBtn.setAttribute('aria-expanded', 'true');
}
function closeThemeMenu() {
  themeMenu.classList.remove('open');
  themeMenu.setAttribute('aria-hidden', 'true');
  themeBtn.setAttribute('aria-expanded', 'false');
}
themeBtn.addEventListener('click', function (e) {
  e.stopPropagation();
  if (themeMenu.classList.contains('open')) closeThemeMenu(); else openThemeMenu();
});
document.addEventListener('click', function (e) {
  if (!themeMenu.contains(e.target) && e.target !== themeBtn) closeThemeMenu();
});
document.addEventListener('keydown', function (e) {
  if (e.key === 'Escape') { closeThemeMenu(); closeBetMenu(); closeHistPanel(); closeSettingsPanel(); closeHistModal(); }
});

applyTheme(themeKey);
renderThemeSelection();

// ---- bet-amount picker: quick chips + a "+" menu (same pattern as the theme menu) ----
// LOCAL offers CFG.menuBets; LIVE rebuilds everything from the RGS betLevels grid.
// A single custom slot before "+" holds the menu pick, so the row never overflows.
var betRow = document.getElementById('betSizes');
var betMoreBtn = document.getElementById('betMoreBtn');
var betMenu = document.getElementById('betMenu');
var customBetBtn = null;
// the menu shows the FULL grid (quick-chip values included), like the real bet menu
var menuBets = CFG.betLevels.filter(function (v) {
  return v >= CFG.minBet && v <= CFG.maxBet;
});

function fmtBet(v) { return fmtAmt(v); }

function quickChipFor(v) {
  var chips = betRow.querySelectorAll('[data-v]');
  for (var i = 0; i < chips.length; i++) {
    if (chips[i] !== customBetBtn && Number(chips[i].dataset.v) === v &&
        chips[i].style.display !== 'none') return chips[i];
  }
  return null;
}

function renderBetSelection() {
  betRow.querySelectorAll('[data-v]').forEach(function (b) {
    b.classList.toggle('on', Number(b.dataset.v) === betSize);
  });
  betMenu.querySelectorAll('.betOpt').forEach(function (opt) {
    opt.setAttribute('aria-checked', String(Number(opt.dataset.v) === betSize));
  });
}

function setBetSize(v) {
  betSize = v;
  try { localStorage.setItem('taptrade.betSize', String(v)); } catch (e) { /* ignore */ }
  renderBetSelection();
}

// a menu pick lands in the row: reuse the matching quick chip if one exists,
// otherwise fill/replace the single custom slot before the "+" button
function selectBet(v) {
  if (!quickChipFor(v)) {
    if (!customBetBtn) {
      customBetBtn = document.createElement('button');
      customBetBtn.type = 'button';
      customBetBtn.className = 'num';
      betRow.insertBefore(customBetBtn, betMoreBtn);
    }
    customBetBtn.dataset.v = String(v);
    customBetBtn.textContent = fmtBet(v);
  }
  setBetSize(v);
}

function buildBetMenu() {
  betMenu.querySelectorAll('.betOpt').forEach(function (o) { o.remove(); });
  menuBets.forEach(function (v) {
    var opt = document.createElement('button');
    opt.type = 'button';
    var isMax = menuBets.length > 1 && v === menuBets[menuBets.length - 1];
    opt.className = 'betOpt num' + (isMax ? ' max' : '');
    opt.setAttribute('role', 'menuitemradio');
    opt.dataset.v = String(v);
    opt.textContent = isMax ? 'MAX' : fmtBet(v);
    if (isMax) opt.title = fmtBet(v);
    opt.addEventListener('click', function () { selectBet(v); closeBetMenu(); });
    betMenu.appendChild(opt);
  });
  betMoreBtn.style.display = menuBets.length ? '' : 'none';
  renderBetSelection();
}

function openBetMenu() {
  closeThemeMenu(); closeHistPanel(); closeSettingsPanel(); // only one menu open at a time
  betMenu.classList.add('open');
  betMenu.setAttribute('aria-hidden', 'false');
  betMoreBtn.setAttribute('aria-expanded', 'true');
}
function closeBetMenu() {
  betMenu.classList.remove('open');
  betMenu.setAttribute('aria-hidden', 'true');
  betMoreBtn.setAttribute('aria-expanded', 'false');
}
betMoreBtn.addEventListener('click', function (e) {
  e.stopPropagation();
  if (betMenu.classList.contains('open')) closeBetMenu(); else openBetMenu();
});
document.addEventListener('click', function (e) {
  if (!betMenu.contains(e.target) && !betMoreBtn.contains(e.target)) closeBetMenu();
});

// LIVE: rebuild the whole picker from the RGS bet grid (display dollars, capped
// at CFG.maxBet). Quick chips snap to their nearest grid values; the menu gets
// every grid value above the quick chips; any off-grid selection snaps too.
function applyBetConfig(config) {
  if (!config.betLevels || !config.betLevels.length) return;
  // operator limits win over the demo defaults; the demo caps are fallbacks
  var minB = typeof config.minBet === 'number' ? config.minBet / MONEY : CFG.minBet;
  var maxB = typeof config.maxBet === 'number' ? config.maxBet / MONEY : CFG.maxBet;
  var grid = snapGrid(config.betLevels, minB, maxB, MONEY);
  if (!grid.length) return;
  var quick = quickPicksFromGrid(grid, CFG.betSizes);
  var staticChips = Array.prototype.filter.call(betRow.querySelectorAll('[data-v]'),
    function (b) { return b !== customBetBtn; });
  staticChips.forEach(function (chip, i) {
    if (i < quick.length) {
      chip.dataset.v = String(quick[i]);
      chip.textContent = fmtBet(quick[i]);
      chip.style.display = '';
    } else {
      chip.style.display = 'none';
    }
  });
  if (customBetBtn && grid.indexOf(Number(customBetBtn.dataset.v)) < 0) {
    customBetBtn.remove();
    customBetBtn = null;
  }
  menuBets = grid;
  buildBetMenu();
  if (grid.indexOf(betSize) < 0) {
    // current selection is off-grid: prefer the operator's default level
    var preferred = typeof config.defaultBetLevel === 'number'
      ? config.defaultBetLevel / MONEY : betSize;
    selectBet(nearestOnGrid(grid, preferred));
  }
}

// Regulated-market flags from the authenticate config.
function applyJurisdiction(jur) {
  if (jur.disabledTurbo) {
    speedSeg.querySelectorAll('button').forEach(function (b) {
      if (Number(b.dataset.s) > 1) b.style.display = 'none';
    });
    if (speedMult !== 1) {
      speedMult = 1;
      try { localStorage.setItem('taptrade.speed', '1'); } catch (e) { /* ignore */ }
      renderSettings();
    }
  }
  if (jur.socialCasino) {
    document.querySelector('#betSizes .label').textContent = 'Play';
  }
}

betRow.addEventListener('click', function (e) {
  var b = e.target.closest('[data-v]');
  if (!b) return;
  setBetSize(Number(b.dataset.v));
});

buildBetMenu();
// restore the last bet size — only values the picker actually offers
try {
  var storedBet = parseFloat(localStorage.getItem('taptrade.betSize'));
  if (menuBets.indexOf(storedBet) >= 0) selectBet(storedBet);
} catch (e) { /* ignore */ }

// ---- bet history: every resolved bet keeps a landing shot + an animated replay ----
var histBtn = document.getElementById('histBtn');
var histPanel = document.getElementById('histPanel');
var histList = document.getElementById('histList');

function escHtml(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;'); }

function clockFromTs(ts) {
  var d = new Date(ts);
  var h = d.getHours(), mi = d.getMinutes(), s = d.getSeconds();
  var ap = h >= 12 ? 'PM' : 'AM'; h = h % 12 || 12;
  var two = function (n) { return (n < 10 ? '0' : '') + n; };
  return two(h) + ':' + two(mi) + ':' + two(s) + ' ' + ap;
}

// called at resolution (stepSim); the shot + line slice land ~0.5s later in
// captureShots, once the win/loss beat has actually been rendered
function pushHist(b, won, payout) {
  var entry = {
    ts: Date.now(), stake: b.stake, mult: b.outcome ? b.outcome.payoutMult : b.mult,
    won: won, payout: payout, shot: null,
    cell: { t1: b.t1, t2: b.t2, low: b.low, high: b.high }, line: null
  };
  b.histEntry = entry;
  b.pendingShot = true;
  histEntries.unshift(entry);
  if (histEntries.length > HIST_CAP) histEntries.pop();
  renderHistPanel();
}

function captureShots() {
  for (var i = 0; i < bets.length; i++) {
    var b = bets[i];
    if (!b.pendingShot || !b.histEntry || b.stateAge < 0.5) continue;
    b.pendingShot = false;
    var e = b.histEntry;
    // the line slice that approaches + resolves this cell, for the replay
    // slice up to the capture moment (simTime), so the replay ends exactly
    // where the landing shot shows the line
    var t0 = b.t1 - 8, t1 = simTime, pts = [];
    for (var j = 0; j < history.length; j++) {
      if (history[j].t >= t0 && history[j].t <= t1) pts.push({ t: history[j].t, p: history[j].p });
    }
    e.line = pts;
    // landing shot: the freshly-rendered canvas region around the cell
    // (source coords ×DPR — the backing store is W*DPR wide)
    var r = chipRect(b);
    var sw = Math.min(260, W), sh = Math.min(170, H);
    var sx = Math.max(0, Math.min(W - sw, r.x + r.w / 2 - sw / 2));
    var sy = Math.max(0, Math.min(H - sh, r.y + r.h / 2 - sh / 2));
    if (!shotCanvas) {
      shotCanvas = document.createElement('canvas');
      shotCtx = shotCanvas.getContext('2d');
    }
    shotCanvas.width = sw * 2; shotCanvas.height = sh * 2; // 2x for crisp thumbnails
    try {
      shotCtx.drawImage(canvas, sx * DPR, sy * DPR, sw * DPR, sh * DPR, 0, 0, sw * 2, sh * 2);
      e.shot = shotCanvas.toDataURL('image/jpeg', 0.75);
    } catch (err) { /* capture is decorative — keep the entry without a shot */ }
    renderHistPanel();
  }
}

function renderHistPanel() {
  if (!histEntries.length) {
    histList.innerHTML = '<div id="histEmpty">No bets yet — tap a square to play.</div>';
    return;
  }
  histList.innerHTML = '';
  histEntries.forEach(function (e) {
    var row = document.createElement('button');
    row.type = 'button';
    row.className = 'histRow';
    row.setAttribute('role', 'menuitem');
    row.innerHTML =
      (e.shot ? '<img src="' + e.shot + '" alt="Where the line landed">'
              : '<span class="thumbless"></span>') +
      '<span class="col">' +
      '<span class="amt ' + (e.won ? 'w' : 'l') + ' num">' +
        (e.won ? '+' : '−') + escHtml(fmtAmt(e.won ? e.payout : e.stake)) + '</span>' +
      '<span class="sub num">' + escHtml(fmtMult(e.mult)) + ' · ' + escHtml(fmtAmt(e.stake)) + ' stake</span>' +
      '<span class="sub num">' + escHtml(clockFromTs(e.ts)) + '</span>' +
      '</span>';
    row.addEventListener('click', function () { closeHistPanel(); openHistModal(e); });
    histList.appendChild(row);
  });
}

function openHistPanel() {
  closeThemeMenu(); closeBetMenu(); closeSettingsPanel();
  renderHistPanel();
  histPanel.classList.add('open');
  histPanel.setAttribute('aria-hidden', 'false');
  histBtn.setAttribute('aria-expanded', 'true');
}
function closeHistPanel() {
  histPanel.classList.remove('open');
  histPanel.setAttribute('aria-hidden', 'true');
  histBtn.setAttribute('aria-expanded', 'false');
}
histBtn.addEventListener('click', function (e) {
  e.stopPropagation();
  if (histPanel.classList.contains('open')) closeHistPanel(); else openHistPanel();
});
document.addEventListener('click', function (e) {
  if (!histPanel.contains(e.target) && !histBtn.contains(e.target)) closeHistPanel();
});
// the session-strip pips are the miniature of this feature — clicking them opens it
// (stopPropagation so the document-level outside-click close doesn't undo the open)
document.getElementById('tickerPips').addEventListener('click', function (e) {
  e.stopPropagation();
  openHistPanel();
});
renderHistPanel();

// ---- settings: game speed + touch tap-to-confirm, same panel family as the menus ----
var settingsBtn = document.getElementById('settingsBtn');
var settingsPanel = document.getElementById('settingsPanel');
var speedSeg = document.getElementById('speedSeg');
var tapToggle = document.getElementById('tapConfirmToggle');
var soundToggle = document.getElementById('soundToggle');

function renderSettings() {
  speedSeg.querySelectorAll('button').forEach(function (b) {
    b.classList.toggle('on', Number(b.dataset.s) === speedMult);
  });
  soundToggle.setAttribute('aria-checked', String(!muted));
  tapToggle.setAttribute('aria-checked', String(tapConfirm));
}

speedSeg.addEventListener('click', function (e) {
  var b = e.target.closest('[data-s]');
  if (!b) return;
  speedMult = Number(b.dataset.s);
  try { localStorage.setItem('taptrade.speed', String(speedMult)); } catch (err) { /* ignore */ }
  renderSettings();
});
soundToggle.addEventListener('click', function () {
  muted = !muted;
  try { localStorage.setItem('taptrade.muted', muted ? '1' : '0'); } catch (err) { /* ignore */ }
  renderSettings();
});
tapToggle.addEventListener('click', function () {
  tapConfirm = !tapConfirm;
  if (!tapConfirm) armed = null; // drop any pending preview
  try { localStorage.setItem('taptrade.tapConfirm', tapConfirm ? '1' : '0'); } catch (err) { /* ignore */ }
  renderSettings();
});

function openSettingsPanel() {
  closeThemeMenu(); closeBetMenu(); closeHistPanel();
  renderSettings();
  settingsPanel.classList.add('open');
  settingsPanel.setAttribute('aria-hidden', 'false');
  settingsBtn.setAttribute('aria-expanded', 'true');
}
function closeSettingsPanel() {
  settingsPanel.classList.remove('open');
  settingsPanel.setAttribute('aria-hidden', 'true');
  settingsBtn.setAttribute('aria-expanded', 'false');
}
settingsBtn.addEventListener('click', function (e) {
  e.stopPropagation();
  if (settingsPanel.classList.contains('open')) closeSettingsPanel(); else openSettingsPanel();
});
document.addEventListener('click', function (e) {
  if (!settingsPanel.contains(e.target) && !settingsBtn.contains(e.target)) closeSettingsPanel();
});
renderSettings();

// ---- replay modal: animated approach + the authentic landing shot ----
var histModal = document.getElementById('histModal');
var replayCanvas = document.getElementById('replayCanvas');
var replayCtx = replayCanvas.getContext('2d');
var replayAnim = null;
var modalEntry = null;

function drawReplayFrame(e, frac) {
  // Faithful mini-chart: same seconds-to-dollars aspect as the live chart
  // (CFG.pxPerSec : CFG.pxPerDollar) and the real cell grid, so the replay
  // is geometrically the scene the landing shot captured — not a stylized fit.
  var w = replayCanvas.width, h = replayCanvas.height, pad = 18;
  var pts = e.line || [];
  var t0 = pts.length ? pts[0].t : e.cell.t1 - 8;
  var t1 = e.cell.t2 + 0.5;
  var pMin = e.cell.low, pMax = e.cell.high;
  for (var i = 0; i < pts.length; i++) {
    if (pts[i].p < pMin) pMin = pts[i].p;
    if (pts[i].p > pMax) pMax = pts[i].p;
  }
  var pxSec = (w - pad * 2) / (t1 - t0);
  // keep the game's aspect; only compress further if the price range overflows
  var pxDol = Math.min(pxSec * (CFG.pxPerDollar / CFG.pxPerSec),
                       (h - pad * 2) / Math.max(pMax - pMin, 0.2));
  var pMid = (pMin + pMax) / 2;
  var X = function (t) { return pad + (t - t0) * pxSec; };
  var Y = function (p) { return h / 2 - (p - pMid) * pxDol; };

  replayCtx.fillStyle = COLOR.bg;
  replayCtx.fillRect(0, 0, w, h);

  // the real cell grid, like the live chart
  replayCtx.lineWidth = 1;
  replayCtx.strokeStyle = COLOR.gridLine;
  var gt0 = Math.ceil(t0 / CFG.cellSeconds) * CFG.cellSeconds;
  for (var gt = gt0; gt <= t1; gt += CFG.cellSeconds) {
    var gx = Math.round(X(gt)) + 0.5;
    replayCtx.beginPath(); replayCtx.moveTo(gx, 0); replayCtx.lineTo(gx, h); replayCtx.stroke();
  }
  var rowLo = Math.floor((pMid - (h / 2) / pxDol) / CFG.cellDollars) * CFG.cellDollars;
  var rowHi = pMid + (h / 2) / pxDol;
  for (var gp = rowLo; gp <= rowHi; gp += CFG.cellDollars) {
    var gy = Math.round(Y(gp)) + 0.5;
    if (gy < 0 || gy > h) continue;
    replayCtx.beginPath(); replayCtx.moveTo(0, gy); replayCtx.lineTo(w, gy); replayCtx.stroke();
  }

  // the tapped cell; fills with the outcome once the line arrives
  var cx1 = X(e.cell.t1), cx2 = X(e.cell.t2), cy1 = Y(e.cell.high), cy2 = Y(e.cell.low);
  var done = frac >= 1;
  replayCtx.fillStyle = done ? (e.won ? COLOR.chip2 : COLOR.lossFill1) : COLOR.hoverFill;
  replayCtx.globalAlpha = done ? 0.9 : 1;
  replayCtx.fillRect(cx1, cy1, cx2 - cx1, cy2 - cy1);
  replayCtx.globalAlpha = 1;
  replayCtx.strokeStyle = done ? (e.won ? COLOR.ring : COLOR.lossGlow) : COLOR.hover;
  replayCtx.lineWidth = 1.5;
  replayCtx.strokeRect(cx1, cy1, cx2 - cx1, cy2 - cy1);

  // the line, drawn up to the current playhead
  if (pts.length > 1) {
    var upto = Math.max(1, Math.round(frac * (pts.length - 1)));
    replayCtx.save();
    replayCtx.strokeStyle = COLOR.line;
    replayCtx.lineWidth = 1.8; replayCtx.lineJoin = 'round';
    replayCtx.shadowColor = COLOR.lineGlow; replayCtx.shadowBlur = 6;
    replayCtx.beginPath();
    replayCtx.moveTo(X(pts[0].t), Y(pts[0].p));
    for (var j = 1; j <= upto; j++) replayCtx.lineTo(X(pts[j].t), Y(pts[j].p));
    replayCtx.stroke();
    replayCtx.fillStyle = COLOR.dot; replayCtx.shadowBlur = 10;
    replayCtx.beginPath();
    replayCtx.arc(X(pts[upto].t), Y(pts[upto].p), 3, 0, Math.PI * 2);
    replayCtx.fill();
    replayCtx.restore();
  }

  if (done) {
    replayCtx.fillStyle = e.won ? COLOR.betText : COLOR.lossText;
    replayCtx.font = 'bold 13px ' + MONO;
    replayCtx.textAlign = 'center'; replayCtx.textBaseline = 'middle';
    replayCtx.fillText(e.won ? '+' + fmtAmt(e.payout) : 'MISS',
                       (cx1 + cx2) / 2, (cy1 + cy2) / 2);
  }
}

function runReplay() {
  if (!modalEntry) return;
  if (replayAnim) { cancelAnimationFrame(replayAnim); replayAnim = null; }
  var e = modalEntry;
  if (REDUCED || !e.line || e.line.length < 2) { drawReplayFrame(e, 1); return; }
  var start = performance.now(), DUR = 1400;
  var tick = function (now) {
    var frac = Math.min(1, (now - start) / DUR);
    drawReplayFrame(e, frac);
    replayAnim = frac < 1 ? requestAnimationFrame(tick) : null;
  };
  replayAnim = requestAnimationFrame(tick);
}

function openHistModal(e) {
  modalEntry = e;
  var amtEl = document.getElementById('histCapAmt');
  amtEl.textContent = (e.won ? '+' : '−') + fmtAmt(e.won ? e.payout : e.stake);
  amtEl.className = 'num ' + (e.won ? 'w' : 'l');
  document.getElementById('histCapSub').textContent =
    fmtMult(e.mult) + ' · ' + fmtAmt(e.stake) + ' stake · ' + clockFromTs(e.ts);
  var shotEl = document.getElementById('histShot');
  if (e.shot) { shotEl.src = e.shot; shotEl.classList.remove('none'); }
  else shotEl.classList.add('none');
  histModal.classList.add('open');
  histModal.setAttribute('aria-hidden', 'false');
  runReplay();
}
function closeHistModal() {
  if (replayAnim) { cancelAnimationFrame(replayAnim); replayAnim = null; }
  histModal.classList.remove('open');
  histModal.setAttribute('aria-hidden', 'true');
  modalEntry = null;
}
document.getElementById('replayBtn').addEventListener('click', runReplay);
document.getElementById('histModalClose').addEventListener('click', closeHistModal);
histModal.addEventListener('click', function (e) { if (e.target === histModal) closeHistModal(); });

document.getElementById('balancePill').addEventListener('click', function () {
  if (IS_LIVE) return; // live balance is the wallet's, not ours to reset
  setBalance(CFG.startBalance);
  toast('Balance reset', '', 1.6);
});

(function warmup() {
  var t = -40;
  while (t < 0) {
    stepFeed(CFG.tick);
    history.push({ t: t, p: price });
    t += CFG.tick;
  }
  camPrice = price;
  dispPrice = price;
  updateVolEst();
})();


setBalance(balance);
requestAnimationFrame(frame);
