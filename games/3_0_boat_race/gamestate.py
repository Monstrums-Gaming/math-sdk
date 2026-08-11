"""
Boat Race (3_0) — one certified 4-boat race resolves to a Win/Place payout.

Per-round event order:
    raceSetup -> raceRun -> raceResult -> (wincap on a 1st-place book) -> finalWin
"""

from game_override import GameStateOverride


class GameState(GameStateOverride):
    """Handle a single race for a given simulation number."""

    def run_spin(self, sim: int, simulation_seed=None) -> None:
        # Single mode, so the plain per-sim seed is collision-free (no cross-mode
        # offset needed — contrast market_crash's 30-mode seed stride).
        self.reset_seed(sim if simulation_seed is None else simulation_seed)
        self.repeat = True
        while self.repeat:
            self.reset_book()
            self.evaluate_race()
            # Flush spin_win into the basegame bucket so update_final_win's
            # base + free == total assertion holds.
            self.win_manager.update_gametype_wins(self.gametype)
            self.evaluate_finalwin()
            self.check_repeat()
        self.imprint_wins()

    def run_freespin(self) -> None:
        # Boat Race has no free-spin phase; required only to satisfy the base.
        raise NotImplementedError("Boat Race has no free-spin round.")
