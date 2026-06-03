"""Driver script for Mystery Box (2_1_85).

Mystery Box is a single-purchase prize draw, not a reel game. Each simulated
round opens one box and reveals exactly one prize from a fixed probability
table. Because the odds are authored directly in game_config.py, the Rust
optimiser is not used: the lookup-table weights stay uniform (1 per book) and
the prize frequencies are driven entirely by the distribution quotas.
"""

from gamestate import GameState
from game_config import GameConfig
from utils.game_analytics.run_analysis import create_stat_sheet
from utils.rgs_verification import execute_all_tests
from src.state.run_sims import create_books
from src.write_data.write_configs import generate_configs


if __name__ == "__main__":
    num_threads = 1
    batching_size = 50000
    compression = False
    profiling = False

    num_sims = int(50)
    num_sim_args = {
        "base": num_sims,
    }

    run_conditions = {
        "run_sims": True,
        # The analysis spreadsheet tooling assumes a multi-gametype slot game
        # (base + free spins). A mystery box has a single gametype, which makes
        # that tooling raise; leave it off (the RGS format checks below are the
        # meaningful verification for this game).
        "run_analysis": False,
        "run_format_checks": False,
    }

    config = GameConfig()
    gamestate = GameState(config)

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

    if run_conditions["run_analysis"]:
        custom_keys = [
            {"criteria": "wincap"},
            {"criteria": "0"},
            {"prize": "P3"},
            {"prize": "P8"},
        ]
        create_stat_sheet(gamestate, custom_keys=custom_keys)

    if run_conditions["run_format_checks"]:
        execute_all_tests(config)
