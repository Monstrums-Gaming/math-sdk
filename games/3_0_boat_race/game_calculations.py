"""Win evaluation for Boat Race (3_0).

There is no board to evaluate: the outcome is forced by the active criteria and the
payout is read straight from the mode's payout ladder (game_executables).
"""

from src.executables.executables import Executables


class GameCalculations(Executables):
    """Boat Race specific calculations."""

    def get_mode_params(self) -> dict:
        """Return the mode parameters for the bet mode currently being simulated."""
        return self.config.mode_params[self.betmode]
