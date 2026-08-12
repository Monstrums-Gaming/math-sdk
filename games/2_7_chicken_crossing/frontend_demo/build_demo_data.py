#!/usr/bin/env python3
"""
Build the frontend-demo data bundle for Chicken Crossing (2_7) from the REAL
generated math output, so the browser demo replays the published lookup tables
instead of faking outcomes client-side.

It reads the game's published library:
    library/publish_files/index.json                -> the modes + their lookup tables
    library/publish_files/lookUpTable_<mode>_0.csv   -> the weighted payout distribution
    library/configs/event_config_<mode>.json         -> the engine's per-mode event template
    library/configs/config.json                      -> per-mode cost / maxWin

and emits ONE compact file the demo fetches:
    frontend_demo/chicken_rgs.json

Unlike Limbo (2 outcomes) each chicken mode is MULTI-OUTCOME: one distinct payout
per snapped ladder rung plus a single 0-payout (pop). The LUT collapses by distinct
`payout_cents`; the demo weighted-picks an outcome and synthesises the
crossingSetup+crossingResult+finalWin events, reproducing the real book with no
zstd decoder in the browser. Predetermined replay only (the RGS settles one book
per round — see README.md / the game readme.txt warning).

Re-run this after any math rebuild (the bundle is generated, not source):
    PYTHONPATH="$(pwd)" env/bin/python games/2_7_chicken_crossing/frontend_demo/build_demo_data.py
"""

import csv
import json
import os

# Demo RTP sanity band. Chicken is authored at ~97% (the user spec), which is ABOVE
# Stake's 96.70% ACP ceiling — the demo only checks the numbers are self-consistent
# and prints a notice; it does not enforce the ACP ceiling (see readme.txt warning #2).
RTP_FLOOR, RTP_CEIL = 0.90, 0.98
ACP_CEIL = 0.967

HERE = os.path.dirname(os.path.abspath(__file__))
LIBRARY = os.path.join(HERE, "..", "library")
PUBLISH = os.path.join(LIBRARY, "publish_files")
CONFIGS = os.path.join(LIBRARY, "configs")
OUT_FILE = os.path.join(HERE, "chicken_rgs.json")


def _read_lut(path):
    """Return {payout_cents: weight_sum} collapsed over a chicken lookup table.

    Asserts uniform weight 1 per row so a math change can never silently break the
    demo's odds.
    """
    payout_rows = {}
    with open(path, newline="", encoding="UTF-8") as fh:
        for sim_id, weight, payout in csv.reader(fh):
            w = float(weight)
            p = int(payout)
            assert w == 1, f"{os.path.basename(path)}: non-uniform weight {w} (demo assumes weight 1)"
            payout_rows[p] = payout_rows.get(p, 0) + 1
    return payout_rows


def _pop_weights(ladder, mode_rtp):
    """Cosmetic per-step 'died crossing lane k' weights for the LOCAL loss reveal.

    cumSurv_k = mode_rtp / ladder[k] (ladder[k] = 0.97/cumSurv_k by construction);
    weight_k = cumSurv_{k-1} - cumSurv_k with cumSurv_{-1}=1. Purely for choosing a
    natural-looking crash lane — the loss payout is always 0.
    """
    weights, prev = [], 1.0
    for m in ladder:
        cs = mode_rtp / m
        weights.append(max(prev - cs, 0.0))
        prev = cs
    tot = sum(weights) or 1.0
    return [round(w / tot, 8) for w in weights]


def main():
    index = json.load(open(os.path.join(PUBLISH, "index.json"), encoding="UTF-8"))
    cfg = json.load(open(os.path.join(CONFIGS, "config.json"), encoding="UTF-8"))
    game_id = cfg.get("gameID", "2_7_chicken_crossing")
    by_name = {b["name"]: b for b in cfg["bookShelfConfig"]}

    modes = {}
    order = []
    for entry in index["modes"]:
        name = entry["name"]
        lut_path = os.path.join(PUBLISH, entry["weights"])
        payout_rows = _read_lut(lut_path)
        total = sum(payout_rows.values())

        # Authoritative per-mode event template written by the engine.
        setup = json.load(
            open(os.path.join(CONFIGS, f"event_config_{name}.json"), encoding="UTF-8")
        )["crossingSetup"]
        ladder = [round(x, 2) for x in setup["ladder"]]
        num_steps = setup["numSteps"]
        max_win = setup["maxWin"]
        assert len(ladder) == num_steps, f"{name}: ladder {len(ladder)} != numSteps {num_steps}"

        shelf = by_name[name]
        cost = shelf.get("cost", 1.0)

        # Cross-check: every distinct non-zero LUT payout is a rung of the ladder.
        ladder_cents = {int(round(m * 100)) for m in ladder}
        for cents in payout_rows:
            if cents != 0:
                assert cents in ladder_cents, (
                    f"{name}: LUT payout {cents}c not found in ladder {sorted(ladder_cents)}"
                )

        # Realised RTP recomputed from the collapsed distribution.
        rtp_mode = round(sum(c * w for c, w in payout_rows.items()) / total / 100.0, 6)
        assert RTP_FLOOR - 1e-9 <= rtp_mode <= RTP_CEIL + 1e-9, (
            f"{name}: RTP {rtp_mode} outside demo band [{RTP_FLOOR}, {RTP_CEIL}]"
        )

        outcomes = [
            {"payoutCents": c, "weight": payout_rows[c]}
            for c in sorted(payout_rows)
        ]
        max_win_cents = int(round(max_win * 100))
        max_win_rows = payout_rows.get(max_win_cents, 0)

        modes[name] = {
            "name": name,
            "difficulty": name,
            "numSteps": num_steps,
            "cost": cost,
            "ladder": ladder,
            "maxWin": max_win,
            "rtp": rtp_mode,
            "totalWeight": total,
            "outcomes": outcomes,
            "popWeights": _pop_weights(ladder, rtp_mode),
            "maxWinRows": max_win_rows,
        }
        order.append(name)

    rtps = [m["rtp"] for m in modes.values()]
    bundle = {
        "game_id": game_id,
        "difficulties": order,
        "rtp": round(max(rtps), 4),
        # A real RGS sources this from the authenticate config.jurisdiction; the demo
        # passes it through so the autoplay panel can honour the kill-switch (True hides it).
        "disabledAutoplay": False,
        # Predetermined replay: the book fixes the whole outcome, cash-out step included.
        "predeterminedSettlement": True,
        "modes": modes,
    }
    with open(OUT_FILE, "w", encoding="UTF-8") as fh:
        json.dump(bundle, fh, indent=1)

    print(f"Wrote {OUT_FILE}")
    for name in order:
        m = modes[name]
        top = m["ladder"][-1]
        mwp = m["maxWinRows"] / m["totalWeight"] if m["totalWeight"] else 0
        one_in = (1 / mwp) if mwp else float("inf")
        print(
            f"  {name:10s} steps={m['numSteps']:2d} max={top:>8.1f}x rtp={m['rtp']:.5f} "
            f"outcomes={len(m['outcomes']):2d} maxWin=1 in {one_in:,.0f}"
        )
    print(f"  RTP range: {min(rtps)}..{max(rtps)}")
    if max(rtps) > ACP_CEIL + 1e-9:
        print(
            f"  NOTICE: RTP {max(rtps):.4f} exceeds the ACP ceiling {ACP_CEIL} — demo/faithful build. "
            f"Rebuild the math with RTP_TARGET=0.965 for an ACP-valid bundle."
        )


if __name__ == "__main__":
    main()
