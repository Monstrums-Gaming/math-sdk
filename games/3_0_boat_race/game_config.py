"""
Boat Race (3_0) — game configuration.

A pari-mutuel-styled **boat race** bet: the player picks one of 4 visually distinct but
statistically identical boats, and is paid by that boat's finishing place in a certified,
pre-generated race. Books are **pick-neutral** — the transcript addresses abstract racers
r0..r3 where **r0 is always the player's pick** (the porkageddon slot-index precedent
generalised): the client maps the chosen boat onto r0 at render time, so all four boats
have identical odds *by construction* and only ONE book pool is published.

Like the dice/limbo/crypto-pulse/market-crash family this is a **direct-probability**
game: no reels, no free spins, Rust optimiser disabled, LUT weights uniform (1 per book),
odds authored entirely by the distribution quotas below.

## The Win/Place ladder (single mode `race`, cost 1.0)

| place | payout | cents | probability |
|-------|--------|-------|-------------|
| 1st   | 3.00x  |  300  | 1/4 |
| 2nd   | 0.60x  |   60  | 1/4 |
| 3rd   | 0.20x  |   20  | 1/4 |
| 4th   | 0      |    0  | 1/4 |

A fair 4-boat race gives each place probability exactly 1/4 (and the rendered race must
LOOK fair, so the LUT must BE fair) — which quantises achievable RTP to steps of
0.1/4 = 0.025x. RTP = (3.0 + 0.6 + 0.2)/4 = **0.95 exactly**, the maximum honest value
under the 96.70% ACP ceiling. Payout std = sqrt(E[X^2] - E[X]^2) = sqrt(2.35 - 0.9025)
= **1.2031**, well clear of the 0.60 Base-Volatility floor. Hit rate 75%.

Sub-1x payouts (0.60x, 0.20x) are the plinko precedent (its low-difficulty edge cells pay
0.5x); both sit on the 0.1x LUT grid (>= 10 cents, % 10 == 0).

## The certified transcript

Every book carries a `raceRun.ranks` timeline — one row per gate segment
(LAPS x GATES = 30), porkageddon's `fieldOrder` + fixed-order int-array idiom — whose
rows evolve ONLY by adjacent-rank swaps (plausible overtakes) and converge on the book's
`finishOrder`. Generation is verdict-first (the criteria fixes the payout, the payout
fixes r0's place, the transcript is manufactured to honestly produce it — never the other
way around), fully seeded per sim, and `verify_books.py` walks every published book
asserting the timeline/finishOrder/payout agreement mechanically.

## Global wincap

`wincap = 3.0` — the game's true maximum win, carried by the 1st-place outcome. Those
books use the `wincap` criteria with `force_wincap: True`, so the engine emits a `wincap`
event on every 3.00x book (matching how the plinko-family top payout behaves); the
frontend needs a no-op-or-better `wincap` handler.

## ACP rules satisfied

  1. 0.1x LUT grid — 300/60/20/0 are all multiples of 10 cents.
  2. Mode RTP 0.95 in [90%, 96.70%].
  3. Cross-mode spread — trivially 0 (single mode).
  4. Base bet mode cost = 1.0.
  5. Volatility — payout std 1.2031 >= 0.60.
  6. num_sims x quota is an exact integer for every criteria (N = 4000, 1000 per place).
"""

import os
from math import sqrt

from src.config.config import Config
from src.config.distributions import Distribution
from src.config.betmode import BetMode

WINCAP = 3.0  # the 1st-place payout IS the game's maximum win
_EPS = 1e-9

NUM_BOATS = 4
LAPS = 3
GATES = 10
SEGMENTS = LAPS * GATES

# (place, payout multiplier, criteria name) — plinko naming: top payout is `wincap`,
# intermediate paid outcomes `p_<cents>`, the unpaid bucket `0`.
LADDER = [
    (1, 3.0, "wincap"),
    (2, 0.6, "p_60"),
    (3, 0.2, "p_20"),
    (4, 0.0, "0"),
]

# 1000 books per place: enough distinct certified transcripts that the served race never
# visibly repeats (the market_crash NUM_SIMS_MIN >= 5000 rationale, scaled to a game
# where every book is a full 30-row timeline rather than one number).
BOOKS_PER_PLACE = 1000
NUM_SIMS = BOOKS_PER_PLACE * len(LADDER)

WIN_CHANCE = 0.75  # P(any payout) = P(place <= 3)


class GameConfig(Config):
    """Boat Race configuration — one pick-neutral Win/Place mode."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        super().__init__()
        self.game_id = "3_0_boat_race"
        self.provider_number = 2  # placeholder — confirm ACP-assigned value before prod upload
        self.provider_name = "monstrum"
        self.game_name = "Boat Race"
        self.working_name = "Boat Race"
        self.win_type = "scatter"
        self.lut_grid_exempt = False
        self.construct_paths()

        # No board mechanic: model a single resolved round (1 reel x 1 row).
        self.num_reels = 1
        self.num_rows = [1] * self.num_reels

        self.wincap = WINCAP
        self.rtp = sum(payout for _, payout, _ in LADDER) / len(LADDER)
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

    # ---------------------------------------------------------------- betmodes
    def _build_bet_modes(self) -> list:
        """One mode `race`, four equal-quota place outcomes."""
        dummy_reels = {
            "reel_weights": {
                self.basegame_type: {"BR0": 1},
                self.freegame_type: {"BR0": 1},
            }
        }

        payout_ladder_cents = [round(payout * 100) for _, payout, _ in LADDER]
        self.mode_params["race"] = {
            "num_sims": NUM_SIMS,
            "num_boats": NUM_BOATS,
            "laps": LAPS,
            "gates": GATES,
            "segments": SEGMENTS,
            "payout_ladder_cents": payout_ladder_cents,
            "win_chance": WIN_CHANCE,
            "rtp": self.rtp,
            # criteria -> finishing place of r0 (the player's boat)
            "criteria_place": {criteria: place for place, _, criteria in LADDER},
        }

        distributions = []
        for place, payout, criteria in LADDER:
            # Floor-safe +0.5 quota (get_sim_splits does int(num_sims * quota)).
            quota = (BOOKS_PER_PLACE + 0.5) / NUM_SIMS
            distributions.append(
                Distribution(
                    criteria=criteria,
                    quota=quota,
                    win_criteria=payout,
                    conditions={
                        **dummy_reels,
                        "force_wincap": criteria == "wincap",
                        "force_freegame": False,
                    },
                )
            )

        return [
            BetMode(
                name="race",
                cost=1.0,
                rtp=self.rtp,
                max_win=self.wincap,
                auto_close_disabled=False,
                is_feature=False,
                is_buybonus=False,
                distributions=distributions,
            )
        ]

    # ---------------------------------------------------------------- validate
    def _validate(self) -> None:
        """Guard the configuration before the engine consumes it."""
        payouts = [payout for _, payout, _ in LADDER]
        cents = [round(p * 100) for p in payouts]

        assert self.wincap == WINCAP == max(payouts), "wincap must equal the top payout"
        assert len(self.bet_modes) == 1 and self.bet_modes[0].get_name() == "race"
        assert [place for place, _, _ in LADDER] == [1, 2, 3, 4], "ladder must cover places 1..4"

        # ACP grid: non-zero payouts >= 10 cents and multiples of 10.
        for c in cents:
            if c > 0:
                assert c >= 10 and c % 10 == 0, f"payout {c} cents off the 0.1x LUT grid"

        # RTP: exactly 0.95, inside [0.90, 0.967].
        rtp = sum(payouts) / len(payouts)
        assert abs(rtp - 0.95) < _EPS, f"RTP {rtp} != 0.95"
        assert 0.90 - _EPS <= rtp <= 0.967 + _EPS, f"RTP {rtp} outside the ACP window"

        # Volatility: payout std over the uniform place distribution.
        e2 = sum(p * p for p in payouts) / len(payouts)
        std = sqrt(e2 - rtp * rtp)
        assert std >= 0.60, f"payout std {std:.4f} below the ACP Base-Volatility floor"

        # Exact splits: int(N * quota) must land on the published counts and sum to N.
        quota = (BOOKS_PER_PLACE + 0.5) / NUM_SIMS
        assert int(NUM_SIMS * quota) == BOOKS_PER_PLACE, "quota split off"
        assert int(NUM_SIMS * quota) * len(LADDER) == NUM_SIMS, "splits do not sum to N"

        # Only the top payout may use the wincap criteria / force_wincap.
        for dist, (place, payout, criteria) in zip(
            self.bet_modes[0].get_distributions(), LADDER
        ):
            assert dist._criteria == criteria
            assert dist._conditions["force_wincap"] == (criteria == "wincap")

        assert WIN_CHANCE == 3 / 4, "winChance must be P(place <= 3)"
        assert SEGMENTS == 30, "frontend contract: 30 rank-timeline rows"
