"""
Porkageddon (2_0) — game configuration.

A Stake-style **pig-fighting battler**, converted from the shipped PixiJS client
(`frontend_demo/`, v1.0.5) to the Stake Engine LUT/replay model. Like the dice
(`2_4`), limbo (`2_5`), plinko (`2_6`) and chicken (`2_7`/`2_8`) games this is a
**direct-probability** game: no reels, no free spins, Rust optimiser disabled. The
odds come straight from the distribution quotas.

Every number lives in `pork_math.py` — read its module docstring first, it is the
real specification. This file is the thin SDK-facing wrapper: it turns the tables
`pork_math.build_stances()` produces into `BetMode`/`Distribution` objects and
asserts the ACP rules before the engine consumes them.

## Modes: three stances, all `cost = 1.0`

    skirmish   6-8 rounds   pot 1.1x-2.7x   golden 0.6%   max win    10.0x
    brawl      3-4 rounds   pot 1.4x-2.5x   golden 1.0%   max win  2000.0x
    bloodbath  2-3 rounds   pot 1.4x-2.7x   golden 2.0%   max win  2000.0x

Mode names are dot-free (the ACP publisher parses `<mode>` out of
`books_<mode>.jsonl.zst`). The conversion plan's stance costs (2.0 / 4.0 / 7.0)
are NOT used as `cost` — that would fail the ACP "Base Mode Cost must be 1.0x"
validator. They survive only as the per-stance `pool_norm` divisor, and real stake
sizing belongs in the operator's ACP bet-level template.

## Multi-outcome: one Distribution per distinct payout

Same shape as plinko / chicken_crossing. Per mode: one `Distribution` per distinct
snapped payout (the pot body, ~12 rungs, plus one per Golden Pig tier) and one loss
bucket that absorbs the integer-count residual — 16-18 distributions per mode. The
mode's own top payout takes the `"wincap"` criteria; the rest are `p_<cents>`.

## The three ACP math rules

1. **0.1x LUT grid** — every non-zero payout is integer cents, `>= 10`, a multiple
   of 10. `lut_grid_exempt = False` keeps `verify_lookup_format` enforcing it.
2. **Per-mode RTP in [90%, 96.70%]** — all three modes realise **96.35%**,
   recomputed from the integer book counts (exactly what the ACP derives from the
   LUT). `pork_math` pins this with a one-book correction pass, so it holds at any
   `num_sims`.
3. **Cross-mode spread <= 1.00%** — measured spread is under 1e-5.

## `max_win` is PER MODE, and that matters

`src/state/run_sims.py` overwrites `config.wincap` with `BetMode.max_win` before
each mode's sims. A `max_win` **below** a mode's true top payout makes
`update_final_win` clamp the payout, so `final_win != win_criteria`,
`check_repeat` never accepts, and `run_spin`'s `while self.repeat` loop spins
forever. A `max_win` **above** it publishes a `maxWin` the LUT cannot reach. So
each mode declares its own true maximum (10.0 / 2000.0 / 2000.0) and `self.wincap`
is the global top (2000.0).

Consequence: the standard `wincap` event fires on exactly the top-payout books of
each mode (`porkResult -> wincap -> finalWin`), including skirmish's 10.0x books.
That is intended; the client may treat it as a no-op.
"""

import os
from fractions import Fraction

import pork_math as pm
from src.config.betmode import BetMode
from src.config.config import Config
from src.config.distributions import Distribution

# The ACP's cross-mode RTP consistency limit.
MAX_CROSS_MODE_SPREAD = Fraction(1, 100)


class GameConfig(Config):
    """Porkageddon configuration — three stances, multi-outcome per mode."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        super().__init__()
        self.game_id = "2_0_porkageddon"
        self.provider_number = 2  # placeholder — confirm the ACP-assigned value before upload
        self.provider_name = "monstrum"
        self.game_name = "Porkageddon"
        self.working_name = "Porkageddon"
        self.win_type = "scatter"
        # Payouts are floor-snapped onto the ACP 0.1x grid; keep the SDK check ON.
        self.lut_grid_exempt = False
        self.construct_paths()

        # No board mechanic: model a single revealed cell (1 reel x 1 row).
        self.num_reels = 1
        self.num_rows = [1] * self.num_reels

        self.num_sims = int(os.environ.get("NUM_SIMS", pm.DEFAULT_NUM_SIMS))
        self.tiers = pm.build_stances(self.num_sims)
        self.wincap = max(float(t["max_win"]) for t in self.tiers)
        self.rtp = max(float(t["rtp"]) for t in self.tiers)
        self.mode_params = {}

        # Minimal boardless scaffolding (mirrors the dice / plinko / chicken games).
        # A single dummy symbol keeps the symbol map self-consistent; the board and
        # paytable are never evaluated.
        self.paytable = {(1, "P"): 1.0}
        self.include_padding = False
        self.special_symbols = {"wild": [], "scatter": [], "multiplier": []}
        self.freespin_triggers = {self.basegame_type: {}, self.freegame_type: {}}
        self.anticipation_triggers = {self.basegame_type: 0, self.freegame_type: 0}

        self.reels = {"BR0": self.read_reels_csv(os.path.join(self.reels_path, "BR0.csv"))}
        self.padding_reels = {
            self.basegame_type: self.reels["BR0"],
            self.freegame_type: self.reels["BR0"],
        }

        self.bet_modes = self._build_bet_modes()
        self._validate()

    # ---------------------------------------------------------------- betmodes
    def _build_bet_modes(self) -> list:
        """One bet mode per stance; one Distribution per distinct payout plus a loss."""
        dummy_reels = {
            "reel_weights": {
                self.basegame_type: {"BR0": 1},
                self.freegame_type: {"BR0": 1},
            }
        }
        modes = []
        for row in self.tiers:
            stance = row["stance"]
            num_sims = row["num_sims"]
            mode_max_cents = max(row["count"])
            tier_mult = {t: m for t, m, _w in row["golden_sources"]}

            criteria_payout, criteria_meta, distributions = {}, {}, []
            for cents in sorted(row["count"]):
                payout = cents / 100.0
                count = row["count"][cents]
                # Floor-safe quota: get_sim_splits does int(num_sims * quota), so the
                # +0.5 offset reproduces `count` exactly (the chicken_crossing trick).
                quota = (count + 0.5) / num_sims
                is_top = cents == mode_max_cents
                criteria = "wincap" if is_top else f"p_{cents}"
                tier = row["tier_of"].get(cents)
                criteria_payout[criteria] = payout
                criteria_meta[criteria] = {
                    "kind": row["kind"][cents],
                    "cents": cents,
                    "tier": tier,
                    "tierMultiplier": tier_mult.get(tier, 1),
                }
                distributions.append(
                    Distribution(
                        criteria=criteria,
                        quota=quota,
                        win_criteria=payout,
                        conditions={
                            **dummy_reels,
                            "force_wincap": is_top,
                            "force_freegame": False,
                        },
                    )
                )

            criteria_payout["0"] = 0.0
            criteria_meta["0"] = {"kind": "loss", "cents": 0, "tier": None, "tierMultiplier": 1}
            distributions.append(
                Distribution(
                    criteria="0",
                    quota=(row["loss_count"] + 0.5) / num_sims,
                    win_criteria=0.0,
                    conditions={**dummy_reels, "force_wincap": False, "force_freegame": False},
                )
            )

            pool_norm = row["pool_norm"]
            self.mode_params[stance] = {
                "stance": stance,
                "label": row["label"],
                "cost": 1.0,
                "num_sims": num_sims,
                "hp": row["hp"],
                "rtp": float(row["rtp"]),
                "win_rate": float(row["win_rate"]),
                "max_win": float(row["max_win"]),
                "pool_norm": float(pool_norm),
                "pool_norm_thousandths": int(pool_norm * 1000),
                "costs": pm.cost_values(pm.STANCES[stance]),
                "slots": row["slots"],
                "heal_slot": row["heal_slot"],
                "heal_cost_hundredths": pm.STANCES[stance]["heal_cost_h"],
                "rounds": row["rounds"],
                "criteria_payout": criteria_payout,
                "criteria_meta": criteria_meta,
                # payout cents -> the (rounds, pool) shapes that snap to it
                "body_sources": {str(c): v for c, v in row["body_sources"].items()},
                # the full (rounds, pool) PMF, for golden wins and losses
                "pool_sources": row["pool_sources"],
                "golden_sources": row["golden_sources"],
                "payout_count": {str(c): n for c, n in row["count"].items()},
                "loss_count": row["loss_count"],
            }

            modes.append(
                BetMode(
                    name=stance,
                    cost=1.0,
                    rtp=float(row["rtp"]),
                    max_win=float(row["max_win"]),
                    auto_close_disabled=False,
                    is_feature=False,
                    is_buybonus=False,
                    distributions=distributions,
                )
            )
        return modes

    # ---------------------------------------------------------------- validate
    def _validate(self) -> None:
        """Assert every ACP rule and internal invariant before the engine runs."""
        assert len(self.bet_modes) == len(self.tiers) == len(pm.STANCE_NAMES), "unexpected mode count"
        assert self.wincap == max(float(t["max_win"]) for t in self.tiers), "wincap must be the global top"
        assert self.wincap == float(pm.GLOBAL_MAX_MULT), (
            f"top payout {self.wincap} should land on the {pm.GLOBAL_MAX_MULT}x cap"
        )

        rtps = [t["rtp"] for t in self.tiers]
        spread = max(rtps) - min(rtps)
        assert spread <= MAX_CROSS_MODE_SPREAD, (
            f"cross-mode RTP spread {float(spread):.6f} exceeds the ACP 1.00% cap"
        )

        for row in self.tiers:
            stance, num_sims = row["stance"], row["num_sims"]

            # ACP rule 2: per-mode RTP band.
            assert pm.RTP_FLOOR <= row["rtp"] <= pm.RTP_CEIL, (
                f"{stance}: RTP {float(row['rtp']):.6f} outside "
                f"[{float(pm.RTP_FLOOR)}, {float(pm.RTP_CEIL)}]"
            )

            # ACP rule 1: the 0.1x grid, and nothing above the global cap.
            for cents in row["count"]:
                assert cents >= 10 and cents % 10 == 0, f"{stance}: {cents}c off the 0.1x grid"
                assert cents <= pm.MAX_CENTS, f"{stance}: {cents}c exceeds the {pm.GLOBAL_MAX_MULT}x cap"

            # Exact integer book split (floor-safe "+0.5"), summing to num_sims.
            total = 0
            for cents, count in row["count"].items():
                quota = (count + 0.5) / num_sims
                assert int(num_sims * quota) == count, f"{stance}: split off for {cents}c"
                total += count
            loss_quota = (row["loss_count"] + 0.5) / num_sims
            assert int(num_sims * loss_quota) == row["loss_count"], f"{stance}: loss split off"
            assert total + row["loss_count"] == num_sims, (
                f"{stance}: books sum to {total + row['loss_count']}, expected {num_sims}"
            )

            # A body rung and a golden badge must never share a payout value, or the
            # reveal would be ambiguous.
            for cents in row["tier_of"]:
                assert row["kind"][cents] == "golden", f"{stance}: {cents}c tier/body collision"

            # Every published pool must be reachable by a real battle, and must snap
            # to the payout it is filed under — otherwise the transcript generator
            # cannot reproduce the drawn outcome.
            costs = tuple(pm.cost_values(pm.STANCES[stance]))
            norm = int(row["pool_norm"] * 1000)
            reach = {}
            for rounds, pool_h, _w in row["pool_sources"]:
                if rounds not in reach:
                    reach[rounds] = pm.cost_sequence_counts(costs, 2 * rounds)
                assert reach[rounds].get((2 * rounds, pool_h), 0) > 0, (
                    f"{stance}: pool {pool_h} unreachable in {2 * rounds} picks"
                )
            for cents, sources in row["body_sources"].items():
                for _rounds, pool_h, _w in sources:
                    assert pm.body_cents(pool_h, norm) == cents, (
                        f"{stance}: pool {pool_h} does not snap to {cents}c"
                    )

        # Every mode must be simulated: run.py keys num_sim_args off mode_params.
        assert set(self.mode_params) == {m.get_name() for m in self.bet_modes}, (
            "mode_params / bet_modes mismatch"
        )
        for mode in self.bet_modes:
            assert mode.get_cost() == 1.0, f"{mode.get_name()}: base mode cost must be 1.0"
