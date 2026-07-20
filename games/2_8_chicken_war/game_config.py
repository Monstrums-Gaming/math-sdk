"""
Chicken War (2_8_chicken_war) — game configuration.

Mission Uncrossable: Chicken — the "Chicken Game Math" spreadsheet published as
Stake Engine math. Same per-lane independent-wager mechanics as 2_8_chicken_run
(each PLAY is one single-book wager on crossing the NEXT lane), but with the
original game's EXACT math table:

  EDGE 0.03 (target RTP 0.97 at every lane) · NUM OF PUMPS 25
  | difficulty | risk | lanes | first mult | max mult      |
  |------------|------|-------|------------|---------------|
  | easy       |  1   |  24   | 1.01       | 24.25         |
  | medium     |  3   |  22   | 1.10       | 2,231.00      |
  | hard       |  5   |  20   | 1.21       | 51,536.10     |
  | daredevil  | 10   |  15   | 1.62       | 3,170,697.20  |

## The closed form (verified against the spreadsheet)

Per-step pop chance at round r (0-based) is `risk / (PUMPS - r)`, so the cumulative
survival probability is EXACT:

    cum[r] = prod_{i=0..r} (PUMPS - risk - i) / (PUMPS - i)

e.g. easy cum[r] = (24-r)/25; daredevil cum[14] = 1/C(25,10) = 1/3,268,760.
The lane multiplier is 0.97 / cum[r], rounded to the nearest CENT (the RGS payout
unit): daredevil_15 = 0.97 x 3,268,760 = 3,170,697.20 exactly.

## Probability & exact book counts

Win probability per mode is the exact reduced fraction W/N from the closed form;
`num_sims = N` yields exactly `W` winning books (optimiser off), so the published
odds ARE the spreadsheet's. Realised per-mode RTP = cum[r] x cents-multiplier
(~0.97, wobble only from cent rounding; asserted within [0.96, 0.98]).

## Deviations from the usual ACP band (user-approved with Stake)

  1. Payouts are NOT on the 0.1x grid (`lut_grid_exempt = True`) — the spreadsheet
     multipliers are cent-precise (1.01, 1.05, ..., 24.25, ...).
  2. Per-mode RTP ~0.97 (above the 96.70% band used by 2_8_chicken_run).
  3. Cross-mode spread stays well under 1% by construction.
"""

import os
from fractions import Fraction

from src.config.config import Config
from src.config.distributions import Distribution
from src.config.betmode import BetMode

RTP_FLOOR = 0.960
RTP_CEIL = 0.980
_EPS = 1e-9

PUMPS = 25
RISK = {"easy": 1, "medium": 3, "hard": 5, "daredevil": 10}
LANES_PER_DIFFICULTY = {"easy": 24, "medium": 22, "hard": 20, "daredevil": 15}
DIFFICULTIES = ["easy", "medium", "hard", "daredevil"]

# Spot checks transcribed from the spreadsheet (lane = sheet round + 1;
# cumulative prob as printed (6dp), payout multiplier as printed).
# _validate pins the build to the sheet through these.
_SHEET_CHECKS = [
    ("easy", 1, 0.960000, 1.01042),
    ("easy", 6, 0.760000, 1.27632),
    ("easy", 24, 0.040000, 24.25),
    ("medium", 1, 0.880000, 1.10227),
    ("medium", 3, 0.669565, 1.44870),
    ("medium", 10, 0.197826, 4.90330),
    ("medium", 22, 0.000435, 2231.00),
    ("hard", 1, 0.800000, 1.2125),
    ("hard", 5, 0.291813, 3.3241),
    ("hard", 20, 0.000019, 51536.10),
    ("daredevil", 1, 0.600000, 1.6167),
    ("daredevil", 5, 0.056522, 17.1615),
    ("daredevil", 15, 0.000000306, 3170697.20),
]


def _cumulative_prob(difficulty: str, lane: int) -> Fraction:
    """Exact survival probability of reaching `lane` (1-based) = sheet round lane-1."""
    risk = RISK[difficulty]
    prob = Fraction(1)
    for i in range(lane):
        prob *= Fraction(PUMPS - risk - i, PUMPS - i)
    return prob


class GameConfig(Config):
    """Chicken War configuration — 81 per-lane win/lose modes at the spreadsheet odds."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        super().__init__()
        self.game_id = "2_8_chicken_war"
        self.provider_number = 2  # placeholder — confirm ACP-assigned value before prod upload
        self.provider_name = "monstrum"
        self.game_name = "Mission Uncrossable: Chicken"
        self.working_name = "Chicken War"
        self.win_type = "scatter"
        self.lut_grid_exempt = True  # cent-precise spreadsheet payouts (user-approved)
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
        """One row per (difficulty, lane): exact spreadsheet probability + cent payout."""
        rows = []
        for difficulty in DIFFICULTIES:
            for lane in range(1, LANES_PER_DIFFICULTY[difficulty] + 1):
                prob = _cumulative_prob(difficulty, lane)
                # Nearest cent to 0.97/prob, in exact Fraction arithmetic
                # (0.97 x 100 = 97; payout_cents = round(97 / prob)).
                payout_cents = round(Fraction(97) / prob)
                payout = payout_cents / 100
                realised_rtp = float(prob * payout_cents) / 100
                assert RTP_FLOOR - _EPS <= realised_rtp <= RTP_CEIL + _EPS, (
                    f"{difficulty}_{lane} RTP {realised_rtp:.4f} outside band"
                )
                rows.append(
                    {
                        "difficulty": difficulty,
                        "lane": lane,
                        "multiplier": payout,
                        "payout_cents": int(payout_cents),
                        "win_chance": float(prob),
                        "rtp": realised_rtp,
                        "W": prob.numerator,    # winning book count
                        "N": prob.denominator,  # num_sims (denominator)
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
        expected = sum(LANES_PER_DIFFICULTY.values())
        assert len(self.bet_modes) == len(self.tiers) == expected, "mode count off"
        assert self.wincap == max(t["multiplier"] for t in self.tiers), "wincap must equal the top mode"

        rtps = [t["rtp"] for t in self.tiers]
        assert max(rtps) - min(rtps) <= 0.01 + _EPS, f"cross-mode RTP spread {max(rtps) - min(rtps):.4f} > 1%"

        for difficulty in DIFFICULTIES:
            snaps = [t["multiplier"] for t in self.tiers if t["difficulty"] == difficulty]
            assert len(snaps) == LANES_PER_DIFFICULTY[difficulty], f"{difficulty}: lane count off"
            assert all(b > a for a, b in zip(snaps, snaps[1:])), f"{difficulty}: ladder not strictly increasing"

        by_key = {(t["difficulty"], t["lane"]): t for t in self.tiers}
        for difficulty, lane, sheet_prob, sheet_mult in _SHEET_CHECKS:
            t = by_key[(difficulty, lane)]
            # The sheet prints 6dp probabilities (10dp for daredevil's tail).
            tol = 5e-7 if sheet_prob >= 1e-5 else 5e-9
            assert abs(t["win_chance"] - sheet_prob) <= tol, (
                f"{difficulty}_{lane} prob {t['win_chance']:.9f} != sheet {sheet_prob}"
            )
            # Cent rounding: our payout must be the sheet multiplier to the cent.
            assert abs(t["multiplier"] - sheet_mult) <= 0.005 + _EPS, (
                f"{difficulty}_{lane} payout {t['multiplier']} != sheet {sheet_mult}"
            )

        for row in self.tiers:
            W, N, cents = row["W"], row["N"], row["payout_cents"]
            assert isinstance(cents, int) and cents >= 100, f"payout {row['multiplier']} must be >= 100 cents"
            win_quota = (W + 0.5) / N
            lose_quota = (N - W + 0.5) / N
            assert int(N * win_quota) == W, f"win split off for {row['difficulty']}_{row['lane']}"
            assert int(N * lose_quota) == N - W, f"lose split off for {row['difficulty']}_{row['lane']}"
            assert int(N * win_quota) + int(N * lose_quota) == N, "split does not sum to N"
