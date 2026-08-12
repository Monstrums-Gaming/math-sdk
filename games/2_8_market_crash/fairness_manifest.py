"""Emit a player-facing fairness manifest for Market Crash (2_8).

WHY THIS EXISTS
---------------
The Stake Engine RGS is a certified *replay* system: outcomes are pre-simulated and the
books / lookup-tables are hash-frozen at publish time (see the repo CLAUDE.md and
docs/rgs_docs/RGS.md). That precludes classic per-round "provably fair" (client seed +
server seed + nonce), because no randomness is drawn at bet time to verify.

What we CAN offer is a *transparency layer* with two parts, and Market Crash is the first
game in this repo where the second part has real content:

  1. ODDS INTEGRITY — a public commitment to the exact odds files that were published, so
     a player can independently confirm the served odds equal the published commitment.
  2. THE CRASH LAW — the rug multiplier is certified in the book (not synthesized by the
     client), drawn from `P(crash >= x) = RTP / x`. Read that law at a mode's SELL AT
     target and you get *exactly* that mode's published win probability. So the two claims
     a player cares about — "what are my odds" and "was that rug fair" — are the same
     number, and a player can check it themselves by counting crash points in the served
     books file.

The build already computes the needed sha256 digests into ``library/configs/config.json``
(``bookShelfConfig[].tables[].sha256`` for each lookup table and
``bookShelfConfig[].booksFile.sha256`` for each books file). This script distils those
into a compact, self-contained ``fairness.json`` that the frontend bundles and renders on
its Fairness page.

The manifest is a transparency artifact, NOT an RGS input: it is deliberately not one of
the three uploaded publish files (index.json, books_*.jsonl.zst, lookUpTable_*.csv).

USAGE
-----
    PYTHONPATH="$PWD" ./env/bin/python games/2_8_market_crash/fairness_manifest.py

Reads:  library/configs/config.json  (+ publish_files/index.json for the cost/file mapping
        the RGS actually serves)
Writes: library/publish_files/fairness.json

Run it after a build (``run.py``) that has produced config.json with hashes. It is
deterministic: same build -> same manifest.
"""

import json
import os
import re

GAME_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_JSON = os.path.join(GAME_DIR, "library", "configs", "config.json")
PUBLISH_DIR = os.path.join(GAME_DIR, "library", "publish_files")
INDEX_JSON = os.path.join(PUBLISH_DIR, "index.json")
OUT_JSON = os.path.join(PUBLISH_DIR, "fairness.json")

_MODE_RE = re.compile(r"^crash_(\d+)$")

# Human explanation shipped inside the manifest so the frontend never hard-codes a
# fairness claim that could drift from what the platform actually does.
FAIRNESS_MODEL = (
    "Outcomes on the Stake Engine RGS are pre-simulated and the odds files (lookup tables "
    "and books) are hash-frozen when the game is published; they cannot change at bet "
    "time. This manifest publishes the SHA-256 of every odds file so you can confirm the "
    "odds served to you are exactly the ones that were certified and published. It "
    "verifies odds integrity for the whole game, not an individual round."
)

CRASH_LAW = {
    "survival": "P(crash >= x) = RTP / x",
    "unit": "integer hundredths (250 = 2.50x)",
    "claim": (
        "Every round's crash point is stored in the book, not invented by the game "
        "client, and the animation is obliged to land on it. It is drawn from the "
        "survival law above, so the win chance quoted for a SELL AT target is exactly "
        "that law read at that target: win chance = RTP / target."
    ),
    "consistency": (
        "A round wins if and only if the crash point reached the SELL AT target: "
        "crashPoint >= target on a win, crashPoint < target on a loss. A crash point of "
        "1.00x is an instant rug."
    ),
    "howToVerify": (
        "Decompress the served books_<mode>.jsonl.zst and count the books whose "
        "crashRound.crashPoint is greater than or equal to crashRound.target. That count "
        "must equal winningBooks below, and dividing it by totalBooks must reproduce the "
        "published win chance."
    ),
    "displayCap": (
        "Crash points are capped for display at 200x the mode's target (and never above "
        "10,000x). The payout is unaffected — a round pays its target, never the crash "
        "point."
    ),
}


def _mode_meta(name):
    """Derive the SELL AT target from a ``crash_<cents>`` mode name.

    The target is encoded as integer cents so the mode name stays dot-free (the ACP
    publisher parses ``<mode>`` out of ``books_<mode>.jsonl.zst``, where a "." would
    collide with the extension).
    """
    match = _MODE_RE.match(name)
    if match is None:
        raise SystemExit(f"unexpected mode name {name!r}: expected crash_<cents>")
    cents = int(match.group(1))
    return cents, round(cents / 100, 2)


def _read_lut(lut_path):
    """Read the authoritative odds straight from the published lookup table.

    LUT rows are ``book_id,weight,payout_cents``. The win multiplier is the largest payout
    / 100; the exact win probability is the summed weight of the winning (payout > 0) rows
    over the total weight. These come from the same file whose sha256 is committed, so the
    manifest is internally consistent with the artifact a player re-hashes.

    Reading the multiplier from the LUT rather than from ``maxWin`` is load-bearing here:
    every Market Crash mode carries the GLOBAL 100x cap as its maxWin, so maxWin says
    nothing about an individual rung's payout.
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

    # index.json is the file the RGS serves; use it to confirm the file names / cost per
    # mode line up with the hashed files in config.json.
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
        target_cents, target = _mode_meta(name)
        lut_file = entry["tables"][0]["file"]
        lut = _read_lut(os.path.join(PUBLISH_DIR, lut_file))
        multiplier = lut["multiplier"]
        # The payout IS the target: a Market Crash mode pays the multiplier it is named
        # for. If these ever disagree, the manifest would advertise odds for a target the
        # LUT does not pay.
        if lut["payoutCents"] != target_cents:
            raise SystemExit(
                f"{name}: LUT pays {lut['payoutCents']} cents but the mode name says "
                f"{target_cents} — the manifest would misstate the payout."
            )
        rtp_pct = round(entry["rtp"] * 100, 2)
        rtps.append(rtp_pct)
        max_multiplier = max(max_multiplier, multiplier)
        win_chance = lut["winWeight"] / lut["totalWeight"]
        modes.append(
            {
                "name": name,
                "sellAt": target,
                "sellAtCents": target_cents,
                "multiplier": multiplier,
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

    modes.sort(key=lambda m: m["sellAtCents"])

    manifest = {
        "schema": "monstrums.fairness/v1",
        "gameID": config["gameID"],
        "gameName": "Market Crash",
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
        "crashLaw": CRASH_LAW,
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
