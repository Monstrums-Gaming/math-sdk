"""Emit games/2_0_porkageddon/docs/PAYTABLE.md from the live GameConfig.

Run from the math-sdk root:  PYTHONPATH="$(pwd)" ./env/bin/python games/2_0_porkageddon/docs/gen_paytable.py
"""

import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
GAME_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, GAME_DIR)

import pork_math as pm  # noqa: E402
from game_config import GameConfig  # noqa: E402

cfg = GameConfig()
rows = cfg.tiers
rtps = [float(r["rtp"]) for r in rows]

out = io.StringIO()
w = out.write

w(f"""# Porkageddon (2_0) — Paytable

The complete published odds for `2_0_porkageddon`, generated from the live
`GameConfig` (see [Regenerating](#regenerating)). Every number here is derived from
`pork_math.py`, not authored by hand.

> **Note:** `self.paytable` in `game_config.py` is **not** this table. It is
> `{{(1, "P"): 1.0}}` — a single dummy symbol that keeps the symbol map
> self-consistent for a boardless game, never evaluated. The real paytable is the
> per-stance outcome table built by `pork_math.build_stances()`.

---

## At a glance

| Property | Value |
|---|---|
| Bet modes | **{len(rows)}** (`{'`, `'.join(r['stance'] for r in rows)}`) |
| Cost multiplier | **1.0x** on every mode (ACP requirement) |
| Books per mode | {rows[0]['num_sims']:,} |
| Payout range | 1.10x – **{max(float(r['max_win']) for r in rows):.1f}x** |
| Realised RTP | **{min(rtps) * 100:.4f}% – {max(rtps) * 100:.4f}%** ({(max(rtps) - min(rtps)) * 100:.5f}pp spread) |
| Payout grid | 0.1x, floor-snapped |
| Optimiser | disabled — published odds equal book counts |

## How a payout is built

One battle is one wager. Each round **both** pigs commit a skill, and each skill's
cost multiplier joins a shared pot before the round resolves (no refunds, even on
the round a pig is killed). The last pig standing takes the pot.

```
raw_pool_units    = sum(player skill costs) + sum(opponent skill costs)
pot payout        = floor_snap_0.1(raw_pool_units / pool_norm)
Golden Pig payout = floor_snap_0.1({pm.CANONICAL_POOL_CENTS / 100:.1f}x * tier)      # pool-independent badge
```

The Golden Pig is drawn **independently of the outcome** and revealed at
matchmaking; a golden battle must still be **won** to pay. Its badge is a fixed
multiple of a canonical {pm.CANONICAL_POOL_CENTS / 100:.1f}x pot rather than the actual pot, so each tier is a
single published payout — which keeps the rare tail from being smeared across a
dozen values and forced to a minimum of one book each.

RTP is not declared, it is derived. Per stance:

```
E[payout | win] = (1 - p) * E[pot] + p * sum_t w_t * badge_t
win_rate        = RTP_TARGET / E[payout | win]          # RTP_TARGET = {float(pm.RTP_TARGET) * 100:.2f}%
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
| Base mode cost | exactly 1.0x | **1.0x** on all {len(rows)} modes |
| Per-mode RTP | 90% – 96.70% | {min(rtps) * 100:.4f}% – {max(rtps) * 100:.4f}% |
| Cross-mode RTP spread | <= 1.00pp | **{(max(rtps) - min(rtps)) * 100:.5f}pp** |
| Payout grid | multiple of 0.1x | every payout, `lut_grid_exempt = False` |

Outstanding: `provider_number` is still a placeholder (`{cfg.provider_number}`) pending the
ACP-assigned value.

The **risk / star-rating** validators (ETL, CVaR, Max Payout, Tail Probability) are
a separate, upload-time gate that neither the SDK nor `execute_all_tests` checks.
See `readme.txt` for this build's posture and the fallback ladder.

---
""")

for row in rows:
    stance = pm.STANCES[row["stance"]]
    num_sims = row["num_sims"]
    body = sorted(c for c in row["count"] if row["kind"][c] == "body")
    gold = sorted((c for c in row["count"] if row["kind"][c] == "golden"))
    win_books = sum(row["count"].values())

    w(f"""
## `{row['stance']}` — {row['label']}

| Property | Value |
|---|---|
| Rounds | {min(stance['rounds'])}–{max(stance['rounds'])} (weights {', '.join(f'{r}: {float(v):.2f}' for r, v in sorted(stance['rounds'].items()))}) |
| Skill cost band | {min(s[0] for s in stance['slots']) / 100:.2f}x – {max(s[0] for s in stance['slots']) / 100:.2f}x |
| Reference chassis HP | {row['hp']} (nominal; per-battle `hpMax` flexes +/-20%) |
| `pool_norm` | {float(row['pool_norm']):.3f} |
| Win chance | **{float(row['win_rate']) * 100:.3f}%** ({win_books:,} of {num_sims:,} books) |
| Golden Pig chance | {float(stance['golden_freq']) * 100:.2f}% |
| Realised RTP | **{float(row['rtp']) * 100:.4f}%** |
| Max win | **{float(row['max_win']):.1f}x** |
| Distinct payouts | {len(row['count'])} ({len(body)} pot rungs + {len(gold)} golden) |

### Skill slots

The stance's canonical slot table, emitted in `porkSetup.slots`. Roll ranges are the
union of every shipped fighter skill at that cost, so no fighter's numbers fall
outside their slot.

| Slot | Cost | Roll range | Canonical name |
|---:|---:|---|---|
""")
    for s in row["slots"]:
        heal = "  *(shares its cost with Penicillin)*" if s["index"] == row["heal_slot"] else ""
        w(f"| {s['index']} | {s['cost']:.2f}x | {s['dmgMin']}–{s['dmgMax']} | {s['name']}{heal} |\n")

    w(f"""
### Pot rungs

The body of the distribution: an ordinary win pays the pot, and because the pot is a
sum of {2 * min(stance['rounds'])}–{2 * max(stance['rounds'])} skill costs it spans a real range rather than one fixed multiplier.

| Payout | Books | Chance |
|---:|---:|---:|
""")
    for cents in body:
        n = row["count"][cents]
        w(f"| {cents / 100:.1f}x | {n:,} | {n / num_sims * 100:.4f}% |\n")

    w("""
### Golden Pig tiers

| Tier | Pot x | Pays | Weight within golden | 1 in N battles | Books | Paid frequency |
|---|---:|---:|---:|---:|---:|---:|
""")
    for tier, mult, weight in stance["golden_tiers"]:
        cents = pm.golden_cents(mult)
        n = row["count"].get(cents, 0)
        drawn = float(stance["golden_freq"] * weight)
        paid = drawn * float(row["win_rate"])
        w(
            f"| {tier.title()} | x{mult} | **{cents / 100:.1f}x** | {float(weight) * 100:.4f}% | "
            f"1 in {round(1 / drawn):,} | {n:,} | 1 in {round(1 / paid):,} |\n"
        )
    w(
        f"\n`E[M] = {float(sum(m * wt for _t, m, wt in stance['golden_tiers'])):.4f}` "
        f"— the tail carries {sum(row['count'][c] * c for c in gold) / (100 * num_sims) / float(row['rtp']) * 100:.2f}% of this mode's RTP.\n"
    )

w(f"""
---

## Losing

| Mode | Losing books | Chance |
|---|---:|---:|
""")
for row in rows:
    w(f"| `{row['stance']}` | {row['loss_count']:,} | {row['loss_count'] / row['num_sims'] * 100:.3f}% |\n")

w(f"""
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
""")

target = os.path.join(GAME_DIR, "docs", "PAYTABLE.md")
with io.open(target, "w", encoding="utf-8") as fh:
    fh.write(out.getvalue())
print(f"wrote {target} ({len(out.getvalue())} bytes, {len(rows)} modes)")
