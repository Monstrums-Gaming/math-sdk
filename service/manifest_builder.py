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

import re

from service.config import settings


class BuildError(ValueError):
    """Raised for inputs we can reject before the validate subprocess (clear 400s)."""


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
