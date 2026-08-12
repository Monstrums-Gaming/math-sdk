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
| Bet modes | **130** (65 `under_NN` + 65 `over_NN`) |
| Distinct win chances | 65 (2% – 70%) |
| Payout range | 1.38× – **48.35×** (`wincap`) |
| Realised RTP band | **96.25% – 96.70%** (0.45% spread) |
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
(`winChance × multiplier`) never exceeds the 96.70% ceiling. A mode survives only if
it stays payable and in band:

```
multiplier >= 1.01x                   # no no-upside modes (must beat the 1.00x stake)
RTP        in [96.2%, 96.70%]        # realised: 96.25%-96.70%
```

`W/N` is the exact integer book split: reduce `winChance/100` to lowest terms, set
`num_sims = N`, and the mode yields exactly `W` winning books — so the published
odds equal the win chance exactly.

**`under_NN` and `over_(100-NN)` are the same bet.** Verified across all 65 win
chances: the multiplier and RTP are identical in both directions. The table below
therefore has one row per win chance, each backing two modes.

---

## ⚠️ This build cannot be published to Stake Engine

The config is tuned to a **97% RTP ceiling with cent-resolution payouts**, which breaks
two ACP rules at once. Stake's dashboard re-checks both server-side and rejects on
either:

| Rule | Requirement | This build |
|---|---|---|
| RTP cap | 90% – 96.70% | ~97% |
| Payout grid | multiple of 0.1× | whole cents (e.g. 1.38×, 3.37×, 32.66×) |

`lut_grid_exempt = True` only skips the **local** SDK guard; the ACP re-runs it.
This build is for a non-Stake operator/platform or internal testing only.

Cent resolution is what makes the high-win-chance end viable. On the coarse 0.1×
grid the smallest payout above the 1× stake is 1.1×, so a mode only has upside when
`winChance% × 1.1 <= ceiling` — capping roll-under at 89%. Whole cents let 97% pay a
real 1.38×, so both directions reach target 97.

**To make it Stake-legal:** set `RTP_CEIL=0.967`, `RTP_FLOOR=0.957`, `MIN_MULT=1.1`,
snap to the 0.1× grid in `_cent_mult_below_ceiling`, and `lut_grid_exempt=False`,
then rebuild. The ladder will shrink — the 90–97% win-chance rows drop out.

Also outstanding: `provider_number` is still a placeholder (`2`) pending the
ACP-assigned value.

---

## The table

65 rows, descending by win chance. Each row is two bet modes.

| Win chance | `under_NN` | `over_NN` | Payout | Cents | RTP | W/N |
|---:|---|---|---:|---:|---:|---|
| 70% | `under_70` | `over_30` | 1.38x | 138 | 96.60% | 7/10 |
| 69% | `under_69` | `over_31` | 1.40x | 140 | 96.60% | 69/100 |
| 68% | `under_68` | `over_32` | 1.42x | 142 | 96.56% | 17/25 |
| 67% | `under_67` | `over_33` | 1.44x | 144 | 96.48% | 67/100 |
| 66% | `under_66` | `over_34` | 1.46x | 146 | 96.36% | 33/50 |
| 64% | `under_64` | `over_36` | 1.51x | 151 | 96.64% | 16/25 |
| 63% | `under_63` | `over_37` | 1.53x | 153 | 96.39% | 63/100 |
| 61% | `under_61` | `over_39` | 1.58x | 158 | 96.38% | 61/100 |
| 60% | `under_60` | `over_40` | 1.61x | 161 | 96.60% | 3/5 |
| 58% | `under_58` | `over_42` | 1.66x | 166 | 96.28% | 29/50 |
| 57% | `under_57` | `over_43` | 1.69x | 169 | 96.33% | 57/100 |
| 56% | `under_56` | `over_44` | 1.72x | 172 | 96.32% | 14/25 |
| 55% | `under_55` | `over_45` | 1.75x | 175 | 96.25% | 11/20 |
| 54% | `under_54` | `over_46` | 1.79x | 179 | 96.66% | 27/50 |
| 53% | `under_53` | `over_47` | 1.82x | 182 | 96.46% | 53/100 |
| 51% | `under_51` | `over_49` | 1.89x | 189 | 96.39% | 51/100 |
| 50% | `under_50` | `over_50` | 1.93x | 193 | 96.50% | 1/2 |
| 49% | `under_49` | `over_51` | 1.97x | 197 | 96.53% | 49/100 |
| 48% | `under_48` | `over_52` | 2.01x | 201 | 96.48% | 12/25 |
| 47% | `under_47` | `over_53` | 2.05x | 205 | 96.35% | 47/100 |
| 46% | `under_46` | `over_54` | 2.10x | 210 | 96.60% | 23/50 |
| 45% | `under_45` | `over_55` | 2.14x | 214 | 96.30% | 9/20 |
| 44% | `under_44` | `over_56` | 2.19x | 219 | 96.36% | 11/25 |
| 43% | `under_43` | `over_57` | 2.24x | 224 | 96.32% | 43/100 |
| 42% | `under_42` | `over_58` | 2.30x | 230 | 96.60% | 21/50 |
| 41% | `under_41` | `over_59` | 2.35x | 235 | 96.35% | 41/100 |
| 40% | `under_40` | `over_60` | 2.41x | 241 | 96.40% | 2/5 |
| 39% | `under_39` | `over_61` | 2.47x | 247 | 96.33% | 39/100 |
| 38% | `under_38` | `over_62` | 2.54x | 254 | 96.52% | 19/50 |
| 37% | `under_37` | `over_63` | 2.61x | 261 | 96.57% | 37/100 |
| 36% | `under_36` | `over_64` | 2.68x | 268 | 96.48% | 9/25 |
| 35% | `under_35` | `over_65` | 2.76x | 276 | 96.60% | 7/20 |
| 34% | `under_34` | `over_66` | 2.84x | 284 | 96.56% | 17/50 |
| 33% | `under_33` | `over_67` | 2.93x | 293 | 96.69% | 33/100 |
| 32% | `under_32` | `over_68` | 3.02x | 302 | 96.64% | 8/25 |
| 31% | `under_31` | `over_69` | 3.11x | 311 | 96.41% | 31/100 |
| 30% | `under_30` | `over_70` | 3.22x | 322 | 96.60% | 3/10 |
| 29% | `under_29` | `over_71` | 3.33x | 333 | 96.57% | 29/100 |
| 28% | `under_28` | `over_72` | 3.45x | 345 | 96.60% | 7/25 |
| 27% | `under_27` | `over_73` | 3.58x | 358 | 96.66% | 27/100 |
| 26% | `under_26` | `over_74` | 3.71x | 371 | 96.46% | 13/50 |
| 25% | `under_25` | `over_75` | 3.86x | 386 | 96.50% | 1/4 |
| 24% | `under_24` | `over_76` | 4.02x | 402 | 96.48% | 6/25 |
| 23% | `under_23` | `over_77` | 4.20x | 420 | 96.60% | 23/100 |
| 22% | `under_22` | `over_78` | 4.39x | 439 | 96.58% | 11/50 |
| 21% | `under_21` | `over_79` | 4.60x | 460 | 96.60% | 21/100 |
| 20% | `under_20` | `over_80` | 4.83x | 483 | 96.60% | 1/5 |
| 19% | `under_19` | `over_81` | 5.08x | 508 | 96.52% | 19/100 |
| 18% | `under_18` | `over_82` | 5.37x | 537 | 96.66% | 9/50 |
| 17% | `under_17` | `over_83` | 5.68x | 568 | 96.56% | 17/100 |
| 16% | `under_16` | `over_84` | 6.04x | 604 | 96.64% | 4/25 |
| 15% | `under_15` | `over_85` | 6.44x | 644 | 96.60% | 3/20 |
| 14% | `under_14` | `over_86` | 6.90x | 690 | 96.60% | 7/50 |
| 13% | `under_13` | `over_87` | 7.43x | 743 | 96.59% | 13/100 |
| 12% | `under_12` | `over_88` | 8.05x | 805 | 96.60% | 3/25 |
| 11% | `under_11` | `over_89` | 8.79x | 879 | 96.69% | 11/100 |
| 10% | `under_10` | `over_90` | 9.67x | 967 | 96.70% | 1/10 |
| 9% | `under_09` | `over_91` | 10.74x | 1074 | 96.66% | 9/100 |
| 8% | `under_08` | `over_92` | 12.08x | 1208 | 96.64% | 2/25 |
| 7% | `under_07` | `over_93` | 13.81x | 1381 | 96.67% | 7/100 |
| 6% | `under_06` | `over_94` | 16.11x | 1611 | 96.66% | 3/50 |
| 5% | `under_05` | `over_95` | 19.34x | 1934 | 96.70% | 1/20 |
| 4% | `under_04` | `over_96` | 24.17x | 2417 | 96.68% | 1/25 |
| 3% | `under_03` | `over_97` | 32.23x | 3223 | 96.69% | 3/100 |
| 2% | `under_02` | `over_98` | 48.35x | 4835 | 96.70% | 1/50 |

---

## Notable rows

| | Win chance | Mode | Payout | RTP |
|---|---:|---|---:|---:|
| Max win (`wincap`) | 2% | `under_02` / `over_98` | **48.35×** | 96.70% |
| Safest | 70% | `under_97` / `over_03` | 1.38× | 96.60% |
| Even money | 50% | `under_50` / `over_50` | 1.93× | 96.50% |
| Lowest RTP | 55% | `under_55` / `over_45` | 1.75× | 96.25% |

6 of the 130 modes land exactly on the 96.70% ceiling — these are the win chances
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
