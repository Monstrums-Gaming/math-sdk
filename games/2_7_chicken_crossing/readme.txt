Chicken Crossing (2_7) — Stake-style Chicken Road
=================================================

Mechanic
--------
A chicken crosses a road one lane ("step") at a time. Every step it survives raises
a cash-out multiplier; if a car hits it, the round pays 0. There is no board, no
reels and no free-spin round.

This is a direct-probability game (like the dice / limbo / plinko games): the odds
are authored in game_config.py from the per-difficulty survival ladders and the Rust
optimiser is disabled. Published odds equal the per-criteria book counts.

Modes: one bet mode per difficulty
----------------------------------
Four modes — easy / medium / hard / daredevil — each cost 1.0. Each mode is a
MULTI-OUTCOME distribution (like plinko): one Distribution per distinct cash-out
multiplier, plus a single loss ("0") outcome. Mode names are the plain difficulty
strings (dot-free — the ACP publisher parses <mode> out of books_<mode>.jsonl.zst).

The ladder (authoritative)
--------------------------
Each difficulty has a per-step cumulative survival probability and

    payoutMultiplier = 0.97 / cumulativeSurvivalProbability

so the theoretical RTP of cashing out at ANY step is exactly 97%. The full ladders
(hard-coded in game_config.py) include huge upper-tail steps; a global 2000x cap
(GLOBAL_MAX_MULT) drops every step at or above the cap, leaving only publishable
rungs:

    Easy       24 steps, max   24.25x   (nothing capped)
    Medium     21 steps, max  557.75x   (round 21 = 2231.00x  capped)
    Hard       17 steps, max  920.29x   (rounds 17-19 capped, incl. 51536.10x)
    Daredevil  10 steps, max 1055.84x   (rounds 10-14 capped, incl. 3170697.20x)

The original uncapped Daredevil maximum (3,170,697.20x) is NEVER published (a
_validate assertion guards this).

Grid snapping + probability adjustment
--------------------------------------
Raw multipliers are not on the ACP 0.1x grid (e.g. 1.01042, 24.25), so each is
FLOOR-snapped onto the grid (snapped = floor(raw*10)/10, cents a multiple of 10).
Floor-snapping lowers the multiplier, so the per-step reach probability is set to

    rho_k = RTP_TARGET / snapped_k

which pins the realised per-step RTP back to RTP_TARGET regardless of snapping
(rho_k <= 1 always, since snapped_k >= 1.0 > RTP_TARGET). The SDK grid check
(verify_lookup_format) stays ON — lut_grid_exempt = False.

Outcome probabilities (target-weight mixture)
---------------------------------------------
A round is predetermined to cash out at a target step k (weight w_k, default uniform
1/S) and survives to it with probability rho_k, paying snapped_k; else it pops
(pays 0). Outcome probability q_k = w_k * rho_k; loss q_loss = 1 - sum(q_k). Because
q_k * snapped_k = w_k * RTP_TARGET, the overall RTP equals RTP_TARGET for ANY w_k —
the target weight only shapes hit-frequency / volatility, never RTP. Steps whose
snapped multipliers collide (e.g. easy 1.0x, 1.0x) are pooled into one outcome.

Exact integer book counts
-------------------------
Optimiser off -> published odds equal the per-criteria book counts. With num_sims
(default 1,000,000; env NUM_SIMS) each distinct payout's book count is
round(num_sims * q); the loss bucket absorbs the rounding residual so counts sum to
num_sims exactly; the floor-safe "+0.5" quota (get_sim_splits does
int(num_sims*quota)) reproduces the count. Realised RTP is recomputed from the
integer counts (tools/report.py) and lands within the integer-rounding bound of 97%.

Per-round events
----------------
    crossingSetup  : {difficulty, costMultiplier, numSteps, ladder[], maxWin,
                      productMode}
    crossingResult : {difficulty, isWin, cashOutStep|null, poppedAtStep|null,
                      payoutMultiplier}
    finalWin       : {amount(cents), multiplier}      (+ a wincap event on the top
                      Daredevil rung)

WARNINGS — unsupported / non-default Stake Engine behaviour
-----------------------------------------------------------
1. PREDETERMINED SETTLEMENT (no dynamic cash-out). The RGS is a certified replay:
   the book selected at /play fixes the WHOLE outcome, including the cash-out step.
   The player pressing "Cash Out" CANNOT change the payout mid-round — do not rely on
   /bet/event to mutate the settled payout. Player-controlled dynamic cash-out stays
   DISABLED unless Stake Engine explicitly confirms an in-progress action can change
   the final round payout. (In this design the cash-out step is drawn by the book;
   the frontend replays it.)

2. RTP vs the ACP ceiling. RTP_TARGET = 0.97 exceeds Stake's per-mode RTP validator
   ceiling of 96.70% and will FAIL that validator at ACP upload (the SDK format
   checks do NOT enforce it — execute_all_tests passes at 0.97). For a guaranteed
   ACP-uploadable build set RTP_TARGET=0.965 (env `RTP_TARGET=0.965`, or the constant
   in game_config.py) and rebuild; realised RTP then lands safely inside the
   90-96.70% band. (Targeting exactly 0.967 can round a hair over the ceiling after
   integer book rounding — 0.965 leaves a safe margin; verify with tools/report.py.)

Reports
-------
    PYTHONPATH="$(pwd):games/2_7_chicken_crossing" \
      env/bin/python games/2_7_chicken_crossing/tools/report.py
Prints, per mode: the full ladder table (step, cumSurv, rawMult, snapped, rho, book
count, LUT cents), the RTP report (theoretical vs realised), the max-win frequency
report (probability, 1-in-N hit rate, expected per 1,000,000 sims), and cross-checks
the built LUT's payout cents + counts against the config.

Build
-----
Dev (readable books, no checks; small NUM_SIMS for speed):
    NUM_SIMS=50000 PYTHONPATH="$(pwd)" env/bin/python games/2_7_chicken_crossing/run.py
Production / verification (compressed books + RGS format checks + book<->LUT hash):
    NUM_SIMS=1000000 COMPRESSION=1 RUN_FORMAT_CHECKS=1 PYTHONPATH="$(pwd)" \
      env/bin/python games/2_7_chicken_crossing/run.py
Then upload library/publish_files/{index.json, books_<mode>.jsonl.zst,
lookUpTable_<mode>_0.csv} via the ACP dashboard. Bet levels and gameID are set in
ACP, not here. provider_number is a placeholder (2) pending the ACP-assigned value.
See warning #2 before uploading (set RTP_TARGET=0.967 for an ACP-valid build).
