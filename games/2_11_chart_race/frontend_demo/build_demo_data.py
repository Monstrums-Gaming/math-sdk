"""Build the frontend demo odds bundle for Chart Race (2_11).

Reads the PUBLISHED artifacts (never hand-authored data) into the `chart_race_rgs.json`
bundle the web app's mock RGS serves, so the offline game plays odds and finishing
orders the live RGS could genuinely have served. Per mode it emits the odds scalars,
the two-outcome weight table, and a reproducible sample of REAL certified finishOrders
split by outcome (the 2_9 `landRows` pattern) — carrying the published conditional
frequencies so the mock reproduces the presentation law by construction.

Usage (from the math-sdk root):
    env/bin/python games/2_11_chart_race/frontend_demo/build_demo_data.py [dest.json]

Default dest: games/2_11_chart_race/frontend_demo/chart_race_rgs.json
"""

import json
import os
import random
import sys

import zstandard

GAME_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUBLISH = os.path.join(GAME_DIR, "library", "publish_files")

MODES = {
    "highest": (1, (2, 3)),
    "lowest": (3, (1, 2)),
}
PAYOUT_CENTS = 300
WIN_CHANCE = 8 / 25
RTP = 0.96
NUM_RACERS = 3
SAMPLE_PER_OUTCOME = 300
SAMPLE_SEED = 20260811
DEFAULT_MODE = "highest"


def _read_books(mode: str) -> list:
    with open(os.path.join(PUBLISH, f"books_{mode}.jsonl.zst"), "rb") as fh:
        data = zstandard.ZstdDecompressor().stream_reader(fh).read()
    return [json.loads(line) for line in data.decode("utf-8").strip().splitlines()]


def _read_lut(mode: str) -> list:
    path = os.path.join(PUBLISH, f"lookUpTable_{mode}_0.csv")
    with open(path, "r", encoding="utf-8") as fh:
        rows = [line.strip().split(",") for line in fh if line.strip()]
    for _, weight, _ in rows:
        assert float(weight) == 1, "direct-probability weights must be 1"
    return rows


def _sample(values: list, rng: random.Random) -> list:
    if len(values) <= SAMPLE_PER_OUTCOME:
        return sorted(values)
    return sorted(rng.sample(values, SAMPLE_PER_OUTCOME))


def main() -> None:
    rng = random.Random(SAMPLE_SEED)
    modes_out = {}

    for mode, (win_place, lose_places) in MODES.items():
        books = _read_books(mode)
        lut = _read_lut(mode)
        assert len(lut) == len(books), f"{mode}: LUT rows != books"

        win_orders, lose_orders = [], []
        win_count = 0
        for book in books:
            result = book["events"][0]
            assert result["type"] == "raceResult", f"{mode}: first event not raceResult"
            order = result["finishOrder"]
            place = result["playerPlace"]
            assert sorted(order) == list(range(NUM_RACERS))
            assert place == order.index(0) + 1
            # The honesty invariant re-asserted per book.
            assert (place == win_place) == result["isWin"], (
                f"{mode} book {book['id']}: finishOrder contradicts the payout"
            )
            if result["isWin"]:
                win_count += 1
                win_orders.append(order)
            else:
                assert place in lose_places
                lose_orders.append(order)

        rtp_mode = win_count / len(books) * PAYOUT_CENTS / 100
        assert abs(rtp_mode - RTP) < 1e-12, f"{mode}: realised RTP {rtp_mode} != {RTP}"

        modes_out[mode] = {
            "market": mode,
            "winPlace": win_place,
            "multiplier": PAYOUT_CENTS / 100,
            "multiplierCents": PAYOUT_CENTS,
            "winChance": WIN_CHANCE,
            "rtp": rtp_mode,
            "totalWeight": len(books),
            "outcomes": [
                {"payoutCents": PAYOUT_CENTS, "weight": win_count},
                {"payoutCents": 0, "weight": len(books) - win_count},
            ],
            # Reproducible samples of REAL certified finishing orders, split by outcome,
            # so the web mock replays orders the RGS could genuinely have served.
            "finishOrders": {
                "win": _sample(win_orders, rng),
                "lose": _sample(lose_orders, rng),
            },
        }

    bundle = {
        "game_id": "2_11_chart_race",
        "rtp": RTP,
        "rtpNote": (
            "Both markets quote 3.00x at a certified 8/25 = 32% (Stern-Brocot pin in "
            "[96.00%, 96.70%]); the rendered race law is conditional on each mode's "
            "verdict, not a uniform 1/3 race — the odds derive from the LUT alone."
        ),
        "winChance": WIN_CHANCE,
        "maxWin": PAYOUT_CENTS / 100,
        "numRacers": NUM_RACERS,
        "defaultMode": DEFAULT_MODE,
        "disabledAutoplay": False,
        "modes": modes_out,
    }

    dest = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "chart_race_rgs.json"
    )
    with open(dest, "w", encoding="utf-8") as fh:
        json.dump(bundle, fh, separators=(",", ":"))
        fh.write("\n")
    sizes = {m: (len(v["finishOrders"]["win"]), len(v["finishOrders"]["lose"])) for m, v in modes_out.items()}
    print(f"wrote {dest}: 2 modes, RTP {RTP}, finishOrder samples {sizes}")


if __name__ == "__main__":
    main()
