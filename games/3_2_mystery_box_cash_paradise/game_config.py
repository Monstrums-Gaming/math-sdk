"""
Cash Paradise — game configuration (3_2).

This is NOT a reel/slot game. It is a single-purchase "mystery box": the player
pays a fixed cost (4.98x the base bet) and receives exactly one cash-voucher
prize, drawn from a fixed probability table. There is no board mechanic, no free
spins and no optimisation — the prize odds are authored directly here.

Prize table (engine name -> fiction / catalog value / probability). Payouts are
expressed as a multiple of the base bet (base bet == 1 currency unit), so the
multiplier equals the voucher's catalog value in currency:

    $0.01 Voucher   -> CP1   ($0.01)   30.200%  (below RGS minimum, pays 0)
    $0.10 Voucher   -> CP2   ($0.10)   28.000%
    $1 Voucher      -> CP3   ($1.00)   25.000%
    $2 Voucher      -> CP4   ($2.00)    5.000%
    $5 Voucher      -> CP5   ($5.00)    5.000%
    $10 Voucher     -> CP6   ($10.00)   5.000%
    $50 Voucher     -> CP7   ($50.00)   1.000%
    $100 Voucher    -> CP8   ($100.00)  0.600%
    $1,000 Voucher  -> CP9   ($1,000.00) 0.200%  <- max win / wincap

RTP note:
    Authored expected value (full catalog values) = 4.23102. With the box cost of
    4.98 that is a nominal 4.23102 / 4.98 == 0.84960 (~84.96%).
    The $0.01 voucher (CP1) is below the RGS minimum payout (0.1x) and must
    resolve to 0 — see below. That removes 0.302 x 0.01 = 0.00302 from the
    expected value, giving an effective EV of 4.22800 and an ACTUAL RTP of
    4.22800 / 4.98 == 0.84900 (~84.90%). (A box cost of 4.97767 would instead
    hit exactly 85.00% nominal; 4.98 is the rounded price in use.)

Every non-zero payout is a whole multiple of 0.1x the base bet, satisfying the
RGS lookup-table format (integer payouts in increments of 10 "cents").
"""

import os

from src.config.config import Config
from src.config.distributions import Distribution
from src.config.betmode import BetMode


class GameConfig(Config):
    """Cash Paradise configuration — one bet mode, one prize per purchase."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        super().__init__()
        self.game_id = "3_2_mystery_box_cash_paradise"
        self.provider_number = 3
        self.provider_name = "monstrum"
        self.game_name = "Cash Paradise"
        self.working_name = "Cash Paradise"
        # Cost of opening one box, expressed in base-bet units.
        self.box_cost = 4.98
        # Highest payout ($1,000 Voucher) doubles as the win cap.
        self.wincap = 1000.0
        self.win_type = "scatter"
        self.rtp = 0.85
        self.construct_paths()

        # No board mechanic: model a single revealed cell (1 reel x 1 row).
        self.num_reels = 1
        self.num_rows = [1] * self.num_reels

        # Full prize table. "payout" is the RGS multiplier (== catalog value in
        # base-bet currency); "criteria" buckets the prize for the simulation.
        # Zero-payout prizes MUST use criteria "0" (engine convention); the
        # single max-win prize uses criteria "wincap".
        #
        # CP1 ($0.01) is below the RGS minimum increment (0.1x) and so cannot be
        # paid as authored; following the mystery_box precedent it pays 0 and is
        # bucketed under criteria "0".
        self.prize_table = {
            "CP1": {"name": "$0.01 Voucher",   "payout": 0.0,    "prob": 0.30200, "criteria": "0"},
            "CP2": {"name": "$0.10 Voucher",   "payout": 0.1,    "prob": 0.28000, "criteria": "p_voucher_010"},
            "CP3": {"name": "$1 Voucher",      "payout": 1.0,    "prob": 0.25000, "criteria": "p_voucher_1"},
            "CP4": {"name": "$2 Voucher",      "payout": 2.0,    "prob": 0.05000, "criteria": "p_voucher_2"},
            "CP5": {"name": "$5 Voucher",      "payout": 5.0,    "prob": 0.05000, "criteria": "p_voucher_5"},
            "CP6": {"name": "$10 Voucher",     "payout": 10.0,   "prob": 0.05000, "criteria": "p_voucher_10"},
            "CP7": {"name": "$50 Voucher",     "payout": 50.0,   "prob": 0.01000, "criteria": "p_voucher_50"},
            "CP8": {"name": "$100 Voucher",    "payout": 100.0,  "prob": 0.00600, "criteria": "p_voucher_100"},
            "CP9": {"name": "$1,000 Voucher",  "payout": 1000.0, "prob": 0.00200, "criteria": "wincap"},
        }
        self._validate_prize_table()

        # Each prize is a single-symbol "pay" of kind 1 so the symbol set and
        # the frontend config list every prize. The board is never evaluated
        # against this paytable; payouts come straight from prize_table.
        self.paytable = {(1, sym): info["payout"] for sym, info in self.prize_table.items()}

        self.include_padding = False
        self.special_symbols = {"wild": [], "scatter": [], "multiplier": []}

        # No free spins in a mystery box.
        self.freespin_triggers = {self.basegame_type: {}, self.freegame_type: {}}
        self.anticipation_triggers = {self.basegame_type: 0, self.freegame_type: 0}

        # Helper lookups consumed by run_spin (built once).
        self.prize_payouts = {sym: info["payout"] for sym, info in self.prize_table.items()}
        self.prize_names = {sym: info["name"] for sym, info in self.prize_table.items()}
        self.criteria_draw_weights = self._build_criteria_draw_weights()

        # Only the rare prizes are recorded for the force/search files. Recording
        # every book would make state.imprint_wins O(n^2) (it de-dups bookIds with
        # a list membership test), so common prizes are left to be discovered from
        # the per-book mysteryReveal event instead.
        self.record_prize_threshold = 0.01
        self.record_prizes = {
            sym for sym, info in self.prize_table.items() if info["prob"] <= self.record_prize_threshold
        }

        # A reel strip is not used for logic, but listing the prize symbols
        # keeps the published frontend config self-describing.
        reels = {"BR0": "BR0.csv"}
        self.reels = {}
        for r, f in reels.items():
            self.reels[r] = self.read_reels_csv(os.path.join(self.reels_path, f))
        self.padding_reels = {
            self.basegame_type: self.reels["BR0"],
            self.freegame_type: self.reels["BR0"],
        }

        self.bet_modes = [
            BetMode(
                name="base",
                cost=self.box_cost,
                rtp=self.rtp,
                max_win=self.wincap,
                auto_close_disabled=False,
                is_feature=False,
                is_buybonus=False,
                distributions=self._build_distributions(),
            ),
        ]

    def _validate_prize_table(self) -> None:
        """Guard the authored odds and payouts before the engine consumes them."""
        total_prob = round(sum(info["prob"] for info in self.prize_table.values()), 8)
        if total_prob != 1.0:
            raise RuntimeError(f"Prize probabilities must sum to 1.0, got {total_prob}.")

        for sym, info in self.prize_table.items():
            payout_cents = round(info["payout"] * 100, 6)
            if payout_cents != int(payout_cents):
                raise RuntimeError(f"Prize {sym} payout {info['payout']} is finer than 0.01x; not RGS-valid.")
            payout_int = int(payout_cents)
            if payout_int != 0 and (payout_int < 10 or payout_int % 10 != 0):
                raise RuntimeError(
                    f"Prize {sym} payout {info['payout']} -> {payout_int} violates RGS increments of 10."
                )
            if info["payout"] > self.wincap:
                raise RuntimeError(f"Prize {sym} payout {info['payout']} exceeds wincap {self.wincap}.")

    def _build_criteria_draw_weights(self) -> dict:
        """Map each criteria to the relative draw weights of the prizes it contains."""
        weights: dict[str, dict[str, float]] = {}
        for sym, info in self.prize_table.items():
            weights.setdefault(info["criteria"], {})[sym] = info["prob"]
        return weights

    def _build_distributions(self) -> list:
        """One distribution per criteria; quotas equal the summed prize odds."""
        dummy_reels = {
            "reel_weights": {
                self.basegame_type: {"BR0": 1},
                self.freegame_type: {"BR0": 1},
            }
        }
        criteria_quota: dict[str, float] = {}
        for info in self.prize_table.values():
            criteria_quota[info["criteria"]] = round(
                criteria_quota.get(info["criteria"], 0.0) + info["prob"], 8
            )

        distributions = []
        for criteria, quota in criteria_quota.items():
            if criteria == "0":
                win_criteria = 0.0
                conditions = {**dummy_reels, "force_wincap": False, "force_freegame": False}
            elif criteria == "wincap":
                win_criteria = self.wincap
                conditions = {**dummy_reels, "force_wincap": True, "force_freegame": False}
            else:
                # A paying, non-cap prize: force the exact payout of its single prize.
                (prize_payout,) = {self.prize_payouts[s] for s in self.criteria_draw_weights[criteria]}
                win_criteria = prize_payout
                conditions = {**dummy_reels, "force_wincap": False, "force_freegame": False}

            distributions.append(
                Distribution(criteria=criteria, quota=quota, win_criteria=win_criteria, conditions=conditions)
            )
        return distributions
