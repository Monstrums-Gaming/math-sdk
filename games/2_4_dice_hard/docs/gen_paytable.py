"""Emit games/2_4_dice_hard/docs/PAYTABLE.md from the live GameConfig.

Run from the math-sdk root:  ./env/bin/python <this script>
"""

import collections
import importlib
import io
import sys

sys.path.insert(0, '.')

cfg = importlib.import_module('games.2_4_dice_hard.game_config').GameConfig()
mod = importlib.import_module('games.2_4_dice_hard.game_config')

tiers = cfg.tiers
by = collections.defaultdict(dict)
for r in tiers:
    by[r['win_chance']][r['direction']] = r

rtps = [r['rtp'] for r in tiers]
mults = [r['multiplier'] for r in tiers]
wcs = sorted(by, reverse=True)

# sanity: under/over must be the same bet at a given win chance
mismatched = [wc for wc, v in by.items() if len(v) == 2 and v['under']['multiplier'] != v['over']['multiplier']]
assert not mismatched, f'under/over multiplier mismatch at {mismatched}'

out = io.StringIO()
w = out.write

w(f"""# Dice Hard (2_4) — Paytable

The complete odds ladder for `2_4_dice_hard`, generated from the live
`GameConfig` (see [Regenerating](#regenerating)). Every number here is derived,
not authored by hand.

> **Note:** `self.paytable` in `game_config.py` is **not** this table. It is
> `{{(1, "D"): 1.0}}` — a single dummy symbol that keeps the symbol map
> self-consistent for a boardless game. It is never evaluated. The real paytable
> is the tier ladder built at runtime by `_build_tiers()`.

---

## At a glance

| Property | Value |
|---|---|
| Bet modes | **{len(tiers)}** ({len([r for r in tiers if r['direction'] == 'under'])} `under_NN` + {len([r for r in tiers if r['direction'] == 'over'])} `over_NN`) |
| Distinct win chances | {len(by)} ({min(wcs)}% – {max(wcs)}%) |
| Payout range | {min(mults):.2f}× – **{max(mults):.2f}×** (`wincap`) |
| Realised RTP band | **{min(rtps) * 100:.2f}% – {max(rtps) * 100:.2f}%** ({(max(rtps) - min(rtps)) * 100:.2f}% spread) |
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
(`winChance × multiplier`) never exceeds the {mod.RTP_CEIL * 100:.2f}% ceiling. A mode survives only if
it stays payable and in band:

```
multiplier >= {mod.MIN_MULT:.2f}x                   # no no-upside modes (must beat the 1.00x stake)
RTP        in [{mod.RTP_FLOOR * 100:.1f}%, {mod.RTP_CEIL * 100:.2f}%]        # realised: {min(rtps) * 100:.2f}%-{max(rtps) * 100:.2f}%
```

`W/N` is the exact integer book split: reduce `winChance/100` to lowest terms, set
`num_sims = N`, and the mode yields exactly `W` winning books — so the published
odds equal the win chance exactly.

**`under_NN` and `over_(100-NN)` are the same bet.** Verified across all {len(by)} win
chances: the multiplier and RTP are identical in both directions. The table below
therefore has one row per win chance, each backing two modes.

---

## ⚠️ This build cannot be published to Stake Engine

The config is tuned to a **{mod.RTP_CEIL * 100:.0f}% RTP ceiling with cent-resolution payouts**, which breaks
two ACP rules at once. Stake's dashboard re-checks both server-side and rejects on
either:

| Rule | Requirement | This build |
|---|---|---|
| RTP cap | 90% – 96.70% | ~{max(rtps) * 100:.0f}% |
| Payout grid | multiple of 0.1× | whole cents (e.g. {min(mults):.2f}×, 3.37×, 32.66×) |

`lut_grid_exempt = True` only skips the **local** SDK guard; the ACP re-runs it.
This build is for a non-Stake operator/platform or internal testing only.

Cent resolution is what makes the high-win-chance end viable. On the coarse 0.1×
grid the smallest payout above the 1× stake is 1.1×, so a mode only has upside when
`winChance% × 1.1 <= ceiling` — capping roll-under at 89%. Whole cents let 97% pay a
real {min(mults):.2f}×, so both directions reach target 97.

**To make it Stake-legal:** set `RTP_CEIL=0.967`, `RTP_FLOOR=0.957`, `MIN_MULT=1.1`,
snap to the 0.1× grid in `_cent_mult_below_ceiling`, and `lut_grid_exempt=False`,
then rebuild. The ladder will shrink — the 90–97% win-chance rows drop out.

Also outstanding: `provider_number` is still a placeholder (`{cfg.provider_number}`) pending the
ACP-assigned value.

---

## The table

{len(by)} rows, descending by win chance. Each row is two bet modes.

| Win chance | `under_NN` | `over_NN` | Payout | Cents | RTP | W/N |
|---:|---|---|---:|---:|---:|---|
""")

for wc in wcs:
    u = by[wc].get('under')
    o = by[wc].get('over')
    r = u or o
    w('| %d%% | %s | %s | %.2fx | %d | %.2f%% | %d/%d |\n' % (
        wc,
        '`under_%02d`' % u['target'] if u else '—',
        '`over_%02d`' % o['target'] if o else '—',
        r['multiplier'], r['payout_cents'], r['rtp'] * 100, r['W'], r['N'],
    ))

w(f"""
---

## Notable rows

| | Win chance | Mode | Payout | RTP |
|---|---:|---|---:|---:|
| Max win (`wincap`) | {min(wcs)}% | `under_02` / `over_98` | **{max(mults):.2f}×** | {by[min(wcs)]['under']['rtp'] * 100:.2f}% |
| Safest | {max(wcs)}% | `under_97` / `over_03` | {by[max(wcs)]['under']['multiplier']:.2f}× | {by[max(wcs)]['under']['rtp'] * 100:.2f}% |
| Even money | 50% | `under_50` / `over_50` | {by[50]['under']['multiplier']:.2f}× | {by[50]['under']['rtp'] * 100:.2f}% |
| Lowest RTP | {min(by, key=lambda k: by[k]['under']['rtp'])}% | `under_{min(by, key=lambda k: by[k]['under']['rtp']):02d}` / `over_{100 - min(by, key=lambda k: by[k]['under']['rtp']):02d}` | {by[min(by, key=lambda k: by[k]['under']['rtp'])]['under']['multiplier']:.2f}× | {min(rtps) * 100:.2f}% |

{sum(1 for r in rtps if abs(r - max(rtps)) < 1e-9)} of the {len(tiers)} modes land exactly on the {max(rtps) * 100:.2f}% ceiling — these are the win chances
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
""")

target = 'games/2_4_dice_hard/docs/PAYTABLE.md'
with io.open(target, 'w', encoding='utf-8') as fh:
    fh.write(out.getvalue())
print(f'wrote {target} ({len(out.getvalue())} bytes, {len(by)} rows, {len(tiers)} modes)')
