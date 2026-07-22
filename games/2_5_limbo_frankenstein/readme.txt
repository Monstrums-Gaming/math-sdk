Limbo Frankenstein (2_5) — Stake-style Limbo
============================================

Mechanic
--------
Classic "Limbo": the player picks a target multiplier T; a crash multiplier is
rolled and the round WINS T* (times the stake) if the roll >= T, otherwise pays 0.
Each round has exactly two outcomes — win (pays a fixed multiplier) or lose (0).
There is no board, no reels and no free-spin round.

This is a direct-probability game (like games/mystery_box and the dice game
games/2_4_dice_kong_climb): the odds are authored in game_config.py and the Rust
optimiser is disabled. Published odds equal the per-criteria book counts.

Modes: base tier only (cost 1.0), target ladder capped at 100x
--------------------------------------------------------------
Each bet mode is one (base, target T, cost 1). The LUT win payout is W = T and the
win probability is p, so:

    RTP = EV / cost = (p * W) / 1 = p * T

wincap = max(W) = 100, carried by base_100.00.

TARGET WINDOW = 1.40x .. 100x (Stake risk / star-rating validators)
-------------------------------------------------------------------
A Limbo mode is all-or-nothing (win T x, else 0), which the risk validators squeeze
from BOTH ends:

  CEILING 100x -- ~100% of a mode's RTP sits in its single win, so any target >= 150x
    fails Expected-Tail-Liability (ETL 40x) and CVaR at BOTH 2- and 3-star (base_100
    passes ETL-40x, base_150 fails it; base_800 also breaches CVaR).

  FLOOR 1.40x -- the game's "Base Volatility (Std Dev)" is rated off its TAMEST mode
    and must be >= 0.60. A two-outcome payout has std = sqrt(0.96*T - 0.9216), so
    T = 1.10/1.20/1.30 give 0.36/0.48/0.57 (below 0.60) and drag the whole game under
    the floor (all modes then report as failing). T = 1.40 is the first target >= 0.60
    (std 0.649), so the ladder starts there.

Net: 27 modes (targets 1.40x .. 100x), max win 100x, inside the 2-star band on every
metric. NOTE: this window is narrow and inherent to single-outcome Limbo -- if a later
validator pass still fails volatility for every mode, no fixed-target mode can reach
0.60 and the mechanic must change (roll a spread of outcomes per round, not T x-or-0).

The former streak (cost 2/5) and high (cost 100) tiers were REMOVED. They only
rescaled the bet, but the risk validators read the raw payout W absolutely, so cost
100 inflated modest targets into 5,000x-50,000x payouts that breached Max-Payout
(high_500 = 50,000x), Tail-Probability (high_50 pays 5,000x ~1.9% of the time) and
ETL-10k. Bet-size scaling is an ACP BET-LEVEL concern (dashboard template), NOT a
published mode -- offer the base targets and let the operator set bet levels in ACP.

Mode NAME tokens are dot-free (base_1_10, base_100_00), NOT dotted. The ACP publisher
parses <mode> out of books_<mode>.jsonl.zst / lookUpTable_<mode>_0.csv, so a "." in a
name collides with the .jsonl.zst extension and the dashboard rejects the upload
("Mode: base_1.10 error in published files : io error"). game_config.py builds names
as f"{tier}_{target:.2f}".replace(".", "_"); keep them dot-free.

ACP math rules (enforced server-side)
-------------------------------------
  1. 0.1x LUT grid: every non-zero payout is an integer number of cents that is a
     multiple of 10. Here W*100 must be a multiple of 10, so we keep GRID-ALIGNED
     targets only and drop any off-grid mode (no floor-snapping). Dropped fine base
     targets: 1.05, 1.15, 1.25, 1.35, 1.45, 2.25.
     lut_grid_exempt = False keeps the SDK grid check ON as a regression guard.
  2. RTP band (per-mode): "Return to Player must be between 90% and 96.70%".
  3. RTP consistency (cross-mode): "RTP within +/-0.5% of each other", i.e.
     variance (max-min) <= 1.00%.
  4. Risk / star-rating: Max Payout, Tail Probability, ETL and CVaR caps -> the 100x
     target ceiling above (all 30 modes clear the 2-star band).

We pin every realised RTP into [96.00%, 96.70%] -> the built set spans
0.9600-0.9667 (a 0.67% spread), safely inside all three RTP rules. 27 base modes
survive (targets 1.40x .. 100.00x).

Exact integer book counts
-------------------------
Optimiser off -> published odds equal the per-criteria book counts, so
num_sims * quota must be an exact integer. For each target we pick the
SMALLEST-denominator rational p = a/b whose realised RTP (a/b)*T lands in
[96.00%, 96.70%] (game_config.py::_simplest_fraction_in). num_sims = b yields
exactly a winning books. Numerator-1 fractions win for large targets, so every
num_sims stays small (base_100 -> 1/104) and each mode fits a
single batch (exact split). Quotas use the floor-safe "+0.5" trick because
get_sim_splits does int(num_sims*quota).

Per-round events
----------------
    winInfo  : {isWin, payoutMultiplier(cents = W*100), totalWin(cents),
                target, winChance(probability)}   (emitted every round)
    finalWin : {amount(cents)}   (amount = W*100 on a win, else 0)

Build
-----
Dev (readable books):
    PYTHONPATH="$(pwd)" ./env/bin/python games/2_5_limbo_frankenstein/run.py
Production (compressed + format-checked):
    PYTHONPATH="$(pwd)" COMPRESSION=1 RUN_FORMAT_CHECKS=1 \
        ./env/bin/python games/2_5_limbo_frankenstein/run.py
Then upload library/publish_files/{index.json, books_<mode>.jsonl.zst,
lookUpTable_<mode>_0.csv} via the ACP dashboard. Bet levels (the bet-size scaling
that replaces the old streak/high tiers) and gameID are set in ACP, not here.
provider_number is a placeholder (2) pending the ACP-assigned value.
