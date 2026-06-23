"""
Mystery Box — game configuration (2_1_85).

This is NOT a reel/slot game. It is a single-purchase "mystery box": the player
pays a fixed cost (32.94x the base bet) and receives exactly one prize, drawn
from a fixed probability table. There is no board mechanic, no free spins and
no optimisation — the prize odds are authored directly here.

Symbol mapping (prize fiction -> engine name). Payouts are expressed as a
multiple of the base bet (base bet == 1 currency unit), so the multiplier
equals the prize's catalog value in currency:

    Blue Checkmark     -> P1   ($7.00)
    Grok Subscription  -> P2   ($30.00)
    Cybertruck         -> P3   ($130,000.00)  <- max win / wincap
    Dogecoin           -> P4   ($0.10)
    TBC Hat            -> P5   ($40.00)
    SpaceX Hoodie      -> P6   ($129.00)
    Plaid Hat          -> P7   ($68.80)
    Tesla Model 4      -> P8   ($80,600.00)
    Neuralink Hat      -> P9   ($60.00)
    Voucher            -> P10  ($0.01  -> below RGS minimum, pays 0)
    Flamethrower       -> P11  ($540.00)
    Biography          -> P12  ($30.00)

RTP check (sum of prob x payout, divided by cost):
    28.001 / 32.94 == 0.85003  (85%)

Each prize pays its full catalog value as the RGS multiplier, so the wallet
total equals the catalog value with no top-up required. The single exception is
the Voucher: its $0.01 value is below the RGS minimum payout (0.1x), so it pays
0 (a negligible 0.0022% of cost). Every non-zero payout is a whole multiple of
0.1x the base bet, satisfying the RGS lookup-table format (integer payouts in
increments of 10).
"""

import os

from src.config.config import Config
from src.config.distributions import Distribution
from src.config.betmode import BetMode


class GameConfig(Config):
    """Mystery Box configuration — one bet mode, one prize per purchase."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        super().__init__()
        self.game_id = "mystery_box"
        self.provider_number = 2
        self.provider_name = "monstrum"
        self.game_name = "Mystery Box"
        self.working_name = "Mystery Box"
        # Cost of opening one box, expressed in base-bet units.
        self.box_cost = 32.94
        # Highest payout (Cybertruck) doubles as the win cap.
        self.wincap = 130000.0
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
        self.prize_table = {
            "P1":  {"name": "Blue Checkmark",    "payout": 7.0,      "prob": 0.07000,  "criteria": "p_blue_checkmark"},
            "P2":  {"name": "Grok Subscription", "payout": 30.0,     "prob": 0.07000,  "criteria": "p_grok"},
            "P3":  {"name": "Cybertruck",        "payout": 130000.0, "prob": 0.00002,  "criteria": "wincap"},
            "P4":  {"name": "Dogecoin",          "payout": 0.1,      "prob": 0.30000,  "criteria": "p_dogecoin"},
            "P5":  {"name": "TBC Hat",           "payout": 40.0,     "prob": 0.08000,  "criteria": "p_tbc_hat"},
            "P6":  {"name": "SpaceX Hoodie",     "payout": 129.0,    "prob": 0.05500,  "criteria": "p_spacex_hoodie"},
            "P7":  {"name": "Plaid Hat",         "payout": 68.8,     "prob": 0.06000,  "criteria": "p_plaid_hat"},
            "P8":  {"name": "Tesla Model 4",     "payout": 80600.0,  "prob": 0.00003,  "criteria": "p_tesla"},
            "P9":  {"name": "Neuralink Hat",     "payout": 60.0,     "prob": 0.03500,  "criteria": "p_neuralink_hat"},
            "P10": {"name": "Voucher",           "payout": 0.0,      "prob": 0.21895,  "criteria": "0"},
            #VIOLATE RGS Increment 10,   "P10": {"name": "Voucher",           "payout": 0.01,      "prob": 0.21895,  "criteria": "0"},
            "P11": {"name": "Flamethrower",      "payout": 540.0,    "prob": 0.00100,  "criteria": "p_flamethrower"},
            "P12": {"name": "Biography",         "payout": 30.0,     "prob": 0.11000,  "criteria": "p_biography"},
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
