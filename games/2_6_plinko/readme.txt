Plinko (2_6) — Stake-style Galton board
=======================================

Mechanic
--------
A ball drops through N rows of pegs and lands in one of N+1 bins. At each peg it
deflects left/right with equal probability, so the bin index k (number of right
deflections) is Binomial(N, 1/2) with probability C(N,k)/2**N. Each bin pays a
fixed multiplier; the payout table is symmetric (edges pay the most, centre the
least). There is no board to spin, no reels and no free-spin round.

This is a direct-probability game (like games/mystery_box, the dice game
games/2_4_dice_kong_climb and the limbo game games/2_5_limbo_frankenstein): the
odds are authored in game_config.py and the Rust optimiser is disabled. Published
odds equal the per-criteria book counts.

Modes: base product only (1 ball, cost 1.0)
-------------------------------------------
27 bet modes = rows {8..16} x difficulty {low, medium, high}, each named
base_r{NN}_{difficulty} (e.g. base_r08_low, base_r16_high). All cost 1.0.

  RTP = EV / cost = (1/2**N) * sum(C(N,k) * cells[k])

wincap = the single largest edge across all modes (carried by base_r16_high = 970x).
Each mode's own max_win = its edge (the corner bins).

An "expert" 4th tier was TRIED and REMOVED. Its near all-or-nothing shape (~99% of
drops at the 0.1x floor, a rare huge edge up to ~6400x) breaks Stake's 2-star risk
validators (CVaR / ETL / volatility) for rows 11..16: high_r16 = 970x PASSES 2-star
while expert_r11 = 340x FAILED it, so the reject is driven by the tail SHAPE, not the
edge magnitude. `high` already sits at the top of the 2-star volatility envelope, so
there is no 2-star room for a more-extreme tier -- the same wall that capped limbo at
100x. To add a spicier tier you must either target a higher star rating or reshape it
to high's risk discipline (raise the floor, spread the mid-tiers) so it is no more
volatile than high.

DEFERRED: the balls100 product
-------------------------------
The reference RGS also exposes balls100_* (100 balls at a 0.99x per-drop stake,
costMultiplier 99). It is NOT published as a math mode:
  * its round payout is a SUM of 100 draws -> astronomically many distinct totals
    (an unusable LUT), and the 0.99x stake is off the 0.1x grid;
  * its RTP is identical to the base drop (E[sum of 100 drops]*0.99 / 99 = E[drop]).
"Drop 100 balls" is an ACP bet-level / a frontend batch replay, exactly like limbo
pushing its streak/high bet-scaling tiers into the ACP bet-level template.

Payout-cell tables (game_config.py)
-----------------------------------
Each mode's payout_cells (length N+1) is symmetric, monotone toward the centre, on
the ACP 0.1x grid, and RTP-tuned:
  1. a difficulty-scaled edge sets the volatility (low..high = bigger edges),
     rounded to ~2 significant figures for clean multipliers;
  2. a coordinate-descent solver (_fit_cells) nudges the higher-weight inner bins on
     the 0.1x grid so the realised RTP lands near a shared 96.35% target;
  3. if an edge is so large that no in-band table exists, the solver lowers the edge
     to the largest grid value that admits one.

The real Stake tables run ~99% RTP (r16 "high" [1000,130,26,9,4,2,0.2,...] = 98.98%)
and the reference base_r16_expert "100000x" edge alone would be +305% RTP under a
binomial -- both impossible under ACP's 96.70% ceiling, hence the re-tune / edge caps.

ACP math rules (enforced server-side)
-------------------------------------
  1. 0.1x LUT grid: every cell*100 is a multiple of 10 (all cells >= 0.1x; there are
     no 0x/loss bins). lut_grid_exempt = False keeps the SDK grid check ON.
  2. RTP band (per-mode): 90%..96.70%. Every mode is pinned into [96.00%, 96.70%];
     the built set spans ~96.17-96.64% (a <= 0.47% spread), inside all three RTP rules.
  3. RTP consistency (cross-mode): variance (max-min) <= 1.00%.
  4. Risk / star-rating (Max Payout, Tail Probability, ETL, CVaR): CONFIRMED at upload
     -- the low/medium/high set (top edge high_r16 = 970x) PASSES 2-star on every row;
     the removed "expert" tier FAILED 2-star for rows 11..16 (see the tier note above).
     The reject is tail SHAPE, not edge size (high_r16 970x passes, expert_r11 340x did
     not). If a future tweak-ing of the tables trips these again, lower that difficulty's
     _DIFFICULTY[<d>]["edge8"]/"growth" and/or raise its "floor" (less all-or-nothing) in
     game_config.py and rebuild -- the same empirical loop limbo used.

Exact integer book counts
--------------------------
Optimiser off -> published odds equal the per-criteria book counts, so
num_sims * quota must be an exact integer. Bin probability is C(N,k)/2**N, so
num_sims = 2**N yields exactly C(N,k) books per bin. One Distribution per DISTINCT
payout value (bins sharing a multiplier are pooled): quota = (count + 0.5)/2**N so
int(num_sims*quota) == count (the floor-safe "+0.5" trick; get_sim_splits does
int(num_sims*quota)), the counts summing to 2**N. r16 = 65536 books/mode (one batch).

Mode NAME tokens are dot-free (base_r16_high). The ACP publisher parses <mode> out of
books_<mode>.jsonl.zst / lookUpTable_<mode>_0.csv, so a "." would collide with the
.jsonl.zst extension and the dashboard rejects the upload.

Per-round events
----------------
    gameSetup : {costMultiplier, difficulty, dropCount, maxWin(raw edge multiplier),
                 payoutCells[raw multipliers], productMode:"base", rows}
    dropBatch : {drops:[{ballIndex, binIndex, difficulty, dropIndex, payoutMultiplier
                 (raw), rows, tier:"win" if mult>=1 else "loss"}]}   (1 drop, base product)
    finalWin  : {amount(cents = multiplier*100), multiplier(raw)}
The authoritative LUT/hash payout is the SDK book payoutMultiplier (cents); the events
above are descriptive replay data for the frontend.

Build
-----
Dev (readable books):
    PYTHONPATH="$(pwd)" ./env/bin/python games/2_6_plinko/run.py
Production (compressed + format-checked):
    PYTHONPATH="$(pwd)" COMPRESSION=1 RUN_FORMAT_CHECKS=1 \
        ./env/bin/python games/2_6_plinko/run.py
Then upload library/publish_files/{index.json, books_<mode>.jsonl.zst,
lookUpTable_<mode>_0.csv} via the ACP dashboard. Bet levels (incl. the 100-ball batch
as a bet-size construct) and gameID are set in ACP, not here. provider_number is a
placeholder (2) pending the ACP-assigned value.

Frontend demo
-------------
frontend_demo/ replays the PUBLISHED odds in a self-contained browser Galton board:
build_demo_data.py reads library/publish_files + library/configs and writes
plinko_rgs.json (per-mode cells + binomial weights + rtp); plinko.html renders the
board and weighted-picks a bin by those weights (so realised RTP ~ published).
Rebuild the bundle after any math change:
    PYTHONPATH="$(pwd)" ./env/bin/python games/2_6_plinko/frontend_demo/build_demo_data.py
