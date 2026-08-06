"""Win evaluation for Porkageddon (2_0).

There is no board to evaluate: the outcome is forced by the active criteria and the
payout is read straight from the current stance's parameters.
"""

from src.executables.executables import Executables


class GameCalculations(Executables):
    """Porkageddon specific calculations."""

    def get_mode_params(self) -> dict:
        """Return the stance parameters for the bet mode currently being simulated.

        `self.betmode` is the active mode name (set by the engine in run_sims);
        `mode_params` is built once in game_config for every stance.
        """
        return self.config.mode_params[self.betmode]
