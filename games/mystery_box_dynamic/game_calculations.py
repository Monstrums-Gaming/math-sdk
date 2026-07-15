"""Win evaluation for Mystery Box (2_1_85)."""

from src.executables.executables import Executables
from src.calculations.statistics import get_random_outcome


class GameCalculations(Executables):
    """Mystery-box specific calculations.

    There is no board to evaluate: a single prize is drawn from the criteria's
    fixed weight table and its payout is read straight from the prize table.
    """

    def draw_prize(self) -> tuple[str, float]:
        """Draw one prize symbol for the active criteria and return (symbol, payout)."""
        weights = self.config.criteria_draw_weights[self.criteria]
        symbol = get_random_outcome(weights)
        payout = self.config.prize_payouts[symbol]
        return symbol, payout
