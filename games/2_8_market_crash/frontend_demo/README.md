# Market Crash (2_8) — frontend demo

A self-contained browser mockup of the Market Crash mechanic: set a **SELL AT** cash-out
multiplier, watch a market index climb from `1.00×`, and either sell at your target or get
**rugged** short of it.

It is independent of the published RGS frontend config and of the build pipeline — a
preview of the mechanic and a reference for whoever wires the real Svelte app
(`monstrums-web-sdk/apps/2-8-market-crash`).

## Run

```sh
./run.sh                       # http://localhost:7921/
PORT=8123 ./run.sh
```

A static server is required (the page fetches `market_crash_rgs.json`; `file://` is blocked
by CORS).

## Two modes

**LOCAL** (default) replays the **published odds**. It picks an outcome from the lookup
table's weights, then picks a **real certified `crashPoint`** from that mode's sampled book
values. Neither the outcome nor the rug is invented client-side — this is the whole point of
the game, and the demo respects it. Play money starts at $1,000.

**LIVE** places real RGS bets at the selected `crash_<cents>` mode:

```
http://localhost:7921/?rgs_url=<url>&sessionID=<id>&currency=USD
```

Two RGS quirks the code handles, both worth knowing before porting:

- `round.payoutMultiplier` is a **plain** multiplier, while the nested `state[]` events use
  the book's **integer-hundredths** scale. Read money from the round, the crash point from
  the event.
- `/wallet/end-round` is called **only on a win**. A loss is already settled inside the
  `/wallet/play` response.

`?mode=crash_250` opens directly on a rung.

## Regenerate the data bundle

```sh
PYTHONPATH="$PWD" ./env/bin/python games/2_8_market_crash/frontend_demo/build_demo_data.py
```

Reads `library/publish_files/{index.json,lookUpTable_*,books_*}` plus
`library/configs/event_config_*.json`, re-asserts that each mode's LUT payout matches its
`crash_<cents>` name and that every sampled crash point agrees with its own outcome, then
writes `market_crash_rgs.json` (~180 KB: 30 modes × 300 win + 300 lose real crash points,
sampled under a fixed seed so the bundle is reproducible).

## How the chart works

The chart is **ported from `apps/2-7-prediction-market/src/components/Scene.svelte`** — it is
a market index **price** chart, and the multiplier is the price relative to the bet-time price
(drawn as the dashed baseline, `= 1.00×`, exactly like 2-7's). Two pieces of that engine are
what make it look alive, and both must survive any port:

**1. The y-axis auto-ranges to the visible data every frame** (`Scene.svelte:143-153`). `lo`/`hi`
come from the series, seeded with the baseline price so it is always in frame, and the
half-range is inflated `× 1.4`. Data therefore occupies `1/1.4 ≈ 71%` of the band height,
centred — the line always fills the plot and never touches an edge. (Measured on this demo:
70.9%.) A `max(..., price * 0.0012)` floor stops flat data degenerating. Eased with a 240 ms
time constant.

> An earlier revision of this demo instead put the **multiplier** on the y-axis and anchored it
> at `1.00×` with a fixed top at `target × 1.18`. Between rounds the index wanders in a
> 1.00–1.06 band, which then had nowhere to go but the bottom 3% of the plot — the line sat
> pinned along the floor and looked dead. **Do not re-anchor the axis.**

**2. Sub-cell scroll** (`Scene.svelte:541-568`). `glide` is a *fractional* point index
subtracted from every x, so the tape slides continuously and consumes a point when it crosses
1. The head barely moves; the grid and the tape do.

The round itself, in log space: `ln m(u) = u·ln(C) + A(u)·bell(u)·X(u)`. The backbone
`u·ln(C)` is the exponential climb (convex on the linear axis — the classic upward-bending
crash curve); **`X(u)` is a seeded excursion field** — three momentum waves (pumps that slow,
correct and rebound; sideways consolidations where their slope cancels the backbone), one
volatility burst (a jumpy stretch somewhere in the round, calm elsewhere), and fine jitter —
which is what makes the climb read as a real pump-and-dump instead of a near-straight line.
Its parameters derive from the round seeds through an integer hash (**no `Math.random()` in
the path**), so the path is a pure `(u, seeds)` function: replayable, testable, and a
different pattern every round.

The amplitude `A(u)` keys off the height climbed **so far** (`min(u·ln C, ln 8) × 0.35`),
never off `ln C` — the anti-leak property: the wobble cannot telegraph where the round will
end. `m(0) = 1` and `m(1) = crashPoint` exactly, because the envelope is zero at both ends.
Duration saturates in `log(crashPoint)` (1.1 s → 3.4 s); on a win the post-sell tail is
compressed into a fixed 620 ms budget so a `143×` tail after a `2×` sell doesn't run seconds
of dead time. On a win, **SOLD fires at the first touch** of the sell price (the path is
non-monotone now — a later dip back below the line is honest market behaviour, not a revoked
win), and the big multiplier readout **ratchets on the round's high-water mark** so dips
never tick it down. After the rug the market breaks down in a **liquidation cascade** — two
near-vertical dump legs, a dead-cat bounce, then a fast bleed back under the baseline —
which also keeps the index anchored around its base over many rounds instead of drifting
multiplicatively upward.

The **SELL AT line** is only pulled into the auto-range once it is within 35% above the head;
before that it is a pinned dashed marker at the top edge with an `↑`. Forcing a `100×` target
into frame from the start would squash the climb into the bottom sliver — the very defect
above. While idle the marker is shown dimmed against the live price, so the player can see
where the goal sits before committing.

Five invariants the port must keep:

- **A loss must never visually touch the SELL AT line.** An excursion can push a near miss
  (rug `4.97` against a `5.00` sell) across it, which reads as a stolen win. The loss branch is
  clamped strictly below the line.
- **The path must never draw above the crash point** — the rug is the round's maximum, and a
  peak above the stamped value contradicts the story.
- **The animation must land on `crashPoint` exactly**, including on the reduced-motion and
  backgrounded-tab paths — both still stamp the certified value.
- **No overlapping rounds.** The promise resolves at the rug so the money settles promptly
  (matching the RGS, where a loss is settled inside `/wallet/play`), but the post-rug collapse
  keeps draining for ~1 s afterwards. Betting is gated on `round` as well as `busy`, or a second
  bet pins its `1.00×` baseline to a price that is still falling.
- **The axis labels are right-aligned** against the reserved column — the multiplier readout owns
  the top-left, and a left-aligned SELL label collides with it whenever the line is high.

## Not carried over from 2-7's demo

The Prediction Market demo hard-codes `modes.base` and posts `mode:"base"`, which stopped
existing when it moved to a tier ladder — so that page is inert and has no tier selector at
all. This one derives its entire ladder from the bundle, parses the target out of the mode
key, and cross-checks that key against the payout at load time (it throws rather than
silently mis-pricing a rung).

One 2-7 bug deliberately *not* inherited: its forward grid-column loop (`Scene.svelte:360-368`)
is dead code — with a 24-point pitch at `rest = 0.9W` its first candidate x lands past the right
edge, so columns never stream in from the right. This demo uses a 20-point pitch (`0.15W`), which
actually draws.

`window.__mc` exposes the chart state (series, view range, round, band geometry) for poking at
in the console or asserting against in a browser test.
