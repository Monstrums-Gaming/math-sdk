# Porkageddon (2_0) — Paytable

The complete published odds for `2_0_porkageddon`, generated from the live
`GameConfig` (see [Regenerating](#regenerating)). Every number here is derived from
`pork_math.py`, not authored by hand.

> **Note:** `self.paytable` in `game_config.py` is **not** this table. It is
> `{(1, "P"): 1.0}` — a single dummy symbol that keeps the symbol map
> self-consistent for a boardless game, never evaluated. The real paytable is the
> per-stance outcome table built by `pork_math.build_stances()`.

---

## At a glance

| Property | Value |
|---|---|
| Bet modes | **3** (`skirmish`, `brawl`, `bloodbath`) |
| Cost multiplier | **1.0x** on every mode (ACP requirement) |
| Books per mode | 200,000 |
| Payout range | 1.10x – **2000.0x** |
| Realised RTP | **96.3497% – 96.3504%** (0.00075pp spread) |
| Payout grid | 0.1x, floor-snapped |
| Optimiser | disabled — published odds equal book counts |

## How a payout is built

One battle is one wager. Each round **both** pigs commit a skill, and each skill's
cost multiplier joins a shared pot before the round resolves (no refunds, even on
the round a pig is killed). The last pig standing takes the pot.

```
raw_pool_units    = sum(player skill costs) + sum(opponent skill costs)
pot payout        = floor_snap_0.1(raw_pool_units / pool_norm)
Golden Pig payout = floor_snap_0.1(2.0x * tier)      # pool-independent badge
```

The Golden Pig is drawn **independently of the outcome** and revealed at
matchmaking; a golden battle must still be **won** to pay. Its badge is a fixed
multiple of a canonical 2.0x pot rather than the actual pot, so each tier is a
single published payout — which keeps the rare tail from being smeared across a
dozen values and forced to a minimum of one book each.

RTP is not declared, it is derived. Per stance:

```
E[payout | win] = (1 - p) * E[pot] + p * sum_t w_t * badge_t
win_rate        = RTP_TARGET / E[payout | win]          # RTP_TARGET = 96.35%
```

and `pool_norm` is solved by integer bisection so that derived `win_rate` lands on
the stance's target win rate. Book counts are then laid down as exact integers
(`quota = (count + 0.5) / num_sims`, which `get_sim_splits`' `int()` truncation
reproduces exactly), with the loss bucket absorbing the residual and a one-book
correction pass pinning realised RTP.

## Fighters do not affect odds

Books are **fighter-neutral**: a stance publishes one book set whose transcript
addresses skills by *slot index*, and the client renders slot `k` with the chosen
fighter's name, art and rig. Every fighter therefore draws from the same book pool
and has mathematically identical odds — by construction, with nothing to calibrate.
Fighter choice changes pacing and flavour only.

## ACP compliance

| Rule | Requirement | This build |
|---|---|---|
| Base mode cost | exactly 1.0x | **1.0x** on all 3 modes |
| Per-mode RTP | 90% – 96.70% | 96.3497% – 96.3504% |
| Cross-mode RTP spread | <= 1.00pp | **0.00075pp** |
| Payout grid | multiple of 0.1x | every payout, `lut_grid_exempt = False` |

Outstanding: `provider_number` is still a placeholder (`2`) pending the
ACP-assigned value.

The **risk / star-rating** validators (ETL, CVaR, Max Payout, Tail Probability) are
a separate, upload-time gate that neither the SDK nor `execute_all_tests` checks.
See `readme.txt` for this build's posture and the fallback ladder.

---

## `skirmish` — Skirmish

| Property | Value |
|---|---|
| Rounds | 6–8 (weights 6: 0.25, 7: 0.50, 8: 0.25) |
| Skill cost band | 0.50x – 0.90x |
| Reference chassis HP | 235 (nominal; per-battle `hpMax` flexes +/-20%) |
| `pool_norm` | 5.208 |
| Win chance | **47.201%** (94,402 of 200,000 books) |
| Golden Pig chance | 0.60% |
| Realised RTP | **96.3504%** |
| Max win | **10.0x** |
| Distinct payouts | 18 (17 pot rungs + 1 golden) |

### Skill slots

The stance's canonical slot table, emitted in `porkSetup.slots`. Roll ranges are the
union of every shipped fighter skill at that cost, so no fighter's numbers fall
outside their slot.

| Slot | Cost | Roll range | Canonical name |
|---:|---:|---|---|
| 0 | 0.50x | 10–40 | Mutant Serum |
| 1 | 0.75x | 20–45 | Shield Bash |
| 2 | 0.80x | 25–40 | Lasso Wrangle  *(shares its cost with Penicillin)* |
| 3 | 0.85x | 30–55 | Shock Snout |
| 4 | 0.90x | 30–50 | Meat Hook |

### Pot rungs

The body of the distribution: an ordinary win pays the pot, and because the pot is a
sum of 12–16 skill costs it spans a real range rather than one fixed multiplier.

| Payout | Books | Chance |
|---:|---:|---:|
| 1.1x | 1 | 0.0005% |
| 1.2x | 1 | 0.0005% |
| 1.3x | 6 | 0.0030% |
| 1.4x | 148 | 0.0740% |
| 1.5x | 1,212 | 0.6060% |
| 1.6x | 5,609 | 2.8045% |
| 1.7x | 9,654 | 4.8270% |
| 1.8x | 9,363 | 4.6815% |
| 1.9x | 12,903 | 6.4515% |
| 2.0x | 17,516 | 8.7580% |
| 2.1x | 14,533 | 7.2665% |
| 2.2x | 7,766 | 3.8830% |
| 2.3x | 8,111 | 4.0555% |
| 2.4x | 5,793 | 2.8965% |
| 2.5x | 1,168 | 0.5840% |
| 2.6x | 51 | 0.0255% |
| 2.7x | 1 | 0.0005% |

### Golden Pig tiers

| Tier | Pot x | Pays | Weight within golden | 1 in N battles | Books | Paid frequency |
|---|---:|---:|---:|---:|---:|---:|
| Bronze | x5 | **10.0x** | 100.0000% | 1 in 167 | 566 | 1 in 353 |

`E[M] = 5.0000` — the tail carries 2.94% of this mode's RTP.

## `brawl` — Brawl

| Property | Value |
|---|---|
| Rounds | 3–4 (weights 3: 0.50, 4: 0.50) |
| Skill cost band | 0.90x – 1.20x |
| Reference chassis HP | 150 (nominal; per-battle `hpMax` flexes +/-20%) |
| `pool_norm` | 3.706 |
| Win chance | **43.901%** (87,803 of 200,000 books) |
| Golden Pig chance | 1.00% |
| Realised RTP | **96.3497%** |
| Max win | **2000.0x** |
| Distinct payouts | 16 (12 pot rungs + 4 golden) |

### Skill slots

The stance's canonical slot table, emitted in `porkSetup.slots`. Roll ranges are the
union of every shipped fighter skill at that cost, so no fighter's numbers fall
outside their slot.

| Slot | Cost | Roll range | Canonical name |
|---:|---:|---|---|
| 0 | 0.90x | 30–50 | Six-Snout Shooter  *(shares its cost with Penicillin)* |
| 1 | 1.05x | 25–50 | Snout Shot |
| 2 | 1.10x | 30–55 | Snout Lunge |
| 3 | 1.15x | 35–55 | Flying Oink Drop |
| 4 | 1.20x | 40–70 | Boar Charge |

### Pot rungs

The body of the distribution: an ordinary win pays the pot, and because the pot is a
sum of 6–8 skill costs it spans a real range rather than one fixed multiplier.

| Payout | Books | Chance |
|---:|---:|---:|
| 1.4x | 20 | 0.0100% |
| 1.5x | 817 | 0.4085% |
| 1.6x | 10,687 | 5.3435% |
| 1.7x | 21,754 | 10.8770% |
| 1.8x | 9,834 | 4.9170% |
| 1.9x | 236 | 0.1180% |
| 2.0x | 111 | 0.0555% |
| 2.1x | 2,602 | 1.3010% |
| 2.2x | 11,938 | 5.9690% |
| 2.3x | 19,417 | 9.7085% |
| 2.4x | 9,211 | 4.6055% |
| 2.5x | 296 | 0.1480% |

### Golden Pig tiers

| Tier | Pot x | Pays | Weight within golden | 1 in N battles | Books | Paid frequency |
|---|---:|---:|---:|---:|---:|---:|
| Bronze | x5 | **10.0x** | 89.0700% | 1 in 112 | 784 | 1 in 256 |
| Silver | x20 | **40.0x** | 7.7300% | 1 in 1,294 | 68 | 1 in 2,947 |
| Gold | x100 | **200.0x** | 3.0000% | 1 in 3,333 | 26 | 1 in 7,593 |
| Diamond | x1000 | **2000.0x** | 0.2000% | 1 in 50,000 | 2 | 1 in 113,891 |

`E[M] = 10.9995` — the tail carries 10.25% of this mode's RTP.

## `bloodbath` — Bloodbath

| Property | Value |
|---|---|
| Rounds | 2–3 (weights 2: 0.50, 3: 0.50) |
| Skill cost band | 1.20x – 1.50x |
| Reference chassis HP | 138 (nominal; per-battle `hpMax` flexes +/-20%) |
| `pool_norm` | 3.281 |
| Win chance | **39.241%** (78,482 of 200,000 books) |
| Golden Pig chance | 2.00% |
| Realised RTP | **96.3497%** |
| Max win | **2000.0x** |
| Distinct payouts | 16 (12 pot rungs + 4 golden) |

### Skill slots

The stance's canonical slot table, emitted in `porkSetup.slots`. Roll ranges are the
union of every shipped fighter skill at that cost, so no fighter's numbers fall
outside their slot.

| Slot | Cost | Roll range | Canonical name |
|---:|---:|---|---|
| 0 | 1.20x | 40–70 | Extra Hit  *(shares its cost with Penicillin)* |
| 1 | 1.25x | 45–70 | Cleaver Whirl |
| 2 | 1.40x | 45–65 | Piggie Suplex |
| 3 | 1.50x | 50–70 | Arena Slam |

### Pot rungs

The body of the distribution: an ordinary win pays the pot, and because the pot is a
sum of 4–6 skill costs it spans a real range rather than one fixed multiplier.

| Payout | Books | Chance |
|---:|---:|---:|
| 1.4x | 1,664 | 0.8320% |
| 1.5x | 10,738 | 5.3690% |
| 1.6x | 18,524 | 9.2620% |
| 1.7x | 7,108 | 3.5540% |
| 1.8x | 151 | 0.0755% |
| 2.1x | 9 | 0.0045% |
| 2.2x | 1,560 | 0.7800% |
| 2.3x | 10,653 | 5.3265% |
| 2.4x | 16,740 | 8.3700% |
| 2.5x | 7,968 | 3.9840% |
| 2.6x | 1,720 | 0.8600% |
| 2.7x | 66 | 0.0330% |

### Golden Pig tiers

| Tier | Pot x | Pays | Weight within golden | 1 in N battles | Books | Paid frequency |
|---|---:|---:|---:|---:|---:|---:|
| Bronze | x5 | **10.0x** | 84.8667% | 1 in 59 | 1,341 | 1 in 150 |
| Silver | x20 | **40.0x** | 10.0333% | 1 in 498 | 159 | 1 in 1,270 |
| Gold | x100 | **200.0x** | 5.0000% | 1 in 1,000 | 79 | 1 in 2,548 |
| Diamond | x1000 | **2000.0x** | 0.1000% | 1 in 50,000 | 2 | 1 in 127,418 |

`E[M] = 12.2500` — the tail carries 20.53% of this mode's RTP.

---

## Losing

| Mode | Losing books | Chance |
|---|---:|---:|
| `skirmish` | 105,598 | 52.799% |
| `brawl` | 112,197 | 56.098% |
| `bloodbath` | 121,518 | 60.759% |

A loss pays 0. The battle transcript still shows a pot building and a Golden Pig
badge if one was drawn — you can lose a golden fight, and at these win rates you
usually will. That is the point of revealing it at matchmaking.

## Regenerating

This file is generated. To rebuild it after a `pork_math.py` / `game_config.py`
change, run from the math-sdk root:

```sh
PYTHONPATH="$(pwd)" ./env/bin/python games/2_0_porkageddon/docs/gen_paytable.py
```

The generator loads `GameConfig` directly, so the table can never drift from the
shipped odds. `GameConfig._validate()` runs on import and fails loudly if any ACP
rule or internal invariant is broken.
