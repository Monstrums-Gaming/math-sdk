"""
Battleships (2_3) — game configuration (conserved-board, per-click wager model).

A Stake-style Mines game built as **per-click independent wagers** on a **conserved
board**. On a 5x5 board a difficulty fixes exactly `ships` winning tiles and
`mines = 25 - ships` losing tiles. Each tile click is a SEPARATE `/wallet/play`
wager, priced by the board's CURRENT remaining composition:

  - reveal a SHIP  -> the wager pays the current rung's multiplier (banked), and one
    ship leaves the pool (shipsLeft -= 1).
  - reveal a MINE  -> the wager loses its stake, and one mine leaves the pool
    (minesLeft -= 1). The run CONTINUES (a mine no longer ends it).

The run ends when every ship is found (shipsLeft == 0), when every mine is cleared
(minesLeft == 0 -> the remaining tiles are all ships, auto-revealed for free), or when
the player presses END. Because the board is conserved, the number of ships/mines the
player meets always equals the difficulty's counts — mines can never exceed `mines`,
and all `ships` ships are findable. (The frontend state machine enforces those caps.)

## Modes: one per remaining-board STATE  `<shipsLeft>_<minesLeft>`

Odds depend only on the remaining pool, so a mode is keyed by `(shipsLeft, minesLeft)`
and is SHARED across difficulties (state (5,8) has the same odds whether it came from an
easy or hard start). We publish every state reachable from the four starts, with
shipsLeft >= 1 and minesLeft >= 1 (at minesLeft == 0 the frontend stops wagering and
reveals the rest for free, so those states are never bet — and never published):

    easy     15 ships / 10 mines     start state 15_10
    medium   12 ships / 13 mines     start state 12_13
    hard      8 ships / 17 mines     start state 8_17
    extreme   4 ships / 21 mines     start state 4_21

The union of reachable states is ~234 modes. Mode name `<shipsLeft>_<minesLeft>` is
dot-free (the ACP publisher parses `<mode>` out of `books_<mode>.jsonl.zst`).

## The rung (rarity-priced) + probability

At state (shipsLeft, minesLeft) with tilesLeft = shipsLeft + minesLeft, the true ship
probability (draw WITHOUT replacement) is `p = shipsLeft / tilesLeft`. The wager pays
`multiplier = floor_to_grid(RTP_TARGET / p)` — rising as ships get rarer, so the last
rare ship (many mines still down) is the big hit. Because minesLeft >= 1 and
shipsLeft <= 15, `p < 1` always, so the multiplier is always >= 1.0x (no sub-1x rungs).
Each mode wins with probability = the smallest-denominator rational `a/b` whose realised
RTP `(a/b)*multiplier` lands in `[96.00%, 96.70%]` (limbo/chicken-run
`_simplest_fraction_in`); `num_sims = b` yields exactly `a` winning books, so the
published odds equal the book counts (optimiser off).

## ACP rules satisfied
  1. 0.1x LUT grid (payouts floor-snapped; grid check ON).
  2. Per-mode RTP in [96.00%, 96.70%].
  3. Cross-mode RTP spread <= 1.00%.
"""

import os
from fractions import Fraction
from math import floor

from src.config.config import Config
from src.config.distributions import Distribution
from src.config.betmode import BetMode

BOARD_TILES = 25

# RTP used to shape the ladder payout NUMBERS.
RTP_TARGET = float(os.environ.get("RTP_TARGET", "0.965"))
# ACP per-mode RTP band the realised win/lose RTP must land in.
RTP_FLOOR = 0.960
RTP_CEIL = 0.967
# Global max-win cap (informational; the largest single rung is well below it).
GLOBAL_MAX_MULT = float(os.environ.get("GLOBAL_MAX_MULT", "2000"))
_EPS = 1e-9

# difficulty -> number of WINNING ship tiles (mines = BOARD_TILES - ships).
# Ordered easy -> extreme; more ships = easier. These fix each run's START state.
DIFFICULTIES = {
    "easy": 15,
    "medium": 12,
    "hard": 8,
    "extreme": 4,
}


def _snap_floor(mult: float) -> float:
    """Floor-snap a multiplier onto the 0.1x grid (conservative: never rounds up)."""
    return (int(mult * 10 + _EPS)) / 10.0


def _reachable_states() -> list:
    """Every (shipsLeft, minesLeft) a run can BET on, unioned across the four starts.

    From a start (S, M) any (s, m) with 1 <= s <= S and 1 <= m <= M is reachable
    (reveal S-s ships and M-m mines in some order). minesLeft == 0 is excluded: at
    that point the remaining tiles are all ships and the frontend reveals them free.
    Returned sorted for a stable, deterministic mode order.
    """
    states = set()
    for ships in DIFFICULTIES.values():
        mines = BOARD_TILES - ships
        for s in range(1, ships + 1):
            for m in range(1, mines + 1):
                states.add((s, m))
    return sorted(states)


def _simplest_fraction_in(lo: Fraction, hi: Fraction) -> Fraction:
    """Smallest-denominator fraction x with lo <= x <= hi (requires 0 < lo <= hi)."""
    if lo > hi:
        lo, hi = hi, lo
    n = floor(lo)
    if n >= lo:
        return Fraction(n)
    if n + 1 <= hi:
        return Fraction(n + 1)
    return n + 1 / _simplest_fraction_in(1 / (hi - n), 1 / (lo - n))


class GameConfig(Config):
    """Battleships configuration — per-(shipsLeft, minesLeft) win/lose modes."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        super().__init__()
        self.game_id = "2_3_battleships"
        self.provider_number = 2  # placeholder — confirm ACP-assigned value before prod upload
        self.provider_name = "monstrum"
        self.game_name = "Battleships"
        self.working_name = "Battleships"
        self.win_type = "scatter"
        self.lut_grid_exempt = False
        self.construct_paths()

        # No board mechanic in the sim: model a single revealed cell (1 reel x 1 row).
        self.num_reels = 1
        self.num_rows = [1] * self.num_reels

        self.tiers = self._build_tiers()
        self.wincap = max(t["multiplier"] for t in self.tiers)
        self.rtp = max(t["rtp"] for t in self.tiers)
        self.mode_params = {}

        # Minimal boardless scaffolding (mirrors the dice / limbo / chicken games).
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
        """One row per reachable (shipsLeft, minesLeft): rarity payout + win prob."""
        rows = []
        for s, m in _reachable_states():
            tiles_left = s + m
            raw = RTP_TARGET / (s / tiles_left)  # rarity price: RTP / P(ship)
            snapped = _snap_floor(raw)
            payout_cents = int(round(snapped * 100))
            assert payout_cents >= 100 and payout_cents % 10 == 0, (
                f"{s}_{m} payout {snapped} off the 0.1x grid / below 1.0x"
            )
            p_frac = Fraction(payout_cents, 100)
            lo = Fraction(round(RTP_FLOOR * 1000), 1000) / p_frac
            hi = Fraction(round(RTP_CEIL * 1000), 1000) / p_frac
            prob = _simplest_fraction_in(lo, hi)
            a, b = prob.numerator, prob.denominator
            realised_rtp = float(prob * p_frac)
            assert RTP_FLOOR - _EPS <= realised_rtp <= RTP_CEIL + _EPS, (
                f"{s}_{m} RTP {realised_rtp:.4f} outside band"
            )
            rows.append(
                {
                    "ships_left": s,
                    "mines_left": m,
                    "tiles_left": tiles_left,
                    "multiplier": snapped,
                    "payout_cents": payout_cents,
                    "win_chance": a / b,
                    "rtp": realised_rtp,
                    "W": a,  # winning book count
                    "N": b,  # num_sims (denominator)
                }
            )
        return rows

    # ---------------------------------------------------------------- betmodes
    def _build_bet_modes(self) -> list:
        """One bet mode per (shipsLeft, minesLeft); each a forced win/lose split."""
        dummy_reels = {
            "reel_weights": {
                self.basegame_type: {"BR0": 1},
                self.freegame_type: {"BR0": 1},
            }
        }

        modes = []
        for row in self.tiers:
            m = row["multiplier"]
            W, N = row["W"], row["N"]
            name = f"{row['ships_left']}_{row['mines_left']}"

            win_quota = (W + 0.5) / N
            lose_quota = (N - W + 0.5) / N

            if m >= self.wincap:
                win_criteria_name = "wincap"
                win_conditions = {**dummy_reels, "force_wincap": True, "force_freegame": False}
            else:
                win_criteria_name = "win"
                win_conditions = {**dummy_reels, "force_wincap": False, "force_freegame": False}
            lose_conditions = {**dummy_reels, "force_wincap": False, "force_freegame": False}

            self.mode_params[name] = {
                "ships_left": row["ships_left"],
                "mines_left": row["mines_left"],
                "tiles_left": row["tiles_left"],
                "multiplier": m,
                "multiplier_cents": row["payout_cents"],
                "win_chance": row["win_chance"],
                "num_sims": N,
            }

            distributions = [
                Distribution(
                    criteria=win_criteria_name,
                    quota=win_quota,
                    win_criteria=m,
                    conditions=win_conditions,
                ),
                Distribution(
                    criteria="0",
                    quota=lose_quota,
                    win_criteria=0.0,
                    conditions=lose_conditions,
                ),
            ]

            modes.append(
                BetMode(
                    name=name,
                    cost=1.0,
                    rtp=row["rtp"],
                    max_win=self.wincap,
                    auto_close_disabled=False,
                    is_feature=False,
                    is_buybonus=False,
                    distributions=distributions,
                )
            )
        return modes

    # ---------------------------------------------------------------- validate
    def _validate(self) -> None:
        assert self.wincap == max(t["multiplier"] for t in self.tiers), "wincap must equal the top mode"
        assert len(self.bet_modes) == len(self.tiers) == len(_reachable_states()), "mode count off"

        rtps = [t["rtp"] for t in self.tiers]
        assert max(rtps) - min(rtps) <= 0.01 + _EPS, (
            f"cross-mode RTP spread {max(rtps) - min(rtps):.4f} > 1%"
        )

        # Rarity is monotonic in the pool: for a fixed minesLeft, fewer ships left =>
        # rarer ship => higher (or equal, after grid-snap) multiplier.
        by_mines = {}
        for t in self.tiers:
            by_mines.setdefault(t["mines_left"], []).append((t["ships_left"], t["multiplier"]))
        for mines_left, pairs in by_mines.items():
            pairs.sort(key=lambda p: -p[0])  # ships_left descending
            mults = [mult for _, mult in pairs]
            assert all(b >= a for a, b in zip(mults, mults[1:])), (
                f"minesLeft={mines_left}: multiplier not non-decreasing as ships get rarer"
            )

        for row in self.tiers:
            mult, W, N, cents = row["multiplier"], row["W"], row["N"], row["payout_cents"]
            assert isinstance(cents, int) and cents >= 100, f"payout {mult} must be an integer >= 100 cents"
            assert cents % 10 == 0, f"payout {mult} off the 0.1x grid"
            assert row["ships_left"] + row["mines_left"] == row["tiles_left"], "ships+mines != tiles"
            assert RTP_FLOOR - _EPS <= (W / N) * mult <= RTP_CEIL + _EPS, (
                f"{row['ships_left']}_{row['mines_left']} RTP out of band"
            )
            win_quota = (W + 0.5) / N
            lose_quota = (N - W + 0.5) / N
            assert int(N * win_quota) == W, f"win split off for {row['ships_left']}_{row['mines_left']}"
            assert int(N * lose_quota) == N - W, f"lose split off for {row['ships_left']}_{row['mines_left']}"
            assert int(N * win_quota) + int(N * lose_quota) == N, "split does not sum to N"
