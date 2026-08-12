"""Emit a player-facing fairness manifest for Porkageddon (2_0).

WHY THIS EXISTS
---------------
The Stake Engine RGS is a certified *replay* system: outcomes are pre-simulated
and the books / lookup-tables are hash-frozen at publish time (see the repo
CLAUDE.md and docs/rgs_docs/RGS.md). That precludes classic per-round
"provably fair" (client seed + server seed + nonce), because no randomness is
drawn at bet time to verify — the platform's seed pair selects WHICH pre-generated
book the RGS serves, and that book already contains the whole battle.

What we CAN offer is a *transparency layer*: a public commitment to the exact odds
files that were published, so a player can independently confirm the served odds
equal the published commitment (odds INTEGRITY, not each round).

The build already computes the needed sha256 digests into
``library/configs/config.json`` (``bookShelfConfig[].tables[].sha256`` for each
lookup table and ``bookShelfConfig[].booksFile.sha256`` for each books file).
This script distills those into a compact, self-contained ``fairness.json`` that
the frontend bundles and renders on its Fairness page.

The manifest is a transparency artifact, NOT an RGS input: it is deliberately kept
OUT of the three uploaded publish files (index.json, books_*.jsonl.zst,
lookUpTable_*.csv), exactly like the readable events sample.

USAGE
-----
    python games/2_0_porkageddon/fairness_manifest.py

Reads:  library/configs/config.json  (+ publish_files/index.json for the cost/
        file mapping the RGS actually serves)
Writes: library/publish_files/fairness.json

Run it after a build (``run.py``) that has produced config.json with hashes.
It is deterministic: same build -> same manifest.
"""

import json
import os

import pork_math as pm

GAME_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_JSON = os.path.join(GAME_DIR, "library", "configs", "config.json")
PUBLISH_DIR = os.path.join(GAME_DIR, "library", "publish_files")
INDEX_JSON = os.path.join(PUBLISH_DIR, "index.json")
OUT_JSON = os.path.join(PUBLISH_DIR, "fairness.json")

# Human explanation shipped inside the manifest so the frontend never hard-codes a
# fairness claim that could drift from what the platform actually does.
FAIRNESS_MODEL = (
    "Outcomes on the Stake Engine RGS are pre-simulated and the odds files "
    "(lookup tables and books) are hash-frozen when the game is published; they "
    "cannot change at bet time. This manifest publishes the SHA-256 of every "
    "odds file so you can confirm the odds served to you are exactly the ones "
    "that were certified and published. It verifies odds integrity for the whole "
    "game, not an individual battle."
)

# Every fighter draws from the same per-stance book pool, so this is a fact about
# the published files rather than a claim — worth stating plainly.
ROSTER_FAIRNESS = (
    "Books are fighter-neutral: a stance publishes one book set addressed by skill "
    "slot, so every fighter has mathematically identical odds. Fighter choice "
    "changes pacing and presentation only."
)


def _stance_meta(name):
    """Stance metadata for the manifest, read from the authored tables."""
    stance = pm.STANCES[name]
    return {
        "label": stance["label"],
        "roundRange": [min(stance["rounds"]), max(stance["rounds"])],
        "skillCostRange": [
            min(c for c, *_ in stance["slots"]) / 100.0,
            max(c for c, *_ in stance["slots"]) / 100.0,
        ],
        "goldenPigChance": float(stance["golden_freq"]),
        "goldenTiers": [
            {
                "tier": tier,
                "poolMultiplier": mult,
                "pays": pm.golden_cents(mult) / 100.0,
                "weightWithinGolden": float(weight),
                "oneInBattles": round(1 / float(stance["golden_freq"] * weight)),
            }
            for tier, mult, weight in stance["golden_tiers"]
        ],
    }


def _read_lut(lut_path):
    """Read the authoritative odds straight from the published lookup table.

    LUT rows are ``book_id,weight,payout_cents``. These come from the same file
    whose sha256 is committed, so the manifest is internally consistent with the
    artifact a player re-hashes.
    """
    win_weight = 0
    total_weight = 0
    payouts = {}
    with open(lut_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            _book_id, weight, payout_cents = line.split(",")
            weight = int(weight)
            payout_cents = int(payout_cents)
            total_weight += weight
            payouts[payout_cents] = payouts.get(payout_cents, 0) + weight
            if payout_cents > 0:
                win_weight += weight
    return {
        "multiplier": round(max(payouts) / 100, 2),
        "winWeight": win_weight,
        "totalWeight": total_weight,
        # The full published paytable: every payout a player can be dealt, and how
        # many of the mode's books pay it.
        "payTable": [
            {"multiplier": cents / 100.0, "books": books}
            for cents, books in sorted(payouts.items())
            if cents > 0
        ],
    }


def build_manifest():
    with open(CONFIG_JSON, "r", encoding="utf-8") as f:
        config = json.load(f)

    # index.json is the file the RGS serves; use it to confirm the file names /
    # cost per mode line up with the hashed files in config.json.
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
        lut_file = entry["tables"][0]["file"]
        # Read the true top multiplier + odds from the hashed LUT itself, not from
        # maxWin (which is declared metadata).
        lut = _read_lut(os.path.join(PUBLISH_DIR, lut_file))
        rtp_pct = round(entry["rtp"] * 100, 2)
        rtps.append(rtp_pct)
        max_multiplier = max(max_multiplier, lut["multiplier"])
        modes.append(
            {
                "name": name,
                **_stance_meta(name),
                "maxMultiplier": lut["multiplier"],
                "rtp": rtp_pct,
                "cost": index_costs.get(name, entry.get("cost")),
                "odds": {
                    "winningBooks": lut["winWeight"],
                    "totalBooks": lut["totalWeight"],
                    "winChance": round(lut["winWeight"] / lut["totalWeight"], 6),
                },
                "payTable": lut["payTable"],
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

    modes.sort(key=lambda m: pm.STANCES[m["name"]]["order"])

    return {
        "schema": "monstrums.fairness/v1",
        "gameID": config["gameID"],
        "gameName": "Porkageddon",
        "fairnessModel": "certified-replay",
        "description": FAIRNESS_MODEL,
        "rosterFairness": ROSTER_FAIRNESS,
        "verification": {
            "algorithm": "SHA-256",
            "how": (
                "For any mode, fetch the served lookUpTable_<mode>_0.csv (or "
                "books_<mode>.jsonl.zst) and compute its SHA-256; it must equal "
                "the value below. In a browser: crypto.subtle.digest('SHA-256', "
                "bytes). Offline: sha256sum <file>."
            ),
        },
        "rtp": {
            "overall": round(config["rtp"], 2),
            "minMode": min(rtps) if rtps else None,
            "maxMode": max(rtps) if rtps else None,
        },
        "maxMultiplier": max_multiplier,
        "modeCount": len(modes),
        "modes": modes,
    }


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
