---
name: stake-price-grid-game
description: >-
  Build, modify, or extend a PRICE-GRID (tap-cell-to-bet / "Euphoria") game in the
  math-sdk — the family led by games/2_6_tap_trade (formerly
  2_11_crypto_pulse_grid / 2_11_price_grid; its retired predecessor 2_10_crypto_pulse_grid followed the same
  recipe): a live price line scrolls across a chart, the future region is a grid of
  (time x price) multiplier cells, and each tapped cell is an independent win/lose
  bet at a fixed ladder multiplier. Use when creating a new grid variant (new
  game_id, different multiplier ladder), changing an existing grid game's ladder or
  odds, wiring a frontend to this math (steered-line reveal, LOCAL LUT replay or
  LIVE RGS bets), or reasoning about multi-chip placement rules (why max 2 chips per
  time-column). Encodes the ladder recipe, the outcome-neutral-cell model, the
  cellCall/wincap/finalWin book contract, the build+verify pipeline, and the
  frontend_demo conventions. Complements stake-direct-probability-game (the general
  boardless recipe this family follows), stake-risk-validators (volatility floor /
  100x cap), and publish-stake-game (ACP upload).
---

# Build a Stake price-grid (tap-cell) game

A **price-grid** game shows a live-looking price chart; the future region is covered
by a grid of multiplier cells. A tap places a chip; if the line later reaches that
cell the chip pays `bet × cellMultiplier`, else it loses. Reference implementation:

| Game | Folder | Ladder |
|---|---|---|
| Tap Trade (2_6) | `games/2_6_tap_trade` | 28 rungs, 1.4x–100x, dense below 10x |

(Its predecessor, also named Crypto Pulse Grid, lived at `2_10_crypto_pulse_grid`
with a sparser 20-rung ladder; it was removed 2026-07-20 and the survivor — then
named `2_11_price_grid` — was renamed to `2_11_crypto_pulse_grid` to take over the
slug/name as the sole surviving grid game. On 2026-07-22 it was renamed again to
`2_6_tap_trade` ("Tap Trade") to pair with the web-sdk app `apps/2-6-tap-trade`;
only the identity changed, never the ladder/odds/contract.)

## The model in one paragraph

The book is **position-neutral**: WHERE the tapped cell sits is pure client-side
presentation. Each chip is an independent win/lose bet at a fixed multiplier M —
exactly the `2_9_crypto_pulse` model. One published bet mode per distinct ladder
multiplier, named `call_<cents>` (dot-free: the ACP publisher parses `<mode>` out of
`books_<mode>.jsonl.zst`). The RGS draws a pre-frozen book; the frontend then
**steers the line** to hit or miss the tapped cell to match `isWin`. Prices are RNG
theatre; odds cannot change at runtime.

## Ladder recipe (the only real math surface)

All of this is implemented in `game_config.py` of either reference game — clone it,
don't rewrite it:

1. `_MULTIPLIERS`: every value a multiple of **0.10** (`lut_grid_exempt = False`),
   floor **1.4x** (a 1.2x win/lose mode has payout std ~0.48, below ACP's 0.60
   Base-Volatility floor — see stake-risk-validators), cap **100x** (the approved
   Limbo `base_100` envelope).
2. Per rung M: win probability = smallest-denominator fraction a/b with realised RTP
   `(a/b)×M` inside **[96.00%, 96.70%]** via `_simplest_fraction_in` (Stern-Brocot).
   `num_sims = b` (assert ≤ 1000) → exactly `a` winning books; published odds equal
   book counts (Rust optimiser off, uniform weight 1 per book).
3. Cross-mode RTP spread ≤ 1% is automatic (all rungs inside a 0.70%-wide band).
4. **Per-mode wincap is intentional**: each `BetMode.max_win` = that rung's own M, so
   every winning book emits `cellCall -> wincap -> finalWin` (losing:
   `cellCall -> finalWin`). The web side treats `wincap` as a no-op. Do not "fix" it.
5. Every mode `cost = 1.0`.
6. `_validate()` pins mode count, 0.1x grid, RTP band, exact quota splits — update
   its expected count when changing the ladder.

## New variant checklist

1. Copy the newest grid game folder (exclude generated `library/`); keep the file
   set: run.py, game_config.py, gamestate.py, game_override.py, game_executables.py,
   game_calculations.py, game_events.py, game_optimization.py (disabled stub),
   build_odds_bundle.py, reels/BR0.csv (dummy), readme.txt, frontend_demo/.
2. Change: `game_id`, `game_name`/`working_name`, `_MULTIPLIERS`, `_validate` counts,
   module docstrings, readme.txt (paste the real a/b table after the first run).
3. Sanity: import GameConfig and print the tiers — the asserts do the checking.

## Build + verify pipeline

```bash
# dev (readable .json books)
PYTHONPATH="$PWD" ./env/bin/python games/<id>/run.py
# production (mandatory: format checks reject non-.jsonl.zst books)
COMPRESSION=1 RUN_FORMAT_CHECKS=1 PYTHONPATH="$PWD" ./env/bin/python games/<id>/run.py
# re-verify every artifact book-by-book + emit library/odds_bundle.json
PYTHONPATH="$PWD" ./env/bin/python games/<id>/build_odds_bundle.py
# refresh the demo's data bundle
PYTHONPATH="$PWD" ./env/bin/python games/<id>/frontend_demo/build_demo_data.py
```

Publish set = `library/publish_files/` (index.json, books_*.jsonl.zst,
lookUpTable_*_0.csv) — see publish-stake-game. `odds_bundle.json` goes to the web
team separately; it is NOT an RGS artifact.

## Frontend rules (frontend_demo/ or a web app)

- **Cell multiplier display**: price cells with a local vol model (Φ approximation of
  touch probability), then snap to the **nearest ladder rung in log space**. The
  displayed value must always be a real published mode; true odds come from the
  mode, never the display model.
- **Placing a chip** = one bet at that rung's mode. LIVE: `/wallet/play {sessionID,
  mode: call_<cents>, currency, amount}`; amounts ×1,000,000 (integer money).
  **`round.payoutMultiplier` is a PLAIN multiplier** (e.g. `4.5` for a 4.5x win),
  **not** ×100 cents — confirmed against a live response (`{round:{payoutMultiplier:
  4.5, payout:22500000, amount:5000000}}` for a $5 bet at 4.5x = $22.50). Only the
  nested `state[]` book events (`cellCall.payoutMultiplier`, `wincap`/
  `finalWin.amount`) use the ×100-cents scale — don't apply that scaling to the
  top-level `round` fields, or a win pays 1/100th of the real amount. `round.payout`
  is the authoritative payout in the standard money scale (÷1,000,000) — prefer it
  outright over recomputing `stake × payoutMultiplier` client-side. Call
  `/wallet/end-round` **only when the play response shows a win**
  (`payoutMultiplier > 0`) — a loss has nothing to pay out, so the RGS already
  settles and closes the round inside the play response itself (`round.active:
  false`); calling end-round on it anyway throws `"player does not have active
  round"`. Mirrors the production noWin/singleRoundWin split in
  monstrums-web-sdk's `packages/utils-xstate/createPrimaryMachines.ts`. LOCAL:
  weighted draw over the bundle's `outcomes` (the exact certified odds). Serialize
  rounds through a promise chain (RGS: one active round per session) — queue, don't
  reject.
- **Steering**: the drawn book decides; the line is steered afterward. Winners:
  converge on the nearest unrevealed winning cell, then sweep to the second. Losers:
  hold a miss lane clear of every losing band; hard-clamp inside the window so a
  losing cell is never touched. Use a critically-damped velocity pull, not raw force
  (raw force overshoots into a visible dive).
- **Max 2 chips per time-column, distinct cells.** With ≤2 outcomes one line can
  always render the combination (enter on the safe side / sweep two winners); a 3rd
  chip allows an impossible win-lose-win sandwich. The cap must be STATIC — an
  outcome-dependent rejection would leak what has already been drawn. Cross-column
  chips are unrestricted.
- **Never spoil the outcome**: defer balance-display updates to the reveal (the line
  reaching the cell), even though the book settles at bet time. Camera should frame
  both the line and the nearest chip through its resolution beat.
- Established UX conventions (see `games/2_6_tap_trade/frontend_demo/`): first-play
  hint, cause-specific rejection copy ("Too close to the line" / "Column full — max 2
  chips" / "Chip already there"), session strip (P/L, at-risk, last-8 ticker),
  win tiers (<5x / 5–20x / ≥20x with escalating beat), hot-chip countdown bar,
  synth audio cues with persisted mute, touch two-tap confirm, reduced-motion
  fallbacks.

## Book event contract (byte-level, shared with the web side)

All amounts are bet-relative multiplier cents (×100).

```
cellCall { index, type, result: "Win"|"Lose", isWin, payoutMultiplier, winChance }
wincap   { index, type, amount }   # win books only; amount == payoutMultiplier
finalWin { index, type, amount }   # M*100 on win, 0 on loss == the LUT payout
```
