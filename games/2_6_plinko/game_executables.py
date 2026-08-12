"""Orchestrating routines for Plinko (2_6)."""

import random

from game_calculations import GameCalculations
from game_events import game_setup_event, drop_batch_event, plinko_final_win_event


class GameExecutables(GameCalculations):
    """Resolve a single Plinko round and emit its client events."""

    def evaluate_plinko(self) -> None:
        """Resolve the round for the active criteria and emit gameSetup + dropBatch.

        The criteria assigned to this sim fixes the payout multiplier (one criteria
        per distinct payout value). We then draw a bin that pays that multiplier and
        a per-ball id (seeded via reset_seed(sim), so reproducible); the payout is
        deterministic given the criteria, so check_repeat accepts the round on the
        first pass.
        """
        params = self.get_mode_params()
        n = params["rows"]
        cells = params["cells"]
        difficulty = params["difficulty"]
        edge = params["edge"]

        payout = params["criteria_payout"][self.criteria]  # raw multiplier
        cents = int(round(payout * 100))
        bins = params["payout_bins"][str(cents)]           # bins paying this multiplier
        bin_index = random.choice(bins)                    # symmetric pick (seeded)
        ball_index = random.getrandbits(32)
        tier = "win" if payout >= 1.0 else "loss"

        game_setup_event(
            self,
            cost_multiplier=int(params["cost"]),
            difficulty=difficulty,
            drop_count=1,
            max_win=edge,                                  # base product: 1 drop -> maxWin = edge
            payout_cells=cells,
            product_mode="base",
            rows=n,
        )
        drop_batch_event(
            self,
            drops=[
                {
                    "ballIndex": ball_index,
                    "binIndex": bin_index,
                    "difficulty": difficulty,
                    "dropIndex": 0,
                    "payoutMultiplier": payout,
                    "rows": n,
                    "tier": tier,
                }
            ],
        )

        self.win_manager.update_spinwin(payout)
        if payout > 0:
            self.evaluate_wincap()

    def evaluate_plinko_finalwin(self) -> None:
        """Finalise the round payout and emit the custom finalWin (amount+multiplier).

        Replaces the base `evaluate_finalwin` (whose built-in finalWin event carries
        only `amount`) — we call update_final_win for the win-manager bookkeeping /
        base+free==total assertion, then emit the reference-shaped finalWin.
        """
        self.update_final_win()
        plinko_final_win_event(
            self,
            amount=int(round(self.final_win * 100, 0)),
            multiplier=self.final_win,
        )
