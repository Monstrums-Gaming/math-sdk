"""
Cash Paradise (3_2) — one purchase resolves to exactly one prize.

Per-round event order:
    mysteryReveal -> [winInfoSpecial] -> [setWin] -> setTotalWin -> finalWin
"""

from game_override import GameStateOverride


class GameState(GameStateOverride):
    """Handle a single mystery-box purchase for a given simulation number."""

    def run_spin(self, sim: int, simulation_seed=None) -> None:
        self.reset_seed(sim)
        self.repeat = True
        while self.repeat:
            self.reset_book()
            self.evaluate_mystery_box()
            self.win_manager.update_gametype_wins(self.gametype)
            self.evaluate_finalwin()
            self.check_repeat()
        self.imprint_wins()

    def run_freespin(self) -> None:
        # Mystery box has no free-spin phase; required only to satisfy the
        # abstract base class.
        raise NotImplementedError("Cash Paradise has no free-spin round.")
