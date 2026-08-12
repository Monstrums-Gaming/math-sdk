"""Driver script for Chicken Crossing (2_7).

Chicken Crossing is a Stake-style Chicken Road game, not a reel game. Each round
resolves to a predetermined cash-out step (a fixed 0.1x-grid multiplier) or a pop
(payout 0). Because the odds are authored directly in game_config.py from the
per-difficulty survival ladders, the Rust optimiser is not used: the lookup-table
weights stay uniform (1 per book) and the outcome frequencies are driven entirely
by the distribution quotas.

One bet mode per difficulty (easy / medium / hard / daredevil), each a multi-outcome
split. Every mode uses num_sims = config.num_sims (default 1,000,000, env NUM_SIMS)
so book counts land near round(num_sims * outcome_probability). Theoretical RTP is
97% per step (see the game_config RTP_TARGET warning — 0.97 > the 96.70% ACP
ceiling; set RTP_TARGET=0.967 for an ACP-uploadable build).

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
    batching_size = 100000  # >= 1000 so no divisibility constraint at num_sims 1e6
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

    # Per-mode num_sims (uniform; env NUM_SIMS overrides via game_config).
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
