"""Win evaluation for Chicken Crossing (2_7).

There is no board to evaluate: the active criteria fixes which payout the round
lands on, and the cash-out / pop step are then drawn (seeded) to be consistent.
"""

from src.executables.executables import Executables


class GameCalculations(Executables):
    """Chicken Crossing specific calculations."""

    def get_mode_params(self) -> dict:
        """Return the parameters for the bet mode currently being simulated.

        `self.betmode` is the active mode name (set by the engine in run_sims);
        `mode_params` is built once in game_config for every mode.
        """
        return self.config.mode_params[self.betmode]
