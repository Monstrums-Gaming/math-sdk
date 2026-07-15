"""
Optimization setup for Cash Paradise (3_2).

The mystery box has FIXED, authored prize odds, so there is nothing for the
Rust optimiser to tune — the published weights are uniform (weight 1 per book)
and the prize frequencies come directly from the distribution quotas in
`game_config.py`. `run.py` therefore leaves `run_optimization` off and never
instantiates this class.

It is kept as a documented stub so the game folder matches the standard layout
and so a future variant that DOES need optimisation has an obvious home.
"""


class OptimizationSetup:
    """Intentionally disabled — see module docstring."""

    def __init__(self, game_config: object):
        raise RuntimeError(
            "3_2 (Cash Paradise) uses fixed prize odds and is not optimised. "
            "Leave run_optimization disabled in run.py."
        )
