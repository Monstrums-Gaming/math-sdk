"""Driver script for Battleships (2_3).

Battleships is a Stake-style Mines game with a naval reskin, not a reel game, using a
**continue-after-mine, rising-by-rarity** model. Each tile click is one independent
per-click wager (chicken_run style): a SHIP wins its rung multiplier and advances
depth (ships_found += 1); a MINE loses only its stake and does NOT end the run or
change depth. The run ends only when all ships are found, the player presses END, or
no unopened tiles remain. Each round resolves to a fixed 0.1x-grid multiplier (ship)
or a mine hit (payout 0). Because the odds are authored directly in game_config.py
from the per-difficulty INCREMENTAL (per-step) ladders, the Rust optimiser is not
used: the lookup-table weights stay uniform (1 per book) and the outcome frequencies
are driven entirely by the distribution quotas.

39 modes total: one bet mode per (difficulty, reveal-depth k = 1..ships) —
easy_1..15, medium_1..12, hard_1..8, extreme_1..4 — each a win/lose split with
`cost = 1.0`. The k-th rung's ship probability is `p_k = (ships-(k-1))/(25-(k-1))`
(ships get rarer as they are found) and it pays `floor_to_grid(RTP_TARGET / p_k)`, so
ships pay MORE the more you have found. Each mode's num_sims is the denominator of its
smallest-denominator win fraction (env NUM_SIMS unused here) so book counts equal the
published odds exactly. Realised RTP per mode is inside the ACP [96.00%, 96.70%] band.

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

    # Per-mode num_sims = the denominator of that mode's win fraction (exact books).
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
