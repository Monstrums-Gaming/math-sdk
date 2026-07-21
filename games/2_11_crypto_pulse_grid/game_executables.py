"""Orchestrating routines for Crypto Pulse Grid (2_11)."""

from game_calculations import GameCalculations
from game_events import cell_call_event


class GameExecutables(GameCalculations):
    """Resolve a single tap-cell chip and emit its client events."""

    def evaluate_call(self) -> None:
        """Resolve the round for the active criteria and emit the outcome event.

        The tapped cell is outcome-neutral (its position is client-side), so the round
        is direction-neutral: the criteria assigned to this sim decides win/lose, and
        the frontend steers the line to hit or miss the tapped cell from the player's
        tap + isWin.
          - criteria "0"       -> lose (payout 0, line missed the cell)
          - criteria "wincap"  -> win  (payout = the offered multiplier)
        The payout is deterministic, so the round satisfies its criteria's win_criteria
        on the first pass (no repeat). On a win, update_spinwin reaches this mode's own
        cap (max_win = M), so evaluate_wincap emits a `wincap` event before finalWin.
        """
        params = self.get_mode_params()
        is_win = self.criteria != "0"
        payout = params["multiplier"] if is_win else 0.0

        cell_call_event(
            self,
            is_win=is_win,
            multiplier=params["multiplier"],
            win_chance=params["win_chance"],
        )

        self.win_manager.update_spinwin(payout)
        if payout > 0:
            self.evaluate_wincap()
