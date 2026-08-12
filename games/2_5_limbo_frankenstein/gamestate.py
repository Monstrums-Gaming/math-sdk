"""
Limbo Frankenstein (2_5) — one crash roll resolves to a win or a loss.

The player targets a multiplier T; the round wins T*cost if the rolled crash
multiplier >= T, else pays 0.

Per-round event order:
    winInfo -> finalWin
"""

from game_override import GameStateOverride


class GameState(GameStateOverride):
    """Handle a single Limbo round for a given simulation number."""

    def run_spin(self, sim: int, simulation_seed=None) -> None:
        self.reset_seed(sim)
        self.repeat = True
        while self.repeat:
            self.reset_book()
            self.evaluate_limbo()
            # Flush spin_win into the basegame bucket so update_final_win's
            # base + free == total assertion holds.
            self.win_manager.update_gametype_wins(self.gametype)
            self.evaluate_finalwin()
            self.check_repeat()
        self.imprint_wins()

    def run_freespin(self) -> None:
        # Limbo has no free-spin phase; required only to satisfy the abstract base.
        raise NotImplementedError("Limbo Frankenstein has no free-spin round.")
