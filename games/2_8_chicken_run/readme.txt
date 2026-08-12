Chicken Run (2_8) — Stake-style Chicken Road (per-lane wagers)
=============================================================

Mechanic
--------
Help the chicken cross as many lanes as possible. Each press of PLAY is a SEPARATE,
INDEPENDENT wager on crossing the next lane:

  - Safe crossing -> that wager is paid immediately at the lane's multiplier, and the
    next lane becomes available.
  - Hit by a car  -> that wager loses and the run returns to the start.

Previously-won lanes are already settled and unaffected. The lane multiplier is NOT a
cumulative cash-out — it is the standalone payout for that one lane's wager. Each
wager runs at ~97% RTP (published, capped at the ACP 96.70% ceiling). GO TO START
resets the chicken to lane 1 without placing a wager.

This is a direct-probability win/lose game (like the dice 2_4 and limbo 2_5 games):
no board, no reels, no free spins, Rust optimiser disabled.

Modes: 72 = 3 difficulties x 24 lanes
-------------------------------------
easy_1..24, medium_1..24, hard_1..24. Mode <difficulty>_<lane> = "wager on crossing
to lane n": pays ladder[difficulty][n] on a win, 0 on a hit. One /wallet/play on a
mode returns a single win/lose book; the frontend animates the crossing. Matches the
real Stake config exactly.

Lane multipliers (max per difficulty)
-------------------------------------
  Easy   1.0x  .. 23.8x   (24 lanes)
  Medium 1.1x  .. 548x    (24 lanes)
  Hard   1.2x  .. 918x    (24 lanes)

The ladders rise smoothly (geometric) from the lane-1 value to the stated max,
floor-snapped onto the 0.1x grid and strictly increasing. They are DERIVED to spec:
swap the `_LADDERS` literals in game_config.py for the real game's exact 72
multipliers for 1:1 parity — nothing else changes.

Probability & exact book counts
-------------------------------
Each mode wins with probability = the smallest-denominator rational a/b whose realised
RTP (a/b * payout) lands in [96.00%, 96.70%] (limbo's _simplest_fraction_in). Then
num_sims = b yields exactly a winning books, so published odds equal the book counts
(optimiser off). num_sims stays tiny (<= ~950).

ACP rules satisfied
-------------------
  1. 0.1x LUT grid (payouts floor-snapped; grid check ON).
  2. Per-mode RTP in [96.00%, 96.70%].
  3. Cross-mode RTP spread <= 1.00% (realised ~0.69%).

Per-round events
----------------
  outcome  : {result:"Win"|"Lose", difficulty, lane, winChance, isWin, payoutMultiplier}
  finalWin : {amount(cents), ...}

Build
-----
Dev (readable books):
  PYTHONPATH="$(pwd)" env/bin/python games/2_8_chicken_run/run.py
Production / verification (compressed + RGS format checks + book<->LUT hash):
  COMPRESSION=1 RUN_FORMAT_CHECKS=1 PYTHONPATH="$(pwd)" \
    env/bin/python games/2_8_chicken_run/run.py
Then upload library/publish_files/{index.json, books_<mode>.jsonl.zst,
lookUpTable_<mode>_0.csv} via the ACP dashboard. Bet levels + gameID are set in ACP.
provider_number is a placeholder (2) pending the ACP-assigned value.

Relationship to 2_7_chicken_crossing
------------------------------------
2_7 is the v1 predetermined-reveal build (one book decides the whole run; the player
watches). 2_8 is v2: each lane is its own wager, so pressing PLAY genuinely advances
and pays per lane — the honest, interactive model that fits Stake's single-book RGS.
Both are kept.
