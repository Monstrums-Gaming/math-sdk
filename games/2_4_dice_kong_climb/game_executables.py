"""Orchestrating routines for Kong Climb (2_4)."""

import random

from game_calculations import GameCalculations
from game_events import dice_result_event

# Dice covers a roll spread of 00.00–100.00, i.e. 10,001 discrete outcomes in
# integer hundredths (0..10000). Mirrors Stake's native dice range so the stored
# roll is directly comparable to a provably-fair verification (roll = float*10001/100).
_ROLL_MAX_HUNDREDTHS = 10000


def _roll_for_outcome(direction: str, target: int, is_win: bool) -> float:
    """Return a 2-dp roll (00.00–100.00) inside the range consistent with the outcome.

    Win conditions (see readme):  under_NN wins if roll < NN;  over_NN wins if roll > NN.
    Ties (roll == NN) are losses. Work in integer hundredths to avoid float-boundary
    bugs, then present as a 2-dp number. Uses the module RNG, which run_spin has already
    seeded per-sim (reset_seed), so the roll is deterministic/reproducible for a sim.
    """
    t = target * 100  # slider target NN in hundredths
    if direction == "over":
        # win: roll > NN  -> (NN, 100];  lose: roll <= NN -> [0, NN]
        lo, hi = (t + 1, _ROLL_MAX_HUNDREDTHS) if is_win else (0, t)
    else:  # under
        # win: roll < NN  -> [0, NN);  lose: roll >= NN -> [NN, 100]
        lo, hi = (0, t - 1) if is_win else (t, _ROLL_MAX_HUNDREDTHS)
    return random.randint(lo, hi) / 100.0


class GameExecutables(GameCalculations):
    """Resolve a single dice round and emit its client events."""

    def evaluate_dice(self) -> None:
        """Resolve the round for the active criteria and emit the diceResult event.

        The criteria assigned to this sim decides win/lose:
          - criteria "0"        -> lose  (payout 0)
          - criteria "win"/"wincap" -> win (payout = the tier multiplier)
        The payout is deterministic, so the round always satisfies its criteria's
        win_criteria on the first pass (no repeat).

        The displayed dice roll is generated here (seeded, reproducible) and stored
        in the book, always inside the winning range on a win / losing range on a
        loss. At bet time the RGS's provably-fair seed pair selects which book is
        served, so the stored roll a player sees is the certified outcome of that
        selection (odds/book selection stay provably fair; the roll is consistent).
        """
        params = self.get_mode_params()
        is_win = self.criteria != "0"
        payout = params["multiplier"] if is_win else 0.0
        roll = _roll_for_outcome(params["direction"], params["target"], is_win)

        dice_result_event(
            self,
            direction=params["direction"],
            target=params["target"],
            win_chance=params["win_chance"],
            is_win=is_win,
            multiplier=params["multiplier"],
            roll=roll,
        )

        self.win_manager.update_spinwin(payout)
        if payout > 0:
            self.evaluate_wincap()
