"""Win evaluation for Tap Trade (2_6).

There is no board to evaluate: the outcome is forced by the active criteria and the
payout is read straight from the current mode's parameters (game_executables).
"""

from src.executables.executables import Executables


class GameCalculations(Executables):
    """Tap Trade specific calculations."""

    def get_mode_params(self) -> dict:
        """Return the mode parameters for the bet mode currently being simulated.

        `self.betmode` is the active mode name (set by the engine in run_sims);
        `mode_params` is built once in game_config for every mode.
        """
        return self.config.mode_params[self.betmode]
