"""
Chicken Crossing (2_7) — one round resolves to a cash-out step or a pop.

The chicken crosses lanes ("steps"); the active criteria fixes the payout (a
cash-out multiplier, or 0 for a pop). The cash/pop step is drawn to be consistent.

Per-round event order:
    crossingSetup -> crossingResult -> finalWin
"""

from game_override import GameStateOverride


class GameState(GameStateOverride):
    """Handle a single Chicken Crossing round for a given simulation number."""

    def run_spin(self, sim: int, simulation_seed=None) -> None:
        self.reset_seed(sim)
        self.repeat = True
        while self.repeat:
            self.reset_book()
            self.evaluate_crossing()
            # Flush spin_win into the basegame bucket so update_final_win's
            # base + free == total assertion holds.
            self.win_manager.update_gametype_wins(self.gametype)
            self.evaluate_crossing_finalwin()
            self.check_repeat()
        self.imprint_wins()

    def run_freespin(self) -> None:
        # Chicken Crossing has no free-spin phase; required only to satisfy the base.
        raise NotImplementedError("Chicken Crossing has no free-spin round.")
