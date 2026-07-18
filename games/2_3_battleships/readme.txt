Battleships (2_3) — Stake-style Mines as per-click wagers
========================================================

WHAT IT IS
----------
A 5x5 board of 25 tiles. Some tiles are SHIPS (winning), the rest are MINES
(losing). It plays as **per-click independent wagers**, structurally identical to
Chicken Run (2_8) — each tile click is a SEPARATE `/wallet/play`:

  * reveal a SHIP  -> that wager is paid IMMEDIATELY at the current depth's
    multiplier, and the next (deeper) wager unlocks.
  * reveal a MINE  -> that wager loses and the run ends (RESET / NEW BOARD to start
    a fresh board). Previously-won reveals are already banked and unaffected.

The depth-k multiplier is the Mines cumulative-survival value (1.60x, 2.70x, 4.80x
...), so wagering deeper pays more but wins less often. There is NO cumulative
cash-out — each click settles itself; the frontend uses an END GAME / NEW BOARD
button instead of a cash-out. This is the v2 "honest interactive" model (cf. the v1
cumulative predetermined-reveal build), matching Stake's single-book RGS.

Direct-probability win/lose game (like dice 2_4, limbo 2_5, chicken run 2_8): no
board, no reels, no free spins, Rust optimiser disabled.

MODES: difficulty x depth  (ships = WINNING tiles; more ships = easier)
-----------------------------------------------------------------------
One bet mode per (difficulty, reveal-depth), each cost = 1.0. Depth = how many ships
already revealed this run. Publishable depths per difficulty = rungs below the
GLOBAL_MAX_MULT cap. 25 modes total:

    easy     15 ships / 10 mines   depths 1..10   easy_1 .. easy_10
    medium   12 ships / 13 mines   depths 1..7    medium_1 .. medium_7
    hard      8 ships / 17 mines   depths 1..5    hard_1 .. hard_5
    extreme   4 ships / 21 mines   depths 1..3    extreme_1 .. extreme_3

Mode name `<difficulty>_<depth>` is dot-free. `/wallet/play` on a mode returns a
single win/lose book; the frontend maps the player's tile click onto it.

THE LADDER + PROBABILITY
------------------------
Revealing k ships in a row survives with P(survive k) = prod_{i<k} (ships-i)/(25-i).
depth-k multiplier = floor_to_grid(RTP_TARGET / P(survive k)) (cumulative survival,
0.1x grid). Each mode wins with probability = the smallest-denominator rational a/b
whose realised RTP (a/b * multiplier) lands in [96.00%, 96.70%]
(`_simplest_fraction_in`); num_sims = b yields exactly a winning books, so the
published odds equal the book counts (optimiser off). num_sims stays small (<= ~1090).

Sample per-depth multipliers (x):
    easy    : 1.6 2.7 4.8 8.9 17.0 34.1 72.0 162.1 393.9 1050.4
    medium  : 2.0 4.3 10.0 24.6 64.7 184.9 585.7
    hard    : 3.0 10.3 39.6 174.3 915.5
    extreme : 6.0 48.2 554.8

PER-ROUND EVENTS (the frontend contract — integer cents)
--------------------------------------------------------
  outcome  : {result:"Win"|"Lose", difficulty, depth, ships, winChance, isWin,
              payoutMultiplierCents}
  finalWin : {amount}  (settled cents = payoutMultiplierCents on win, 0 on loss)

ACP RULES SATISFIED
-------------------
  1. 0.1x LUT grid (payouts floor-snapped; grid check ON).
  2. Per-mode RTP in [96.00%, 96.70%].
  3. Cross-mode RTP spread <= 1.00% (realised ~0.007).

BUILD / VERIFY
--------------
Dev (readable books):
  PYTHONPATH="$PWD" env/bin/python games/2_3_battleships/run.py
Release (upload-ready, per-mode num_sims — NUM_SIMS env is ignored):
  COMPRESSION=1 RUN_FORMAT_CHECKS=1 PYTHONPATH="$PWD" \
    env/bin/python games/2_3_battleships/run.py
Upload index.json + books_<mode>.jsonl.zst + lookUpTable_<mode>_0.csv (25 modes)
from library/publish_files/. Bet levels + gameID are set in the ACP dashboard.

Note: the repo's editable install path is stale, so PYTHONPATH="$PWD" (repo root) is
required when invoking run.py directly until `make setup` is re-run.
