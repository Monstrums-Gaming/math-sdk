"""Book-invariant walker for Chart Race (2_11).

`execute_all_tests` only proves book <-> LUT agreement; it says nothing about whether a
certified finishing order is internally honest. This walker re-proves, over EVERY
published book of BOTH modes:

  1. event chain is raceResult -> [wincap] -> finalWin with dense 0-based indices,
     wincap present exactly on 3.00x books
  2. finishOrder is a permutation of [0, 1, 2] and playerPlace == index of r0 + 1
  3. the market semantics hold: `highest` wins iff playerPlace == 1, `lowest` wins iff
     playerPlace == 3 — the order can NEVER contradict the payout
  4. payoutMultiplier == book payoutMultiplier == finalWin.amount, isWin <=> payout > 0,
     winChance == 8/25 exactly
  5. LUT agreement: lookUpTable_<mode>_0.csv rows are (book id, 1, payout cents)
  6. per-mode counts: 5000 books, exactly 1600 winners, LUT RTP == 0.96 exactly
  7. the conditional loss law is balanced: each losing place count within 4 sigma of
     its uniform expectation (a canned or drifted sampler fails the build)

Run from the math-sdk root AFTER run.py:
    env/bin/python games/2_11_chart_race/verify_books.py
"""

import json
import os
import sys
from collections import Counter
from math import sqrt

GAME_DIR = os.path.dirname(os.path.abspath(__file__))
PUBLISH = os.path.join(GAME_DIR, "library", "publish_files")

MODES = {
    # mode -> (winning place, losing places)
    "highest": (1, (2, 3)),
    "lowest": (3, (1, 2)),
}
PAYOUT_CENTS = 300
WIN_CHANCE = 8 / 25
NUM_SIMS = 5000
WINNERS = 1600
NUM_RACERS = 3


def _load_books(mode: str) -> list:
    zst = os.path.join(PUBLISH, f"books_{mode}.jsonl.zst")
    raw = os.path.join(GAME_DIR, "library", "books", f"books_{mode}.jsonl")
    if os.path.exists(zst):
        import zstandard

        with open(zst, "rb") as fh:
            data = zstandard.ZstdDecompressor().stream_reader(fh).read()
        lines = data.decode("utf-8").strip().splitlines()
    elif os.path.exists(raw):
        with open(raw, "r", encoding="utf-8") as fh:
            lines = fh.read().strip().splitlines()
    else:
        sys.exit(f"no books for mode {mode} in {PUBLISH} or library/books — run run.py first")
    return [json.loads(line) for line in lines]


def _check_book(mode: str, book: dict) -> int:
    win_place, lose_places = MODES[mode]
    events = book["events"]
    types = [e["type"] for e in events]
    payout = book["payoutMultiplier"]

    expected = ["raceResult"]
    expected += ["wincap"] if payout == PAYOUT_CENTS else []
    expected += ["finalWin"]
    assert types == expected, f"{mode} book {book['id']}: event chain {types}"
    for i, e in enumerate(events):
        assert e["index"] == i, f"{mode} book {book['id']}: index gap at {i}"

    result = events[0]
    final_win = events[-1]

    finish_order = result["finishOrder"]
    assert sorted(finish_order) == list(range(NUM_RACERS)), (
        f"{mode} book {book['id']}: bad finishOrder {finish_order}"
    )
    place = result["playerPlace"]
    assert place == finish_order.index(0) + 1, (
        f"{mode} book {book['id']}: playerPlace != r0's place in finishOrder"
    )

    # The honesty invariant: the certified order can never contradict the payout.
    is_win = place == win_place
    assert result["isWin"] == is_win, f"{mode} book {book['id']}: isWin vs place"
    if not is_win:
        assert place in lose_places, f"{mode} book {book['id']}: impossible losing place"

    expected_cents = PAYOUT_CENTS if is_win else 0
    assert result["payoutMultiplier"] == PAYOUT_CENTS, (
        f"{mode} book {book['id']}: payoutMultiplier must quote the mode price win or lose"
    )
    assert payout == expected_cents, f"{mode} book {book['id']}: book payout"
    assert final_win["amount"] == expected_cents, f"{mode} book {book['id']}: finalWin"
    assert result["result"] == ("Win" if is_win else "Lose")
    assert abs(result["winChance"] - WIN_CHANCE) < 1e-12
    return place


def _check_mode(mode: str) -> None:
    win_place, lose_places = MODES[mode]
    books = _load_books(mode)
    places = Counter(_check_book(mode, b) for b in books)

    n = len(books)
    assert n == NUM_SIMS, f"{mode}: expected {NUM_SIMS} books, found {n}"
    assert places[win_place] == WINNERS, (
        f"{mode}: {places[win_place]} winners, expected {WINNERS}"
    )

    # Conditional loss law: uniform over the two losing places, within 4 sigma.
    losses = n - WINNERS
    expect = losses / len(lose_places)
    sigma = sqrt(losses * 0.5 * 0.5)
    for p in lose_places:
        assert abs(places[p] - expect) <= 4 * sigma, (
            f"{mode}: losing place {p} count {places[p]} outside 4 sigma of {expect:.0f}"
        )

    # LUT agreement + RTP (exact: 1600 * 300 / 5000 / 100 == 0.96).
    lut_path = os.path.join(PUBLISH, f"lookUpTable_{mode}_0.csv")
    assert os.path.exists(lut_path), f"{mode}: published LUT missing"
    by_id = {b["id"]: b["payoutMultiplier"] for b in books}
    total = 0
    with open(lut_path, "r", encoding="utf-8") as fh:
        rows = [line.strip().split(",") for line in fh if line.strip()]
    assert len(rows) == n, f"{mode}: LUT row count != book count"
    for sim_id, weight, cents in rows:
        assert int(weight) == 1, "direct-probability weights must be 1"
        assert by_id[int(sim_id)] == int(cents), (
            f"{mode}: LUT/book payout mismatch at id {sim_id}"
        )
        total += int(cents)
    rtp = total / n / 100
    assert abs(rtp - 0.96) < 1e-12, f"{mode}: LUT RTP {rtp} != 0.96"

    print(f"OK {mode}: {n} books · places {dict(sorted(places.items()))} · LUT RTP {rtp}")


def main() -> None:
    for mode in MODES:
        _check_mode(mode)
    print("all order, payout and LUT invariants hold for both modes")


if __name__ == "__main__":
    main()
