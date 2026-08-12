"""Orchestrating routines for Chicken Crossing (2_7)."""

import random

from game_calculations import GameCalculations
from game_events import crossing_setup_event, crossing_result_event, crossing_final_win_event
from src.calculations.statistics import get_random_outcome


class GameExecutables(GameCalculations):
    """Resolve a single Chicken Crossing round and emit its client events."""

    def evaluate_crossing(self) -> None:
        """Resolve the round for the active criteria and emit the reveal events.

        The criteria assigned to this sim fixes the payout multiplier (one criteria
        per distinct cash-out multiplier, or "0" for a pop). We then draw the reveal
        detail — which step was cashed (win) or which step popped (loss) — seeded via
        reset_seed(sim), so it is reproducible and payout-neutral. The payout is
        deterministic given the criteria, so check_repeat accepts on the first pass.
        """
        params = self.get_mode_params()
        difficulty = params["difficulty"]
        ladder = params["ladder"]

        payout = params["criteria_payout"][self.criteria]  # raw multiplier (0.0 on loss)
        is_win = self.criteria != "0"

        if is_win:
            cents = int(round(payout * 100))
            cash_step = random.choice(params["payout_steps"][str(cents)])  # among steps sharing this payout
            popped_step = None
        else:
            # Cosmetic pop step (payout is always 0): weighted by marginal die-at-step j.
            pop_weights = {int(k): w for k, w in params["pop_weights"].items()}
            cash_step = None
            popped_step = int(get_random_outcome(pop_weights))

        crossing_setup_event(
            self,
            difficulty=difficulty,
            cost_multiplier=int(params["cost"]),
            num_steps=params["num_steps"],
            ladder=ladder,
            max_win=params["max_win"],
        )
        crossing_result_event(
            self,
            difficulty=difficulty,
            is_win=is_win,
            cash_out_step=cash_step,
            popped_at_step=popped_step,
            payout_multiplier=payout,
        )

        self.win_manager.update_spinwin(payout)
        if payout > 0:
            self.evaluate_wincap()

    def evaluate_crossing_finalwin(self) -> None:
        """Finalise the round payout and emit the custom finalWin (amount + multiplier).

        Calls update_final_win for the win-manager bookkeeping / base+free==total
        assertion, then emits the reference-shaped finalWin event.
        """
        self.update_final_win()
        crossing_final_win_event(
            self,
            amount=int(round(self.final_win * 100, 0)),
            multiplier=self.final_win,
        )
