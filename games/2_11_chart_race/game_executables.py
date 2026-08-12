"""Orchestrating routines for Chart Race (2_11).

Verdict-first generation (the boat_race/porkageddon rule): the criteria assigned to this
sim fixes the payout, the payout plus the active market fix r0's finishing place, and
THIS module's job is to draw a finishing order that honestly produces that place — never
the reverse. Everything is drawn from the module RNG, which run_spin has already seeded
per (mode, sim), so a book's order is fully reproducible.
"""

import random

from game_calculations import GameCalculations
from game_events import race_result_event


def _finish_order(num_racers: int, player_place: int) -> list:
    """Certified finishing order: r0 pinned at `player_place`, rivals shuffled.

    Returns a permutation of racer ids [0..num_racers-1] indexed by place (element 0
    finishes highest). Uniform over the (num_racers-1)! arrangements of the rivals,
    conditioned on r0's fixed place — the published conditional presentation law.
    """
    others = list(range(1, num_racers))
    random.shuffle(others)
    order = [None] * num_racers
    order[player_place - 1] = 0
    k = 0
    for i in range(num_racers):
        if order[i] is None:
            order[i] = others[k]
            k += 1
    return order


class GameExecutables(GameCalculations):
    """Resolve a single certified race outcome and emit its client event."""

    def evaluate_race(self) -> None:
        """Resolve the round for the active criteria and emit the raceResult event.

        criteria "wincap" -> r0 at the market's winning place; criteria "0" -> r0 at a
        losing place drawn uniformly from the market's lose_places (the conditional law
        published in the readme and re-proved by verify_books.py). The payout is
        deterministic, so the round always satisfies its criteria's win_criteria on the
        first pass (no repeat) — the order is drawn exactly once per book.
        """
        params = self.get_mode_params()
        is_win = self.criteria != "0"
        # The event quotes the mode's price win OR lose (the zoneRound/priceCall
        # convention); the round's actual payout is what finalWin carries.
        quote_cents = params["payout_cents"]
        payout_cents = quote_cents if is_win else 0
        player_place = (
            params["win_place"] if is_win else random.choice(params["lose_places"])
        )

        final_order = _finish_order(params["num_racers"], player_place)

        # Generation-time contract asserts (verify_books.py re-proves these on the
        # published artifacts).
        assert final_order.index(0) + 1 == player_place, "order disagrees with place"
        assert (player_place == params["win_place"]) == is_win, (
            "finishing place would flip the verdict"
        )

        race_result_event(
            self,
            is_win=is_win,
            player_place=player_place,
            finish_order=final_order,
            payout_cents=quote_cents,
            win_chance=params["win_chance"],
        )

        self.win_manager.update_spinwin(payout_cents / 100.0)
        if payout_cents > 0:
            # Both markets' win payout equals the global 3.00x cap, so every winning
            # book emits `wincap` (the boat_race 1st-place pattern).
            self.evaluate_wincap()
