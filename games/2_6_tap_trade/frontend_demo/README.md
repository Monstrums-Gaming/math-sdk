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
- Bet sizes: four quick chips ($1/$2/$5/$20) plus a "+" menu showing the full bet
  grid as a 3-column cell grid (mirrors the production Stake bet menu; the $1,000
  cap renders as MAX), clamped to the $1 min / $1,000 max. A menu pick fills a
  single custom chip in the row and the selection persists
  (`localStorage: taptrade.betSize`). In LIVE mode the whole picker is rebuilt from
  the RGS `config.betLevels` grid (off-grid play amounts are ERR_VAL).
- Win celebration scales with the multiplier (<5x / 5–20x / ≥20x adds a screen flash);
  hot chips show a depleting countdown bar until their column resolves.
- Synth sound cues (place / win / loss), mute toggle next to the bet sizes
  (`localStorage: taptrade.muted`).
- On touch devices the first tap previews a cell ("tap again to confirm"), the
  second places the chip.

  (The localStorage keys were renamed `pricegrid.*` → `taptrade.*` with the
  2026-07-22 Tap Trade rename — internal storage keys only; worst-case fallout of
  the key change is the first-visit hint showing once more.)

- Juice wordmark top-left: `juice_logo.svg` is fetched and inlined so its two
  plates recolor with the active theme (face → `--accent`, extrusion → `--loss`;
  on the default Terminal Rose theme that resolves to the brand's yellow + pink).
- Chart zoom (0.5x–2.5x): mouse wheel, two-finger pinch, or the [−][+] buttons
  bottom-left. Zoom only rescales pixels-per-unit — odds and cell sizes in
  time/price units are untouched. Cell labels and chip text hide when cells get
  too small to read. Session-only (resets to 1x on reload).
- Bet history (clock button in the bet row, or click the session-strip pips):
  every resolved bet keeps a JPEG "landing shot" captured from the canvas ~0.5s
  after the reveal, plus the line's approach path. Clicking an entry opens a
  modal that replays the approach into the cell and shows the shot. Last 24
  bets, in-memory only (screenshots are too big for localStorage — history
  clears on reload).

- Game title badge bottom-center (`tap_trade_logo.svg`, inlined): its rounded
  plate and artwork take the active theme's vars (plate → `--panel`/`--border`,
  TAP → `--text`, TRADE → `--accent`, tap ring/line/candles → `--gain`), so it
  re-inks on every theme change. Sits above the time labels, clear of the bet bar
  and zoom rail; hidden on phones where the bet bar spans the width.

## Files

- `index.html` — the whole demo (canvas renderer, feed + steering, RGS client).
- `juice_logo.svg` — the Juice wordmark, background plate stripped and paths
  classed (`lf` face / `ls` extrusion) for CSS-variable theming.
- `tap_trade_logo.svg` — the Tap Trade title art, colors stripped into classes
  (`tt-plate`/`tt-tap`/`tt-trade`/`tt-*`) for CSS-variable theming.
- `build_demo_data.py` — verifies + copies `../library/odds_bundle.json` →
  `tap_trade_rgs.json`.
- `run.sh` — local HTTP server (the demo fetches JSON, so `file://` won't work).
