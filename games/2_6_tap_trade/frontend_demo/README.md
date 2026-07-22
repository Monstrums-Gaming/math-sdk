# Tap Trade (2_6) — frontend demo

A self-contained browser demo of the Tap Trade mechanic: a live price line
scrolls across a canvas; the future region is a grid of (time × price) cells, each
labelled with a multiplier **snapped to the published 28-rung ladder**. Click a cell
to place a chip; when the line reaches the cell's column the chip wins
`stake × multiplier` or loses.

The outcome is **never** decided by the on-screen line. Each chip is one bet at the
cell's ladder mode (`call_<cents>`); the drawn book decides win/lose and the line is
**steered** to hit or miss the tapped cell accordingly — the cell position is
presentation, the book is the truth. Up to two chips per time-column on distinct
cells: with two outcomes a single line can always render the combination (enter on
the safe side, sweep between two winners), while a third chip can create an
impossible win-lose-win sandwich. The cap is static so a rejection never leaks
anything about outcomes already drawn.

## Run

```bash
./run.sh            # http://localhost:7921 (LOCAL mode)
```

`tap_trade_rgs.json` must exist — rebuild it after any math change:

```bash
PYTHONPATH="$(git rev-parse --show-toplevel 2>/dev/null || pwd)" \
  ../../../env/bin/python build_demo_data.py
```

(Requires `../library/odds_bundle.json`, produced by `../build_odds_bundle.py` after
a production build.)

## Modes

- **LOCAL** (default): play-money wallet ($2,000, click the balance pill to reset).
  Outcomes are weighted draws over the **published lookup-table odds** for the chosen
  rung — the exact certified probabilities, replayed client-side.
- **LIVE**: launch with RGS parameters and every chip places a real bet:

  ```
  index.html?rgs_url=https://<rgs-host>&sessionID=<session>&currency=USD
  ```

  Flow per chip: `/wallet/play {mode: call_<cents>, amount, currency}`, then
  `/wallet/end-round` **only if it won** (a loss is already settled inside the
  play response — see below). Amounts use the RGS integer money scale
  (×1,000,000). `round.payoutMultiplier` is a **plain** multiplier (e.g. `4.5`,
  not `450`) — only the nested `state[]` book events (`cellCall`, `wincap`,
  `finalWin`) use the ×100-cents scale. `round.payout` is the authoritative
  payout amount in the standard money scale; prefer it over recomputing
  `stake × payoutMultiplier` client-side. Bets are serial (one active round
  per session); clicks while a round is settling are rejected with a toast.
  The balance display defers to the reveal so the wallet movement never
  spoils the outcome.

## UX notes

- First visit shows a one-line hint; it disappears after your first chip
  (`localStorage: taptrade.seenHint`).
- Session strip under the balance: net P/L, amount in play, and the last 8 results.
- Win celebration scales with the multiplier (<5x / 5–20x / ≥20x adds a screen flash);
  hot chips show a depleting countdown bar until their column resolves.
- Synth sound cues (place / win / loss), mute toggle next to the bet sizes
  (`localStorage: taptrade.muted`).
- On touch devices the first tap previews a cell ("tap again to confirm"), the
  second places the chip.

  (The localStorage keys were renamed `pricegrid.*` → `taptrade.*` with the
  2026-07-22 Tap Trade rename — internal storage keys only; worst-case fallout of
  the key change is the first-visit hint showing once more.)

## Files

- `index.html` — the whole demo (canvas renderer, feed + steering, RGS client).
- `build_demo_data.py` — verifies + copies `../library/odds_bundle.json` →
  `tap_trade_rgs.json`.
- `run.sh` — local HTTP server (the demo fetches JSON, so `file://` won't work).
