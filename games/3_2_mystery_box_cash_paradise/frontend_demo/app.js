// app.js
// -----------------------------------------------------------------------------
// Standalone, zero-build frontend for Cash Paradise (3_2_mystery_box_cash_paradise).
//
// Runs in two modes, auto-detected from the launch URL:
//   LIVE RGS  -> when rgs_url + sessionID are present, talks to the Stake Engine:
//                  /wallet/authenticate  -> balance + bet config (on load)
//                  /wallet/play          -> debit + a "round" (one math book)
//                  /wallet/end-round      -> finalize an active round
//   LOCAL SIM -> otherwise, draws a weighted-random prize from the prize table and
//                builds the SAME round shape the RGS returns, so the render path is
//                identical. Balance is tracked client-side. Fully offline.
//
// The live launch URL injects query params: sessionID, rgs_url, lang, device,
// currency, mode. Fetch / query-param / money-scaling patterns follow
// docs/simple_example/app_svelte.txt and docs/rgs_docs/RGS.md.
//
// IMPORTANT (RGS contract): the /wallet/play response carries the event list under
// `round.state` (NOT `round.events`), and `round.active` tells you whether the round
// still needs /wallet/end-round.
// -----------------------------------------------------------------------------

import { PRIZES, PRIZE_BY_ID, BOX_COST } from "./prizes.js";

// Money in the RGS is an integer with 6 decimal places: 1_000_000 == 1.0 unit.
const API_MULTIPLIER = 1_000_000;
// Event amounts (and round.payoutMultiplier) are base-bet multipliers x100: 100 == 1.0x.
const EVENT_SCALE = 100;
// Starting balance for LOCAL SIM (currency units).
const LOCAL_START_BALANCE = 1000;

// ---- query params -----------------------------------------------------------
const getParam = (k) => new URLSearchParams(window.location.search).get(k);
const RGS_URL = getParam("rgs_url");
const SESSION_ID = getParam("sessionID");
const LANG = getParam("lang") || getParam("language") || "en";
const CURRENCY = getParam("currency") || "USD";
const MODE = getParam("mode") || "base"; // single bet mode in game_config.py

// Auto-detect: live only when both launch params are present, else local.
const IS_LIVE = Boolean(RGS_URL && SESSION_ID);

// ---- currency formatting (from docs/rgs_docs/RGS.md) ------------------------
const CURRENCY_META = {
  USD: { symbol: "$", decimals: 2 }, CAD: { symbol: "CA$", decimals: 2 },
  JPY: { symbol: "¥", decimals: 0 }, EUR: { symbol: "€", decimals: 2 },
  RUB: { symbol: "₽", decimals: 2 }, CNY: { symbol: "CN¥", decimals: 2 },
  PHP: { symbol: "₱", decimals: 2 }, INR: { symbol: "₹", decimals: 2 },
  IDR: { symbol: "Rp", decimals: 0 }, KRW: { symbol: "₩", decimals: 0 },
  BRL: { symbol: "R$", decimals: 2 }, MXN: { symbol: "MX$", decimals: 2 },
  DKK: { symbol: "KR", decimals: 2, symbolAfter: true },
  PLN: { symbol: "zł", decimals: 2, symbolAfter: true },
  VND: { symbol: "₫", decimals: 0, symbolAfter: true },
  TRY: { symbol: "₺", decimals: 2 },
  CLP: { symbol: "CLP", decimals: 0, symbolAfter: true },
  ARS: { symbol: "ARS", decimals: 2, symbolAfter: true },
  PEN: { symbol: "S/", decimals: 2, symbolAfter: true },
  XGC: { symbol: "GC", decimals: 2 }, XSC: { symbol: "SC", decimals: 2 },
};
function fmtMoney(amount, currency = state.currency) {
  const m = CURRENCY_META[currency] ?? { symbol: currency, decimals: 2, symbolAfter: true };
  const s = Number(amount).toFixed(m.decimals);
  return m.symbolAfter ? `${s} ${m.symbol}` : `${m.symbol}${s}`;
}

// ---- DOM --------------------------------------------------------------------
const el = (id) => document.getElementById(id);
const ui = {
  banner: el("banner"), modeBadge: el("modeBadge"), balance: el("balance"), box: el("box"),
  prizeCard: el("prizeCard"), prizeEmoji: el("prizeEmoji"),
  prizeName: el("prizeName"), prizeId: el("prizeId"),
  winBanner: el("winBanner"), winLabel: el("winLabel"), winAmount: el("winAmount"),
  betSelect: el("betSelect"), openBtn: el("openBtn"), costHint: el("costHint"),
  prizeList: el("prizeList"), prizeSummary: el("prizeSummary"),
  playJson: el("playJson"), endJson: el("endJson"),
};

// ---- state ------------------------------------------------------------------
const state = {
  phase: "rest", // rest | playing
  balanceApi: 0, // balance in RGS integer units (6 decimals)
  currency: CURRENCY,
  bet: API_MULTIPLIER, // base bet in RGS integer units
  hasOpenRound: false, // a live round awaiting /end-round
};

// ---- money helpers ----------------------------------------------------------
const toUnits = (apiAmount) => apiAmount / API_MULTIPLIER; // RGS int -> currency units
const toApi = (units) => Math.round(units * API_MULTIPLIER); // currency units -> RGS int
const betUnits = () => toUnits(state.bet);

function setBalanceApi(apiAmount) {
  state.balanceApi = apiAmount;
  ui.balance.textContent = fmtMoney(toUnits(apiAmount));
}

// =============================================================================
// LIVE RGS client (pattern from docs/simple_example/app_svelte.txt)
// =============================================================================
async function rgsCall(endpoint, body) {
  const res = await fetch(`https://${RGS_URL}${endpoint}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const json = await res.json().catch(() => ({}));
  if (!res.ok || json?.statusCode) {
    throw new Error(json?.statusCode || json?.error || `HTTP ${res.status}`);
  }
  return json;
}

const liveAuth = () =>
  rgsCall("/wallet/authenticate", { sessionID: SESSION_ID, language: LANG });
const livePlay = () =>
  rgsCall("/wallet/play", { sessionID: SESSION_ID, mode: MODE, currency: CURRENCY, amount: state.bet });
const liveEndRound = () => rgsCall("/wallet/end-round", { sessionID: SESSION_ID });

// =============================================================================
// LOCAL SIM — mirrors the math engine: weighted draw -> same event sequence
// =============================================================================

// winLevel buckets (lower bound, base-bet multiplier x) — matches the engine's 1..10 scale.
const WIN_LEVEL_BOUNDS = [0, 0.1, 1, 2, 5, 15, 30, 50, 100, 1000];
function winLevelFor(valueX) {
  let level = 1;
  for (let i = 0; i < WIN_LEVEL_BOUNDS.length; i++) {
    if (valueX >= WIN_LEVEL_BOUNDS[i]) level = i + 1;
  }
  return level;
}

function drawPrize() {
  const r = Math.random();
  let acc = 0;
  for (const p of PRIZES) {
    acc += p.prob;
    if (r < acc) return p;
  }
  return PRIZES[PRIZES.length - 1]; // floating-point safety net
}

// Build the exact event sequence the math engine emits for a drawn prize.
function buildEvents(prize) {
  const amount = Math.round(prize.value * EVENT_SCALE); // x100 base-bet units
  const events = [
    { index: 0, type: "mysteryReveal", prize: prize.id, prizeName: prize.name, amount },
  ];
  if (prize.id === "CP9") events.push({ type: "wincap", amount });
  if (amount > 0) {
    events.push({
      type: "winInfo",
      totalWin: amount,
      wins: [{ win: amount, positions: [], meta: { prize: prize.id, prizeName: prize.name } }],
    });
  }
  events.push({ type: "setWin", amount, winLevel: winLevelFor(prize.value) });
  events.push({ type: "setTotalWin", amount });
  events.push({ type: "finalWin", amount });
  return events.map((e, i) => ({ ...e, index: i })); // re-index sequentially
}

// Returns the same { round, balance } shape as /wallet/play.
function localPlay() {
  const cost = betUnits() * BOX_COST;
  state.balanceApi -= toApi(cost); // debit the box cost

  const prize = drawPrize();
  const events = buildEvents(prize);
  const payoutMultiplier = Math.round(prize.value * EVENT_SCALE);
  const winUnits = prize.value * betUnits();
  state.balanceApi += toApi(winUnits); // credit the win (settled immediately, like active:false)

  return {
    round: {
      betID: Math.floor(Math.random() * 1e9),
      amount: state.bet,
      payout: toApi(winUnits),
      payoutMultiplier,
      active: false,
      mode: MODE,
      state: events,
    },
    balance: { amount: state.balanceApi, currency: state.currency },
  };
}

function localAuth() {
  state.balanceApi = toApi(LOCAL_START_BALANCE);
  return {
    balance: { amount: state.balanceApi, currency: state.currency },
    config: {
      // Single fixed base bet of 1.0 -> box always costs 1.0 x box_cost.
      defaultBetLevel: API_MULTIPLIER,
      betLevels: [API_MULTIPLIER],
    },
    round: null,
  };
}

// ---- helpers ----------------------------------------------------------------
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function toast(msg) {
  const t = document.createElement("div");
  t.className = "toast";
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 4000);
}

function setBusy(busy) {
  state.phase = busy ? "playing" : "rest";
  ui.openBtn.disabled = busy;
  // betSelect stays permanently disabled (fixed bet) — see populateBetLevels().
}

function resetStage() {
  ui.box.dataset.state = "closed";
  ui.prizeCard.hidden = true;
  ui.winBanner.hidden = true;
  ui.winBanner.removeAttribute("data-jackpot");
}

// ---- event replay -----------------------------------------------------------
// One round = an ordered list of events. Walk them in `index` order and animate.
// Win amount in currency = (finalWin.amount / 100) * baseBet.
async function playEvents(events) {
  const ordered = [...events].sort((a, b) => (a.index ?? 0) - (b.index ?? 0));
  let isJackpot = false;
  let winLevel = 0;
  let finalAmountX100 = 0;

  for (const ev of ordered) {
    switch (ev.type) {
      case "mysteryReveal":
        await revealPrize(ev.prize, ev.prizeName);
        break;
      case "wincap":
        isJackpot = true; // CP9 — the $1,000 voucher
        break;
      case "setWin":
        winLevel = ev.winLevel ?? winLevel;
        break;
      case "finalWin":
        finalAmountX100 = ev.amount ?? 0;
        break;
      // winInfo / setTotalWin carry the same totals; nothing extra to draw here.
    }
  }

  const winMultiplier = finalAmountX100 / EVENT_SCALE; // base-bet multiplier (x)
  const winCurrency = winMultiplier * betUnits();
  showWin(winCurrency, winMultiplier, winLevel, isJackpot);
}

async function revealPrize(prizeId, prizeName) {
  const meta = PRIZE_BY_ID[prizeId] || { emoji: "🎁" };
  ui.box.dataset.state = "opening";
  await sleep(420);
  ui.box.dataset.state = "open";
  await sleep(180);
  setPrizeIcon(ui.prizeEmoji, meta);
  // Use the prize-table name, falling back to the event/id name.
  ui.prizeName.textContent = meta.name || prizeName || prizeId;
  ui.prizeId.textContent = prizeId;
  ui.prizeCard.hidden = false;
  ui.box.dataset.state = "revealed";
  await sleep(450);
}

// Build a prize's icon node: the bundled prize image (prizes.js `image` →
// images/CP*.png) when present, otherwise the emoji. If the image fails to load it
// swaps itself out for the emoji so we never show a broken glyph. Built with the
// DOM (no inline onerror) to stay CSP-safe on the Stake Engine.
function makePrizeIcon(meta) {
  const emoji = (meta && meta.emoji) || "🎁";
  if (meta && meta.image) {
    const img = document.createElement("img");
    img.src = meta.image;
    img.alt = meta.name || "";
    img.loading = "lazy";
    img.addEventListener("error", () => img.replaceWith(document.createTextNode(emoji)));
    return img;
  }
  return document.createTextNode(emoji);
}

// Render a prize's icon into `node` (used by the reveal card).
function setPrizeIcon(node, meta) {
  node.replaceChildren(makePrizeIcon(meta));
}

function showWin(winCurrency, winMultiplier, winLevel, isJackpot) {
  ui.winBanner.hidden = false;
  if (winCurrency <= 0) {
    ui.winLabel.textContent = "NO WIN";
    ui.winAmount.textContent = fmtMoney(0);
    ui.winBanner.dataset.level = "0";
    return;
  }
  ui.winLabel.textContent = isJackpot ? "JACKPOT!" : "YOU WON";
  ui.winAmount.textContent = `${fmtMoney(winCurrency)}  (${winMultiplier}x)`;
  ui.winBanner.dataset.level = winLevel >= 6 ? "big" : "normal";
  if (isJackpot) ui.winBanner.dataset.jackpot = "true";
}

// ---- main action ------------------------------------------------------------
async function openBox() {
  if (state.phase !== "rest") return;
  setBusy(true);
  resetStage();

  try {
    // Finalize any still-open live round before starting a new one.
    if (IS_LIVE && state.hasOpenRound) await finalizeRound();

    const resp = IS_LIVE ? await livePlay() : localPlay();
    ui.playJson.textContent = JSON.stringify(resp, null, 2);
    if (resp.balance) setBalanceApi(resp.balance.amount);

    const round = resp.round || {};
    // RGS returns the event list under `state`; older/local shapes may use `events`.
    const events = round.state ?? round.events ?? [];
    if (!events.length) throw new Error("No events in round");

    await playEvents(events);

    // Finalize only when the RGS says the round is still active.
    if (IS_LIVE && round.active === true) {
      state.hasOpenRound = true;
      await finalizeRound();
    }
  } catch (err) {
    console.error(err);
    toast(rgsErrorMessage(err.message));
  } finally {
    setBusy(false);
  }
}

async function finalizeRound() {
  const resp = await liveEndRound();
  ui.endJson.textContent = JSON.stringify(resp, null, 2);
  if (resp.balance) setBalanceApi(resp.balance.amount);
  state.hasOpenRound = false;
}

function rgsErrorMessage(code) {
  const map = {
    ERR_IS: "Invalid or expired session.",
    ERR_IPB: "Insufficient balance.",
    ERR_VAL: "Invalid request.",
    ERR_ATE: "Authentication failed.",
    ERR_GLE: "Gambling limit exceeded.",
    ERR_LOC: "Invalid player location.",
    ERR_GEN: "Server error, try again.",
    ERR_MAINTENANCE: "RGS under maintenance.",
  };
  return map[code] || `Error: ${code}`;
}

// ---- bet level (locked) -----------------------------------------------------
// This game has a single fixed base bet so the box is always its full cost.
// Live mode uses the RGS defaultBetLevel; Local mode uses 1.0 (see localAuth).
// The <select> is rendered with one option and kept disabled.
function populateBetLevels(config) {
  const level = config?.defaultBetLevel || config?.betLevels?.[0] || API_MULTIPLIER;
  state.bet = level;
  ui.betSelect.innerHTML = "";
  const opt = document.createElement("option");
  opt.value = String(level);
  opt.textContent = fmtMoney(toUnits(level));
  ui.betSelect.appendChild(opt);
  ui.betSelect.value = String(level);
  ui.betSelect.disabled = true; // fixed bet — not player-selectable
  updateCostHint();
}

function updateCostHint() {
  const cost = betUnits() * BOX_COST;
  ui.openBtn.textContent = `Open Box · ${fmtMoney(cost)}`;
  ui.costHint.textContent =
    `Cost = base bet ${fmtMoney(betUnits())} × ${BOX_COST} (mode "${MODE}"). Target RTP 85%.`;
}

// ---- prize board ------------------------------------------------------------
function renderPrizeBoard() {
  ui.prizeList.innerHTML = "";
  for (const p of PRIZES) {
    const li = document.createElement("li");

    const icon = document.createElement("span");
    icon.className = "pemoji";
    icon.appendChild(makePrizeIcon(p)); // prize image (with emoji fallback) or emoji

    const name = document.createElement("span");
    name.className = "pname";
    name.textContent = p.name;
    if (p.note) {
      const note = document.createElement("span");
      note.className = "pnote";
      note.textContent = `(${p.note})`;
      name.append(" ", note);
    }

    const prob = document.createElement("span");
    prob.className = "pprob";
    prob.textContent = `${(p.prob * 100).toFixed(p.prob < 0.01 ? 1 : 0)}%`;

    li.append(icon, name, prob);
    ui.prizeList.appendChild(li);
  }
  if (ui.prizeSummary) {
    ui.prizeSummary.textContent = `All possible prizes (${PRIZES.length})`;
  }
}

// ---- init -------------------------------------------------------------------
function setModeBadge() {
  ui.modeBadge.textContent = IS_LIVE ? "LIVE RGS" : "LOCAL SIM";
  ui.modeBadge.dataset.mode = IS_LIVE ? "live" : "local";
}

async function init() {
  state.currency = CURRENCY;
  ui.balance.textContent = "—";
  setModeBadge();
  renderPrizeBoard(); // prizes + baked-image art from prizes.js
  updateCostHint();
  resetStage();

  ui.betSelect.addEventListener("change", () => {
    state.bet = Number(ui.betSelect.value);
    updateCostHint();
  });
  ui.openBtn.addEventListener("click", openBox);
  ui.box.addEventListener("click", () => { if (!ui.openBtn.disabled) openBox(); });
  ui.box.addEventListener("keydown", (e) => {
    if ((e.key === "Enter" || e.key === " ") && !ui.openBtn.disabled) openBox();
  });

  try {
    const resp = IS_LIVE ? await liveAuth() : localAuth();
    state.currency = resp.balance?.currency || CURRENCY;
    setBalanceApi(resp.balance?.amount ?? 0);
    populateBetLevels(resp.config);
    ui.openBtn.disabled = false;
    if (!IS_LIVE) {
      ui.banner.hidden = false;
      ui.banner.innerHTML =
        "Running in <b>LOCAL SIM</b> — outcomes are drawn client-side from the prize " +
        "table (no RGS). Launch with <code>?rgs_url=…&sessionID=…</code> for LIVE RGS.";
    }
    // Resume a still-open live round if the session left one active.
    if (IS_LIVE && resp.round && resp.round.active === true) {
      state.hasOpenRound = true;
    }
  } catch (err) {
    console.error(err);
    ui.banner.hidden = false;
    ui.banner.innerHTML =
      "Could not authenticate with the RGS. Check <code>rgs_url</code> / " +
      "<code>sessionID</code>, or drop them to use LOCAL SIM.";
    toast(rgsErrorMessage(err.message));
  }
}

init();
