---
name: stake-direct-probability-game
description: >-
  Build, fix, or ACP-compliance-check a Stake-style DIRECT-PROBABILITY game in the
  math-sdk that is NOT a dice game — Limbo, Plinko, Chicken Road, or any new
  boardless game whose odds come straight from the distribution quotas (no reels, no
  free spins, Rust optimiser disabled). Use when adding such a game, choosing its
  payouts/probabilities/RTP, needing exact integer book counts, building a
  multi-outcome (one-Distribution-per-payout) game, or fixing ACP math rejections
  like "Return to Player must be between 90% and 96.70%", "RTP across all modes must
  be within ±0.5% of each other", or off-0.1x-grid payout errors. Reference games:
  games/2_5_limbo_frankenstein (win/lose), games/2_6_plinko + games/2_7_chicken_crossing
  (multi-outcome), games/2_8_chicken_run (win/lose). Complements stake-dice-game (the
  over_NN/under_NN slider variant), stake-risk-validators (the ETL/CVaR/star-rating
  caps that bound how high a payout can go), and publish-stake-game (the ACP upload).
---

# Build an ACP-compliant Stake direct-probability game (non-dice)

A **direct-probability** game draws one outcome per round from a fixed odds table
authored in `game_config.py` — no board, no reels, no free-spin round, no Rust
optimiser. Published odds equal the per-criteria book counts (`round(num_sims ×
quota)`), so **RTP is set by the authored numbers, not an optimiser**. The dice game
(`stake-dice-game`) is the two-outcome integer-slider special case; this skill covers
the rest of the family:

| Game | Ref folder | Shape | Modes |
|---|---|---|---|
| Limbo | `games/2_5_limbo_frankenstein` | win `T×` or lose (2-outcome) | one per target `T` |
| Chicken Run | `games/2_8_chicken_run` | win lane-mult or lose (2-outcome) | 72 = 3 diff × 24 lanes |
| Plinko | `games/2_6_plinko` | **multi-outcome** (one payout per bin) | rows × difficulty |
| Chicken Crossing | `games/2_7_chicken_crossing` | **multi-outcome** cash-out ladder | one per difficulty |

## Start a new game

Copy the **closest existing family game** (NOT `games/template/`, which is
slot-oriented and wrong for this model): a 2-outcome game → copy `2_5_limbo_frankenstein`
or `2_8_chicken_run`; a multi-outcome game → copy `2_6_plinko` or `2_7_chicken_crossing`.
Read the copied `game_config.py` module docstring + `readme.txt` first — nearly
everything below is already implemented there. Then set `game_id`
(`<provider>_<num>_<name>`), `provider_name`, `game_name`, `working_name`, and
`provider_number` (a **placeholder** until you have the real ACP-assigned value).
`game_config.py` is effectively the whole game; the other engine files
(`game_events.py`, `gamestate.py`, `game_executables.py`, `game_override.py`,
`game_calculations.py`) are thin, `game_optimization.py` is a disabled stub, and
`run.py` drives `create_books → generate_configs → execute_all_tests`.

## Boardless scaffolding recipe (identical across the family)

Every family `game_config.py` is a singleton (`__new__`) that sets up a dummy
1×1 board and builds `tiers → bet_modes → validate`:

```python
self.lut_grid_exempt = False           # keep the SDK grid check ON as a guard
self.num_reels = 1
self.num_rows = [1] * self.num_reels
self.tiers = self._build_tiers()
self.wincap = max(t["multiplier"] for t in self.tiers)   # DERIVED, never hard-coded
self.rtp    = max(t["rtp"] for t in self.tiers)          # DERIVED
self.mode_params = {}
self.paytable = {(1, "L"): 1.0}        # one dummy symbol, never evaluated
self.include_padding = False
self.special_symbols = {"wild": [], "scatter": [], "multiplier": []}
self.freespin_triggers = {self.basegame_type: {}, self.freegame_type: {}}
self.anticipation_triggers = {self.basegame_type: 0, self.freegame_type: 0}
# single BR0 reel; padding_reels point base+free at it
self.bet_modes = self._build_bet_modes()
self._validate()
```

Each bet mode uses `dummy_reels = {"reel_weights": {base: {"BR0": 1}, free: {"BR0": 1}}}`
in every `Distribution.conditions`, with `force_wincap`/`force_freegame` flags.

## The three ACP math rules (enforced server-side; SDK does not fully check)

Same three as dice — a build can pass locally and still be rejected at upload:

1. **0.1× LUT grid.** Every non-zero payout, as integer cents (`multiplier×100`),
   must be `≥10` and a multiple of `10`. Keep `lut_grid_exempt = False` so
   `utils/rgs_verification.py::verify_lookup_format` re-enforces it. Never set it
   `True` to "pass" locally — the ACP re-runs the check with no exemption.
2. **Per-mode RTP: 90% ≤ RTP ≤ 96.70%.** RTP is **derived** by the ACP from the
   published LUT as `EV/cost` (`utils/analysis/distribution_functions.py::calculate_rtp`);
   the `rtp=` passed to `BetMode` is only metadata. **97% is impossible — 96.70% is
   the hard ceiling.** A "≈97%" design intent (limbo, chicken) must be capped here.
3. **Cross-mode RTP consistency: spread ≤ 1.00%.** `max(RTP) − min(RTP) ≤ 0.01`.
   (The SDK only *warns* at a looser 5% spread — that is **not** the ACP limit.)

There is also a **fourth** gate — risk / star-rating (ETL / CVaR / volatility) —
that bounds how high a single payout can go and is the wall that capped limbo at
100× and killed plinko's expert tier. It has its own skill: **`stake-risk-validators`**.

## The family conventions

### RTP pin window `[96.00%, 96.70%]`

Every non-dice family game pins realised RTP into a shared narrow window so the
cross-mode spread lands well under the 1.00% cap (~0.70% in practice). Constants at
the top of `game_config.py`:

```python
RTP_CEIL  = 0.967   # 96.70% hard ceiling (inclusive)
RTP_FLOOR = 0.960   # floor → cross-mode spread ≤ 0.70%
# multi-outcome games also aim at a shared target inside the band:
RTP_TARGET = 0.9635 # plinko  (0.965 for chicken_crossing — 0.967 can round a hair
                    #          over the ceiling after integer book rounding)
```

This differs from the dice skill's `RTP_FLOOR = 0.957`; the family runs a tighter,
higher window.

### Exact integer book counts — `_simplest_fraction_in` (2-outcome games)

With the optimiser off, `num_sims × quota` must be an exact integer. For a win/lose
game the win probability is chosen as the **smallest-denominator** rational `a/b`
whose realised RTP `(a/b)·payout` lands in `[RTP_FLOOR, RTP_CEIL]`; then `num_sims =
b` produces exactly `a` winning books. The helper is a Stern-Brocot descent —
**copy-pasted verbatim in `2_5_limbo_frankenstein/game_config.py` (≈L101) and
`2_8_chicken_run/game_config.py` (≈L76)**:

```python
from fractions import Fraction
from math import floor

def _simplest_fraction_in(lo: Fraction, hi: Fraction) -> Fraction:
    """Smallest-denominator fraction x with lo <= x <= hi (requires 0 < lo <= hi)."""
    if lo > hi:
        lo, hi = hi, lo
    n = floor(lo)
    if n >= lo:              # lo is a whole number -> simplest
        return Fraction(n)
    if n + 1 <= hi:          # a whole number lies inside [lo, hi]
        return Fraction(n + 1)
    return n + 1 / _simplest_fraction_in(1 / (hi - n), 1 / (lo - n))
```

Usage per payout (`p_frac = Fraction(payout_cents, 100)`):

```python
lo = Fraction(round(RTP_FLOOR * 1000), 1000) / p_frac
hi = Fraction(round(RTP_CEIL  * 1000), 1000) / p_frac
prob = _simplest_fraction_in(lo, hi)
W, N = prob.numerator, prob.denominator     # W winning books out of num_sims = N
```

Because numerator-1 fractions win for large payouts, `N` stays small (limbo
`base_100 → 1/104`), so each mode fits a single batch and the split stays exact.

### Floor-safe `+0.5` quota split (all family games)

`create_books` assigns criteria via `int(num_sims × quota)`. To make that land on
the exact integer count, offset each quota by `+0.5`:

```python
win_quota  = (W + 0.5) / N
lose_quota = (N - W + 0.5) / N
# generalises to N outcomes: each quota = (count_k + 0.5)/num_sims; counts sum to num_sims
assert int(N * win_quota) + int(N * lose_quota) == N     # asserted in _validate()
```

### Multi-outcome: one `Distribution` per distinct payout (Plinko, Chicken Crossing)

When a round can pay more than two values, declare **one `Distribution` per distinct
payout value** (bins/steps that snap to the same multiplier are pooled), plus a loss
bucket where applicable. The top payout routes to the `"wincap"` criteria, the rest
to per-payout `p_<cents>` criteria.

- **Plinko** — bin `k` has binomial weight `C(N,k)/2ᴺ`, so choosing `num_sims = 2**N`
  makes each bin's book count exactly `C(N,k)` (an integer for free). Pool bins by
  cents: `quota = (Σ C(N,k) over that payout's bins + 0.5)/2**N`. Cells are
  grid-aligned, symmetric, monotone-toward-centre, and RTP-tuned onto the grid by a
  coordinate-descent solver (`_fit_cells`) to hit `RTP_TARGET`; if an edge is too
  large for any in-band table to exist, the solver lowers the edge.
- **Chicken Crossing** — raw ladder multipliers are floor-snapped and the *loss
  bucket absorbs the integer-rounding residual* so counts sum to `num_sims`
  (default `1e6`); realised RTP is recomputed from the integer counts.

### Floor-snap + probability compensation (Chicken Crossing)

When you must publish an off-grid raw multiplier, **floor-snap** it (never round up)
and then *raise the reach probability* to pin RTP back after the snap lowered the
payout:

```python
def _snap_floor(mult: float) -> float:
    return (int(mult * 10 + _EPS)) / 10.0     # floor onto the 0.1x grid

# floor-snapping lowers the payout, so compensate the probability of reaching step k:
rho_k = RTP_TARGET / snapped_k                # <= 1 always (snapped_k >= 1.0 > RTP_TARGET)
q_k   = w_k * rho_k                           # w_k = target-step weight (shapes volatility only)
q_loss = 1 - sum(q_k)
```

Because `q_k · snapped_k = w_k · RTP_TARGET`, the overall RTP equals `RTP_TARGET` for
**any** weight `w_k` — the weight tunes hit-frequency/volatility, never RTP. (This
differs from limbo/chicken_run, which use grid-aligned targets and adjust only the
probability, and from the dice ceiling-snap.)

### Global max-win cap + forbidden-max guard (Chicken Crossing)

An env-configurable `GLOBAL_MAX_MULT` (default `2000`) drops every ladder step at or
above it, and a `_FORBIDDEN_MAX` assertion guarantees a specific uncapped tail (the
`3,170,697.20×` Daredevil rung) is **never** published. Env overrides
(`RTP_TARGET`, `GLOBAL_MAX_MULT`, `NUM_SIMS`) allow a one-switch retune.

### `_validate()` — assert everything before the engine runs

Mirror the existing `_validate()`: `wincap == max(multiplier)`; mode count matches
the tier count; cross-mode `max(rtp) − min(rtp) ≤ 0.01`; each payout is an integer
`≥100` cents and a multiple of `10`; per-mode `(W/N)·payout ∈ [RTP_FLOOR, RTP_CEIL]`;
base modes are `cost == 1.0`; and the `+0.5` splits sum to `num_sims`. For a
strictly-increasing ladder (chicken_run) assert monotonicity too.

### Mode names must be DOT-FREE

The ACP publisher parses `<mode>` out of `books_<mode>.jsonl.zst` /
`lookUpTable_<mode>_0.csv`, so a `.` collides with the `.jsonl.zst` extension and the
dashboard rejects the upload (`"Mode: base_1.10 error … io error"`). Build names with
`f"{tier}_{target:.2f}".replace(".", "_")` (limbo `base_1_40`) or plain tokens
(chicken_run `easy_1`, plinko `base_r16_high`).

## Build & verify

Run from the **repo root** with the venv; `PYTHONPATH="$(pwd)"` is required (`src`
resolves via cwd, not the editable install).

```sh
# Wipe stale generated output first — leftover LUTs/books from a prior/larger build
# are read by execute_all_tests and cause off-grid / "Payout hash mismatch" failures.
rm -rf games/<game_id>/library

# Production build: compression is mandatory for the format checks.
PYTHONPATH="$(pwd)" COMPRESSION=1 RUN_FORMAT_CHECKS=1 ./env/bin/python games/<game_id>/run.py
```

`execute_all_tests` must **exit 0 with no warnings**. A `Mode RTP difference exceedes
allowed difference for approvals` warning means spread > 5% (SDK guard) — the real
ACP limit is 1.00%, so keep the `[96.00, 96.70]` pin. Independent re-derivation of
the numbers the ACP will compute (adapt the dice skill's `publish_files` snippet:
`RTP = Σ(payout×weight)/Σweight/100` per mode, assert grid + `cost==1.0` + spread).

## Gotchas

- **`PYTHONPATH="$(pwd)"`** or `src` import fails (`ModuleNotFoundError: No module named 'src'`).
- **Wipe `library/` before every rebuild** — stale files from removed modes fail the grid / hash check.
- **`provider_number`** stays a placeholder until you have the real ACP-assigned value.
- **`lut_grid_exempt = False` always** — never flip it to force a local pass.
- **The 96.70% ceiling is real** — a `RTP_TARGET = 0.97` (chicken_crossing's default)
  fails ACP; ship at `0.965`. RTP is what the LUT computes, not what you declare.
- **`frontend_demo/`** (limbo, plinko, chicken_crossing): regenerate its bundle after
  a rebuild so the demo replays the published math.

## Related skills

- **`stake-dice-game`** — the two-outcome `over_NN`/`under_NN` integer-slider variant (uses a gcd reduction instead of `_simplest_fraction_in`, and a lower `RTP_FLOOR`).
- **`stake-risk-validators`** — the ETL/CVaR/volatility star-rating caps: why limbo tops out at 100× and plinko has no expert tier. Read it before pushing any payout into the hundreds-of-× range.
- **`publish-stake-game`** — the ACP dashboard upload + bet-level template steps for the finished build.
