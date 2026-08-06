"""
Porkageddon (2_0) — one battle resolves to a pot win, a Golden Pig badge, or a loss.

Two pigs trade blows; every skill committed adds its cost multiplier to a shared
pot and the last pig standing takes it. The criteria assigned to this sim fixes the
payout, and `evaluate_battle` manufactures a transcript consistent with it.

Per-round event order:
    porkSetup -> porkBattle -> porkResult -> [wincap] -> finalWin
"""

from game_override import GameStateOverride


class GameState(GameStateOverride):
    """Handle a single Porkageddon battle for a given simulation number."""

    def run_spin(self, sim: int, simulation_seed=None) -> None:
        self.reset_seed(sim)
        self.repeat = True
        while self.repeat:
            self.reset_book()
            self.evaluate_battle()
            # Flush spin_win into the basegame bucket so update_final_win's
            # base + free == total assertion holds.
            self.win_manager.update_gametype_wins(self.gametype)
            self.evaluate_battle_finalwin()
            self.check_repeat()
        self.imprint_wins()

    def run_freespin(self) -> None:
        # Porkageddon has no free-spin phase; required only to satisfy the base.
        raise NotImplementedError("Porkageddon has no free-spin round.")
