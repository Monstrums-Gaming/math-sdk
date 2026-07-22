---
name: mystery-box-manifest
description: >-
  Author or fix a JSON manifest for the dynamic mystery-box generator
  (games/mystery_box_dynamic/manifests/*.json) — the way to add a direct-probability
  mystery-box game WITHOUT hand-writing a games/<id>/ folder. Use when creating a new
  mystery box, editing prize odds/payouts, choosing cost_model (unit vs box_cost),
  picking num_sims so num_sims×prob is integral, or fixing build failures like a
  non-integer book-count drift or the ACP "Base Mode Cost must be 1.0x" rejection.
  Reference: games/mystery_box_dynamic/manifests/cash_paradise_unit.json + that
  folder's README.md / BUILD.md. Complements publish-stake-game (ACP upload) and
  mystery-box-build-service (build the manifest over HTTP).
---

# Author a mystery-box manifest (`games/mystery_box_dynamic/`)

`games/mystery_box_dynamic/` builds **any** direct-probability mystery-box game from
a JSON **manifest** — add a game by adding a manifest under `manifests/`, not by
copying a `games/<id>/` folder. The engine derives every output path from the
manifest's `game_id`, so each manifest builds into its own auto-created
`games/<game_id>/library/` tree. **The six engine `.py` files are generic copies of
the `mystery_box` engine — never edit them per-game; author a manifest.**

## Manifest shape

```jsonc
{
  "game_id": "my_box",                 // drives output dir + published gameID (must be UNIQUE)
  "provider_number": 3, "provider_name": "monstrum",  // provider_number is a PLACEHOLDER — set real ACP value before prod upload
  "game_name": "My Box", "working_name": "My Box",
  "box_cost": 4.98,                    // box price in base-bet units
  "wincap": 1000,                      // max multiplier (box_cost mode); DERIVED in unit mode
  "rtp": 0.85,                         // declared RTP (< 1.0)
  "cost_model": "box_cost",            // "box_cost" (default) | "unit"  — see below
  "build": { "num_sims": 100000, "compression": true, "run_format_checks": true,
             "num_threads": 1, "batching_size": 50000, "sample_events": 100 },
  "prizes": {                          // authored exactly as the internal prize_table
    "P1": { "name": "$0.01 Voucher", "payout": 0.01, "prob": 0.302, "criteria": "0" },
    "P9": { "name": "$1000 Voucher", "payout": 1000, "prob": 0.002, "criteria": "wincap" }
  }
}
```

- **`prizes[sku]`**: `payout` = RGS multiplier (catalog value at base-bet 1),
  `prob` = draw odds (**must sum to 1.0**), `criteria` = `"0"` (pays nothing),
  `"wincap"` (the single max prize), or any unique `p_*` bucket.
- **`criteria: "0"` is authoritative** — its `payout` is forced to 0, so sub-0.1×
  catalog values (like `$0.01`) are legal to author (they just pay nothing).

## `cost_model` decides ACP validity — this is the crux

- **`box_cost`** (default): payouts authored literally, base mode `cost = box_cost`.
  Reproduces the legacy math but **FAILS the ACP "Base Mode Cost must be 1.0x"
  validator**. Use only for parity checks, not for an ACP upload.
- **`unit`**: the loader divides each payout by `box_cost`, snaps to the 0.1× grid,
  sets base mode `cost = 1.0`, and **derives** `wincap` = max multiplier.
  **ACP-valid.** Consequences to expect:
  - max-win rescales (e.g. `1000× → 200.8×` at `box_cost 4.98`),
  - sub-0.1× prizes pay `0` (grid floor),
  - the **real box price becomes the ACP bet level** (set in the dashboard, not here).

  `manifests/cash_paradise_unit.json` is the ACP-valid sample — copy it as a starting
  point for anything you intend to publish.

## The integrality rule (build refuses to violate it)

**`num_sims × prob` must be an exact integer for every prize.** With the optimiser
off, published odds equal `round(num_sims × prob)`, so any drift corrupts the odds.
`prod` builds **assert** this and refuse to build on drift; `dev` only warns. Pick
`num_sims` so every `prob` lands exactly — a multiple of **500** works for the sample
manifests (`num_sims = 100000` clears them). If you change a `prob`, re-check the
product for every prize.

## Validate & build

```sh
# Schema-check only, no sims (fast; also what the build service calls):
GAME_MANIFEST=manifests/<file>.json python games/mystery_box_dynamic/run.py --validate

# Build with build.sh (works from any dir, no venv activation):
cd games/mystery_box_dynamic
./build.sh dev  <file>.json     # smoke: 1000 sims, no compression/checks, _dev game-id suffix
./build.sh prod <file>.json     # full: manifest build block (compressed + format-checked) → publishable
NUM_SIMS=5000 ./build.sh dev <file>.json   # override sim count
# all manifests at once:
./build.sh dev                  # (no file arg) builds every manifests/*.json
make build_all_dynamic          # one process per manifest
```

`dev` builds get a `_dev` game-id suffix so they never clobber a prod
`publish_files/`. Lower-level env overrides `run.py` honours: `NUM_SIMS`,
`COMPRESSION`, `RUN_FORMAT_CHECKS`, `GAME_ID_SUFFIX`, `SAMPLE_EVENTS`.

The three publishable files land in `games/<game_id>/library/publish_files/`
(`index.json`, `books_base.jsonl.zst`, `lookUpTable_base_0.csv`) from a **prod**
build. `build.sample_events` also writes a readable
`library/samples/books_events_base.json` (one round per distinct criteria, for
frontend devs) — kept **out** of `publish_files/`.

## Gotchas

- **`make run GAME=mystery_box_dynamic` does NOT work** — it passes no manifest. Always go through `build.sh` or set `GAME_MANIFEST`.
- **Never edit the six engine `.py` files** in `mystery_box_dynamic/` per-game — they are generic; the manifest is the only per-game input.
- **`game_id` must be unique** — it is the output dir *and* the published gameID; a collision overwrites another game's `library/`.
- **`python -m utils.rgs_verification -g <game_id>` won't reload a dynamic game** (there is no `games/<game_id>/game_config.py`); format checks run inline during the build instead.
- **`provider_number`** in shipped manifests is a placeholder (`3`) — set the real ACP-assigned value before the final prod build you upload.

## Related skills

- **`publish-stake-game`** — upload the prod `publish_files` and set the box price as the ACP bet level (unit-mode's cost=1.0 depends on this).
- **`mystery-box-build-service`** — the FastAPI wrapper that builds a manifest (or a simplified box form) over HTTP and returns the publish zip.
