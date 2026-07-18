"""Orchestrating routines for Crypto Pulse (2_9)."""

from game_calculations import GameCalculations
from game_events import price_call_event


class GameExecutables(GameCalculations):
    """Resolve a single HIGH/LOW call and emit its client events."""

    def evaluate_call(self) -> None:
        """Resolve the round for the active criteria and emit the outcome event.

        HIGH/LOW are symmetric, so the round is direction-neutral: the criteria
        assigned to this sim decides win/lose, and the frontend derives the chart
        direction from the player's chosen side + isWin.
          - criteria "0"       -> lose (payout 0, price finished the wrong side)
          - criteria "wincap"  -> win  (payout = the offered multiplier)
        The payout is deterministic, so the round satisfies its criteria's
        win_criteria on the first pass (no repeat).
        """
        params = self.get_mode_params()
        is_win = self.criteria != "0"
        payout = params["multiplier"] if is_win else 0.0

        price_call_event(
            self,
            is_win=is_win,
            multiplier=params["multiplier"],
            win_chance=params["win_chance"],
        )

        self.win_manager.update_spinwin(payout)
        if payout > 0:
            self.evaluate_wincap()
