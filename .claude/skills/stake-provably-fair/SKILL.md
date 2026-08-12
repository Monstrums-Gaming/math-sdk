---
name: stake-provably-fair
description: >-
  Make a Stake Engine game provably-fair-verifiable and add fairness/odds
  transparency. Use when adding provably-fair to a game, storing a seed-consistent
  result (e.g. a dice `roll`) in the book, wiring a Fairness/verification UI in the
  web app, or answering "how does provably fair work on Stake Engine / can we do
  it". Explains the REAL model (the platform's seed pair selects WHICH book the RGS
  serves from the weighted LUT — the game does NOT manage seeds), what the book
  must store, the SHA-256 odds-integrity manifest, and the hard gotchas. Reference
  implementation: math-sdk games/2_4_dice_kong_climb + web apps/2-0-dice
  (typesBookEvent/bookEventHandlerMap/FairnessModal). Complements stake-dice-game,
  stake-direct-probability-game, and publish-stake-game.
---

# Provably fair on Stake Engine (the real model)

Stake Engine **has** provably fair. Live Engine games show the standard Stake
seed-pair UI (Active Client Seed, Active Server Seed *hashed*, nonce = "total bets
made with pair", Rotate Seed Pair, New Client Seed). Do **not** repeat the earlier
mistake of concluding it's "impossible" — that came from a broken docs tool citing
our own stale code. Ground truth is below; the authoritative algorithm lives at
**https://stake-engine.com/fair** (fetch it fresh — the on-site `/fair` page is a
JS SPA, so use the Stake docs prose, WebSearch, or ask the user, who may be an
insider).

## How it actually works — and how it reconciles with certified replay

The RGS is a certified **replay** system: per mode we publish a weighted lookup
table (`lookUpTable_<mode>_0.csv`, rows `book_id,weight,payout_cents`) + books
(`books_<mode>.jsonl.zst`), hash-frozen at publish time. Provably fair is **not** a
contradiction — it is what **selects which pre-generated book** the RGS serves:

```
float = generateFloats( HMAC_SHA256(serverSeed, "clientSeed:nonce:round") )   # ∈ [0,1)
selected book = weighted pick over the mode's LUT using that float
              = "float × possible outcomes" (Stake's docs), applied to the LUT
```

- **Native Stake Dice** (their own game) is formula-based: `roll = float*10001/100`
  (00.00–100.00), win/lose from `roll` vs target. Cursor stays 0 (one float).
- **Our Engine games are LUT-based**: the float picks a book; for dice all LUT
  weights are `1` (optimiser off), so the pick is uniform over the mode's books and
  the win/lose ratio is just the book counts. Odds stay frozen/certified; the
  *selection* is what's verifiable.

## Who owns what — CRITICAL

- **The Stake platform owns seed management.** The RGS API a game talks to has **no
  seed endpoints** (`packages/rgs-fetcher/src/schema.ts` in the web repo: only
  authenticate/balance/play/end-round/bet.event/bet.action/session/game.search).
  You **cannot** build a working client/server-seed + rotate panel in-game — there
  is no API for it. Any in-game seed panel would be a non-functional mock. Don't.
- **The game (you) owns the book contents.** Your job for provably fair is to make
  each book carry a **seed-consistent, reproducible displayed result** so the number
  a player sees matches the RGS-selected book, and to publish odds/hash
  transparency. The platform's fairness modal does the seed→book verification.

## What the book must store (the core change)

Store the displayed result **in the book event**, generated at simulation time with
the per-sim seeded RNG (deterministic → a `/bet/replay` shows the same number), and
**always consistent with `isWin`**. For dice (`games/2_4_dice_kong_climb`):

- `game_executables.py::_roll_for_outcome(direction, target, is_win)` — pick an
  integer-hundredths roll (0..10000, i.e. 00.00–100.00) in the correct half-open
  range, then present as a 2-dp number:
  - `over_NN`  win → roll ∈ (NN, 100.00]   lose → roll ∈ [0.00, NN]
  - `under_NN` win → roll ∈ [0.00, NN)     lose → roll ∈ [NN, 100.00]
  (matches the win rule; a tie at NN is a loss.) Work in **integer hundredths**, not
  floats, to avoid a rounding push across the boundary (e.g. 47.999→48.00 flipping a
  win to a loss).
- `game_events.py::dice_result_event(..., roll=...)` — add `"roll": round(roll, 2)`
  to the emitted event. Keep every existing field.
- RNG is already seeded per-sim by `reset_seed(sim)` in `gamestate.py::run_spin`, so
  `import random; random.randint(lo, hi)` here is reproducible. Consuming a randint
  does not affect which criteria (win/lose) the sim was assigned — that is set before
  `run_spin` by the distribution quotas.

For a **non-dice** game, the same principle applies: store whatever result the UI
reveals (crash point, path, gem, …) in the book, generated seeded and consistent
with the book's payout, so it is stable and matches the selected book.

## Odds are UNCHANGED — but this is still a versioned change

Adding a result field changes **RTP? multiplier? win probability? roll boundaries?
event structure?** → only **event structure**. Per the versioning rule, an
event-structure change means the **books (and their hashes) change → a production
rebuild + republish is required** for it to go live. But win chances, multipliers,
LUT weights and the mode set are untouched, so there is **no re-optimisation** and
no odds/RTP review. Say this explicitly when handing off.

## Web side — consume the stored result (`apps/2-0-dice`)

- `src/game/typesBookEvent.ts` — add the field as **optional** (`roll?: number`) for
  back-compat with older books.
- `src/game/bookEventHandlerMap.ts` and `src/game/actor.ts` (resume path) — use
  `bookEvent.roll ?? syntheticRoll(...)`. Prefer the certified book value; fall back
  to the synthesized one only for pre-field books.
- `src/game/local/localBook.ts::buildDiceEvents` — bake a roll into LOCAL/mock books
  too (reuse `syntheticRoll`) so LOCAL and LIVE take the same `bookEvent.roll` path.
- Before this change the roll was fabricated every render with `Math.random()`
  (`syntheticRoll`), so replays were inconsistent and unverifiable — that is the gap
  this closes.

## Fairness / odds-transparency UI (what CAN ship in prod)

There are TWO independently useful things; only publish what actually works in the
deployed RGS (strict CSP + no public URL for the raw math files):

1. **Per-round outcome** → verified by the **platform's** provably-fair modal
   (seed → book selection → the stored roll). Link out to it; don't rebuild it.
2. **Odds weren't altered** → a **SHA-256 odds-integrity manifest**. The build
   already writes per-file sha256 into `library/configs/config.json`
   (`bookShelfConfig[].tables[].sha256`, `.booksFile.sha256`, from
   `src/write_data/write_configs.py`). Distill it:
   - `games/2_4_dice_kong_climb/fairness_manifest.py` → `publish_files/fairness.json`
     (per-mode: winChance, multiplier, RTP, win/total book counts read from the
     **hashed LUT** — NOT `maxWin`, which is the game-wide wincap identical across
     modes — plus the LUT + books sha256). Kept **out** of the 3 uploaded RGS files;
     it ships bundled in the frontend. Regenerate it **after** the prod rebuild.
   - web `apps/2-0-dice`: `scripts/gen-fairness.mjs` → `src/assets/fairnessManifest.data.ts`;
     `src/game/fairness.ts` (bundled accessor); `src/components/FairnessModal.svelte`
     (per-mode odds + copyable hashes + a "how provably fair works" explainer + a
     link to the platform verifier + **offline** `sha256sum` steps).

### DO NOT ship an in-browser "live re-hash" of the served files
Fetching `lookUpTable_*.csv` / `books_*.jsonl.zst` from the browser to re-hash them
**404s in the live RGS** (the raw math files are served to the RGS backend, not the
frontend, at no public URL) and the deployed artifact's **CSP blocks cross-host
fetches** anyway. Rely on: the published hashes + **offline** verification + the
platform verifier. (This was tried and removed — don't re-add without a real,
CSP-allowed files URL.)

### Prod placement is a product decision
The platform already gives players seed verification in prod, so an in-game modal
mainly adds **per-mode odds/hash transparency**. Whether to show it as a standalone
button, fold it into the game's info/paytable surface, or gate it dev-only is a
UX/compliance call for the game owner — confirm before assuming.

## Build & verify (dev)

The dice folder `2_4_dice_kong_climb` ≠ its `game_id` `2_4_kong_climb`, and paths
derive from `game_id`, so create a symlink first:

```sh
cd math-sdk/games && ln -sf 2_4_dice_kong_climb 2_4_kong_climb          # then rm it after
cd .. && PYTHONPATH="$PWD" env/bin/python games/2_4_dice_kong_climb/run.py            # dev (readable books)
# prod artifacts (upload-ready): compression + format checks ON, then regen fairness.json
COMPRESSION=1 RUN_FORMAT_CHECKS=1 PYTHONPATH="$PWD" env/bin/python games/2_4_dice_kong_climb/run.py
PYTHONPATH="$PWD" env/bin/python games/2_4_dice_kong_climb/fairness_manifest.py
```

Verify: decompress a book and assert every `diceResult.roll` is in the winning range
on `isWin:true` and the losing range on `isWin:false`; re-run the build and confirm
the rolls are **identical** (seeded, not random); confirm `fairness.json` hashes
equal `shasum -a 256` of the served files (book hash changes with the new field, LUT
hash does NOT). Web: after the roll change, LOCAL bets must roll on the win-consistent
side of the target; the Fairness modal renders with no broken live-check button.

## Checklist
- [ ] Result field stored in the book, seeded, consistent with `isWin`/payout.
- [ ] Integer-hundredths (or equivalent) generation — no float-boundary flips.
- [ ] Event field optional on the web type; `?? syntheticRoll` fallback kept.
- [ ] LOCAL mock books carry the field too.
- [ ] Odds/LUT/mode set unchanged; flagged as an event-structure change ⇒ republish.
- [ ] `fairness.json` regenerated after the PROD build; hashes match served files.
- [ ] No in-game seed panel; no in-browser live re-hash; platform owns seeds.
- [ ] Prod visibility of the Fairness UI confirmed with the game owner.
