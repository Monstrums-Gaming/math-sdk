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

The two ACP rules the payouts must satisfy (both enforced server-side, learned
the hard way from upload rejections):

1. **0.1× LUT grid** — every non-zero payout is an integer number of "cents" that
   is a multiple of 10 (a whole multiple of 0.1×).
2. **RTP** — two dashboard validators, both enforced:
     a. per-mode band: *"Return to Player must be between 90% and 96.70%"*.
     b. cross-mode consistency: *"RTP across all modes must be within ±0.5% of each
        other"* — i.e. variance (max−min) ≤ 1.00%.
   There is **no** volatility/hit-rate rule (compliant modes span 14–69% hit).

The *true* dice multiplier `0.97 / winChance` sits at 97% RTP — just over the
96.70% cap — and rarely lands on the grid. So we **floor-snap** each multiplier
onto the 0.1× grid to the largest value with RTP ≤ 96.70%
(`_grid_mult_below_ceiling`) and keep the mode only if payable and inside a tight
band that satisfies BOTH RTP rules at once:

    payout > 1.00×                 (no no-upside modes)
    RTP    in [95.70%, 96.70%]      (>= 90%, <= 96.70%, and a 0.90% spread so the
                                    cross-mode variance stays under 1.00%)

The realised max is 96.60%, so the floor is pinned at 95.70% (`RTP_FLOOR`) to hold
the whole set inside a 0.90% spread. Volatility is unrestricted, but the tight RTP
window is what bounds the count: **72 modes** survive (36 win chances × over/under,
winChance 2–48%), spanning 1.1×…48.3× (`wincap = 48.3×`), realised RTP 95.7–96.6%.

### Exact integer book counts

For `winChance = c%`, reduce `c/100 = W/N` in lowest terms (`g = gcd(c, 100)`,
`W = c/g`, `N = 100/g`). The mode's `num_sims = N` (≤ 100) yields exactly `W`
winning books, so the published odds (= book counts, optimiser off) equal the
win chance. Quotas use the floor-safe `+0.5` trick because `get_sim_splits` does
`int(num_sims·quota)` and fills any leftover with weighted-random picks. The
snap moves the multiplier, never the win chance, so `W`/`N`/`num_sims`/quotas are
unchanged; realised RTP is `(c/100)·(snapped multiplier)`, floored to ≤ 96.70%.
"""

import os
from math import gcd

from src.config.config import Config
from src.config.distributions import Distribution
from src.config.betmode import BetMode

# Stake ACP RTP requirement (from the dashboard validator, verbatim):
#   "Return to Player must be between 90% and 96.70%".
# It is an ABSOLUTE per-mode band — there is NO "within X% of each other" rule
# (confirmed empirically: 96.60% modes passed while siblings sat at 97.50%) and
# NO volatility/hit-rate rule (compliant modes span 14–69% hit). So every mode's
# realised RTP simply has to land in [RTP_FLOOR, RTP_CEIL].
RTP_CEIL = 0.967  # 96.70% — hard maximum (inclusive; grid keeps realised max at 96.60%)
# The ACP also enforces CROSS-MODE RTP consistency: "RTP across all modes must be within
# ±0.5% of each other" i.e. variance (max−min) ≤ 1.00%. Realised max is 96.60%, so floor at
# 95.7% keeps the whole set within a 0.90% spread — safely under the 1.00% cap.
RTP_FLOOR = 0.957
MIN_MULT = 1.1  # payout must beat the stake; also the smallest on-grid win > 1.0x
_EPS = 1e-9  # absorb float noise at the band edges (e.g. 0.75*1.2 == 0.8999999…)


def _grid_mult_below_ceiling(win_chance: int, ceil: float) -> float:
    """Largest 0.1x-grid multiplier whose realised RTP (win_chance% * mult) does NOT
    exceed `ceil`. Floor-snapping (not nearest) guarantees RTP <= ceil for every mode —
    the true dice multiplier 0.97/winChance would land at 97% RTP, above the cap."""
    max_cents = int((ceil / (win_chance / 100.0)) * 100 + _EPS)  # 0.01x upper bound
    return ((max_cents // 10) * 10) / 100.0  # floor onto the 0.1x grid


class GameConfig(Config):
    """Kong Climb configuration — grid-snapped dice modes (RTP 90–96.70%), one forced win/lose each."""

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
        # Payouts are floor-snapped onto the ACP 0.1× LUT grid so realised RTP never
        # exceeds 96.70%; the SDK grid check stays ON as a regression guard.
        self.lut_grid_exempt = False
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
        """Return the ordered list of ACP-compliant dice modes (`over_NN`/`under_NN`).

        One row per integer slider target `NN` in each direction:

            under_NN -> winChance = NN%          (NN = 02..97)
            over_NN  -> winChance = (100 - NN)%  (NN = 03..98)

        The true dice multiplier `0.97 / winChance` sits at 97% RTP, above Stake's
        96.70% cap, so each multiplier is FLOOR-snapped onto the 0.1× grid to the
        largest value with RTP <= 96.70%. A mode is kept only if it stays payable and
        in band (payout > 1.00×, RTP in [90%, 96.70%]). Volatility is unrestricted —
        every integer target survives except the highest win chances, where no
        on-grid payout above 1.0× keeps RTP <= 96.70%. Each kept row carries the
        snapped multiplier as integer cents, its realised RTP, and the exact
        `(W winners / N sims)` split for that win chance.
        """
        rows = []
        for direction in ("under", "over"):
            for nn in range(2, 99):  # slider target
                win_chance = nn if direction == "under" else 100 - nn
                if not (2 <= win_chance <= 97):
                    continue

                # Floor-snap onto the 0.1× grid so realised RTP never exceeds the cap.
                multiplier = _grid_mult_below_ceiling(win_chance, RTP_CEIL)
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

            # ACP compliance, guaranteed at build time (not just at upload):
            #   on the 0.1× grid, and realised RTP inside Stake's 90%–96.70% band.
            assert cents % 10 == 0, f"payout {m} off the 0.1x grid ({cents} cents)"
            assert RTP_FLOOR - _EPS <= (W / N) * m <= RTP_CEIL + _EPS, (
                f"mode {row['direction']}_{row['target']:02d} RTP {(W / N) * m:.4f} outside [{RTP_FLOOR}, {RTP_CEIL}]"
            )

            # Deterministic, float-safe split (no get_sim_splits leftover).
            win_quota = (W + 0.5) / N
            lose_quota = (N - W + 0.5) / N
            assert int(N * win_quota) == W, f"win split off for m={m}"
            assert int(N * lose_quota) == N - W, f"lose split off for m={m}"
            assert int(N * win_quota) + int(N * lose_quota) == N, f"split does not sum to N for m={m}"
