# Kong Climb — RGS integration reference (for porting to Svelte)

This document explains how the standalone `frontend_demo` talks to the RGS, so you can
re-implement the same behaviour in a Svelte project. It is **concept-only** and
framework-agnostic — no Svelte code — but every rule here is what your Svelte port must
reproduce to stay faithful to the certified math.

All references point at `kong-dice.js` (the client) and `build_demo_data.py` (the bundle
generator) in this folder.

---

## 0. The one principle that makes the port clean

The demo runs in **two modes** — LIVE (online RGS) and LOCAL (offline replay) — but **both
produce the exact same `round` object shape**, and a single renderer (`playEvents()`) replays
either one. The RGS logic is therefore a **thin, DOM-free layer** you can lift straight out of
`kong-dice.js` into a plain `.ts`/`.js` module; only the drawing code needs to become Svelte
components.

> Keep this invariant in your port: **LIVE and LOCAL must return an identical `round` shape** so
> one replay path serves both.

---

## 1. Two runtime modes (the online/offline split)

Mode is **auto-detected from the launch URL query params** (`kong-dice.js:39-46`):

```
IS_LIVE = Boolean(rgs_url && sessionID)
```

| Param        | Meaning                                                  |
| ------------ | ------------------------------------------------------- |
| `rgs_url`    | RGS host (no scheme; the client prepends `https://`)    |
| `sessionID`  | Player session issued by Stake Engine                   |
| `currency`   | e.g. `USD` (default `USD`)                               |
| `lang`/`language` | UI language (default `en`)                         |
| `mode`       | optional initial dice mode, e.g. `over_50`               |

- **LIVE RGS** — launched by Stake Engine with both `rgs_url` **and** `sessionID`. Outcomes come
  from the real wallet API.
- **LOCAL REPLAY** — anything else (e.g. opened directly / served locally). Outcomes are a weighted
  pick from the mode's real lookup table baked into `kong_dice_rgs.json`. Fully offline.

A badge (`setModeBadge`, `kong-dice.js:646`) shows which mode is active. If a LIVE
`authenticate` call fails, the demo shows an error but keeps running against the LOCAL data it
already loaded.

---

## 2. LIVE (online) RGS — the certified-replay wallet API

The RGS is a **certified replay system**: odds are frozen at publish time. `/wallet/play` does not
compute anything at runtime — it returns a **pre-generated book** chosen weighted-random over the
mode's published lookup table.

### Transport
All calls are `POST` + JSON to `https://${rgs_url}${endpoint}` (`rgsCall`, `kong-dice.js:205-216`).
A response is an error if `!res.ok` **or** the body carries a `statusCode` — surface `statusCode`
/ `error` as the message.

### Lifecycle (three endpoints)

1. **`/wallet/authenticate`** — `{ sessionID, language }`
   Returns:
   - `balance: { amount, currency }`
   - `config: { defaultBetLevel, betLevels, … }` (bet-level template — see below)
   - `round`: may already be **active** (a round left open from a previous session — resume it).

2. **`/wallet/play`** — `{ sessionID, mode, currency, amount }`
   `mode` is the dice mode name (`currentMode().name`, e.g. `under_20`). `amount` is the bet in
   **API integer units** (see §5), snapped to a valid bet level. Returns a `round`:
   - `payout` — gross win in API integer units
   - `payoutMultiplier` — base-bet ×100 (see §5)
   - `active` — `true` if the round must still be settled
   - `state` — the ordered **event list** to replay
   - plus `betID`, `amount`, `mode`.

3. **`/wallet/end-round`** — `{ sessionID }`
   Settles an open round and returns the updated `balance`. Called when a round comes back
   `active: true`.

### Open-round handling
The client tracks `state.hasOpenRound`. Before each new play it finalizes any still-open round, and
after a play whose `round.active === true` it calls `finalizeRound()` → `/wallet/end-round`
(`kong-dice.js:377, 390-415`). On authenticate, an already-`active` round sets `hasOpenRound = true`.
**Your port must keep this settle-before-next-play discipline** or the RGS will reject the next play.

### Bet levels
The math-sdk does **not** emit bet levels — they come from the RGS `config` (an ACP dashboard
"bet-level template"). `snapLiveBet()` (`kong-dice.js:227-238`) snaps a requested bet to the nearest
entry in `config.betLevels`, or falls back to `stepBet`/`minBet`/`maxBet` rounding. In LOCAL mode
there are no bet levels (`betLevels: null`) and the bet is free-form.

### Error codes
`rgsErrorMessage()` (`kong-dice.js:526-534`) maps RGS codes to user text:
`ERR_IS` (invalid/expired session), `ERR_IPB` (insufficient balance), `ERR_VAL` (invalid request),
`ERR_ATE` (auth failed), `ERR_GLE` (gambling limit), `ERR_LOC` (bad location), `ERR_GEN` (server),
`ERR_MAINTENANCE`.

---

## 3. LOCAL (offline) replay — reproducing the book without a server

LOCAL mode fabricates the **same round/event shape** the RGS returns, using only
`kong_dice_rgs.json` (`kong-dice.js:240-300`):

- **`localAuth()`** — seeds a fake balance (`LOCAL_START_BALANCE = 1000`) and `betLevels: null`.
- **`localPlay()`**:
  1. Debit the bet from the local balance.
  2. `pickOutcome(mode)` — weighted random pick over `mode.outcomes` (§6).
  3. `buildDiceEvents(mode, outcome)` — synthesize the `diceResult` + `finalWin` event pair.
  4. Credit the win (settled immediately, `active: false`).
  5. Return a `round` object **identical in shape** to `/wallet/play`.

### Why this is faithful (not a fake)
Every Kong lookup table has **uniform weight 1** and exactly **two distinct payouts** — `0` (loss)
or the single win value. So the mode collapses to two outcomes, and a weighted pick + synthesized
events reproduces the real book exactly — no zstd decoder or server needed. This 2-outcome/uniform
shape is **asserted at build time** (§6), so the demo can never silently drift from the math.

### The rolled number is cosmetic
Books store **no** dice number. `syntheticRoll(mode, isWin)` (`kong-dice.js:307-312`) fabricates a
value on the correct side of the target purely so the animation lands inside/outside the win zone.
Payouts and odds are 100% real; only the displayed roll number is invented. Your port can invent it
however it likes (or omit it) without affecting correctness.

---

## 4. The round/event contract (what `playEvents` consumes)

`playEvents(events)` (`kong-dice.js:314-339`) is the single replay path. It reads:

**Round fields** (used by `rollDice`, `kong-dice.js:379-396`):
- `round.state` — the event list (fallback `round.events` for safety)
- `round.payout` — gross payout (API integer units) — for net calc
- `round.amount` — stake (API integer units)
- `round.active` — whether to call end-round
- `resp.balance.amount` — authoritative balance after the call

**Events** — an ordered array; each has an `index` (sorted before replay). Two types:

| Event type   | Fields                                                          |
| ------------ | -------------------------------------------------------------- |
| `diceResult` | `direction`, `target`, `winChance`, `isWin`, `payoutMultiplier` (×100) |
| `finalWin`   | `amount` (base-bet ×100; `0` on a loss)                        |

`isWin` comes from the `diceResult`; the win amount comes from `finalWin.amount`. Net for the
autobet/profit logic is `round.payout − round.amount` in API integer units.

---

## 5. Money & scaling rules (the easiest thing to get wrong)

Two different integer scales are in play — do not mix them:

| Constant | Value | Applies to |
| --- | --- | --- |
| `API_MULTIPLIER` | `1_000_000` | **Wallet money**: balance, bet `amount`, `round.payout`. `1_000_000` == `1.0` currency unit. |
| `EVENT_SCALE` | `100` | **Multipliers**: `payoutMultiplier`, `finalWin.amount`. `194` == `1.94×`. |

Helpers (`kong-dice.js:26-28, 124-127`):
- `toUnits(api)  = api / 1_000_000` — API integer → currency units
- `toApi(units)  = round(units * 1_000_000)` — currency units → API integer
- **Currency win** = `bet_units × payoutMultiplier / 100`
- **Net** = `payout − stake` (compute in API integer units so it works in both modes)

Display: `fmtMoney()` + the `CURRENCY_META` table (`kong-dice.js:49-63`) hold per-currency symbol
and decimal count (e.g. `JPY`/`KRW`/`IDR` have 0 decimals). Keep this table when porting or amounts
will render wrong for zero-decimal currencies.

---

## 6. `kong_dice_rgs.json` — structure and role

This is the **offline odds bundle** the demo `fetch`es once at startup (`loadBundle`,
`kong-dice.js:653-674`; `DATA_URL = "./kong_dice_rgs.json"`).

- **LOCAL mode** needs the `outcomes` to weighted-pick a result.
- **BOTH modes** read the mode **metadata** (`name`, `direction`, `target`, `winChance`,
  `multiplier`) to drive the slider, the win-chance/multiplier readouts, and mode selection. So you
  need this file (or an equivalent) even for a LIVE-only port.

### Shape

```jsonc
{
  "game_id": "2_4_kong_climb",
  "rtp": 0.966,                 // advertised = max mode RTP (ACP cap is 96.70%)
  "modes": [
    {
      "name": "under_05",      // "<direction>_<NN>" — this is the RGS `mode` string
      "direction": "under",     // "under" | "over"
      "tier": 5,                // = NN
      "multiplier": 19.3,       // floor-snapped dice multiplier (payoutMultiplier / 100)
      "winChance": 5,           // integer win % 
      "target": 5,              // slider point on 0–100
      "cost": 1.0,              // base-bet cost (ACP: base mode == 1.0)
      "maxWin": 48.3,           // wincap
      "outcomes": [
        { "payoutCents": 1930, "weight": 1 },   // WIN  (payoutCents = multiplier ×100)
        { "payoutCents": 0,    "weight": 19 }   // LOSS
      ]
    }
    // … one entry per published mode
  ]
}
```

### Mode naming & selection
- `modeName(direction, nn)` → `over_NN` / `under_NN` (`kong-dice.js:187-188`) — this string is the
  RGS `mode` argument.
- **`under_NN` wins if roll < NN** (winChance = NN%); **`over_NN` wins if roll > NN**
  (winChance = 100 − NN%). `over` and `under` are **not** mirrors — different win chance at the same
  NN, except NN = 50.
- The ACP-compliant target set is **sparse** (gaps). `loadBundle` collects the sorted list of
  published `target`s per direction into `state.targets`, and `clampTarget` **snaps the slider to
  the nearest published target** (`kong-dice.js:190-197`). Your port must snap the same way — an
  arbitrary slider value has no mode.

### It is generated, not source
`kong_dice_rgs.json` is produced by **`build_demo_data.py`** from the game's published library:
`library/publish_files/index.json` + each `lookUpTable_<mode>_0.csv` + `library/configs/*`. The
generator:
- **asserts** every LUT collapses to uniform weight 1 and ≤2 payouts `{0, win}` (`_read_lut`), and
- **cross-checks** the engine event template's `payoutMultiplier`, `winChance`, and per-mode RTP
  (~0.97) against the raw LUT — failing loudly on any mismatch.

So the demo can never silently diverge from the certified math. **Regenerate it after every math
rebuild:**

```sh
env/bin/python games/2_4_kong_climb/frontend_demo/build_demo_data.py
```

---

## 7. Porting checklist for Svelte

**Lift these DOM-free functions into a plain module** (`rgsClient.ts` or similar) — they need no
changes beyond ESM imports:

- Transport / LIVE: `rgsCall`, `liveAuth`, `livePlay`, `liveEndRound`, `snapLiveBet`,
  `finalizeRound`, `rgsErrorMessage`
- LOCAL: `localAuth`, `localPlay`, `pickOutcome`, `buildDiceEvents`, `syntheticRoll`
- Money/mode helpers: `toUnits`, `toApi`, `fmtMoney` + `CURRENCY_META`, `modeName`, `clampTarget`,
  `currentMode`, `loadBundle`

**Rewrite these DOM-bound parts as Svelte components / effects:** `playEvents`, `updateUI`,
`paintWinZone`, `paintRuler`, `showResult`, `showToast`, `pushHistory`, the autobet UI, and the
ape-drag handler.

**State**: the single `state` object (`kong-dice.js:100-122`) maps naturally onto a Svelte store or
`$state` runes. Derive `ranges` and sorted `targets` per direction exactly as `loadBundle` does.

**Data loading**: load `kong_dice_rgs.json` once at init — import it as a static asset or `fetch`
it. Keep it in sync by re-running `build_demo_data.py`; don't hand-edit it.

**Invariants to preserve:**
1. LIVE and LOCAL return an identical `round` shape → one replay path.
2. Keep the two integer scales distinct (`API_MULTIPLIER` for money, `EVENT_SCALE` for
   multipliers).
3. Snap the slider to a published target; never send an unpublished `mode`.
4. In LIVE mode, settle any open round before the next play.

---

## Reference

- Client: `games/2_4_kong_climb/frontend_demo/kong-dice.js`
- Bundle generator: `games/2_4_kong_climb/frontend_demo/build_demo_data.py`
- Demo overview: `games/2_4_kong_climb/frontend_demo/README.md`
- RGS wallet spec: `docs/rgs_docs/RGS.md`
- Prior pattern this mirrors: `games/3_2_mystery_box_cash_paradise/frontend_demo/app.js`
