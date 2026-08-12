"""Driver script for Porkageddon (2_0).

Porkageddon is a direct-probability battler, not a reel game. Each simulated round
plays one complete pig fight whose payout was already fixed by the criteria the
engine assigned, so the Rust optimiser is not used: lookup-table weights stay
uniform (1 per book) and the win frequencies come entirely from the distribution
quotas in `game_config.py` / `pork_math.py`.

All three stance modes are `cost = 1.0` and realise RTP 96.35%, inside the ACP
[90%, 96.70%] band with a cross-mode spread under 1e-5.

Production settings: `COMPRESSION=1 RUN_FORMAT_CHECKS=1` (compression is mandatory —
`utils/rgs_verification.py::execute_all_tests` rejects non-`.jsonl.zst` books).

    PYTHONPATH="$(pwd)" COMPRESSION=1 RUN_FORMAT_CHECKS=1 \
        ./env/bin/python games/2_0_porkageddon/run.py

Useful env overrides (see pork_math.py): `NUM_SIMS` (books per mode),
`GLOBAL_MAX_MULT` (published max-win ceiling, default 2000), `RTP_TARGET_BP`.
"""

import os

from game_config import GameConfig
from gamestate import GameState
from src.state.run_sims import create_books
from src.write_data.write_configs import generate_configs
from utils.rgs_verification import execute_all_tests


def _env_bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


if __name__ == "__main__":
    num_threads = 1
    batching_size = 50000
    profiling = False

    # Dev defaults: readable .json books, no format checks.
    compression = _env_bool("COMPRESSION", False)

    run_conditions = {
        "run_sims": True,
        # The slot analytics in utils/game_analytics/ assume base+freespin gametypes
        # and raise on a single-gametype game; the RGS format checks are the
        # meaningful verification here.
        "run_analysis": False,
        "run_format_checks": _env_bool("RUN_FORMAT_CHECKS", False),
    }

    config = GameConfig()
    gamestate = GameState(config)

    num_sim_args = {name: params["num_sims"] for name, params in config.mode_params.items()}

    # run_multi_process_sims derives num_repeats/sims_per_thread by rounding and does
    # NOT assert they multiply back to num_sims — a mismatch silently drops books,
    # which would break every authored count and drift realised RTP. Check it here.
    for mode_name, nsims in num_sim_args.items():
        repeats = max(round(nsims / num_threads / batching_size), 1)
        per_thread = int(nsims / num_threads / repeats)
        assert num_threads * repeats * per_thread == nsims, (
            f"{mode_name}: {num_threads} threads x {repeats} repeats x {per_thread} sims "
            f"= {num_threads * repeats * per_thread}, expected {nsims}. Adjust "
            f"batching_size or NUM_SIMS so the split is exact."
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
