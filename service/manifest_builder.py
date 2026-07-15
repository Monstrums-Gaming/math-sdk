"""Assemble a full dynamic-mystery-box manifest from simplified backoffice box inputs.

The backoffice sends a *box*: identity + price + a flat list of prize rows (name, catalog
payout multiplier, draw probability). This module derives everything the manifest format
requires but an admin shouldn't have to hand-compute:

- **criteria** — one bucket per distinct effective payout; the single highest paying prize
  is ``"wincap"``; any prize whose payout snaps to 0 on the RGS 0.1x grid becomes ``"0"``.
- **wincap** — the max catalog payout.
- **rtp** — expected payout / cost, from the grid-snapped effective payouts.
- **num_sims** — fixed (settings.MANIFEST_NUM_SIMS); the odds must keep num_sims*prob
  integral (validated downstream by run.py --validate).

The result is best-effort; the endpoint runs ``run.py --validate`` on it so any remaining
invariant violation (probs != 1.0, non-integral quotas, rtp >= 1.0) comes back as a clean
error rather than a silently-wrong game.
"""

import math
import re

from service.config import settings

# How far the incoming probabilities may drift from 1.0 before we treat it as an authoring
# error rather than rounding noise. Coarse decimals (e.g. 0.99999) fall well inside this and
# get snapped to an exact distribution; a fat-fingered 0.9 / weights summing to 100 do not.
_PROB_SUM_TOLERANCE = 0.01


class BuildError(ValueError):
    """Raised for inputs we can reject before the validate subprocess (clear 400s)."""


def _normalize_prob_counts(enriched: list, num_sims: int) -> None:
    """Snap the prizes' draw probabilities onto the ``num_sims`` integer grid, in place.

    The RGS math requires the probabilities to sum to *exactly* 1.0 and each ``num_sims*prob``
    to be integral (odds are published as ``round(num_sims*prob)`` books per prize). Backoffice
    inputs are coarse (a handful of decimals) and routinely sum to 0.99999/1.00001. Rather than
    reject that, we allocate ``num_sims`` draws across the prizes by largest-remainder (Hamilton)
    apportionment, then set ``prob = count / num_sims`` — exact multiples of ``1/num_sims`` that
    sum to 1.0. Genuinely wrong odds (sum far from 1.0) still raise a clear error.
    """
    probs = [e["prob"] for e in enriched]
    if any(p < 0 for p in probs):
        raise BuildError("prize probabilities must be non-negative.")
    total = sum(probs)
    if total <= 0:
        raise BuildError("prize probabilities must be positive and sum to ~1.0.")
    if abs(total - 1.0) > _PROB_SUM_TOLERANCE:
        raise BuildError(
            f"prize probabilities sum to {total:.6f}; they must sum to 1.0 "
            f"(within {_PROB_SUM_TOLERANCE}). Fix the odds — the service only auto-corrects "
            f"rounding drift, not a real mismatch."
        )

    # Largest-remainder apportionment of num_sims across the prizes (normalized by `total`,
    # so a 0.99999 sum becomes an exact num_sims split with no bias toward any prize).
    scaled = [p / total * num_sims for p in probs]
    counts = [int(math.floor(s)) for s in scaled]
    residual = num_sims - sum(counts)  # in [0, len(enriched)]
    order = sorted(range(len(scaled)), key=lambda i: scaled[i] - counts[i], reverse=True)
    for i in range(residual):
        counts[order[i]] += 1

    for e, c, p in zip(enriched, counts, probs):
        if c == 0 and p > 0:
            raise BuildError(
                f"prize {e['sku']!r} probability {p:g} is too rare for num_sims={num_sims} "
                f"(it would never be drawn); raise its probability or num_sims."
            )
        e["prob"] = c / num_sims
        e["count"] = c


def _snap_to_grid(multiplier: float) -> float:
    """Snap a payout multiplier to the RGS 0.1x grid (nearest 10 cents); sub-0.1x -> 0.
    Mirrors games/mystery_box_dynamic/game_config.py::_snap_to_grid exactly."""
    cents = int(round(round(multiplier * 100) / 10.0)) * 10
    return cents / 100.0


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "box"


def _effective_payout(catalog_payout: float, box_cost: float, cost_model: str) -> float:
    """The payout the RGS actually pays for this prize, after the cost model + grid snap."""
    raw = catalog_payout / box_cost if cost_model == "unit" else float(catalog_payout)
    return _snap_to_grid(raw)


def assemble_manifest(spec: dict) -> dict:
    """Build a full manifest dict from a simplified box spec. Raises BuildError on inputs
    we can reject up front; deeper invariants are left to run.py --validate."""
    game_name = spec["game_name"]
    box_cost = float(spec["box_cost"])
    if box_cost <= 0:
        raise BuildError("box_cost must be > 0.")
    cost_model = spec.get("cost_model", "unit")
    if cost_model not in ("unit", "box_cost"):
        raise BuildError("cost_model must be 'unit' or 'box_cost'.")

    prizes_in = spec["prizes"]
    if not prizes_in:
        raise BuildError("at least one prize is required.")

    num_sims = int(spec.get("num_sims") or settings.MANIFEST_NUM_SIMS)

    # Enrich each prize with its SKU and effective (grid-snapped) payout.
    enriched = []
    for i, p in enumerate(prizes_in):
        enriched.append({
            "sku": p.get("sku") or f"P{i + 1}",
            "name": p["name"],
            "payout": float(p["payout"]),
            "prob": float(p["prob"]),
            "eff": _effective_payout(p["payout"], box_cost, cost_model),
        })

    skus = [e["sku"] for e in enriched]
    if len(set(skus)) != len(skus):
        raise BuildError(f"prize SKUs must be unique, got {skus}.")

    # Snap odds onto the num_sims grid so they sum to exactly 1.0 with integral quotas.
    _normalize_prob_counts(enriched, num_sims)

    paying = [e for e in enriched if e["eff"] > 0]
    if not paying:
        raise BuildError("no prize pays out: every payout snaps to 0 on the 0.1x grid.")

    # criteria: one "wincap" (the single max effective payout), "0" for zero-payout prizes,
    # and a bucket keyed by effective cents for every other distinct paying value.
    max_eff = max(e["eff"] for e in paying)
    wincap_taken = False
    for e in enriched:
        if e["eff"] == 0:
            e["criteria"] = "0"
        elif e["eff"] == max_eff and not wincap_taken:
            e["criteria"] = "wincap"
            wincap_taken = True
        else:
            e["criteria"] = f"p_{int(round(e['eff'] * 100))}"

    # wincap value = max catalog payout (used by box_cost; unit derives its own from eff).
    wincap = max(e["payout"] for e in enriched)

    # rtp = EV / cost, from the effective payouts the player actually receives.
    cost = 1.0 if cost_model == "unit" else box_cost
    ev = sum(e["eff"] * e["prob"] for e in enriched)
    rtp = round(ev / cost, 6)
    if rtp >= 1.0:
        raise BuildError(f"prizes pay {rtp:.4f} RTP (>= 1.0); lower payouts or odds.")

    game_id = spec.get("game_id") or f"{int(spec['provider_number'])}_{_slug(game_name)}"

    build = {
        "num_sims": num_sims,
        "compression": True,
        "run_format_checks": True,
        "num_threads": 1,
        "batching_size": min(50000, num_sims),
    }
    build.update(spec.get("build") or {})

    return {
        "game_id": game_id,
        "provider_number": int(spec["provider_number"]),
        "provider_name": spec["provider_name"],
        "game_name": game_name,
        "working_name": spec.get("working_name") or game_name,
        "box_cost": box_cost,
        "wincap": wincap,
        "rtp": rtp,
        "win_type": spec.get("win_type", "scatter"),
        "cost_model": cost_model,
        "build": build,
        "prizes": {
            e["sku"]: {
                "name": e["name"],
                "payout": e["payout"],
                "prob": e["prob"],
                "criteria": e["criteria"],
            }
            for e in enriched
        },
    }
