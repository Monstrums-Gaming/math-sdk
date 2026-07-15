"""Dynamic driver for manifest-authored mystery-box games.

Selects a manifest (``--manifest`` arg, else ``GAME_MANIFEST`` env var), builds the
game defined by it, and writes output to ``games/<manifest game_id>/library``.

    GAME_MANIFEST=manifests/cash_paradise.json python games/mystery_box_dynamic/run.py
    python games/mystery_box_dynamic/run.py --manifest manifests/cash_paradise.json

NOTE: plain ``make run GAME=mystery_box_dynamic`` will NOT work — it passes no manifest.
Build knobs (num_sims, compression, run_format_checks, threads, batching) come from the
manifest's ``build`` block, not this file.
"""

import argparse
import os
import sys

from gamestate import GameState
from game_config import GameConfig
from utils.rgs_verification import execute_all_tests
from src.state.run_sims import create_books
from src.write_data.write_configs import generate_configs


def _env_bool(name: str, default: bool) -> bool:
    """Parse a boolean env override; unset -> default."""
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _assert_integral_quotas(config, num_sims: int) -> None:
    """With the optimiser off, published odds == round(num_sims * criteria_quota); every
    criteria quota (summed prize probs) must therefore land on an exact integer."""
    criteria_quota = {}
    for info in config.prize_table.values():
        criteria_quota[info["criteria"]] = round(
            criteria_quota.get(info["criteria"], 0.0) + info["prob"], 8
        )
    for criteria, quota in criteria_quota.items():
        exact = num_sims * quota
        if abs(exact - round(exact)) > 1e-9:
            raise RuntimeError(
                f"num_sims ({num_sims}) x quota for criteria {criteria!r} ({quota}) = {exact} "
                f"is not an integer; published odds would drift. Pick a compatible num_sims."
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=os.environ.get("GAME_MANIFEST"))
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Load and validate the manifest (prize table, RGS grid, integral quotas) "
        "without running any sims, then exit. Used by the build service for a fast "
        "pre-flight check; a normal build never passes this flag.",
    )
    args, _ = parser.parse_known_args()

    # Load config + resolve build knobs. Under --validate we convert any authoring error
    # into a clean one-line stderr message (exit 2) so the build service can surface it
    # verbatim as an HTTP 400 instead of parsing a traceback. A normal build re-raises.
    try:
        config = GameConfig(args.manifest, os.environ.get("GAME_ID_SUFFIX", ""))

        # Build knobs come from the manifest's "build" block, overridable via env vars
        # (build.sh dev/prod modes set these).
        build = config.build_opts
        num_sims = int(os.environ.get("NUM_SIMS", build.get("num_sims", 100000)))
        compression = _env_bool("COMPRESSION", bool(build.get("compression", True)))
        run_format_checks = _env_bool("RUN_FORMAT_CHECKS", bool(build.get("run_format_checks", True)))
        num_threads = int(build.get("num_threads", 1))
        batching_size = int(build.get("batching_size", 50000))
        profiling = False

        # --validate: GameConfig() above already ran the prize-table/RGS-grid checks; the
        # only remaining production gate is integral quotas at this num_sims. Assert it and
        # exit (no sims, no output beyond the reels/BR0.csv that GameConfig writes).
        if args.validate:
            _assert_integral_quotas(config, num_sims)
            print(f"[validate] OK: {config.game_id} manifest is valid at num_sims={num_sims}.")
            raise SystemExit(0)
    except (RuntimeError, FileNotFoundError, ValueError, KeyError, TypeError) as err:
        if args.validate:
            print(f"[validate] INVALID: {err}", file=sys.stderr)
            raise SystemExit(2)
        raise

    gamestate = GameState(config)

    # Non-integral quotas drift the published odds — fatal for a production build,
    # tolerated (warned) for a fast dev smoke test where format checks are off.
    try:
        _assert_integral_quotas(config, num_sims)
    except RuntimeError as err:
        if run_format_checks:
            raise
        print(f"[dev] WARNING: {err}")

    create_books(
        gamestate,
        config,
        {"base": num_sims},
        batching_size,
        num_threads,
        compression,
        profiling,
    )

    generate_configs(gamestate)

    if run_format_checks:
        execute_all_tests(config)
