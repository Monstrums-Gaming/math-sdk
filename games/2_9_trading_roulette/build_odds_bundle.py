"""Post-build verifier + odds-bundle emitter for Trading Roulette (2_9).

Run AFTER a prod build (COMPRESSION=1 RUN_FORMAT_CHECKS=1). Re-verifies every published
artifact against the authoritative GameConfig, then emits `odds_bundle.json` (consumed by
frontend_demo/build_demo_data.py and the web app `apps/2-9-trading-roulette`). Kept OUT of
publish_files/ (it is not an RGS artifact).

Why this exists on top of `execute_all_tests`: that only proves the books agree with the
lookup table, and says nothing about whether a book's *narrative* is internally honest —
the `2_0_porkageddon` lesson. Here the equivalent risk is a `landRow` outside its zone on
a win (a chart that visibly lands in your cell yet pays nothing), or a landing
distribution that quietly drifts off the published conditional law.

Per mode it asserts, against publish_files/lookUpTable_<mode>_0.csv +
books_<mode>.jsonl.zst:
  * uniform LUT weights (1 per book);
  * payout set == {0, M*100 cents} exactly;
  * winning-row count == W, total rows == N, and Fraction(W, N) == Fraction(a, b);
  * recomputed RTP == (W/N)*M == config RTP (in [96.15%, 96.65%]);
  * every book: zoneRound result/isWin casing, zone id == the mode's cell,
    payoutMultiplier == cents, finalWin.amount == LUT payout, and `wincap` present IFF
    this is an exact-line win (global cap 21x) — win order `zoneRound -> [wincap] ->
    finalWin`;
  * the landRow audit (see `audit_land_rows`) — the verdict invariant, the exact split,
    row-coverage floors, the conditional landing law within 4 sigma, and the mechanical
    proof that landRow cannot move the RTP.

Usage:  PYTHONPATH="$PWD" ./env/bin/python games/2_9_trading_roulette/build_odds_bundle.py
"""

import io
import json
import math
import os
import sys
from fractions import Fraction

import zstandard as zstd

_HERE = os.path.dirname(os.path.abspath(__file__))
_LIB = os.path.join(_HERE, "library")
_PUBLISH = os.path.join(_LIB, "publish_files")
sys.path.insert(0, _HERE)

from game_config import (  # noqa: E402
    GameConfig,
    LAND_WEIGHTS,
    ROWS,
    ROW_MIN,
    ROW_MAX,
    RTP_FLOOR,
    RTP_CEIL,
    WIN_BOOKS_MIN,
)

_EPS = 1e-9

# Conditional-law tolerance. Every (mode, side, row) cell in this build has np >= ~200,
# so the normal approximation is sound; the build is seed-deterministic, so a pass is a
# permanent property of the artifact, not a lucky draw.
_LAW_SIGMA = 4.0

# Full row coverage is demanded only when the draw count comfortably saturates the pool
# (coupon-collector: at n >= 50 * pool the miss probability is astronomically small).
_COVERAGE_FACTOR = 50


def _read_lut(mode: str) -> dict:
    """Return {book_id: payout_cents} from the published LUT, asserting weight == 1."""
    path = os.path.join(_PUBLISH, f"lookUpTable_{mode}_0.csv")
    payout = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            sid, weight, pay = line.split(",")
            assert int(weight) == 1, f"{mode}: non-uniform weight {weight}"
            payout[int(sid)] = int(pay)
    return payout


def _read_books(mode: str):
    """Yield each decompressed book dict from books_<mode>.jsonl.zst."""
    path = os.path.join(_PUBLISH, f"books_{mode}.jsonl.zst")
    with open(path, "rb") as f:
        with zstd.ZstdDecompressor().stream_reader(f) as reader:
            for line in io.TextIOWrapper(reader, encoding="utf-8"):
                if line.strip():
                    yield json.loads(line)


def _conditional_law(zone: set, winning_side: bool) -> dict:
    """The published conditional landing law: row -> probability, over one verdict pool."""
    pool = [r for r in ROWS if (r in zone) == winning_side]
    total = sum(LAND_WEIGHTS[abs(r)] for r in pool)
    return {r: LAND_WEIGHTS[abs(r)] / total for r in pool}


def audit_land_rows(mode: str, row: dict, lrs: list, is_wins: list, payouts: list) -> dict:
    """Assert every landRow is honest, and that none of them can move the odds.

    `lrs` / `is_wins` / `payouts` are parallel per-book lists in LUT order.
    """
    cents, W, N = row["payout_cents"], row["W"], row["N"]
    zone = set(row["zone_rows"])

    # A1 — type and range.
    for lr in lrs:
        assert isinstance(lr, int), f"{mode}: landRow {lr!r} is not an integer"
        assert ROW_MIN <= lr <= ROW_MAX, f"{mode}: landRow {lr} outside [{ROW_MIN}, {ROW_MAX}]"

    # A2 — THE honesty invariant: the landed row decides the verdict, with no exceptions.
    for i, (lr, won) in enumerate(zip(lrs, is_wins)):
        assert (lr in zone) == won, (
            f"{mode} book {i}: landRow {lr} vs zone {sorted(zone)} contradicts isWin={won}"
        )

    # A3 — the landRow split must reproduce the published LUT split exactly.
    inside = sum(1 for lr in lrs if lr in zone)
    assert inside == W, f"{mode}: {inside} landRows in zone != W {W}"
    assert len(lrs) - inside == N - W, f"{mode}: outside-zone count off"

    # A4 — row coverage: neither side of the verdict may look canned. Full coverage is
    # demanded only where the draw count saturates the pool.
    win_rows = [lr for lr, won in zip(lrs, is_wins) if won]
    lose_rows = [lr for lr, won in zip(lrs, is_wins) if not won]
    complement = [r for r in ROWS if r not in zone]
    distinct_win, distinct_lose = len(set(win_rows)), len(set(lose_rows))
    if W >= _COVERAGE_FACTOR * len(zone):
        assert distinct_win == len(zone), (
            f"{mode}: win books cover {distinct_win}/{len(zone)} zone rows"
        )
    else:
        assert distinct_win >= 1, f"{mode}: no winning landRow at all"
    if (N - W) >= _COVERAGE_FACTOR * len(complement):
        assert distinct_lose == len(complement), (
            f"{mode}: lose books cover {distinct_lose}/{len(complement)} complement rows"
        )
    else:
        assert distinct_lose >= 1, f"{mode}: no losing landRow at all"

    # A5 — the conditional landing law. The sampler draws from the published weights
    # restricted to the verdict pool, so both conditional distributions are falsifiable.
    law = []
    for side_name, side_rows, n, winning_side in (
        ("win", win_rows, W, True),
        ("lose", lose_rows, N - W, False),
    ):
        theory = _conditional_law(zone, winning_side)
        if len(theory) < 2:
            continue  # single-row pool: A2/A3 already pin it completely
        counts = {}
        for lr in side_rows:
            counts[lr] = counts.get(lr, 0) + 1
        for r, p in sorted(theory.items()):
            empirical = counts.get(r, 0) / n
            se = math.sqrt(p * (1.0 - p) / n)
            z = (empirical - p) / se
            assert abs(z) <= _LAW_SIGMA, (
                f"{mode}: P(landRow={r} | {side_name}) empirical {empirical:.5f} vs law "
                f"{p:.5f} is {z:+.2f} sigma (> {_LAW_SIGMA})"
            )
            law.append({"side": side_name, "row": r, "empirical": empirical, "law": p, "z": z})

    # A6 — the mechanical proof that landRow is PRESENTATION data and cannot move the
    # odds: the payout must be a function of the verdict ALONE.
    win_payouts = {p for p, won in zip(payouts, is_wins) if won}
    lose_payouts = {p for p, won in zip(payouts, is_wins) if not won}
    assert win_payouts <= {cents}, f"{mode}: winning payouts vary with landRow: {win_payouts}"
    assert lose_payouts <= {0}, f"{mode}: losing payouts vary with landRow: {lose_payouts}"
    # ...so the RTP is fully determined by the win COUNT, independent of any landing row.
    assert abs(inside * cents / 100.0 / N - row["rtp"]) < 1e-9, (
        f"{mode}: RTP is not reproduced by the win count alone"
    )

    return {
        "distinctWinRows": distinct_win,
        "distinctLoseRows": distinct_lose,
        "law": law,
    }


def verify_mode(row: dict) -> dict:
    """Verify one cell mode's artifacts; return its odds-bundle entry."""
    cents = row["payout_cents"]
    mode = f"zone_{row['zone_id']}"
    M, W, N = row["multiplier"], row["W"], row["N"]
    a, b = row["a"], row["b"]
    is_top = row["zone_id"] == "line"

    lut = _read_lut(mode)
    assert len(lut) == N, f"{mode}: LUT has {len(lut)} rows != num_sims {N}"
    payset = set(lut.values())
    assert payset <= {0, cents}, f"{mode}: unexpected payouts {payset - {0, cents}}"
    win_rows = sum(1 for p in lut.values() if p == cents)
    assert win_rows == W, f"{mode}: {win_rows} winning rows != W {W}"
    assert sum(1 for p in lut.values() if p == 0) == N - W, f"{mode}: lose-row count off"
    # The k-scaled book count must not have perturbed the odds by even one ULP.
    assert Fraction(win_rows, len(lut)) == Fraction(a, b), (
        f"{mode}: published odds {win_rows}/{len(lut)} != {a}/{b}"
    )

    recon_rtp = sum(lut.values()) / 100.0 / N
    assert abs(recon_rtp - (W / N) * M) < 1e-9, f"{mode}: RTP recompute mismatch"
    assert abs(recon_rtp - row["rtp"]) < 1e-9, f"{mode}: RTP {recon_rtp} != config {row['rtp']}"
    assert RTP_FLOOR - _EPS <= recon_rtp <= RTP_CEIL + _EPS, f"{mode}: RTP {recon_rtp} out of band"

    # Event <-> LUT cross-check on every book, collecting the landRows for the audit.
    n_books = n_win = 0
    lrs, is_wins, payouts = [], [], []
    for bk in _read_books(mode):
        n_books += 1
        bid = bk["id"]
        evs = bk["events"]
        rnd = evs[0]
        assert rnd["type"] == "zoneRound", f"{mode} {bid}: first event {rnd['type']}"
        assert rnd["zone"] == row["zone_id"], f"{mode} {bid}: zone {rnd['zone']} != mode's cell"
        assert rnd["payoutMultiplier"] == cents, f"{mode} {bid}: payoutMultiplier != {cents}"
        assert abs(rnd["winChance"] - W / N) < 1e-12, f"{mode} {bid}: winChance != W/N"
        fw = next(e for e in evs if e["type"] == "finalWin")
        wincaps = [e for e in evs if e["type"] == "wincap"]
        lut_pay = lut[bid]
        assert fw["amount"] == lut_pay, f"{mode} {bid}: finalWin {fw['amount']} != LUT {lut_pay}"
        assert bk["payoutMultiplier"] == lut_pay, f"{mode} {bid}: book payoutMultiplier != LUT"
        # The payout derives from the criteria, never from the landing row.
        assert rnd["isWin"] == (bk["criteria"] != "0"), f"{mode} {bid}: isWin != criteria"

        lrs.append(rnd["landRow"])
        is_wins.append(lut_pay > 0)
        payouts.append(lut_pay)

        if lut_pay > 0:
            n_win += 1
            assert rnd["isWin"] is True and rnd["result"] == "Win", f"{mode} {bid}: win casing"
            assert fw["amount"] == cents, f"{mode} {bid}: win finalWin != {cents}"
            # Global cap 21x: only the exact-line cell's payout reaches it.
            if is_top:
                assert len(wincaps) == 1 and wincaps[0]["amount"] == cents, f"{mode} {bid}: wincap"
                assert [e["type"] for e in evs] == ["zoneRound", "wincap", "finalWin"], (
                    f"{mode} {bid}: win order"
                )
            else:
                assert not wincaps, f"{mode} {bid}: non-line win emitted a wincap event"
                assert [e["type"] for e in evs] == ["zoneRound", "finalWin"], (
                    f"{mode} {bid}: win order"
                )
        else:
            assert rnd["isWin"] is False and rnd["result"] == "Lose", f"{mode} {bid}: lose casing"
            assert fw["amount"] == 0, f"{mode} {bid}: lose finalWin != 0"
            assert not wincaps, f"{mode} {bid}: lose book has a wincap event"
            assert [e["type"] for e in evs] == ["zoneRound", "finalWin"], f"{mode} {bid}: lose order"

    assert n_books == N, f"{mode}: {n_books} books != num_sims {N}"
    assert n_win == W, f"{mode}: {n_win} winning books != W {W}"

    land = audit_land_rows(mode, row, lrs, is_wins, payouts)

    return {
        "zone": row["zone_id"],
        "rows": list(row["zone_rows"]),
        "multiplier": M,
        "multiplierCents": cents,
        "winChance": W / N,
        "rtp": recon_rtp,
        "numSims": N,
        "winBooks": W,
        "exactOdds": f"{a}/{b}",
        "std": row["std"],
        "outcomes": [
            {"payoutCents": cents, "weight": W},
            {"payoutCents": 0, "weight": N - W},
        ],
        "land": land,
    }


def main() -> None:
    config = GameConfig()

    modes = {}
    rtps = []
    worst_z = 0.0
    for row in config.tiers:
        entry = verify_mode(row)
        modes[f"zone_{row['zone_id']}"] = entry
        rtps.append(entry["rtp"])
        zs = [abs(p["z"]) for p in entry["land"]["law"]]
        worst_z = max([worst_z] + zs)
        print(
            f"  zone_{row['zone_id']:<7} M={entry['multiplier']:<5} "
            f"{entry['exactOdds']:>6}  RTP={entry['rtp']*100:.4f}%  "
            f"books={entry['numSims']:<5} win={entry['winBooks']:<5} "
            f"rows={entry['land']['distinctWinRows']}/{entry['land']['distinctLoseRows']}  "
            f"maxZ={max(zs) if zs else 0:.2f}  OK"
        )

    spread = max(rtps) - min(rtps)
    # 0.50% — the tightened window, satisfying both readings of the ACP cross-mode rule.
    assert spread <= 0.005 + _EPS, f"cross-mode RTP spread {spread} > 0.50%"

    bundle = {
        "game_id": config.game_id,
        "rtp": max(rtps),
        "rtpMin": min(rtps),
        "rtpMax": max(rtps),
        "maxWin": config.wincap,
        "defaultMode": "zone_half_o",
        "disabledAutoplay": False,
        # The board is published data: the frontend renders cells and the landing law
        # display straight from here, never from hard-coded geometry.
        "board": {
            "rowMin": ROW_MIN,
            "rowMax": ROW_MAX,
            "landWeights": {str(r): LAND_WEIGHTS[abs(r)] for r in ROWS},
            "landWeightTotal": sum(LAND_WEIGHTS[abs(r)] for r in ROWS),
        },
        # The landing law is the game's transparency claim — stated precisely: the row is
        # certified in the book, always on the verdict's side of the bet's zone, drawn
        # from the published weights conditional on the verdict. The odds themselves come
        # from the lookup table alone (per-cell pinned, NOT one coherent wheel).
        "landingLaw": {
            "weights": "proportional to 1/multiplier per |row| (published above)",
            "unit": "signed integer row, 0 = on the line, +/-7 = off-scale tails",
            "note": (
                "landRow is certified in the book and consistent with the payout: inside "
                "the bet's zone on a win, outside it on a loss. It cannot alter the odds, "
                "which derive from the lookup table alone. The unconditional row "
                "frequencies observed while betting a cell are the mixture of the two "
                "published conditional laws at that cell's published win chance."
            ),
        },
        "modes": modes,
    }

    out_path = os.path.join(_LIB, "odds_bundle.json")
    assert not out_path.startswith(_PUBLISH), "odds_bundle.json must stay out of publish_files/"
    with open(out_path, "w") as f:
        json.dump(bundle, f, indent=2)

    total = sum(m["numSims"] for m in modes.values())
    print(
        f"\nALL {len(modes)} MODES VERIFIED  ({total} books, RTP "
        f"{min(rtps)*100:.4f}-{max(rtps)*100:.4f}%, spread {spread*100:.4f}%, "
        f"worst conditional-law deviation {worst_z:.2f} sigma)"
    )
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
