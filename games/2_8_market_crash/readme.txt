Market Crash (2_8) — a crash game dressed as a market index
===========================================================

MECHANIC
--------
The player sets a SELL AT cash-out multiplier T before the bet. A market index climbs
from 1.00x and either reaches T — the round WINS T x — or RUGS short of it, paying 0.

The index chart does NOT use real market prices. The frontend animates a plausible
climb whose endpoint is the certified crash point stored in the book (see CRASH POINT),
so the visual is a rendering of the book, not an invention of the client.

WHY THE TARGET IS THE BET MODE (not a mid-flight cash-out)
---------------------------------------------------------
The Stake Engine RGS is a certified REPLAY system: books and lookup tables are
hash-frozen at publish time and the payout of a served book cannot be changed at bet
time. A player pressing "cash out" mid-flight therefore cannot be paid — there is no
runtime path that could price it.

So the target is committed BEFORE the bet and IS the published bet mode. That makes this
structurally the 2_5_limbo_frankenstein model: one cost-1.0 two-outcome mode per rung.
The difference is presentational (a climbing index that rugs, rather than a single
revealed number) plus the certified crash point, which limbo does not have.

SELL AT LADDER — 30 modes, crash_140 .. crash_10000
---------------------------------------------------
  1.40  1.50  1.60  1.70  1.80  1.90  2.00
  2.20  2.50  2.80  3.00  3.50  4.00  4.50  5.00
  6.00  7.00  8.00  9.00  10.00
  12.00  15.00  20.00  25.00  30.00  40.00  50.00  65.00  80.00  100.00

Each rung is its own dot-free mode `crash_<cents>` (the ACP publisher parses <mode> out
of books_<mode>.jsonl.zst, so a "." would collide with the extension), each cost = 1.0.
Rung-to-rung ratio runs 1.053x-1.333x — tightest below 5x where the mass of play sits
(win chance 19-69%), loosest in the lottery tail. A player wanting "sell at 2.35x" is
never more than ~6% from an available rung below 5x.

Per rung, the win probability is the smallest-denominator rational a/b whose realised RTP
(a/b)*T lands in [96.15%, 96.65%] (`_simplest_fraction_in`, the limbo Stern-Brocot
descent). Realised: RTP 96.1538%-96.6102%, cross-mode spread 0.4563%, payout std
0.649-9.759, max win 100x.

  mode         T      a/b     RTP%    std     books    wins
  crash_140    1.40   11/16   96.2500 0.649    5008    3443
  crash_200    2.00   13/27   96.2963 0.999    5022    2418
  crash_250    2.50    5/13   96.1538 1.216    5005    1925
  crash_500    5.00    5/26   96.1538 1.971    5018     965
  crash_1000  10.00    5/52   96.1538 2.948    5044     485
  crash_5000  50.00    1/52   96.1538 6.867    7800     150
  crash_10000 100.00  1/104   96.1538 9.759   15600     150
  (full table: library/odds_bundle.json, or print config.tiers)

WHY THE RTP WINDOW IS [96.15%, 96.65%] AND NOT THE FAMILY'S [96.00%, 96.70%]
---------------------------------------------------------------------------
The ACP dashboard string is "Return to Player across all modes must be within +/-0.5% of
each other". This repo has always read that as max-min <= 1.00% (asserted in 2_5, 2_6,
2_7), and those builds ship a 0.667% spread — which passes that reading and FAILS a
literal max-min <= 0.5% one. That ambiguity is avoidable risk on a new upload.

The wide window exists only to keep the Stern-Brocot denominator b small, because those
games set num_sims = b. This game scales num_sims to k*b anyway (below), so b is not a
binding constraint and the window is tightened for free. [96.15%, 96.65%] gives a
realised spread of 0.4563% — inside BOTH readings — and pins the top rung to exactly
1/104, bit-identical to the already-ACP-approved 2_5 base_100_00.

WHY 1.40x FLOOR / 100x CEILING (the hard walls, not preferences)
---------------------------------------------------------------
FLOOR. A two-outcome mode's payout std is sqrt(R*T - R^2), giving 0.480 / 0.571 / 0.649
at T = 1.20 / 1.30 / 1.40. ACP rates Base Volatility off the game's TAMEST mode against a
0.60 floor, so 1.40x is the lowest publishable rung. (Same reason limbo's approved ladder
and tap-trade's both start at 1.40x.)

CEILING. Per .claude/skills/stake-risk-validators and 2_5's readme: an all-or-nothing
target >= 150x fails the ETL-40x / CVaR tail caps (base_150 fails at both 2- and 3-star;
base_800 also breaches CVaR). base_100_00 passed. This ladder's top rung reproduces that
mode's LUT shape exactly — 1/104 at 10,000 cents, uniform weights — so every statistic
ACP derives from it (Max Payout, Tail Probability, ETL-40x, CVaR, std 9.759) is
numerically identical to an approved mode.

Bet-size scaling belongs in the ACP bet-level template, never in a published mode: the
risk validators read the raw payout absolutely, which is exactly how 2_5's removed
`streak` (cost 2/5) and `high` (cost 100) tiers inflated modest targets into
5,000x-50,000x payouts.

If ACP still flags the top rung, the fallback is one line: drop the last entry of
_SELL_AT so 80x becomes the ceiling. Do NOT chase it by moving the RTP window.

num_sims = k * b, NOT b
-----------------------
With num_sims = b, crash_10000 would have ONE winning book: every 100x win in the game's
history would serve the same bytes, hence the same crash point — datamineable, and a
visibly canned animation. Each mode instead publishes N = k*b books with W = k*a winners,
k = max(ceil(5000/b), ceil(150/a)), so N is 5,005-15,600 and every mode has at least 150
distinct winning crash points. Total 177,924 books (~1.2 MB compressed, ~3.0 MB including
the LUT CSVs).

Fraction(W, N) == Fraction(a, b) EXACTLY, so every ACP-derived statistic is bit-identical
to a k = 1 build. k is provably risk-neutral; _validate() and build_odds_bundle.py both
assert it.

THE TRAP: the floor-safe +0.5 quotas must be computed from the PUBLISHED W/N, never from
a/b. get_sim_splits does int(num_sims * quota), so (a+0.5)/b against num_sims = k*b
over-allocates winners by k/2. _validate() asserts int(N*win_quota) == W.

CRASH POINT (the departure from 2_5 / 2_7)
------------------------------------------
Every book carries `crashPoint`, the multiplier at which the index rugged, in integer
hundredths. Unlike 2_7_prediction_market — where the chart direction is synthesized
client-side as endsHigh = (pickedHigh == isWin) — this value is CERTIFIED and the frontend
animation is obliged to land on it. It follows the pattern in
.claude/skills/stake-provably-fair: store a seeded, outcome-consistent result in the book.

The law, using the mode's REALISED RTP R = (a/b)*T:

    P(C >= x) = R / x        for x >= 1

Read at x = T this gives R/T = (a/b)*T/T = a/b — exactly the mode's published win
probability. That identity is the point: the odds a player is quoted ARE this law read at
their SELL AT, so the paytable and the crash animation tell one story.

Win/lose is already decided (the distribution quota assigns the sim's criteria before
run_spin), so C is sampled CONDITIONALLY:

    win  (C >= T):  v ~ U(0,1],  C = T / v                  (conditional survival T/x)
    lose (C <  T):  with prob q_atom = (1-R)*T/(T-R)  ->  C = 1.00  (instant rug;
                    3.7%-12.0% of losses depending on the rung)
                    else u ~ U(1/T, 1],  C = 1/u  in [1, T)

The mixture reproduces the UNCONDITIONAL law at every x, which is what makes
build_odds_bundle.py's survival audit a real falsifiable check rather than decoration
(worst observed deviation across all 30 modes: 2.45 sigma against a 4-sigma gate).

Quantisation is by FLOOR — physically right ("the index ticked past cp and rugged before
cp+0.01") and bias-free at grid points, since floor(100C) >= x_h <=> 100C >= x_h. Boundary
contract: cp == target counts as a WIN; a loss must be <= target - 1. The maths is exact
but floats are not, so the sampler clamps unconditionally and then asserts; over a million
draws per mode the clamp never binds, so it is a free correctness proof rather than a
distortion.

DISPLAY CAP: min(200 * target, 10,000.00x), per mode. Truncating an unbounded 1/x tail
creates an atom at the cap of size target/cap, so a per-mode multiple holds that atom at a
uniform ~0.5% of wins on every rung (1.0% on the top rung, where the absolute cap binds).
A single global 10,000x cap would let a 1.40x win display 10,000x — absurd on the chart,
and it degenerates the frontend's log axis; a global 1,000x cap would park 10% of top-rung
wins on one canned value.

SEEDING: the module RNG, already seeded per-sim by reset_seed (the sanctioned pattern from
2_4_dice_kong_climb), PLUS a per-mode offset. reset_seed(sim) alone seeds random with
sim+1, so sim #7 in crash_140 and sim #7 in crash_200 would draw the same uniform and
their crash points would be rank-correlated across the whole ladder. gamestate.py passes
seed_override = payout_cents * 1_000_003 + sim; the stride exceeds every mode's num_sims so
no two modes can collide. Criteria assignment happens before run_spin under its own fixed
seed, so drawing here cannot perturb which sims win — the build is byte-reproducible
(verified: two clean builds produce identical sha256 for all 30 books files).

crashPoint is presentation + fairness data ONLY. The payout derives from the criteria and
the RTP from the lookup table; build_odds_bundle.py asserts this mechanically (A8: payouts
must be constant within each verdict group, so no crash point value can leak into the
payout path).

PER-ROUND EVENTS
----------------
  lose (all modes)      : crashRound -> finalWin
  win  (29 lower rungs) : crashRound -> finalWin
  win  (crash_10000)    : crashRound -> wincap -> finalWin

crashRound (index 0 of every book):
  type              "crashRound"
  result            "Win" | "Lose"          (capitalised, matches priceCall / cellCall)
  isWin             bool
  target            SELL AT in integer hundredths (140..10000) — equals the mode
  crashPoint        rug multiplier in integer hundredths; >= target iff isWin;
                    100 <= crashPoint <= the mode's cap; == 100 means an instant rug
  payoutMultiplier  offered payout in hundredths (== target), present win OR lose
  winChance         probability in [0, 1]

`target` and `payoutMultiplier` are equal by construction (the target IS the mode, and the
mode pays its target). Both are kept: payoutMultiplier is the field every frontend in this
family already reads for money, target names the mechanic for the chart line. The verifier
asserts they agree.

`wincap` and `finalWin` come free from the base engine. BetMode.max_win is the GLOBAL 100.0
on every mode (the 2_5/2_7 convention, NOT 2_6's per-mode cap), so `wincap` fires only on
crash_10000 wins — 150 books — rather than on all ~27k winning books across the ladder.
That is semantically correct (the game's max win genuinely is 100x, carried by the top
rung) and keeps this a minimal delta from the approved 2_5 build. The web side still needs
a no-op `wincap` handler: utils-book logs a console.error for an unhandled event type.

Example books (crash_500 win / lose, then crash_10000 win):

  {"id":0,"payoutMultiplier":500,"events":[{"index":0,"type":"crashRound","result":"Win",
   "isWin":true,"target":500,"crashPoint":684,"payoutMultiplier":500,
   "winChance":0.19230769230769232},{"index":1,"type":"finalWin","amount":500}],
   "criteria":"win","baseGameWins":5.0,"freeGameWins":0.0}

  {"id":1,"payoutMultiplier":0,"events":[{"index":0,"type":"crashRound","result":"Lose",
   "isWin":false,"target":500,"crashPoint":219,"payoutMultiplier":500,
   "winChance":0.19230769230769232},{"index":1,"type":"finalWin","amount":0}],
   "criteria":"0","baseGameWins":0.0,"freeGameWins":0.0}

  {"id":373,"payoutMultiplier":10000,"events":[{"index":0,"type":"crashRound",
   "result":"Win","isWin":true,"target":10000,"crashPoint":13227,
   "payoutMultiplier":10000,"winChance":0.009615384615384616},
   {"index":1,"type":"wincap","amount":10000},{"index":2,"type":"finalWin",
   "amount":10000}],"criteria":"wincap","baseGameWins":100.0,"freeGameWins":0.0}

(Read the last one: sold at 100x, the market ran on to 132.27x — a legitimate 1/104
outcome. A golden rug is still a rug; the payout is the target, never the crash point.)

ACP MATH RULES SATISFIED
------------------------
  1. 0.1x LUT grid — every payout is an integer cents multiple of 10 (lut_grid_exempt=False).
  2. Per-mode RTP in [90%, 96.70%] — every rung pinned into [96.15%, 96.65%].
  3. Cross-mode spread 0.4563% — inside both the +/-0.5% and the 1.00% readings.
  4. Base bet mode cost = 1.0 on all 30 modes.
  5. Risk: two-outcome all-or-nothing per mode, interior to limbo's approved 1.40x-100x
     envelope, with the top rung numerically identical to base_100_00.
  6. Bet levels are an ACP dashboard template, not published modes.

`provider_number` is a PLACEHOLDER (2). Set the real ACP-assigned value before the final
prod build you upload.

BUILD
-----
  # dev smoke test — TRIM _SELL_AT to a few rungs first. The full 30-rung ladder at
  # COMPRESSION=0 writes ~45 MB of readable JSON (178k books) and trips create_books'
  # large-uncompressed warning.
  PYTHONPATH="$(pwd)" ./env/bin/python games/2_8_market_crash/run.py

  # production (compression is mandatory — execute_all_tests rejects non-.jsonl.zst)
  rm -rf games/2_8_market_crash/library
  PYTHONPATH="$(pwd)" COMPRESSION=1 RUN_FORMAT_CHECKS=1 \
      ./env/bin/python games/2_8_market_crash/run.py

  # MANDATORY before upload: artifact + event + crashPoint audit
  PYTHONPATH="$(pwd)" ./env/bin/python games/2_8_market_crash/build_odds_bundle.py

  # transparency manifest (AFTER the prod build, so the hashes match)
  PYTHONPATH="$(pwd)" ./env/bin/python games/2_8_market_crash/fairness_manifest.py

  # frontend demo bundle
  PYTHONPATH="$(pwd)" ./env/bin/python games/2_8_market_crash/frontend_demo/build_demo_data.py

Always `rm -rf library` first: a leftover LUT from a prior or larger build is read by
execute_all_tests and surfaces as a phantom payout-hash mismatch.

build_odds_bundle.py is not optional. execute_all_tests only proves the books agree with
the lookup table; it says nothing about whether a book's narrative is internally honest.
The 2_0_porkageddon lesson is the precedent — an earlier revision there silently published
out-of-range damage numbers that passed every RGS check. Here the equivalent failure is a
crashPoint on the wrong side of its target, or one that quietly drifts off the crash law.
The audit walks all 177,924 books asserting: the verdict invariant (crashPoint >= target
iff isWin, zero exceptions), the exact split, the cap atom, the distinct-value floors, the
survival law within 4 sigma, and that no crash point can influence a payout.

UPLOAD
------
Upload the three artifact families from library/publish_files/ via the ACP dashboard:
index.json, books_crash_*.jsonl.zst (30), lookUpTable_crash_*_0.csv (30).
odds_bundle.json stays in library/ and fairness.json is a transparency artifact — neither
is an RGS input.

WEB PAIRING
-----------
monstrums-web-sdk app `apps/2-8-market-crash`. The frontend derives the entire ladder from
the published modes and parses the target out of the `crash_<cents>` key, so adding,
removing or re-pinning a rung needs no frontend change beyond regenerating its odds
bundle — but a mode name that is not `crash_<integer>` breaks that parse, which the web
app's gen-odds-bundle script guards at build time.
