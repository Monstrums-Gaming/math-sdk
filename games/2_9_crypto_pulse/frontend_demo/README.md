# Crypto Pulse (2_9) — frontend demo

A self-contained browser mockup of the HIGH/LOW mechanic that **replays the published
math**. Pick HIGH or LOW; a BTC/USD chart animates ~5–8s and finishes above/below the
start line according to the RGS result; the payout is credited after the animation.

It is a preview only — independent of the published RGS frontend config and the build
pipeline. The chart is a generated random-walk (not real BTC prices); the countdown,
"online" count and live-bets feed are cosmetic chrome.

## Run

```sh
./run.sh            # http://localhost:7919  (serves over http; file:// won't work)
./run.sh 3000       # custom port
```

## How it replays the real odds

`build_demo_data.py` reads the game's published library
(`library/publish_files/index.json` + `lookUpTable_base_0.csv` +
`library/configs/event_config_base.json`), asserts the LUT is uniform-weight with
exactly two payouts `{0, win}`, and emits **`crypto_pulse_rgs.json`**:

```json
{ "game_id":"2_9_crypto_pulse", "rtp":0.9667, "multiplier":1.9, "winChance":0.508772,
  "modes": { "base": { "multiplier":1.9, "winChance":0.508772,
    "outcomes":[{"payoutCents":190,"weight":29},{"payoutCents":0,"weight":28}] }}}
```

The page does a **weighted pick** over those exact outcomes (29 win / 28 lose), so the
demo's realised odds match the certified LUT. HIGH and LOW share the single `base`
mode — the chart direction is derived client-side: `endsHigh = (pickedHigh === isWin)`.

**Rebuild the bundle after any math rebuild:**

```sh
PYTHONPATH="$(pwd)" ./env/bin/python games/2_9_crypto_pulse/frontend_demo/build_demo_data.py
```

## LOCAL vs LIVE

Default is **LOCAL** (offline weighted replay; badge shows `LOCAL`). Passing
`?rgs_url=<url>&sessionID=<id>&currency=USD` switches to **LIVE**: the page calls
`/wallet/authenticate` → `/wallet/play {mode:"base"}` → `/wallet/end-round` and reads
the pre-frozen book's `payoutMultiplier`. Both paths feed the same chart renderer.
