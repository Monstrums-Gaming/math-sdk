#!/usr/bin/env python3
"""
Build the frontend-demo data bundle for Crypto Pulse (2_9) from the REAL generated
math output, so the browser demo replays the published lookup table instead of
faking outcomes client-side.

Reads the game's published library:
    library/publish_files/index.json                -> the modes + their LUTs
    library/publish_files/lookUpTable_<mode>_0.csv   -> the win/lose distribution
    library/configs/event_config_<mode>.json         -> the per-mode event template

The single `base` mode is one win/lose call (two payouts: the offered multiplier or
0). Emits ONE file the demo fetches:
    frontend_demo/crypto_pulse_rgs.json  { game_id, rtp, multiplier, winChance,
      modes:{ "base": { multiplier, winChance, rtp, outcomes:[{payoutCents,weight}x2] }}}

Re-run after any math rebuild:
    PYTHONPATH="$(pwd)" env/bin/python games/2_9_crypto_pulse/frontend_demo/build_demo_data.py
"""

import csv
import json
import os

RTP_FLOOR, RTP_CEIL = 0.90, 0.98
ACP_CEIL = 0.967

HERE = os.path.dirname(os.path.abspath(__file__))
LIBRARY = os.path.join(HERE, "..", "library")
PUBLISH = os.path.join(LIBRARY, "publish_files")
CONFIGS = os.path.join(LIBRARY, "configs")
OUT_FILE = os.path.join(HERE, "crypto_pulse_rgs.json")


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
    game_id = cfg.get("gameID", "2_9_crypto_pulse")

    modes = {}
    for entry in index["modes"]:
        name = entry["name"]
        win_payout, win_rows, loss_rows = _read_lut(os.path.join(PUBLISH, entry["weights"]))
        total = win_rows + loss_rows

        ev = json.load(open(os.path.join(CONFIGS, f"event_config_{name}.json"), encoding="UTF-8"))["priceCall"]
        multiplier = ev["payoutMultiplier"] / 100.0
        assert round(multiplier * 100) == win_payout, f"{name}: event mult != LUT payout"
        rtp_mode = round((win_rows / total) * multiplier, 6)
        assert RTP_FLOOR - 1e-9 <= rtp_mode <= RTP_CEIL + 1e-9, f"{name}: RTP {rtp_mode} out of band"

        modes[name] = {
            "multiplier": multiplier,
            "winChance": round(win_rows / total, 6),
            "rtp": rtp_mode,
            "totalWeight": total,
            "outcomes": [
                {"payoutCents": win_payout, "weight": win_rows},
                {"payoutCents": 0, "weight": loss_rows},
            ],
        }

    # Top-level scalars mirror a single representative (default) mode for back-compat with
    # consumers that read the flat fields. Prefer the Medium tier (call_190), then a legacy
    # single "base" mode, else the first published mode.
    default_name = next((n for n in ("call_190", "base") if n in modes), next(iter(modes)))
    default = modes[default_name]
    bundle = {
        "game_id": game_id,
        "rtp": round(default["rtp"], 4),
        "multiplier": default["multiplier"],
        "winChance": default["winChance"],
        "defaultMode": default_name,
        "disabledAutoplay": False,
        "modes": modes,
    }
    with open(OUT_FILE, "w", encoding="UTF-8") as fh:
        json.dump(bundle, fh, indent=1)

    print(f"Wrote {OUT_FILE}  (default mode: {default_name})")
    for name, m in modes.items():
        flag = "  <-- exceeds ACP ceiling" if m["rtp"] > ACP_CEIL + 1e-9 else ""
        print(f"  {name}: {m['multiplier']}x  winChance={m['winChance']}  rtp={m['rtp']}  books={m['totalWeight']}{flag}")


if __name__ == "__main__":
    main()
