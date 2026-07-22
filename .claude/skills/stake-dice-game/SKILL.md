---
name: stake-dice-game
description: >-
  Build, fix, or ACP-compliance-check a Stake-style DICE game (roll over/under) in
  the math-sdk. Use when adding or editing a dice game, choosing dice payouts/RTP,
  or fixing Stake ACP dashboard math rejections on a dice build — e.g. "Return to
  Player must be between 90% and 96.70%", "RTP across all modes must be within
  ±0.5% of each other", or off-grid payout errors. Covers the over_NN/under_NN
  model, floor-snapping payouts onto the 0.1x LUT grid, the per-mode + cross-mode
  RTP rules, and the build/verify loop. Reference game: games/2_4_dice_kong_climb
  (Kong Climb). Complements the publish-stake-game skill, which owns the ACP upload steps.
---

# Build an ACP-compliant Stake dice game (math-sdk)

A **dice** game is a *direct-probability* game (like `games/mystery_box`), **not** a
reel/slot: no board, no reels, no free-spin round, no Rust optimiser. Each round is one
roll on a 0–100 scale and there are exactly two outcomes — **win** (fixed multiplier) or
**lose** (0). The odds come straight from the distribution quotas.

Canonical Stake format — one bet mode per integer slider target `NN`, in each direction:

```
under_NN   wins if roll < NN    ->  winChance = NN%
over_NN    wins if roll > NN    ->  winChance = (100 - NN)%
```

**Reference implementation:** `games/2_4_dice_kong_climb/` (Kong Climb). It is the only
dice game and the source of truth — read its `game_config.py` module docstring and
`readme.txt` first. Almost everything below is already implemented there. (The folder was
renamed from `2_4_kong_climb`, but its internal `game_id` is still `"2_4_kong_climb"` — so
build/verify commands that take a `game_id`, like `python -m utils.rgs_verification -g
2_4_kong_climb`, use the old string while the path uses the new one.)

## Start a new dice game

Copy **`games/2_4_dice_kong_climb/`** (NOT `games/template/`, which is slot-oriented), then:

- Set `game_id` (`<provider>_<num>_<name>`), `provider_name`, `game_name`, `working_name`,
  and `provider_number` in `game_config.py`. `provider_number` is a **placeholder** — set
  the real ACP-assigned value before the production upload.
- `game_config.py` is the whole game: it builds the `over_NN`/`under_NN` tiers, floor-snaps
  the payouts, filters to the compliant RTP window, and derives `wincap`. The rest inherit:
  `game_events.py` emits `diceResult` + `finalWin`; `gamestate.py` / `game_executables.py` /
  `game_override.py` / `game_calculations.py` are thin; `game_optimization.py` is a disabled
  stub (dice has no optimiser); `run.py` drives `create_books → generate_configs →
  execute_all_tests`.

## The three ACP math rules a dice game MUST satisfy

The Stake ACP dashboard enforces these **server-side** — the SDK does not fully check them,
so a build can pass locally and still be rejected. All three were learned from real
rejections; each maps to a dashboard error.

1. **0.1x LUT grid.** Every non-zero payout, as integer "cents" (`multiplier × 100`), must
   be `≥ 10` **and a multiple of 10** (i.e. a whole multiple of `0.1x`). The true dice
   multiplier `0.97 / winChance` almost never lands on this grid (50% → 1.94x, 3% → 32.33x),
   so you must snap it. Keep `self.lut_grid_exempt = False` (`game_config.py`) so the SDK's
   `utils/rgs_verification.py::verify_lookup_format` re-enforces the grid as a guard.
   *Do not* set `lut_grid_exempt = True` to "pass" locally — the ACP re-runs the check and
   has no exemption.

2. **Per-mode RTP band: 90% ≤ RTP ≤ 96.70%.** Dashboard error:
   *"Return to Player must be between 90% and 96.70%"*. RTP is **derived**, not declared:
   the ACP recomputes it from the published LUT as `EV / cost`
   (`utils/analysis/distribution_functions.py::calculate_rtp`, = `Σ(payout×weight)/Σweight/cost`).
   The `rtp=` you pass to `BetMode` is only metadata. So:
   - **97% is impossible.** The hard ceiling is **96.70%**. There is no config knob, bonus
     mode, or cost trick to exceed it (base cost must be `1.0`; `cost>1` only *lowers* RTP).
   - With **integer** win chances the realised max is **96.60%** (the grid can't hit 96.70%
     exactly for any integer `c`). Reaching exactly 96.70% requires a **non-integer** win
     chance ladder: pick a grid multiplier `M`, set `w = 0.967 / M` (e.g. `M=2.0 →
     w=48.35%`), which needs a larger `num_sims` (see below).

3. **Cross-mode RTP consistency: variance ≤ 1.00%.** Dashboard error: *"RTP across all
   modes must be within ±0.5% of each other"* → `max(RTP) − min(RTP) ≤ 1.00%`. This is the
   binding constraint on how many modes you can ship: they must all fit inside a 1%-wide RTP
   window. (The SDK only *warns* at a looser 5% spread — that warning is **not** the ACP
   limit.)

**NOT a rule:** volatility / hit-rate. Compliant modes span 14–69% win chance; do not trim
modes for being "too rare" or "too frequent". Only RTP + grid gate a dice mode.

## The compliant design pattern (already in Kong Climb)

Floor-snap each multiplier to the largest `0.1x`-grid value whose RTP does **not** exceed
the cap, then keep only payable modes inside a ≤1%-wide RTP window. Constants at the top of
`game_config.py`:

```python
RTP_CEIL  = 0.967   # 96.70% hard cap (grid keeps realised max at 96.60%)
RTP_FLOOR = 0.957   # pin so max-min stays < 1.00% cross-mode variance
MIN_MULT  = 1.1     # payout must beat the stake (drop no-upside 1.0x modes)

def _grid_mult_below_ceiling(win_chance: int, ceil: float) -> float:
    """Largest 0.1x-grid multiplier with (win_chance% * mult) <= ceil (FLOOR-snap)."""
    max_cents = int((ceil / (win_chance / 100.0)) * 100 + 1e-9)
    return ((max_cents // 10) * 10) / 100.0
```

Keep a mode when, after snapping: `payout > 1.00x` **and** `RTP_FLOOR ≤ RTP ≤ RTP_CEIL`.
`wincap` and the advertised `self.rtp` are **derived** from the surviving modes (max
multiplier / max mode RTP) — never hard-code them. Kong Climb's current result: **72 modes**
(36 win chances × over/under, winChance 2–48%), RTP **95.7–96.6%** (variance 0.90%), wincap
**48.3x**, all `cost = 1.0`.

**Exact odds via `num_sims`.** For `winChance = c%`, reduce `c/100 = W/N` in lowest terms
(`g = gcd(c, 100)`, `W = c/g`, `N = 100/g`); set the mode's `num_sims = N` so it produces
exactly `W` winning books (published odds == win chance, optimiser off). Quotas use the
floor-safe `+0.5` trick (`win = (W+0.5)/N`, `lose = (N-W+0.5)/N`) so `int(num_sims·quota)`
lands exactly. Integer win chances give `N ≤ 100`; a **non-integer** ladder (to hit exactly
96.70%) needs a larger `N` (e.g. `w = 967/2000` → `num_sims = 2000`) — `num_sims` is
uncapped, so this is fine.

To change the RTP target or how many modes ship, adjust `RTP_FLOOR` (raise it → tighter
variance, fewer modes; the realised max is fixed near 96.60% by the grid). Do **not** raise
`RTP_CEIL` above `0.967`.

## Build & verify

Run from the **repo root** with the venv. `PYTHONPATH="$(pwd)"` is required — `src` resolves
via cwd, not the editable install.

```sh
# Wipe stale generated output first — leftover files from a prior/larger build fail the
# grid or book<->LUT hash check (execute_all_tests reads publish_files/, not just new modes).
rm -rf games/<game_id>/library

# Production build with format checks ON (compression is mandatory for the checks).
PYTHONPATH="$(pwd)" COMPRESSION=1 RUN_FORMAT_CHECKS=1 ./env/bin/python games/<game_id>/run.py
```

`execute_all_tests` must **exit 0 with no warnings**. A `Mode RTP difference exceedes
allowed difference for approvals` warning means variance > 5% (SDK guard) — the real ACP
limit is 1%, so tighten `RTP_FLOOR` well before that fires.

Independent re-derivation from the published files (the numbers the ACP will compute):

```sh
cd games/<game_id>/library/publish_files && python3 -c "
import glob,csv,json
idx=json.load(open('index.json')); v=[]
for m in idx['modes']:
    rows=list(csv.reader(open(m['weights'])))
    tot=sum(int(r[1]) for r in rows); s=sum(int(r[1])*int(r[2]) for r in rows)
    v.append(s/tot/100)
    assert all(int(r[2])==0 or (int(r[2])>=10 and int(r[2])%10==0) for r in rows), m['name']+' off-grid'
    assert m['cost']==1.0, m['name']+' cost!=1.0'
print('modes',len(idx['modes']),'RTP %.2f-%.2f%% variance %.2f%%'%(min(v)*100,max(v)*100,(max(v)-min(v))*100))
assert all(0.90<=x<=0.967 for x in v), 'RTP out of [90,96.70]'
assert (max(v)-min(v))<=0.01+1e-9, 'variance > 1.00%'
print('ACP math rules: PASS')
"
```

## Gotchas

- **`PYTHONPATH="$(pwd)"`** or `src` import fails (`ModuleNotFoundError: No module named 'src'`).
- **Wipe `library/` before every rebuild** — stale LUTs/books from removed modes are read by
  the verifier and cause off-grid / `Payout hash mismatch` failures.
- **`provider_number`** stays a placeholder until you have the real ACP-assigned value.
- **Frontend demo** (if present, `frontend_demo/`): regenerate the bundle after a rebuild
  (`build_demo_data.py`), and make the slider **snap to the nearest published target** — the
  compliant mode set is sparse (gaps), so an exact-target lookup returns `undefined`.

## Upload

Once the build passes, uploading the three `publish_files/` (`index.json`,
`books_<mode>.jsonl.zst`, `lookUpTable_<mode>_0.csv`) to the ACP dashboard and the bet-level
template are covered by the **`publish-stake-game`** skill — use that for the release steps.
