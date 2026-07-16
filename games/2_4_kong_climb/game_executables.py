"""Orchestrating routines for Kong Climb (2_4)."""

from game_calculations import GameCalculations
from game_events import dice_result_event


class GameExecutables(GameCalculations):
    """Resolve a single dice round and emit its client events."""

    def evaluate_dice(self) -> None:
        """Resolve the round for the active criteria and emit the diceResult event.

        The criteria assigned to this sim decides win/lose:
          - criteria "0"        -> lose  (payout 0)
          - criteria "win"/"wincap" -> win (payout = the tier multiplier)
        The payout is deterministic, so the round always satisfies its criteria's
        win_criteria on the first pass (no repeat).
        """
        params = self.get_mode_params()
        is_win = self.criteria != "0"
        payout = params["multiplier"] if is_win else 0.0

        dice_result_event(
            self,
            direction=params["direction"],
            target=params["target"],
            win_chance=params["win_chance"],
            is_win=is_win,
            multiplier=params["multiplier"],
        )

        self.win_manager.update_spinwin(payout)
        if payout > 0:
            self.evaluate_wincap()
