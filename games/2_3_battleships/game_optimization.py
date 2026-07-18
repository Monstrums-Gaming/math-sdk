"""
Optimization setup for Battleships (2_3).

Battleships has FIXED, derived odds (each mode is a multi-outcome split whose
per-outcome probabilities come from the computed Mines survival ladder), so there is
nothing for the Rust optimiser to tune — the published weights are uniform (weight 1
per book) and the outcome frequencies come directly from the distribution quotas in
`game_config.py`. `run.py` therefore leaves `run_optimization` off and never
instantiates this class.

It is kept as a documented stub so the game folder matches the standard layout.
"""


class OptimizationSetup:
    """Intentionally disabled — see module docstring."""

    def __init__(self, game_config: object):
        raise RuntimeError(
            "2_3 (Battleships) uses fixed, derived odds and is not optimised. "
            "Leave run_optimization disabled in run.py."
        )
