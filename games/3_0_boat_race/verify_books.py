"""Book-invariant walker for Boat Race (3_0).

`execute_all_tests` only proves book <-> LUT agreement; it says nothing about whether a
race transcript is internally honest. This walker re-proves, over EVERY published book:

  1. event chain is raceSetup -> raceRun -> raceResult -> [wincap] -> finalWin with
     dense 0-based indices, wincap present exactly on 3.00x books
  2. every ranks row is [seg, r0..r3] with seg dense and ranks a permutation of 1..4
  3. consecutive rows differ by at most ONE adjacent-rank transposition (a plausible
     overtake — nothing teleports)
  4. the last row's ranks equal the ranks implied by raceResult.finishOrder, and
     playerPlace == rank of r0 there
  5. payoutMultiplier == payout ladder at playerPlace == book payoutMultiplier
     == finalWin.amount, and isWin <=> payout > 0
  6. LUT agreement: lookUpTable_race_0.csv rows are (book id, 1, payout cents)
  7. place counts are exactly uniform (1000 each) and LUT RTP == 0.95

Run from the math-sdk root AFTER run.py:  env/bin/python games/3_0_boat_race/verify_books.py
"""

import json
import os
import sys
from collections import Counter

GAME_DIR = os.path.dirname(os.path.abspath(__file__))
PUBLISH = os.path.join(GAME_DIR, "library", "publish_files")
LADDER_CENTS = [300, 60, 20, 0]
SEGMENTS = 30


def _load_books() -> list:
    zst = os.path.join(PUBLISH, "books_race.jsonl.zst")
    raw = os.path.join(GAME_DIR, "library", "books", "books_race.jsonl")
    if os.path.exists(zst):
        import zstandard

        with open(zst, "rb") as fh:
            data = zstandard.ZstdDecompressor().stream_reader(fh).read()
        lines = data.decode("utf-8").strip().splitlines()
    elif os.path.exists(raw):
        with open(raw, "r", encoding="utf-8") as fh:
            lines = fh.read().strip().splitlines()
    else:
        sys.exit(f"no books found in {PUBLISH} or library/books — run run.py first")
    return [json.loads(line) for line in lines]


def _check_book(book: dict) -> int:
    events = book["events"]
    types = [e["type"] for e in events]
    payout = book["payoutMultiplier"]

    expected = ["raceSetup", "raceRun", "raceResult"]
    expected += ["wincap"] if payout == 300 else []
    expected += ["finalWin"]
    assert types == expected, f"book {book['id']}: event chain {types}"
    for i, e in enumerate(events):
        assert e["index"] == i, f"book {book['id']}: index gap at {i}"

    setup, run, result = events[0], events[1], events[2]
    final_win = events[-1]

    assert setup["payoutLadder"] == LADDER_CENTS, f"book {book['id']}: ladder mismatch"
    assert run["fieldOrder"] == ["seg", "r0", "r1", "r2", "r3"]
    ranks = run["ranks"]
    assert len(ranks) == SEGMENTS, f"book {book['id']}: {len(ranks)} rows"

    prev = None
    for s, row in enumerate(ranks):
        assert row[0] == s, f"book {book['id']}: seg index gap at {s}"
        assert sorted(row[1:]) == [1, 2, 3, 4], f"book {book['id']} seg {s}: not a permutation"
        if prev is not None:
            diff = [i for i in range(1, 5) if row[i] != prev[i]]
            assert len(diff) in (0, 2), f"book {book['id']} seg {s}: non-adjacent change"
            if len(diff) == 2:
                a, b = row[diff[0]], row[diff[1]]
                assert abs(a - b) == 1, f"book {book['id']} seg {s}: rank jump"
        prev = row

    finish_order = result["finishOrder"]
    assert sorted(finish_order) == [0, 1, 2, 3], f"book {book['id']}: bad finishOrder"
    last = ranks[-1]
    for place_idx, racer in enumerate(finish_order):
        assert last[1 + racer] == place_idx + 1, f"book {book['id']}: last row != finishOrder"

    place = result["playerPlace"]
    assert place == last[1], f"book {book['id']}: playerPlace != r0's final rank"
    expected_cents = LADDER_CENTS[place - 1]
    assert result["payoutMultiplier"] == expected_cents, f"book {book['id']}: result payout"
    assert payout == expected_cents, f"book {book['id']}: book payout"
    assert final_win["amount"] == expected_cents, f"book {book['id']}: finalWin amount"
    assert result["isWin"] == (expected_cents > 0), f"book {book['id']}: isWin"
    assert result["result"] == ("Win" if expected_cents > 0 else "Lose")
    assert abs(result["winChance"] - 0.75) < 1e-12
    return place


def main() -> None:
    books = _load_books()
    places = Counter(_check_book(b) for b in books)

    n = len(books)
    assert n == 4000, f"expected 4000 books, found {n}"
    assert all(places[p] == n // 4 for p in (1, 2, 3, 4)), f"place counts not uniform: {places}"

    # LUT agreement + RTP
    lut_path = os.path.join(PUBLISH, "lookUpTable_race_0.csv")
    assert os.path.exists(lut_path), "published LUT missing"
    by_id = {b["id"]: b["payoutMultiplier"] for b in books}
    total = 0
    with open(lut_path, "r", encoding="utf-8") as fh:
        rows = [line.strip().split(",") for line in fh if line.strip()]
    assert len(rows) == n, "LUT row count != book count"
    for sim_id, weight, cents in rows:
        assert int(weight) == 1, "direct-probability weights must be 1"
        assert by_id[int(sim_id)] == int(cents), f"LUT/book payout mismatch at id {sim_id}"
        total += int(cents)
    rtp = total / n / 100
    assert abs(rtp - 0.95) < 1e-12, f"LUT RTP {rtp} != 0.95"

    print(f"OK: {n} books · places {dict(sorted(places.items()))} · LUT RTP {rtp}")
    print("all transcript, payout and LUT invariants hold")


if __name__ == "__main__":
    main()
