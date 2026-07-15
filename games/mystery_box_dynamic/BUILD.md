# Build guide — dynamic mystery-box generator

How to build a mystery-box game from a JSON manifest, in **dev** (fast iteration) or
**prod** (publishable) mode.

## Prerequisites

The project venv must exist (it exposes `src`/`utils` as importable packages via
`pip install -e .`). Once:

```sh
cd /Users/jdev/www/monstrums/stake-engine/math-sdk
make setup            # creates ./env and installs the editable package
```

`build.sh` calls `env/bin/python` directly, so you do **not** need to activate the venv.
If you run `run.py` by hand instead, activate it first (`source env/bin/activate`) or you
get `ModuleNotFoundError: No module named 'src'`.

## Quick start

```sh
cd games/mystery_box_dynamic

./build.sh dev                     # fast smoke build of every manifest
./build.sh prod                    # full production build of every manifest
./build.sh prod cash_paradise.json # production build of ONE manifest
./build.sh dev  cash_paradise.json # dev build of ONE manifest
```

The manifest argument is a filename under `manifests/` or an explicit path. Multiple
manifests can be listed. With no manifest argument, every `manifests/*.json` is built.

## Modes

`build.sh <dev|prod>` sets the build knobs. **prod overrides nothing** — it uses each
manifest's own `build` block. **dev** overrides them for speed and isolation.

| Knob | dev | prod |
|------|-----|------|
| `num_sims` | `1000` (override with `NUM_SIMS`) | manifest `build.num_sims` (e.g. `100000`) |
| `compression` | `false` (readable JSON) | manifest `build.compression` (**`true`**) |
| `run_format_checks` | `false` | manifest `build.run_format_checks` (`true`) |
| `game_id` suffix | `_dev` | none |
| output dir | `games/<game_id>_dev/library/` | `games/<game_id>/library/` |
| quota-integrality | warns | **enforced** (build fails on drift) |

Dev builds carry a `_dev` game-id suffix so they land in a separate tree and **never
clobber** a production build's `publish_files`. Publish only **prod** builds.

## The prod config lives in the manifest

A production build is defined entirely by the manifest's `build` block:

```json
"build": {
  "num_sims": 100000,        // full count; num_sims * prob must be integer for every prize
  "compression": true,       // emits books_base.jsonl.zst (required to publish)
  "run_format_checks": true, // runs execute_all_tests (RGS pre-publish gate)
  "num_threads": 1,
  "batching_size": 50000
}
```

To change what a prod build does, edit that block. `num_sims` must keep
`num_sims × prob` an exact integer for every prize (a multiple of 500 for the sample
manifests) — otherwise the published odds drift; prod refuses to build, dev only warns.

## One-off overrides (either mode)

`run.py` honours these env vars on top of the manifest; `build.sh` sets them for dev:

```sh
NUM_SIMS=200000    ./build.sh prod cash_paradise.json   # more sims, still compressed+checked
COMPRESSION=false  ./build.sh prod cash_paradise.json   # readable JSON (NOT publishable)
RUN_FORMAT_CHECKS=false ./build.sh prod ...             # skip the RGS gate
GAME_ID_SUFFIX=_test    ./build.sh prod ...             # write to games/<id>_test/
```

## Lower-level equivalents

What `build.sh` runs under the hood (venv must be active):

```sh
# single manifest, manifest's build values
GAME_MANIFEST=manifests/cash_paradise.json python games/mystery_box_dynamic/run.py
# every manifest, one process each
make build_all_dynamic
```

`make run GAME=mystery_box_dynamic` does **not** work — it passes no manifest.

## Output

Each build writes to `games/<game_id>/library/` (`game_id` from the manifest). The three
files to upload to the ACP are in `library/publish_files/`:

```
index.json
books_base.jsonl.zst      # only present when compression=true (prod)
lookUpTable_base_0.csv
```

A build also writes `games/<game_id>/reels/BR0.csv` (the prize SKUs) for parity with the
static games.

## Verifying a build

Prod builds print `[FAST PATH] base: SHA-256 OK, payout hash OK, entries=<num_sims>` from
the format checks. Spot-check the payout histogram matches the authored odds:

```sh
awk -F, '{print $3}' games/<game_id>/library/publish_files/lookUpTable_base_0.csv \
  | sort -n | uniq -c
```

## Before publishing: set the real `provider_number`

The manifests ship with `"provider_number": 3` as a **placeholder**. `provider_number` is
your Stake Engine studio/provider ID (assigned to your ACP account, not chosen by you —
it is not documented in the SDK). Before the final prod build you upload, replace it in
each manifest with your real provider number (found in your ACP account, or from your
Stake Engine onboarding contact), and align the leading segment of `game_id` to match it.
It does not affect local builds/format checks — only the `providerNumber` written into
`config.json`.

## Publishing

Only a **prod** build is publishable. Upload the three `publish_files` to the Stake
Engine ACP — see the `publish-stake-game` skill and
`games/3_2_mystery_box_cash_paradise/docs/PRODUCTION.md`.

Note: a manifest with `cost_model: "box_cost"` (base cost = box_cost) reproduces the
legacy math but **fails** the ACP "cost must be 1.0" validator. For an ACP-valid prod
build use `cost_model: "unit"` (see `manifests/cash_paradise_unit.json`) — base cost
becomes 1.0, payouts snap to the 0.1× grid, and the box price is set as the ACP bet level.
