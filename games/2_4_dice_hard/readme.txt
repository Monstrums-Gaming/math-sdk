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

*** STAKE ACP BUILD with CENT-RESOLUTION (0.01x) payouts ***
The RGS accepts payouts down to 0.01x since 2026-08. The ACP's rejection of the
earlier 98%-RTP build (2026-08-12) contained ZERO grid errors across 192 whole-cent
modes — the grid objection is gone. What the ACP DOES enforce (each drawn from
that rejection) and this ladder is tuned to:

  (a) RTP band: 90.0% <= per-mode RTP <= 96.70% (recomputed from the LUT).
  (b) Cross-Mode RTP Consistency: max - min <= 0.50% — the STRICT reading
      (Kong Climb's approved 0.90% spread would fail this validator today).
  (c) Base Mode STD: per-mode payout std M*sqrt(w*(1-w)) >= 0.60x. This kills
      the high-win-chance tail (a 97%-chance 1.01x mode has std 0.17x); with
      RTP ~0.965 the floor binds at winChance ~71%.

Why cent resolution: on the coarse 0.1x grid the ceiling forces multiplier steps
that leave whole-point RTP gaps (Kong Climb spans 95.7-96.6%). Whole-cent snapping
pins every mode within half a point of the cap, which is what makes the strict
0.50% spread limit satisfiable across 130 modes.

We FLOOR-snap each multiplier onto the 0.01x grid to the largest value with
RTP <= 96.70%:

    multiplier  = largest 0.01x-grid value with (winChance% * mult) <= 96.70%
    payoutCents = multiplier * 100                  (a whole number of cents)

Compliance filter (130 modes)
-----------------------------
A mode is kept only when, after floor-snapping:

    payout > 1.00x                 (drop no-upside modes)
    RTP    in [96.25%, 96.70%]     (realised spread 0.45% < the 0.50% ACP limit)
    std    >= 0.62x                (margin over the 0.60x ACP Base-STD floor)

This yields 130 modes (65 win chances x over/under, winChance 2-70%; win chances
52/59/62/65 snap below the RTP floor and are skipped — slider UIs must snap to
the nearest published target) spanning 1.38x .. 48.35x. wincap = 48.35x, carried
by the 2%-chance modes under_02 / over_98. Min std 0.632x (under_70 / over_30 at
1.38x).

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
untouched (same modes, win chances, multipliers, LUT weights); only the
diceResult payload grows. Regenerate fairness.json after the prod rebuild.

Build
-----
Dev (readable books):
    env/bin/python games/2_4_dice_hard/run.py
Production (wipe library/ first if modes changed):
    COMPRESSION=1 RUN_FORMAT_CHECKS=1 env/bin/python games/2_4_dice_hard/run.py
then upload library/publish_files/{index.json, books_<mode>.jsonl.zst,
lookUpTable_<mode>_0.csv} via the ACP dashboard. Regenerate fairness.json
(fairness_manifest.py), docs/PAYTABLE.md (docs/gen_paytable.py) and
frontend_demo/dice_hard_rgs.json (frontend_demo/build_demo_data.py) after every
rebuild. provider_number is a placeholder (2) — set the ACP-assigned value before
the final upload. Bet levels are set in the ACP dashboard, not here.
