"""Build the frontend demo odds bundle for Boat Race (3_0).

Samples the PUBLISHED books (never hand-authored ones) into the `*_rgs.json` bundle the
standalone frontend's mock RGS serves, so the demo plays real certified books and can't
drift from the math. Odds are preserved exactly: the same number of books per place is
sampled, all weight 1, so the bundle's realised RTP equals the published 0.95.

Usage (from the math-sdk root):
    env/bin/python games/3_0_boat_race/frontend_demo/build_demo_data.py [dest.json]

Default dest: games/3_0_boat_race/frontend_demo/boat_race_rgs.json
"""

import json
import os
import sys
from collections import defaultdict

import zstandard

GAME_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUBLISH = os.path.join(GAME_DIR, "library", "publish_files")
LADDER_CENTS = [300, 60, 20, 0]
BOOKS_PER_PLACE = 10  # sampled uniformly per place -> odds identical to the full set


def main() -> None:
    with open(os.path.join(PUBLISH, "books_race.jsonl.zst"), "rb") as fh:
        lines = zstandard.ZstdDecompressor().stream_reader(fh).read().decode().strip().splitlines()
    books = [json.loads(line) for line in lines]

    by_place = defaultdict(list)
    for book in books:
        result = next(e for e in book["events"] if e["type"] == "raceResult")
        by_place[result["playerPlace"]].append(book)

    sampled = []
    for place in (1, 2, 3, 4):
        assert len(by_place[place]) >= BOOKS_PER_PLACE, f"not enough place-{place} books"
        sampled.extend(by_place[place][:BOOKS_PER_PLACE])
    sampled.sort(key=lambda b: b["id"])

    setup = sampled[0]["events"][0]
    bundle = {
        "game_id": "3_0_boat_race",
        "rtp": 0.95,
        "rtpNote": (
            "Uniform 1/4 place odds on the 0.1x payout grid quantize RTP to 0.025 "
            "steps; 0.95 is the max honest value <= the 0.967 ACP ceiling."
        ),
        "defaultMode": "race",
        "numBoats": setup["numBoats"],
        "laps": setup["laps"],
        "gates": setup["gates"],
        "winChance": 0.75,
        "disabledAutoplay": False,
        "payoutLadder": [
            {"place": i + 1, "payoutCents": c} for i, c in enumerate(LADDER_CENTS)
        ],
        "modes": {
            "race": {
                "cost": 1.0,
                "rtp": 0.95,
                "winChance": 0.75,
                "totalWeight": len(sampled),
                "outcomes": [
                    {"payoutCents": c, "weight": BOOKS_PER_PLACE} for c in LADDER_CENTS
                ],
                "books": sampled,
            }
        },
    }

    ev = sum(o["payoutCents"] * o["weight"] for o in bundle["modes"]["race"]["outcomes"])
    assert ev / bundle["modes"]["race"]["totalWeight"] / 100 == 0.95, "bundle RTP drifted"

    dest = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "boat_race_rgs.json"
    )
    with open(dest, "w", encoding="utf-8") as fh:
        json.dump(bundle, fh, indent=1)
        fh.write("\n")
    print(f"wrote {dest}: {len(sampled)} published books ({BOOKS_PER_PLACE}/place), RTP 0.95")


if __name__ == "__main__":
    main()
