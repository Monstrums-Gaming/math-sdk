"""Win evaluation for Chicken Run (2_8).

There is no board to evaluate: the outcome is forced by the active criteria and
the payout is read straight from the current mode's (difficulty, lane) parameters.
"""

from src.executables.executables import Executables


class GameCalculations(Executables):
    """Chicken Run specific calculations."""

    def get_mode_params(self) -> dict:
        """Return the tier parameters for the bet mode currently being simulated.

        `self.betmode` is the active mode name (set by the engine in run_sims);
        `mode_params` is built once in game_config for every mode.
        """
        return self.config.mode_params[self.betmode]
