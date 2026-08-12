"""
Kong Climb — game configuration (2_4).

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

!!! NON-STAKE BUILD: this variant targets a 98% RTP ceiling with CENT-RESOLUTION
(0.01×) payouts. It violates TWO Stake ACP rules: (a) RTP exceeds the 96.70% cap,
and (b) payouts are off the 0.1× LUT grid. Stake's ACP dashboard re-checks both
server-side and rejects on either, so this build **cannot be published to Stake
Engine** — it is for a non-Stake operator/platform or an internal/test build only.
See the RTP_CEIL / RTP_FLOOR / MIN_MULT constants below (and `self.lut_grid_exempt`)
for how to revert to a Stake-legal 96.70%, 0.1×-grid build.

Why cent resolution: on the coarse 0.1× grid the smallest payout above the 1× stake
is 1.1×, so a mode only has upside when `winChance% × 1.1 ≤ ceiling` — capping
roll-under at winChance 89% (`under_89`). Cent (0.01×) resolution lets high win
chances pay a real small profit (winChance 97% → 1.01×), so both directions reach
target 97 (`under_97` / `over_03`).

Two rules shape the ladder:

1. **0.01× (whole-cent) grid** — every non-zero payout is an integer number of
   "cents" (`multiplier × 100`), the SDK's native resolution. `self.lut_grid_exempt
   = True` disables the SDK's 0.1×-grid guard so these off-grid cents are accepted.
2. **RTP band** — every mode's realised RTP lands in [RTP_FLOOR, RTP_CEIL] =
   [97.0%, 98.00%]. Cent resolution snaps every mode just under 98.00%, so the
   realised span is 97.18–98.00% (a self-imposed ≤1.00% spread, not an ACP rule).

We **floor-snap** each multiplier onto the 0.01× grid to the largest value with
RTP ≤ 98.00% (`_cent_mult_below_ceiling`) and keep the mode only if payable and in
band:

    payout > 1.00×                 (no no-upside modes; smallest is 1.01×)
    RTP    in [97.0%, 98.00%]       (realised 97.18–98.00%, 0.82% spread)

Result: **192 modes** (96 win chances × over/under, winChance 2–97%), spanning
1.01×…49.0× (`wincap = 49.0×`), realised RTP 97.18–98.0%.

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

# !!! NON-STAKE BUILD — DELIBERATELY EXCEEDS STAKE'S ACP RTP CAP *AND* ITS 0.1x GRID !!!
# This game is tuned to a 98% RTP ceiling with CENT-RESOLUTION (0.01x) payouts. Stake's ACP
# dashboard (a) recomputes RTP and HARD-REJECTS anything above 96.70% ("Return to Player must
# be between 90% and 96.70%"), and (b) re-runs the 0.1x LUT-grid check and rejects any payout
# that is not a multiple of 0.1x. THIS BUILD VIOLATES BOTH, so it CANNOT BE PUBLISHED TO STAKE
# ENGINE — it is valid only for a non-Stake operator/platform, or an internal/test build.
# To make it Stake-publishable again: RTP_CEIL=0.967, RTP_FLOOR=0.957, MIN_MULT=1.1, snap to
# the 0.1x grid in _cent_mult_below_ceiling, and set self.lut_grid_exempt=False.
RTP_CEIL = 0.98  # 98.0% — hard maximum (inclusive; cent grid hits realised max exactly 98.00%)
# We still keep the whole mode set inside a ≤1.00% RTP spread — no longer an ACP requirement
# (this build isn't ACP-bound) but retained so the game stays internally balanced. Cent
# resolution snaps every mode just under 98.00%, so realised RTP spans 97.18–98.00% (0.82%
# spread); floor at 97.0% keeps the full contiguous ladder (min realised RTP is 97.18%).
RTP_FLOOR = 0.97
MIN_MULT = 1.01  # payout must beat the 1.00x stake; smallest whole-cent win above it
_EPS = 1e-9  # absorb float noise at the band edges (e.g. 0.75*1.2 == 0.8999999…)


def _cent_mult_below_ceiling(win_chance: int, ceil: float) -> float:
    """Largest 0.01x-grid (whole-cent) multiplier whose realised RTP (win_chance% * mult)
    does NOT exceed `ceil`. Floor-snapping (not nearest) guarantees RTP <= ceil for every
    mode. Cent resolution (not the coarse 0.1x ACP grid) lets high win chances still pay a
    real profit above the stake — e.g. winChance 97% snaps to 1.01x instead of dropping."""
    return int((ceil / (win_chance / 100.0)) * 100 + _EPS) / 100.0  # floor onto the 0.01x grid


class GameConfig(Config):
    """Kong Climb configuration — cent-snapped dice modes (RTP 97.18–98.0%; NON-STAKE build off the 0.1× grid, see docstring), one forced win/lose each."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        super().__init__()
        self.game_id = "2_4_kong_climb"
        self.provider_number = 2  # placeholder — confirm ACP-assigned value before prod upload
        self.provider_name = "monstrum"
        self.game_name = "Kong Climb"
        self.working_name = "Kong Climb"
        self.win_type = "scatter"
        # Payouts are floor-snapped onto the 0.01× (whole-cent) grid so realised RTP
        # never exceeds 98.00% (NON-STAKE build). These are OFF the 0.1× ACP grid, so the
        # SDK grid check must be disabled (execute_all_tests would otherwise reject them).
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
        """Return the ordered list of dice modes (`over_NN`/`under_NN`). NON-STAKE:
        cent-resolution payouts off the 0.1× ACP grid (see module docstring).

        One row per integer slider target `NN` in each direction:

            under_NN -> winChance = NN%          (NN = 02..97)
            over_NN  -> winChance = (100 - NN)%  (NN = 03..98)

        Each multiplier is FLOOR-snapped onto the 0.01× (whole-cent) grid to the largest
        value with RTP <= 98.00% (NON-STAKE ceiling; Stake caps at 96.70%). A mode is kept
        only if it stays payable and in band (payout > 1.00×, RTP in [97.0%, 98.00%]).
        Volatility is unrestricted — cent resolution keeps every target from winChance 2%
        up to 97% (under_97 pays 1.01×); only winChance 98%+ drop (1.00× snap = no upside).
        Each kept row carries the snapped multiplier as integer cents, its realised RTP,
        and the exact `(W winners / N sims)` split for that win chance.
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

                # Keep only payable modes whose RTP lands inside Stake's absolute band.
                if multiplier < MIN_MULT:
                    continue
                if not (RTP_FLOOR - _EPS <= realised_rtp <= RTP_CEIL + _EPS):
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

            # Guaranteed at build time: whole-cent (0.01×) payout, and realised RTP inside
            # the [97.0%, 98.00%] band. NON-STAKE — payouts are OFF the 0.1× ACP grid (that
            # server-side check would reject them; lut_grid_exempt=True skips the SDK guard).
            assert RTP_FLOOR - _EPS <= (W / N) * m <= RTP_CEIL + _EPS, (
                f"mode {row['direction']}_{row['target']:02d} RTP {(W / N) * m:.4f} outside [{RTP_FLOOR}, {RTP_CEIL}]"
            )

            # Deterministic, float-safe split (no get_sim_splits leftover).
            win_quota = (W + 0.5) / N
            lose_quota = (N - W + 0.5) / N
            assert int(N * win_quota) == W, f"win split off for m={m}"
            assert int(N * lose_quota) == N - W, f"lose split off for m={m}"
            assert int(N * win_quota) + int(N * lose_quota) == N, f"split does not sum to N for m={m}"
