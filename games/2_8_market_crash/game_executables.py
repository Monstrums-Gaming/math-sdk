"""Orchestrating routines for Market Crash (2_8)."""

import random

from game_calculations import GameCalculations
from game_events import crash_round_event

# 1.00x in hundredths — an instant rug, the floor of the crash distribution.
_MIN_CRASH_HUNDREDTHS = 100


def _crash_point_hundredths(
    sell_at_cents: int,
    sell_at: float,
    rtp: float,
    cap_hundredths: int,
    is_win: bool,
) -> int:
    """Seeded rug multiplier in integer hundredths, consistent with the verdict.

    The canonical crash survival function, parameterised by this mode's REALISED RTP
    `R = (a/b)*T`, is

        P(C >= x) = R / x        for x >= 1

    Evaluated at x = T this gives `R/T = (a/b)*T/T = a/b` — exactly the mode's published
    win probability. That identity is the point: the odds the player is quoted ARE this
    law read at their SELL AT, so the crash point and the paytable tell the same story.

    Win/lose is already decided (the distribution quota assigned this sim's criteria
    before `run_spin`), so sample C *conditionally*:

      win  (C >= T):  conditional survival T/x  ->  v ~ U(0,1],  C = T / v
      lose (C <  T):  an atom at C = 1 of size q_atom = (1-R)*T/(T-R) (the crash law's
                      instant-rug mass renormalised over the loss mass), else
                      u ~ U(1/T, 1],  C = 1/u  in [1, T)

    The mixture reproduces the UNCONDITIONAL law at every x, which is what makes the
    survival-curve audit in `build_odds_bundle.py` falsifiable rather than decorative.

    Quantisation is by FLOOR, which is both physically right ("the index ticked past cp
    and rugged before cp+0.01") and bias-free at grid points, since
    `floor(100C) >= x_h  <=>  100C >= x_h`. Boundary contract: `cp == target` counts as a
    WIN (the market reached the sell-at), so a loss must be `<= target - 1`. The maths is
    exact but floats are not — `1/u` with u a hair above `1/T` can round up onto the
    target — so clamp unconditionally and then assert. The clamp is a free correctness
    proof, not a distribution distortion: over a million ordinary draws per mode none of
    them bind.

    Uses the module RNG, which `run_spin` has already seeded per-sim AND per-mode
    (reset_seed with a seed_override), so the value is deterministic for a (mode, sim) and
    is not rank-correlated with the same sim in a neighbouring mode.
    """
    target_h = sell_at_cents
    if is_win:
        v = 1.0 - random.random()  # (0, 1]
        cp = target_h if v >= 1.0 else int(target_h / v)  # floor(100 * T/v)
        cp = max(target_h, min(cp, cap_hundredths))
    else:
        q_atom = (1.0 - rtp) * sell_at / (sell_at - rtp)
        if random.random() < q_atom:
            cp = _MIN_CRASH_HUNDREDTHS  # instant rug at 1.00x
        else:
            inv = 1.0 / sell_at
            u = inv + random.random() * (1.0 - inv)  # (1/T, 1)
            cp = int(100.0 / u)  # floor(100/u) in [100, target_h)
            cp = max(_MIN_CRASH_HUNDREDTHS, min(cp, target_h - 1))

    assert (cp >= target_h) == is_win, "crashPoint would flip the verdict"
    assert _MIN_CRASH_HUNDREDTHS <= cp <= cap_hundredths, "crashPoint outside its mode's range"
    return cp


class GameExecutables(GameCalculations):
    """Resolve a single index run and emit its client events."""

    def evaluate_crash(self) -> None:
        """Resolve the round for the active criteria and emit the crashRound event.

        The criteria assigned to this sim decides win/lose:
          - criteria "0"             -> lose (payout 0, the index rugged short of SELL AT)
          - criteria "win"/"wincap"  -> win  (payout = the SELL AT target)
        The payout is deterministic, so the round always satisfies its criteria's
        win_criteria on the first pass (no repeat) — which also means the crash point is
        drawn exactly once per book.

        The rug multiplier is generated here (seeded, reproducible) and stored in the
        book, always on the correct side of the target. At bet time the RGS's
        provably-fair seed pair selects WHICH book is served, so the crash point a player
        sees is the certified outcome of that selection.
        """
        params = self.get_mode_params()
        is_win = self.criteria != "0"
        payout = params["multiplier"] if is_win else 0.0
        crash_point = _crash_point_hundredths(
            sell_at_cents=params["sell_at_cents"],
            sell_at=params["sell_at"],
            rtp=params["rtp"],
            cap_hundredths=params["cap_hundredths"],
            is_win=is_win,
        )

        crash_round_event(
            self,
            is_win=is_win,
            sell_at_cents=params["sell_at_cents"],
            crash_point=crash_point,
            win_chance=params["win_chance"],
        )

        self.win_manager.update_spinwin(payout)
        if payout > 0:
            # Global cap is 100x, so this emits a `wincap` event only in crash_10000.
            self.evaluate_wincap()
