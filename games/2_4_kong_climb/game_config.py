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

The payout is the **true dice multiplier** `RTP / winChance`, rounded to whole
"cents" (payout×100). This is the honest way to author a dice game — the win
chance is an integer the player sees and the multiplier follows from it — but the
resulting multiplier almost never lands on the ACP 0.1× LUT grid (e.g. 50% →
1.94×, 3% → 32.33×). A genuine dice multiplier *cannot* satisfy that grid, and
Stake's own reference dice (50% → 1.88×) doesn't either, so this game is flagged
`lut_grid_exempt` and the SDK's grid check is skipped for it (see
`utils/rgs_verification.py::verify_lookup_format`).

### Range (192 modes)

We keep every payout ≥ 1.00× (no sub-stake "wins"), i.e. winChance ≤ 97%:
`under_02…under_97` and `over_03…over_98`. The ladder spans 1.00× (97% chance)
up to 48.50× (2% chance), so `wincap = 48.5×`. The two 2%-chance modes
(`under_02`, `over_98`) carry the `"wincap"` criteria.

### Exact integer book counts

For `winChance = c%`, reduce `c/100 = W/N` in lowest terms (`g = gcd(c, 100)`,
`W = c/g`, `N = 100/g`). The mode's `num_sims = N` (≤ 100) yields exactly `W`
winning books, so the published odds (= book counts, optimiser off) equal the
win chance. Quotas use the floor-safe `+0.5` trick because `get_sim_splits` does
`int(num_sims·quota)` and fills any leftover with weighted-random picks. RTP is
`(c/100)·(payout_cents/100)` — exactly 0.97 where `c` divides 9700, else within
cent-rounding (~±0.05%), as with any real dice game.
"""

import os
from math import gcd

from src.config.config import Config
from src.config.distributions import Distribution
from src.config.betmode import BetMode

RTP = 0.97
# Highest multiplier tier doubles as the win cap.
WINCAP = 48.5


class GameConfig(Config):
    """Kong Climb configuration — 102 dice modes, one forced win/lose outcome each."""

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
        self.wincap = WINCAP
        self.win_type = "scatter"
        self.rtp = RTP
        # Dice payouts (RTP / winChance) never sit on the ACP 0.1× LUT grid, so
        # the SDK's grid check is skipped for this direct-probability game.
        self.lut_grid_exempt = True
        self.construct_paths()

        # No board mechanic: model a single revealed cell (1 reel x 1 row).
        self.num_reels = 1
        self.num_rows = [1] * self.num_reels

        # Build the tier ladder and per-mode parameters.
        self.tiers = self._build_tiers()
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
        """Return the ordered list of dice modes (canonical `over_NN`/`under_NN`).

        One row per integer slider target `NN` in each direction, restricted to
        payouts ≥ 1.00× (winChance ≤ 97%):

            under_NN -> winChance = NN%          (NN = 02..97)
            over_NN  -> winChance = (100 - NN)%  (NN = 03..98)

        Each row carries the true dice multiplier `RTP / winChance` as integer
        cents, plus the exact `(W winners / N sims)` split for that win chance.
        """
        rows = []
        for direction in ("under", "over"):
            for nn in range(2, 99):  # slider target
                win_chance = nn if direction == "under" else 100 - nn
                if not (2 <= win_chance <= 97):
                    continue
                payout_cents = round(RTP * 100 * 100 / win_chance)  # round(9700 / c)
                g = gcd(win_chance, 100)  # c/100 = W/N in lowest terms
                W = win_chance // g
                N = 100 // g
                rows.append(
                    {
                        "direction": direction,
                        "target": nn,
                        "win_chance": win_chance,
                        "multiplier": payout_cents / 100,
                        "payout_cents": payout_cents,
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
            direction = row["direction"]
            nn = row["target"]

            # Floor-safe quotas: int(N*quota) lands exactly, no leftover.
            win_quota = (W + 0.5) / N
            lose_quota = (N - W + 0.5) / N

            # The 2%-chance modes pay the win cap -> "wincap" criteria.
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
                    rtp=RTP,
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
        # under_02..under_97 + over_03..over_98 = 96 + 96 modes.
        assert len(self.bet_modes) == len(self.tiers) == 192, "expected 192 dice modes"

        for row in self.tiers:
            m = row["multiplier"]
            W, N = row["W"], row["N"]
            cents = row["payout_cents"]

            # Payout is a positive integer number of cents, >= 1.00x (no sub-stake win).
            assert isinstance(cents, int) and cents >= 100, f"payout {m} must be an integer >= 100 cents"
            assert round(m * 100) == cents, f"multiplier {m} disagrees with cents {cents}"

            # RTP ~= 0.97 (exact where the win chance divides 9700, else cent-rounded).
            assert abs((W / N) * m - RTP) <= 0.01, f"mode RTP {(W / N) * m} too far from {RTP}"

            # Deterministic, float-safe split (no get_sim_splits leftover).
            win_quota = (W + 0.5) / N
            lose_quota = (N - W + 0.5) / N
            assert int(N * win_quota) == W, f"win split off for m={m}"
            assert int(N * lose_quota) == N - W, f"lose split off for m={m}"
            assert int(N * win_quota) + int(N * lose_quota) == N, f"split does not sum to N for m={m}"
