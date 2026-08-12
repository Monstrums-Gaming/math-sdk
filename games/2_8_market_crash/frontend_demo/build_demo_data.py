#!/usr/bin/env python3
"""
Build the frontend-demo data bundle for Market Crash (2_8) from the REAL generated math
output, so the browser demo replays the published lookup table instead of faking outcomes
client-side.

Reads the game's published library:
    library/publish_files/index.json                 -> the modes + their LUTs
    library/publish_files/lookUpTable_<mode>_0.csv    -> the win/lose distribution
    library/publish_files/books_<mode>.jsonl.zst      -> REAL certified crash points
    library/configs/event_config_<mode>.json          -> the per-mode event template

Each `crash_<cents>` mode is one SELL AT win/lose bet (two payouts: the target multiplier
or 0). Unlike 2_7_prediction_market's demo — which synthesizes its chart from isWin alone —
this bundle also ships a SAMPLE OF REAL crashPoints per mode and outcome, so the demo's
chart animates certified rug values rather than resampling the law in JavaScript.

Emits one file the demo fetches:
    frontend_demo/market_crash_rgs.json
      { game_id, rtp, defaultMode, ladder, modes: { "crash_<cents>": {
          target, multiplier, winChance, rtp, totalWeight,
          outcomes: [{payoutCents, weight} x2],
          crashPoints: { win: [...], lose: [...] } } } }

Re-run after any math rebuild:
    PYTHONPATH="$(pwd)" env/bin/python games/2_8_market_crash/frontend_demo/build_demo_data.py
"""

import csv
import io
import json
import os
import random
import re

import zstandard as zstd

RTP_FLOOR, RTP_CEIL = 0.9615, 0.9665
ACP_CEIL = 0.967
DEFAULT_MODE = "crash_200"

# How many real crash points to ship per mode per outcome. Enough that the demo never
# visibly repeats, small enough to keep the bundle a reasonable download.
SAMPLE_PER_OUTCOME = 300
# Fixed seed: the bundle must be reproducible, like every other build artifact.
SAMPLE_SEED = 20260806

HERE = os.path.dirname(os.path.abspath(__file__))
LIBRARY = os.path.join(HERE, "..", "library")
PUBLISH = os.path.join(LIBRARY, "publish_files")
CONFIGS = os.path.join(LIBRARY, "configs")
OUT_FILE = os.path.join(HERE, "market_crash_rgs.json")

_MODE_RE = re.compile(r"^crash_(\d+)$")


def _read_lut(path):
    """Return (win_payout_cents, win_rows, loss_rows) for a win/lose lookup table."""
    payout_rows = {}
    with open(path, newline="", encoding="UTF-8") as fh:
        for _sim, weight, payout in csv.reader(fh):
            assert float(weight) == 1, f"{os.path.basename(path)}: non-uniform weight"
            p = int(payout)
            payout_rows[p] = payout_rows.get(p, 0) + 1
    payouts = set(payout_rows)
    assert payouts <= {0} | {max(payouts)}, (
        f"{os.path.basename(path)}: expected {{0, win}}, got {sorted(payouts)}"
    )
    win_payout = max(payouts)
    assert win_payout > 0, f"{os.path.basename(path)}: no winning payout"
    return win_payout, payout_rows[win_payout], payout_rows.get(0, 0)


def _read_crash_points(mode, target_cents):
    """Collect the real crashPoints from the published books, split by outcome.

    Also re-asserts the honesty invariant here, so the demo bundle can never ship a rug
    value that contradicts its own outcome (a crashPoint below the target on a win would
    render a chart that visibly never reaches the SELL AT line yet pays).
    """
    path = os.path.join(PUBLISH, f"books_{mode}.jsonl.zst")
    win, lose = [], []
    with open(path, "rb") as fh:
        with zstd.ZstdDecompressor().stream_reader(fh) as reader:
            for line in io.TextIOWrapper(reader, encoding="utf-8"):
                if not line.strip():
                    continue
                book = json.loads(line)
                ev = book["events"][0]
                assert ev["type"] == "crashRound", f"{mode}: first event {ev['type']}"
                cp = ev["crashPoint"]
                is_win = book["payoutMultiplier"] > 0
                assert (cp >= target_cents) == is_win, (
                    f"{mode} book {book['id']}: crashPoint {cp} contradicts the payout"
                )
                (win if is_win else lose).append(cp)
    return win, lose


def _sample(values, rng):
    """A reproducible, sorted-input-independent sample of at most SAMPLE_PER_OUTCOME."""
    if len(values) <= SAMPLE_PER_OUTCOME:
        return sorted(values)
    return sorted(rng.sample(values, SAMPLE_PER_OUTCOME))


def main():
    index = json.load(open(os.path.join(PUBLISH, "index.json"), encoding="UTF-8"))
    cfg = json.load(open(os.path.join(CONFIGS, "config.json"), encoding="UTF-8"))
    game_id = cfg.get("gameID", "2_8_market_crash")
    rng = random.Random(SAMPLE_SEED)

    modes = {}
    for entry in index["modes"]:
        name = entry["name"]
        match = _MODE_RE.match(name)
        assert match, f"mode {name!r} is not crash_<cents> — the demo parses the target out of it"
        target_cents = int(match.group(1))

        win_payout, win_rows, loss_rows = _read_lut(os.path.join(PUBLISH, entry["weights"]))
        total = win_rows + loss_rows
        assert win_payout == target_cents, (
            f"{name}: LUT pays {win_payout} but the mode name says {target_cents}"
        )

        ev = json.load(
            open(os.path.join(CONFIGS, f"event_config_{name}.json"), encoding="UTF-8")
        )["crashRound"]
        multiplier = ev["payoutMultiplier"] / 100.0
        assert round(multiplier * 100) == win_payout, f"{name}: event mult != LUT payout"
        assert ev["target"] == target_cents, f"{name}: event target != mode name"
        rtp_mode = round((win_rows / total) * multiplier, 6)
        assert RTP_FLOOR - 1e-9 <= rtp_mode <= RTP_CEIL + 1e-9, f"{name}: RTP {rtp_mode} out of band"

        win_cps, lose_cps = _read_crash_points(name, target_cents)
        assert len(win_cps) == win_rows, f"{name}: {len(win_cps)} win crashPoints != {win_rows}"
        assert len(lose_cps) == loss_rows, f"{name}: lose crashPoint count off"

        modes[name] = {
            "target": multiplier,
            "targetCents": target_cents,
            "multiplier": multiplier,
            "winChance": round(win_rows / total, 6),
            "rtp": rtp_mode,
            "totalWeight": total,
            "outcomes": [
                {"payoutCents": win_payout, "weight": win_rows},
                {"payoutCents": 0, "weight": loss_rows},
            ],
            # Real certified values, sampled reproducibly. The demo picks an outcome from
            # the LUT weights, then a crash point from the matching list, so what it draws
            # on screen is always a rug the RGS could genuinely have served.
            "crashPoints": {
                "win": _sample(win_cps, rng),
                "lose": _sample(lose_cps, rng),
            },
        }

    ladder = sorted(m["targetCents"] for m in modes.values())
    default_name = DEFAULT_MODE if DEFAULT_MODE in modes else f"crash_{ladder[0]}"
    default = modes[default_name]
    rtps = [m["rtp"] for m in modes.values()]

    bundle = {
        "game_id": game_id,
        "rtp": round(default["rtp"], 4),
        "rtpMin": min(rtps),
        "rtpMax": max(rtps),
        "maxWin": max(m["multiplier"] for m in modes.values()),
        "target": default["target"],
        "winChance": default["winChance"],
        "defaultMode": default_name,
        "disabledAutoplay": False,
        "ladder": ladder,
        "crashLaw": {
            "survival": "rtp / x",
            "note": (
                "crashPoint is certified in the book: >= target on a win, < target on a "
                "loss. The win chance for a SELL AT target is this law read at that target."
            ),
        },
        "modes": modes,
    }
    with open(OUT_FILE, "w", encoding="UTF-8") as fh:
        json.dump(bundle, fh, indent=1)

    print(f"Wrote {OUT_FILE}  (default mode: {default_name}, {len(modes)} modes)")
    for name in (f"crash_{c}" for c in ladder):
        m = modes[name]
        flag = "  <-- exceeds ACP ceiling" if m["rtp"] > ACP_CEIL + 1e-9 else ""
        print(
            f"  {name}: {m['multiplier']}x  winChance={m['winChance']}  rtp={m['rtp']}  "
            f"books={m['totalWeight']}  cp={len(m['crashPoints']['win'])}w/"
            f"{len(m['crashPoints']['lose'])}l{flag}"
        )


if __name__ == "__main__":
    main()
