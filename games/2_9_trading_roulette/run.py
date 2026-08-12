"""Driver script for Trading Roulette (2_9).

A zone board dressed as a market chart: the player bets a board cell before the round, a
market index line animates, and the ROW it crosses at the right edge decides the round —
the row is certified in the book (`landRow`). This is a direct-probability game (like
limbo 2_5 and market-crash 2_8), not a reel game: odds are authored in game_config.py, so
the Rust optimiser is not used — lookup-table weights stay uniform (1 per book) and the
win frequency is driven entirely by the distribution quotas.

Twenty-one modes zone_o1 .. zone_line (fine rows, bands, halves, tails, exact line), each
its own cost-1.0 win/lose bet mode. Realised RTP is (a/b)*multiplier, pinned into
[96.15%, 96.65%]. Each mode publishes N = k*b books of which W = k*a win, so the odds are
exactly a/b while every mode carries enough books that its certified landRows never look
canned. num_threads = 1 and batching_size >= every mode's num_sims so each mode is one
exact batch.

Production settings: COMPRESSION=1 and RUN_FORMAT_CHECKS=1 (compression is mandatory —
utils/rgs_verification.py::execute_all_tests rejects non-.jsonl.zst books).
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
    batching_size = 50000  # >= every mode's num_sims (max ~5.1k) -> one batch per mode
    profiling = False

    # Dev defaults: readable .json books, no format checks.
    # Production: COMPRESSION=1 RUN_FORMAT_CHECKS=1 (compression is mandatory —
    # execute_all_tests rejects non-.jsonl.zst books).
    compression = _env_bool("COMPRESSION", False)

    run_conditions = {
        "run_sims": True,
        # Slot analytics assume base+freespin gametypes and raise on a single
        # gametype game; leave off. The RGS format checks plus build_odds_bundle.py
        # are the meaningful verification for this game.
        "run_analysis": False,
        "run_format_checks": _env_bool("RUN_FORMAT_CHECKS", False),
    }

    config = GameConfig()
    gamestate = GameState(config)

    # Per-mode num_sims = k*b (an exact integer multiple of the win probability's
    # denominator, so the +0.5 quota split lands exactly).
    num_sim_args = {name: params["num_sims"] for name, params in config.mode_params.items()}

    # One batch per mode keeps the split exact and the per-batch _payout_ints sidecar
    # clean. Above batching_size, run_multi_process_sims would shard a mode across
    # repeats and the floor-safe quotas would no longer land on the published counts.
    assert max(num_sim_args.values()) <= batching_size, (
        "every mode's num_sims must fit in one batch (exact +0.5 quota split)"
    )

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
