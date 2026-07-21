"""
Optimization setup for Crypto Pulse Grid (2_11).

Crypto Pulse Grid has FIXED, derived odds (a forced win/lose split per ladder rung),
so there is nothing for the Rust optimiser to tune — the published weights are
uniform (weight 1 per book) and the win frequency comes directly from the
distribution quotas in `game_config.py`. `run.py` therefore leaves
`run_optimization` off and never instantiates this class.

It is kept as a documented stub so the game folder matches the standard layout.
"""


class OptimizationSetup:
    """Intentionally disabled — see module docstring."""

    def __init__(self, game_config: object):
        raise RuntimeError(
            "2_11 (Crypto Pulse Grid) uses fixed, authored odds and is not optimised. "
            "Leave run_optimization disabled in run.py."
        )
