# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Python engine (Python ≥ 3.12) for defining slot/casino game math, simulating millions of round outcomes, optimizing win distributions, and emitting the backend/frontend config files, lookup tables, and "books" (per-round event sequences) that the Stake Engine RGS consumes. The win-distribution optimizer is a separate Rust/Cargo program under `optimization_program/`.

## Setup & common commands

```sh
make setup                      # creates ./env venv, installs requirements.txt + editable package
source env/bin/activate         # activate venv (Make prints this)

make run GAME=3_2_mystery_box_cash_paradise   # run a game's run.py; auto-formats books JSON if compression=False
make test                       # run pytest suite in tests/
make test_run                   # run run.py for the games in Makefile TEST_NAMES
make clean                      # remove env/ and __pycache__/*.pyc
pytest tests/win_calculations/test_linespay.py        # single test file
pytest tests/win_calculations/test_linespay.py::<name> # single test
```

There is no configured linter/formatter (no ruff/black/flake8/pyproject) — don't go looking for a lint command. `make test` is pytest-only and covers just the win-calculation math (see "Conventions & gotchas").

The games that currently exist are `3_2_mystery_box_cash_paradise`, `mystery_box`, `mystery_box_dynamic` (the JSON-manifest generator — see "Dynamic mystery-box generator" below), `2_4_kong_climb` (a Stake-style dice game — roll over/under; see the `stake-dice-game` skill), and `template`. The `0_0_*` slot samples and `fifty_fifty` were removed (commit `155c385`); `make test_run`'s `TEST_NAMES` is trimmed to `mystery_box` and `3_2_mystery_box_cash_paradise`. Reference-only mentions of the deleted slot games below are kept because they illustrate the reel-slot model.

Running a game directly (equivalent to `make run`, useful for flags): `python games/<game_id>/run.py`. The venv is required because the project is installed as an editable package (`pip install -e .`) exposing `src`, `optimization_program`, `uploads`, and `utils` as importable top-level modules — game files import e.g. `from src.state.run_sims import create_books`.

Rust optimizer is built/invoked automatically from Python (`optimization_program/run_script.py` shells out to Cargo); needs Rust/Cargo installed only when `run_optimization` is enabled.

## Build pipeline (run.py)

Each game's `run.py` is the entrypoint and is driven by two dicts you edit in place:
- `num_sim_args` — sims per bet mode, e.g. `{"base": int(1e6)}`.
- `run_conditions` — booleans toggling the four stages: `run_sims` → `run_optimization` → `run_analysis` → `upload_data`. `generate_configs(gamestate)` always runs.

Stage order and what each does:
1. **run_sims** (`src/state/run_sims.py::create_books`) — multiprocess simulation. Splits sims across `num_threads` and batches of `batching_size`, assigns each sim a distribution *criteria* by quota, writes per-thread temp files, then merges into `games/<id>/library/`.
2. **generate_configs** (`src/write_data/write_configs.py`) — writes `config.json` (BE), `config_fe_*.json` (FE), `math_config.json`, `index.json` manifest.
3. **run_optimization** — Rust program reshapes the lookup-table weights to hit target RTP per the `opt_params` defined in `game_optimization.py`; regenerates configs.
4. **run_analysis** (`utils/game_analytics/`) — PAR-sheet style stats.
5. **upload_data** (`uploads/aws_upload.py::upload_to_aws`) — verifies file hashes/lengths then pushes to S3 (needs `.env` AWS creds).

Key run.py flags: `compression` (False emits readable `.json` books and triggers `utils/format_books_json.py`; True emits `.jsonl.zst`), `profiling` (cProfile + snakeviz flamegraph, forces `threads=1`).

Sim count constraint: when `num_sims > batch_size²`, it must be divisible by `threads * batch_size` with no remainder.

## Game module structure

Every game lives in `games/<game_id>/` (id convention `<provider>_<num>_<name>`, e.g. `0_0_lines`). Copy `games/template/` to start a new one. Required files form a strict inheritance chain — a game subclasses the engine's `Executables` and progressively overrides:

```
GameState (gamestate.py)            # run_spin / run_freespin orchestration for one round
  └ GameStateOverride (game_override.py)   # reset_book, special-symbol fns, repeat logic overrides
      └ GameExecutables (game_executables.py)  # game-specific reusable actions
          └ GameCalculations (game_calculations.py) # game-specific win calc tweaks
              └ Executables (src/executables/executables.py)  # shared, mostly side-effecting actions
                  └ Conditions, Tumble, … → GeneralGameState (src/state/state.py)
```

- `gamestate.py` — defines `run_spin(sim, seed)` and `run_freespin()`. The `while self.repeat` loop re-runs a round until it satisfies the active criteria's win condition (see "criteria/repeat" below).
- `game_config.py` — subclass of `src/config/config.py::Config`. Sets `game_id`, dimensions (`num_reels`, `num_rows`), `paytable` (keyed `('kind','symbol')`), `special_symbols`, `freespin_triggers`, loads reel CSVs from `reels/`, and defines `bet_modes` (list of `BetMode`).
- `game_optimization.py` — `opt_params` per mode using `ConstructConditions` / `ConstructScaling` / `ConstructParameters` from `optimization_program/optimization_config.py`.
- `reels/` — CSV reel strips (e.g. `BR0.csv` base, `FR0.csv` free); referenced by name in config.
- `readme.txt` — per-game rules description (worth reading to understand a game's mechanics).
- `library/` — **generated output**, not source. Contains `books/`, `lookup_tables/`, `configs/`, `forces/`, `publish_files/` (the RGS-required files), `optimization_files/`.

Not every game is a reel slot. The `mystery_box` and `3_2_mystery_box_cash_paradise` games are direct-probability games: a round draws one prize from a fixed odds table authored in `game_config.py` (via `get_random_outcome`) with no board, no reels, no freespin round, and `run_optimization` disabled — RTP is set by the authored odds and box cost, not the Rust optimizer. Their `run.py` trims `run_conditions` to `run_sims`/`run_analysis`/`run_format_checks` (the slot-oriented analytics in `utils/game_analytics/` assume base+freespin gametypes and raise on a single-gametype game, so `run_analysis` stays off; `run_format_checks` calls `execute_all_tests` for RGS validation). With the optimiser off, published odds equal books-per-criteria, i.e. `round(num_sims * quota)` — pick `num_sims` so every quota lands on an exact integer. When working on a game, read its `readme.txt` and `run.py` first to learn which model it follows.

Some games also ship a standalone `frontend_demo/` (plain `index.html`/`app.js`/CSS) — a self-contained browser mockup of the game UI for previewing the mechanic; it's independent of the published RGS frontend config and the build pipeline.

### Dynamic mystery-box generator (`games/mystery_box_dynamic/`)

One reusable folder that builds **any** direct-probability mystery-box game from a JSON **manifest** under `manifests/`, instead of hand-authoring a `games/<id>/` folder per game. The engine derives every output path from `config.game_id` (loaded from the manifest, not this folder's name), so each manifest builds into its own auto-created `games/<game_id>/library/` tree. The six engine files here (`gamestate.py`, `game_override.py`, `game_events.py`, `game_executables.py`, `game_calculations.py`, `game_optimization.py`) are generic copies of the `mystery_box` engine — **don't edit them per-game**; author a manifest instead. `game_config.py` loads the manifest; `run.py` drives the standard `create_books → generate_configs → execute_all_tests` pipeline. Full docs in the folder's `README.md` and `BUILD.md`.

- **Build with `build.sh <dev|prod> [manifest]`** (calls `env/bin/python` directly, no venv activation needed). `dev` = fast smoke build (num_sims 1000, no compression/checks, `_dev` game-id suffix so it never clobbers a prod `publish_files/`); `prod` = full build from the manifest's `build` block (compression + format checks on). With no manifest arg, every `manifests/*.json` builds. `make build_all_dynamic` builds all manifests one process each. `make run GAME=mystery_box_dynamic` does **not** work — it passes no manifest.
- **Lower-level:** `GAME_MANIFEST=manifests/<f>.json python games/mystery_box_dynamic/run.py`; `run.py` also honours env overrides `NUM_SIMS`, `COMPRESSION`, `RUN_FORMAT_CHECKS`, `GAME_ID_SUFFIX`.
- **`cost_model` (per manifest)** decides ACP validity: `"box_cost"` (default) authors payouts literally with base `cost = box_cost` — reproduces the legacy math but **fails** the ACP "cost must be 1.0" validator; `"unit"` divides each payout by `box_cost`, snaps to the 0.1× grid, sets base `cost = 1.0`, and derives `wincap` — **ACP-valid** (max-win rescales, sub-0.1× prizes pay 0, and the real box price becomes the ACP bet level). `cash_paradise_unit.json` is the ACP-valid sample.
- **`num_sims × prob` must be an exact integer for every prize** (a multiple of 500 for the sample manifests) — prod enforces this and refuses to build on drift; dev only warns. `provider_number` in the shipped manifests is a placeholder (`3`); set the real ACP-assigned value before the final prod build you upload.
- **Readable events sample:** every build also writes `library/samples/books_events_base.json` — a coverage-first, human-readable slice (one round per distinct `criteria` so every event shape incl. `wincap` appears, then filled to the count) for frontend/game devs (`utils/sample_events.py`, called from `run.py` *after* `execute_all_tests` so it never touches the ACP artifacts). Count via manifest `build.sample_events` (default 100, `0` off) / `SAMPLE_EVENTS` env. It is kept **out** of `publish_files/`; the service delivers it separately as `events_file` / `GET /builds/{id}/events` (never in `publish.zip`).

### Build service (`service/`)

A standalone **FastAPI** HTTP API that wraps the dynamic generator so a backoffice can build a mystery box and download its publish files. It is **additive** — it shells out to the same `games/mystery_box_dynamic/run.py`, so service and manual (`build.sh`) builds are identical, and the manual path is unchanged. Run with `API_KEY=… ./service/run_service.sh` (or the `service/Dockerfile`). Full docs in `service/README.md`.

- **Async job model:** `POST /builds?mode=prod|dev` (manifest JSON body, `X-API-Key` header) validates synchronously (400 on a bad manifest, via `run.py --validate` — a no-op flag added just for this), then returns `202 {job_id}`. Poll `GET /builds/{job_id}`; download the zip at `GET /builds/{job_id}/download` once `succeeded`. `/healthz` is open. API reference in `service/API.md` (+ auto Swagger at `/docs`).
- **Manifest builder** (`service/manifest_builder.py`): `POST /manifests` assembles a full manifest from simplified box inputs (name, price, prize rows) — auto-derives `game_id`, per-prize `criteria` (max payout→`wincap`, grid-zero→`"0"`, else per-payout bucket), `wincap`, `rtp` (EV/cost), and a fixed `num_sims` (`MANIFEST_NUM_SIMS`, default 100000) — validates via `run.py --validate`, and optionally builds with `?build=true`. This is the path a backoffice "create a box" form uses instead of hand-writing manifest JSON.
- **Never call `create_books` in-process** — it spawns `multiprocessing.Process` workers; the service always subprocesses `run.py` (as `build.sh` does). Output paths are absolute (rooted at the repo via `src/config/paths.py`), so `GAME_ID_SUFFIX` is **not** used for prod isolation (it would leak into the published `gameID`); instead a per-`game_id` lock (in-process **and** a cross-process `fcntl.flock` on `service/artifacts/.locks/<id>.lock`) serializes same-game builds so two builds never share the `games/<id>/library/` tree — concurrent unserialized same-game builds corrupt each other and surface as a book↔LUT "Payout hash mismatch". Each job snapshots `publish_files/` into `service/artifacts/<job_id>/` immediately after the build.
- Job status is persisted to **SQLite** (`jobs.py` → `settings.JOBS_DB_PATH`, default `ARTIFACT_DIR/jobs.db`) so it survives a process restart; one connection + in-process lock, so still **single-worker** (mount `ARTIFACT_DIR` on a volume — the deploy workflows use `-v mbs-data:/app/service/artifacts` — to also survive a container recreate). Artifacts persist on disk. `service/` files: `app.py` (routes), `builder.py` (subprocess build + snapshot + zip), `jobs.py`, `auth.py`, `schemas.py`, `s3.py`, `config.py`.
- **Optional S3 deploy** (`service/s3.py`, boto3): set `AWS_S3_BUCKET` and a successful **prod** build auto-uploads its publish files (+ zip) to `s3://<bucket>/<S3_PREFIX><game_id>/`, returning stable savable paths in the job status (`s3_files[].url`, from `S3_PUBLIC_BASE_URL`/CDN or the S3 https URL — the backoffice stores these). This is delivery to **your** bucket — **not** Stake RGS publishing (still the ACP dashboard), and separate from the slot-oriented `uploads/aws_upload.py` (interactive, `uploads/.env`). Best-effort: a failure leaves the build `succeeded`/`deploy_status:"failed"` (never loses the artifact); no bucket ⇒ `"skipped"`.
- **Ephemeral builds** (`EPHEMERAL_BUILDS`, default on when a bucket is set): after a successful upload the local build (`games/<id>/` + the job zip) is **deleted** — the service is a stateless worker and S3 is the source of truth. A failed upload deletes nothing. In this mode `/download` 409s (files are in S3) and `already_built` checks S3 (`HeadObject`) instead of local disk. Deploy + cleanup run inside the per-`game_id` lock. Verify S3 paths with stubbed boto3 (`service/s3.py::_client`) or LocalStack via `S3_ENDPOINT_URL`.

## Publishing to Stake Engine (RGS/ACP)

The RGS is a certified **replay** system: it serves pre-generated, hash-verified books/lookup tables, so a game's odds and payouts are **frozen at publish time and cannot change at runtime** (no live/API-driven odds; the published frontend artifact's CSP also blocks external fetches). Publishing = regenerate a compressed, format-checked build, then upload the three files in `library/publish_files/` — `index.json`, `books_<mode>.jsonl.zst`, `lookUpTable_<mode>_0.csv` — via the ACP dashboard. (`uploads/aws_upload.py` is an alternate S3 path but ships with an empty `BUCKET_NAME`.)

Production `run.py` settings: `compression=True` (mandatory — `utils/rgs_verification.py::verify_books_and_payout_mults` and `execute_all_tests` reject non-`.jsonl.zst` books), `run_format_checks=True`, and `num_sims` chosen so every criteria quota is an exact integer.

ACP validation rules the **math must satisfy** but the SDK does **not** enforce (each has bitten this repo):
- **Base/default bet mode cost multiplier must be exactly `1.0`.** The mystery-box games set `cost = box_cost` (e.g. 4.98) and so **fail** this validator as authored. It is not a one-line fix: RTP is `EV ÷ cost` (`utils/analysis/distribution_functions.py::calculate_rtp`), so flipping cost to 1.0 without re-expressing payouts turns an 85% game into a ~420% one. Payouts must be re-expressed as multipliers of a 1× bet (the real box price becomes the operator-set **bet level**), averaging the target RTP.
- **Lookup-table payout format** (`verify_lookup_format`): each payout is an integer of "cents" (`payout×100`), `0` or `≥10`, and a multiple of `10` — i.e. non-zero payouts must be multiples of `0.1×`; anything below `0.1×` must resolve to `0`.
- **Bet levels** are applied in the ACP dashboard (bet-level template; Stake US requires a `us_` prefix), NOT emitted by the math-sdk — a missing template is the "Bet Level Validator: no valid levels" error. The SDK only writes `minDenomination`/`betDenomination`, both derived from `config.min_denomination`.

`config.json` carries sha256 hashes of the published files, and `execute_all_tests` cross-checks book↔LUT payout arrays (fast path via the `books_<mode>.verification.json` sidecar) before upload. A worked runbook lives at `games/3_2_mystery_box_cash_paradise/docs/PRODUCTION.md`.

## Core engine concepts (src/)

- **BetMode → Distribution → criteria** (`src/config/betmode.py`, `distributions.py`): a bet mode (e.g. `base`, `bonus`) holds `Distribution`s, each with a `criteria` name (`"wincap"`, `"freegame"`, `"0"`, `"basegame"`, …), a `quota` (fraction of sims), optional `win_criteria`, and `conditions` (reel weights, forced freegame/wincap, multiplier values, etc.). During sims each round is assigned a criteria; `GeneralGameState.check_repeat` rejects and re-runs a round whose `final_win` doesn't match the criteria's `win_criteria` or that failed to force a freegame.
- **Win calculations** (`src/calculations/`): pluggable win types — `lines.py`, `ways.py`, `cluster.py`, `scatter.py`, plus `board.py` (reveal), `tumble.py` (cascading), `symbol.py` (symbol storage + special-symbol attributes like multipliers), `statistics.py` (`get_random_outcome` weighted picks).
- **Events** (`src/events/`): `events.py` emits the ordered event dicts (board reveal, win info, tumble, freespin trigger/update/end, multiplier update, final win) that become the per-round "book". This event stream is the contract with the frontend — adding a mechanic usually means adding an event here and recording it.
- **WinManager** (`src/wins/win_manager.py`): tracks base vs free vs running/cumulative wins; `update_final_win` asserts `base + free == total` (capped at `wincap`). The `multiplier_strategy.py` defines how multipliers combine.
- **Books & recording** (`src/state/books.py`, `state.py`): `imprint_wins` finalizes each round into `self.library` keyed by sim, accumulates `_payout_ints` (the per-round payout multiplier sidecar used for the books-vs-LUT hash verification). `record(...)` logs distribution/force keys used for criteria acceptance and force files.
- **Output writers** (`src/write_data/`): `write_data.py` (books, lookup tables, segmented LUTs, library events), `write_configs.py`, `force.py`. `src/config/output_filenames.py` owns every output path/name.

## Conventions & gotchas

- RNG is seeded per-sim (`reset_seed`) for reproducibility — sim N always produces the same round. Don't introduce unseeded randomness; use `get_random_outcome`.
- Payouts are integer-scaled multipliers internally; `update_final_win` rounds to 2 dp and enforces the base+free==total invariant — breaking it raises `AssertionError`.
- `_payout_ints` must be reset per batch (it accumulates across `run_spin`); see the comment in `state.py::run_sims` — a stale sidecar breaks the publish-time hash check.
- Multiprocess sims: `run_sims` runs per-thread into temp files; force keys are merged via `combine` then locked. Profiling requires `threads=1`.
- `tests/` only covers the win-calculation math (lines/ways/cluster/scatter) using fixtures in `tests/win_calculations/game_test_config.py`.
- Utilities in `utils/`: `decompress_zstd.py`, `format_books_json.py`, `rgs_verification.py` (`execute_all_tests`), `merge_luts/`, `swap_lookups.py`, `game_analytics/`, `search_tool/`.
- Docs source is `docs/` (MkDocs Material, `mkdocs.yml`); published at stakeengine.github.io/math-sdk.
