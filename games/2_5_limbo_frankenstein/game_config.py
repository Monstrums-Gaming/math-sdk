"""
Limbo Frankenstein — game configuration (2_5).

A Stake-style **Limbo** game. The player picks a target multiplier `T`; a crash
multiplier is rolled and the round **wins `T×` if the roll >= T**, otherwise pays
0. Like `games/mystery_box` / the dice game this is a direct-probability game (two
outcomes per round, no board, no reels, no free spins, Rust optimiser disabled) —
the odds come straight from the distribution quotas.

## Modes: base tier only (cost 1.0), target ladder capped at 100x

Each bet mode is one `(base, target T, cost 1)`. The LUT win payout is `W = T`, the
win probability is `p`, and:

    RTP = EV / cost = (p * W) / 1 = p * T

The ladder is a **1.40x .. 100x window** (see `_BASE_TARGETS`). Stake's risk /
star-rating validators squeeze an all-or-nothing Limbo mode from both ends: targets
>= 150x fail the ETL-40x / CVaR tail caps (RTP is ~100% tail), and targets < 1.40x
fall under the 0.60 "Base Volatility (Std Dev)" floor (the game is rated off its
tamest mode). `wincap = max(W)` = 100 (base_100.00).

The earlier `streak` (cost 2/5) and `high` (cost 100) tiers were **removed**: they
only rescaled the bet, but the risk validators read the raw payout `W` absolutely,
so cost 100 inflated modest targets into 5,000x-50,000x payouts that breached
Max-Payout / Tail-Probability / ETL. **Bet-size scaling is an ACP bet-level concern
(dashboard template), not a published mode.**

## ACP math rules (enforced server-side)

1. **0.1x LUT grid** — every non-zero payout is an integer number of "cents" that
   is a multiple of 10 (a whole multiple of 0.1x). Here `W*100` must be a multiple
   of 10, so we keep **grid-aligned targets only** and drop any mode whose payout
   is off the grid (no floor-snapping). This drops the fine base targets
   1.05 / 1.15 / 1.25 / 1.35 / 1.45 / 2.25 (cost-1 payout cents not a multiple of 10).
2. **RTP band (per-mode):** "Return to Player must be between 90% and 96.70%".
3. **RTP consistency (cross-mode):** "RTP within +/-0.5% of each other", i.e.
   variance (max-min) <= 1.00%. We pin every mode's realised RTP into
   [96.00%, 96.70%] -> a <= 0.70% spread, safely inside the cap.

The SDK grid check (`utils/rgs_verification.py::verify_lookup_format`) stays ON as
a regression guard (`lut_grid_exempt = False`).

## Exact integer book counts

Optimiser off -> published odds equal the per-criteria book counts, so
`num_sims * quota` must be an exact integer. For each target we pick the
**smallest-denominator** rational `p = a/b` whose realised RTP `(a/b)*T` lands in
[96.00%, 96.70%] (`_simplest_fraction_in`). Then `num_sims = b` and there are
exactly `a` winning books. Because numerator-1 fractions win for large targets,
every `num_sims` stays small (e.g. base_100 -> 1/104), so a single batch per mode
keeps the split exact. Quotas use the floor-safe "+0.5" trick (`get_sim_splits`
does `int(num_sims*quota)`).
"""

import os
from fractions import Fraction
from math import floor

from src.config.config import Config
from src.config.distributions import Distribution
from src.config.betmode import BetMode

# Stake ACP RTP window (dashboard validators, verbatim):
#   per-mode:  "Return to Player must be between 90% and 96.70%"
#   cross-mode: "RTP across all modes must be within +/-0.5% of each other" (spread <= 1.00%)
# We hold every realised RTP inside [RTP_FLOOR, RTP_CEIL] -> a <= 0.70% spread.
RTP_CEIL = 0.967  # 96.70% — hard maximum (inclusive)
RTP_FLOOR = 0.960  # 96.00% floor -> cross-mode spread <= 0.70%, well under the 1.00% cap
_EPS = 1e-9

# Reference Limbo modes, GRID-ALIGNED targets only (payout W = target*cost must
# land on the 0.1x grid). Dropped off-grid base targets: 1.05, 1.15, 1.25, 1.35,
# 1.45, 2.25 (their cost-1 payout cents are not multiples of 10).
#
# TARGET WINDOW = 1.40x .. 100x. Stake's risk / star-rating validators squeeze an
# all-or-nothing Limbo mode from BOTH ends:
#   * CEILING 100x — every winning round pays the single target multiplier and
#     nothing else, so ~100% of the mode's RTP sits in the "tail"; the
#     Expected-Tail-Liability (ETL 40x) and CVaR caps fail for any target >= 150x
#     (base_100 passes ETL-40x, base_150 fails it at BOTH 2- and 3-star; base_800
#     also breaches CVaR).
#   * FLOOR 1.40x — the game's "Base Volatility (Std Dev)" is rated off its tamest
#     mode, which must be >= 0.60. A two-outcome mode's payout std is
#     sqrt(0.96*T - 0.9216), so T=1.10/1.20/1.30 give 0.36/0.48/0.57 (< 0.60) and
#     drag the whole game below the floor. T=1.40 is the first target at/above 0.60
#     (std 0.649), so the ladder starts there.
# Result: 27 modes, all inside the 2-star band on every metric. Max win: 100x.
_BASE_TARGETS = [
    1.40, 1.50, 1.60, 1.70, 1.80, 1.90, 2.00,
    2.50, 2.80, 3.10, 3.50, 4.00, 4.50, 5.00, 6.00, 7.00, 8.00,
    10.00, 12.50, 15.00, 20.00, 25.00, 30.00, 40.00, 50.00, 75.00, 100.00,
]
# The former `streak` (cost 2/5) and `high` (cost 100) tiers were REMOVED: they
# only rescaled the bet size, but the risk validators read the raw LUT payout W in
# absolute terms, so cost 100 turned modest targets into 5,000x-50,000x payouts and
# breached Max-Payout / Tail-Probability / ETL-10k. Bet-size scaling belongs in the
# ACP **bet-level template** (dashboard), not baked into separate published modes.


def _simplest_fraction_in(lo: Fraction, hi: Fraction) -> Fraction:
    """Smallest-denominator fraction x with lo <= x <= hi (requires 0 < lo <= hi).

    Stern-Brocot descent: if a whole number lies in [lo, hi] it is simplest;
    otherwise lo and hi share an integer part `n` and the simplest value is
    `n + 1/simplest(1/frac(hi), 1/frac(lo))`.
    """
    if lo > hi:
        lo, hi = hi, lo
    n = floor(lo)
    if n >= lo:  # lo is a whole number -> it is the simplest
        return Fraction(n)
    if n + 1 <= hi:  # a whole number lies inside [lo, hi]
        return Fraction(n + 1)
    return n + 1 / _simplest_fraction_in(1 / (hi - n), 1 / (lo - n))


class GameConfig(Config):
    """Limbo configuration — grid-aligned target modes (RTP 96.00–96.70%), one forced win/lose each."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        super().__init__()
        self.game_id = "2_5_limbo_frankenstein"
        self.provider_number = 2  # placeholder — confirm ACP-assigned value before prod upload
        self.provider_name = "monstrum"
        self.game_name = "Limbo Frankenstein"
        self.working_name = "FrankenCharge Limbo"
        self.win_type = "scatter"
        # Payouts are authored on the ACP 0.1× LUT grid (grid-aligned targets only);
        # the SDK grid check stays ON as a regression guard.
        self.lut_grid_exempt = False
        self.construct_paths()

        # No board mechanic: model a single revealed cell (1 reel x 1 row).
        self.num_reels = 1
        self.num_rows = [1] * self.num_reels

        # Build the tier ladder and per-mode parameters. wincap and the advertised
        # RTP are derived from the surviving modes.
        self.tiers = self._build_tiers()
        self.wincap = max(t["multiplier"] for t in self.tiers)
        self.rtp = max(t["rtp"] for t in self.tiers)
        self.mode_params = {}

        # Minimal boardless scaffolding (mirrors mystery_box / the dice game). A
        # single dummy symbol keeps the symbol map / frontend config self-consistent;
        # the board and paytable are never evaluated for a Limbo game.
        self.paytable = {(1, "L"): 1.0}
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

    # ------------------------------------------------------------------ ladder
    def _build_tiers(self) -> list:
        """Return the ordered list of ACP-compliant Limbo modes (base tier, cost 1).

        For each `(tier, target T, cost C)`: the LUT win payout is `W = T*C` (asserted
        on the 0.1x grid), and the win probability is the smallest-denominator rational
        `a/b` whose realised RTP `(a/b)*T` lands in [96.00%, 96.70%]. `num_sims = b`
        yields exactly `a` winning books.
        """
        # Base tier only (cost 1.0); bet-size scaling is an ACP bet-level concern.
        specs = [("base", t, 1) for t in _BASE_TARGETS]

        rows = []
        for tier, target, cost in specs:
            t_frac = Fraction(round(target * 100), 100)
            payout = target * cost  # W = T * C  (the LUT win multiplier)
            payout_cents = round(payout * 100)
            assert payout_cents % 10 == 0, f"{tier}_{target:.2f} payout {payout} off the 0.1x grid"

            lo = Fraction(round(RTP_FLOOR * 1000), 1000) / t_frac
            hi = Fraction(round(RTP_CEIL * 1000), 1000) / t_frac
            p = _simplest_fraction_in(lo, hi)
            a, b = p.numerator, p.denominator
            realised_rtp = float(p * t_frac)  # = (a/b)*T = RTP (cost cancels)

            assert RTP_FLOOR - _EPS <= realised_rtp <= RTP_CEIL + _EPS, (
                f"{tier}_{target:.2f} RTP {realised_rtp:.4f} outside [{RTP_FLOOR}, {RTP_CEIL}]"
            )

            rows.append(
                {
                    "tier": tier,
                    "target": target,
                    "cost": cost,
                    "multiplier": payout,  # W (LUT win payout)
                    "payout_cents": payout_cents,
                    "win_chance": a / b,  # p (probability)
                    "rtp": realised_rtp,
                    "W": a,  # winning book count
                    "N": b,  # num_sims (denominator)
                }
            )
        return rows

    # ---------------------------------------------------------------- betmodes
    def _build_bet_modes(self) -> list:
        """One bet mode per (tier, target); each a forced win/lose split."""
        dummy_reels = {
            "reel_weights": {
                self.basegame_type: {"BR0": 1},
                self.freegame_type: {"BR0": 1},
            }
        }

        modes = []
        for row in self.tiers:
            payout = row["multiplier"]  # W
            W, N = row["W"], row["N"]  # winners / num_sims
            mode_rtp = row["rtp"]
            tier = row["tier"]
            target = row["target"]
            cost = row["cost"]

            # Floor-safe quotas: int(N*quota) lands exactly, no leftover.
            win_quota = (W + 0.5) / N
            lose_quota = (N - W + 0.5) / N

            # The top-payout mode(s) pay the win cap -> "wincap" criteria.
            if payout >= self.wincap:
                win_criteria_name = "wincap"
                win_conditions = {**dummy_reels, "force_wincap": True, "force_freegame": False}
            else:
                win_criteria_name = "win"
                win_conditions = {**dummy_reels, "force_wincap": False, "force_freegame": False}
            lose_conditions = {**dummy_reels, "force_wincap": False, "force_freegame": False}

            # ACP/RGS mode names must be dot-free: the publisher parses the
            # `<mode>` token out of `books_<mode>.jsonl.zst` / `lookUpTable_<mode>_0.csv`,
            # and a `.` in the name collides with the `.jsonl.zst` extension → the
            # dashboard rejects the upload with "Mode: <name> error ... io error".
            # Encode the target with an underscore instead (base_1.10 -> base_1_10),
            # mirroring the working 2_4_dice_kong_climb convention (under_02 / over_98).
            # Mode name tokens must be DOT-FREE: the ACP publisher parses <mode> out of
            # books_<mode>.jsonl.zst / lookUpTable_<mode>_0.csv, so a "." collides with the
            # .jsonl.zst extension and the dashboard rejects the upload. base_1.10 -> base_1_10.
            name = f"{tier}_{target:.2f}".replace(".", "_").replace(".", "_")
            self.mode_params[name] = {
                "tier": tier,
                "target": target,
                "cost": cost,
                "multiplier": payout,
                "win_chance": row["win_chance"],
                "num_sims": N,
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
                    cost=float(cost),
                    rtp=mode_rtp,
                    max_win=self.wincap,
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
        assert self.wincap == max(t["multiplier"] for t in self.tiers), "wincap must equal the top payout"
        assert len(self.bet_modes) == len(self.tiers) >= 2, "empty / mismatched Limbo mode set"

        rtps = [t["rtp"] for t in self.tiers]
        assert max(rtps) - min(rtps) <= 0.01 + _EPS, (
            f"cross-mode RTP spread {max(rtps) - min(rtps):.4f} exceeds 1.00%"
        )

        for row in self.tiers:
            payout = row["multiplier"]
            W, N = row["W"], row["N"]
            cents = row["payout_cents"]
            tier, target = row["tier"], row["target"]

            # Payout is a positive integer number of cents, strictly above a 1x stake.
            assert isinstance(cents, int) and cents > 100, f"payout {payout} must be an integer > 100 cents"
            assert round(payout * 100) == cents, f"payout {payout} disagrees with cents {cents}"
            # On the 0.1x grid.
            assert cents % 10 == 0, f"payout {payout} off the 0.1x grid ({cents} cents)"
            # Per-mode RTP inside Stake's band (realised = (W/N)*target).
            assert RTP_FLOOR - _EPS <= (W / N) * target <= RTP_CEIL + _EPS, (
                f"mode {tier}_{target:.2f} RTP {(W / N) * target:.4f} outside [{RTP_FLOOR}, {RTP_CEIL}]"
            )
            # Base/default modes must be cost 1.0 (ACP requires the default mode = 1.0x).
            if tier == "base":
                assert row["cost"] == 1, f"base mode {tier}_{target:.2f} must be cost 1.0"

            # Deterministic, float-safe split (no get_sim_splits leftover).
            win_quota = (W + 0.5) / N
            lose_quota = (N - W + 0.5) / N
            assert int(N * win_quota) == W, f"win split off for {tier}_{target:.2f}"
            assert int(N * lose_quota) == N - W, f"lose split off for {tier}_{target:.2f}"
            assert int(N * win_quota) + int(N * lose_quota) == N, f"split != N for {tier}_{target:.2f}"
