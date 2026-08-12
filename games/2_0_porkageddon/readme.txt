Porkageddon (2_0) — Stake-style pig battler
===========================================

Mechanic
--------
Two pigs fight. Each round BOTH sides commit one skill, and each skill's cost
multiplier joins a shared prize pot before the round resolves. The last pig
standing takes the pot. There is no board, no reels and no free-spin round.

This is a direct-probability game (like limbo 2_5, plinko 2_6, chicken 2_7/2_8):
the odds are authored in pork_math.py and the Rust optimiser is disabled.
Published odds equal the per-criteria book counts.

The source game is the shipped PixiJS client in frontend_demo/ (v1.0.5). The
conversion plan it was built against is
frontend_demo/docs/PORKAGEDDON_PLAN.md — read that for the product reasoning;
this file records what was actually built and where it departs from the plan.


What the conversion changed
---------------------------
On Stake Engine the RGS is a certified REPLAY: at /wallet/play a book is drawn
from a weighted lookup table and the entire outcome is already fixed. So:

  * One battle is ONE wager, one debit. v1.0.5 charged per move, per round.
  * Every skill "pick" is a commit REVEAL. No player action after /wallet/play
    can move the payout.
  * The prize pot is derived from the book, not from live debits. It is still
    genuinely the sum of both sides' skill costs — that mechanic survives intact.
  * Cost is 1.0x on every mode. Real stake sizing is the operator's ACP bet-level
    template, not a published mode.


Modes: three stances
--------------------
One bet mode per stance. Names are dot-free (the ACP publisher parses <mode> out
of books_<mode>.jsonl.zst). Each stance restricts the skill pool to a cost band
taken straight from the shipped paytables, which sets both the pot size and the
pace:

  mode        rounds  cost band     pot rungs   golden   max win   win chance
  skirmish     6-8    0.50-0.90x    1.1-2.7x     0.6%      10.0x     47.201%
  brawl        3-4    0.90-1.20x    1.4-2.5x     1.0%    2000.0x     43.902%
  bloodbath    2-3    1.20-1.50x    1.4-2.7x     2.0%    2000.0x     39.241%

All three realise RTP 96.35%. brawl's 43.9% win chance is deliberately the
v1.0.5 random-play baseline (44.0%), so returning players feel no regression.


Payout model
------------
Two disjoint shapes, both floor-snapped onto the ACP 0.1x grid:

  1. POT (ordinary win)   payout = pool_units / pool_norm
     The pot is a sum of 2R skill costs, so this is a real spread of ~12 rungs
     rather than one fixed multiplier. That body is what keeps every mode clear
     of the ACP Base-Volatility floor without relying on the tail.

  2. GOLDEN PIG (drawn independently of win/lose, revealed at matchmaking)
     A fixed badge of 2.00x * tier, i.e. pool-INDEPENDENT:

         bronze  x5     ->    10.0x        silver  x20   ->    40.0x
         gold    x100   ->   200.0x        diamond x1000 ->  2000.0x

     Fixed tier payouts are deliberate. Scaling a tier by the ACTUAL pot would
     smear it across ~12 distinct payouts, and since `get_sim_splits` forces
     every criteria to at least one book, a 1-in-50,000 outcome spread over 12
     values would inflate RTP by whole percentage points. One value per tier also
     lets the badge show the player an exact number up front.

     A golden battle must still be WON to pay. Effective paid-diamond frequency
     in brawl is 1/50,000/0.439 = 1 in 113,865. State that plainly in marketing.

GLOBAL_MAX_MULT (default 2000, env-overridable) is the published ceiling, and
diamond lands exactly on it — so max win is exactly 2000.0x with no clamping
distortion.


How RTP is pinned
-----------------
RTP is not declared, it is what the LUT computes. Per stance:

    E[payout | win] = (1-p) * E[pot] + p * sum_t w_t * badge_t
    win_rate        = RTP_TARGET / E[payout | win]

pool_norm is solved by integer bisection so the DERIVED win rate lands on the
stance's target (47.2% / 44.0% / 39.5%, carried from the plan). Book counts are
then laid down as exact integers, the loss bucket absorbs the residual, and a
one-book correction pass pins realised RTP to 96.35%. All exact integer /
Fraction arithmetic — no floating-point probability accumulation, which matters
because a float divide by a non-dyadic pool_norm silently drops a whole 0.1x
grid step on the high tiers.


Books are fighter-neutral — and that is what makes the roster fair
------------------------------------------------------------------
The eight fighters are wildly unbalanced under free play: the GDD reports Gladi
Piggie ~76% wins vs Pr. Oinkstein ~14%. HP x attackMod is nearly flat across the
roster (94.8-110), so the cause is the skill ROLL RANGES, which differ by 2x.
v1.0.5 tried to price that with cost multipliers, but cost never affected win
rate — only pot size. Under a fixed per-battle cost that lever disappears and the
imbalance becomes naked unfairness.

The plan proposed fixing it by solving 8 x 3 = 24 opponent-damage scalars by
binary search. That is unnecessary here. Because the outcome is drawn from a
per-mode LUT, a fighter-neutral book pool makes every fighter's odds
MATHEMATICALLY IDENTICAL by construction — there is nothing to calibrate and no
per-fighter RTP to verify.

So a stance publishes ONE book set whose transcript addresses skills by SLOT
INDEX. The client renders slot k with the chosen fighter's name, art, rig and
SFX. Fighter choice becomes pacing and flavour, which also means streak and
revenge matchmaking survive untouched — opponent identity is now cosmetic.


The transcript generator (game_executables.py)
----------------------------------------------
Given a payout the RGS already drew, it manufactures a battle that honestly
produces it:

  1. Draw a (rounds, pool) shape consistent with the criteria.
  2. Draw the Golden Pig tier (fixed by the criteria on a golden win; cosmetic on
     a pot win or a loss).
  3. Draw a cost sequence of 2R skill picks summing to that pool EXACTLY — a
     uniform draw over the compositions with the required sum, via a DP.
  4. Roll honest damage/heal amounts inside each slot's published range, then
     solve for the battle's absolute hpMax so the loser dies exactly in the final
     round and the winner survives.

Step 4 is a fairness decision. Something must give for the drawn round count to
come out exact, and the choice of WHAT gives matters:

  * Rubber-banding the damage numbers to fit was REJECTED. The roll ranges are
    wide (10-40 vs 60-70), so out-of-range numbers are trivially datamineable and
    would read as rigged.
  * Instead the free variable is hpMax, which the player never sees as a number
    (the client renders a bar). Every damage number stays inside its published
    range; only the size of the HP pool flexes, held within +/-20% of the
    stance's nominal chassis.

An infeasible plan costs nothing but a redraw, so the generator redraws instead of
ever editing a number. Two shapes make "dies exactly on the final swing"
impossible: the winner absorbing more damage than the loser, and a LOSER HEAL
walking its accumulated damage back below an earlier peak. Both are resolved by
resampling; past the first 64 draws the loser's heals are suppressed, which is
presentation-only and cannot touch the pot or the payout. Measured on the shipped
build, 0 of 600,000 battles fall outside the chassis tolerance.

This was got wrong once and is worth not repeating: an earlier revision had a
"clamp the killing blow to the loser's remaining HP" fallback. Because the fallback
also raised hpMax back to nominal, the clamp AMPLIFIED rather than clamped, and it
published damage numbers far outside the slot range in ~1% of books — a 10-40
"Mutant Serum" blow showing 235 damage. tools/verify_books.py exists to make that
class of bug impossible to ship again.

Both sides commit a skill in EVERY round including the last, so the pot is always
2R costs even when the killing blow lands before the second move resolves. That
is the shipped engine's behaviour (battleEngine.js adds both costs to the pot
before resolving, and there are no refunds), and it is why the published pool PMF
is a sum over an even number of picks.


Per-round events (the book contract)
------------------------------------
    porkSetup -> porkBattle -> porkResult -> [wincap] -> finalWin

  porkSetup    stance, hpMax, rounds, the slot table, and the Golden Pig badge
               (revealed here, before the fight)
  porkBattle   the whole transcript as one event: rounds[] of fixed-order integer
               arrays (see game_events.ROUND_FIELDS; fieldOrder is echoed into
               the event so a client can bind by name). Arrays not objects — at
               6-8 rounds x 200k books the repeated key strings were the single
               largest contributor to compressed book size (~2x).
  porkResult   isWin, poolUnits, poolMultiplier, golden tier, payoutMultiplier
  wincap       the SDK's standard event; fires only on a mode's max-win books
               because each BetMode.max_win is that mode's true top payout.
               Includes skirmish's 10.0x books. Treat as a no-op if unused.
  finalWin     amount (integer cents) + multiplier

max_win is PER MODE and that matters: run_sims.py overwrites config.wincap with
BetMode.max_win before each mode's sims. A max_win BELOW a mode's true top payout
makes update_final_win clamp the payout, so final_win != win_criteria,
check_repeat never accepts, and run_spin's `while self.repeat` loop spins forever.
A max_win ABOVE it publishes a maxWin the LUT cannot reach.


ACP compliance
--------------
  Base mode cost         exactly 1.0x        1.0x on all three modes
  Per-mode RTP           90% - 96.70%        96.3497% - 96.3504%
  Cross-mode spread      <= 1.00pp           0.00075pp
  Payout grid            multiple of 0.1x    every payout; lut_grid_exempt=False

Note the plan doc's target RTP of 96.74% is NOT achievable — 96.70% is the hard
ACP ceiling. This build ships 96.35%, which leaves symmetric headroom for the
integer-count correction.

Outstanding: provider_number is still a placeholder (2) pending the ACP-assigned
value. Bet levels are set in the ACP dashboard, not emitted here.


Risk / star-rating posture (the second ACP gate)
------------------------------------------------
ETL, CVaR, Max Payout and Tail Probability are checked server-side at upload and
neither the SDK nor execute_all_tests looks at them. Where this build stands:

  * Base Volatility (Std Dev) floor of 0.60 — PASSES with wide margin. Payout std
    is 1.1154 (skirmish, the tamest mode), 6.8533 (brawl), 7.6423 (bloodbath). A
    win/lose game's std is bounded below by RTP*sqrt(1/q - 1), which at these win
    rates cannot fall under 0.60 for any pot spread — the floor is structurally
    unreachable here. (This is the opposite of limbo, whose problem was a HIGH
    win rate.)
  * Tail SHAPE — on the passing side by a wide margin. The tail carries 2.9%
    (skirmish) / 10.3% (brawl) / 20.3% (bloodbath) of RTP, against 79% for
    plinko's high_r16 which PASSED and ~100% for limbo's failing base_150. The
    body is 12-17 distinct mid-size payouts, which is the textbook "spread the
    weight, don't just cap the edge" case.
  * Max Payout as a STANDALONE validator is the one genuine exposure. 2000x is
    ~2x above the highest multiplier this repo has confirmed passing (plinko
    high_r16 = 970x). chicken_crossing's 2000x cap is NOT a precedent — that game
    has never been through ACP.

Bloodbath's golden split is already de-risked: gold 5.0000% / diamond 0.1000%
(rather than gold 4% / diamond 0.3%). Both hit E[M] = 12.25 exactly and therefore
the same RTP and the same 20% tail share, but this one halves the frequency of
the 2000x max win, roughly halving the tail liability ETL/CVaR key on. It also
makes diamond exactly 1 in 50,000 battles in both modes.

If the ACP rejects on risk, lower in this order:
  1. GLOBAL_MAX_MULT=1000 — one env switch. Puts max win just above plinko's
     validated 970x. Cheapest, highest-value rung; consider shipping here first.
  2. bloodbath golden 2.0% -> 1.0% (adopt brawl's table). Costs bloodbath its
     product identity; only if the rejection names bloodbath specifically.
  3. diamond x1000 -> x500. Keeps a four-tier ladder and a >1000x headline.
  4. Drop diamond, roll its weight into gold. Max win ~200x — cannot plausibly
     fail any tail validator. The guaranteed-pass configuration.
Do NOT chase a risk rejection by editing RTP or the win rates; RTP is already
pinned and lowering win rates RAISES std, moving toward the ceiling.


num_sims: bounded from both sides
---------------------------------
DEFAULT_NUM_SIMS = 200,000 per mode (env NUM_SIMS).

  * From below: get_sim_splits forces every criteria to at least one book. When a
    tail outcome's true expectation is under 1, the forced book buys RTP that the
    correction pass takes back out of the body — paid for in WIN RATE, not RTP
    (RTP stays pinned either way). Measured drift from the design win rate:
    20k -> -5.1pp (unusable), 100k -> -0.12pp, 200k -> -0.27pp, 1e6 -> -0.02pp.
    pork_math asserts the drift stays inside the plan's +/-0.5pp acceptance gate,
    so a too-small NUM_SIMS fails loudly rather than silently shipping the wrong
    hit rate.
  * From above: a battle transcript is much bigger than chicken/plinko's
    three-event books. 200k/mode is ~55 MB of publish files; 1e6 would be
    ~275 MB.

Raise to 1e6 if a tighter win rate is worth ~5x the bytes.


Building
--------
Run from the math-sdk root with the venv (PYTHONPATH is required — src resolves
via cwd, not the editable install). Wipe library/ first: leftover artifacts from a
prior build are read by execute_all_tests and cause off-grid / hash-mismatch
failures.

    rm -rf games/2_0_porkageddon/library
    PYTHONPATH="$(pwd)" COMPRESSION=1 RUN_FORMAT_CHECKS=1 \
        ./env/bin/python games/2_0_porkageddon/run.py

Compression is mandatory for the format checks (execute_all_tests rejects
non-.jsonl.zst books). Takes ~65 s and writes ~55 MB into
library/publish_files/ (index.json + 3 books + 3 lookup tables).

Env overrides: NUM_SIMS, GLOBAL_MAX_MULT, RTP_TARGET_BP.

Then verify the transcripts. execute_all_tests only proves the books and the LUT
agree with each other; it says nothing about whether a battle is internally honest:

    PYTHONPATH="$(pwd)" ./env/bin/python games/2_0_porkageddon/tools/verify_books.py

That walks all 600,000 books and asserts every attack amount re-derives EXACTLY
from its own roll and sits inside its slot's published range, every heal is capped
at full HP, the HP track reconstructs from nothing but hpMax and the moves, the pot
equals the summed slot costs, and payouts agree across book / porkResult / finalWin
on the 0.1x grid. Run it on every build before uploading.

Two optional transparency artifacts (both deliberately kept OUT of the three
uploaded publish files):

    ./env/bin/python games/2_0_porkageddon/fairness_manifest.py        # fairness.json
    PYTHONPATH="$(pwd)" ./env/bin/python games/2_0_porkageddon/docs/gen_paytable.py


Before committing this folder: frontend_demo/ is a nested git repo
--------------------------------------------------------------------
frontend_demo/ carries its OWN .git (12 commits, no remote). `git add
games/2_0_porkageddon` therefore stages it as a GITLINK — a bare commit pointer —
and since there is no remote to fetch it from, anyone cloning this repo gets an
empty directory and the shipped PixiJS client is effectively lost. `git status`
shows only `?? games/2_0_porkageddon/`, so this is easy to miss.

Decide before the first commit. Either bundle its history out and flatten it:

    git -C games/2_0_porkageddon/frontend_demo bundle create <somewhere>/porkageddon-client.bundle --all
    rm -rf games/2_0_porkageddon/frontend_demo/.git

or keep it out of this repo entirely and reference it. Note public/assets/ is
~123 MB of Spine rigs, audio and comic art — a separate reviewable decision (git-lfs
or an external asset source), not something to drop in as a side effect.


What the frontend still has to change
-------------------------------------
The math side is done; these are the client-side consequences.

  * Replace local RNG call sites with book playback: porkSetup -> porkBattle ->
    porkResult -> finalWin. Wire authenticate / play / end-round.
  * Render the HP bar from the book's hpMax and per-round hp values, NOT from the
    fighter's HP stat. hpMax varies per battle by design (see "transcript
    generator"), so do not display absolute HP numbers.
  * Source the skill cost badge from porkSetup.slots, not gameData.js. Within a
    stance every fighter's slot-k skill shares the stance's canonical cost — this
    is the one place the shipped per-fighter cost data no longer applies.
  * Cut Run Away, replace with Skip (fast-forward to result). Same UX value, no
    compliance question, doubles as a turbo control.
  * Strip the level +2% damage scaling (levels become cosmetic prestige) and the
    settings "balance reset" (the wallet is RGS-authoritative).
  * Remove the hardcoded "RTP = 96,74%" string in src/app/strings.js and audit
    the comic for the same claim. RTP is platform-computed; this build is 96.35%.
  * Gate autoplay on the jurisdiction flags from /wallet/authenticate rather than
    local settings.
  * /bet/event may checkpoint in-progress battle state so a disconnected player
    resumes mid-fight. It carries no money and CANNOT alter the outcome.
