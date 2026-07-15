"""
Dynamic mystery-box game configuration.

Unlike the per-game folders (``games/mystery_box``, ``games/3_2_mystery_box_cash_paradise``)
this config is authored by a JSON **manifest** rather than hardcoded. One folder + one
manifest per game. The manifest carries the game identity/economics and the prize table
in the exact internal ``prize_table`` shape, so the JSON *is* the prize table.

Manifest selection: ``GameConfig(manifest_path)`` argument, else the ``GAME_MANIFEST``
environment variable. Output is written to ``games/<manifest game_id>/library`` because
the engine derives every path from ``config.game_id`` (not this folder's name).

cost_model:
  - absent / "box_cost" (default): payouts are authored literally as RGS multipliers and
    the base bet mode cost == box_cost (reproduces the static games; fails the ACP
    "cost must be 1.0" validator unless the manifest is already authored for cost 1.0).
  - "unit": the loader divides each payout by box_cost and snaps to the 0.1x grid, sets
    base mode cost == 1.0 and derives wincap as the new max multiplier (ACP-valid).
"""

import json
import os

from src.config.config import Config
from src.config.distributions import Distribution
from src.config.betmode import BetMode


def _snap_to_grid(multiplier: float) -> float:
    """Snap a payout multiplier to the RGS 0.1x grid (nearest 10 cents); sub-0.1x -> 0."""
    cents = int(round(round(multiplier * 100) / 10.0)) * 10
    return cents / 100.0


class GameConfig(Config):
    """Manifest-driven mystery-box configuration — one bet mode, one prize per purchase."""

    # NOTE: intentionally NO _instance/__new__ singleton — it would break
    # GameConfig(manifest_path) and leak state across builds.

    def __init__(self, manifest_path: str = None, game_id_suffix: str = ""):
        super().__init__()
        manifest = self._load_manifest(manifest_path)

        # --- game-level identity / economics ---
        # game_id_suffix (e.g. "_dev") keeps dev builds in a separate games/<id>_dev/
        # tree so they never clobber a production build's publish_files.
        self.game_id = manifest["game_id"] + game_id_suffix
        self.provider_number = int(manifest["provider_number"])
        self.provider_name = manifest["provider_name"]
        self.game_name = manifest["game_name"]
        self.working_name = manifest.get("working_name", manifest["game_name"])
        self.box_cost = float(manifest["box_cost"])
        self.win_type = manifest.get("win_type", "scatter")
        self.rtp = float(manifest["rtp"])
        self.cost_model = manifest.get("cost_model", "box_cost")
        if self.cost_model not in ("box_cost", "unit"):
            raise RuntimeError(f"cost_model must be 'box_cost' or 'unit', got {self.cost_model!r}.")

        # --- prize table: the manifest 'prizes' block IS the prize_table ---
        # Each entry: {name, payout (RGS multiplier), prob, criteria}. Copy so the
        # optional unit transform below never mutates the on-disk manifest object.
        self.prize_table = {sku: dict(info) for sku, info in manifest["prizes"].items()}

        # --- optional ACP-valid transform (cost 1.0) ---
        # NB: prizes that fall below the 0.1x grid become 0 but KEEP their authored
        # criteria. A zero-payout prize forces a 0 win identically whether its criteria
        # is "0" or a per-sku bucket, and keeping distinct criteria preserves the exact
        # per-criteria sim quotas (merging into one "0" bucket produces a float like
        # 0.582 whose int(num_sims*quota) truncates and drifts the published odds by ±1).
        if self.cost_model == "unit":
            for info in self.prize_table.values():
                info["payout"] = _snap_to_grid(float(info["payout"]) / self.box_cost)
            self.wincap = max(info["payout"] for info in self.prize_table.values())
        else:
            self.wincap = float(manifest["wincap"])

        # criteria "0" is authoritative — it means "pays nothing" (e.g. a sub-0.1x
        # catalog value like $0.01 that the RGS cannot pay). Force those payouts to 0
        # so the authored display value need not itself be RGS-valid.
        for info in self.prize_table.values():
            if info["criteria"] == "0":
                info["payout"] = 0.0

        self.construct_paths()

        self.num_reels = 1
        self.num_rows = [1] * self.num_reels

        self._validate_prize_table()

        # Each prize is a single-symbol "pay" of kind 1; the board is never evaluated,
        # payouts come straight from prize_table.
        self.paytable = {(1, sym): info["payout"] for sym, info in self.prize_table.items()}

        self.include_padding = False
        self.special_symbols = {"wild": [], "scatter": [], "multiplier": []}

        # No free spins in a mystery box.
        self.freespin_triggers = {self.basegame_type: {}, self.freegame_type: {}}
        self.anticipation_triggers = {self.basegame_type: 0, self.freegame_type: 0}

        # Helper lookups consumed by run_spin (built once).
        self.prize_payouts = {sym: info["payout"] for sym, info in self.prize_table.items()}
        self.prize_names = {sym: info["name"] for sym, info in self.prize_table.items()}
        self.criteria_draw_weights = self._build_criteria_draw_weights()

        # Only rare prizes are recorded for the force/search files (perf: keeps
        # imprint_wins from going O(n^2) on common prizes).
        self.record_prize_threshold = 0.01
        self.record_prizes = {
            sym for sym, info in self.prize_table.items() if info["prob"] <= self.record_prize_threshold
        }

        # Write a reels/BR0.csv (prize skus, one per line) into the built game's folder
        # for parity with the static games, then read it back through the same code path.
        # read_reels_csv returns a single reel whose rows are the skus: [[sku, sku, ...]].
        # SKUs must be alphanumeric (read_reels_csv strips non-alnum characters).
        os.makedirs(self.reels_path, exist_ok=True)
        br0_path = os.path.join(self.reels_path, "BR0.csv")
        with open(br0_path, "w", encoding="UTF-8") as f:
            f.write("\n".join(self.prize_table.keys()) + "\n")
        self.reels = {"BR0": self.read_reels_csv(br0_path)}
        self.padding_reels = {
            self.basegame_type: self.reels["BR0"],
            self.freegame_type: self.reels["BR0"],
        }

        base_cost = 1.0 if self.cost_model == "unit" else self.box_cost
        self.bet_modes = [
            BetMode(
                name="base",
                cost=base_cost,
                rtp=self.rtp,
                max_win=self.wincap,
                auto_close_disabled=False,
                is_feature=False,
                is_buybonus=False,
                distributions=self._build_distributions(),
            ),
        ]

        # Run knobs consumed by run.py.
        self.build_opts = dict(manifest.get("build", {}))

    def _load_manifest(self, manifest_path: str) -> dict:
        """Resolve the manifest path (arg -> GAME_MANIFEST env) and load it.

        Accepts an absolute path, a path relative to the CWD, a bare filename, or a
        ``manifests/<file>`` relative path — resolving against this folder's manifests/.
        """
        path = manifest_path or os.environ.get("GAME_MANIFEST")
        if not path:
            raise RuntimeError(
                "No manifest: pass GameConfig(manifest_path) or set GAME_MANIFEST env var."
            )
        here = os.path.dirname(os.path.abspath(__file__))
        candidates = [
            path,
            os.path.join(here, path),
            os.path.join(here, "manifests", os.path.basename(path)),
        ]
        resolved = next((c for c in candidates if os.path.isfile(c)), None)
        if resolved is None:
            raise FileNotFoundError(f"Manifest not found. Tried: {candidates}")
        with open(resolved, "r", encoding="UTF-8") as f:
            return json.load(f)

    def _validate_prize_table(self) -> None:
        """Guard the authored odds, payouts and criteria before the engine consumes them."""
        total_prob = round(sum(info["prob"] for info in self.prize_table.values()), 8)
        if total_prob != 1.0:
            raise RuntimeError(f"Prize probabilities must sum to 1.0, got {total_prob}.")

        if self.rtp >= 1.0:
            raise RuntimeError(f"rtp must be < 1.0, got {self.rtp}.")

        wincap_skus = []
        for sym, info in self.prize_table.items():
            for key in ("name", "payout", "prob", "criteria"):
                if key not in info:
                    raise RuntimeError(f"Prize {sym} missing required key '{key}'.")

            payout_cents = round(info["payout"] * 100, 6)
            if payout_cents != int(payout_cents):
                raise RuntimeError(f"Prize {sym} payout {info['payout']} is finer than 0.01x; not RGS-valid.")
            payout_int = int(payout_cents)
            if payout_int != 0 and (payout_int < 10 or payout_int % 10 != 0):
                raise RuntimeError(
                    f"Prize {sym} payout {info['payout']} -> {payout_int} violates RGS increments of 10."
                )
            if info["payout"] > self.wincap:
                raise RuntimeError(f"Prize {sym} payout {info['payout']} exceeds wincap {self.wincap}.")

            if info["criteria"] == "wincap":
                wincap_skus.append(sym)

        if len(wincap_skus) != 1:
            raise RuntimeError(f"Exactly one prize must use criteria 'wincap', got {wincap_skus}.")
        if self.prize_table[wincap_skus[0]]["payout"] != self.wincap:
            raise RuntimeError(
                f"wincap prize {wincap_skus[0]} payout "
                f"{self.prize_table[wincap_skus[0]]['payout']} != wincap {self.wincap}."
            )

    def _build_criteria_draw_weights(self) -> dict:
        """Map each criteria to the relative draw weights of the prizes it contains."""
        weights: dict[str, dict[str, float]] = {}
        for sym, info in self.prize_table.items():
            weights.setdefault(info["criteria"], {})[sym] = info["prob"]
        return weights

    def _build_distributions(self) -> list:
        """One distribution per criteria; quotas equal the summed prize odds."""
        dummy_reels = {
            "reel_weights": {
                self.basegame_type: {"BR0": 1},
                self.freegame_type: {"BR0": 1},
            }
        }
        criteria_quota: dict[str, float] = {}
        for info in self.prize_table.values():
            criteria_quota[info["criteria"]] = round(
                criteria_quota.get(info["criteria"], 0.0) + info["prob"], 8
            )

        distributions = []
        for criteria, quota in criteria_quota.items():
            if criteria == "0":
                win_criteria = 0.0
                conditions = {**dummy_reels, "force_wincap": False, "force_freegame": False}
            elif criteria == "wincap":
                win_criteria = self.wincap
                conditions = {**dummy_reels, "force_wincap": True, "force_freegame": False}
            else:
                # A paying, non-cap prize: force the exact payout of its single prize.
                (prize_payout,) = {self.prize_payouts[s] for s in self.criteria_draw_weights[criteria]}
                win_criteria = prize_payout
                conditions = {**dummy_reels, "force_wincap": False, "force_freegame": False}

            distributions.append(
                Distribution(criteria=criteria, quota=quota, win_criteria=win_criteria, conditions=conditions)
            )
        return distributions
