# Chicken Run — frontend demo

A self-contained browser demo of the `2_8_chicken_run` game, wired to the **real published RGS
math**. **Each press of PLAY is a separate, independent wager on the next lane** — cross safely and
that wager pays immediately at the lane's multiplier and you advance; get hit and that wager loses
and the chicken returns to the start. No cumulative cash-out; every press is its own single-book bet.

## Run

```sh
./run.sh              # serves http://localhost:7818/index.html (default)
./run.sh 3000         # custom port
```
Must be served over http:// (the page `fetch()`es `chicken_run_rgs.json`; `file://` won't work).

## How to play

1. Set the **Play Amount** and pick a **difficulty** (Easy / Medium / Hard).
2. Press **PLAY** to wager on crossing the next lane. Safe → paid `Play Amount × lane multiplier`
   and the chicken advances; hit → that stake is lost and the chicken returns to the start.
3. Keep pressing PLAY to attempt further lanes (higher multipliers, lower odds).
4. **GO TO START** resets to the first lane with no wager.

## Two auto-detected modes

| Mode | When | Outcome source |
|---|---|---|
| **LOCAL** (default) | no RGS params | weighted-pick the `<difficulty>_<lane>` mode's win/lose outcome from `chicken_run_rgs.json` |
| **LIVE** | `?rgs_url=<host>&sessionID=<id>` | each PLAY = `/wallet/play` on that lane's mode, then `/wallet/end-round` |

Optional params: `currency`, `lang`, `mode`. Money: wallet is integer ×1,000,000; event multipliers
are raw (e.g. `1.1` = 1.1×). Currency win = `stake × multiplier`.

## The model (honest & single-book)

Stake Engine settles one pre-frozen book per `/wallet/play`, so there is no live cash-out. Chicken
Run fits that exactly by making **each lane its own wager**: the player's real decision is simply
whether to press PLAY again (attempt the next, higher-multiplier, lower-probability lane) or stop.
Each wager runs at ~97% RTP (published within the ACP 96.00–96.70% band). See the game `readme.txt`.

## The data bundle (generated, not source)

`chicken_run_rgs.json` is produced from the built `library/` — regenerate after any math rebuild:

```sh
PYTHONPATH="$(pwd)" env/bin/python games/2_8_chicken_run/frontend_demo/build_demo_data.py
```

It collapses each of the 72 modes' lookup tables into a `{win, lose}` outcome pair and exposes the
per-difficulty ladders (`ladders.easy/medium/hard`, 24 multipliers each). Modes: `easy/medium/hard`
× `1..24`, maxima 23.8× / 548× / 918×.
