#!/usr/bin/env python3
"""
Build the frontend-demo data bundle for Tap Trade (2_6) from the REAL
generated math output, so the browser demo replays the published lookup tables
instead of faking odds client-side.

Reads the verified odds bundle emitted by ../build_odds_bundle.py:
    library/odds_bundle.json

(which is itself re-verified row-by-row against library/publish_files/ — LUT weights,
winning-row counts, book events — before it is written). Emits ONE file the demo
fetches:
    frontend_demo/tap_trade_rgs.json
      { game_id, rtpMin, rtpMax, ladder:[cents...],
        modes:{ "call_<cents>": { multiplier, multiplierCents, winChance, rtp,
                                   numSims, outcomes:[{payoutCents,weight}x2] }}}

Re-run after any math rebuild:
    PYTHONPATH="$(pwd)" env/bin/python games/2_6_tap_trade/frontend_demo/build_demo_data.py
"""

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
BUNDLE = os.path.join(HERE, "..", "library", "odds_bundle.json")
OUT_FILE = os.path.join(HERE, "tap_trade_rgs.json")

RTP_FLOOR, RTP_CEIL = 0.90, 0.967


def main():
    with open(BUNDLE, encoding="UTF-8") as fh:
        bundle = json.load(fh)

    assert bundle["game_id"] == "2_6_tap_trade", f"unexpected game_id {bundle['game_id']}"
    modes = bundle["modes"]
    assert len(modes) == len(bundle["ladder"]) == 28, "expected the 28-rung ladder"

    for name, m in modes.items():
        assert name == f"call_{m['multiplierCents']}", f"mode key {name} != cents"
        assert RTP_FLOOR - 1e-9 <= m["rtp"] <= RTP_CEIL + 1e-9, f"{name}: RTP {m['rtp']} out of band"
        total = sum(o["weight"] for o in m["outcomes"])
        assert total == m["numSims"], f"{name}: outcome weights != numSims"

    with open(OUT_FILE, "w", encoding="UTF-8") as fh:
        json.dump(bundle, fh, indent=1)

    print(f"Wrote {OUT_FILE}")
    for name in sorted(modes, key=lambda n: modes[n]["multiplierCents"]):
        m = modes[name]
        print(f"  {name}: {m['multiplier']}x  winChance={m['winChance']:.6f}  rtp={m['rtp']:.4f}")


if __name__ == "__main__":
    main()
