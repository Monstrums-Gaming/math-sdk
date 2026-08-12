"""
Plinko (2_6) — one ball drop resolves to a bin payout.

A ball falls through N peg rows and lands in one of N+1 bins (Binomial(N, 1/2)).
The active criteria fixes the payout; the bin/path are drawn to be consistent.

Per-round event order:
    gameSetup -> dropBatch -> finalWin
"""

from game_override import GameStateOverride


class GameState(GameStateOverride):
    """Handle a single Plinko round for a given simulation number."""

    def run_spin(self, sim: int, simulation_seed=None) -> None:
        self.reset_seed(sim)
        self.repeat = True
        while self.repeat:
            self.reset_book()
            self.evaluate_plinko()
            # Flush spin_win into the basegame bucket so update_final_win's
            # base + free == total assertion holds.
            self.win_manager.update_gametype_wins(self.gametype)
            self.evaluate_plinko_finalwin()
            self.check_repeat()
        self.imprint_wins()

    def run_freespin(self) -> None:
        # Plinko has no free-spin phase; required only to satisfy the abstract base.
        raise NotImplementedError("Plinko has no free-spin round.")
