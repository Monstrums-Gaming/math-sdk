Tap Trade (2_6) — tap-cell-to-bet multiplier grid (dense ladder)
==================================================================

(Formerly `2_11_crypto_pulse_grid`; renamed 2026-07-22 to pair with the web-sdk app
`apps/2-6-tap-trade`. Only the identity changed — the ladder, odds, and book/event
contract are untouched.)

Mechanic
--------
A denser-ladder variant of games/2_10_crypto_pulse_grid (the Euphoria mechanic).
A live-looking price chart runs continuously on the left; the future (right) portion
of the chart is covered by a grid of (time x price) multiplier cells. The player taps
a cell to place a chip; if the price line reaches that cell the chip pays
`bet x cellMultiplier`, otherwise the chip loses. Multiple chips are allowed, at most
two per time-column on distinct cells (with two outcomes a single line can always
render the combination — enter on the safe side, sweep between two winners — while a
third chip can create an impossible win-lose-win sandwich; the cap is static so a
rejection never leaks drawn outcomes). There is no timer — play is continuous and
each chip resolves when the line reaches its column.

WHERE a tapped cell sits (its row/column) is pure client-side presentation: the book
carries only win/lose + the offered multiplier, and the frontend steers the line to
hit or miss the tapped cell. Prices are pure RNG theatre — outcomes are pre-generated
books (the RGS is a certified replay system; odds cannot change at runtime).

From the math's point of view each chip is an independent win/lose bet at a fixed
multiplier M — exactly the games/2_9_crypto_pulse / games/2_10_crypto_pulse_grid
model. This is a direct-probability game (like games/2_4_dice_kong_climb,
games/2_5_limbo_frankenstein): odds authored in game_config.py, Rust optimiser
disabled, published odds equal the per-criteria book counts.

What differs from 2_10: the ladder is DENSE below 10x (18 rungs vs 2_10's 10),
giving the on-screen grid finer multiplier resolution where most cells live (near
the line's projected path). The risk envelope (1.4x floor, 100x cap, all-or-nothing
two-outcome modes) is identical to 2_10 at both ends.

Modes: a 28-rung multiplier ladder (cost 1.0 each)
--------------------------------------------------
Every distinct cell multiplier is its own published win/lose mode `call_<cents>`
(dot-free — the ACP publisher parses `<mode>` out of `books_<mode>.jsonl.zst`). Ladder:

  1.4, 1.5, 1.6, 1.8, 2, 2.2, 2.5, 2.8, 3.2, 3.6, 4, 4.5, 5, 6, 7, 8, 9, 10,
  12, 15, 20, 25, 30, 40, 50, 65, 80, 100
  -> modes call_140, call_150, ... call_10000.

For each multiplier M the win probability is the smallest-denominator rational a/b
whose realised RTP (a/b)*M lands in [96.00%, 96.70%] (`_simplest_fraction_in`, the
limbo/chicken Stern-Brocot descent); num_sims = b yields exactly a winning books.

  mode        a/b      RTP        mode        a/b       RTP
  call_140    11/16    96.25%     call_700    4/29      96.55%
  call_150    9/14     96.43%     call_800    3/25      96.00%
  call_160    3/5      96.00%     call_900    3/28      96.43%
  call_180    8/15     96.00%     call_1000   5/52      96.15%
  call_200    12/25    96.00%     call_1200   2/25      96.00%
  call_220    7/16     96.25%     call_1500   5/78      96.15%
  call_250    5/13     96.15%     call_2000   4/83      96.39%
  call_280    10/29    96.55%     call_2500   1/26      96.15%
  call_320    3/10     96.00%     call_3000   4/125     96.00%
  call_360    4/15     96.00%     call_4000   2/83      96.39%
  call_400    6/25     96.00%     call_5000   1/52      96.15%
  call_450    3/14     96.43%     call_6500   2/135     96.30%
  call_500    5/26     96.15%     call_8000   1/83      96.39%
  call_600    4/25     96.00%     call_10000  1/104     96.15%

Realised RTP band 96.00-96.55%, cross-mode spread 0.5517% (<= 1%). Total books across
all modes = 1,176; largest num_sims = 135 (call_6500).

The floor is 1.4x, NOT 1.2x
---------------------------
A 1.2x win/lose mode has payout std ~0.48, below ACP's Base-Volatility floor of 0.60,
which rates the whole game off its tamest mode (documented in the stake-risk-validators
skill — the exact reason Limbo's approved ladder starts at 1.40x). 1.4x has std ~0.62,
just clear. The 100x ceiling is the Limbo `base_100` precedent that passed ACP's
ETL/CVaR risk validators; this ladder is interior to Limbo's approved 1.40x-100x
envelope at both ends. Every mode is a two-outcome all-or-nothing bet.

Per-mode wincap event (INTENTIONAL — do not "fix" it)
-----------------------------------------------------
Each mode's BetMode.max_win is set to that mode's OWN multiplier M (not the global
100x). The engine applies a per-mode wincap override during sims
(src/state/run_sims.py sets config.wincap = BetMode.max_win), so a winning book — whose
payout equals M — reaches the active mode's cap and the base engine emits a standard
`wincap` event on EVERY winning book in EVERY mode. So a winning book is
`cellCall -> wincap -> finalWin`; a losing book is `cellCall -> finalWin` (no wincap).
This is deliberate; the web side treats the `wincap` event as a no-op. self.wincap =
100.0 is the global maximum (top rung), used only for the module-level cap assertion.

Book event contract (identical to 2_10)
---------------------------------------
Per-round book = ONE chip. ALL amounts are BET-RELATIVE MULTIPLIER CENTS (x100).

  cellCall { index, type, result, isWin, payoutMultiplier, winChance }
    result "Win" | "Lose" (capitalized, 2_9 priceCall convention); isWin bool;
    payoutMultiplier = the offered multiplier in cents, PRESENT win or lose;
    winChance = a/b float.
  wincap   { index, type, amount }   only on a win; amount == payoutMultiplier cents.
  finalWin { index, type, amount }   base-engine event, AMOUNT ONLY (no float
    multiplier field); amount = M*100 on a win, 0 on a loss == the LUT payout.

Mode keys are `call_<multiplierCents>`; the client ladder derives from
odds_bundle.json so math naming wins. The book is position-neutral — the tapped cell
(col/row) is client-side; the app steers the line to hit/miss it.

ACP math rules satisfied
------------------------
  1. 0.1x LUT grid — every multiplier is a multiple of 0.10 (lut_grid_exempt = False).
  2. Per-mode RTP in [90%, 96.70%] — realised 96.00-96.55%.
  3. Cross-mode spread <= 1.00% — realised 0.5517%.
  4. Base bet mode cost = 1.0.
Risk / star-rating (ETL / CVaR / volatility) is the one gate not provable locally; the
ladder is designed inside the approved Limbo envelope (1.40x floor for std >= 0.60,
100x cap).

Files
-----
  game_config.py       - the ladder (_MULTIPLIERS), win/lose BetMode per rung
                         (max_win = own M), _simplest_fraction_in, _validate.
  game_events.py       - cell_call_event (the single cellCall emitter).
  game_executables.py  - evaluate_call (resolve win/lose, emit cellCall, wincap on win).
  gamestate.py         - run_spin (cellCall -> finalWin); run_freespin raises.
  game_calculations.py - get_mode_params.
  game_override.py     - boardless reset/special-symbol stubs.
  game_optimization.py - disabled stub (odds are authored, optimiser off).
  run.py               - driver; num_threads=1, batching_size=50000, env gates
                         COMPRESSION / RUN_FORMAT_CHECKS.
  build_odds_bundle.py - post-build verifier + odds_bundle.json emitter (NOT an RGS
                         artifact; kept OUT of publish_files/).
  frontend_demo/       - self-contained browser demo (canvas price line + multiplier
                         grid). LOCAL mode replays the published LUT odds; LIVE mode
                         places real bets against the Stake Engine RGS when launched
                         with ?rgs_url=...&sessionID=... (see frontend_demo/README.md).

Build
-----
Config sanity + dev build (readable JSON books, eyeball win + lose):
  rm -rf games/2_6_tap_trade/library && \
    PYTHONPATH="$PWD" ./env/bin/python games/2_6_tap_trade/run.py

Production (mandatory — execute_all_tests rejects non-.jsonl.zst books):
  COMPRESSION=1 RUN_FORMAT_CHECKS=1 PYTHONPATH="$PWD" \
    ./env/bin/python games/2_6_tap_trade/run.py

Then re-verify artifacts + emit the odds bundle, and rebuild the demo data:
  PYTHONPATH="$PWD" ./env/bin/python games/2_6_tap_trade/build_odds_bundle.py
  PYTHONPATH="$PWD" ./env/bin/python games/2_6_tap_trade/frontend_demo/build_demo_data.py
  make test

Publish files: library/publish_files/ — index.json (28 modes, cost 1.0),
books_<mode>.jsonl.zst, lookUpTable_<mode>_0.csv. Follow the publish-stake-game skill
for the ACP upload. odds_bundle.json is delivered to the web team separately (it is
NOT part of publish_files/).
