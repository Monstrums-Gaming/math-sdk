"""Driver script for Cash Paradise (3_2).

Cash Paradise is a single-purchase prize draw, not a reel game. Each simulated
round opens one box and reveals exactly one cash-voucher prize from a fixed
probability table. Because the odds are authored directly in game_config.py, the
Rust optimiser is not used: the lookup-table weights stay uniform (1 per book)
and the prize frequencies are driven entirely by the distribution quotas.
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
    # Production: emit compressed books (.jsonl.zst) so the published config
    # carries a real books hash. Set to False for a readable-JSON smoke test.
    compression = True
    profiling = False

    # With the optimiser disabled, published odds == books-per-criteria, i.e.
    # round(num_sims * quota). At 100,000 every quota lands on an exact integer
    # count (30200 / 28000 / 25000 / 5000 / 5000 / 5000 / 1000 / 600 / 200), so
    # the lookup table reproduces the authored odds exactly. Drop to a small
    # number (e.g. 50) only for a quick smoke test.
    num_sims = int(100000)
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
        "run_format_checks": True,
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
            {"prize": "CP9"},
            {"prize": "CP8"},
        ]
        create_stat_sheet(gamestate, custom_keys=custom_keys)

    if run_conditions["run_format_checks"]:
        execute_all_tests(config)
