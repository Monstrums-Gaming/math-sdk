"""
Optimization setup for Boat Race (3_0).

Boat Race has FIXED, authored odds (a forced 4-way place split), so there is nothing for
the Rust optimiser to tune — the published weights are uniform (weight 1 per book) and
the place frequencies come directly from the distribution quotas in `game_config.py`.
`run.py` therefore leaves `run_optimization` off and never instantiates this class.

Kept as a documented stub so the game folder matches the standard layout.
"""


class OptimizationSetup:
    """Intentionally disabled — see module docstring."""

    def __init__(self, game_config: object):
        raise RuntimeError(
            "3_0 (Boat Race) uses fixed, authored odds and is not optimised. "
            "Leave run_optimization disabled in run.py."
        )
