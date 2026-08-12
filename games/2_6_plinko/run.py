"""Driver script for Plinko (2_6).

Plinko is a Stake-style Galton-board game, not a reel game. Each round drops a ball
through N peg rows into one of N+1 bins (Binomial(N, 1/2)); each bin pays a fixed
0.1x-grid multiplier. Because the odds are authored directly in game_config.py, the
Rust optimiser is not used: the lookup-table weights stay uniform (1 per book) and
the bin frequencies are driven entirely by the distribution quotas.

Each mode uses num_sims = 2**rows so the published book counts equal the binomial
weights C(N,k) exactly; realised RTP is pinned into [96.00%, 96.70%].

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
    batching_size = 70000  # >= every mode's num_sims (2**16 = 65536) -> one batch, exact split
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

    # Per-mode num_sims = 2**rows (exact binomial book counts).
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
