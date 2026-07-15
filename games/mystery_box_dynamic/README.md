# mystery_box_dynamic — JSON-manifest mystery-box generator

One reusable folder that builds **any** direct-probability mystery-box game from a JSON
**manifest**, instead of hand-authoring a new `games/<id>/` folder per game. Add a game =
add a manifest under `manifests/`.

## How it works

The engine derives every output path from `config.game_id` (not this folder's name), so a
manifest's `game_id` makes the build land in its own auto-created
`games/<game_id>/library/` tree. `game_config.py` loads the manifest, and `run.py` drives
the standard `create_books → generate_configs → execute_all_tests` pipeline.

The 6 engine files (`gamestate.py`, `game_override.py`, `game_events.py`,
`game_executables.py`, `game_calculations.py`, `game_optimization.py`) are copies of the
`mystery_box` engine — do not edit them here; they are generic.

## Manifest format (`manifests/*.json`)

```jsonc
{
  "game_id": "my_box",                // drives output dir + published gameID (unique!)
  "provider_number": 3, "provider_name": "monstrum",
  "game_name": "My Box", "working_name": "My Box",
  "box_cost": 4.98,                   // box price in base-bet units
  "wincap": 1000,                     // max multiplier (box_cost mode); derived in unit mode
  "rtp": 0.85,                        // declared RTP (< 1.0)
  "cost_model": "box_cost",           // "box_cost" (default) | "unit" (see below)
  "build": { "num_sims": 100000, "compression": true, "run_format_checks": true,
             "num_threads": 1, "batching_size": 50000 },
  "prizes": {                         // authored exactly as the internal prize_table
    "P1": { "name": "$0.01 Voucher", "payout": 0.01, "prob": 0.302, "criteria": "0" },
    "P9": { "name": "$1000 Voucher", "payout": 1000, "prob": 0.002, "criteria": "wincap" }
  }
}
```

- `prizes[sku]`: `payout` = RGS multiplier (catalog value at base-bet 1), `prob` = draw
  odds (must sum to 1.0), `criteria` = `"0"` (pays nothing), `"wincap"` (single max
  prize), or any unique `p_*` bucket.
- `criteria: "0"` is authoritative — its `payout` is forced to 0 (so sub-0.1× catalog
  values like `$0.01` are legal to author).
- `num_sims` must make `num_sims × prob` an exact integer for every prize (100000 works
  for the sample); `run.py` asserts this.

### cost_model

- **`box_cost`** (default): payouts authored literally; base mode `cost = box_cost`.
  Reproduces the legacy games but **fails the ACP "cost must be 1.0" validator**.
- **`unit`**: loader divides each payout by `box_cost`, snaps to the 0.1× grid, sets base
  mode `cost = 1.0`, and derives `wincap` = max multiplier. **ACP-valid.** Consequence:
  max-win rescales (e.g. 1000× → 200.8× at box_cost 4.98) and sub-0.1× prizes pay 0. The
  real box price is set as the ACP bet level. See the `publish-stake-game` skill.

## Build

Use `build.sh` with a **mode** (works from any directory, no venv activation needed):

```sh
cd games/mystery_box_dynamic
./build.sh dev                     # fast smoke build of every manifest
./build.sh prod                    # full production build of every manifest
./build.sh dev cash_paradise.json  # one manifest (name under manifests/ or a path)
NUM_SIMS=5000 ./build.sh dev ...   # override the sim count
```

| Mode | num_sims | compression | format checks | output |
|------|----------|-------------|---------------|--------|
| `dev`  | 1000 (override via `NUM_SIMS`) | off | off | `games/<game_id>_dev/library/` |
| `prod` | manifest `build.num_sims` (e.g. 100000) | on | on | `games/<game_id>/library/` |

Dev builds get a `_dev` game-id suffix so they land in a separate tree and never clobber
a production build's `publish_files`. `num_sims` must keep `num_sims × prob` integral for
every prize (a multiple of 500 for the sample manifests) — in prod that's enforced, in dev
it only warns.

Lower-level equivalents (what `build.sh` runs under the hood):

```sh
# single game, prod defaults from the manifest
GAME_MANIFEST=manifests/cash_paradise.json python games/mystery_box_dynamic/run.py
# env overrides run.py honours: NUM_SIMS, COMPRESSION, RUN_FORMAT_CHECKS, GAME_ID_SUFFIX
# all manifests, one process each
make build_all_dynamic
```

Plain `make run GAME=mystery_box_dynamic` will NOT work (no manifest passed). The 3
publishable files land in `games/<game_id>/library/publish_files/` — publish a **prod**
build via the ACP per the `publish-stake-game` skill.

Note: dynamic `game_id`s are not independently reloadable by folder
(`python -m utils.rgs_verification -g <game_id>` would look for `games/<game_id>/game_config.py`,
which doesn't exist) — format checks run inline during the build instead.
