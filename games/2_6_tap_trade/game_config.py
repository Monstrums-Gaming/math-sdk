"""
Tap Trade (2_6) — game configuration.

A **tap-cell-to-bet** game (formerly `2_11_crypto_pulse_grid`; renamed 2026-07-22 to
pair with the web-sdk app `apps/2-6-tap-trade`. Before that "Price Grid", renamed
2026-07-20 to take over the `2_10_crypto_pulse_grid` slug/name after that earlier,
sparser-ladder build was retired). A live-looking price chart runs continuously; the future region of the
chart is covered by a grid of (time x price) multiplier cells. The player taps a
cell to place a chip; if the price line reaches that cell the chip pays
`bet x cellMultiplier`, otherwise it loses. WHERE the cell sits is pure client-side
presentation — the line is steered to hit or miss the tapped cell.

From the book's point of view this is exactly the `2_9_crypto_pulse` model: each
chip is an independent **win/lose bet at a fixed multiplier M** (the tapped cell is
outcome-neutral). Like the dice (`2_4`), limbo (`2_5`) and crypto-pulse (`2_9`)
games this is a **direct-probability** game: no reels, no free spins, Rust
optimiser disabled. The odds come straight from the distribution quotas.

## Modes: a 28-multiplier ladder, one published win/lose mode per multiplier

Every distinct cell multiplier is its own dot-free mode `call_<cents>` (the ACP
publisher parses `<mode>` out of `books_<mode>.jsonl.zst`, so a "." would collide
with the extension), each `cost = 1.0`. For each multiplier M the win probability is
the smallest-denominator rational a/b whose realised RTP `(a/b)*M` lands in
[96.00%, 96.70%] (`_simplest_fraction_in`, the limbo/chicken Stern-Brocot descent);
`num_sims = b` yields exactly `a` winning books, so published odds equal book counts.

**Ladder (1.4x .. 100x, 28 rungs — dense below 10x):** 1.4, 1.5, 1.6, 1.8, 2, 2.2,
2.5, 2.8, 3.2, 3.6, 4, 4.5, 5, 6, 7, 8, 9, 10, then the 2_10 sparse tail 12, 15, 20,
25, 30, 40, 50, 65, 80, 100. The extra low rungs give the on-screen grid finer
multiplier resolution where most cells live (near the line's projected path); the
risk envelope is IDENTICAL to 2_10 at both ends. The 100x cap is the Limbo
`base_100` precedent that passed ACP's ETL/CVaR risk validators. The **floor is
1.4x, not 1.2x**: a 1.2x win/lose mode has payout std ~0.48, below ACP's
Base-Volatility floor of 0.60 that rates the whole game off its tamest mode (the
exact reason Limbo's approved ladder starts at 1.40x).

## Per-mode wincap (intentional)

Each mode's `BetMode.max_win` is set to that mode's **own** multiplier M (NOT the
global 100x). The engine applies a per-mode wincap override during sims
(`src/state/run_sims.py` sets `config.wincap = BetMode.max_win`), so a winning book —
whose payout equals M — reaches the active mode's cap and emits a standard `wincap`
event on **every winning book in every mode** (event order `cellCall -> wincap ->
finalWin`). Losing books emit `cellCall -> finalWin` (no wincap). This is deliberate;
the web side treats the `wincap` event as a no-op. `self.wincap = 100.0` is the global
maximum (the top rung) used for the module-level cap assertion.

## ACP rules satisfied

  1. 0.1x LUT grid — every multiplier is a multiple of 0.10 (`lut_grid_exempt = False`).
  2. Per-mode RTP in [90%, 96.70%] — every rung pinned into [96.00%, 96.70%].
  3. Cross-mode spread <= 1.00% — automatic (all rungs inside a 0.70%-wide band).
  4. Base bet mode cost = 1.0.
  5. Risk: every mode is a two-outcome all-or-nothing bet — the shape ACP approved for
     Limbo's 1.40x-100x ladder; this ladder is interior to it at both ends.
"""

import os
from fractions import Fraction
from math import floor

from src.config.config import Config
from src.config.distributions import Distribution
from src.config.betmode import BetMode

RTP_FLOOR = 0.960
RTP_CEIL = 0.967
WINCAP = 100.0  # global maximum (top ladder rung)
_EPS = 1e-9

# The published multiplier ladder. Each value becomes its own dot-free mode
# "call_<cents>" with an independently-derived win probability pinning realised RTP
# into [96.00%, 96.70%]. Floor 1.4x clears the ACP volatility floor; 100x cap is the
# Limbo-approved ceiling. Every value is a multiple of 0.10 (0.1x LUT grid).
# Dense below 10x (18 rungs) — the variant's point — then the 2_10 sparse tail.
_MULTIPLIERS = [
    1.4, 1.5, 1.6, 1.8, 2.0, 2.2, 2.5, 2.8, 3.2, 3.6, 4.0, 4.5, 5.0,
    6.0, 7.0, 8.0, 9.0, 10.0,
    12.0, 15.0, 20.0, 25.0, 30.0, 40.0, 50.0, 65.0, 80.0, 100.0,
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
    """Tap Trade configuration — a 28-rung win/lose multiplier ladder."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        super().__init__()
        self.game_id = "2_6_tap_trade"
        self.provider_number = 2  # placeholder — confirm ACP-assigned value before prod upload
        self.provider_name = "monstrum"
        self.game_name = "Tap Trade"
        self.working_name = "Tap Trade"
        self.win_type = "scatter"
        self.lut_grid_exempt = False
        self.construct_paths()

        # No board mechanic: model a single revealed cell (1 reel x 1 row).
        self.num_reels = 1
        self.num_rows = [1] * self.num_reels

        self.tiers = self._build_tiers()
        self.wincap = WINCAP  # global maximum (top rung); per-mode caps set on each BetMode
        self.rtp = max(t["rtp"] for t in self.tiers)
        self.mode_params = {}

        # Minimal boardless scaffolding (mirrors the limbo / crypto-pulse games).
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
        """One row per ladder multiplier M.

        The win probability is the smallest-denominator rational a/b whose realised
        RTP (a/b)*M lands in [96.00%, 96.70%]; num_sims = b yields exactly a winning
        books (optimiser off -> published odds equal book counts).
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
        """One bet mode per ladder rung; a forced win/lose split, max_win = own M."""
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

            # Floor-safe quotas: int(N*quota) lands exactly, no leftover.
            win_quota = (W + 0.5) / N
            lose_quota = (N - W + 0.5) / N

            # The offered payout is this mode's own win cap.
            win_conditions = {**dummy_reels, "force_wincap": True, "force_freegame": False}
            lose_conditions = {**dummy_reels, "force_wincap": False, "force_freegame": False}

            name = f"call_{row['payout_cents']}"
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
                    max_win=m,  # per-mode cap = this rung's multiplier (drives the wincap event)
                    auto_close_disabled=False,
                    is_feature=False,
                    is_buybonus=False,
                    distributions=distributions,
                )
            )
        return modes

    # ---------------------------------------------------------------- validate
    def _validate(self) -> None:
        assert self.wincap == WINCAP == max(t["multiplier"] for t in self.tiers), (
            "wincap must equal the top ladder rung (100x)"
        )
        assert len(self.bet_modes) == len(self.tiers) == len(_MULTIPLIERS) == 28, (
            "expected exactly 28 ladder modes"
        )
        assert len({t["payout_cents"] for t in self.tiers}) == 28, "duplicate ladder multiplier"

        rtps = [t["rtp"] for t in self.tiers]
        assert max(rtps) - min(rtps) <= 0.01 + _EPS, (
            f"cross-mode RTP spread {max(rtps) - min(rtps):.4f} > 1%"
        )

        for i, row in enumerate(self.tiers):
            m, W, N, cents = row["multiplier"], row["W"], row["N"], row["payout_cents"]
            assert isinstance(cents, int) and cents > 100, f"payout {m} must be an integer > 100 cents"
            assert round(m * 100) == cents, f"payout {m} disagrees with cents {cents}"
            assert cents % 10 == 0, f"payout {m} off the 0.1x grid ({cents} cents)"
            assert N <= 1000, f"num_sims {N} for {m}x exceeds the 1000 cap"
            assert self.bet_modes[i]._wincap == m, f"mode {cents} max_win must equal its own multiplier"
            assert RTP_FLOOR - _EPS <= (W / N) * m <= RTP_CEIL + _EPS, (
                f"mode payout {m} RTP {(W / N) * m:.4f} outside [{RTP_FLOOR}, {RTP_CEIL}]"
            )
            # Deterministic, float-safe split (no get_sim_splits leftover).
            win_quota = (W + 0.5) / N
            lose_quota = (N - W + 0.5) / N
            assert int(N * win_quota) == W, f"win split off for payout {m}"
            assert int(N * lose_quota) == N - W, f"lose split off for payout {m}"
            assert int(N * win_quota) + int(N * lose_quota) == N, f"split != N for payout {m}"
