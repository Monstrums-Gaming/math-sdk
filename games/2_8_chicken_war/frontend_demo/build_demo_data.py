#!/usr/bin/env python3
"""
Build the frontend-demo data bundle for Chicken War (2_8_chicken_war) from the REAL
generated math output, so the browser demo replays the published lookup tables
instead of faking outcomes client-side.

Reads the game's published library:
    library/publish_files/index.json                 -> the 81 modes + their LUTs
    library/publish_files/lookUpTable_<mode>_0.csv   -> the win/lose distribution
    library/configs/event_config_<mode>.json         -> the per-mode event template

Each mode `<difficulty>_<lane>` is a single win/lose wager (two payouts: the lane
multiplier or 0), so each collapses to two outcomes. Emits ONE file the demo fetches:
    frontend_demo/chicken_war_rgs.json  { game_id, difficulties, lanes, lanesPer, rtp,
      ladders:{easy:[..24],medium:[..22],hard:[..20],daredevil:[..15]}, modes:{...} }

Re-run after any math rebuild:
    PYTHONPATH="$(pwd)" env/bin/python games/2_8_chicken_war/frontend_demo/build_demo_data.py
"""

import csv
import json
import os

RTP_FLOOR, RTP_CEIL = 0.90, 0.98

HERE = os.path.dirname(os.path.abspath(__file__))
LIBRARY = os.path.join(HERE, "..", "library")
PUBLISH = os.path.join(LIBRARY, "publish_files")
CONFIGS = os.path.join(LIBRARY, "configs")
OUT_FILE = os.path.join(HERE, "chicken_war_rgs.json")
DIFFICULTIES = ["easy", "medium", "hard", "daredevil"]


def _read_lut(path):
    """Return (win_payout_cents, win_rows, loss_rows) for a win/lose lookup table."""
    payout_rows = {}
    with open(path, newline="", encoding="UTF-8") as fh:
        for _sim, weight, payout in csv.reader(fh):
            assert float(weight) == 1, f"{os.path.basename(path)}: non-uniform weight"
            p = int(payout)
            payout_rows[p] = payout_rows.get(p, 0) + 1
    payouts = set(payout_rows)
    assert payouts <= {0} | {max(payouts)}, f"{os.path.basename(path)}: expected {{0, win}}, got {sorted(payouts)}"
    win_payout = max(payouts)
    assert win_payout > 0, f"{os.path.basename(path)}: no winning payout"
    return win_payout, payout_rows[win_payout], payout_rows.get(0, 0)


def main():
    index = json.load(open(os.path.join(PUBLISH, "index.json"), encoding="UTF-8"))
    cfg = json.load(open(os.path.join(CONFIGS, "config.json"), encoding="UTF-8"))
    game_id = cfg.get("gameID", "2_8_chicken_war")

    modes, ladders = {}, {d: {} for d in DIFFICULTIES}
    for entry in index["modes"]:
        name = entry["name"]
        difficulty, lane = name.rsplit("_", 1)
        lane = int(lane)
        win_payout, win_rows, loss_rows = _read_lut(os.path.join(PUBLISH, entry["weights"]))
        total = win_rows + loss_rows

        ev = json.load(open(os.path.join(CONFIGS, f"event_config_{name}.json"), encoding="UTF-8"))["outcome"]
        multiplier = ev["payoutMultiplier"]
        assert round(multiplier * 100) == win_payout, f"{name}: event mult != LUT payout"
        # 10dp: daredevil's deep lanes have winChance down to 3.06e-7.
        rtp_mode = round((win_rows / total) * multiplier, 6)
        assert RTP_FLOOR - 1e-9 <= rtp_mode <= RTP_CEIL + 1e-9, f"{name}: RTP {rtp_mode} out of band"

        ladders[difficulty][lane] = multiplier
        modes[name] = {
            "difficulty": difficulty,
            "lane": lane,
            "multiplier": multiplier,
            "winChance": round(win_rows / total, 10),
            "rtp": rtp_mode,
            "totalWeight": total,
            "outcomes": [
                {"payoutCents": win_payout, "weight": win_rows},
                {"payoutCents": 0, "weight": loss_rows},
            ],
        }

    ladders = {d: [ladders[d][n] for n in sorted(ladders[d])] for d in DIFFICULTIES}
    rtps = [m["rtp"] for m in modes.values()]
    bundle = {
        "game_id": game_id,
        "difficulties": DIFFICULTIES,
        "lanes": max(len(v) for v in ladders.values()),
        "lanesPerDifficulty": {d: len(ladders[d]) for d in DIFFICULTIES},
        "rtp": round(max(rtps), 4),
        "disabledAutoplay": False,
        "ladders": ladders,
        "modes": modes,
    }
    with open(OUT_FILE, "w", encoding="UTF-8") as fh:
        json.dump(bundle, fh, indent=1)

    print(f"Wrote {OUT_FILE}")
    for d in DIFFICULTIES:
        lad = ladders[d]
        print(f"  {d:9s} lanes={len(lad)} max={lad[-1]}x  lane1={lad[0]}x")
    print(f"  RTP range: {min(rtps)}..{max(rtps)}")


if __name__ == "__main__":
    main()
