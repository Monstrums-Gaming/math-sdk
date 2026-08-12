"""Orchestrating routines for Limbo Frankenstein (2_5)."""

from game_calculations import GameCalculations
from game_events import limbo_win_info_event


class GameExecutables(GameCalculations):
    """Resolve a single Limbo round and emit its client events."""

    def evaluate_limbo(self) -> None:
        """Resolve the round for the active criteria and emit the winInfo event.

        Limbo: the player targets multiplier `T`; the round wins `W = T*cost` if the
        rolled crash multiplier >= T. Here the criteria assigned to this sim decides
        win/lose:
          - criteria "0"            -> lose (payout 0)
          - criteria "win"/"wincap" -> win  (payout = the mode's W = target*cost)
        The payout is deterministic, so the round always satisfies its criteria's
        win_criteria on the first pass (no repeat).
        """
        params = self.get_mode_params()
        is_win = self.criteria != "0"
        payout = params["multiplier"] if is_win else 0.0  # W = target * cost

        limbo_win_info_event(
            self,
            is_win=is_win,
            offered_multiplier=params["multiplier"],
            win_amount=payout,
            target=params["target"],
            win_chance=params["win_chance"],
        )

        self.win_manager.update_spinwin(payout)
        if payout > 0:
            self.evaluate_wincap()
