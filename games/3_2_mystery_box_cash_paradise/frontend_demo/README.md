# Cash Paradise — frontend demo

A standalone, **zero-build** web frontend for `3_2_mystery_box_cash_paradise`. It animates
this game's event stream (open box → reveal voucher → settle win) in plain HTML/CSS/JS — no
npm, no bundler, no framework.

It runs in **two auto-detected modes**:

| Mode          | When                                    | Outcomes                                              |
| ------------- | --------------------------------------- | ----------------------------------------------------- |
| **LIVE RGS**  | launched with `rgs_url` **and** `sessionID` | from the real Stake Engine (`/wallet/play`)           |
| **LOCAL SIM** | otherwise                               | drawn client-side from the prize table (no RGS)       |

The header shows a badge for the active mode. Both modes feed the **same** `playEvents()`
renderer and balance logic, so the UI behaves identically — Local mode builds the exact
event sequence the math engine emits.

```
frontend_demo/
  index.html    # page layout
  app.js        # RGS client + event replay (ES module)
  styles.css    # box / reveal / win animations
  prizes.js     # CP1–CP9 catalog (copy of the generated config_fe) + baked image paths
  images/       # CP1.png … CP9.png — prize art baked into the bundle
  README.md
```

## How this game works

Not a slot. One purchase (cost **4.98× base bet**, single `base` mode) returns exactly
one cash-voucher prize from a fixed probability table. Target RTP 85%.

## The RGS contract this implements

Spec: `docs/rgs_docs/RGS.md`. Pattern: `docs/simple_example/app_svelte.txt`.

- The game is launched at a Stake URL with query params: `sessionID`, `rgs_url`, `lang`,
  `device`, `currency`, `mode`. All calls are `POST https://${rgs_url}${endpoint}`.
- **Money is an integer with 6 decimal places**: `1_000_000` = `1.0`. A `$1` bet is sent
  as `amount: 1000000`.
- `POST /wallet/authenticate {sessionID, language}` → `{balance, config:{betLevels,
  defaultBetLevel, …}, round}`. Called on load.
- `POST /wallet/play {sessionID, mode, currency, amount}` → `{balance, round}` where
  `round = {betID, payout, payoutMultiplier, active, mode, state:[…events]}` (one math "book").
  **The event list is `round.state`, not `round.events`.**
- `POST /wallet/end-round {sessionID}` → `{balance}`. Called only when `round.active === true`
  (the RGS may auto-settle a round, returning `active:false` — then no end-round is needed).

### Event stream (per round, in `index` order)

Event `amount` / `payoutMultiplier` are base-bet multipliers **×100** (`100` = `1.0x`).

| Event           | When                | Used for                                        |
| --------------- | ------------------- | ----------------------------------------------- |
| `mysteryReveal` | always, first       | `prize` (`CP1…CP9`) + `prizeName` → reveal card |
| `wincap`        | only CP9 ($1,000)   | jackpot treatment                               |
| `winInfo`       | only if payout > 0  | win breakdown (`totalWin`, `wins[]`)            |
| `setWin`        | always              | `winLevel` 1–10 → animation intensity           |
| `setTotalWin`   | always              | running total                                   |
| `finalWin`      | always, last        | settle amount                                   |

Win in currency = `finalWin.amount / 100 × baseBet`.

## Run it

Serve the folder with any static server (an http server is required because `app.js` is an
ES module — `file://` won't work):

```sh
cd games/3_2_mystery_box_cash_paradise/frontend_demo
python3 -m http.server 8000
```

Any static server works (`npx serve`, VS Code Live Server, …); `python3 -m http.server`
just needs no dependencies. Pick any free port. Then open one of:

- **LOCAL SIM (no RGS, fully offline):** open `http://localhost:8000/`. With no `rgs_url`/
  `sessionID` the demo auto-runs Local mode — it draws weighted-random prizes from the prize
  table, builds the same event sequence the engine emits, and tracks a client-side balance
  (starts at 1,000). Over many opens the outcome frequencies match the prize table (~85% RTP).

  The prize art comes from the **baked-in** `images/CP*.png` (see below) — no
  network call, so it looks the same here as on live RGS.

- **LIVE RGS:** open with the params from a real Stake session, e.g.
  `http://localhost:8000/?rgs_url=<host>&sessionID=<id>&currency=USD&mode=base`.
  Balance and outcomes come from the RGS; wins are finalized via `/wallet/end-round`.

The header badge shows which mode is active.

## Prize art: baked images

The CP1–CP9 prize art is **baked into the bundle** as `images/CP*.png` and
referenced from `prizes.js` (`image: "./images/CP1.png"`). The renderer prefers
that image and falls back to the prize's emoji if a file is missing. These images
are same-origin assets, so they render on the live Stake RGS (whose CSP allows
`img-src 'self'`) with **no network call** — prize names, art, and probabilities
all come from `prizes.js`, identically off-RGS and on live.

To change the art, just overwrite the `images/CP*.png` files (keeping the
`CP1`…`CP9` names) — no code change needed.

## Bet level

The demo uses a **single fixed base bet** (the selector is locked), so the box always costs
its full price (`base bet × box_cost`). Local mode fixes it at `1.00`; Live mode uses the RGS
`defaultBetLevel`.

Note: `box_cost` in `game_config.py` is the bet mode's **cost multiplier** (`debit = base bet ×
cost`), not a bet amount. The selectable base-bet levels (`minBet`/`maxBet`/`stepBet`/
`betLevels`) are **not** defined by the math-sdk — they come from `/wallet/authenticate` and are
configured operator-side on the Stake Engine dashboard. To truly restrict bet levels for the
live game, set them there; this demo only locks its own UI.

## Deploy to Stake Engine

Upload the whole folder as the game's **frontend files**: `index.html`, `app.js`,
`styles.css`, `prizes.js`, **and the `images/` folder** (`CP1.png … CP9.png` — the
prize art must ship in the bundle, since the CSP blocks fetching it at runtime).
No build step — unlike the Svelte/Vite example in
`docs/simple_example/`, which requires `yarn build` and uploading `dist/`. Stake
injects the query params at launch.

## Source of truth

`prizes.js` mirrors `library/configs/config_fe_3_2_mystery_box_cash_paradise.json` and the
probabilities in `readme.txt`. If the prize table changes in `game_config.py`, rerun the
game and update `prizes.js` to match.
