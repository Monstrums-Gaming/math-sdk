"""
Price Grid (2_11) — one tap-cell chip resolves to a win or a loss.

Per-round event order:
    cellCall -> (wincap on a win) -> finalWin
"""

from game_override import GameStateOverride


class GameState(GameStateOverride):
    """Handle a single tap-cell chip for a given simulation number."""

    def run_spin(self, sim: int, simulation_seed=None) -> None:
        self.reset_seed(sim)
        self.repeat = True
        while self.repeat:
            self.reset_book()
            self.evaluate_call()
            # Flush spin_win into the basegame bucket so update_final_win's
            # base + free == total assertion holds.
            self.win_manager.update_gametype_wins(self.gametype)
            self.evaluate_finalwin()
            self.check_repeat()
        self.imprint_wins()

    def run_freespin(self) -> None:
        # Price Grid has no free-spin phase; required only to satisfy the base.
        raise NotImplementedError("Price Grid has no free-spin round.")
