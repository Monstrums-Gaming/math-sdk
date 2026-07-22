"""Driver script for Tap Trade (2_6).

A tap-cell-to-bet game: each chip is a win/lose bet at a fixed multiplier. This is a
direct-probability game (like the original Crypto Pulse 2_9), not a reel game: odds
are authored in game_config.py, so the Rust optimiser is not used — lookup-table
weights stay uniform (1 per book) and the win frequency is driven entirely by the
distribution quotas.

Twenty-eight modes call_140 .. call_10000 (the 1.4x-100x multiplier ladder, dense
below 10x), each its own cost-1.0 win/lose bet mode. Each mode's num_sims = the exact
denominator b of its win probability a/b, so published book counts equal the win
chance; realised RTP is (a/b)*multiplier, pinned into [96.00%, 96.70%].
num_threads = 1 and batching_size >= every mode's num_sims so each mode is one exact
batch.

Production settings: COMPRESSION=1 and RUN_FORMAT_CHECKS=1 (compression is
mandatory — utils/rgs_verification.py::execute_all_tests rejects non-.jsonl.zst
books).
"""

import os

from gamestate import GameState
from game_config import GameConfig
from utils.rgs_verification import execute_all_tests
from src.state.run_sims import create_books
from src.write_data.write_configs import generate_configs


def _env_bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


if __name__ == "__main__":
    num_threads = 1
    batching_size = 50000  # >= every mode's num_sims (max 135) -> one batch per mode, exact split
    profiling = False

    # Dev defaults: readable .json books, no format checks.
    # Production: COMPRESSION=1 RUN_FORMAT_CHECKS=1 (compression is mandatory —
    # execute_all_tests rejects non-.jsonl.zst books).
    compression = _env_bool("COMPRESSION", False)

    run_conditions = {
        "run_sims": True,
        # Slot analytics assume base+freespin gametypes and raise on a single
        # gametype game; leave off. The RGS format checks are the meaningful
        # verification for this game.
        "run_analysis": False,
        "run_format_checks": _env_bool("RUN_FORMAT_CHECKS", False),
    }

    config = GameConfig()
    gamestate = GameState(config)

    # Per-mode num_sims = b (exact denominator of that mode's win probability a/b).
    num_sim_args = {name: params["num_sims"] for name, params in config.mode_params.items()}

    if run_conditions["run_sims"]:
        create_books(
            gamestate,
            config,
            num_sim_args,
            batching_size,
            num_threads,
            compression,
            profiling,
        )

    generate_configs(gamestate)

    if run_conditions["run_format_checks"]:
        execute_all_tests(config)
