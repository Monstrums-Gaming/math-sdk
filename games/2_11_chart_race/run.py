"""Driver script for Chart Race (2_11).

Two pick-neutral finishing-place markets over a 3-line chart race: `highest` and
`lowest`, both paying 3.00x at a certified 8/25 = 32% (RTP exactly 96.00%). Books carry
a certified `finishOrder` (r0 = the player's pick) that the frontend race is obliged to
arrive at; there is no rank timeline — the chart is continuous and cosmetic. This is a
direct-probability game (like limbo 2_5, market_crash 2_8, trading_roulette 2_9): odds
are authored in game_config.py, the Rust optimiser is not used, lookup-table weights
stay uniform (1 per book), and win frequencies come entirely from the distribution
quotas.

Two modes, 5,000 books each (1,600 winners). num_threads = 1 and batching_size >=
num_sims so each mode is one exact batch and the +0.5 quota split lands on the published
counts.

Production settings: COMPRESSION=1 and RUN_FORMAT_CHECKS=1 (compression is mandatory —
utils/rgs_verification.py::execute_all_tests rejects non-.jsonl.zst books). After a
production run, execute `verify_books.py` to walk every published book and prove the
order/payout invariants.
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
    batching_size = 50000  # >= every mode's num_sims (5000) -> one exact batch per mode
    profiling = False

    compression = _env_bool("COMPRESSION", False)

    run_conditions = {
        "run_sims": True,
        # Slot analytics assume base+freespin gametypes and raise on a single
        # gametype game; leave off. The RGS format checks plus verify_books.py
        # are the meaningful verification for this game.
        "run_analysis": False,
        "run_format_checks": _env_bool("RUN_FORMAT_CHECKS", False),
    }

    config = GameConfig()
    gamestate = GameState(config)

    num_sim_args = {name: params["num_sims"] for name, params in config.mode_params.items()}
    assert max(num_sim_args.values()) <= batching_size, (
        "num_sims must fit in one batch (exact +0.5 quota split)"
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
