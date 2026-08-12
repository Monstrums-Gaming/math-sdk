"""
Chicken Crossing (2_7) — game configuration.

A Stake-style **Chicken Road** game. The chicken crosses a road one lane ("step")
at a time; every step it survives raises a cash-out multiplier; if a car hits it
the round pays 0. Like the dice (`2_4`), limbo (`2_5`) and plinko (`2_6`) games this
is a **direct-probability** game: no reels, no free spins, Rust optimiser disabled.
The odds come straight from the distribution quotas.

## Modes: one bet mode per difficulty (Easy / Medium / Hard / Daredevil)

Four bet modes, one per difficulty, each `cost = 1.0`. Every mode is a
**multi-outcome** distribution (like plinko): one `Distribution` per distinct
cash-out multiplier, plus a single loss ("0") outcome. Mode names are the plain
difficulty strings (dot-free — the ACP publisher parses `<mode>` out of
`books_<mode>.jsonl.zst`).

## The ladder (authoritative, user-supplied)

Each difficulty has a per-step **cumulative survival probability** and
`payoutMultiplier = 0.97 / cumulativeSurvivalProbability`, so the *theoretical* RTP
of cashing out at any step is exactly 97%. The full ladders below include the huge
upper-tail steps; a **global 2000x cap** (`GLOBAL_MAX_MULT`) drops every step at or
above the cap, so only the publishable rungs survive:

    Easy       24 steps, max   24.25x   (nothing capped)
    Medium     21 steps, max  557.75x   (round 21 = 2231.00x  capped)
    Hard       17 steps, max  920.29x   (rounds 17-19 capped, incl. 51536.10x)
    Daredevil  10 steps, max 1055.84x   (rounds 10-14 capped, incl. 3170697.20x)

## Grid snapping + probability adjustment (the dice trick)

The raw multipliers are not on the ACP 0.1x grid (e.g. 1.01042, 24.25), so each is
**floor-snapped** onto the grid (`snapped = floor(raw*10)/10`, cents a multiple of
10). Floor-snapping lowers the multiplier, so we then **adjust the probability** of
reaching each step to `rho_k = RTP_TARGET / snapped_k`, which pins the realised
per-step RTP back to `RTP_TARGET` regardless of snapping (`rho_k <= 1` always, since
`snapped_k >= 1.0 > RTP_TARGET`).

## Outcome probabilities (target-weight mixture)

A round is predetermined to cash out at a target step `k` (weight `w_k`, default
uniform `1/S`) and survives to it with probability `rho_k`, paying `snapped_k`; else
it pops (pays 0). Outcome probability `q_k = w_k * rho_k`; loss `q_loss = 1 - sum(q_k)`.
Because `q_k * snapped_k = w_k * RTP_TARGET`, the overall RTP is `RTP_TARGET` for ANY
`w_k` (the weight only shapes hit-frequency / volatility, never RTP). Steps whose
snapped multipliers collide are pooled into one distinct-payout outcome.

## Exact integer book counts

Optimiser off -> published odds equal the per-criteria book counts. With `num_sims`
(default 1,000,000) each distinct payout's book count is `round(num_sims * q)`, the
loss bucket absorbs the rounding residual so counts sum to `num_sims`, and the
floor-safe `+0.5` quota (`get_sim_splits` does `int(num_sims*quota)`) reproduces the
count exactly. Realised RTP is recomputed from the integer counts (see tools/report.py).

## Two warnings (see readme.txt)

  1. **Predetermined settlement.** The RGS is a certified replay: the book selected
     at /play fixes the whole outcome, including the cash-out step. The player CANNOT
     change the payout by pressing "Cash Out" mid-round (do not rely on /bet/event to
     mutate the settled payout). Player-controlled dynamic cash-out stays DISABLED.
  2. **RTP vs the ACP ceiling.** `RTP_TARGET = 0.97` exceeds Stake's 96.70% per-mode
     RTP validator ceiling and will FAIL it. Set `RTP_TARGET=0.967` (env or the
     constant below) for an ACP-uploadable build.
"""

import os
from math import gcd  # noqa: F401  (kept for parity with sibling games)

from src.config.config import Config
from src.config.distributions import Distribution
from src.config.betmode import BetMode

# Theoretical RTP of every cash-out step (user spec = 0.97). NOTE: 0.97 > the ACP
# per-mode ceiling of 0.967 and will fail that validator. For a guaranteed
# ACP-valid build set RTP_TARGET=0.965 (0.967 as the target can round a hair over
# the ceiling after integer book rounding; 0.965 leaves a safe margin). Overridable
# via env for a one-switch retune.
RTP_TARGET = float(os.environ.get("RTP_TARGET", "0.97"))

# Global max-win cap (req: configurable, default 2000x). Any step whose raw
# multiplier is >= this is never published; a mode is rejected if a published step
# would exceed it. Overridable via env.
GLOBAL_MAX_MULT = float(os.environ.get("GLOBAL_MAX_MULT", "2000"))

# Simulations per mode. num_sims * q must be ~integer per outcome; the loss bucket
# absorbs the residual. 1e6 keeps even the rarest max-win outcome at ~80-90 books.
DEFAULT_NUM_SIMS = int(os.environ.get("NUM_SIMS", "1000000"))

_EPS = 1e-9

# --------------------------------------------------------------------- ladders
# Per-difficulty FULL raw multiplier ladders (payoutMultiplier = 0.97/cumSurv),
# 0-indexed by step. Includes the upper-tail steps >= 2000x that GLOBAL_MAX_MULT
# drops. These numbers are authoritative (user-supplied) — do NOT recompute.
_LADDERS = {
    "easy": [
        1.01042, 1.05435, 1.10227, 1.15476, 1.21250, 1.27632, 1.34722, 1.42647,
        1.51563, 1.61667, 1.73214, 1.86538, 2.02083, 2.20455, 2.42500, 2.69444,
        3.03125, 3.46429, 4.04167, 4.85000, 6.06250, 8.08333, 12.12500, 24.25000,
    ],
    "medium": [
        1.10227, 1.25974, 1.44870, 1.67744, 1.95702, 2.30237, 2.73407, 3.28088,
        3.98393, 4.90330, 6.12912, 7.80070, 10.14091, 13.52121, 18.59167, 26.55952,
        39.83929, 63.74286, 111.55000, 223.10000, 557.75000, 2231.00000,
    ],
    "hard": [
        1.21250, 1.53160, 1.95700, 2.53260, 3.32410, 4.43210, 6.01500, 8.32840,
        11.79860, 17.16150, 25.74230, 40.04360, 65.07080, 111.55000, 204.50830,
        409.01670, 920.28750, 2454.10000, 8589.35000, 51536.10000,
    ],
    "daredevil": [
        1.61670, 2.77140, 4.90330, 8.98940, 17.16150, 34.32310, 72.45980, 163.03460,
        395.94120, 1055.84320, 3167.52970, 11086.35380, 48040.86670, 288245.20000,
        3170697.20000,
    ],
}
DIFFICULTIES = ["easy", "medium", "hard", "daredevil"]

# The original uncapped Daredevil maximum that must NEVER be published (req 14).
_FORBIDDEN_MAX = 3170697.20


def _snap_floor(mult: float) -> float:
    """Floor-snap a multiplier onto the 0.1x grid (conservative: never rounds up)."""
    return (int(mult * 10 + _EPS)) / 10.0


class GameConfig(Config):
    """Chicken Crossing configuration — 4 difficulty ladders, multi-outcome per mode."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        super().__init__()
        self.game_id = "2_7_chicken_crossing"
        self.provider_number = 2  # placeholder — confirm ACP-assigned value before prod upload
        self.provider_name = "monstrum"
        self.game_name = "Chicken Crossing"
        self.working_name = "Chicken Crossing"
        self.win_type = "scatter"
        # Payouts floor-snapped onto the ACP 0.1x grid; keep the SDK grid check ON.
        self.lut_grid_exempt = False
        self.construct_paths()

        # No board mechanic: model a single revealed cell (1 reel x 1 row).
        self.num_reels = 1
        self.num_rows = [1] * self.num_reels

        self.num_sims = DEFAULT_NUM_SIMS
        self.tiers = self._build_tiers()
        self.wincap = max(t["max_win"] for t in self.tiers)  # global top (daredevil)
        self.rtp = max(t["rtp"] for t in self.tiers)
        self.mode_params = {}

        # Minimal boardless scaffolding (mirrors the dice / plinko games).
        self.paytable = {(1, "D"): 1.0}
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
        """Return one row per difficulty: snapped ladder, per-payout book counts, RTP.

        Applies the global cap (drop steps whose raw multiplier >= GLOBAL_MAX_MULT),
        floor-snaps each surviving multiplier onto the 0.1x grid, sets the per-step
        reach probability rho_k = RTP_TARGET/snapped_k (pins each step's RTP to
        RTP_TARGET after snapping), spreads a uniform cash-target weight w_k = 1/S,
        pools colliding payouts, and lays down exact integer book counts.
        """
        num_sims = self.num_sims
        rows = []
        for difficulty in DIFFICULTIES:
            raw_full = _LADDERS[difficulty]
            # Global cap: keep only steps strictly below the cap.
            published = [(k, r) for k, r in enumerate(raw_full) if r < GLOBAL_MAX_MULT]
            S = len(published)
            assert S >= 2, f"{difficulty}: fewer than 2 publishable steps"
            w = 1.0 / S  # uniform cash-target weight (RTP-invariant knob)

            steps = []  # per published step: dict of raw/snapped/cents/rho/q/cumsurv
            for k, raw in published:
                snapped = _snap_floor(raw)
                cents = int(round(snapped * 100))
                rho = RTP_TARGET / snapped
                steps.append(
                    {
                        "step": k,
                        "raw": raw,
                        "cumsurv": RTP_TARGET / raw,
                        "snapped": snapped,
                        "cents": cents,
                        "rho": rho,
                        "q": w * rho,
                    }
                )

            # Pool steps sharing a snapped payout into one distinct-payout outcome.
            payout_q = {}       # cents -> summed q
            payout_val = {}     # cents -> float multiplier
            payout_steps = {}   # cents -> [step indices]
            for s in steps:
                payout_q[s["cents"]] = payout_q.get(s["cents"], 0.0) + s["q"]
                payout_val[s["cents"]] = s["snapped"]
                payout_steps.setdefault(s["cents"], []).append(s["step"])

            # Exact integer book counts; loss bucket absorbs the residual.
            payout_count = {c: max(1, int(round(num_sims * q))) for c, q in payout_q.items()}
            win_books = sum(payout_count.values())
            loss_count = num_sims - win_books
            assert loss_count > 0, f"{difficulty}: no loss mass (win books {win_books} >= {num_sims})"

            realised_rtp = sum(payout_count[c] * payout_val[c] for c in payout_count) / num_sims

            # Cosmetic pop-step weights: marginal P(die exactly at step j) from cumSurv
            # (cumsurv_{-1}=1). Purely for the loss reveal; payout is always 0.
            pop_weights = {}
            prev_cs = 1.0
            for s in steps:
                cs = s["cumsurv"]
                pop_weights[s["step"]] = max(prev_cs - cs, 0.0)
                prev_cs = cs

            rows.append(
                {
                    "difficulty": difficulty,
                    "steps": steps,
                    "num_steps": S,
                    "max_win": steps[-1]["snapped"],
                    "num_sims": num_sims,
                    "payout_val": payout_val,
                    "payout_count": payout_count,
                    "payout_steps": payout_steps,
                    "loss_count": loss_count,
                    "pop_weights": pop_weights,
                    "rtp": realised_rtp,
                }
            )
        return rows

    # ---------------------------------------------------------------- betmodes
    def _build_bet_modes(self) -> list:
        """One bet mode per difficulty; one Distribution per distinct payout + a loss."""
        dummy_reels = {
            "reel_weights": {
                self.basegame_type: {"BR0": 1},
                self.freegame_type: {"BR0": 1},
            }
        }
        wincap_cents = int(round(self.wincap * 100))

        modes = []
        for row in self.tiers:
            difficulty = row["difficulty"]
            num_sims = row["num_sims"]

            criteria_payout = {}
            distributions = []
            # Winning outcomes (one per distinct snapped payout).
            for cents in sorted(row["payout_count"]):
                payout = row["payout_val"][cents]
                count = row["payout_count"][cents]
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
            # Loss outcome (pop -> pays 0). The pop step is drawn cosmetically at runtime.
            criteria_payout["0"] = 0.0
            distributions.append(
                Distribution(
                    criteria="0",
                    quota=(row["loss_count"] + 0.5) / num_sims,
                    win_criteria=0.0,
                    conditions={**dummy_reels, "force_wincap": False, "force_freegame": False},
                )
            )

            self.mode_params[difficulty] = {
                "difficulty": difficulty,
                "cost": 1.0,
                "num_steps": row["num_steps"],
                "num_sims": num_sims,
                "max_win": row["max_win"],
                "rtp": row["rtp"],
                # ladder for the setup event (snapped multiplier per published step)
                "ladder": [s["snapped"] for s in row["steps"]],
                # criteria -> forced payout
                "criteria_payout": criteria_payout,
                # payout cents -> published step indices (win cash-step reveal)
                "payout_steps": {str(c): ks for c, ks in row["payout_steps"].items()},
                # step index -> pop weight (loss pop-step reveal)
                "pop_weights": {str(k): w for k, w in row["pop_weights"].items()},
                # full per-step detail for tools/report.py
                "steps": row["steps"],
                "loss_count": row["loss_count"],
                "payout_count": {str(c): n for c, n in row["payout_count"].items()},
            }

            modes.append(
                BetMode(
                    name=difficulty,
                    cost=1.0,
                    rtp=row["rtp"],
                    max_win=row["max_win"],
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
        assert len(self.bet_modes) == len(self.tiers) == len(DIFFICULTIES), "unexpected mode count"
        assert self.wincap == max(t["max_win"] for t in self.tiers), "wincap must equal the top mode"

        expected_steps = {"easy": 24, "medium": 21, "hard": 17, "daredevil": 10}
        for row in self.tiers:
            difficulty = row["difficulty"]
            steps = row["steps"]
            num_sims = row["num_sims"]

            # Step count matches the 2000x-cap truncation.
            assert row["num_steps"] == expected_steps[difficulty], (
                f"{difficulty}: {row['num_steps']} steps, expected {expected_steps[difficulty]}"
            )

            for s in steps:
                # Global cap enforced: no published step at/above the cap.
                assert s["raw"] < GLOBAL_MAX_MULT, f"{difficulty} step {s['step']} raw {s['raw']} exceeds cap"
                # The forbidden Daredevil max is never published.
                assert abs(s["raw"] - _FORBIDDEN_MAX) > 1.0, f"{difficulty}: forbidden max published"
                # On the 0.1x grid, >= stake.
                assert s["cents"] >= 100 and s["cents"] % 10 == 0, (
                    f"{difficulty} step {s['step']}: {s['snapped']} off the 0.1x grid"
                )
                # Per-step RTP is pinned to RTP_TARGET after snapping (rho compensates).
                assert abs(s["rho"] * s["snapped"] - RTP_TARGET) < 1e-9, (
                    f"{difficulty} step {s['step']}: per-step RTP off target"
                )
                assert s["rho"] <= 1.0 + _EPS, f"{difficulty} step {s['step']}: rho > 1"

            # Ladder is strictly increasing (a real cash-out ladder).
            snaps = [s["snapped"] for s in steps]
            assert all(b >= a for a, b in zip(snaps, snaps[1:])), f"{difficulty}: ladder not monotone"

            # Exact integer book split (floor-safe "+0.5"), summing to num_sims.
            total = 0
            for cents, count in row["payout_count"].items():
                quota = (count + 0.5) / num_sims
                assert int(num_sims * quota) == count, f"{difficulty}: split off for payout {cents}"
                total += count
            loss_quota = (row["loss_count"] + 0.5) / num_sims
            assert int(num_sims * loss_quota) == row["loss_count"], f"{difficulty}: loss split off"
            total += row["loss_count"]
            assert total == num_sims, f"{difficulty}: books sum to {total}, expected {num_sims}"

            # Realised RTP recomputed from integer counts, near the target. Integer
            # book rounding perturbs RTP by up to ~0.5 book per distinct payout, i.e.
            # 0.5*sum(payouts)/num_sims — tiny at prod num_sims (1e6), larger for a
            # low-num_sims dev smoke. Scale the tolerance to that bound (+cushion).
            rounding_tol = sum(row["payout_val"].values()) / num_sims + 1e-6
            assert abs(row["rtp"] - RTP_TARGET) <= rounding_tol, (
                f"{difficulty}: realised RTP {row['rtp']:.4f} off target {RTP_TARGET} "
                f"by more than the rounding bound {rounding_tol:.4f}"
            )
