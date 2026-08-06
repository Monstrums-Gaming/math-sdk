"""
Market Crash (2_8) — game configuration.

A **crash** game dressed as a market index. The player commits a **SELL AT** cash-out
multiplier T *before* the bet; a market index climbs from 1.00x and either reaches T
(win T x) or **rugs** short of it (lose, pay 0).

The RGS is a certified *replay* system — the payout is frozen in the book at publish
time — so a mid-flight manual cash-out can never be paid. The target must therefore BE
the published bet mode, which makes this structurally the `2_5_limbo_frankenstein`
model: one cost-1.0 two-outcome mode per rung, `crash_<cents>`. Like the dice (`2_4`),
limbo (`2_5`), crypto-pulse (`2_7_prediction_market`) and tap-trade (`2_6`) games this is
a **direct-probability** game: no reels, no free spins, Rust optimiser disabled. The odds
come straight from the distribution quotas.

## Modes: a 30-rung SELL AT ladder

Every rung is its own dot-free mode `crash_<cents>` (the ACP publisher parses `<mode>`
out of `books_<mode>.jsonl.zst`, so a "." would collide with the extension), each
`cost = 1.0`. For each target T the win probability is the smallest-denominator rational
a/b whose realised RTP `(a/b)*T` lands in [96.15%, 96.65%] (`_simplest_fraction_in`, the
limbo Stern-Brocot descent).

**Ladder (1.40x .. 100x, 30 rungs — dense below 10x):** 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2,
2.2, 2.5, 2.8, 3, 3.5, 4, 4.5, 5, 6, 7, 8, 9, 10, then the sparse tail 12, 15, 20, 25,
30, 40, 50, 65, 80, 100. Rung-to-rung ratio 1.053x-1.333x, tightest where the mass of
play sits (win chance 19-69%) and loosest in the lottery tail. The 100x cap is the Limbo
`base_100` precedent that passed ACP's ETL/CVaR risk validators. The **floor is 1.40x**:
a two-outcome mode's payout std is `sqrt(R*T - R^2)`, giving 0.48 / 0.57 / 0.649 at
T = 1.20 / 1.30 / 1.40, and ACP rates Base Volatility off the game's *tamest* mode
against a 0.60 floor — the exact reason Limbo's approved ladder starts at 1.40x.

## Why the RTP window is [96.15%, 96.65%] and not the family's [96.00%, 96.70%]

The ACP dashboard string is "Return to Player across all modes must be within +/-0.5% of
each other". This repo has always read that as `max - min <= 1.00%` (asserted in `2_5`,
`2_6`, `2_7`), and those builds ship a 0.667% spread — which passes that reading and
*fails* a literal `max - min <= 0.5%` one. The wide window exists only to keep the
Stern-Brocot denominator `b` small, because those games set `num_sims = b`. This game
scales `num_sims` to `k*b` anyway (see below), so `b` is no longer a binding constraint
and the window can be tightened for free. `[96.15%, 96.65%]` yields a realised spread of
**0.4563%**, satisfying *both* readings, and it pins the top rung to exactly `1/104` —
bit-identical to the already-ACP-approved `2_5` `base_100_00`.

## num_sims = k * b, not b

With `num_sims = b`, `crash_10000` would have **one** winning book: every 100x win in the
game's history would serve the same bytes, so the same `crashPoint` — datamineable and a
visibly canned animation. Each mode therefore publishes `N = k*b` books with `W = k*a`
winners, `k` chosen so `N >= 5000` and `W >= 150`. `Fraction(W, N) == Fraction(a, b)`
exactly, so every ACP-derived statistic (RTP, hit rate, std, Max Payout, ETL, CVaR) is
bit-identical to a `k = 1` build — `k` is provably risk-neutral, and `_validate` asserts
it. Total: 177,924 books across the 30 modes (~1.2 MB compressed).

The `+0.5` quotas MUST be computed from the published `W`/`N`, never from `a`/`b`:
`get_sim_splits` does `int(num_sims * quota)`, so `(a+0.5)/b` with `num_sims = k*b`
over-allocates winners by `k/2`.

## crashPoint

Each book carries the certified rug multiplier in integer hundredths (see
`game_executables.py` for the sampler and `game_events.py` for the field). It is drawn
from the canonical crash law `P(C >= x) = R/x` — whose value at x = T is exactly this
mode's published win probability — conditioned on the pre-assigned verdict. It is
presentation + fairness data only and cannot move the odds; `build_odds_bundle.py`
asserts that mechanically. Per-mode display cap `min(200*T, 10000x)` keeps the truncation
atom a uniform ~0.5% of wins on every rung.

## Global wincap (not per-mode)

`BetMode.max_win` is the global 100.0 on every mode (the `2_5`/`2_7` convention, NOT
`2_6`'s per-mode cap), so the engine's `wincap` event fires only on `crash_10000` wins —
150 books — rather than on all ~27k winning books across the ladder. That is semantically
correct (the game's max win genuinely is 100x, carried by the top rung) and keeps this a
minimal delta from the approved `2_5` build. The web side still needs a no-op `wincap`
handler.

## ACP rules satisfied

  1. 0.1x LUT grid — every payout is a multiple of 0.10 (`lut_grid_exempt = False`).
  2. Per-mode RTP in [90%, 96.70%] — every rung pinned into [96.15%, 96.65%].
  3. Cross-mode spread — 0.4563%, inside both the +/-0.5% and the 1.00% readings.
  4. Base bet mode cost = 1.0.
  5. Risk: every mode is a two-outcome all-or-nothing bet — the shape ACP approved for
     Limbo's 1.40x-100x ladder, with the top rung numerically identical to `base_100_00`.
"""

import os
from fractions import Fraction
from math import ceil, floor, sqrt

from src.config.config import Config
from src.config.distributions import Distribution
from src.config.betmode import BetMode

# Tightened RTP window — see the "Why the RTP window" section above.
RTP_FLOOR = 0.9615
RTP_CEIL = 0.9665
WINCAP = 100.0  # global maximum win (the top ladder rung)
_EPS = 1e-9

# Book-count floors. NUM_SIMS_MIN gives every mode enough books that the served outcome
# is not identifiable; WIN_BOOKS_MIN guarantees enough DISTINCT winning crashPoints that
# the win animation never repeats visibly (at 150, a player needs ~150/p bets before
# repeats are statistically apparent — ~15,600 bets on the top rung).
NUM_SIMS_MIN = 5000
WIN_BOOKS_MIN = 150

# crashPoint display cap, per mode: min(200 * target, 10000.00x). Truncating an
# unbounded 1/x tail creates an atom at the cap of size target/cap, so a PER-MODE
# multiple keeps that atom a uniform 0.5% of wins on every rung (1.0% on the top rung,
# where the absolute cap binds). A single global 10000x cap would let a 1.40x win display
# 10000x — absurd on the chart, and it degenerates the frontend's log axis; a global
# 1000x cap would park 10% of top-rung wins on one canned value.
CRASH_CAP_MULTIPLE = 200
CRASH_CAP_ABS_HUNDREDTHS = 1_000_000  # 10,000.00x

# Per-mode RNG seed offset stride. reset_seed(sim) seeds random with sim+1, so without an
# offset sim #7 in crash_140 and sim #7 in crash_200 would draw the SAME uniform and
# crashPoints would be rank-correlated across the whole ladder. The stride exceeds every
# mode's num_sims (max 15,600) so no two modes can ever collide on a seed.
_MODE_SEED_STRIDE = 1_000_003

# The published SELL AT ladder. Each value becomes its own dot-free mode
# "crash_<cents>" with an independently-derived win probability pinning realised RTP into
# [96.15%, 96.65%]. Every value is a multiple of 0.10 (0.1x LUT grid). Floor 1.40x clears
# the ACP volatility floor; the 100x cap is the Limbo-approved ceiling.
_SELL_AT = [
    1.40, 1.50, 1.60, 1.70, 1.80, 1.90, 2.00,
    2.20, 2.50, 2.80, 3.00, 3.50, 4.00, 4.50, 5.00,
    6.00, 7.00, 8.00, 9.00, 10.00,
    12.00, 15.00, 20.00, 25.00, 30.00, 40.00, 50.00, 65.00, 80.00, 100.00,
]


def _simplest_fraction_in(lo: Fraction, hi: Fraction) -> Fraction:
    """Smallest-denominator fraction x with lo <= x <= hi (requires 0 < lo <= hi)."""
    if lo > hi:
        lo, hi = hi, lo
    n = floor(lo)
    if n >= lo:
        return Fraction(n)
    if n + 1 <= hi:
        return Fraction(n + 1)
    return n + 1 / _simplest_fraction_in(1 / (hi - n), 1 / (lo - n))


class GameConfig(Config):
    """Market Crash configuration — a 30-rung SELL AT win/lose ladder."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        super().__init__()
        self.game_id = "2_8_market_crash"
        self.provider_number = 2  # placeholder — confirm ACP-assigned value before prod upload
        self.provider_name = "monstrum"
        self.game_name = "Market Crash"
        self.working_name = "Market Crash"
        self.win_type = "scatter"
        self.lut_grid_exempt = False
        self.construct_paths()

        # No board mechanic: model a single resolved round (1 reel x 1 row).
        self.num_reels = 1
        self.num_rows = [1] * self.num_reels

        self.tiers = self._build_tiers()
        self.wincap = WINCAP  # global cap; every BetMode.max_win is this value
        self.rtp = max(t["rtp"] for t in self.tiers)
        self.mode_params = {}

        # Minimal boardless scaffolding (mirrors the limbo / crypto-pulse games).
        self.paytable = {(1, "M"): 1.0}
        self.include_padding = False
        self.special_symbols = {"wild": [], "scatter": [], "multiplier": []}
        self.freespin_triggers = {self.basegame_type: {}, self.freegame_type: {}}
        self.anticipation_triggers = {self.basegame_type: 0, self.freegame_type: 0}

        reels = {"BR0": "BR0.csv"}
        self.reels = {}
        for r, f in reels.items():
            self.reels[r] = self.read_reels_csv(os.path.join(self.reels_path, f))
        self.padding_reels = {
            self.basegame_type: self.reels["BR0"],
            self.freegame_type: self.reels["BR0"],
        }

        self.bet_modes = self._build_bet_modes()
        self._validate()

    # ------------------------------------------------------------------ tiers
    def _build_tiers(self) -> list:
        """One row per SELL AT rung T.

        The win probability is the smallest-denominator rational a/b whose realised RTP
        (a/b)*T lands in [96.15%, 96.65%]. Published book counts are then scaled by an
        integer k -- N = k*b sims of which W = k*a win -- so the odds are unchanged
        (Fraction(W, N) == Fraction(a, b)) while each mode carries enough books that its
        crashPoints do not visibly repeat.
        """
        rows = []
        for sell_at in _SELL_AT:
            payout_cents = round(sell_at * 100)
            assert payout_cents % 10 == 0, f"payout {sell_at} off the 0.1x grid"
            t_frac = Fraction(payout_cents, 100)
            lo = Fraction(round(RTP_FLOOR * 10000), 10000) / t_frac
            hi = Fraction(round(RTP_CEIL * 10000), 10000) / t_frac
            prob = _simplest_fraction_in(lo, hi)
            a, b = prob.numerator, prob.denominator
            realised_rtp = float(prob * t_frac)
            assert RTP_FLOOR - _EPS <= realised_rtp <= RTP_CEIL + _EPS, (
                f"target {sell_at} RTP {realised_rtp:.4f} outside band"
            )

            # Scale the book count up while holding the odds EXACTLY: same fraction,
            # more books, so more distinct crashPoints per outcome.
            k = max(ceil(NUM_SIMS_MIN / b), ceil(WIN_BOOKS_MIN / a))
            num_sims, winners = k * b, k * a
            assert Fraction(winners, num_sims) == prob, "k scaling changed the odds"

            # Two-outcome payout std: Var = R*T - R^2. ACP rates Base Volatility off the
            # game's tamest mode against a 0.60 floor.
            std = sqrt(realised_rtp * sell_at - realised_rtp**2)

            # Share of LOSING rounds that rug instantly at 1.00x. Derived from the crash
            # law's atom at C = 1 (1 - R) renormalised over the loss mass (T - R)/T.
            q_atom = (1.0 - realised_rtp) * sell_at / (sell_at - realised_rtp)

            rows.append(
                {
                    "sell_at": sell_at,
                    "multiplier": sell_at,  # the payout IS the target
                    "payout_cents": payout_cents,
                    "win_chance": a / b,
                    "rtp": realised_rtp,
                    "std": std,
                    "q_atom": q_atom,
                    "a": a,  # numerator of the exact win probability
                    "b": b,  # denominator ditto
                    "k": k,  # book-count multiplier
                    "W": winners,   # winning book count  (k*a)
                    "N": num_sims,  # num_sims            (k*b)
                    "cap_hundredths": min(
                        CRASH_CAP_MULTIPLE * payout_cents, CRASH_CAP_ABS_HUNDREDTHS
                    ),
                    "seed_offset": payout_cents * _MODE_SEED_STRIDE,
                }
            )
        return rows

    # ---------------------------------------------------------------- betmodes
    def _build_bet_modes(self) -> list:
        """One bet mode per SELL AT rung; a forced win/lose split, global max_win."""
        dummy_reels = {
            "reel_weights": {
                self.basegame_type: {"BR0": 1},
                self.freegame_type: {"BR0": 1},
            }
        }

        modes = []
        for row in self.tiers:
            payout = row["multiplier"]
            W, N = row["W"], row["N"]

            # Floor-safe quotas computed from the PUBLISHED counts (not a/b — see the
            # module docstring: get_sim_splits does int(num_sims * quota), so (a+0.5)/b
            # against num_sims = k*b would over-allocate winners by k/2).
            win_quota = (W + 0.5) / N
            lose_quota = (N - W + 0.5) / N

            # Only the top rung's payout reaches the global cap, so only it forces (and
            # emits) a `wincap` event. Mirrors 2_5_limbo_frankenstein.
            if payout >= self.wincap:
                win_criteria_name = "wincap"
                win_conditions = {**dummy_reels, "force_wincap": True, "force_freegame": False}
            else:
                win_criteria_name = "win"
                win_conditions = {**dummy_reels, "force_wincap": False, "force_freegame": False}
            lose_conditions = {**dummy_reels, "force_wincap": False, "force_freegame": False}

            # Mode names must be DOT-FREE: the ACP publisher parses <mode> out of
            # books_<mode>.jsonl.zst, so a "." collides with the extension. The target is
            # encoded as integer cents, which the frontend parses back out of the key.
            name = f"crash_{row['payout_cents']}"
            self.mode_params[name] = {
                "sell_at": row["sell_at"],
                "sell_at_cents": row["payout_cents"],
                "multiplier": payout,
                "rtp": row["rtp"],
                "win_chance": row["win_chance"],
                "num_sims": N,
                "cap_hundredths": row["cap_hundredths"],
                "seed_offset": row["seed_offset"],
            }

            distributions = [
                Distribution(
                    criteria=win_criteria_name,
                    quota=win_quota,
                    win_criteria=payout,
                    conditions=win_conditions,
                ),
                Distribution(
                    criteria="0",
                    quota=lose_quota,
                    win_criteria=0.0,
                    conditions=lose_conditions,
                ),
            ]

            modes.append(
                BetMode(
                    name=name,
                    cost=1.0,
                    rtp=row["rtp"],
                    max_win=self.wincap,  # GLOBAL cap (2_5/2_7 convention, not 2_6's per-mode)
                    auto_close_disabled=False,
                    is_feature=False,
                    is_buybonus=False,
                    distributions=distributions,
                )
            )
        return modes

    # ---------------------------------------------------------------- validate
    def _validate(self) -> None:
        """Guard the mode list before the engine consumes it."""
        top = max(t["sell_at"] for t in self.tiers)
        assert self.wincap == WINCAP == top, "wincap must equal the top ladder rung (100x)"
        assert len(self.bet_modes) == len(self.tiers) == len(_SELL_AT) == 30, (
            "expected exactly 30 ladder modes"
        )
        assert len({t["payout_cents"] for t in self.tiers}) == 30, "duplicate ladder rung"
        assert _SELL_AT == sorted(_SELL_AT), "ladder must be strictly increasing"
        assert max(t["payout_cents"] for t in self.tiers) == 10000, (
            "top rung must be 100x — the ACP ETL/CVaR ceiling"
        )

        rtps = [t["rtp"] for t in self.tiers]
        # 0.50%, satisfying BOTH readings of the ACP cross-mode rule (see docstring).
        assert max(rtps) - min(rtps) <= 0.005 + _EPS, (
            f"cross-mode RTP spread {max(rtps) - min(rtps):.6f} > 0.50%"
        )
        stds = [t["std"] for t in self.tiers]
        assert min(stds) >= 0.60, (
            f"tamest mode std {min(stds):.4f} below the ACP Base-Volatility floor of 0.60"
        )
        offsets = {t["seed_offset"] for t in self.tiers}
        assert len(offsets) == 30, "duplicate per-mode seed offset"
        assert _MODE_SEED_STRIDE > max(t["N"] for t in self.tiers), (
            "seed stride must exceed every mode's num_sims or two modes share seeds"
        )

        for i, row in enumerate(self.tiers):
            t, W, N, cents = row["sell_at"], row["W"], row["N"], row["payout_cents"]
            a, b, k = row["a"], row["b"], row["k"]
            mode = self.bet_modes[i]

            assert t > 1.0 and t >= 1.40, f"target {t} below the 1.40x volatility floor"
            assert isinstance(cents, int) and cents > 100, f"payout {t} must be an integer > 100 cents"
            assert round(t * 100) == cents, f"payout {t} disagrees with cents {cents}"
            assert cents % 10 == 0, f"payout {t} off the 0.1x grid ({cents} cents)"
            assert RTP_FLOOR - _EPS <= (W / N) * t <= RTP_CEIL + _EPS, (
                f"mode payout {t} RTP {(W / N) * t:.4f} outside [{RTP_FLOOR}, {RTP_CEIL}]"
            )
            # k must not have perturbed the odds by even one ULP.
            assert Fraction(W, N) == Fraction(a, b), f"k scaling changed the odds for {t}"
            assert k >= 1 and N == k * b and W == k * a, f"N/W not a clean k multiple for {t}"
            assert N >= NUM_SIMS_MIN, f"num_sims {N} for {t}x below the {NUM_SIMS_MIN} floor"
            assert W >= WIN_BOOKS_MIN, f"only {W} winning books for {t}x"
            assert 0 < W < N, f"degenerate split for {t}x"
            assert mode.get_cost() == 1.0, f"mode {cents} cost must be 1.0 (ACP base-cost rule)"
            assert mode._wincap == WINCAP, f"mode {cents} max_win must be the global {WINCAP}"
            assert (mode.get_distributions()[0]._criteria == "wincap") == (cents == 10000), (
                f"mode {cents}: only the top rung may use the wincap criteria"
            )
            assert mode.get_name() == f"crash_{cents}", f"mode {i} name off-convention"
            assert 0.0 < row["q_atom"] < 1.0, f"instant-rug share for {t}x is not a probability"
            assert row["cap_hundredths"] > cents, f"crashPoint cap for {t}x is below its own target"

            # Deterministic, float-safe split (no get_sim_splits leftover).
            win_quota = (W + 0.5) / N
            lose_quota = (N - W + 0.5) / N
            assert int(N * win_quota) == W, f"win split off for payout {t}"
            assert int(N * lose_quota) == N - W, f"lose split off for payout {t}"
            assert int(N * win_quota) + int(N * lose_quota) == N, f"split != N for payout {t}"
