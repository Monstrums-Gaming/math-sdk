"""
Crypto Pulse (2_9) — game configuration.

A Stake-style **HIGH/LOW** binary game. The player picks HIGH or LOW and a bet; a
BTC/USD chart animates for a few seconds and finishes above or below the start
line. The round **wins** the offered multiplier if the price finishes on the
player's chosen side, otherwise pays 0. Like the dice (`2_4`), limbo (`2_5`) and
chicken (`2_7`/`2_8`) games this is a **direct-probability** game: no board, no
reels, no free spins, Rust optimiser disabled. The odds come straight from the
distribution quotas.

## Mode: a single base mode (cost 1.0), one ~50/50 win/lose split

HIGH and LOW are **symmetric** (identical odds), so from the book's point of view
the direction is cosmetic — the book encodes only win/lose and the offered
multiplier. The frontend derives which way the chart finishes from the player's
chosen side + `isWin` (`endsHigh = pickedHigh == isWin`). One published `base` mode
therefore covers both buttons; the bet chips ($10/$50/$100/MAX in the UI) are ACP
**bet levels**, not published modes.

## The multiplier (grid + RTP)

The reference mockup shows **1.87x**, which is OFF the ACP 0.1x grid (187 cents is
not a multiple of 10) and cannot be published literally. **1.90x** (190 cents) is
the nearest grid-legal value, so it is both the LUT payout and the honest displayed
multiplier. The win probability is the smallest-denominator rational `a/b` whose
realised RTP `(a/b)*1.90` lands in [96.00%, 96.70%] (`_simplest_fraction_in`, the
limbo/chicken Stern-Brocot descent):

    p = 29/57 (~50.88%)  ->  RTP = 29/57 * 1.90 = 96.67%

`num_sims = 57` yields exactly 29 winning and 28 losing books, so the published odds
equal the book counts (optimiser off). `wincap = 1.90` (the single payout is the win
cap). Risk validators are clean: two-outcome payout std ~0.95 (>= the 0.60
volatility floor) and 1.90x is far under the ~100x all-or-nothing ETL/CVaR ceiling.

## ACP rules satisfied

  1. 0.1x LUT grid — payout 1.90x = 190 cents; `lut_grid_exempt = False` keeps the check on.
  2. Per-mode RTP in [90%, 96.70%] (realised 96.67%).
  3. Cross-mode spread <= 1.00% — trivially satisfied (single mode).
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

# Published payout multiplier(s). The mockup's 1.87x is off the 0.1x grid; 1.90x is
# the nearest grid-legal value (190 cents). One symmetric multiplier covers HIGH and
# LOW. (Add more entries here to offer a payout ladder as extra modes — see readme.)
_MULTIPLIERS = [1.90]


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
    """Crypto Pulse configuration — a single ~50/50 win/lose mode (RTP 96.00–96.70%)."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        super().__init__()
        self.game_id = "2_9_crypto_pulse"
        self.provider_number = 2  # placeholder — confirm ACP-assigned value before prod upload
        self.provider_name = "monstrum"
        self.game_name = "Crypto Pulse"
        self.working_name = "Crypto Pulse Pro"
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

        # Minimal boardless scaffolding (mirrors the limbo / chicken games).
        self.paytable = {(1, "B"): 1.0}
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
        """One row per payout multiplier (here a single 1.90x mode).

        For each multiplier M the win probability is the smallest-denominator rational
        a/b whose realised RTP (a/b)*M lands in [96.00%, 96.70%]; num_sims = b yields
        exactly a winning books.
        """
        rows = []
        for multiplier in _MULTIPLIERS:
            payout_cents = round(multiplier * 100)
            assert payout_cents % 10 == 0, f"payout {multiplier} off the 0.1x grid"
            m_frac = Fraction(payout_cents, 100)
            lo = Fraction(round(RTP_FLOOR * 1000), 1000) / m_frac
            hi = Fraction(round(RTP_CEIL * 1000), 1000) / m_frac
            prob = _simplest_fraction_in(lo, hi)
            a, b = prob.numerator, prob.denominator
            realised_rtp = float(prob * m_frac)
            assert RTP_FLOOR - _EPS <= realised_rtp <= RTP_CEIL + _EPS, (
                f"multiplier {multiplier} RTP {realised_rtp:.4f} outside band"
            )
            rows.append(
                {
                    "multiplier": multiplier,
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
        """One bet mode ('base'); a forced win/lose split. HIGH and LOW share it."""
        dummy_reels = {
            "reel_weights": {
                self.basegame_type: {"BR0": 1},
                self.freegame_type: {"BR0": 1},
            }
        }

        modes = []
        for i, row in enumerate(self.tiers):
            m = row["multiplier"]
            W, N = row["W"], row["N"]

            # Floor-safe quotas: int(N*quota) lands exactly, no leftover.
            win_quota = (W + 0.5) / N
            lose_quota = (N - W + 0.5) / N

            # The offered payout is the win cap.
            win_conditions = {**dummy_reels, "force_wincap": True, "force_freegame": False}
            lose_conditions = {**dummy_reels, "force_wincap": False, "force_freegame": False}

            # Single mode -> "base"; a payout ladder would use distinct dot-free names.
            name = "base" if len(self.tiers) == 1 else f"call_{row['payout_cents']}"
            self.mode_params[name] = {
                "multiplier": m,
                "win_chance": row["win_chance"],
                "num_sims": N,
            }

            distributions = [
                Distribution(
                    criteria="wincap",
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
        assert len(self.bet_modes) == len(self.tiers) >= 1, "empty / mismatched mode set"

        rtps = [t["rtp"] for t in self.tiers]
        assert max(rtps) - min(rtps) <= 0.01 + _EPS, f"cross-mode RTP spread {max(rtps) - min(rtps):.4f} > 1%"

        for row in self.tiers:
            m, W, N, cents = row["multiplier"], row["W"], row["N"], row["payout_cents"]
            assert isinstance(cents, int) and cents > 100, f"payout {m} must be an integer > 100 cents"
            assert round(m * 100) == cents, f"payout {m} disagrees with cents {cents}"
            assert cents % 10 == 0, f"payout {m} off the 0.1x grid ({cents} cents)"
            assert RTP_FLOOR - _EPS <= (W / N) * m <= RTP_CEIL + _EPS, (
                f"mode payout {m} RTP {(W / N) * m:.4f} outside [{RTP_FLOOR}, {RTP_CEIL}]"
            )
            # Deterministic, float-safe split (no get_sim_splits leftover).
            win_quota = (W + 0.5) / N
            lose_quota = (N - W + 0.5) / N
            assert int(N * win_quota) == W, f"win split off for payout {m}"
            assert int(N * lose_quota) == N - W, f"lose split off for payout {m}"
            assert int(N * win_quota) + int(N * lose_quota) == N, f"split != N for payout {m}"
