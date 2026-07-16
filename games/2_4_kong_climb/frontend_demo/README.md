# Kong Climb — frontend demo

A standalone, **zero-build** web frontend for `2_4_kong_climb` (a Stake-style dice game). It
replays the **real generated math** — the published lookup tables — in plain HTML/CSS/JS. No npm,
no bundler, no framework.

It runs in **two auto-detected modes**:

| Mode             | When                                        | Outcomes                                                          |
| ---------------- | ------------------------------------------- | ---------------------------------------------------------------- |
| **LIVE RGS**     | launched with `rgs_url` **and** `sessionID` | from the real Stake Engine (`/wallet/play`)                      |
| **LOCAL REPLAY** | otherwise                                   | weighted pick from the mode's real lookup table (fully offline)  |

A badge (top-right) shows the active mode. Both modes feed the **same** `playEvents()` renderer
and balance logic, so the UI behaves identically — LOCAL mode reproduces the exact
`diceResult` + `finalWin` event pair the math engine emits.

```
frontend_demo/
  index.html   # page layout + styles + the climbing-ape SVG
  kong-dice.js          # RGS client + event replay (ES module)
  kong_dice_rgs.json    # GENERATED odds bundle (do not hand-edit)
  build_demo_data.py    # regenerates the bundle from library/ output
  run.sh                # local http server
  README.md
```

## How this game works

Not a slot. Each round is one dice roll (roll **over** / **under** a point on 0–100). The math-sdk
generates **72 ACP-compliant modes** = 36 integer win-chance targets × {over, under}. Each mode's
true dice multiplier (`0.97 / winChance`) is **floor-snapped onto the RGS 0.1× grid** to the largest
value with RTP ≤ 96.70%. Only modes inside the tight RTP window that satisfies both ACP RTP rules
are published — per-mode RTP between 90% and 96.70%, **and** all modes within a 1.0% variance of
each other (realised **95.7–96.6%**, a 0.9% spread). Multipliers span **1.1×–48.3×**
(`wincap = 48.3×`). The published target set is sparse, so the slider snaps to the nearest available
target; the multiplier and win chance shown are the real generated values. See the game's
`readme.txt` for the full rationale.

## The RGS contract this implements

Spec: `docs/rgs_docs/RGS.md`; pattern mirrors
`games/3_2_mystery_box_cash_paradise/frontend_demo/app.js`.

- The RGS is a **certified replay**: `/wallet/play {amount, sessionID, mode}` returns a
  pre-generated book chosen **weighted-random over the mode's lookUpTable**, carrying
  `payoutMultiplier` (base-bet ×100) and the event list under `round.state`.
- **Money is an integer with 6 decimals**: `1_000_000` = `1.0`. `payoutMultiplier`/event `amount`
  are base-bet ×100 (`190` = `1.90×`). Currency win = `bet × payoutMultiplier / 100`.
- LIVE flow: `/wallet/authenticate` (balance + bet levels) → `/wallet/play` → `/wallet/end-round`.
- LOCAL mode reproduces the odds exactly because every Kong lookup table has **uniform weight 1**
  and exactly two payouts (`0` or the win value): a weighted pick over `outcomes` and the
  synthesized `diceResult`+`finalWin` events are identical to the real book. The rolled **number**
  shown is cosmetic (books store none) — synthesized consistent with the win/lose so the ape's
  climb reads authentically; payouts and odds are 100% from the real data.

## Run it

```sh
# 1) (Re)generate the data bundle from the current math output:
env/bin/python games/2_4_kong_climb/frontend_demo/build_demo_data.py

# 2) Serve over http (ES module + fetch need http, not file://):
./games/2_4_kong_climb/frontend_demo/run.sh          # http://localhost:7810/index.html
```

LIVE RGS is launched at a Stake URL that injects the query params, e.g.:
`…/index.html?rgs_url=<host>&sessionID=<session>&currency=USD&mode=over_50`.

## Regenerating the bundle

`kong_dice_rgs.json` is **generated**, not source. Re-run `build_demo_data.py` after any math
rebuild — it reads `library/publish_files/index.json` + the 102 `lookUpTable_<mode>_0.csv` +
`library/configs/` and **fails loudly** if a lookup table stops collapsing to two uniform-weight
outcomes (so the demo can never silently drift from the certified math).
