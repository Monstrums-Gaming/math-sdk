# Chicken Crossing — frontend demo

A self-contained browser demo of the `2_7_chicken_crossing` game, wired to the **real published
RGS math**. The chicken crosses lanes; each surviving step raises a cash-out multiplier; a car ends
the round at 0. It replays the game's certified books — it does not fake outcomes client-side.

## Run

```sh
./run.sh              # serves http://localhost:7817/index.html (default)
./run.sh 3000         # custom port
```
Must be served over http:// (the page `fetch()`es `chicken_rgs.json`; `file://` won't work).

## Two auto-detected modes

| Mode | When | Outcome source |
|---|---|---|
| **LOCAL** (default) | no RGS params | weighted-pick a real published outcome from `chicken_rgs.json`, then synthesise the `crossingSetup → crossingResult → finalWin` book |
| **LIVE** | `?rgs_url=<host>&sessionID=<id>` present | `/wallet/authenticate → /wallet/play → /wallet/end-round`; the returned book is replayed |

Both paths produce an **identical `round` shape**, so one reveal path renders either. The badge next
to Balance shows LOCAL/LIVE. Optional params: `currency`, `lang`, `mode` (initial difficulty).

## Predetermined settlement (important)

The RGS is a certified **replay**: `/wallet/play` returns ONE book that fixes the whole round —
including the cash-out step. **The player cannot change the payout mid-round** (no `/bet/event`
dynamic settlement). So the demo is a *faithful replay*: Bet locks the outcome; "Go" steps the
chicken up the lanes on rails; a **win** auto-cashes exactly at the book's `cashOutStep` (paying
`ladder[cashOutStep]`), a **loss** ends with a car crash at `poppedAtStep`. "Cash Out" is not a free
choice (it lights up only at the book's cash step). This mirrors the game's `readme.txt` warning #1.

## Money conventions (LIVE)

- Wallet money (balance, bet `amount`, `round.payout`) is an integer with 6 decimals
  (`1_000_000 == 1.0`).
- Event/multiplier scale is ×100 (`finalWin.amount` cents; `payoutMultiplier` raw, e.g. `1.1`).
- Currency win = `betUnits × payoutMultiplier`. Bet levels come from the RGS `config` (snapped in
  `snapLiveBet`), not the math-sdk. In LOCAL a demo balance is tracked and bets are free-form.

## The data bundle (generated, not source)

`chicken_rgs.json` is produced from the built `library/` — regenerate after any math rebuild:

```sh
PYTHONPATH="$(pwd)" env/bin/python games/2_7_chicken_crossing/frontend_demo/build_demo_data.py
```

It reads `library/publish_files/{index.json,lookUpTable_<mode>_0.csv}` +
`library/configs/{event_config_<mode>.json,config.json}`, collapses each LUT by distinct
`payout_cents` into `outcomes:[{payoutCents, weight}]`, reads the authoritative snapped `ladder`
from the `crossingSetup` template, and **fails loudly** if a payout isn't a ladder rung or a mode's
RTP drifts out of band. Per-mode `popWeights` give the LOCAL loss a natural crash lane (cosmetic;
the loss payout is always 0). Modes: `easy/medium/hard/daredevil` (24/21/17/10 steps).

Note: the shipped bundle runs at ~97% RTP (the faithful build), which is above Stake's 96.70% ACP
ceiling — see the game `readme.txt` warning #2. Rebuild the math with `RTP_TARGET=0.965` and re-run
this generator for an ACP-valid bundle.
