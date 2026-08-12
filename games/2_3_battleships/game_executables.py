"""Orchestrating routines for Battleships (2_3) — conserved-board per-click model."""

from game_calculations import GameCalculations
from game_events import outcome_event


class GameExecutables(GameCalculations):
    """Resolve a single tile-click wager and emit its client event."""

    def evaluate_wager(self) -> None:
        """Resolve the round for the active criteria and emit the outcome event.

        The mode (`<shipsLeft>_<minesLeft>`) fixes the remaining-board state being
        wagered; the criteria assigned to this sim decides win/lose:
          - criteria "0"            -> lose (payout 0, mine hit)
          - criteria "win"/"wincap" -> win  (payout = the state's rarity multiplier)
        The payout is deterministic, so the round satisfies its criteria's
        win_criteria on the first pass (no repeat).
        """
        params = self.get_mode_params()
        is_win = self.criteria != "0"
        payout = params["multiplier"] if is_win else 0.0

        outcome_event(
            self,
            ships_left=params["ships_left"],
            mines_left=params["mines_left"],
            win_chance=params["win_chance"],
            is_win=is_win,
            multiplier_cents=params["multiplier_cents"],
        )

        self.win_manager.update_spinwin(payout)
        if payout > 0:
            self.evaluate_wincap()
