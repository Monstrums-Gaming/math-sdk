"""
Optimization setup for Plinko (2_6).

Plinko has FIXED odds: each bin's probability is the binomial C(N,k)/2**N and the
payouts are authored on the 0.1x grid in game_config.py, so there is nothing for the
Rust optimiser to tune — the published LUT weights are uniform (1 per book) and the
bin frequencies come straight from the distribution quotas. `run.py` therefore leaves
run_optimization off and never instantiates this class.

Kept as a documented stub so the game folder matches the standard layout.
"""


class OptimizationSetup:
    """Intentionally disabled — see module docstring."""

    def __init__(self, game_config: object):
        raise RuntimeError(
            "2_6 (Plinko) uses fixed binomial odds and is not optimised. "
            "Leave run_optimization disabled in run.py."
        )
