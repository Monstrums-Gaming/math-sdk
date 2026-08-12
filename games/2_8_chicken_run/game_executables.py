"""Orchestrating routines for Chicken Run (2_8)."""

from game_calculations import GameCalculations
from game_events import outcome_event


class GameExecutables(GameCalculations):
    """Resolve a single lane wager and emit its client events."""

    def evaluate_lane(self) -> None:
        """Resolve the round for the active criteria and emit the outcome event.

        The mode (`<difficulty>_<lane>`) fixes which lane is being wagered; the
        criteria assigned to this sim decides win/lose:
          - criteria "0"            -> lose (payout 0, car hit)
          - criteria "win"/"wincap" -> win  (payout = the lane multiplier)
        The payout is deterministic, so the round satisfies its criteria's
        win_criteria on the first pass (no repeat).
        """
        params = self.get_mode_params()
        is_win = self.criteria != "0"
        payout = params["multiplier"] if is_win else 0.0

        outcome_event(
            self,
            difficulty=params["difficulty"],
            lane=params["lane"],
            win_chance=params["win_chance"],
            is_win=is_win,
            multiplier=params["multiplier"],
        )

        self.win_manager.update_spinwin(payout)
        if payout > 0:
            self.evaluate_wincap()
