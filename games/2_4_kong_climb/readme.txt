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

The payout is the true dice multiplier, rounded to whole cents:

    payoutCents = round(9700 / winChance%)     (RTP 0.97)
    multiplier  = payoutCents / 100

A genuine dice multiplier (RTP/winChance) almost never lands on ACP's 0.1x LUT
grid (50% -> 1.94x, 3% -> 32.33x), and Stake's own reference dice (50% -> 1.88x)
doesn't either. So this game is flagged lut_grid_exempt and the SDK's grid check
is skipped for it (utils/rgs_verification.py::verify_lookup_format). RTP is
0.97 exactly where the win chance divides 9700, else within cent-rounding
(~+/-0.05%), as with any real dice game.

Range (192 modes)
-----------------
Every payout is kept >= 1.00x (no sub-stake "win"), i.e. winChance <= 97%:

    under_02 .. under_97   and   over_03 .. over_98

Range: 1.0x (97% chance) up to 48.5x (2% chance). wincap = 48.5x. The two
2%-chance modes (under_02, over_98) carry the "wincap" criteria.

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
