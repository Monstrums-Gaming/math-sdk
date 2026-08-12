"""Orchestrating routines for Boat Race (3_0).

Verdict-first generation (the porkageddon rule): the criteria assigned to this sim fixes
the payout, the payout fixes r0's finishing place, and THIS module's job is to
manufacture a race transcript that honestly produces that place — never the reverse.
Everything is drawn from the module RNG, which run_spin has already seeded per-sim, so a
book's transcript is fully reproducible.
"""

import random

from game_calculations import GameCalculations
from game_events import race_setup_event, race_run_event, race_result_event

_MAX_START_DISTANCE = 4  # Kendall-tau cap between start and final order
_DRAMA_FIRST, _DRAMA_LAST = 3, 16  # segments allowed a random mid-race overtake
_CONVERGE_FROM = 18  # first segment of the forced convergence window


def _kendall(a: list, b: list) -> int:
    """Kendall-tau distance between two orders (arrays of racer ids, index = rank-1)."""
    pos_b = {racer: i for i, racer in enumerate(b)}
    d = 0
    for i in range(len(a)):
        for j in range(i + 1, len(a)):
            if pos_b[a[i]] > pos_b[a[j]]:
                d += 1
    return d


def _converge_swap(order: list, target: list) -> list:
    """One adjacent swap that reduces the Kendall distance toward `target`."""
    pos_t = {racer: i for i, racer in enumerate(target)}
    for i in range(len(order) - 1):
        if pos_t[order[i]] > pos_t[order[i + 1]]:
            nxt = list(order)
            nxt[i], nxt[i + 1] = nxt[i + 1], nxt[i]
            return nxt
    return order


def _make_timeline(start_order: list, final_order: list, segments: int) -> list:
    """Rank rows [seg, r0..r3] evolving by adjacent swaps, converging on final_order.

    Mirrors the frontend demo generator exactly: a drama window (segments 3..16) may
    apply one random adjacent swap per segment as long as the position stays recoverable
    (distance <= 5 with 12 converge segments in hand), then from segment 18 swaps bubble
    toward the final order — forced whenever the remaining segments equal the remaining
    distance, so the last row ALWAYS lands on the certified finish.
    """
    rows = []
    order = list(start_order)
    for seg in range(segments):
        if _DRAMA_FIRST <= seg <= _DRAMA_LAST and random.random() < 0.3:
            i = random.randrange(3)
            nxt = list(order)
            nxt[i], nxt[i + 1] = nxt[i + 1], nxt[i]
            if _kendall(nxt, final_order) <= 5:
                order = nxt
        if seg >= _CONVERGE_FROM:
            dist = _kendall(order, final_order)
            if dist > 0 and (dist >= (segments - 1 - seg) or random.random() < 0.55):
                order = _converge_swap(order, final_order)
        ranks = [0] * 4  # ranks[racer] = place 1..4
        for i, racer in enumerate(order):
            ranks[racer] = i + 1
        rows.append([seg, ranks[0], ranks[1], ranks[2], ranks[3]])
    assert _kendall(order, final_order) == 0, "timeline failed to converge"
    return rows


class GameExecutables(GameCalculations):
    """Resolve a single certified race and emit its client events."""

    def evaluate_race(self) -> None:
        """Resolve the round for the active criteria and emit the race events.

        criteria "wincap"/"p_60"/"p_20"/"0" -> r0 finishes 1st/2nd/3rd/4th. The payout is
        deterministic, so the round always satisfies its criteria's win_criteria on the
        first pass (no repeat) — the transcript is drawn exactly once per book.
        """
        params = self.get_mode_params()
        segments = params["segments"]
        player_place = params["criteria_place"][self.criteria]
        payout_cents = params["payout_ladder_cents"][player_place - 1]
        is_win = payout_cents > 0

        # finish order: r0 at its criteria-fixed place, rivals shuffled around it
        others = [1, 2, 3]
        random.shuffle(others)
        final_order = [None] * 4
        final_order[player_place - 1] = 0
        k = 0
        for i in range(4):
            if final_order[i] is None:
                final_order[i] = others[k]
                k += 1

        # start order: shuffled, guaranteed at least one overtake, always recoverable
        while True:
            start_order = [0, 1, 2, 3]
            random.shuffle(start_order)
            d = _kendall(start_order, final_order)
            if 0 < d <= _MAX_START_DISTANCE:
                break

        ranks = _make_timeline(start_order, final_order, segments)

        # generation-time contract asserts (verify_books.py re-proves these on the
        # published artifacts)
        last = ranks[-1]
        for place_idx, racer in enumerate(final_order):
            assert last[1 + racer] == place_idx + 1, "last ranks row != finishOrder"
        assert last[1] == player_place, "playerPlace disagrees with the timeline"

        race_setup_event(self, params)
        race_run_event(self, ranks)
        race_result_event(
            self,
            is_win=is_win,
            player_place=player_place,
            finish_order=final_order,
            payout_cents=payout_cents,
            win_chance=params["win_chance"],
        )

        self.win_manager.update_spinwin(payout_cents / 100.0)
        if payout_cents > 0:
            # Global cap is 3.00x, so this emits `wincap` only on 1st-place books.
            self.evaluate_wincap()
