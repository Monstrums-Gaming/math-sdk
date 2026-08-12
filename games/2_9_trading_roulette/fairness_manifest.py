"""Emit a player-facing fairness manifest for Trading Roulette (2_9).

WHY THIS EXISTS
---------------
The Stake Engine RGS is a certified *replay* system: outcomes are pre-simulated and the
books / lookup-tables are hash-frozen at publish time. That precludes classic per-round
"provably fair" (client seed + server seed + nonce), because no randomness is drawn at
bet time to verify.

What we CAN offer is a *transparency layer* (the 2_8_market_crash pattern):

  1. ODDS INTEGRITY — a public commitment to the exact odds files that were published, so
     a player can independently confirm the served odds equal the published commitment.
  2. THE LANDING LAW — the landing row is certified in the book (not synthesized by the
     client): inside the bet's zone on a win, outside it on a loss, drawn from published
     integer weights conditional on the verdict. Unlike 2_8's crash law there is no single
     unconditional law whose readout IS the odds — the board quotes per-cell bookmaker
     odds (they cannot form one coherent wheel) — so the manifest states the precise,
     checkable claim instead: the verdict counts in the served books reproduce the
     published win chance, and the row never contradicts the payout.

The build already computes the needed sha256 digests into ``library/configs/config.json``.
This script distils those into a compact ``fairness.json`` the frontend bundles and
renders on its Fairness page. It is a transparency artifact, NOT an RGS input.

USAGE
-----
    PYTHONPATH="$PWD" ./env/bin/python games/2_9_trading_roulette/fairness_manifest.py

Reads:  library/configs/config.json  (+ publish_files/index.json for the cost/file mapping)
Writes: library/publish_files/fairness.json
"""

import json
import os
import re
import sys

GAME_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_JSON = os.path.join(GAME_DIR, "library", "configs", "config.json")
PUBLISH_DIR = os.path.join(GAME_DIR, "library", "publish_files")
INDEX_JSON = os.path.join(PUBLISH_DIR, "index.json")
OUT_JSON = os.path.join(PUBLISH_DIR, "fairness.json")

sys.path.insert(0, GAME_DIR)
from game_config import GameConfig, LAND_WEIGHTS, ROWS  # noqa: E402

_MODE_RE = re.compile(r"^zone_([a-z0-9_]+)$")

FAIRNESS_MODEL = (
    "Outcomes on the Stake Engine RGS are pre-simulated and the odds files (lookup tables "
    "and books) are hash-frozen when the game is published; they cannot change at bet "
    "time. This manifest publishes the SHA-256 of every odds file so you can confirm the "
    "odds served to you are exactly the ones that were certified and published. It "
    "verifies odds integrity for the whole game, not an individual round."
)

LANDING_LAW = {
    "unit": "signed integer row: 0 on the line, +1..+6 over, -1..-6 under, +/-7 off-scale",
    "weights": {str(r): LAND_WEIGHTS[abs(r)] for r in ROWS},
    "claim": (
        "Every round's landing row is stored in the book, not invented by the game "
        "client, and the chart animation is obliged to land the line in that row. It is "
        "drawn from the published integer weights above, conditional on the round's "
        "verdict: restricted to your cell's rows on a win, to the other rows on a loss."
    ),
    "consistency": (
        "A round wins if and only if the landing row is inside the bet cell's zone: "
        "landRow in zone on a win, outside it on a loss — no exceptions."
    ),
    "oddsAreNotOneWheel": (
        "The board quotes per-cell bookmaker odds. Those quoted odds cannot form a single "
        "landing distribution (their implied probabilities do not sum to one), so each "
        "cell's win chance is certified independently by its own lookup table, and the "
        "row frequencies you observe while betting a cell are the mixture of the two "
        "conditional laws above at that cell's published win chance."
    ),
    "howToVerify": (
        "Decompress the served books_<mode>.jsonl.zst and count the books whose "
        "zoneRound.landRow falls inside that cell's rows. That count must equal "
        "winningBooks below, and dividing it by totalBooks must reproduce the published "
        "win chance."
    ),
}


def _read_lut(lut_path):
    """Read the authoritative odds straight from the published lookup table.

    LUT rows are ``book_id,weight,payout_cents``. Reading the multiplier from the LUT
    rather than from ``maxWin`` is load-bearing: every Trading Roulette mode carries the
    GLOBAL 21x cap as its maxWin, so maxWin says nothing about an individual cell.
    """
    win_weight = 0
    total_weight = 0
    max_payout_cents = 0
    with open(lut_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            _, weight, payout_cents = line.split(",")
            weight = int(weight)
            payout_cents = int(payout_cents)
            total_weight += weight
            if payout_cents > 0:
                win_weight += weight
                max_payout_cents = max(max_payout_cents, payout_cents)
    return {
        "multiplier": round(max_payout_cents / 100, 2),
        "payoutCents": max_payout_cents,
        "winWeight": win_weight,
        "totalWeight": total_weight,
    }


def build_manifest():
    with open(CONFIG_JSON, "r", encoding="utf-8") as f:
        config = json.load(f)

    game_config = GameConfig()
    zone_meta = {p["zone_id"]: p for p in game_config.mode_params.values()}

    index_costs = {}
    if os.path.exists(INDEX_JSON):
        with open(INDEX_JSON, "r", encoding="utf-8") as f:
            index = json.load(f)
        index_costs = {m["name"]: m.get("cost") for m in index.get("modes", [])}

    modes = []
    rtps = []
    max_multiplier = 0.0
    for entry in config["bookShelfConfig"]:
        name = entry["name"]
        match = _MODE_RE.match(name)
        if match is None:
            raise SystemExit(f"unexpected mode name {name!r}: expected zone_<id>")
        zone_id = match.group(1)
        meta = zone_meta.get(zone_id)
        if meta is None:
            raise SystemExit(f"{name}: no such cell in GameConfig")

        lut_file = entry["tables"][0]["file"]
        lut = _read_lut(os.path.join(PUBLISH_DIR, lut_file))
        # The payout IS the cell's multiplier. If these ever disagree, the manifest would
        # advertise odds for a cell the LUT does not pay.
        if lut["payoutCents"] != meta["payout_cents"]:
            raise SystemExit(
                f"{name}: LUT pays {lut['payoutCents']} cents but the cell says "
                f"{meta['payout_cents']} — the manifest would misstate the payout."
            )
        rtp_pct = round(entry["rtp"] * 100, 2)
        rtps.append(rtp_pct)
        max_multiplier = max(max_multiplier, lut["multiplier"])
        win_chance = lut["winWeight"] / lut["totalWeight"]
        modes.append(
            {
                "name": name,
                "zone": zone_id,
                "rows": list(meta["zone_rows"]),
                "multiplier": lut["multiplier"],
                "winChance": round(win_chance * 100, 4),
                "rtp": rtp_pct,
                "cost": index_costs.get(name, entry.get("cost")),
                "odds": {
                    "winningBooks": lut["winWeight"],
                    "totalBooks": lut["totalWeight"],
                },
                "lookupTable": {
                    "file": lut_file,
                    "sha256": entry["tables"][0]["sha256"],
                },
                "booksFile": {
                    "file": entry["booksFile"]["file"],
                    "sha256": entry["booksFile"]["sha256"],
                },
            }
        )

    modes.sort(key=lambda m: (m["multiplier"], m["zone"]))

    manifest = {
        "schema": "monstrums.fairness/v1",
        "gameID": config["gameID"],
        "gameName": "Trading Roulette",
        "fairnessModel": "certified-replay",
        "description": FAIRNESS_MODEL,
        "verification": {
            "algorithm": "SHA-256",
            "how": (
                "For any mode, fetch the served lookUpTable_<mode>_0.csv (or "
                "books_<mode>.jsonl.zst) and compute its SHA-256; it must equal the value "
                "below. In a browser: crypto.subtle.digest('SHA-256', bytes). Offline: "
                "sha256sum <file>."
            ),
        },
        "landingLaw": LANDING_LAW,
        "rtp": {
            "overall": round(config["rtp"], 2),
            "minMode": min(rtps) if rtps else None,
            "maxMode": max(rtps) if rtps else None,
        },
        "maxMultiplier": max_multiplier,
        "modeCount": len(modes),
        "modes": modes,
    }
    return manifest


def main():
    if not os.path.exists(CONFIG_JSON):
        raise SystemExit(
            f"config.json not found at {CONFIG_JSON}\n"
            "Run the game build (run.py) first so hashes are generated."
        )
    manifest = build_manifest()
    os.makedirs(PUBLISH_DIR, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")
    print(f"Wrote {OUT_JSON}")
    print(
        f"  gameID={manifest['gameID']}  modes={manifest['modeCount']}  "
        f"RTP {manifest['rtp']['minMode']}-{manifest['rtp']['maxMode']}%  "
        f"maxMult={manifest['maxMultiplier']}x"
    )


if __name__ == "__main__":
    main()
