#!/usr/bin/env python3
"""
Build the frontend-demo data bundle for Plinko (2_6) from the REAL generated math
output, so the browser demo replays the published lookup tables instead of faking
outcomes client-side.

It reads the game's published library:
    library/publish_files/index.json                -> the modes + their lookup tables
    library/publish_files/lookUpTable_<mode>_0.csv   -> the realised payout distribution
    library/configs/event_config_<mode>.json         -> the engine's gameSetup cells
    library/configs/config.json                      -> per-mode cost / maxWin

and emits ONE compact file the demo fetches:
    frontend_demo/plinko_rgs.json

Each Plinko mode is a Galton board: bin k (0..N) is hit with binomial probability
C(N,k)/2**N and pays cells[k]. The demo weighted-picks a bin by those binomial
weights and reads the payout straight from the published cells, reproducing the
real book with no zstd decoder in the browser. Realised RTP therefore converges to
the published RTP = sum(C(N,k)*cells[k]) / 2**N.

Re-run this after any math rebuild (the bundle is generated, not source):
    PYTHONPATH="$(pwd)" ./env/bin/python games/2_6_plinko/frontend_demo/build_demo_data.py
"""

import csv
import json
import os
from math import comb

# Stake's ACP RTP band (per-mode). Modes are authored to land inside this; the demo
# just checks each mode stays within it.
RTP_FLOOR, RTP_CEIL = 0.90, 0.967

HERE = os.path.dirname(os.path.abspath(__file__))
LIBRARY = os.path.join(HERE, "..", "library")
PUBLISH = os.path.join(LIBRARY, "publish_files")
CONFIGS = os.path.join(LIBRARY, "configs")
OUT_FILE = os.path.join(HERE, "plinko_rgs.json")


def _lut_rtp(path):
    """Return realised RTP (mean payout / 100) from a lookup table, asserting weight 1."""
    total_cents = 0
    n_rows = 0
    with open(path, newline="", encoding="UTF-8") as fh:
        for _sim, weight, payout in csv.reader(fh):
            assert int(weight) == 1, f"{os.path.basename(path)}: non-uniform weight {weight}"
            total_cents += int(payout)
            n_rows += 1
    return total_cents / n_rows / 100.0, n_rows


def main():
    index = json.load(open(os.path.join(PUBLISH, "index.json"), encoding="UTF-8"))
    cfg = json.load(open(os.path.join(CONFIGS, "config.json"), encoding="UTF-8"))
    game_id = cfg.get("gameID", "2_6_plinko")
    by_name = {b["name"]: b for b in cfg["bookShelfConfig"]}

    modes = {}
    rows_set, diffs_set = set(), set()
    for entry in index["modes"]:
        name = entry["name"]
        n = int(name.split("_")[1][1:])            # base_rNN_diff -> NN
        difficulty = name.split("_", 2)[2]         # -> low|medium|high|expert
        rows_set.add(n)
        diffs_set.add(difficulty)

        # Authoritative per-mode cells from the engine's gameSetup event template.
        ev = json.load(open(os.path.join(CONFIGS, f"event_config_{name}.json"), encoding="UTF-8"))
        cells = ev["gameSetup"]["payoutCells"]
        assert len(cells) == n + 1, f"{name}: expected {n + 1} cells, got {len(cells)}"

        # Binomial bin weights C(N,k)/2**N (the ball-drop distribution).
        weights = [comb(n, k) for k in range(n + 1)]
        bin_weights = [w / (2 ** n) for w in weights]

        # Cross-check the cells against the raw lookup table.
        lut_rtp, n_books = _lut_rtp(os.path.join(PUBLISH, entry["weights"]))
        cells_rtp = sum(weights[k] * cells[k] for k in range(n + 1)) / (2 ** n)
        assert abs(cells_rtp - lut_rtp) < 1e-6, f"{name}: cells RTP {cells_rtp} != LUT {lut_rtp}"
        assert n_books == 2 ** n, f"{name}: {n_books} books != 2**{n}"
        assert RTP_FLOOR - 1e-9 <= lut_rtp <= RTP_CEIL + 1e-9, (
            f"{name}: RTP {lut_rtp} outside [{RTP_FLOOR}, {RTP_CEIL}]"
        )

        shelf = by_name.get(name, {})
        modes[name] = {
            "rows": n,
            "difficulty": difficulty,
            "cells": cells,                        # raw multiplier per bin
            "binWeights": bin_weights,             # C(N,k)/2**N
            "rtp": round(lut_rtp, 6),
            "edge": max(cells),                    # corner multiplier = maxWin (base product)
            "maxWin": shelf.get("maxWin", max(cells)),
            "cost": shelf.get("cost", 1.0),
        }

    rtps = [m["rtp"] for m in modes.values()]
    bundle = {
        "game_id": game_id,
        "rows": sorted(rows_set),
        "difficulties": [d for d in ["low", "medium", "high", "expert"] if d in diffs_set],
        "rtp": round(max(rtps), 4),
        # A real RGS sources this from the authenticate config.jurisdiction; the demo
        # passes it through so the autoplay panel can honour the kill-switch.
        "disabledAutoplay": False,
        "modes": modes,
    }
    with open(OUT_FILE, "w", encoding="UTF-8") as fh:
        json.dump(bundle, fh, indent=1)

    print(f"Wrote {OUT_FILE}")
    print(f"  modes={len(modes)}  rows={bundle['rows']}  difficulties={bundle['difficulties']}")
    print(f"  RTP range: {min(rtps) * 100:.3f}%..{max(rtps) * 100:.3f}% (Stake band 90-96.70%)")


if __name__ == "__main__":
    main()
