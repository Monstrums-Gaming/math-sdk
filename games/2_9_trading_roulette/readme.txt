TRADING ROULETTE (2_9) — design & build notes
=========================================

WHAT THE GAME IS
----------------
A zone board dressed as a market chart. The board's rows are price zones relative to the
round's start line; the player bets a CELL, a market index line animates for a few
seconds, and the ROW it crosses at the right edge decides the round. The row is CERTIFIED
in the book (`landRow` — the 2_8_market_crash `crashPoint` pattern made position-bearing),
so the chart is a rendering of the book, never a client-side invention.

Reference material: cloned from 2_8_market_crash (which was cloned from
2_7_prediction_market). Web app: monstrums-web-sdk apps/2-9-trading-roulette.

THE BOARD (15 landing rows, 21 bettable cells)
----------------------------------------------
landRow in [-7, +7]: 0 = exactly on the line; +/-1..6 fine rows nearest..farthest;
+/-7 = the off-scale tails ("over/under the line", beyond the fine rows).

  cell                    rows        pays   quoted     exact odds  RTP
  zone_o1 / zone_u1       {+-1}       10x    9/1        5/52        96.1538%
  zone_o2 / zone_u2       {+-2}       12x    11/1       7/87        96.5517%
  zone_o3 / zone_u3       {+-3}       14x    13/1       2/29        96.5517%
  zone_o4 / zone_u4       {+-4}       16x    15/1       5/83        96.3855%
  zone_o5 / zone_u5       {+-5}       17x    16/1       3/53        96.2264%
  zone_o6 / zone_u6       {+-6}       18x    17/1       3/56        96.4286%
  zone_bin_o / zone_bin_u {1..3}      4x     3/1        7/29        96.5517%
  zone_bout_o/ zone_bout_u{4..6}      5x     4/1        5/26        96.1538%
  zone_half_o/ zone_half_u{1..7}      2x     1/1        13/27       96.2963%
  zone_tail_o/ zone_tail_u{7}         8x     7/1        7/58        96.5517%
  zone_line               {0}         21x    20/1       4/87        96.5517%

Cross-mode RTP spread: 0.3979% (window [96.15%, 96.65%], both ACP readings satisfied).
Tamest mode (2.0x) payout std 0.9993 >= the 0.60 ACP Base-Volatility floor. Global
wincap = 21.0 (zone_line), so `wincap` events fire only on exact-line wins.

PER-MODE PINNED ODDS, NOT A COHERENT WHEEL
------------------------------------------
The quoted board odds cannot form one landing distribution (the two 1/1 halves alone
would take ~R of the mass, leaving the exact-line cell's 21x paying ~78%). Each cell's
win probability is therefore pinned independently — the limbo/2_8 Stern-Brocot descent
into [96.15%, 96.65%] — and the landing row is sampled CONDITIONAL on the pre-assigned
verdict. Consequence (stated in fairness.json): landing-row frequencies observed while
betting a cell are the mixture of the two published conditional laws at that cell's win
chance; the odds themselves derive from the LUT alone, and build_odds_bundle.py proves
mechanically that landRow cannot move them.

THE LANDING LAW (presentation + fairness data)
----------------------------------------------
Integer weights proportional to 1/multiplier, unit 85680 = lcm(8,10,12,14,16,17,18,21):

  |row|:   0     1     2     3     4     5     6     7
  weight:  4080  8568  7140  6120  5355  5040  4760  10710   (total 99466)

Win: draw from weights restricted to the zone. Lose: restricted to the complement. Both
conditional laws are audited per mode within 4 sigma (worst observed: 3.78 sigma,
deterministic build => permanent property).

SEEDS / BOOK COUNTS (inherited from 2_8, one delta)
---------------------------------------------------
N = k*b books, W = k*a winners per mode (N >= 5000, W >= 150; Fraction(W,N) == a/b
exactly; the +0.5 quotas computed from W/N, never a/b). DELTA vs 2_8: per-mode seed
offsets are keyed off the MODE INDEX, not payout cents — payout cents repeat across
over/under mirrors. Total build: 105,742 books.

THE FRONTEND CONTRACT (sequential wagers)
-----------------------------------------
One wager = one cell. Books are position-BEARING (zone + landRow), so two independent
books can contradict each other on one chart (both "Win" on disjoint zones). The web app
therefore plays a multi-cell chip layout as a QUEUE of sequential wagers — one book, one
line pass, one certified landing per cell (the tap-trade pump) — inside an emulated
countdown round loop. Nothing in the math side spans cells.

Book event order and payload (all multipliers/amounts in integer hundredths; winChance
alone is a probability; landRow a signed integer):

  lose:            zoneRound -> finalWin(0)
  win (non-line):  zoneRound -> finalWin(cents)
  win (zone_line): zoneRound -> wincap -> finalWin(2100)

  zoneRound: { index, type, result: "Win"|"Lose", isWin, zone: "<id>", landRow,
               payoutMultiplier: <cents>, winChance }

BUILD & VERIFY
--------------
  # dev (readable .json books)
  PYTHONPATH="$PWD" env/bin/python games/2_9_trading_roulette/run.py

  # production (mandatory: compressed books + RGS format checks)
  COMPRESSION=1 RUN_FORMAT_CHECKS=1 PYTHONPATH="$PWD" \
      env/bin/python games/2_9_trading_roulette/run.py

  # post-build auditor + odds bundle (library/odds_bundle.json)
  PYTHONPATH="$PWD" env/bin/python games/2_9_trading_roulette/build_odds_bundle.py

  # player-facing transparency manifest (publish_files/fairness.json)
  PYTHONPATH="$PWD" env/bin/python games/2_9_trading_roulette/fairness_manifest.py

  # web bundle with real certified landRow samples (frontend_demo/trading_roulette_rgs.json;
  # copy to apps/2-9-trading-roulette/src/assets/ and re-run its gen-odds-bundle.mjs)
  PYTHONPATH="$PWD" env/bin/python games/2_9_trading_roulette/frontend_demo/build_demo_data.py

PUBLISH ARTIFACTS (library/publish_files/)
------------------------------------------
index.json, 21x books_zone_<id>.jsonl.zst, 21x lookUpTable_zone_<id>_0.csv (uniform
weight 1). Non-RGS side artifacts: library/odds_bundle.json, publish_files/fairness.json,
frontend_demo/trading_roulette_rgs.json.
