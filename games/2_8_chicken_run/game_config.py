"""
Chicken Run (2_8) — game configuration.

A Stake-style **Chicken Road** game built as **per-lane independent wagers**. Each
press of PLAY is a separate single-book bet on crossing the NEXT lane: cross safely
-> paid immediately at that lane's multiplier; hit by a car -> that wager loses and
the run returns to the start. The lane multiplier is NOT a cumulative cash-out — it
is the standalone payout for that one lane's wager, and each wager runs at ~97% RTP.

This maps exactly to the real Stake config: 72 bet modes `<difficulty>_<lane>`
(easy/medium/hard × 1..24). One `/wallet/play` on a mode returns a single win/lose
book. It is the direct-probability win/lose pattern of the dice (`2_4`) and limbo
(`2_5`) games — no reels, no free spins, Rust optimiser disabled.

## Modes: 72 = 3 difficulties × 24 lanes

`easy_1..24`, `medium_1..24`, `hard_1..24`. Mode `<d>_<n>` = "wager on crossing to
lane n at difficulty d": pays `ladder[d][n]` on a win, 0 on a hit. Names are dot-free.

## The ladders (derived, swappable)

The published lane multipliers rise across 24 lanes to the game's stated maxima
(Easy 23.8× · Medium 548× · Hard 918×). They are a smooth geometric ladder from the
lane-1 value to the lane-24 max, floor-snapped onto the ACP 0.1× grid and forced
strictly increasing. **These are derived to spec** — replace the `_LADDERS` literals
with the real game's exact 72 multipliers for 1:1 parity (nothing else changes).

## Probability & exact book counts (limbo pattern)

Each mode's win probability is the **smallest-denominator rational** `a/b` whose
realised RTP `(a/b)·payout` lands in [96.00%, 96.70%] (`_simplest_fraction_in`, a
Stern-Brocot descent). `num_sims = b` yields exactly `a` winning books, so the
published odds equal the book counts (optimiser off). RTP is pinned into the ACP
band by construction; the "≈97%" design intent is capped at the 96.70% ceiling.

## ACP rules satisfied

  1. 0.1× LUT grid — payouts floor-snapped; `lut_grid_exempt = False` keeps the check on.
  2. Per-mode RTP in [96.00%, 96.70%].
  3. Cross-mode spread ≤ 1.00% (realised ~0.69%).
"""

import os
from fractions import Fraction
from math import floor

from src.config.config import Config
from src.config.distributions import Distribution
from src.config.betmode import BetMode

RTP_FLOOR = 0.960
RTP_CEIL = 0.967
_EPS = 1e-9

# Per-difficulty lane multipliers (lane 1..24), floor-snapped to the 0.1x grid and
# strictly increasing to the stated maxima. DERIVED — swap in the real game's exact
# 72 values here for 1:1 parity.
_LADDERS = {
    "easy": [
        1.0, 1.1, 1.3, 1.5, 1.7, 2.0, 2.3, 2.6, 3.0, 3.4, 3.9, 4.5,
        5.2, 6.0, 6.9, 7.9, 9.0, 10.4, 11.9, 13.7, 15.7, 18.0, 20.7, 23.8,
    ],
    "medium": [
        1.1, 1.4, 1.8, 2.4, 3.2, 4.2, 5.5, 7.2, 9.5, 12.4, 16.3, 21.4,
        28.1, 36.8, 48.2, 63.1, 82.7, 108.4, 142.0, 186.0, 243.7, 319.3, 418.3, 548.0,
    ],
    "hard": [
        1.2, 1.6, 2.1, 2.8, 3.8, 5.1, 6.8, 9.1, 12.1, 16.2, 21.6, 28.8,
        38.4, 51.3, 68.5, 91.4, 121.9, 162.7, 217.1, 289.7, 386.5, 515.7, 688.0, 918.0,
    ],
}
DIFFICULTIES = ["easy", "medium", "hard"]
LANES = 24


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
    """Chicken Run configuration — 72 per-lane win/lose modes (RTP 96.00–96.70%)."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        super().__init__()
        self.game_id = "2_8_chicken_run"
        self.provider_number = 2  # placeholder — confirm ACP-assigned value before prod upload
        self.provider_name = "monstrum"
        self.game_name = "Chicken Run"
        self.working_name = "Chicken Run"
        self.win_type = "scatter"
        self.lut_grid_exempt = False
        self.construct_paths()

        # No board mechanic: model a single revealed cell (1 reel x 1 row).
        self.num_reels = 1
        self.num_rows = [1] * self.num_reels

        self.tiers = self._build_tiers()
        self.wincap = max(t["multiplier"] for t in self.tiers)
        self.rtp = max(t["rtp"] for t in self.tiers)
        self.mode_params = {}

        # Minimal boardless scaffolding (mirrors the dice / limbo games).
        self.paytable = {(1, "C"): 1.0}
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
        """One row per (difficulty, lane): payout + smallest-denominator win prob."""
        rows = []
        for difficulty in DIFFICULTIES:
            ladder = _LADDERS[difficulty]
            assert len(ladder) == LANES, f"{difficulty}: expected {LANES} lanes"
            for i, payout in enumerate(ladder):
                lane = i + 1
                payout_cents = round(payout * 100)
                assert payout_cents % 10 == 0, f"{difficulty}_{lane} payout {payout} off the 0.1x grid"
                p_frac = Fraction(payout_cents, 100)
                lo = Fraction(round(RTP_FLOOR * 1000), 1000) / p_frac
                hi = Fraction(round(RTP_CEIL * 1000), 1000) / p_frac
                prob = _simplest_fraction_in(lo, hi)
                a, b = prob.numerator, prob.denominator
                realised_rtp = float(prob * p_frac)
                assert RTP_FLOOR - _EPS <= realised_rtp <= RTP_CEIL + _EPS, (
                    f"{difficulty}_{lane} RTP {realised_rtp:.4f} outside band"
                )
                rows.append(
                    {
                        "difficulty": difficulty,
                        "lane": lane,
                        "multiplier": payout,
                        "payout_cents": payout_cents,
                        "win_chance": a / b,
                        "rtp": realised_rtp,
                        "W": a,   # winning book count
                        "N": b,   # num_sims (denominator)
                    }
                )
        return rows

    # ---------------------------------------------------------------- betmodes
    def _build_bet_modes(self) -> list:
        """One bet mode per (difficulty, lane); each a forced win/lose split."""
        dummy_reels = {
            "reel_weights": {
                self.basegame_type: {"BR0": 1},
                self.freegame_type: {"BR0": 1},
            }
        }

        modes = []
        for row in self.tiers:
            m = row["multiplier"]
            W, N = row["W"], row["N"]
            difficulty = row["difficulty"]
            lane = row["lane"]

            win_quota = (W + 0.5) / N
            lose_quota = (N - W + 0.5) / N

            if m >= self.wincap:
                win_criteria_name = "wincap"
                win_conditions = {**dummy_reels, "force_wincap": True, "force_freegame": False}
            else:
                win_criteria_name = "win"
                win_conditions = {**dummy_reels, "force_wincap": False, "force_freegame": False}
            lose_conditions = {**dummy_reels, "force_wincap": False, "force_freegame": False}

            name = f"{difficulty}_{lane}"
            self.mode_params[name] = {
                "difficulty": difficulty,
                "lane": lane,
                "multiplier": m,
                "win_chance": row["win_chance"],
                "num_sims": N,
            }

            distributions = [
                Distribution(
                    criteria=win_criteria_name,
                    quota=win_quota,
                    win_criteria=m,
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
        assert self.wincap == max(t["multiplier"] for t in self.tiers), "wincap must equal the top mode"
        assert len(self.bet_modes) == len(self.tiers) == len(DIFFICULTIES) * LANES, "mode count off"

        rtps = [t["rtp"] for t in self.tiers]
        assert max(rtps) - min(rtps) <= 0.01 + _EPS, f"cross-mode RTP spread {max(rtps) - min(rtps):.4f} > 1%"

        for difficulty in DIFFICULTIES:
            snaps = [t["multiplier"] for t in self.tiers if t["difficulty"] == difficulty]
            assert all(b > a for a, b in zip(snaps, snaps[1:])), f"{difficulty}: ladder not strictly increasing"

        for row in self.tiers:
            m, W, N, cents = row["multiplier"], row["W"], row["N"], row["payout_cents"]
            assert isinstance(cents, int) and cents >= 100, f"payout {m} must be an integer >= 100 cents"
            assert cents % 10 == 0, f"payout {m} off the 0.1x grid"
            assert RTP_FLOOR - _EPS <= (W / N) * m <= RTP_CEIL + _EPS, (
                f"{row['difficulty']}_{row['lane']} RTP out of band"
            )
            win_quota = (W + 0.5) / N
            lose_quota = (N - W + 0.5) / N
            assert int(N * win_quota) == W, f"win split off for {row['difficulty']}_{row['lane']}"
            assert int(N * lose_quota) == N - W, f"lose split off for {row['difficulty']}_{row['lane']}"
            assert int(N * win_quota) + int(N * lose_quota) == N, "split does not sum to N"
