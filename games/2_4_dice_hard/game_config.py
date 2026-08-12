"""
Dice Hard — game configuration (2_4).

A Stake-style **Dice** game (roll over / roll under on a 0–100 scale). This is a
direct-probability game, NOT a reel/slot: every round has exactly two outcomes —
win (pays a fixed multiplier) or lose (pays 0). There is no board mechanic, no
free spins and no Rust optimiser; the odds come straight from the distribution
quotas (as in `games/mystery_box`).

## Canonical Stake dice format (`over_NN` / `under_NN`)

This mirrors Stake's reference Dice config: one bet mode per integer slider
target `NN`, in each direction.

    under_NN  wins if the roll < NN   ->  winChance = NN%
    over_NN   wins if the roll > NN   ->  winChance = (100 - NN)%

STAKE ACP BUILD with CENT-RESOLUTION (0.01×) payouts. The RGS accepts payouts down
to 0.01× since 2026-08 — the ACP rejection of the earlier 98%-RTP build (2026-08-12)
listed *zero* grid errors across 192 whole-cent modes, confirming the cent grid is
accepted server-side. What that rejection DID enforce (and this ladder is tuned to):

1. **Per-mode RTP band 90.0%–96.70%** — realised RTP is recomputed from the LUT.
2. **Cross-mode spread ≤ 0.50%** (STRICT max−min, not the older ±0.5% ⇒ ≤1.00%
   reading — Kong Climb's approved 0.90% spread would fail this validator today).
3. **Base Mode STD ≥ 0.60×** — per-mode payout standard deviation
   `M·sqrt(w·(1−w))`. This kills the high-win-chance tail: a 97%-chance 1.01×
   mode has std 0.17×. With RTP ≈ 0.965 the floor binds at winChance ≈ 71%, so
   the ladder stops at 70% (`under_70` pays 1.38×, std 0.632).

Why cent resolution: on the coarse 0.1× grid the ceiling forces multiplier steps
that leave whole-point RTP gaps (Kong Climb spans 95.7–96.6%); whole-cent snapping
pins every mode within half a point of the cap, which is what makes the strict
0.50% spread limit satisfiable across 130 modes.

We **floor-snap** each multiplier onto the 0.01× grid to the largest value with
RTP ≤ 96.70% (`_cent_mult_below_ceiling`) and keep the mode only if payable,
in band, and volatile enough:

    payout > 1.00×                  (no no-upside modes)
    RTP    in [96.25%, 96.70%]      (spread ≤ 0.45% < the 0.50% ACP limit)
    std    ≥ 0.62×                  (margin over the 0.60× ACP floor)

Result: **130 modes** (65 win chances × over/under, winChance 2–70%; win chances
52/59/62/65 drop below the RTP floor and are skipped), spanning 1.38×…48.35×
(`wincap = 48.35×`), realised RTP 96.25–96.70%, min std 0.632×.

### Exact integer book counts

For `winChance = c%`, reduce `c/100 = W/N` in lowest terms (`g = gcd(c, 100)`,
`W = c/g`, `N = 100/g`). The mode's `num_sims = N` (≤ 100) yields exactly `W`
winning books, so the published odds (= book counts, optimiser off) equal the
win chance. Quotas use the floor-safe `+0.5` trick because `get_sim_splits` does
`int(num_sims·quota)` and fills any leftover with weighted-random picks. The
snap moves the multiplier, never the win chance, so `W`/`N`/`num_sims`/quotas are
unchanged; realised RTP is `(c/100)·(snapped multiplier)`, floored to ≤ 98.00%.
"""

import os
from math import gcd

from src.config.config import Config
from src.config.distributions import Distribution
from src.config.betmode import BetMode

# Stake ACP constants — all three learned from the real 2026-08-12 rejection of the earlier
# 98%-RTP build (which drew RTP-band + spread + STD errors but ZERO grid errors, proving the
# RGS now accepts whole-cent 0.01x payouts).
RTP_CEIL = 0.967  # ACP hard cap ("Return to Player must be between 90% and 96.70%")
# The ACP cross-mode validator is the STRICT reading: max(RTP) - min(RTP) <= 0.50%
# ("Cross-Mode RTP Consistency ... Limit: <= 0.50%"). Floor at 96.25% keeps the realised
# spread at 0.45%.
RTP_FLOOR = 0.9625
MIN_MULT = 1.01  # payout must beat the 1.00x stake (the STD floor below dominates in practice)
# ACP "Base Mode STD" floor is 0.60x per mode (std = M*sqrt(w*(1-w))); require 0.62x for
# margin. Binds at winChance ~71%, ending the ladder at under_70/over_30 (1.38x, std 0.632).
STD_FLOOR = 0.62
_EPS = 1e-9  # absorb float noise at the band edges (e.g. 0.75*1.2 == 0.8999999…)


def _cent_mult_below_ceiling(win_chance: int, ceil: float) -> float:
    """Largest 0.01x-grid (whole-cent) multiplier whose realised RTP (win_chance% * mult)
    does NOT exceed `ceil`. Floor-snapping (not nearest) guarantees RTP <= ceil for every
    mode. Cent resolution (accepted by the RGS since 2026-08) pins every mode within half
    a point of the cap, which is what satisfies the strict 0.50% cross-mode spread."""
    return int((ceil / (win_chance / 100.0)) * 100 + _EPS) / 100.0  # floor onto the 0.01x grid


class GameConfig(Config):
    """Dice Hard configuration — cent-snapped dice modes (RTP 96.25–96.70%, std ≥ 0.62×, ACP-compliant; see docstring), one forced win/lose each."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        super().__init__()
        self.game_id = "2_4_dice_hard"
        self.provider_number = 2  # placeholder — confirm ACP-assigned value before prod upload
        self.provider_name = "monstrum"
        self.game_name = "Dice Hard"
        self.working_name = "Dice Hard"
        self.win_type = "scatter"
        # Payouts are floor-snapped onto the 0.01× (whole-cent) grid so realised RTP
        # never exceeds the 96.70% ACP cap. Whole-cent payouts sit off the legacy 0.1×
        # slot grid, so the SDK's increments-of-10 guard is skipped — the RGS accepts
        # 0.01× payouts since 2026-08 (the ACP raised no grid errors on this ladder).
        self.lut_grid_exempt = True
        self.construct_paths()

        # No board mechanic: model a single revealed cell (1 reel x 1 row).
        self.num_reels = 1
        self.num_rows = [1] * self.num_reels

        # Build the tier ladder and per-mode parameters. wincap and the advertised
        # RTP are derived from the surviving modes (they follow the RTP-band filter).
        self.tiers = self._build_tiers()
        self.wincap = max(t["multiplier"] for t in self.tiers)
        self.rtp = max(t["rtp"] for t in self.tiers)
        self.mode_params = {}

        # Minimal boardless scaffolding (mirrors mystery_box). A single dummy
        # symbol keeps the symbol map / frontend config self-consistent; the
        # board and paytable are never evaluated for a dice game.
        self.paytable = {(1, "D"): 1.0}
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
        """Return the ordered list of dice modes (`over_NN`/`under_NN`) — ACP-compliant
        cent-resolution ladder (see module docstring).

        One row per integer slider target `NN` in each direction:

            under_NN -> winChance = NN%          (NN = 02..70, minus RTP-floor gaps)
            over_NN  -> winChance = (100 - NN)%  (NN = 30..98, minus RTP-floor gaps)

        Each multiplier is FLOOR-snapped onto the 0.01× (whole-cent) grid to the largest
        value with RTP <= 96.70% (the ACP cap). A mode is kept only if it is payable, in
        band, and volatile enough for the ACP Base-STD floor:

            payout > 1.00×, RTP in [96.25%, 96.70%], std = M·sqrt(w(1−w)) >= 0.62×

        The STD floor ends the ladder at winChance 70% (1.38×, std 0.632); win chances
        52/59/62/65 snap below the RTP floor and are skipped (slider UIs must snap to the
        nearest published target). Each kept row carries the snapped multiplier as integer
        cents, its realised RTP, and the exact `(W winners / N sims)` split.
        """
        rows = []
        for direction in ("under", "over"):
            for nn in range(2, 99):  # slider target
                win_chance = nn if direction == "under" else 100 - nn
                if not (2 <= win_chance <= 97):
                    continue

                # Floor-snap onto the 0.01× (whole-cent) grid so realised RTP never exceeds the cap.
                multiplier = _cent_mult_below_ceiling(win_chance, RTP_CEIL)
                realised_rtp = (win_chance / 100.0) * multiplier
                w = win_chance / 100.0
                std = multiplier * (w * (1.0 - w)) ** 0.5

                # Keep only payable modes inside the band that clear the ACP STD floor.
                if multiplier < MIN_MULT:
                    continue
                if not (RTP_FLOOR - _EPS <= realised_rtp <= RTP_CEIL + _EPS):
                    continue
                if std < STD_FLOOR - _EPS:
                    continue

                payout_cents = round(multiplier * 100)  # on-grid: a multiple of 10
                g = gcd(win_chance, 100)  # c/100 = W/N in lowest terms
                W = win_chance // g
                N = 100 // g
                rows.append(
                    {
                        "direction": direction,
                        "target": nn,
                        "win_chance": win_chance,
                        "multiplier": multiplier,
                        "payout_cents": payout_cents,
                        "rtp": realised_rtp,
                        "std": std,
                        "W": W,
                        "N": N,
                    }
                )
        return rows

    # ---------------------------------------------------------------- betmodes
    def _build_bet_modes(self) -> list:
        """One bet mode per (direction, target); each a forced win/lose split."""
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
            wc = row["win_chance"]
            mode_rtp = row["rtp"]
            direction = row["direction"]
            nn = row["target"]

            # Floor-safe quotas: int(N*quota) lands exactly, no leftover.
            win_quota = (W + 0.5) / N
            lose_quota = (N - W + 0.5) / N

            # The top-multiplier mode(s) pay the win cap -> "wincap" criteria.
            if m >= self.wincap:
                win_criteria_name = "wincap"
                win_conditions = {**dummy_reels, "force_wincap": True, "force_freegame": False}
            else:
                win_criteria_name = "win"
                win_conditions = {**dummy_reels, "force_wincap": False, "force_freegame": False}
            lose_conditions = {**dummy_reels, "force_wincap": False, "force_freegame": False}

            name = f"{direction}_{nn:02d}"
            self.mode_params[name] = {
                "direction": direction,
                "target": nn,
                "multiplier": m,
                "win_chance": wc,
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
        assert self.wincap == max(t["multiplier"] for t in self.tiers), "wincap must equal the top mode"
        assert len(self.bet_modes) == len(self.tiers) >= 2, "empty / mismatched dice mode set"

        for row in self.tiers:
            m = row["multiplier"]
            W, N = row["W"], row["N"]
            cents = row["payout_cents"]
            wc = row["win_chance"]

            # Payout is a positive integer number of cents, strictly above the stake.
            assert isinstance(cents, int) and cents > 100, f"payout {m} must be an integer > 100 cents"
            assert round(m * 100) == cents, f"multiplier {m} disagrees with cents {cents}"

            # Guaranteed at build time: whole-cent (0.01×) payout, realised RTP inside the
            # ACP band, and per-mode STD above the ACP Base-Volatility floor (with margin).
            assert RTP_FLOOR - _EPS <= (W / N) * m <= RTP_CEIL + _EPS, (
                f"mode {row['direction']}_{row['target']:02d} RTP {(W / N) * m:.4f} outside [{RTP_FLOOR}, {RTP_CEIL}]"
            )
            wf = wc / 100.0
            assert m * (wf * (1.0 - wf)) ** 0.5 >= STD_FLOOR - _EPS, (
                f"mode {row['direction']}_{row['target']:02d} std below the {STD_FLOOR} floor"
            )

            # Deterministic, float-safe split (no get_sim_splits leftover).
            win_quota = (W + 0.5) / N
            lose_quota = (N - W + 0.5) / N
            assert int(N * win_quota) == W, f"win split off for m={m}"
            assert int(N * lose_quota) == N - W, f"lose split off for m={m}"
            assert int(N * win_quota) + int(N * lose_quota) == N, f"split does not sum to N for m={m}"

        # ACP Cross-Mode RTP Consistency: STRICT max−min spread <= 0.50%.
        rtps = [t["rtp"] for t in self.tiers]
        assert max(rtps) - min(rtps) <= 0.005 + _EPS, (
            f"cross-mode RTP spread {(max(rtps) - min(rtps)) * 100:.2f}% exceeds the 0.50% ACP limit"
        )
