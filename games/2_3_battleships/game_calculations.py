"""Win evaluation for Battleships (2_3).

There is no board to evaluate: the active criteria fixes which payout the round
lands on, and the cash-out rung / mine-hit position are then drawn (seeded) to be
consistent.
"""

from src.executables.executables import Executables


class GameCalculations(Executables):
    """Battleships specific calculations."""

    def get_mode_params(self) -> dict:
        """Return the parameters for the bet mode currently being simulated.

        `self.betmode` is the active mode name (set by the engine in run_sims);
        `mode_params` is built once in game_config for every mode.
        """
        return self.config.mode_params[self.betmode]
