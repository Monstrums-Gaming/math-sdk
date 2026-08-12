"""
Porkageddon (2_0) — pure math layer (no SDK imports, importable standalone).

This module owns every number the game publishes. `game_config.py` is a thin
SDK-facing wrapper around `build_stances()`; `game_executables.py` consumes the
per-stance tables it produces to generate a battle transcript consistent with the
payout the RGS already drew. Keeping the math here means it can be exercised
without the engine (see `docs/gen_paytable.py` and `tools/report.py`).

## The mechanic (unchanged from the shipped PixiJS client)

Two pigs trade blows. Each round BOTH sides commit one skill, and each skill's
**cost multiplier** is added to a shared prize pool *before* the round resolves
(no refunds — that is the shipped engine's behaviour). The last pig standing
takes the whole pool.

    raw_pool_units = sum(player skill costs) + sum(opponent skill costs)

## What changed to make it a Stake Engine LUT game

On Stake Engine the RGS is a certified **replay**: a book is drawn from a weighted
lookup table at `/wallet/play` and the entire outcome is already fixed. So:

  * One battle = **one** wager, one debit. The v1.0.5 pay-per-move model is gone.
  * Every mode is `cost = 1.0` (the ACP "Base Mode Cost must be 1.0x" validator).
    The plan document's nominal stance costs (2.0 / 4.0 / 7.0) survive **only** as
    the per-stance `pool_norm` divisor that maps raw pool units into stake
    multiples; real stake sizing is the operator's ACP bet-level template.
  * The player's skill "pick" is a **reveal**, not a decision. No post-`/play`
    action can move the payout.

## Modes: three stances

One bet mode per stance, dot-free names (the ACP publisher parses `<mode>` out of
`books_<mode>.jsonl.zst`). Each stance restricts the skill pool to a cost band
taken straight from the shipped paytables, which sets both the pot size and the
pace:

    skirmish   costs 0.50-0.90   6-8 rounds   grindy, small pots, low variance
    brawl      costs 0.90-1.20   3-4 rounds   the v1.0.5 default feel
    bloodbath  costs 1.20-1.50   2-3 rounds   short, swingy, big pots

## Books are FIGHTER-NEUTRAL — and that is what makes the roster fair

The eight fighters are wildly unbalanced under free play (the GDD reports Gladi
Piggie ~76% wins vs Pr. Oinkstein ~14%), because their skill roll ranges differ by
2x while `HP x attackMod` is nearly flat. The conversion plan proposed fixing this
by solving 8x3 = 24 opponent-damage scalars via binary search.

That is unnecessary here. Because the outcome is drawn from a per-mode LUT, a
fighter-neutral book pool gives **every fighter mathematically identical odds by
construction** — there is nothing to calibrate. So a stance publishes ONE book set
built on a neutral reference chassis, and the transcript addresses skills by
**slot index**, not by fighter. The client renders slot `k` using the chosen
fighter's art, rig, name and SFX; the cost badge and the HP track come from the
book.

Consequence to carry into the client: within a stance every fighter's slot-`k`
skill shares the stance's canonical cost. That is a real (small) change to the
shipped per-fighter cost data — see readme.txt.

## Payout model

Two disjoint shapes, both floor-snapped onto the ACP 0.1x grid:

  1. **Body** (ordinary win, no Golden Pig) — `pool_units / pool_norm`. Because
     the pool is a sum of 2R skill costs, this is a genuine spread of ~10-14 rungs
     rather than one fixed multiplier, which is what keeps the modes clear of the
     ACP Base-Volatility floor without an all-or-nothing tail.
  2. **Golden Pig** (drawn INDEPENDENTLY of win/lose, revealed at matchmaking) —
     a fixed badge of `CANONICAL_POOL_CENTS x tier`, i.e. pool-independent:

         bronze  x5     ->    10.0x      silver  x20   ->    40.0x
         gold    x100   ->   200.0x      diamond x1000 ->  2000.0x

     Fixed tier payouts are deliberate. Scaling the tier by the *actual* pool
     would smear each tier across ~12 distinct payouts, and `max(1, round(...))`
     book counts on a 1-in-50,000 outcome would then inflate RTP by whole
     percentage points. One value per tier also lets the badge show the player an
     exact number up front.

     A golden battle must still be **won** to pay: effective paid-diamond
     frequency in brawl is `1 / 50,000 / 0.44 ~ 1 in 113,600`.

`GLOBAL_MAX_MULT` (default 2000x, env-overridable) is the published ceiling;
diamond lands exactly on it, so max win is exactly 2000.0x with no clamping
distortion. The plan's `bloodbath` "Mythic x2500" tier is dropped for it.

## How RTP is pinned

RTP is not declared, it is what the LUT computes. With the optimiser off, the
published odds ARE the per-criteria book counts, so:

    E[payout | win] = (1-p) * E[body] + p * sum_t w_t * tier_payout_t
    win_rate        = RTP_TARGET / E[payout | win]

`pool_norm` is solved (integer bisection over thousandths) so that the derived
`win_rate` lands on the stance's target win rate, which is carried from the plan
and, for `brawl`, from the v1.0.5 random-play baseline:

    skirmish 47.2%      brawl 44.0%      bloodbath 39.5%

Integer book counts then get one pass of correction: after `count =
max(1, round(num_sims * q))` the residual sits in the loss bucket, and a single
body outcome's count is nudged +/-1 until realised RTP (recomputed from the
integer counts, which is exactly what the ACP will do) is as close to
`RTP_TARGET` as one book allows. Everything is exact integer / `Fraction`
arithmetic — no floating-point probability accumulation.
"""

import os
from fractions import Fraction

# --------------------------------------------------------------------- targets
# Family window: per-mode RTP must satisfy 90% <= RTP <= 96.70% (ACP), and the
# cross-mode spread must be <= 1.00%. We pin all three modes onto one target so
# the spread is ~0.
RTP_TARGET = Fraction(int(os.environ.get("RTP_TARGET_BP", "9635")), 10000)  # 96.35%
RTP_FLOOR = Fraction(9600, 10000)
RTP_CEIL = Fraction(9670, 10000)

# Published max-win ceiling. Diamond is built to land exactly here.
GLOBAL_MAX_MULT = int(os.environ.get("GLOBAL_MAX_MULT", "2000"))
MAX_CENTS = GLOBAL_MAX_MULT * 100

# Simulations (= books) per mode.
#
# This number is bounded from BELOW by the tail and from ABOVE by file size:
#
#   * Below. `max(1, round(num_sims * q))` forces a rare outcome to at least one
#     book. Diamond's true rate in brawl is 8.8e-6, so a forced book buys RTP that
#     the correction pass then has to take back out of the body — which is paid for
#     in WIN RATE, not RTP (RTP stays pinned either way). Measured drift from the
#     design win rate: 20k -> -5.1pp (unusable), 100k -> -0.12pp, 200k -> -0.27pp,
#     1e6 -> -0.02pp. `_MAX_WIN_RATE_DRIFT` below fails the build if it exceeds the
#     plan's +/-0.5pp acceptance gate, so a too-small NUM_SIMS is loud, not silent.
#   * Above. A battle transcript is far bigger than chicken/plinko's three-event
#     books. Measured compressed: skirmish ~100 B/book, brawl ~55, bloodbath ~40.
#     200k/mode is ~40 MB of publish files; 1e6 would be ~200 MB.
#
# 200k sits inside the win-rate gate with ~2x margin at a manageable upload size.
# Raise it to 1e6 (NUM_SIMS=1000000) if a tighter win rate is worth ~5x the bytes.
DEFAULT_NUM_SIMS = int(os.environ.get("NUM_SIMS", "200000"))

# The plan's acceptance gate: each mode within +/-0.5pp of its target win rate.
_MAX_WIN_RATE_DRIFT = Fraction(5, 1000)

# Hard cap on battle length. The authored round bands top out at 8; this exists
# because "no round limit" is fine for a live client and fatal for book
# generation (the plan's Phase 1 gate).
MAX_ROUNDS = 20

# The Golden Pig badge multiplies this fixed pot, not the actual pool — see the
# module docstring. 200 cents = 2.00x, the design mean pot in every stance.
CANONICAL_POOL_CENTS = 200

# ------------------------------------------------------------------- chassis
# Neutral reference fighter: El Porkador's chassis (attack 10 -> attackMod 1.00),
# the roster's exact median. Damage rolls keep the shipped client's 0.97 / 1.00
# scalars purely so the numbers a player sees still match the published paytable
# ranges; they no longer set the house edge (the LUT does).
REFERENCE_ATTACK_MOD = Fraction(1, 1)
PLAYER_ROLL_SCALE = Fraction(97, 100)
OPPONENT_ROLL_SCALE = Fraction(1, 1)

# Penicillin, from the shipped paytable. Cost is per-stance (it reuses one of the
# stance's slot costs so the pool distribution is untouched).
HEAL_MIN, HEAL_MAX = 10, 70
HEAL_LIMIT = 5           # per side, per battle (the shipped client's player cap)
HEAL_RENDER_CHANCE = 0.30  # chance a heal-cost pick is rendered as Penicillin

STANCE_NAMES = ["skirmish", "brawl", "bloodbath"]

# ------------------------------------------------------------------- stances
# `slots` are (cost_hundredths, canonical_name, dmg_min, dmg_max). Costs and roll
# ranges are lifted from the shipped src/engine/gameData.js; where several real
# skills share a cost the range is their union, so no fighter's numbers fall
# outside their slot. `hp` is tuned so the natural battle length sits at the
# centre of `rounds` (mean damage/round ~ hp / mean rounds).
STANCES = {
    "skirmish": {
        "order": 0,
        "label": "Skirmish",
        "plan_nominal_cost": 2.0,
        "hp": 235,
        "rounds": {6: Fraction(1, 4), 7: Fraction(1, 2), 8: Fraction(1, 4)},
        "target_win_rate": Fraction(472, 1000),
        "golden_freq": Fraction(6, 1000),
        "golden_tiers": [("bronze", 5, Fraction(1, 1))],
        "heal_cost_h": 80,
        "slots": [
            (50, "Mutant Serum", 10, 40),
            (75, "Shield Bash", 20, 45),
            (80, "Lasso Wrangle", 25, 40),
            (85, "Shock Snout", 30, 55),
            (90, "Meat Hook", 30, 50),
        ],
    },
    "brawl": {
        "order": 1,
        "label": "Brawl",
        "plan_nominal_cost": 4.0,
        "hp": 150,
        "rounds": {3: Fraction(1, 2), 4: Fraction(1, 2)},
        "target_win_rate": Fraction(440, 1000),
        "golden_freq": Fraction(10, 1000),
        "golden_tiers": [
            ("bronze", 5, Fraction(8907, 10000)),
            ("silver", 20, Fraction(773, 10000)),
            ("gold", 100, Fraction(300, 10000)),
            ("diamond", 1000, Fraction(20, 10000)),
        ],
        "heal_cost_h": 90,
        "slots": [
            (90, "Six-Snout Shooter", 30, 50),
            (105, "Snout Shot", 25, 50),
            (110, "Snout Lunge", 30, 55),
            (115, "Flying Oink Drop", 35, 55),
            (120, "Boar Charge", 40, 70),
        ],
    },
    "bloodbath": {
        "order": 2,
        "label": "Bloodbath",
        "plan_nominal_cost": 7.0,
        "hp": 138,
        "rounds": {2: Fraction(1, 2), 3: Fraction(1, 2)},
        "target_win_rate": Fraction(395, 1000),
        "golden_freq": Fraction(20, 1000),
        # Weighted toward GOLD relative to brawl (5.00% vs 3.00% within golden, so
        # 1-in-1,000 battles vs 1-in-3,333) while holding E[M] = 12.25 exactly:
        #   5(1273/1500) + 20(301/3000) + 100(1/20) + 1000(1/1000) = 12.25
        #   = 84.8667% / 10.0333% / 5.0000% / 0.1000%
        #
        # Diamond is deliberately held at 0.10% (not the 0.30% a naive "weighted to
        # gold AND diamond" reading of the plan implies). Both splits hit E[M] =
        # 12.25 and therefore the same RTP and the same 20% tail share, but this one
        # halves the frequency of the 2000x max win, which roughly halves the tail
        # liability the ACP's ETL/CVaR validators key on -- a free de-risk on the one
        # axis where this game has no in-repo precedent (see readme.txt "Risk").
        # It also makes diamond exactly 1 in 50,000 battles in BOTH modes.
        "golden_tiers": [
            ("bronze", 5, Fraction(1273, 1500)),
            ("silver", 20, Fraction(301, 3000)),
            ("gold", 100, Fraction(1, 20)),
            ("diamond", 1000, Fraction(1, 1000)),
        ],
        "heal_cost_h": 120,
        "slots": [
            (120, "Extra Hit", 40, 70),
            (125, "Cleaver Whirl", 45, 70),
            (140, "Piggie Suplex", 45, 65),
            (150, "Arena Slam", 50, 70),
        ],
    },
}


# ------------------------------------------------------------- pool distribution
def cost_values(stance: dict) -> list:
    """Slot costs in integer hundredths, ascending. One slot per distinct cost."""
    costs = [s[0] for s in stance["slots"]]
    assert len(set(costs)) == len(costs), "stance slot costs must be distinct"
    return sorted(costs)


def _sum_pmf(costs: list, picks: int) -> dict:
    """PMF of the sum of `picks` i.i.d. uniform draws from `costs` (hundredths)."""
    step = Fraction(1, len(costs))
    pmf = {0: Fraction(1, 1)}
    for _ in range(picks):
        nxt = {}
        for total, p in pmf.items():
            for c in costs:
                nxt[total + c] = nxt.get(total + c, Fraction(0)) + p * step
        pmf = nxt
    return pmf


def pool_pmf(stance: dict) -> dict:
    """PMF over (rounds, raw_pool_hundredths). Both sides pick once per round."""
    costs = cost_values(stance)
    out = {}
    for rounds, weight in sorted(stance["rounds"].items()):
        assert 1 <= rounds <= MAX_ROUNDS, f"round count {rounds} outside 1..{MAX_ROUNDS}"
        for pool_h, p in _sum_pmf(costs, 2 * rounds).items():
            out[(rounds, pool_h)] = out.get((rounds, pool_h), Fraction(0)) + weight * p
    assert sum(out.values()) == 1, "pool PMF must sum to 1"
    return out


def golden_pmf(stance: dict) -> list:
    """[(tier_name, tier_multiplier, unconditional probability)], incl. "none"."""
    p = stance["golden_freq"]
    tiers = [("none", 1, 1 - p)]
    total_w = sum(w for _, _, w in stance["golden_tiers"])
    assert total_w == 1, "golden tier weights must sum to 1"
    for name, mult, w in stance["golden_tiers"]:
        tiers.append((name, mult, p * w))
    assert sum(w for _, _, w in tiers) == 1, "golden PMF must sum to 1"
    return tiers


# --------------------------------------------------------------- payout snapping
def snap_cents(cents_floor: int) -> int:
    """Floor onto the ACP 0.1x grid; anything under 0.1x resolves to 0 (pays nothing)."""
    snapped = (cents_floor // 10) * 10
    return snapped if snapped >= 10 else 0


def body_cents(pool_h: int, norm_thousandths: int) -> int:
    """Ordinary-win payout: pool_units / pool_norm, floor-snapped, capped.

    `pool_h` is the raw pool in hundredths of a cost multiplier, so it is already
    on the "cents" scale once divided by the (dimensionless) pool_norm.
    """
    cents = (pool_h * 1000) // norm_thousandths
    return min(snap_cents(cents), MAX_CENTS)


def golden_cents(tier_mult: int) -> int:
    """Golden Pig badge payout: a fixed pot times the tier, floor-snapped, capped."""
    return min(snap_cents(CANONICAL_POOL_CENTS * tier_mult), MAX_CENTS)


def _expected_win_cents(stance: dict, pools: dict, norm_thousandths: int) -> Fraction:
    """E[payout in cents | the player wins] for a candidate pool_norm."""
    total = Fraction(0)
    for (tier, mult, prob) in golden_pmf(stance):
        if tier == "none":
            body = sum(p * body_cents(pool_h, norm_thousandths) for (_, pool_h), p in pools.items())
            total += prob * body
        else:
            total += prob * golden_cents(mult)
    return total


def solve_pool_norm(stance: dict, pools: dict) -> int:
    """Smallest-error `pool_norm` (in thousandths) hitting the stance's target win rate.

    win_rate = RTP_TARGET / E[payout | win], and E is monotonically decreasing in
    pool_norm, so bisect on the integer thousandths.
    """
    want_cents = RTP_TARGET / stance["target_win_rate"] * 100
    lo, hi = 1, 10_000_000
    while lo < hi:
        mid = (lo + hi) // 2
        if _expected_win_cents(stance, pools, mid) > want_cents:
            lo = mid + 1  # payout too generous -> divide by more
        else:
            hi = mid
    # Pick whichever of the bracketing integers gets closer to the target.
    best, best_err = lo, None
    for cand in (lo - 1, lo, lo + 1):
        if cand < 1:
            continue
        err = abs(_expected_win_cents(stance, pools, cand) - want_cents)
        if best_err is None or err < best_err:
            best, best_err = cand, err
    return best


# ------------------------------------------------------------------- assembly
def build_stance(name: str, num_sims: int = None) -> dict:
    """Build one stance's complete published table (payouts, counts, reveal sources)."""
    stance = STANCES[name]
    num_sims = num_sims or DEFAULT_NUM_SIMS
    pools = pool_pmf(stance)
    norm_thousandths = solve_pool_norm(stance, pools)

    e_win_cents = _expected_win_cents(stance, pools, norm_thousandths)
    assert e_win_cents > 0, f"{name}: no winning payout mass"
    win_rate = RTP_TARGET / (e_win_cents / 100)
    assert 0 < win_rate < 1, f"{name}: derived win rate {float(win_rate)} out of range"

    # ---- unconditional outcome probabilities, keyed by payout cents
    q = {}                 # cents -> Fraction (probability of this payout)
    kind = {}              # cents -> "body" | "golden"
    tier_of = {}           # cents -> tier name (golden outcomes only)
    body_sources = {}      # cents -> [[rounds, pool_h, weight], ...]
    pool_sources = []      # [[rounds, pool_h, weight], ...] (the full pool PMF)
    zero_body_mass = Fraction(0)

    for (rounds, pool_h), p in sorted(pools.items()):
        pool_sources.append([rounds, pool_h, float(p)])

    for (tier, mult, prob) in golden_pmf(stance):
        if tier == "none":
            for (rounds, pool_h), p in sorted(pools.items()):
                cents = body_cents(pool_h, norm_thousandths)
                if cents == 0:
                    # Snapped below 0.1x: pays nothing, so it is a loss.
                    zero_body_mass += win_rate * prob * p
                    continue
                q[cents] = q.get(cents, Fraction(0)) + win_rate * prob * p
                kind[cents] = "body"
                body_sources.setdefault(cents, []).append([rounds, pool_h, float(p)])
        else:
            cents = golden_cents(mult)
            assert cents > 0, f"{name}: golden tier {tier} snapped to zero"
            q[cents] = q.get(cents, Fraction(0)) + win_rate * prob
            # A tier value colliding with a body rung would make the reveal
            # ambiguous (and merge two very different presentations).
            assert kind.get(cents, "golden") == "golden", (
                f"{name}: golden tier {tier} ({cents}c) collides with a body payout"
            )
            kind[cents] = "golden"
            tier_of[cents] = tier

    # ---- integer book counts; the loss bucket absorbs the residual
    count = {c: max(1, int(round(float(num_sims * qc)))) for c, qc in q.items()}
    loss_count = num_sims - sum(count.values())
    assert loss_count > 0, f"{name}: no loss mass ({sum(count.values())} win books of {num_sims})"

    def realised(counts: dict, losses: int) -> Fraction:
        return Fraction(sum(c * n for c, n in counts.items()), 100 * num_sims)

    # One-book correction: nudge the most common body rung until realised RTP
    # (exactly what the ACP recomputes from the LUT) is as close to target as a
    # single book allows.
    tune_cents = max((c for c in count if kind[c] == "body"), key=lambda c: count[c])
    for _ in range(2000):
        cur = realised(count, loss_count)
        if cur == RTP_TARGET:
            break
        step = 1 if cur < RTP_TARGET else -1
        if count[tune_cents] + step < 1 or loss_count - step < 1:
            break
        nxt_count = dict(count)
        nxt_count[tune_cents] += step
        if abs(realised(nxt_count, loss_count - step) - RTP_TARGET) >= abs(cur - RTP_TARGET):
            break
        count = nxt_count
        loss_count -= step

    rtp = realised(count, loss_count)
    achieved_win_rate = Fraction(sum(count.values()), num_sims)
    # A pot that snapped below 0.1x pays nothing, so its mass silently becomes part
    # of the loss bucket (which is `num_sims - sum(win counts)`). That is the right
    # behaviour but it should never actually happen — the smallest published pot is
    # well above 0.1x — so surface it rather than letting it pass unnoticed.
    assert zero_body_mass == 0, (
        f"{name}: {float(zero_body_mass) * 100:.4f}% of win mass snapped below 0.1x and "
        f"was folded into the loss bucket; pool_norm {norm_thousandths / 1000} is too large"
    )
    assert sum(count.values()) + loss_count == num_sims, f"{name}: book counts do not sum"
    assert RTP_FLOOR <= rtp <= RTP_CEIL, (
        f"{name}: realised RTP {float(rtp):.6f} outside [{float(RTP_FLOOR)}, {float(RTP_CEIL)}]"
    )
    # Forcing a sub-1-book tail outcome to 1 book costs RTP that the correction pass
    # takes back out of the body, which shows up as win-rate drift. Fail loudly
    # rather than silently shipping a hit rate the design never intended.
    drift = abs(achieved_win_rate - win_rate)
    assert drift <= _MAX_WIN_RATE_DRIFT, (
        f"{name}: win rate {float(achieved_win_rate) * 100:.3f}% drifted "
        f"{float(drift) * 100:.3f}pp from the {float(win_rate) * 100:.3f}% design target "
        f"(gate {float(_MAX_WIN_RATE_DRIFT) * 100:.1f}pp). num_sims={num_sims} is too "
        f"small for this mode's tail — raise NUM_SIMS."
    )

    max_cents = max(count)
    return {
        "stance": name,
        "label": stance["label"],
        "order": stance["order"],
        "hp": stance["hp"],
        "num_sims": num_sims,
        "pool_norm": Fraction(norm_thousandths, 1000),
        "win_rate": achieved_win_rate,
        "design_win_rate": win_rate,
        "rtp": rtp,
        "max_win": Fraction(max_cents, 100),
        "count": count,
        "loss_count": loss_count,
        "kind": kind,
        "tier_of": tier_of,
        "body_sources": body_sources,
        "pool_sources": pool_sources,
        "golden_sources": [[t, m, float(p)] for t, m, p in golden_pmf(stance)],
        "zero_body_mass": zero_body_mass,
        "slots": [
            {"index": i, "cost": ch / 100.0, "costHundredths": ch, "name": nm, "dmgMin": lo, "dmgMax": hi}
            for i, (ch, nm, lo, hi) in enumerate(stance["slots"])
        ],
        "heal_slot": next(i for i, s in enumerate(stance["slots"]) if s[0] == stance["heal_cost_h"]),
        "rounds": {str(r): float(w) for r, w in sorted(stance["rounds"].items())},
    }


def build_stances(num_sims: int = None) -> list:
    """Every stance, in publish order."""
    return [build_stance(n, num_sims) for n in STANCE_NAMES]


# ------------------------------------------------------ constrained cost sampler
def cost_sequence_counts(costs: tuple, picks: int) -> dict:
    """DP table: counts[(picks_left, total_left)] = # sequences reaching that total.

    Used to draw a cost sequence uniformly at random *conditioned* on summing to
    the pool the book already fixed — the transcript must reproduce the drawn pot
    exactly.
    """
    table = {(0, 0): 1}
    for n in range(1, picks + 1):
        prev = {k[1]: v for k, v in table.items() if k[0] == n - 1}
        for total, cnt in prev.items():
            for c in costs:
                key = (n, total + c)
                table[key] = table.get(key, 0) + cnt
    return table
