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

Vite project (Node >= 20; vite is the only dependency, dev-only):

```bash
./run.sh            # npm install (first run) + vite dev on http://localhost:7921
npm run build       # production build → dist/ (minified, sourcemapped, relative URLs)
npm run preview     # serve the built dist/ on http://localhost:7922
```

**Deploy (Stake Engine)**: upload the *contents* of `dist/` (index.html at the
root) to the Stake Engine game's Files page, then Publish → Front End.
`base: './'` keeps every asset URL relative, so the build also works from any
static subpath. LIVE mode is the same `?rgs_url=…&sessionID=…` launch params
as always.

**Deploy (Vercel)**: `vercel.json` is included (`npm ci` / `npm run build` /
`dist`). In the Vercel dashboard: New Project → import the math-sdk repo → set
**Root Directory** to `games/2_6_tap_trade/frontend_demo` (framework
auto-detects as Vite). Two flavors:

- **Staging / public demo** — playable play-money at the bare URL: either run
  `npm run build:staging` (uses `.env.staging` → `VITE_DEMO_OK=1`) or set the
  `VITE_DEMO_OK=1` environment variable on the Vercel environment.
- **Production** — the default `npm run build`: locked to casino launches (a
  paramless visit shows the "launch from the casino" screen; `?demo=1` still
  opens play-money for ad-hoc review). This is also the build for Stake uploads.

`public/tap_trade_rgs.json` must exist — rebuild it after any math change:

```bash
PYTHONPATH="$(git rev-parse --show-toplevel 2>/dev/null || pwd)" \
  ../../../env/bin/python build_demo_data.py
```

(Requires `../library/odds_bundle.json`, produced by `../build_odds_bundle.py` after
a production build.)

## Modes

- **LOCAL** (play-money wallet, $2,000, click the balance pill to reset): outcomes
  are weighted draws over the **published lookup-table odds** for the chosen rung —
  the exact certified probabilities, replayed client-side. Dev builds default to
  LOCAL; a **production build requires `?demo=1`** for it (a paramless launch shows
  a blocking "launch from the casino" screen instead of silently degrading).
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

  Production hardening on this path: bets are blocked until `/wallet/authenticate`
  succeeds; an **unfinished round returned by authenticate is settled immediately**
  (end-round + "Last round settled" toast — rounds are serial, so an orphan round
  would block the whole session); `/wallet/end-round` retries with backoff, and a
  win whose release keeps failing raises a blocking reload prompt (reload
  re-authenticates and the resume path settles it); session-level errors
  (`ERR_IS`/`ERR_ATE`) raise a blocking overlay instead of a toast. The
  authenticate `config` is authoritative: `betLevels` + `minBet`/`maxBet` rebuild
  the picker, `defaultBetLevel` seeds the selection, and `jurisdiction` flags are
  honored (`disabledTurbo` removes the 1.5x/2x speeds, `socialCasino` relabels the
  bet row). All money strings format via `Intl.NumberFormat` from the `currency` +
  `lang` params (crypto codes fall back to a `CODE 1.23` prefix).

## UX notes

- Splash on load: one loop of the Stake Engine loader (`stake_engine_loader.webp`,
  on its baked `#041721` ground) then the Monstrums sting (`monstrums_logo.webm`,
  on black, lazy-loaded during the loader phase) — always auto-proceeds (falls back
  to muted autoplay when the browser blocks audio), click or Escape skips, 20s
  failsafe dismiss.
- First visit shows a one-line hint; it disappears after your first chip
  (`localStorage: taptrade.seenHint`).
- Session strip top-right: net P/L, amount in play, and the last 8 results as
  pips (click them to open the bet history). The canvas price ladder starts below
  it so the two never overlap.
- Bet sizes: four quick chips ($1/$2/$5/$20) plus a "+" menu showing the full bet
  grid as a 3-column cell grid (mirrors the production Stake bet menu; the $1,000
  cap renders as MAX), clamped to the $1 min / $1,000 max. A menu pick fills a
  single custom chip in the row and the selection persists
  (`localStorage: taptrade.betSize`). In LIVE mode the whole picker is rebuilt from
  the RGS `config.betLevels` grid (off-grid play amounts are ERR_VAL).
- Win celebration scales with the multiplier (<5x / 5–20x / ≥20x adds a screen flash);
  hot chips show a depleting countdown bar until their column resolves.
- Settings (gear button): game speed 1x / 1.5x / 2x (`localStorage: taptrade.speed`,
  multiplies the sim clock only — odds are untouched), sound on/off
  (`taptrade.muted`), and tap-to-confirm (`taptrade.tapConfirm`) — when on, the
  first tap/click previews the cell and the second places the chip, on any pointer;
  defaults on for touch, off for mouse.
- Synth sound cues (place / win / loss).

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
  modal that replays the approach into the cell and shows the shot; the replay
  redraws the real cell grid at the live chart's own seconds-to-dollars aspect,
  so it is geometrically the scene the shot captured. Last 24 bets, in-memory
  only (screenshots are too big for localStorage — history clears on reload).

- Game title badge bottom-center (`tap_trade_logo.svg`, inlined): its rounded
  plate and artwork take the active theme's vars (plate → `--panel`/`--border`,
  TAP → `--text`, TRADE → `--accent`, tap ring/line/candles → `--gain`), so it
  re-inks on every theme change. Sits above the time labels, clear of the bet bar
  and zoom rail; hidden on phones where the bet bar spans the width.

## Files

- `index.html` — markup shell; all logic lives under `src/`.
- `src/main.js` — the game core (state, feed + steering, render, betting,
  history/replay, menus, settings) — one closure by design; see the module docs.
- `src/config.js`, `src/themes.js`, `src/rgs.js`, `src/splash.js`,
  `src/style.css` — the clean-boundary modules (tunables, palettes, RGS client,
  intro sequence, styles).
- `public/` — runtime-fetched assets, copied verbatim into `dist/`:
  `tap_trade_rgs.json` (the odds bundle), `juice_logo.svg` (wordmark; paths
  classed `lf`/`ls` for CSS-variable theming), `tap_trade_logo.svg` (title art;
  classes `tt-*`), `stake_engine_loader.gif` + `monstrums_logo.webm` (splash).
- `src/betGrid.js`, `src/money.js` — pure helpers (bet-grid snapping, currency
  formatting) with vitest suites (`src/*.test.js`, `npm test`); CI runs test+build
  on every demo change (`.github/workflows/tap-trade-demo.yml`).
- `vite.config.mjs`, `package.json` — the build (`base './'`, es2017, sourcemaps).
- `build_demo_data.py` — verifies + copies `../library/odds_bundle.json` →
  `public/tap_trade_rgs.json`.
- `run.sh` — dev-server launcher (`npm install` guard + `npm run dev`).
