"""
Plinko (2_6) — game configuration.

A Stake-style **Plinko** game. A ball drops through `N` rows of pegs and lands in
one of `N+1` bins; each bin pays a fixed multiplier. The bin the ball lands in is
governed by the **binomial** distribution `C(N,k)/2**N` (a Galton board: the ball
deflects left/right with equal probability at each of the `N` pegs, so the number
of right-deflections `k` — the bin index — is Binomial(N, 1/2)). Like the dice
(`2_4`) and limbo (`2_5`) games this is a **direct-probability** game: no reels, no
free spins, Rust optimiser disabled. The odds come straight from the distribution
quotas.

## Modes: base product only (1 ball, cost 1.0), rows 8..16 x 4 difficulties

36 bet modes = rows {8..16} x difficulty {low, medium, high, expert}, each name
`base_r{NN}_{difficulty}` (dot-free — the ACP publisher parses `<mode>` out of
`books_<mode>.jsonl.zst` / `lookUpTable_<mode>_0.csv`, so a "." would collide with
the extension). Every mode is `cost = 1.0`.

The reference RGS also exposes a `balls100_*` product (100 balls at a 0.99x
per-drop stake, costMultiplier 99). It is **deferred**: its round payout is a sum
of 100 draws (astronomically many distinct totals) at an off-grid 0.99x stake, and
its RTP is identical to the base drop. "Drop 100 balls" is an ACP bet-level / a
frontend batch concern, not a published math mode (mirrors limbo pushing its
streak/high bet-scaling tiers into the ACP bet-level template).

## Payout-cell tables — grid-aligned, symmetric, RTP-tuned

Each mode's `payout_cells` (length `N+1`) is:
  * **symmetric** (`cells[k] == cells[N-k]`) — the binomial is symmetric,
  * **monotone toward the centre** (edges pay the most, centre the least),
  * **on the ACP 0.1x grid** (every multiplier is a whole multiple of 0.1x, so
    `cells[k]*100` is a multiple of 10 — `verify_lookup_format`), and
  * **RTP-tuned** so the mode's realised RTP `(1/2**N) * sum(C(N,k)*cells[k])`
    lands inside [96.00%, 96.70%].

The real Stake tables run ~99% RTP (e.g. r16 "high" `[1000,130,26,9,4,2,0.2,...]`
computes to 98.98%), above ACP's 96.70% ceiling, so every table is re-tuned down
into band. A difficulty-scaled edge sets the volatility; a coordinate-descent
solver (`_fit_cells`) then nudges the higher-weight inner bins on the 0.1x grid to
pin the RTP near a shared 96.35% target (keeping every mode within a <=0.70% spread,
well inside ACP's cross-mode +/-0.5% / <=1.00% rule). If an edge is so large no
in-band table exists (the expert/high case, and why the reference `100000x` edge is
impossible under a binomial — it alone is +305% RTP), the solver lowers the edge to
the largest grid value that admits an in-band table.

## Exact integer book counts

Optimiser off -> published odds equal the per-criteria book counts, so
`num_sims * quota` must be an exact integer. Bin probabilities are `C(N,k)/2**N`,
so `num_sims = 2**N` yields exactly `C(N,k)` books per bin. We declare **one
Distribution per distinct payout value** (bins sharing a multiplier are pooled):
`quota = (sum of C(N,k) over that payout's bins + 0.5)/2**N`, and
`int(2**N * quota)` lands exactly on that integer count (the floor-safe "+0.5"
trick; `get_sim_splits` does `int(num_sims*quota)`), with the counts summing to
`2**N`. Every bin pays >= 0.1x (there are no 0x/loss bins), so criteria are
"wincap" (the global top edge) or `p_<cents>`.

## ACP math rules

  1. 0.1x LUT grid — `lut_grid_exempt = False` keeps the SDK grid check ON.
  2. RTP band (per-mode): 90%..96.70%. We pin every mode into [96.00%, 96.70%].
  3. RTP consistency (cross-mode): within +/-0.5% (spread <= 1.00%). All modes sit
     near 96.35% -> <= 0.70% spread.
  4. Risk / star-rating (Max Payout, Tail Probability, ETL, CVaR): an upload-time
     unknown for the big edges (the checks that capped limbo at 100x). If ACP
     rejects a high/expert edge, lower that difficulty's edge and rebuild — see
     readme.txt.
"""

import os
from math import comb

from src.config.config import Config
from src.config.distributions import Distribution
from src.config.betmode import BetMode

# Stake ACP RTP window.
#   per-mode:   "Return to Player must be between 90% and 96.70%"
#   cross-mode: "RTP within +/-0.5% of each other" (spread <= 1.00%)
# We pin every realised RTP into [RTP_FLOOR, RTP_CEIL], aiming at RTP_TARGET.
RTP_CEIL = 0.967
RTP_FLOOR = 0.960
RTP_TARGET = 0.9635
_EPS = 1e-9

ROWS = list(range(8, 17))  # 8..16
# low / medium / high only. An "expert" tier was tried and REMOVED: its near
# all-or-nothing shape (~99% of drops at the 0.1x floor, a rare huge edge) breaks
# Stake's 2-star risk validators (CVaR / ETL / volatility) for rows 11..16 — high
# already sits at the top of the 2-star volatility envelope (high_r16 = 970x passes
# while expert_r11 = 340x failed, so it's the SHAPE, not the edge). There is no
# 2-star room above `high`, the same wall that capped limbo. See readme.txt.
DIFFICULTIES = ["low", "medium", "high"]

# Per-difficulty shape parameters (starting point; the solver re-tunes RTP):
#   edge8   — edge multiplier at 8 rows (the corner bins).
#   growth  — edge multiplier factor per extra row (edge_N = edge8 * growth**(N-8)).
#   gamma   — centre->edge curvature (higher = flatter centre, sharper edge rise).
#   floor   — centre bin multiplier floor (the least a bin can pay).
# These reproduce roughly Stake-like volatility per difficulty; the exact cells are
# then RTP-tuned onto the 0.1x grid by _fit_cells.
_DIFFICULTY = {
    "low":    {"edge8": 5.0,  "growth": 1.15, "gamma": 1.8, "floor": 0.5},
    "medium": {"edge8": 13.0, "growth": 1.30, "gamma": 2.5, "floor": 0.3},
    "high":   {"edge8": 29.0, "growth": 1.55, "gamma": 3.2, "floor": 0.2},
}


def _snap10(deci: float) -> int:
    """Round a deci-unit value (multiplier*10) to the nearest integer >= 1."""
    return max(1, int(round(deci)))


def _nice_edge_deci(deci: int) -> int:
    """Round an edge deci-value to ~2 significant figures for clean multipliers.

    The edge carries negligible binomial weight (2/2**N), so rounding it barely
    moves RTP and the inner-bin solver absorbs the difference — but it turns
    9662 -> 9700 (966.2x -> 970x) / 63916 -> 64000 (6400x) into sane payouts.
    """
    deci = max(10, int(deci))
    step = 10 ** max(0, len(str(deci)) - 2)
    return max(10, int(round(deci / step)) * step)


def _tier_key(k: int, n: int) -> int:
    """Symmetric distance key for bin k of an n-row board: 0 at centre, n at edges."""
    return abs(2 * k - n)


def _parametric_shape(n: int, edge_deci: int, floor_deci: int, gamma: float) -> list:
    """Symmetric, monotone-toward-centre cell list in deci-units (multiplier*10)."""
    half = n / 2.0
    cells = []
    for k in range(n + 1):
        u = abs(k - half) / half  # 0 centre .. 1 edge
        val = floor_deci + (edge_deci - floor_deci) * (u ** gamma)
        cells.append(_snap10(val))
    # Enforce exact symmetry and monotone-increasing outward (round() can wobble).
    for k in range(n + 1):
        cells[k] = cells[n - k] = max(cells[k], cells[n - k])
    order = sorted(range(n + 1), key=lambda k: _tier_key(k, n))
    prev = floor_deci
    for k in order:
        cells[k] = max(cells[k], prev)
        prev = cells[k]
    return cells


def _rtp_deci(n: int, cells_deci: list, weights: list) -> float:
    """Realised RTP for a deci-unit cell list: sum(C(N,k)*cells)/2**N/10."""
    total = sum(weights[k] * cells_deci[k] for k in range(n + 1))
    return total / (2 ** n) / 10.0


def _fit_cells(n: int, edge_deci: int, floor_deci: int, gamma: float, weights: list):
    """Tune inner bins (0.1x grid, symmetric, monotone) to pin RTP near RTP_TARGET.

    Returns (cells_deci, rtp) or (None, None) if no in-band table exists for this
    edge (caller then lowers the edge). Coordinate descent over symmetric distance
    tiers: the edge tier is held fixed; each inner tier absorbs the RTP residual,
    clamped to keep the table monotone. Because RTP is linear in the tier values and
    the tier just inside the edge carries little weight, the final RTP lands within a
    fraction of a 0.1x step of the target.
    """
    cells = _parametric_shape(n, edge_deci, floor_deci, gamma)

    # Distance tiers centre->edge; each is a set of bins that must share a value.
    tiers = {}
    for k in range(n + 1):
        tiers.setdefault(_tier_key(k, n), []).append(k)
    tier_keys = sorted(tiers)                     # ascending: centre .. edge
    inner_keys = tier_keys[:-1]                   # all but the fixed edge tier
    tier_weight = {tk: sum(weights[k] for k in tiers[tk]) for tk in tier_keys}

    def tier_val(tk):
        return cells[tiers[tk][0]]

    def set_tier(tk, v):
        for k in tiers[tk]:
            cells[k] = v

    # Feasibility: min RTP (inner all at floor) must be <= ceiling, else edge too big.
    for tk in inner_keys:
        set_tier(tk, floor_deci)
    if _rtp_deci(n, cells, weights) > RTP_CEIL + _EPS:
        return None, None

    # Re-seed from the parametric shape and run coordinate descent.
    cells = _parametric_shape(n, edge_deci, floor_deci, gamma)
    scale = (2 ** n) * 10.0
    target_units = RTP_TARGET * scale
    # Visit centre->just-inside-edge each pass so the smallest-weight inner tier is
    # tuned last (finest control); a few passes settle the interdependent clamps.
    for _ in range(60):
        for i, tk in enumerate(inner_keys):
            others = sum(tier_weight[t] * tier_val(t) for t in tier_keys if t != tk)
            ideal = (target_units - others) / tier_weight[tk]
            lower = floor_deci if i == 0 else tier_val(inner_keys[i - 1])
            upper = tier_val(tier_keys[i + 1])  # next tier outward (toward edge)
            set_tier(tk, min(max(int(round(ideal)), lower), upper))

    rtp = _rtp_deci(n, cells, weights)
    if RTP_FLOOR - _EPS <= rtp <= RTP_CEIL + _EPS:
        return cells, rtp
    return None, None


def _build_table(n: int, difficulty: str, weights: list):
    """Build the final (cells_floats, edge_mult, rtp) for one (rows, difficulty)."""
    spec = _DIFFICULTY[difficulty]
    edge_deci = _nice_edge_deci(_snap10(spec["edge8"] * (spec["growth"] ** (n - 8)) * 10.0))
    floor_deci = _snap10(spec["floor"] * 10.0)
    # Lower the edge (10% per step) until an in-band table exists.
    for _ in range(200):
        cells_deci, rtp = _fit_cells(n, edge_deci, floor_deci, spec["gamma"], weights)
        if cells_deci is not None:
            cells = [c / 10.0 for c in cells_deci]
            return cells, cells[0], rtp
        nxt = _nice_edge_deci(_snap10(edge_deci * 0.9))
        if nxt >= edge_deci:  # cannot shrink further
            break
        edge_deci = nxt
    raise RuntimeError(f"no in-band Plinko table for rows={n} difficulty={difficulty}")


class GameConfig(Config):
    """Plinko configuration — binomial bins, grid-aligned RTP-tuned cell tables."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        super().__init__()
        self.game_id = "2_6_plinko"
        self.provider_number = 2  # placeholder — confirm ACP-assigned value before prod upload
        self.provider_name = "monstrum"
        self.game_name = "Plinko"
        self.working_name = "Plinko"
        self.win_type = "scatter"
        # Payouts authored on the ACP 0.1x grid; keep the SDK grid check ON.
        self.lut_grid_exempt = False
        self.construct_paths()

        # No board mechanic: model a single revealed cell (1 reel x 1 row).
        self.num_reels = 1
        self.num_rows = [1] * self.num_reels

        self.tiers = self._build_tiers()
        self.wincap = max(t["edge"] for t in self.tiers)
        self.rtp = max(t["rtp"] for t in self.tiers)
        self.mode_params = {}

        # Minimal boardless scaffolding (mirrors limbo / the dice game).
        self.paytable = {(1, "P"): 1.0}
        self.include_padding = False
        self.special_symbols = {"wild": [], "scatter": [], "multiplier": []}
        self.freespin_triggers = {self.basegame_type: {}, self.freegame_type: {}}
        self.anticipation_triggers = {self.basegame_type: 0, self.freegame_type: 0}

        reels = {"BR0": "BR0.csv"}
        self.reels = {}
        for r, f in reels.items():
            self.reels[r] = self.read_reels_csv(os.path.join(self.reels_path, f))
        self.padding_reels = {
            self.basegame_type: self.reels["BR0"],
            self.freegame_type: self.reels["BR0"],
        }

        self.bet_modes = self._build_bet_modes()
        self._validate()

    # ------------------------------------------------------------------ tiers
    def _build_tiers(self) -> list:
        """Return one row per (rows, difficulty): cells, edge, per-payout bin groups."""
        rows = []
        for n in ROWS:
            weights = [comb(n, k) for k in range(n + 1)]
            for difficulty in DIFFICULTIES:
                cells, edge, rtp = _build_table(n, difficulty, weights)

                # Group bins by payout value (keyed by integer cents for float-safety).
                payout_bins = {}   # cents -> [bin indices]
                payout_val = {}    # cents -> float multiplier
                for k in range(n + 1):
                    cents = int(round(cells[k] * 100))
                    payout_bins.setdefault(cents, []).append(k)
                    payout_val[cents] = round(cells[k], 2)

                # Book count per distinct payout = sum of binomial weights of its bins.
                payout_count = {c: sum(weights[k] for k in ks) for c, ks in payout_bins.items()}

                rows.append(
                    {
                        "rows": n,
                        "difficulty": difficulty,
                        "cells": [round(c, 2) for c in cells],
                        "edge": round(edge, 2),
                        "rtp": rtp,
                        "num_sims": 2 ** n,
                        "weights": weights,
                        "payout_bins": payout_bins,
                        "payout_val": payout_val,
                        "payout_count": payout_count,
                    }
                )
        return rows

    # ---------------------------------------------------------------- betmodes
    def _build_bet_modes(self) -> list:
        """One bet mode per (rows, difficulty); one Distribution per distinct payout."""
        dummy_reels = {
            "reel_weights": {
                self.basegame_type: {"BR0": 1},
                self.freegame_type: {"BR0": 1},
            }
        }
        wincap_cents = int(round(self.wincap * 100))

        modes = []
        for row in self.tiers:
            n = row["rows"]
            difficulty = row["difficulty"]
            num_sims = row["num_sims"]
            name = f"base_r{n:02d}_{difficulty}"  # dot-free by construction

            criteria_payout = {}   # criteria name -> float payout
            distributions = []
            for cents, count in sorted(row["payout_count"].items()):
                payout = row["payout_val"][cents]
                quota = (count + 0.5) / num_sims  # floor-safe: int(num_sims*quota) == count
                if cents == wincap_cents:
                    criteria = "wincap"
                    conditions = {**dummy_reels, "force_wincap": True, "force_freegame": False}
                else:
                    criteria = f"p_{cents}"
                    conditions = {**dummy_reels, "force_wincap": False, "force_freegame": False}
                criteria_payout[criteria] = payout
                distributions.append(
                    Distribution(
                        criteria=criteria,
                        quota=quota,
                        win_criteria=payout,
                        conditions=conditions,
                    )
                )

            self.mode_params[name] = {
                "rows": n,
                "difficulty": difficulty,
                "cost": 1.0,
                "cells": row["cells"],
                "edge": row["edge"],
                "rtp": row["rtp"],
                "num_sims": num_sims,
                "criteria_payout": criteria_payout,
                # payout cents -> bin indices, for the ball-path event.
                "payout_bins": {str(c): ks for c, ks in row["payout_bins"].items()},
            }

            modes.append(
                BetMode(
                    name=name,
                    cost=1.0,
                    rtp=row["rtp"],
                    max_win=row["edge"],
                    auto_close_disabled=False,
                    is_feature=False,
                    is_buybonus=False,
                    distributions=distributions,
                )
            )
        return modes

    # ---------------------------------------------------------------- validate
    def _validate(self) -> None:
        """Guard the mode set before the engine consumes it."""
        assert self.wincap == max(t["edge"] for t in self.tiers), "wincap must equal the top edge"
        assert len(self.bet_modes) == len(self.tiers) == len(ROWS) * len(DIFFICULTIES), (
            "unexpected Plinko mode count"
        )

        rtps = [t["rtp"] for t in self.tiers]
        assert max(rtps) - min(rtps) <= 0.01 + _EPS, (
            f"cross-mode RTP spread {max(rtps) - min(rtps):.4f} exceeds 1.00%"
        )

        for row in self.tiers:
            n = row["rows"]
            cells = row["cells"]
            weights = row["weights"]
            tag = f"r{n:02d}_{row['difficulty']}"

            assert len(cells) == n + 1, f"{tag}: expected {n + 1} cells, got {len(cells)}"
            # Symmetric.
            for k in range(n + 1):
                assert cells[k] == cells[n - k], f"{tag}: cells not symmetric at {k}"
            # On the 0.1x grid, non-zero, >= 0.1x.
            for k, c in enumerate(cells):
                cents = int(round(c * 100))
                assert cents >= 10 and cents % 10 == 0, f"{tag}: cell {c} off the 0.1x grid"
            # Monotone toward the centre (edges pay the most).
            order = sorted(range(n + 1), key=lambda k: _tier_key(k, n))
            for a, b in zip(order, order[1:]):
                assert cells[a] <= cells[b] + _EPS, f"{tag}: not monotone toward centre"
            # Edge is the table max and the mode's advertised max_win.
            assert row["edge"] == max(cells), f"{tag}: edge != max cell"
            # Per-mode RTP inside Stake's band, and matches the reconstructed value.
            recon = sum(weights[k] * cells[k] for k in range(n + 1)) / (2 ** n)
            assert abs(recon - row["rtp"]) < 1e-9, f"{tag}: rtp mismatch {recon} vs {row['rtp']}"
            assert RTP_FLOOR - _EPS <= row["rtp"] <= RTP_CEIL + _EPS, (
                f"{tag}: RTP {row['rtp']:.4f} outside [{RTP_FLOOR}, {RTP_CEIL}]"
            )
            # Exact integer book split (the "+0.5" trick), summing to 2**N.
            num_sims = row["num_sims"]
            total = 0
            for cents, count in row["payout_count"].items():
                quota = (count + 0.5) / num_sims
                assert int(num_sims * quota) == count, f"{tag}: split off for payout {cents}"
                total += int(num_sims * quota)
            assert total == num_sims, f"{tag}: book split sums to {total}, expected {num_sims}"
