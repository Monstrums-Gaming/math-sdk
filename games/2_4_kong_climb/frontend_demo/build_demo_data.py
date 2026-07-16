#!/usr/bin/env python3
"""
Build the frontend-demo data bundle for Kong Climb (2_4) from the REAL generated
math output, so the browser demo replays the published lookup tables instead of
faking outcomes client-side.

It reads the game's published library:
    library/publish_files/index.json          -> the 192 modes + their lookup tables
    library/publish_files/lookUpTable_<mode>_0.csv  -> the weighted payout distribution
    library/configs/event_config_<mode>.json  -> the engine's per-mode event template
    library/configs/config.json               -> per-mode cost / maxWin

and emits ONE compact file the demo fetches:
    frontend_demo/kong_dice_rgs.json

Because every Kong lookup table has uniform weight 1 and at most two distinct
payouts (0 or the win value), each mode collapses to exactly two outcomes. The
demo weighted-picks between them and synthesises the diceResult+finalWin events,
reproducing the real book byte-for-byte with no zstd decoder in the browser.

Re-run this after any math rebuild (the bundle is generated, not source):
    env/bin/python games/2_4_kong_climb/frontend_demo/build_demo_data.py
"""

import csv
import json
import os

RTP = 0.97

HERE = os.path.dirname(os.path.abspath(__file__))
LIBRARY = os.path.join(HERE, "..", "library")
PUBLISH = os.path.join(LIBRARY, "publish_files")
CONFIGS = os.path.join(LIBRARY, "configs")
OUT_FILE = os.path.join(HERE, "kong_dice_rgs.json")


def _read_lut(path):
    """Return (win_payout_cents, win_rows, loss_rows) for a Kong lookup table.

    Asserts the 2-outcome / uniform-weight shape so a math change can never
    silently break the demo's odds.
    """
    payout_rows = {}
    with open(path, newline="", encoding="UTF-8") as fh:
        for sim_id, weight, payout in csv.reader(fh):
            w = float(weight)
            p = int(payout)
            assert w == 1, f"{os.path.basename(path)}: non-uniform weight {w} (demo assumes weight 1)"
            payout_rows[p] = payout_rows.get(p, 0) + 1

    payouts = set(payout_rows)
    assert payouts <= {0} | {max(payouts)}, (
        f"{os.path.basename(path)}: expected at most 2 payouts {{0, win}}, got {sorted(payouts)}"
    )
    win_payout = max(payouts)
    assert win_payout > 0, f"{os.path.basename(path)}: no winning payout"
    win_rows = payout_rows[win_payout]
    loss_rows = payout_rows.get(0, 0)
    return win_payout, win_rows, loss_rows


def main():
    index = json.load(open(os.path.join(PUBLISH, "index.json"), encoding="UTF-8"))
    cfg = json.load(open(os.path.join(CONFIGS, "config.json"), encoding="UTF-8"))
    game_id = cfg.get("gameID", "2_4_kong_climb")
    by_name = {b["name"]: b for b in cfg["bookShelfConfig"]}

    modes = []
    for entry in index["modes"]:
        name = entry["name"]
        lut_path = os.path.join(PUBLISH, entry["weights"])
        win_payout, win_rows, loss_rows = _read_lut(lut_path)
        total = win_rows + loss_rows

        # Authoritative per-mode event template written by the engine.
        ev = json.load(
            open(os.path.join(CONFIGS, f"event_config_{name}.json"), encoding="UTF-8")
        )["diceResult"]
        direction = ev["direction"]
        target = ev["target"]
        win_chance = ev["winChance"]
        multiplier = ev["payoutMultiplier"] / 100.0

        # Cross-check the engine template against the raw lookup table.
        assert ev["payoutMultiplier"] == win_payout, (
            f"{name}: event multiplier {ev['payoutMultiplier']} != LUT payout {win_payout}"
        )
        assert abs(win_chance - win_rows / total * 100) < 0.01, (
            f"{name}: winChance {win_chance} != LUT {win_rows}/{total}"
        )
        # RTP is ~0.97 (exact where winChance divides 9700, else cent-rounded).
        rtp_mode = round((win_rows / total) * multiplier, 6)
        assert abs(rtp_mode - RTP) <= 0.01, f"{name}: RTP {rtp_mode} too far from {RTP}"

        shelf = by_name[name]
        modes.append(
            {
                "name": name,
                "direction": direction,
                "tier": int(name.rsplit("_", 1)[1]),
                "multiplier": multiplier,
                "winChance": win_chance,
                "target": target,
                "cost": shelf.get("cost", 1.0),
                "maxWin": shelf.get("maxWin", 48.5),
                "outcomes": [
                    {"payoutCents": win_payout, "weight": win_rows},
                    {"payoutCents": 0, "weight": loss_rows},
                ],
            }
        )

    bundle = {"game_id": game_id, "rtp": RTP, "modes": modes}
    with open(OUT_FILE, "w", encoding="UTF-8") as fh:
        json.dump(bundle, fh, indent=1)

    tiers = sorted({m["tier"] for m in modes})
    mults = sorted({m["multiplier"] for m in modes})
    rtps = [
        round((m["outcomes"][0]["weight"] / (m["outcomes"][0]["weight"] + m["outcomes"][1]["weight"])) * m["multiplier"], 6)
        for m in modes
    ]
    print(f"Wrote {OUT_FILE}")
    print(f"  modes={len(modes)}  targets={len(tiers)}  multipliers {mults[0]}x..{mults[-1]}x")
    print(f"  RTP range: {min(rtps)}..{max(rtps)} (target {RTP})")


if __name__ == "__main__":
    main()
