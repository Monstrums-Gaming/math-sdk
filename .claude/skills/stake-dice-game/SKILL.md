---
name: stake-dice-game
description: >-
  Build, fix, or ACP-compliance-check a Stake-style DICE game (roll over/under) in
  the math-sdk. Use when adding or editing a dice game, choosing dice payouts/RTP,
  or fixing Stake ACP dashboard math rejections on a dice build — e.g. "Return to
  Player must be between 90% and 96.70%", "Cross-Mode RTP Consistency ... Limit:
  <= 0.50%", or "Base Mode STD ... Limit: = 0.60x". Covers the over_NN/under_NN
  model, floor-snapping payouts onto the LUT grid (whole-cent 0.01x is RGS-legal
  since 2026-08), the per-mode + strict cross-mode RTP rules, the per-mode STD
  floor, and the build/verify loop. Reference games: games/2_4_dice_kong_climb
  (Kong Climb, legacy 0.1x-grid ladder — its 0.90% spread predates the strict
  0.50% validator) and games/2_4_dice_hard (cent-grid ladder, deliberately
  NON-STAKE at 98% RTP with the full 2-97 target range; its 2026-08-12 ACP
  rejection is the source of the tightened rules below). Complements the
  publish-stake-game skill, which owns the ACP upload steps.
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

**Reference implementations:** `games/2_4_dice_kong_climb/` (Kong Climb) is the legacy
0.1×-grid ladder; note its 95.7–96.6% band (0.90% spread) predates the strict 0.50%
cross-mode validator and would be rejected if re-uploaded today. `games/2_4_dice_hard/`
is a cent-grid ladder that is **deliberately non-Stake** (98% RTP, full 2–97 target
range — kept for a non-Stake operator after its 2026-08-12 ACP rejection revealed the
tightened validators below; an ACP-compliant 130-mode retune exists in git history at
`017bef6` if ever needed). No shipped game currently implements the compliant pattern —
copy the constants block below, not either game's band. (Kong Climb's folder was
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

## The four ACP math rules a dice game MUST satisfy

The Stake ACP dashboard enforces these **server-side** — the SDK does not fully check them,
so a build can pass locally and still be rejected. All were learned from real rejections
(most recently the 2026-08-12 rejection of `2_4_dice_hard`'s 98%-RTP build); each maps to a
dashboard error.

1. **Payout grid: integer cents; whole-cent (0.01×) is RGS-legal since 2026-08.** Every
   payout is an integer of "cents" (`multiplier × 100`). The old rule — `≥ 10` and a
   multiple of 10 (the 0.1× grid) — is **gone**: the 2026-08-12 ACP rejection of a
   192-mode whole-cent ladder contained ZERO grid errors. A cent-grid game must set
   `self.lut_grid_exempt = True` (the SDK's default guard still enforces the legacy 0.1×
   grid for slot games). Cent resolution is what makes the strict cross-mode spread (rule
   3) satisfiable across a large ladder — 0.1×-grid snapping loses up to a whole RTP point
   per mode.

2. **Per-mode RTP band: 90% ≤ RTP ≤ 96.70%.** Dashboard error:
   *"Return to Player must be between 90% and 96.70%"*. RTP is **derived**, not declared:
   the ACP recomputes it from the published LUT as `EV / cost`
   (`utils/analysis/distribution_functions.py::calculate_rtp`, = `Σ(payout×weight)/Σweight/cost`).
   The `rtp=` you pass to `BetMode` is only metadata. **97% is impossible** — no config
   knob, bonus mode, or cost trick exceeds 96.70% (base cost must be `1.0`; `cost>1` only
   *lowers* RTP). On the cent grid the floor-snap `floor_cent(0.967/w)` pins every mode
   within `0.01·w` of the cap (under_02 lands on 96.70% exactly).

3. **Cross-mode RTP consistency: max − min ≤ 0.50% (STRICT).** Dashboard error:
   *"Cross-Mode RTP Consistency … Value: 0.82% Limit: ≤ 0.50%"*. This is the strict
   reading of the old "±0.5% of each other" phrasing — a ≤1.00% window **no longer
   passes** (Kong Climb's approved 0.90% spread predates this and would be rejected
   today). All modes must fit inside a half-point RTP window; `2_8_market_crash` /
   `2_9_trading_roulette` use [96.15%, 96.65%] and `2_4_dice_hard` uses [96.25%, 96.70%]
   (realised spread 0.45%).

4. **Base Mode STD floor: per-mode payout std ≥ 0.60×.** Dashboard error: *"Base Mode STD
   … Value: 0.17x Limit: = 0.60x"* (the reported value is the worst mode). For a win/lose
   mode paying `M` at win chance `w`, `std = M·sqrt(w·(1−w))`; with RTP ≈ 0.965 the floor
   binds at **winChance ≈ 71%** (`std = RTP·sqrt((1−w)/w)`). High-win-chance/low-multiplier
   rungs are structurally impossible: a 97%-chance 1.01× mode has std 0.17×. Design with
   margin (`2_4_dice_hard` requires ≥ 0.62×, ending its ladder at winChance 70% / 1.38×).
   This is the same ~0.60 floor that sets `2_6_tap_trade`'s 1.4× minimum rung.

Hit-rate itself is still not gated (modes span 2–70% win chance) — but the STD floor means
"too frequent to be volatile" modes are out.

## The compliant design pattern (verified 2026-08-12; shipped in no game — see git `017bef6`)

Floor-snap each multiplier to the largest **cent-grid** value whose RTP does **not** exceed
the cap, then keep only payable, volatile-enough modes inside a ≤0.5%-wide RTP window.
Constants at the top of `game_config.py`:

```python
RTP_CEIL  = 0.967    # 96.70% ACP hard cap (cent grid pins every mode within 0.01·w of it)
RTP_FLOOR = 0.9625   # realised spread 0.45% < the STRICT 0.50% cross-mode limit
MIN_MULT  = 1.01     # payout must beat the stake (the STD floor dominates in practice)
STD_FLOOR = 0.62     # margin over the 0.60x ACP Base-STD floor (binds at winChance ~71%)

def _cent_mult_below_ceiling(win_chance: int, ceil: float) -> float:
    """Largest 0.01x-grid (whole-cent) multiplier with (win_chance% * mult) <= ceil."""
    return int((ceil / (win_chance / 100.0)) * 100 + 1e-9) / 100.0
```

Keep a mode when, after snapping: `payout > 1.00x`, `RTP_FLOOR ≤ RTP ≤ RTP_CEIL`, **and**
`M·sqrt(w(1−w)) ≥ STD_FLOOR`. `wincap` and the advertised `self.rtp` are **derived** from
the surviving modes (max multiplier / max mode RTP) — never hard-code them. This recipe
yields (verified from publish_files, commit `017bef6`): **130 modes** (65 win chances ×
over/under, winChance 2–70%; 52/59/62/65 snap below the RTP floor → ladder gaps, so slider
UIs must snap to the nearest published target), RTP **96.25–96.70%** (spread 0.45%), min
std **0.632×**, wincap **48.35×**, all `cost = 1.0`. (Kong Climb's legacy 0.1×-grid pattern
— RTP_FLOOR 0.957, 72 modes, 0.90% spread — predates the strict spread validator; don't
copy its band.)

**Exact odds via `num_sims`.** For `winChance = c%`, reduce `c/100 = W/N` in lowest terms
(`g = gcd(c, 100)`, `W = c/g`, `N = 100/g`); set the mode's `num_sims = N` so it produces
exactly `W` winning books (published odds == win chance, optimiser off). Quotas use the
floor-safe `+0.5` trick (`win = (W+0.5)/N`, `lose = (N-W+0.5)/N`) so `int(num_sims·quota)`
lands exactly. Integer win chances give `N ≤ 100`; a **non-integer** ladder (to hit exactly
96.70%) needs a larger `N` (e.g. `w = 967/2000` → `num_sims = 2000`) — `num_sims` is
uncapped, so this is fine.

To change how many modes ship, adjust `RTP_FLOOR` (raise it → tighter spread, fewer modes)
— but keep `RTP_CEIL − RTP_FLOOR ≤ 0.005` for the strict cross-mode validator. Do **not**
raise `RTP_CEIL` above `0.967`, and don't lower `STD_FLOOR` below `0.60`.

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
