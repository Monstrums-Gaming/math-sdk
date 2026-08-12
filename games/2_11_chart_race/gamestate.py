"""
Chart Race (2_11) — one certified 3-line race resolves to a win/lose payout.

Per-round event order:
    raceResult -> (wincap on a winning book) -> finalWin
"""

from game_override import GameStateOverride


class GameState(GameStateOverride):
    """Handle a single race round for a given simulation number."""

    def run_spin(self, sim: int, simulation_seed=None) -> None:
        params = self.config.mode_params[self.betmode]
        base = sim if simulation_seed is None else simulation_seed
        # Per-mode seed offset: reset_seed(sim) alone seeds random with sim+1, so sim #7
        # in `highest` and sim #7 in `lowest` would draw the SAME uniforms and their
        # finishing orders would be correlated across markets. The offset stride exceeds
        # every mode's num_sims, so no two modes can collide. reset_seed still sets
        # self.sim = sim, so book_id == sim and the LUT ordering is untouched.
        self.reset_seed(sim, seed_override=params["seed_offset"] + base)
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
        # Chart Race has no free-spin phase; required only to satisfy the base.
        raise NotImplementedError("Chart Race has no free-spin round.")
