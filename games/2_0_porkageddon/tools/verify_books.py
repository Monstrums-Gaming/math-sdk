"""Verify the published Porkageddon books against the contract they advertise.

`execute_all_tests` only proves the books and the lookup table agree with each other
and that the LUT is on the 0.1x grid. It says nothing about whether the battle
transcripts are internally honest — and a transcript that quietly contradicts the
published slot ranges is both datamineable and a desync for any client that
re-derives damage from `roll`.

This walks every published book and asserts:

  1. Every attack `amount` is EXACTLY the value its own `roll` derives to, using the
     formula documented in game_events.py, against the slot table carried in that
     book's own `porkSetup.slots`. (Catches any path that rewrites a damage number.)
  2. Every attack `amount` sits inside its slot's scaled roll range.
  3. Every heal `amount` sits inside the scaled Penicillin range, and never takes a
     side above `hpMax`.
  4. The HP track reconstructs from nothing but `hpMax` and the per-round moves —
     i.e. the numbers shown and the bar agree.
  5. The loser reaches exactly 0 and the winner survives; the round count, pot and
     `payoutMultiplier` match `porkResult`, and the pot equals the sum of both
     sides' slot costs over every round.
  6. `payoutMultiplier` (book) == `finalWin.amount` == the LUT cents, on the grid.

Run from the math-sdk root after a compressed build:

    PYTHONPATH="$(pwd)" ./env/bin/python games/2_0_porkageddon/tools/verify_books.py

Exits non-zero on the first class of failure, with a concrete book id and round.
"""

import io
import json
import os
import sys
from collections import Counter

import zstandard

GAME_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, GAME_DIR)

import pork_math as pm  # noqa: E402

PUBLISH = os.path.join(GAME_DIR, "library", "publish_files")
ACT_ATTACK, ACT_HEAL, ACT_NONE = 0, 1, 2
FIRST_PLAYER = 0
SCALES = {"p": pm.PLAYER_ROLL_SCALE, "o": pm.OPPONENT_ROLL_SCALE}


def derive(low, high, roll, scale):
    """The documented client-side re-derivation of an amount from its roll."""
    scaled = (low * 10_000 + (high - low) * roll) * scale.numerator
    return max(1, scaled // (10_000 * scale.denominator))


def check_mode(name):
    path = os.path.join(PUBLISH, f"books_{name}.jsonl.zst")
    dctx = zstandard.ZstdDecompressor()
    stats = Counter()
    with open(path, "rb") as fh, dctx.stream_reader(fh) as reader:
        for line in io.TextIOWrapper(reader, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            book = json.loads(line)
            bid = book["id"]
            events = {e["type"]: e for e in book["events"]}
            setup, battle, result = events["porkSetup"], events["porkBattle"], events["porkResult"]
            slots = {s["index"]: s for s in setup["slots"]}
            hp_max = setup["hpMax"]
            order = battle["fieldOrder"]
            col = {f: i for i, f in enumerate(order)}

            hp = {"p": hp_max, "o": hp_max}
            pot_h = 0
            dead = False
            for r_i, row in enumerate(battle["rounds"]):
                where = f"{name} book {bid} round {r_i}"
                first = row[col["first"]]
                sides = ("p", "o") if first == FIRST_PLAYER else ("o", "p")
                for side in sides:
                    pre = "p" if side == "p" else "o"
                    slot = slots[row[col[f"{pre}Slot"]]]
                    act = row[col[f"{pre}Act"]]
                    roll = row[col[f"{pre}Roll"]]
                    amount = row[col[f"{pre}Amt"]]
                    pot_h += slot["costHundredths"]

                    if act == ACT_NONE:
                        assert amount == 0, f"{where}: unresolved move has amount {amount}"
                        assert dead, f"{where}: unresolved move but nobody is dead"
                        stats["unresolved"] += 1
                        continue
                    assert not dead, f"{where}: move resolved after a death"

                    if act == ACT_HEAL:
                        low, high = pm.HEAL_MIN, pm.HEAL_MAX
                        stats["heal"] += 1
                    else:
                        low, high = slot["dmgMin"], slot["dmgMax"]
                        stats["attack"] += 1

                    want = derive(low, high, roll, SCALES[side])
                    lo_amt = derive(low, high, 0, SCALES[side])
                    hi_amt = derive(low, high, 10_000, SCALES[side])

                    if act == ACT_ATTACK:
                        # (1) and (2): the number must be the roll's number, in range.
                        assert amount == want, (
                            f"{where}: {side} attack amount {amount} != {want} derived from "
                            f"roll {roll} on slot '{slot['name']}' ({low}-{high})"
                        )
                        assert lo_amt <= amount <= hi_amt, (
                            f"{where}: {side} attack amount {amount} outside the scaled range "
                            f"{lo_amt}-{hi_amt} for slot '{slot['name']}'"
                        )
                        target = "o" if side == "p" else "p"
                        hp[target] = max(0, hp[target] - amount)
                        if hp[target] == 0:
                            dead = True
                    else:
                        # (3): a heal is capped at full HP, so it may be below `want`.
                        assert amount <= want, (
                            f"{where}: {side} heal {amount} exceeds {want} derived from roll {roll}"
                        )
                        assert amount == min(want, hp_max - hp[side]), (
                            f"{where}: {side} heal {amount} != min(rolled {want}, missing "
                            f"{hp_max - hp[side]})"
                        )
                        hp[side] = min(hp_max, hp[side] + amount)

                # (4): the reconstructed bar must equal what the book published.
                for side, key in (("p", "pHp"), ("o", "oHp")):
                    assert hp[side] == row[col[key]], (
                        f"{where}: reconstructed {key} {hp[side]} != published {row[col[key]]}"
                    )

            # (5) structure vs porkResult
            assert result["rounds"] == len(battle["rounds"]) == setup["rounds"], (
                f"{name} book {bid}: round count disagrees across events"
            )
            assert abs(result["poolUnits"] * 100 - pot_h) < 0.5, (
                f"{name} book {bid}: poolUnits {result['poolUnits']} != summed costs {pot_h / 100}"
            )
            if result["isWin"]:
                assert hp["p"] > 0 and hp["o"] == 0, f"{name} book {bid}: win but HP says otherwise"
            else:
                assert hp["o"] > 0 and hp["p"] == 0, f"{name} book {bid}: loss but HP says otherwise"
                assert book["payoutMultiplier"] == 0, f"{name} book {bid}: loss pays"

            # (6) money agreement
            cents = book["payoutMultiplier"]
            assert cents == int(round(result["payoutMultiplier"] * 100)), (
                f"{name} book {bid}: payoutMultiplier disagrees with porkResult"
            )
            assert cents == events["finalWin"]["amount"], (
                f"{name} book {bid}: finalWin.amount disagrees with payoutMultiplier"
            )
            assert cents == 0 or (cents >= 10 and cents % 10 == 0), (
                f"{name} book {bid}: {cents}c off the 0.1x grid"
            )
            if result["goldenTier"] == "none":
                assert cents == 0 or abs(result["poolMultiplier"] * 100 - cents) < 0.5, (
                    f"{name} book {bid}: non-golden win pays {cents}c, pot is "
                    f"{result['poolMultiplier']}x"
                )
            stats["books"] += 1
    return stats


def main():
    if not os.path.isdir(PUBLISH):
        raise SystemExit(f"{PUBLISH} not found — run a compressed build first.")
    total = Counter()
    for name in pm.STANCE_NAMES:
        stats = check_mode(name)
        total.update(stats)
        print(
            f"  {name:10s} OK  books={stats['books']:,}  attacks={stats['attack']:,}  "
            f"heals={stats['heal']:,}  unresolved={stats['unresolved']:,}"
        )
    print(
        f"\nAll {total['books']:,} books verified: every attack amount re-derives from its "
        f"roll and sits inside its slot's published range; HP tracks reconstruct exactly; "
        f"pots equal the summed slot costs; payouts agree across book/porkResult/finalWin "
        f"and sit on the 0.1x grid."
    )


if __name__ == "__main__":
    main()
