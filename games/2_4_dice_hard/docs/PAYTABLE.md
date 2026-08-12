# Dice Hard (2_4) — Paytable

The complete odds ladder for `2_4_dice_hard`, generated from the live
`GameConfig` (see [Regenerating](#regenerating)). Every number here is derived,
not authored by hand.

> **Note:** `self.paytable` in `game_config.py` is **not** this table. It is
> `{(1, "D"): 1.0}` — a single dummy symbol that keeps the symbol map
> self-consistent for a boardless game. It is never evaluated. The real paytable
> is the tier ladder built at runtime by `_build_tiers()`.

---

## At a glance

| Property | Value |
|---|---|
| Bet modes | **192** (96 `under_NN` + 96 `over_NN`) |
| Distinct win chances | 96 (2% – 97%) |
| Payout range | 1.01× – **49.00×** (`wincap`) |
| Realised RTP band | **97.18% – 98.00%** (0.82% spread) |
| Payout grid | 0.01× (whole cents), floor-snapped |
| Optimiser | disabled — published odds equal book counts |

## How a row is built

Dice Hard is a direct-probability game: one roll on a 0–100 scale, two outcomes.

```
under_NN  wins if roll < NN         ->  winChance = NN%
over_NN   wins if roll > NN         ->  winChance = (100 - NN)%
```

The payout is **derived from the win chance**, not authored:

```
multiplier = floor((RTP_CEIL / winChance) * 100) / 100      # _cent_mult_below_ceiling
```

Floor-snapping onto the 0.01× grid guarantees realised RTP
(`winChance × multiplier`) never exceeds the 98.00% ceiling. A mode survives only if
it stays payable and in band:

```
multiplier >= 1.01x                   # no no-upside modes (must beat the 1.00x stake)
RTP        in [97.0%, 98.00%]        # realised: 97.18%-98.00%
```

`W/N` is the exact integer book split: reduce `winChance/100` to lowest terms, set
`num_sims = N`, and the mode yields exactly `W` winning books — so the published
odds equal the win chance exactly.

**`under_NN` and `over_(100-NN)` are the same bet.** Verified across all 96 win
chances: the multiplier and RTP are identical in both directions. The table below
therefore has one row per win chance, each backing two modes.

---

## ⚠️ This build cannot be published to Stake Engine

The config is tuned to a **98% RTP ceiling with cent-resolution payouts**, which breaks
two ACP rules at once. Stake's dashboard re-checks both server-side and rejects on
either:

| Rule | Requirement | This build |
|---|---|---|
| RTP cap | 90% – 96.70% | ~98% |
| Payout grid | multiple of 0.1× | whole cents (e.g. 1.01×, 3.37×, 32.66×) |

`lut_grid_exempt = True` only skips the **local** SDK guard; the ACP re-runs it.
This build is for a non-Stake operator/platform or internal testing only.

Cent resolution is what makes the high-win-chance end viable. On the coarse 0.1×
grid the smallest payout above the 1× stake is 1.1×, so a mode only has upside when
`winChance% × 1.1 <= ceiling` — capping roll-under at 89%. Whole cents let 97% pay a
real 1.01×, so both directions reach target 97.

**To make it Stake-legal:** set `RTP_CEIL=0.967`, `RTP_FLOOR=0.957`, `MIN_MULT=1.1`,
snap to the 0.1× grid in `_cent_mult_below_ceiling`, and `lut_grid_exempt=False`,
then rebuild. The ladder will shrink — the 90–97% win-chance rows drop out.

Also outstanding: `provider_number` is still a placeholder (`2`) pending the
ACP-assigned value.

---

## The table

96 rows, descending by win chance. Each row is two bet modes.

| Win chance | `under_NN` | `over_NN` | Payout | Cents | RTP | W/N |
|---:|---|---|---:|---:|---:|---|
| 97% | `under_97` | `over_03` | 1.01x | 101 | 97.97% | 97/100 |
| 96% | `under_96` | `over_04` | 1.02x | 102 | 97.92% | 24/25 |
| 95% | `under_95` | `over_05` | 1.03x | 103 | 97.85% | 19/20 |
| 94% | `under_94` | `over_06` | 1.04x | 104 | 97.76% | 47/50 |
| 93% | `under_93` | `over_07` | 1.05x | 105 | 97.65% | 93/100 |
| 92% | `under_92` | `over_08` | 1.06x | 106 | 97.52% | 23/25 |
| 91% | `under_91` | `over_09` | 1.07x | 107 | 97.37% | 91/100 |
| 90% | `under_90` | `over_10` | 1.08x | 108 | 97.20% | 9/10 |
| 89% | `under_89` | `over_11` | 1.10x | 110 | 97.90% | 89/100 |
| 88% | `under_88` | `over_12` | 1.11x | 111 | 97.68% | 22/25 |
| 87% | `under_87` | `over_13` | 1.12x | 112 | 97.44% | 87/100 |
| 86% | `under_86` | `over_14` | 1.13x | 113 | 97.18% | 43/50 |
| 85% | `under_85` | `over_15` | 1.15x | 115 | 97.75% | 17/20 |
| 84% | `under_84` | `over_16` | 1.16x | 116 | 97.44% | 21/25 |
| 83% | `under_83` | `over_17` | 1.18x | 118 | 97.94% | 83/100 |
| 82% | `under_82` | `over_18` | 1.19x | 119 | 97.58% | 41/50 |
| 81% | `under_81` | `over_19` | 1.20x | 120 | 97.20% | 81/100 |
| 80% | `under_80` | `over_20` | 1.22x | 122 | 97.60% | 4/5 |
| 79% | `under_79` | `over_21` | 1.24x | 124 | 97.96% | 79/100 |
| 78% | `under_78` | `over_22` | 1.25x | 125 | 97.50% | 39/50 |
| 77% | `under_77` | `over_23` | 1.27x | 127 | 97.79% | 77/100 |
| 76% | `under_76` | `over_24` | 1.28x | 128 | 97.28% | 19/25 |
| 75% | `under_75` | `over_25` | 1.30x | 130 | 97.50% | 3/4 |
| 74% | `under_74` | `over_26` | 1.32x | 132 | 97.68% | 37/50 |
| 73% | `under_73` | `over_27` | 1.34x | 134 | 97.82% | 73/100 |
| 72% | `under_72` | `over_28` | 1.36x | 136 | 97.92% | 18/25 |
| 71% | `under_71` | `over_29` | 1.38x | 138 | 97.98% | 71/100 |
| 70% | `under_70` | `over_30` | 1.40x | 140 | 98.00% | 7/10 |
| 69% | `under_69` | `over_31` | 1.42x | 142 | 97.98% | 69/100 |
| 68% | `under_68` | `over_32` | 1.44x | 144 | 97.92% | 17/25 |
| 67% | `under_67` | `over_33` | 1.46x | 146 | 97.82% | 67/100 |
| 66% | `under_66` | `over_34` | 1.48x | 148 | 97.68% | 33/50 |
| 65% | `under_65` | `over_35` | 1.50x | 150 | 97.50% | 13/20 |
| 64% | `under_64` | `over_36` | 1.53x | 153 | 97.92% | 16/25 |
| 63% | `under_63` | `over_37` | 1.55x | 155 | 97.65% | 63/100 |
| 62% | `under_62` | `over_38` | 1.58x | 158 | 97.96% | 31/50 |
| 61% | `under_61` | `over_39` | 1.60x | 160 | 97.60% | 61/100 |
| 60% | `under_60` | `over_40` | 1.63x | 163 | 97.80% | 3/5 |
| 59% | `under_59` | `over_41` | 1.66x | 166 | 97.94% | 59/100 |
| 58% | `under_58` | `over_42` | 1.68x | 168 | 97.44% | 29/50 |
| 57% | `under_57` | `over_43` | 1.71x | 171 | 97.47% | 57/100 |
| 56% | `under_56` | `over_44` | 1.75x | 175 | 98.00% | 14/25 |
| 55% | `under_55` | `over_45` | 1.78x | 178 | 97.90% | 11/20 |
| 54% | `under_54` | `over_46` | 1.81x | 181 | 97.74% | 27/50 |
| 53% | `under_53` | `over_47` | 1.84x | 184 | 97.52% | 53/100 |
| 52% | `under_52` | `over_48` | 1.88x | 188 | 97.76% | 13/25 |
| 51% | `under_51` | `over_49` | 1.92x | 192 | 97.92% | 51/100 |
| 50% | `under_50` | `over_50` | 1.96x | 196 | 98.00% | 1/2 |
| 49% | `under_49` | `over_51` | 2.00x | 200 | 98.00% | 49/100 |
| 48% | `under_48` | `over_52` | 2.04x | 204 | 97.92% | 12/25 |
| 47% | `under_47` | `over_53` | 2.08x | 208 | 97.76% | 47/100 |
| 46% | `under_46` | `over_54` | 2.13x | 213 | 97.98% | 23/50 |
| 45% | `under_45` | `over_55` | 2.17x | 217 | 97.65% | 9/20 |
| 44% | `under_44` | `over_56` | 2.22x | 222 | 97.68% | 11/25 |
| 43% | `under_43` | `over_57` | 2.27x | 227 | 97.61% | 43/100 |
| 42% | `under_42` | `over_58` | 2.33x | 233 | 97.86% | 21/50 |
| 41% | `under_41` | `over_59` | 2.39x | 239 | 97.99% | 41/100 |
| 40% | `under_40` | `over_60` | 2.45x | 245 | 98.00% | 2/5 |
| 39% | `under_39` | `over_61` | 2.51x | 251 | 97.89% | 39/100 |
| 38% | `under_38` | `over_62` | 2.57x | 257 | 97.66% | 19/50 |
| 37% | `under_37` | `over_63` | 2.64x | 264 | 97.68% | 37/100 |
| 36% | `under_36` | `over_64` | 2.72x | 272 | 97.92% | 9/25 |
| 35% | `under_35` | `over_65` | 2.80x | 280 | 98.00% | 7/20 |
| 34% | `under_34` | `over_66` | 2.88x | 288 | 97.92% | 17/50 |
| 33% | `under_33` | `over_67` | 2.96x | 296 | 97.68% | 33/100 |
| 32% | `under_32` | `over_68` | 3.06x | 306 | 97.92% | 8/25 |
| 31% | `under_31` | `over_69` | 3.16x | 316 | 97.96% | 31/100 |
| 30% | `under_30` | `over_70` | 3.26x | 326 | 97.80% | 3/10 |
| 29% | `under_29` | `over_71` | 3.37x | 337 | 97.73% | 29/100 |
| 28% | `under_28` | `over_72` | 3.50x | 350 | 98.00% | 7/25 |
| 27% | `under_27` | `over_73` | 3.62x | 362 | 97.74% | 27/100 |
| 26% | `under_26` | `over_74` | 3.76x | 376 | 97.76% | 13/50 |
| 25% | `under_25` | `over_75` | 3.92x | 392 | 98.00% | 1/4 |
| 24% | `under_24` | `over_76` | 4.08x | 408 | 97.92% | 6/25 |
| 23% | `under_23` | `over_77` | 4.26x | 426 | 97.98% | 23/100 |
| 22% | `under_22` | `over_78` | 4.45x | 445 | 97.90% | 11/50 |
| 21% | `under_21` | `over_79` | 4.66x | 466 | 97.86% | 21/100 |
| 20% | `under_20` | `over_80` | 4.90x | 490 | 98.00% | 1/5 |
| 19% | `under_19` | `over_81` | 5.15x | 515 | 97.85% | 19/100 |
| 18% | `under_18` | `over_82` | 5.44x | 544 | 97.92% | 9/50 |
| 17% | `under_17` | `over_83` | 5.76x | 576 | 97.92% | 17/100 |
| 16% | `under_16` | `over_84` | 6.12x | 612 | 97.92% | 4/25 |
| 15% | `under_15` | `over_85` | 6.53x | 653 | 97.95% | 3/20 |
| 14% | `under_14` | `over_86` | 7.00x | 700 | 98.00% | 7/50 |
| 13% | `under_13` | `over_87` | 7.53x | 753 | 97.89% | 13/100 |
| 12% | `under_12` | `over_88` | 8.16x | 816 | 97.92% | 3/25 |
| 11% | `under_11` | `over_89` | 8.90x | 890 | 97.90% | 11/100 |
| 10% | `under_10` | `over_90` | 9.80x | 980 | 98.00% | 1/10 |
| 9% | `under_09` | `over_91` | 10.88x | 1088 | 97.92% | 9/100 |
| 8% | `under_08` | `over_92` | 12.25x | 1225 | 98.00% | 2/25 |
| 7% | `under_07` | `over_93` | 14.00x | 1400 | 98.00% | 7/100 |
| 6% | `under_06` | `over_94` | 16.33x | 1633 | 97.98% | 3/50 |
| 5% | `under_05` | `over_95` | 19.60x | 1960 | 98.00% | 1/20 |
| 4% | `under_04` | `over_96` | 24.50x | 2450 | 98.00% | 1/25 |
| 3% | `under_03` | `over_97` | 32.66x | 3266 | 97.98% | 3/100 |
| 2% | `under_02` | `over_98` | 49.00x | 4900 | 98.00% | 1/50 |

---

## Notable rows

| | Win chance | Mode | Payout | RTP |
|---|---:|---|---:|---:|
| Max win (`wincap`) | 2% | `under_02` / `over_98` | **49.00×** | 98.00% |
| Safest | 97% | `under_97` / `over_03` | 1.01× | 97.97% |
| Even money | 50% | `under_50` / `over_50` | 1.96× | 98.00% |
| Lowest RTP | 86% | `under_86` / `over_14` | 1.13× | 97.18% |

32 of the 192 modes land exactly on the 98.00% ceiling — these are the win chances
that divide the ceiling cleanly on the cent grid.

## Regenerating

This file is generated. To rebuild it after a `game_config.py` change, run from the
math-sdk root:

```sh
./env/bin/python games/2_4_dice_hard/docs/gen_paytable.py
```

The generator loads `GameConfig` directly, so the table can never drift from the
shipped ladder. It asserts that `under`/`over` multipliers agree at every win
chance and will fail loudly if that stops being true.
