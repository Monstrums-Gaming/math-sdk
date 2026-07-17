#!/usr/bin/env python3
"""
Build the frontend-demo data bundle for Limbo Frankenstein (2_5) from the REAL
generated math output, so the browser demo replays the published lookup tables
instead of faking outcomes client-side.

It reads the game's published library:
    library/publish_files/index.json                -> the modes + their lookup tables
    library/publish_files/lookUpTable_<mode>_0.csv   -> the weighted payout distribution
    library/configs/event_config_<mode>.json         -> the engine's per-mode event template
    library/configs/config.json                      -> per-mode cost / maxWin

and emits ONE compact file the demo fetches:
    frontend_demo/limbo_rgs.json

Every Limbo lookup table has uniform weight 1 and exactly two distinct payouts
(0 or the win value W = target*cost), so each mode collapses to two outcomes. The
demo weighted-picks between them and synthesises the winInfo+finalWin events,
reproducing the real book with no zstd decoder in the browser.

Per mode the bundle exposes the player-facing target `T` and its win probability;
the tier's `cost` scales the absolute stake/payout (W = T*cost) but the multiplier
the player wins relative to their stake is always `T`. RTP = (winRows/total)*W/cost
= (winRows/total)*T.

Re-run this after any math rebuild (the bundle is generated, not source):
    env/bin/python games/2_5_limbo_frankenstein/frontend_demo/build_demo_data.py
"""

import csv
import json
import os

# Stake's ACP RTP band (per-mode). Modes are authored to land inside this; the
# demo just checks each mode stays within it.
RTP_FLOOR, RTP_CEIL = 0.90, 0.967

HERE = os.path.dirname(os.path.abspath(__file__))
LIBRARY = os.path.join(HERE, "..", "library")
PUBLISH = os.path.join(LIBRARY, "publish_files")
CONFIGS = os.path.join(LIBRARY, "configs")
OUT_FILE = os.path.join(HERE, "limbo_rgs.json")


def _read_lut(path):
    """Return (win_payout_cents, win_rows, loss_rows) for a Limbo lookup table.

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
    game_id = cfg.get("gameID", "2_5_limbo_frankenstein")
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
        )["winInfo"]
        target = ev["target"]
        win_chance = ev["winChance"]            # probability in [0,1]
        multiplier = ev["payoutMultiplier"] / 100.0   # W = target * cost (LUT win payout)

        shelf = by_name[name]
        cost = shelf.get("cost", 1.0)
        tier = name.split("_", 1)[0]            # base | streak | high  (name is dot-free, e.g. base_1_10)

        # Cross-check the engine template against the raw lookup table.
        assert ev["payoutMultiplier"] == win_payout, (
            f"{name}: event multiplier {ev['payoutMultiplier']} != LUT payout {win_payout}"
        )
        assert abs(win_chance - win_rows / total) < 1e-6, (
            f"{name}: winChance {win_chance} != LUT {win_rows}/{total}"
        )
        # Realised RTP = (winRows/total)*W/cost = (winRows/total)*target; inside Stake's band.
        rtp_mode = round((win_rows / total) * multiplier / cost, 6)
        assert RTP_FLOOR - 1e-9 <= rtp_mode <= RTP_CEIL + 1e-9, (
            f"{name}: RTP {rtp_mode} outside [{RTP_FLOOR}, {RTP_CEIL}]"
        )
        assert abs(multiplier - target * cost) < 1e-6, (
            f"{name}: W {multiplier} != target*cost {target * cost}"
        )

        modes.append(
            {
                "name": name,
                "tier": tier,
                "target": target,            # player-facing win multiplier
                "cost": cost,                # stake scale (base 1, streak 2/5, high 100)
                "multiplier": multiplier,    # W = target*cost (LUT win payout, book payoutMultiplier/100)
                "winChance": win_chance,     # probability of winning
                "rtp": rtp_mode,
                "maxWin": shelf.get("maxWin", 50000.0),
                "outcomes": [
                    {"payoutCents": win_payout, "weight": win_rows},
                    {"payoutCents": 0, "weight": loss_rows},
                ],
            }
        )

    rtps = [m["rtp"] for m in modes]
    tiers = {}
    for m in modes:
        tiers.setdefault(m["tier"], []).append(m["target"])
    for t in tiers:
        tiers[t] = sorted(tiers[t])

    bundle = {
        "game_id": game_id,
        "rtp": round(max(rtps), 4),
        # A real RGS sources this from the authenticate config.jurisdiction; the demo
        # passes it through so the autoplay panel can honour the kill-switch (True hides it).
        "disabledAutoplay": False,
        "tiers": tiers,                      # {tier: [sorted targets]} for the demo slider snap
        "modes": modes,
    }
    with open(OUT_FILE, "w", encoding="UTF-8") as fh:
        json.dump(bundle, fh, indent=1)

    print(f"Wrote {OUT_FILE}")
    print(f"  modes={len(modes)}  tiers={ {t: len(v) for t, v in tiers.items()} }")
    print(f"  RTP range: {min(rtps)}..{max(rtps)} (Stake band 0.90-0.967)")


if __name__ == "__main__":
    main()
