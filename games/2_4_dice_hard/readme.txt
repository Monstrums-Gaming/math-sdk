Dice Hard (2_4) — Stake-style Dice
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

*** NON-STAKE BUILD — DOES NOT PASS STAKE ACP (two rule violations) ***
This variant is tuned to a 98% RTP ceiling with CENT-RESOLUTION (0.01x) payouts.
Stake's ACP dashboard re-checks both server-side and rejects on either:
  (a) RTP: it recomputes RTP from the LUT and HARD-REJECTS anything above 96.70%
      ("Return to Player must be between 90% and 96.70%"); this build is ~98%.
  (b) Grid: it requires every payout to be a multiple of 0.1x; this build pays
      whole cents (e.g. 1.01x = 101 cents), which is off that grid.
So this build CANNOT be published to Stake Engine — non-Stake / internal use only.
To revert to a Stake-legal build: RTP_CEIL=0.967, RTP_FLOOR=0.957, MIN_MULT=1.1,
snap to the 0.1x grid, and lut_grid_exempt=False in game_config.py, then rebuild.

Why cent resolution: on the coarse 0.1x grid the smallest payout above the 1x stake
is 1.1x, so a mode only has upside when winChance% * 1.1 <= ceiling — which caps
roll-under at winChance 89% (under_89); 90%+ can only snap to 1.0x (no profit) and
drop. Cent (0.01x) resolution lets high win chances pay a real small profit
(winChance 97% -> 1.01x), so BOTH directions reach target 97 (under_97 / over_03).

Two rules shape the ladder:

  1. 0.01x (whole-cent) grid: every non-zero payout is an integer number of cents
     (multiplier * 100), the SDK's native resolution. lut_grid_exempt = True
     disables the SDK's 0.1x-grid guard so these off-grid cents pass verification.
  2. RTP band (per-mode): every mode's realised RTP lands in [97.0%, 98.00%]. The
     tight window keeps the cross-mode spread <= 1.00% — a self-imposed balance
     choice here (NOT an ACP requirement in this non-Stake build).
  There is NO volatility/hit-rate rule (modes span a wide hit range).

We FLOOR-snap each multiplier onto the 0.01x grid to the largest value with
RTP <= 98.00%:

    multiplier  = largest 0.01x-grid value with (winChance% * mult) <= 98.00%
    payoutCents = multiplier * 100                  (a whole number of cents)

Compliance filter (192 modes)
-----------------------------
A mode is kept only when, after floor-snapping:

    payout > 1.00x                 (drop no-upside modes; smallest kept is 1.01x)
    RTP    in [97.0%, 98.0%]       (realised 97.18-98.00%, 0.82% spread)

Cent resolution snaps every mode just under 98.00%. This yields 192 modes (96 win
chances x over/under, winChance 2-97%) spanning 1.01x .. 49.0x. wincap = 49.0x,
carried by the 2%-chance modes under_02 / over_98. Realised RTP ranges 97.18-98.00%.
Only winChance 98%+ drop (a 1.00x snap = no upside).

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
    diceResult : {direction, target, winChance, isWin, payoutMultiplier(cents), roll}
    finalWin   : {amount(cents)}   (amount = multiplier*100 on a win, else 0)

Provably-fair roll (the `roll` field)
-------------------------------------
Each book stores the displayed dice result `roll` on the 00.00-100.00 scale (2
decimals), generated at simulation time with the per-sim seeded RNG (reset_seed),
so it is deterministic and reproducible -- a replay always shows the same number.
It is ALWAYS consistent with `isWin`:

    over_NN  win -> roll in (NN, 100.00]   lose -> roll in [0.00, NN]
    under_NN win -> roll in [0.00, NN)     lose -> roll in [NN, 100.00]

(matches the win rule: under wins if roll < NN, over wins if roll > NN; a tie at
NN is a loss.) On Stake Engine the provably-fair seed pair (client seed + hashed
server seed + nonce, HMAC-SHA256 -> float) selects WHICH book of a mode's lookup
table the RGS serves; this stored roll is that selected book's certified outcome,
so the number a player sees matches the RGS result and the odds/selection stay
provably fair. The roll is presentation only -- win/lose and payout are set by the
mode's book counts (win chance) and multiplier, which are UNCHANGED by adding it.

NOTE: adding `roll` is an event-structure change, so the books (and their hashes)
change -- a production rebuild + republish is required for it to go live. Odds are
untouched (same 192 modes, win chances, multipliers, LUT weights); only the
diceResult payload grows. Regenerate fairness.json after the prod rebuild.

Build
-----
Dev (readable books):
    env/bin/python games/2_4_kong_climb/run.py
Production: set compression=True and run_conditions["run_format_checks"]=True in
run.py, then publish library/publish_files/{index.json, books_<mode>.jsonl.zst,
lookUpTable_<mode>_0.csv} to your (non-Stake) target. NOTE: this 98% build is NOT
Stake-publishable — the ACP dashboard rejects RTP > 96.70%. provider_number is a
placeholder (2). Bet levels and gameID are set by the operator, not here.
