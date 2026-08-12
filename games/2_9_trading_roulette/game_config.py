"""
Trading Roulette (2_9) — game configuration.

A **zone board** game dressed as a market chart. Before the bet the player picks a CELL
on a board whose rows are price zones relative to the round's start line; a market index
line then animates for a few seconds and the ROW it crosses at the right edge decides the
round. The row is CERTIFIED in the book (`landRow`, the `2_8_market_crash` `crashPoint`
pattern made position-bearing), so the chart animation is a rendering of the book, never
a client-side invention.

Like dice (`2_4`), limbo (`2_5`), tap-trade (`2_6`), crypto-pulse (`2_7`) and market-crash
(`2_8`) this is a **direct-probability** game: no reels, no free spins, Rust optimiser
disabled. Odds come straight from the distribution quotas.

## The board

Fifteen landing rows, `landRow` in [-7, +7], mirrored around the start line (row 0):

    +7          off-scale tail OVER  ("over the line", beyond the fine rows)
    +6 .. +1    fine rows OVER  (farthest .. nearest)
     0          exactly ON the line
    -1 .. -6    fine rows UNDER (nearest .. farthest)
    -7          off-scale tail UNDER

Twenty-one bettable cells, each its own cost-1.0 two-outcome mode `zone_<id>`:

    zone_o1..zone_o6 / zone_u1..zone_u6   one fine row       pays 10,12,14,16,17,18x
    zone_bin_o  / zone_bin_u              inner band {1,2,3}  pays  4x
    zone_bout_o / zone_bout_u             outer band {4,5,6}  pays  5x
    zone_half_o / zone_half_u             whole side {1..7}   pays  2x
    zone_tail_o / zone_tail_u             off-scale  {7}      pays  8x
    zone_line                             on the line {0}     pays 21x

(The board quotes bookmaker odds: "9/1" pays 10x total, "1/1" pays 2x, "@20/1" pays 21x.)

## One wager = one cell (the frontend contract)

Each mode is an independent certified two-outcome bet. A multi-cell chip layout is played
by the frontend as a QUEUE of sequential wagers — one book, one line pass, one certified
`landRow` per cell — because independent books for two disjoint zones can both draw "Win",
which no single crossing row can render. The web app (apps/2-9-trading-roulette) owns that
queue; nothing in the math side spans cells.

## Per-mode pinned odds, NOT a coherent wheel

The board's quoted odds cannot form one landing distribution: the two 1/1 halves alone
would take 2 * R/2 = R of the mass, leaving 1 - R for the exact-line cell, whose 21x
payout would then return (1 - R) * 21 ~ 78% — nowhere near band. Real chip boards quote
per-cell bookmaker odds with the edge baked into each cell, and so does this game: each
mode's win probability is pinned independently (the limbo/market-crash Stern-Brocot
descent) into [96.15%, 96.65%], and `landRow` is sampled CONDITIONAL on the pre-assigned
verdict from the published landing weights (below). Consequence — stated plainly in the
fairness manifest — the landing-row frequencies a player observes depend on which cell
they bet (mixture of the conditional laws at their mode's win probability); the odds
themselves derive from the lookup table alone, and `build_odds_bundle.py` proves
mechanically that `landRow` cannot move them.

## The landing weights (presentation + fairness data)

Integer weights proportional to 1/multiplier — the same bell shape the quoted odds imply,
with unit 85680 = lcm(8, 10, 12, 14, 16, 17, 18, 21):

    |row|:   0     1     2     3     4     5     6     7
    weight:  4080  8568  7140  6120  5355  5040  4760  10710     (total 99466)

On a win the row is drawn from these weights restricted to the mode's zone; on a loss,
restricted to the complement. Both conditional laws are published in the odds bundle and
audited per mode within 4 sigma, so a canned or drifted sampler fails the build.

## num_sims = k * b, seed offsets, RTP window — inherited from 2_8_market_crash

Each mode publishes N = k*b books with W = k*a winners (Fraction(W, N) == Fraction(a, b)
exactly; k >= 1 chosen so N >= 5000 and W >= 150) — enough books that the served landRow
sequence is not identifiable and never visibly repeats. The `+0.5` quotas MUST be computed
from the published W/N, never a/b (get_sim_splits does int(num_sims * quota)). The RTP
window [96.15%, 96.65%] satisfies both readings of ACP's cross-mode rule (realised spread
here: 0.3979%). Per-mode seed offsets are keyed off the MODE INDEX — unlike 2_8, payout
cents are NOT unique across modes (every over cell has an under mirror at the same
multiplier) — with a stride exceeding every mode's num_sims.

## Global wincap

`BetMode.max_win` is the global 21.0 on every mode (the 2_5/2_7/2_8 convention), so the
engine's `wincap` event fires only on `zone_line` wins. The web side still needs a no-op
`wincap` handler.

## ACP rules satisfied

  1. 0.1x LUT grid — every payout is an integer multiplier (`lut_grid_exempt = False`).
  2. Per-mode RTP in [90%, 96.70%] — every cell pinned into [96.15%, 96.65%].
  3. Cross-mode spread — 0.3979%, inside both the +/-0.5% and the 1.00% readings.
  4. Base bet mode cost = 1.0.
  5. Risk: every mode is a two-outcome all-or-nothing bet, max payout 21x (far inside the
     Limbo-approved 100x ceiling); the tamest mode (2.0x) has payout std 0.9993, above the
     0.60 Base-Volatility floor.
"""

import os
from fractions import Fraction
from math import ceil, floor, sqrt

from src.config.config import Config
from src.config.distributions import Distribution
from src.config.betmode import BetMode

# Tightened RTP window — see the module docstring (inherited from 2_8_market_crash).
RTP_FLOOR = 0.9615
RTP_CEIL = 0.9665
WINCAP = 21.0  # global maximum win (the exact-line cell)
_EPS = 1e-9

# Book-count floors (2_8 rationale): NUM_SIMS_MIN keeps the served outcome unidentifiable;
# WIN_BOOKS_MIN guarantees enough distinct winning landRow draws that a win never looks
# canned (multi-row zones) and win books never visibly repeat (single-row zones, where the
# intra-row chart excursion varies per book id client-side).
NUM_SIMS_MIN = 5000
WIN_BOOKS_MIN = 150

# The landing rows. 0 = exactly on the line; +/-1..6 fine rows nearest..farthest;
# +/-7 the off-scale tails.
ROW_MIN, ROW_MAX = -7, 7
ROWS = tuple(range(ROW_MIN, ROW_MAX + 1))

# Landing weights per |row|, proportional to 1/multiplier with unit lcm(...) = 85680 so
# every weight is an exact integer. Presentation + fairness data only — the odds are
# pinned per mode and cannot be moved by these (build_odds_bundle.py proves it).
_LAND_WEIGHT_UNIT = 85680
LAND_WEIGHTS = {
    0: _LAND_WEIGHT_UNIT // 21,  # 4080
    1: _LAND_WEIGHT_UNIT // 10,  # 8568
    2: _LAND_WEIGHT_UNIT // 12,  # 7140
    3: _LAND_WEIGHT_UNIT // 14,  # 6120
    4: _LAND_WEIGHT_UNIT // 16,  # 5355
    5: _LAND_WEIGHT_UNIT // 17,  # 5040
    6: _LAND_WEIGHT_UNIT // 18,  # 4760
    7: _LAND_WEIGHT_UNIT // 8,   # 10710
}
LAND_WEIGHT_TOTAL = sum(LAND_WEIGHTS[abs(r)] for r in ROWS)  # 99466

# Fine-row multipliers, nearest (|row| = 1) .. farthest (|row| = 6).
_FINE_MULTS = [10, 12, 14, 16, 17, 18]

# Per-mode RNG seed offset stride (2_8 rationale), keyed off the MODE INDEX because
# payout cents repeat across over/under mirrors. The stride exceeds every mode's
# num_sims (max ~5.1k) so no two modes can ever collide on a seed.
_MODE_SEED_STRIDE = 1_000_003


def _build_zones() -> list:
    """The 21 bettable cells: (zone_id, rows tuple, multiplier)."""
    zones = []
    for k, mult in enumerate(_FINE_MULTS, start=1):
        zones.append((f"o{k}", (k,), mult))
    for k, mult in enumerate(_FINE_MULTS, start=1):
        zones.append((f"u{k}", (-k,), mult))
    zones.append(("bin_o", (1, 2, 3), 4))
    zones.append(("bin_u", (-1, -2, -3), 4))
    zones.append(("bout_o", (4, 5, 6), 5))
    zones.append(("bout_u", (-4, -5, -6), 5))
    zones.append(("half_o", tuple(range(1, 8)), 2))
    zones.append(("half_u", tuple(range(-7, 0)), 2))
    zones.append(("tail_o", (7,), 8))
    zones.append(("tail_u", (-7,), 8))
    zones.append(("line", (0,), 21))
    return zones


_ZONES = _build_zones()


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
    """Trading Roulette configuration — a 21-cell win/lose board."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        super().__init__()
        self.game_id = "2_9_trading_roulette"
        self.provider_number = 2  # placeholder — confirm ACP-assigned value before prod upload
        self.provider_name = "monstrum"
        self.game_name = "Trading Roulette"
        self.working_name = "Trading Roulette"
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
        """One row per bettable cell.

        The win probability is the smallest-denominator rational a/b whose realised RTP
        (a/b)*M lands in [96.15%, 96.65%]. Published book counts are then scaled by an
        integer k -- N = k*b sims of which W = k*a win -- so the odds are unchanged
        (Fraction(W, N) == Fraction(a, b)) while each mode carries enough books.
        """
        rows = []
        for index, (zone_id, zone_rows, mult) in enumerate(_ZONES):
            payout_cents = round(mult * 100)
            assert payout_cents % 10 == 0, f"payout {mult} off the 0.1x grid"
            m_frac = Fraction(payout_cents, 100)
            lo = Fraction(round(RTP_FLOOR * 10000), 10000) / m_frac
            hi = Fraction(round(RTP_CEIL * 10000), 10000) / m_frac
            prob = _simplest_fraction_in(lo, hi)
            a, b = prob.numerator, prob.denominator
            realised_rtp = float(prob * m_frac)
            assert RTP_FLOOR - _EPS <= realised_rtp <= RTP_CEIL + _EPS, (
                f"zone {zone_id} RTP {realised_rtp:.4f} outside band"
            )

            # Scale the book count up while holding the odds EXACTLY.
            k = max(ceil(NUM_SIMS_MIN / b), ceil(WIN_BOOKS_MIN / a))
            num_sims, winners = k * b, k * a
            assert Fraction(winners, num_sims) == prob, "k scaling changed the odds"

            # Two-outcome payout std: Var = R*M - R^2. ACP rates Base Volatility off the
            # game's tamest mode against a 0.60 floor.
            std = sqrt(realised_rtp * mult - realised_rtp**2)

            rows.append(
                {
                    "zone_id": zone_id,
                    "zone_rows": zone_rows,
                    "multiplier": float(mult),
                    "payout_cents": payout_cents,
                    "win_chance": a / b,
                    "rtp": realised_rtp,
                    "std": std,
                    "a": a,  # numerator of the exact win probability
                    "b": b,  # denominator ditto
                    "k": k,  # book-count multiplier
                    "W": winners,   # winning book count  (k*a)
                    "N": num_sims,  # num_sims            (k*b)
                    # Keyed off the mode INDEX: payout cents repeat across o/u mirrors.
                    "seed_offset": (index + 1) * _MODE_SEED_STRIDE,
                }
            )
        return rows

    # ---------------------------------------------------------------- betmodes
    def _build_bet_modes(self) -> list:
        """One bet mode per cell; a forced win/lose split, global max_win."""
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

            # Only the exact-line cell's payout reaches the global cap, so only it forces
            # (and emits) a `wincap` event. Mirrors 2_5/2_8.
            if payout >= self.wincap:
                win_criteria_name = "wincap"
                win_conditions = {**dummy_reels, "force_wincap": True, "force_freegame": False}
            else:
                win_criteria_name = "win"
                win_conditions = {**dummy_reels, "force_wincap": False, "force_freegame": False}
            lose_conditions = {**dummy_reels, "force_wincap": False, "force_freegame": False}

            # Mode names must be DOT-FREE (the ACP publisher parses <mode> out of
            # books_<mode>.jsonl.zst). Zone ids are letters/digits/underscores only.
            name = f"zone_{row['zone_id']}"
            self.mode_params[name] = {
                "zone_id": row["zone_id"],
                "zone_rows": row["zone_rows"],
                "multiplier": row["multiplier"],
                "payout_cents": row["payout_cents"],
                "rtp": row["rtp"],
                "win_chance": row["win_chance"],
                "num_sims": N,
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
                    max_win=self.wincap,  # GLOBAL cap (2_5/2_7/2_8 convention)
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
            "wincap must equal the top cell payout (21x, the exact-line cell)"
        )
        assert len(self.bet_modes) == len(self.tiers) == len(_ZONES) == 21, (
            "expected exactly 21 board modes"
        )
        assert len({t["zone_id"] for t in self.tiers}) == 21, "duplicate zone id"

        # The board itself must be coherent.
        assert LAND_WEIGHT_TOTAL == sum(LAND_WEIGHTS[abs(r)] for r in ROWS)
        assert all(w > 0 for w in LAND_WEIGHTS.values()), "landing weight must be positive"
        assert set(LAND_WEIGHTS) == set(range(0, ROW_MAX + 1)), "landing weights must cover |rows|"
        fine_over = [t for t in self.tiers if t["zone_id"].startswith("o")]
        fine_under = [t for t in self.tiers if t["zone_id"].startswith("u")]
        assert [t["multiplier"] for t in fine_over] == [t["multiplier"] for t in fine_under], (
            "over/under fine cells must mirror"
        )
        for t in self.tiers:
            zone = t["zone_rows"]
            assert len(zone) == len(set(zone)) > 0, f"zone {t['zone_id']} rows malformed"
            assert all(ROW_MIN <= r <= ROW_MAX for r in zone), f"zone {t['zone_id']} off-board"
            assert len(zone) < len(ROWS), f"zone {t['zone_id']} leaves no losing rows"

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
        assert len(offsets) == 21, "duplicate per-mode seed offset"
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
                f"zone {row['zone_id']} RTP {(W / N) * m:.4f} outside [{RTP_FLOOR}, {RTP_CEIL}]"
            )
            # k must not have perturbed the odds by even one ULP.
            assert Fraction(W, N) == Fraction(a, b), f"k scaling changed the odds for {row['zone_id']}"
            assert k >= 1 and N == k * b and W == k * a, f"N/W not a clean k multiple for {row['zone_id']}"
            assert N >= NUM_SIMS_MIN, f"num_sims {N} for {row['zone_id']} below the {NUM_SIMS_MIN} floor"
            assert W >= WIN_BOOKS_MIN, f"only {W} winning books for {row['zone_id']}"
            assert 0 < W < N, f"degenerate split for {row['zone_id']}"
            assert mode.get_cost() == 1.0, f"mode {row['zone_id']} cost must be 1.0"
            assert mode._wincap == WINCAP, f"mode {row['zone_id']} max_win must be the global {WINCAP}"
            assert (mode.get_distributions()[0]._criteria == "wincap") == (row["zone_id"] == "line"), (
                f"mode {row['zone_id']}: only the exact-line cell may use the wincap criteria"
            )
            assert mode.get_name() == f"zone_{row['zone_id']}", f"mode {i} name off-convention"

            # The conditional sampler needs mass on both sides of the verdict.
            zone_weight = sum(LAND_WEIGHTS[abs(r)] for r in row["zone_rows"])
            assert 0 < zone_weight < LAND_WEIGHT_TOTAL, f"zone {row['zone_id']} weight degenerate"

            # Deterministic, float-safe split (no get_sim_splits leftover).
            win_quota = (W + 0.5) / N
            lose_quota = (N - W + 0.5) / N
            assert int(N * win_quota) == W, f"win split off for {row['zone_id']}"
            assert int(N * lose_quota) == N - W, f"lose split off for {row['zone_id']}"
            assert int(N * win_quota) + int(N * lose_quota) == N, f"split != N for {row['zone_id']}"
