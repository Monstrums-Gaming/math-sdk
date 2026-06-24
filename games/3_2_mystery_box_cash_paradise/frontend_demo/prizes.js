// prizes.js
// -----------------------------------------------------------------------------
// Prize catalog for Cash Paradise (3_2_mystery_box_cash_paradise).
//
// This is a hand-copy of the generated frontend config
//   library/configs/config_fe_3_2_mystery_box_cash_paradise.json
// (the `symbols` paytable) plus the authored probabilities from readme.txt.
// The math-sdk remains the source of truth — if the prize table changes there,
// regenerate the config and update this file to match.
//
// `value` is the payout as a base-bet multiplier (x). In events / books the same
// number appears as `amount` scaled x100 (value 1.0 -> amount 100). The renderer
// does not depend on this table for results (events carry `prize`/`prizeName`);
// it is only used to draw the "all possible prizes" board.
// -----------------------------------------------------------------------------

export const BOX_COST = 4.98; // base-bet units, single "base" bet mode (matches game_config.py)

// `image` points at a prize PNG baked into the bundle (images/CP*.png) — a
// same-origin asset, so the art renders on the live RGS (whose CSP allows
// `img-src 'self'`) with no network call. The renderer prefers `image` and
// falls back to `emoji` if the file is missing.
export const PRIZES = [
  { id: "CP1", name: "$0.01 Voucher", value: 0.0, prob: 0.302, emoji: "🪙", image: "./images/CP1.png", note: "below RGS minimum → pays 0" },
  { id: "CP2", name: "$0.10 Voucher", value: 0.1, prob: 0.28, emoji: "🎫", image: "./images/CP2.png" },
  { id: "CP3", name: "$1 Voucher", value: 1.0, prob: 0.25, emoji: "💵", image: "./images/CP3.png" },
  { id: "CP4", name: "$2 Voucher", value: 2.0, prob: 0.05, emoji: "💵", image: "./images/CP4.png" },
  { id: "CP5", name: "$5 Voucher", value: 5.0, prob: 0.05, emoji: "💶", image: "./images/CP5.png" },
  { id: "CP6", name: "$10 Voucher", value: 10.0, prob: 0.05, emoji: "💷", image: "./images/CP6.png" },
  { id: "CP7", name: "$50 Voucher", value: 50.0, prob: 0.01, emoji: "💰", image: "./images/CP7.png" },
  { id: "CP8", name: "$100 Voucher", value: 100.0, prob: 0.006, emoji: "🤑", image: "./images/CP8.png" },
  { id: "CP9", name: "$1,000 Voucher", value: 1000.0, prob: 0.002, emoji: "💎", image: "./images/CP9.png", note: "max win / wincap" },
];

export const PRIZE_BY_ID = Object.fromEntries(PRIZES.map((p) => [p.id, p]));
