"""Win evaluation for Plinko (2_6).

There is no board to evaluate: the active criteria fixes which payout the round
lands on, and the ball's bin/path are then drawn (seeded) to be consistent with it.
"""

from src.executables.executables import Executables


class GameCalculations(Executables):
    """Plinko specific calculations."""

    def get_mode_params(self) -> dict:
        """Return the parameters for the bet mode currently being simulated.

        `self.betmode` is the active mode name (set by the engine in run_sims);
        `mode_params` is built once in game_config for every mode.
        """
        return self.config.mode_params[self.betmode]
