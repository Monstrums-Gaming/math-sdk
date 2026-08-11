"""Orchestrating routines for Trading Roulette (2_9)."""

import random

from game_calculations import GameCalculations
from game_config import LAND_WEIGHTS, ROWS
from game_events import zone_round_event


def _land_row(zone_rows: tuple, is_win: bool) -> int:
    """Seeded landing row, consistent with the verdict.

    The published landing weights (game_config.LAND_WEIGHTS, integer, proportional to
    1/multiplier) define the board's landing law. Win/lose is already decided (the
    distribution quota assigned this sim's criteria before `run_spin`), so sample the row
    *conditionally*:

      win  : from the weights restricted to the mode's zone rows
      lose : from the weights restricted to the complement

    Both conditional laws are published in the odds bundle and `build_odds_bundle.py`
    audits every mode's empirical conditional frequencies against them within 4 sigma —
    a canned or drifted sampler fails the build. Unlike 2_8's crash law the mixture is NOT
    mode-independent (the board's quoted odds cannot form one coherent wheel — see
    game_config's "Per-mode pinned odds" section); the conditional laws themselves are the
    published, auditable object.

    Uses the module RNG, which `run_spin` has already seeded per-sim AND per-mode
    (reset_seed with a seed_override), so the value is deterministic for a (mode, sim) and
    is not rank-correlated with the same sim in a neighbouring mode.
    """
    zone = set(zone_rows)
    pool = [r for r in ROWS if (r in zone) == is_win]
    weights = [LAND_WEIGHTS[abs(r)] for r in pool]
    total = sum(weights)
    assert total > 0, "conditional landing pool is empty"

    pick = random.random() * total
    acc = 0.0
    row = pool[-1]  # float-edge fallback: pick == total lands on the last row
    for r, w in zip(pool, weights):
        acc += w
        if pick < acc:
            row = r
            break

    assert (row in zone) == is_win, "landRow would flip the verdict"
    return row


class GameExecutables(GameCalculations):
    """Resolve a single board round and emit its client events."""

    def evaluate_zone(self) -> None:
        """Resolve the round for the active criteria and emit the zoneRound event.

        The criteria assigned to this sim decides win/lose:
          - criteria "0"             -> lose (the line landed outside the cell)
          - criteria "win"/"wincap"  -> win  (payout = the cell's multiplier)
        The payout is deterministic, so the round always satisfies its criteria's
        win_criteria on the first pass (no repeat) — which also means the landing row is
        drawn exactly once per book.

        The landing row is generated here (seeded, reproducible) and stored in the book,
        always on the correct side of the verdict. At bet time the RGS's provably-fair
        seed pair selects WHICH book is served, so the row a player sees is the certified
        outcome of that selection.
        """
        params = self.get_mode_params()
        is_win = self.criteria != "0"
        payout = params["multiplier"] if is_win else 0.0
        land_row = _land_row(params["zone_rows"], is_win)

        zone_round_event(
            self,
            is_win=is_win,
            zone_id=params["zone_id"],
            land_row=land_row,
            payout_cents=params["payout_cents"],
            win_chance=params["win_chance"],
        )

        self.win_manager.update_spinwin(payout)
        if payout > 0:
            # Global cap is 21x, so this emits a `wincap` event only in zone_line.
            self.evaluate_wincap()
