Kong Climb (2_4) — Stake-style Dice
===================================

Mechanic
--------
Classic "Dice": a number is rolled on a 0–100 scale and the player bets that the
roll will be OVER or UNDER a chosen point on the slider. Each round has exactly
two outcomes — win (pays a fixed multiplier) or lose (pays 0). There is no board,
no reels and no free-spin round.

This is a direct-probability game (like games/mystery_box): the odds are authored
in game_config.py and the Rust optimiser is disabled. Published odds equal the
per-criteria book counts.

Canonical dice modes (over_NN / under_NN)
-----------------------------------------
This mirrors Stake's reference Dice config: one mode per integer slider target
NN, in each direction.

    under_NN  wins if roll < NN   ->  winChance = NN%
    over_NN   wins if roll > NN   ->  winChance = (100 - NN)%

The ACP enforces three math rules server-side (all learned from upload rejections):

  1. 0.1x LUT grid: every non-zero payout is an integer number of cents that is a
     multiple of 10 (a whole multiple of 0.1x).
  2. RTP band (per-mode): "Return to Player must be between 90% and 96.70%".
  3. RTP consistency (cross-mode): "RTP across all modes must be within +/-0.5% of
     each other", i.e. variance (max-min) <= 1.00%.
  There is NO volatility/hit-rate rule (compliant modes span 14-69% hit).

The true dice multiplier 0.97 / winChance sits at 97% RTP -- just over the 96.70%
cap -- and rarely lands on the grid. So we FLOOR-snap each multiplier onto the
0.1x grid to the largest value with RTP <= 96.70%:

    multiplier  = largest 0.1x-grid value with (winChance% * mult) <= 96.70%
    payoutCents = multiplier * 100                  (a multiple of 10)

The SDK grid check (utils/rgs_verification.py::verify_lookup_format) stays ON as a
regression guard -- lut_grid_exempt = False.

Compliance filter (72 modes)
----------------------------
A mode is kept only when, after floor-snapping:

    payout > 1.00x                 (drop no-upside modes)
    RTP    in [95.7%, 96.70%]      (>= 90%, <= 96.70%, AND a 0.90% spread so the
                                    cross-mode variance stays under the 1.00% cap)

The realised max RTP is 96.60%, so the floor is pinned at 95.70% to hold the whole
set inside a 0.90% spread. This yields 72 modes (36 win chances x over/under,
winChance 2-48%) spanning 1.1x .. 48.3x. wincap = 48.3x, carried by the 2%-chance
modes under_02 / over_98. Realised RTP ranges 95.7-96.6%, every mode on-grid and
inside all three rules. The tight RTP window (rule 3), not volatility, is what
bounds the mode count.

Exact integer book counts
-------------------------
For winChance = c%, reduce c/100 = W/N in lowest terms (g = gcd(c, 100),
W = c/g, N = 100/g). The mode's num_sims = N (<= 100) produces exactly W winning
books, so the published odds equal the win chance.

Quotas use a floor-safe "+0.5" trick — win = (W+0.5)/N, lose = (N-W+0.5)/N —
because get_sim_splits does int(num_sims*quota) and fills leftovers with
weighted-random picks; a naive W/N quota mis-floors some modes and would make
the RTP non-deterministic.

Per-round events
----------------
    diceResult : {direction, target, winChance, isWin, payoutMultiplier(cents)}
    finalWin   : {amount(cents)}   (amount = multiplier*100 on a win, else 0)

Build
-----
Dev (readable books):
    env/bin/python games/2_4_kong_climb/run.py
Production: set compression=True and run_conditions["run_format_checks"]=True in
run.py, then upload library/publish_files/{index.json, books_<mode>.jsonl.zst,
lookUpTable_<mode>_0.csv} via the ACP dashboard. Bet levels and gameID are set in
ACP, not here. provider_number is a placeholder (2) pending the ACP-assigned value.
