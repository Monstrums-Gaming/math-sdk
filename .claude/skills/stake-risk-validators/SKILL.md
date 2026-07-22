---
name: stake-risk-validators
description: >-
  Understand and design around Stake's ACP RISK / STAR-RATING validators — the
  SECOND class of upload rejection beyond the three RTP/grid math rules. Use when a
  Stake ACP build is rejected (or downgraded to fewer stars) for volatility, tail, or
  max-payout reasons — e.g. Max Payout, Tail Probability, Expected-Tail-Liability
  (ETL-40x / ETL-10k), CVaR, or "Base Volatility (Std Dev)" — or when deciding how
  HIGH a single payout / max-win can go, why a high-multiplier mode won't pass, or
  where bet-size scaling belongs. These caps are the wall that limited Limbo to 100×
  and removed Plinko's expert tier. Reference: games/2_5_limbo_frankenstein and
  games/2_6_plinko readmes + config docstrings. Complements
  stake-direct-probability-game (the RTP/grid/exact-count rules) and publish-stake-game
  (the upload workflow).
---

# Stake ACP risk / star-rating validators

The ACP gates a game on **two** independent classes of check. The
`stake-direct-probability-game` and `stake-dice-game` skills cover the **first**:
the 0.1× LUT grid, per-mode RTP `[90%, 96.70%]`, and cross-mode spread ≤ 1.00%. This
skill covers the **second** — the **risk / star-rating** validators, which read the
**raw published payouts absolutely** and bound the *shape* of the win distribution.
A build can pass every RTP/grid rule and still be rejected (or rated fewer stars)
here. Neither the SDK nor `execute_all_tests` checks them — they are an **upload-time
unknown** you design conservatively for.

## The validators (what each bounds)

| Validator | Bounds | Fails when |
|---|---|---|
| **Max Payout** | the single largest LUT multiplier | a mode can pay an extreme absolute multiplier (e.g. 50,000×) |
| **Tail Probability** | how often a very large payout occurs | a big payout hits too frequently (e.g. 5,000× ~1.9% of the time) |
| **ETL** (Expected Tail Liability, ETL-40x / ETL-10k) | expected payout *conditional on* being in the loss/liability tail | ~all of a mode's RTP sits in one rare huge win (all-or-nothing) |
| **CVaR** (Conditional Value at Risk) | the mean of the worst-case tail | the tail is heavy / near all-or-nothing |
| **Base Volatility (Std Dev)** | a **floor** on the game's *tamest* mode's payout std | the least volatile mode is too flat (std < 0.60) |

The **star rating** (2-star / 3-star volatility bands) is a function of these. A game
is rated within a band; pushing any mode's shape past the band's envelope drops the
rating or rejects the mode.

## Two lessons this repo already paid for

### 1. Limbo — the ~100× all-or-nothing ceiling (and a volatility FLOOR)

A Limbo mode pays a single target `T×` or `0`, so ~100% of its RTP sits in one win —
maximally tail-heavy. The validators squeeze it from **both** ends
(`games/2_5_limbo_frankenstein/readme.txt`):

- **Ceiling ≈ 100×.** Any target `≥ 150×` fails **ETL-40x** and **CVaR** at both 2-
  and 3-star (`base_100` passes ETL-40x; `base_150` fails it; `base_800` also
  breaches CVaR). So the published ladder stops at **100×**.
- **Floor 1.40×.** The **Base Volatility (Std Dev)** validator rates the game off its
  **tamest** mode, which must be `≥ 0.60`. A two-outcome mode's payout std is

  ```
  std(T) = sqrt(0.96*T − 0.9216)      # for a ~96% win/lose mode
  ```

  so `T = 1.10 / 1.20 / 1.30` give `0.36 / 0.48 / 0.57` (< 0.60) and drag the **whole
  game** under the floor. `T = 1.40` is the first target with `std ≥ 0.60` (0.649),
  so the ladder **starts** there.

Net: 27 modes, `1.40×..100×`, inside the 2-star band on every metric. This window is
narrow and **inherent to single-outcome Limbo** — if a later validator pass still
fails volatility for every mode, no fixed-target mode can reach 0.60 and the mechanic
itself must change (roll a spread of outcomes per round, not `T×`-or-`0`).

### 2. Plinko — tail SHAPE, not edge magnitude

Plinko tried a fourth `expert` difficulty and **removed** it
(`games/2_6_plinko/game_config.py` docstring). The lesson: it is the **shape** of the
tail, not the raw edge size, that trips the 2-star validators. A near all-or-nothing
shape (~99% of drops at the 0.1× floor, a rare huge edge) fails CVaR/ETL/volatility
for rows 11–16 even at a *smaller* edge:

```
high_r16   = 970×  → PASSES     (spread of bins, weight off the extreme)
expert_r11 = 340×  → FAILED     (near all-or-nothing: almost everything at the floor)
```

`high` already sits at the **top of the 2-star volatility envelope** — "the same wall
that capped limbo." There is no 2-star room above it, so no expert tier exists.

## The rules of thumb

1. **Spread the weight, don't just cap the edge.** A distribution with many
   mid-size outcomes tolerates a far larger max-win than an all-or-nothing one. Two
   modes with the *same* max multiplier can land on opposite sides of the CVaR/ETL
   line purely on shape.
2. **~100× is the practical ceiling for an all-or-nothing (single-win) mode.**
   Multi-outcome games (plinko-style bins, chicken-crossing ladders) can publish
   higher maxima *because* the weight is spread (plinko `high_r16 = 970×`).
3. **Respect the volatility FLOOR too.** The tamest mode must be volatile enough
   (std ≥ 0.60). Don't ship a batch of near-1× modes that flatten the game's rating.
4. **Bet-size scaling belongs in the ACP bet-level template, NOT in published
   modes.** The validators read the **raw LUT payout `W` absolutely**, so a "high
   cost" tier that multiplies the stake just inflates `W` — limbo's removed `cost 100`
   tier turned modest targets into 5,000×–50,000× payouts and breached
   Max-Payout / Tail-Probability / ETL-10k. Offer base (cost 1.0) modes and let the
   operator set bet levels in the ACP dashboard (see `publish-stake-game`).

## Workflow when the ACP rejects on risk

1. Identify which validator fired (Max Payout / Tail Prob / ETL / CVaR / Std-Dev) and
   which mode.
2. If it's a **high** validator (ETL/CVaR/Max Payout/Tail Prob): **lower that mode's
   top multiplier** (or drop the mode), or **reshape** the distribution to move weight
   off the extreme tail — then rebuild and re-upload. Do not chase it by editing RTP;
   RTP is already pinned into `[96.00, 96.70]`.
3. If it's the **Std-Dev floor**: your tamest mode is too flat — **raise its
   minimum** (limbo starts at 1.40× for exactly this reason).
4. If **every** mode fails volatility, the mechanic can't satisfy the band at any
   fixed target — change the mechanic to pay a spread of outcomes per round.
5. Never disable a check to pass locally — the ACP re-runs them server-side with no
   exemption.

## Related skills

- **`stake-direct-probability-game`** — the RTP/grid/exact-book-count rules and the family idioms; this skill is the risk-side companion to it.
- **`stake-dice-game`** — dice modes span 14–69% win chance and are *not* risk-bound in practice (compliant maxima are small), so risk rarely bites there.
- **`publish-stake-game`** — where bet-size scaling actually lives (the ACP bet-level template) and the upload steps.
