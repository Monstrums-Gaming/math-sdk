"""
Chart Race (2_11) — game configuration.

Three fictional company chart lines race toward a fixed SETTLEMENT line; the player
bets on where their picked company finishes. Two pick-neutral markets, each its own
cost-1.0 two-outcome mode:

    highest   the picked company finishes 1st of 3   pays 3.00x
    lowest    the picked company finishes 3rd of 3   pays 3.00x

Books are **pick-neutral** (the 3_0_boat_race precedent): the book addresses abstract
racers r0..r2 where **r0 is always the player's pick** — the client maps the chosen
company onto r0 at render time, so all three companies have identical odds *by
construction* and one book pool per market serves every pick.

Like the dice/limbo/market-crash/trading-roulette family this is a **direct-probability**
game: no reels, no free spins, Rust optimiser disabled, LUT weights uniform (1 per book),
odds authored entirely by the distribution quotas below.

## Certified outcome, cosmetic chart

Every book carries `raceResult.finishOrder` — the certified finishing order of the three
racers (a permutation of [0,1,2], indexed by place) — and `playerPlace` (r0's place).
Unlike boat_race there is NO rank timeline: the chart is a continuous line race, so the
book certifies the ORDER only and the frontend draws seeded cosmetic paths that are
obliged to arrive at exactly that order at the settlement line (the 2_9 `landRow`
philosophy — the animation is a rendering of the book, never a source of it).

## Per-mode pinned odds, NOT a uniform race

A fair 3-way race gives each company 1/3; 3.00x at 1/3 returns 100%. The quoted 3.00x
therefore rides on a certified win chance pinned BELOW the fair third — the smallest-
denominator rational (the limbo/market-crash Stern-Brocot descent) whose realised RTP
lands in [96.00%, 96.70%]:

    8/25 = 32.00% at 3.00x  ->  RTP exactly 96.00%  (both modes; cross-mode spread 0)

Consequence — stated plainly wherever the odds appear: the finishing-order frequencies a
player observes are the mixture of the conditional laws below at the mode's certified
win probability, not a uniform race. The odds themselves derive from the lookup table
alone; `verify_books.py` proves mechanically that the rendered order cannot move them.

## The conditional presentation law

Verdict-first generation (the boat_race rule): the criteria fixes the payout, the payout
fixes r0's place, the order is manufactured to honestly produce it — never the reverse.

    highest  win  -> r0 place 1;  loss -> r0 place uniform over {2, 3}
    lowest   win  -> r0 place 3;  loss -> r0 place uniform over {1, 2}

The two rivals are shuffled uniformly into the remaining places. Both conditional laws
are re-proved over every published book by `verify_books.py` (loss-place balance within
4 sigma).

## num_sims = k * b, seed offsets — inherited from 2_8/2_9

Each mode publishes N = k*b books with W = k*a winners (Fraction(W, N) == Fraction(a, b)
exactly; k chosen so N >= 5000 and W >= 150): here k = 200 -> 5,000 books per mode,
1,600 winners. The `+0.5` quotas MUST be computed from the published W/N, never a/b
(get_sim_splits does int(num_sims * quota)). Per-mode seed offsets keyed off the MODE
INDEX with a stride exceeding every mode's num_sims (payout cents are identical across
the two modes, so cents can't key the offset — the 2_9 rationale).

## Global wincap

`wincap = 3.0` equals both modes' win payout, so EVERY winning book uses the `wincap`
criteria / `force_wincap: True` and carries a `wincap` event (the boat_race 1st-place
and 2_9 zone_line precedent) — the frontend needs a no-op-or-better `wincap` handler.

## ACP rules satisfied

  1. 0.1x LUT grid — 300 cents is a multiple of 10 (`lut_grid_exempt = False`).
  2. Per-mode RTP 96.00% in [90%, 96.70%].
  3. Cross-mode spread — exactly 0 (both modes share the same a/b and multiplier).
  4. Base bet mode cost = 1.0.
  5. Volatility — two-outcome payout std sqrt(0.96*3 - 0.96^2) = 1.3994 >= 0.60.
  6. num_sims x quota is an exact integer for every criteria (5000 = 1600 + 3400).
"""

import os
from fractions import Fraction
from math import ceil, floor, sqrt

from src.config.config import Config
from src.config.distributions import Distribution
from src.config.betmode import BetMode

# RTP window: the Stern-Brocot pin must land inside [96.00%, 96.70%] (the ACP ceiling).
RTP_FLOOR = 0.9600
RTP_CEIL = 0.9670
WINCAP = 3.0  # both markets' win payout IS the game's maximum win
_EPS = 1e-9

NUM_RACERS = 3
MULTIPLIER = 3.0  # the quoted price of both markets

# Book-count floors (2_8/2_9 rationale): NUM_SIMS_MIN keeps the served outcome
# unidentifiable; WIN_BOOKS_MIN guarantees enough distinct winning orders that a win
# never looks canned (the intra-order chart excursion also varies per book id
# client-side).
NUM_SIMS_MIN = 5000
WIN_BOOKS_MIN = 150

# (mode name, r0's place on a WIN, r0's candidate places on a LOSS)
MARKETS = [
    ("highest", 1, (2, 3)),
    ("lowest", 3, (1, 2)),
]

# Per-mode RNG seed offset stride (2_8/2_9 rationale), keyed off the MODE INDEX because
# payout cents are identical across the two markets. The stride exceeds every mode's
# num_sims so no two modes can ever collide on a seed.
_MODE_SEED_STRIDE = 1_000_003


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
    """Chart Race configuration — two pick-neutral finishing-place markets."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        super().__init__()
        self.game_id = "2_11_chart_race"
        self.provider_number = 2  # placeholder — confirm ACP-assigned value before prod upload
        self.provider_name = "monstrum"
        self.game_name = "Chart Race"
        self.working_name = "Chart Race"
        self.win_type = "scatter"
        self.lut_grid_exempt = False
        self.construct_paths()

        # No board mechanic in the engine sense: a single resolved round (1 reel x 1 row).
        self.num_reels = 1
        self.num_rows = [1] * self.num_reels

        self.tiers = self._build_tiers()
        self.wincap = WINCAP  # global cap; every BetMode.max_win is this value
        self.rtp = max(t["rtp"] for t in self.tiers)
        self.mode_params = {}

        # Minimal boardless scaffolding (mirrors the limbo / market-crash games).
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
        """One row per market.

        The win probability is the smallest-denominator rational a/b whose realised RTP
        (a/b)*M lands in [96.00%, 96.70%]. Published book counts are then scaled by an
        integer k -- N = k*b sims of which W = k*a win -- so the odds are unchanged
        (Fraction(W, N) == Fraction(a, b)) while each mode carries enough books.
        """
        rows = []
        for index, (mode_name, win_place, lose_places) in enumerate(MARKETS):
            payout_cents = round(MULTIPLIER * 100)
            assert payout_cents % 10 == 0, f"payout {MULTIPLIER} off the 0.1x grid"
            m_frac = Fraction(payout_cents, 100)
            lo = Fraction(round(RTP_FLOOR * 10000), 10000) / m_frac
            hi = Fraction(round(RTP_CEIL * 10000), 10000) / m_frac
            prob = _simplest_fraction_in(lo, hi)
            a, b = prob.numerator, prob.denominator
            realised_rtp = float(prob * m_frac)
            assert RTP_FLOOR - _EPS <= realised_rtp <= RTP_CEIL + _EPS, (
                f"market {mode_name} RTP {realised_rtp:.4f} outside band"
            )

            # Scale the book count up while holding the odds EXACTLY.
            k = max(ceil(NUM_SIMS_MIN / b), ceil(WIN_BOOKS_MIN / a))
            num_sims, winners = k * b, k * a
            assert Fraction(winners, num_sims) == prob, "k scaling changed the odds"

            # Two-outcome payout std: Var = R*M - R^2. ACP rates Base Volatility off the
            # game's tamest mode against a 0.60 floor.
            std = sqrt(realised_rtp * MULTIPLIER - realised_rtp**2)

            rows.append(
                {
                    "mode_name": mode_name,
                    "win_place": win_place,
                    "lose_places": lose_places,
                    "multiplier": float(MULTIPLIER),
                    "payout_cents": payout_cents,
                    "win_chance": a / b,
                    "rtp": realised_rtp,
                    "std": std,
                    "a": a,  # numerator of the exact win probability
                    "b": b,  # denominator ditto
                    "k": k,  # book-count multiplier
                    "W": winners,   # winning book count  (k*a)
                    "N": num_sims,  # num_sims            (k*b)
                    # Keyed off the mode INDEX: payout cents repeat across markets.
                    "seed_offset": (index + 1) * _MODE_SEED_STRIDE,
                }
            )
        return rows

    # ---------------------------------------------------------------- betmodes
    def _build_bet_modes(self) -> list:
        """One bet mode per market; a forced win/lose split, global max_win."""
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
            # module docstring: get_sim_splits does int(num_sims * quota)).
            win_quota = (W + 0.5) / N
            lose_quota = (N - W + 0.5) / N

            # Both markets' win payout equals the global cap, so every win forces (and
            # emits) a `wincap` event — the boat_race 1st-place / 2_9 zone_line pattern.
            assert payout >= self.wincap
            win_conditions = {**dummy_reels, "force_wincap": True, "force_freegame": False}
            lose_conditions = {**dummy_reels, "force_wincap": False, "force_freegame": False}

            # Mode names must be DOT-FREE (the ACP publisher parses <mode> out of
            # books_<mode>.jsonl.zst). Market names are plain lowercase words.
            name = row["mode_name"]
            self.mode_params[name] = {
                "mode_name": name,
                "num_racers": NUM_RACERS,
                "win_place": row["win_place"],
                "lose_places": row["lose_places"],
                "multiplier": row["multiplier"],
                "payout_cents": row["payout_cents"],
                "rtp": row["rtp"],
                "win_chance": row["win_chance"],
                "num_sims": N,
                "seed_offset": row["seed_offset"],
            }

            distributions = [
                Distribution(
                    criteria="wincap",
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
                    max_win=self.wincap,  # GLOBAL cap (2_5/2_7/2_8/2_9 convention)
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
        assert self.wincap == WINCAP == max(t["multiplier"] for t in self.tiers), (
            "wincap must equal the markets' win payout"
        )
        assert len(self.bet_modes) == len(self.tiers) == len(MARKETS) == 2, (
            "expected exactly 2 market modes"
        )
        assert [t["mode_name"] for t in self.tiers] == ["highest", "lowest"]

        # The market semantics must be coherent for 3 racers.
        for t in self.tiers:
            assert 1 <= t["win_place"] <= NUM_RACERS
            assert t["win_place"] not in t["lose_places"]
            assert sorted((t["win_place"],) + t["lose_places"]) == list(
                range(1, NUM_RACERS + 1)
            ), f"market {t['mode_name']} places malformed"

        rtps = [t["rtp"] for t in self.tiers]
        assert max(rtps) - min(rtps) <= 0.005 + _EPS, (
            f"cross-mode RTP spread {max(rtps) - min(rtps):.6f} > 0.50%"
        )
        stds = [t["std"] for t in self.tiers]
        assert min(stds) >= 0.60, (
            f"tamest mode std {min(stds):.4f} below the ACP Base-Volatility floor of 0.60"
        )
        offsets = {t["seed_offset"] for t in self.tiers}
        assert len(offsets) == len(self.tiers), "duplicate per-mode seed offset"
        assert _MODE_SEED_STRIDE > max(t["N"] for t in self.tiers), (
            "seed stride must exceed every mode's num_sims or two modes share seeds"
        )

        for i, row in enumerate(self.tiers):
            m, W, N, cents = row["multiplier"], row["W"], row["N"], row["payout_cents"]
            a, b, k = row["a"], row["b"], row["k"]
            mode = self.bet_modes[i]

            assert m >= 1.40, f"payout {m} below the 1.40x volatility floor"
            assert isinstance(cents, int) and cents > 100, f"payout {m} must be > 100 cents"
            assert round(m * 100) == cents, f"payout {m} disagrees with cents {cents}"
            assert cents % 10 == 0, f"payout {m} off the 0.1x grid ({cents} cents)"
            assert RTP_FLOOR - _EPS <= (W / N) * m <= RTP_CEIL + _EPS, (
                f"market {row['mode_name']} RTP {(W / N) * m:.4f} outside band"
            )
            # k must not have perturbed the odds by even one ULP.
            assert Fraction(W, N) == Fraction(a, b), (
                f"k scaling changed the odds for {row['mode_name']}"
            )
            assert k >= 1 and N == k * b and W == k * a, (
                f"N/W not a clean k multiple for {row['mode_name']}"
            )
            assert N >= NUM_SIMS_MIN, f"num_sims {N} below the {NUM_SIMS_MIN} floor"
            assert W >= WIN_BOOKS_MIN, f"only {W} winning books for {row['mode_name']}"
            assert 0 < W < N, f"degenerate split for {row['mode_name']}"
            assert mode.get_cost() == 1.0, f"mode {row['mode_name']} cost must be 1.0"
            assert mode._wincap == WINCAP, f"mode {row['mode_name']} max_win must be {WINCAP}"
            # Both markets pay the cap, so both use the wincap criteria on the win side.
            assert mode.get_distributions()[0]._criteria == "wincap"
            assert mode.get_name() == row["mode_name"], f"mode {i} name off-convention"

            # Deterministic, float-safe split (no get_sim_splits leftover).
            win_quota = (W + 0.5) / N
            lose_quota = (N - W + 0.5) / N
            assert int(N * win_quota) == W, f"win split off for {row['mode_name']}"
            assert int(N * lose_quota) == N - W, f"lose split off for {row['mode_name']}"
            assert int(N * win_quota) + int(N * lose_quota) == N, (
                f"split != N for {row['mode_name']}"
            )
