#!/usr/bin/env python3
"""
Build the frontend data bundle for Trading Roulette (2_9) from the REAL generated math
output, so the web app's offline mock replays the published lookup table instead of
faking outcomes client-side.

Reads the game's published library:
    library/publish_files/index.json                 -> the modes + their LUTs
    library/publish_files/lookUpTable_<mode>_0.csv    -> the win/lose distribution
    library/publish_files/books_<mode>.jsonl.zst      -> REAL certified landing rows
    library/odds_bundle.json                          -> the board (zones, land weights)

Each `zone_<id>` mode is one board-cell win/lose bet (two payouts: the cell multiplier or
0). Like 2_8_market_crash's bundle this also ships a SAMPLE OF REAL landRows per mode and
outcome, so the offline mock animates certified landings rather than resampling the law
in JavaScript.

Emits one file the web app copies into src/assets/:
    frontend_demo/trading_roulette_rgs.json
      { game_id, rtp, defaultMode, board, modes: { "zone_<id>": {
          zone, rows, multiplier, winChance, rtp, totalWeight,
          outcomes: [{payoutCents, weight} x2],
          landRows: { win: [...], lose: [...] } } } }

Re-run after any math rebuild:
    PYTHONPATH="$(pwd)" env/bin/python games/2_9_trading_roulette/frontend_demo/build_demo_data.py
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
DEFAULT_MODE = "zone_half_o"

# How many real landing rows to ship per mode per outcome. Rows are small integers, so
# unlike 2_8's crashPoints the value diversity is bounded — the sample's job is carrying
# the CONDITIONAL FREQUENCIES, so the mock reproduces the published law by construction.
SAMPLE_PER_OUTCOME = 300
# Fixed seed: the bundle must be reproducible, like every other build artifact.
SAMPLE_SEED = 20260811

HERE = os.path.dirname(os.path.abspath(__file__))
LIBRARY = os.path.join(HERE, "..", "library")
PUBLISH = os.path.join(LIBRARY, "publish_files")
ODDS_BUNDLE = os.path.join(LIBRARY, "odds_bundle.json")
OUT_FILE = os.path.join(HERE, "trading_roulette_rgs.json")

_MODE_RE = re.compile(r"^zone_([a-z0-9_]+)$")


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


def _read_land_rows(mode, zone_rows):
    """Collect the real landRows from the published books, split by outcome.

    Also re-asserts the honesty invariant here, so the bundle can never ship a landing
    that contradicts its own outcome (a row inside the zone on a loss would render a
    chart that visibly lands in the bet cell yet pays nothing).
    """
    zone = set(zone_rows)
    path = os.path.join(PUBLISH, f"books_{mode}.jsonl.zst")
    win, lose = [], []
    with open(path, "rb") as fh:
        with zstd.ZstdDecompressor().stream_reader(fh) as reader:
            for line in io.TextIOWrapper(reader, encoding="utf-8"):
                if not line.strip():
                    continue
                book = json.loads(line)
                ev = book["events"][0]
                assert ev["type"] == "zoneRound", f"{mode}: first event {ev['type']}"
                lr = ev["landRow"]
                is_win = book["payoutMultiplier"] > 0
                assert (lr in zone) == is_win, (
                    f"{mode} book {book['id']}: landRow {lr} contradicts the payout"
                )
                (win if is_win else lose).append(lr)
    return win, lose


def _sample(values, rng):
    """A reproducible sample of at most SAMPLE_PER_OUTCOME, preserving frequencies."""
    if len(values) <= SAMPLE_PER_OUTCOME:
        return sorted(values)
    return sorted(rng.sample(values, SAMPLE_PER_OUTCOME))


def main():
    index = json.load(open(os.path.join(PUBLISH, "index.json"), encoding="UTF-8"))
    odds = json.load(open(ODDS_BUNDLE, encoding="UTF-8"))
    game_id = odds["game_id"]
    rng = random.Random(SAMPLE_SEED)

    modes = {}
    for entry in index["modes"]:
        name = entry["name"]
        match = _MODE_RE.match(name)
        assert match, f"mode {name!r} is not zone_<id> — the frontend parses the cell out of it"
        bundle_mode = odds["modes"][name]
        zone_rows = bundle_mode["rows"]
        cents = bundle_mode["multiplierCents"]

        win_payout, win_rows, loss_rows = _read_lut(os.path.join(PUBLISH, entry["weights"]))
        total = win_rows + loss_rows
        assert win_payout == cents, f"{name}: LUT pays {win_payout} but the cell says {cents}"

        multiplier = cents / 100.0
        rtp_mode = round((win_rows / total) * multiplier, 6)
        assert RTP_FLOOR - 1e-9 <= rtp_mode <= RTP_CEIL + 1e-9, f"{name}: RTP {rtp_mode} out of band"

        win_lrs, lose_lrs = _read_land_rows(name, zone_rows)
        assert len(win_lrs) == win_rows, f"{name}: {len(win_lrs)} win landRows != {win_rows}"
        assert len(lose_lrs) == loss_rows, f"{name}: lose landRow count off"

        modes[name] = {
            "zone": match.group(1),
            "rows": zone_rows,
            "multiplier": multiplier,
            "multiplierCents": cents,
            "winChance": round(win_rows / total, 6),
            "rtp": rtp_mode,
            "totalWeight": total,
            "outcomes": [
                {"payoutCents": cents, "weight": win_rows},
                {"payoutCents": 0, "weight": loss_rows},
            ],
            # Real certified values, sampled reproducibly. The mock picks an outcome from
            # the LUT weights, then a landing row from the matching list, so what it draws
            # on screen is always a landing the RGS could genuinely have served.
            "landRows": {
                "win": _sample(win_lrs, rng),
                "lose": _sample(lose_lrs, rng),
            },
        }

    default_name = DEFAULT_MODE if DEFAULT_MODE in modes else sorted(modes)[0]
    default = modes[default_name]
    rtps = [m["rtp"] for m in modes.values()]

    bundle = {
        "game_id": game_id,
        "rtp": round(default["rtp"], 4),
        "rtpMin": min(rtps),
        "rtpMax": max(rtps),
        "maxWin": max(m["multiplier"] for m in modes.values()),
        "winChance": default["winChance"],
        "defaultMode": default_name,
        "disabledAutoplay": False,
        "board": odds["board"],
        "landingLaw": odds["landingLaw"],
        "modes": modes,
    }
    with open(OUT_FILE, "w", encoding="UTF-8") as fh:
        json.dump(bundle, fh, indent=1)

    print(f"Wrote {OUT_FILE}  (default mode: {default_name}, {len(modes)} modes)")
    for name in sorted(modes):
        m = modes[name]
        flag = "  <-- exceeds ACP ceiling" if m["rtp"] > ACP_CEIL + 1e-9 else ""
        print(
            f"  {name}: {m['multiplier']}x rows={m['rows']}  winChance={m['winChance']}  "
            f"rtp={m['rtp']}  books={m['totalWeight']}  lr={len(m['landRows']['win'])}w/"
            f"{len(m['landRows']['lose'])}l{flag}"
        )


if __name__ == "__main__":
    main()
