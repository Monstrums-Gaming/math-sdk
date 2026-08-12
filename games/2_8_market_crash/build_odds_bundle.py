"""Post-build verifier + odds-bundle emitter for Market Crash (2_8).

Run AFTER a prod build (COMPRESSION=1 RUN_FORMAT_CHECKS=1). Re-verifies every published
artifact against the authoritative GameConfig, then emits `odds_bundle.json` (consumed by
frontend_demo/build_demo_data.py and the web app `apps/2-8-market-crash`). Kept OUT of
publish_files/ (it is not an RGS artifact).

Why this exists on top of `execute_all_tests`: that only proves the books agree with the
lookup table, and says nothing about whether a book's *narrative* is internally honest —
the `2_0_porkageddon` lesson, where an earlier revision silently published out-of-range
damage numbers that passed every RGS check. Here the equivalent risk is a `crashPoint` on
the wrong side of its target, or one that quietly drifts off the crash law.

Per mode it asserts, against publish_files/lookUpTable_<mode>_0.csv +
books_<mode>.jsonl.zst:
  * uniform LUT weights (1 per book);
  * payout set == {0, T*100 cents} exactly;
  * winning-row count == W, total rows == N, and Fraction(W, N) == Fraction(a, b) — i.e.
    the k-scaled book count did not perturb the published odds;
  * recomputed RTP == (W/N)*T == config RTP (in [96.15%, 96.65%]);
  * every book: crashRound result/isWin casing, target == payoutMultiplier == cents,
    finalWin.amount == LUT payout, and `wincap` present IFF this is a top-rung win
    (global cap 100x) — win order `crashRound -> [wincap] -> finalWin`;
  * the crashPoint audit (see `audit_crash_points`) — the verdict invariant, the exact
    split, the cap atom, the distinct-value floors, the survival law within 4 sigma, and
    the mechanical proof that crashPoint cannot move the RTP.

Usage:  PYTHONPATH="$PWD" ./env/bin/python games/2_8_market_crash/build_odds_bundle.py
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
    RTP_FLOOR,
    RTP_CEIL,
    WIN_BOOKS_MIN,
    CRASH_CAP_MULTIPLE,
)

_EPS = 1e-9

# Survival-law tolerance. The generator's worst observed deviation across modes and probe
# points is ~1.9 sigma, so a 4-sigma gate is both safe against false alarms and tight
# enough to catch a genuinely wrong distribution.
_LAW_SIGMA = 4.0
_LAW_PROBES = (1.5, 2.0, 3.0, 5.0, 10.0, 50.0)


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


def audit_crash_points(mode: str, row: dict, cps: list, is_wins: list, payouts: list) -> dict:
    """Assert every crashPoint is honest, and that none of them can move the odds.

    `cps` / `is_wins` / `payouts` are parallel per-book lists in LUT order.
    """
    cents, T, R = row["payout_cents"], row["sell_at"], row["rtp"]
    W, N, cap = row["W"], row["N"], row["cap_hundredths"]

    # A1 — type and range.
    for cp in cps:
        assert isinstance(cp, int), f"{mode}: crashPoint {cp!r} is not an integer"
        assert 100 <= cp <= cap, f"{mode}: crashPoint {cp} outside [100, {cap}]"

    # A2 — THE honesty invariant: the rug decides the verdict, with no exceptions.
    for i, (cp, won) in enumerate(zip(cps, is_wins)):
        assert (cp >= cents) == won, (
            f"{mode} book {i}: crashPoint {cp} vs target {cents} contradicts isWin={won}"
        )

    # A3 — the crashPoint split must reproduce the published LUT split exactly.
    above = sum(1 for cp in cps if cp >= cents)
    assert above == W, f"{mode}: {above} crashPoints >= target != W {W}"
    assert len(cps) - above == N - W, f"{mode}: below-target count off"

    # A4 — the truncation atom at the display cap stays near its designed target/cap.
    at_cap = sum(1 for cp in cps if cp == cap)
    assert at_cap <= math.ceil(0.015 * W), (
        f"{mode}: {at_cap} wins pinned at the cap {cap} (> 1.5% of {W})"
    )

    # A5/A6 — enough distinct values that neither animation looks canned.
    #
    # Both floors carry a 0.9 slack because saturation is unreachable, not because the
    # generator is loose: a losing crash point can only take one of (cents - 100)
    # displayable hundredths below the target, and the 1/u density spreads unevenly across
    # them, so coupon-collector misses a handful of the rarer values even at thousands of
    # draws (crash_400 lands 298 of a possible 300). The check exists to catch a canned or
    # collapsed distribution, not to demand every value.
    win_cps = [cp for cp, won in zip(cps, is_wins) if won]
    lose_cps = [cp for cp, won in zip(cps, is_wins) if not won]
    distinct_win = len(set(win_cps))
    assert distinct_win >= 0.9 * min(WIN_BOOKS_MIN, W), (
        f"{mode}: only {distinct_win} distinct winning crashPoints across {W} win books"
    )
    distinct_lose = len(set(lose_cps))
    lose_floor = 0.9 * min(cents - 100, 0.10 * (N - W))
    assert distinct_lose >= lose_floor, (
        f"{mode}: only {distinct_lose} distinct losing crashPoints across {N - W} books "
        f"(floor {lose_floor:.0f})"
    )

    # A7 — the survival law. The conditional sampler is built to reproduce the
    # UNCONDITIONAL law P(C >= x) = R/x at every x, so this is a real falsifiable check on
    # the whole distribution, not just its two tails.
    law = []
    for x in _LAW_PROBES:
        x_h = int(round(100 * x))
        if x_h >= cap:
            break
        theory = min(1.0, R / x)
        empirical = sum(1 for cp in cps if cp >= x_h) / N
        se = math.sqrt(theory * (1.0 - theory) / N)
        if se > 0:
            z = (empirical - theory) / se
            assert abs(z) <= _LAW_SIGMA, (
                f"{mode}: P(C >= {x}x) empirical {empirical:.5f} vs law {theory:.5f} "
                f"is {z:+.2f} sigma (> {_LAW_SIGMA})"
            )
            law.append({"x": x, "empirical": empirical, "law": theory, "z": z})

    # A8 — the mechanical proof that crashPoint is PRESENTATION data and cannot move the
    # odds. The payout must be a function of the verdict ALONE: two books sharing a
    # verdict must pay the same no matter how far apart their crash points are. If any
    # crashPoint value leaked into the payout path, one of these groups would hold more
    # than one distinct payout, and the RTP would then depend on the crashPoint
    # distribution rather than only on how many books win.
    win_payouts = {p for p, won in zip(payouts, is_wins) if won}
    lose_payouts = {p for p, won in zip(payouts, is_wins) if not won}
    assert win_payouts <= {cents}, f"{mode}: winning payouts vary with crashPoint: {win_payouts}"
    assert lose_payouts <= {0}, f"{mode}: losing payouts vary with crashPoint: {lose_payouts}"
    # ...so the RTP is fully determined by the win COUNT, independent of any crash point.
    assert abs(above * cents / 100.0 / N - R) < 1e-9, (
        f"{mode}: RTP is not reproduced by the win count alone"
    )

    return {
        "capHundredths": cap,
        "atomAtCap": cents / cap,
        "booksAtCap": at_cap,
        "instantRugShareOfLosses": row["q_atom"],
        "distinctWinCrashPoints": distinct_win,
        "distinctLoseCrashPoints": distinct_lose,
        "minCrashPoint": min(cps),
        "maxCrashPoint": max(cps),
        "law": law,
    }


def verify_mode(row: dict) -> dict:
    """Verify one ladder mode's artifacts; return its odds-bundle entry."""
    cents = row["payout_cents"]
    mode = f"crash_{cents}"
    T, W, N = row["sell_at"], row["W"], row["N"]
    a, b = row["a"], row["b"]
    is_top = cents == int(round(GameConfig().wincap * 100))

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
    assert abs(recon_rtp - (W / N) * T) < 1e-9, f"{mode}: RTP recompute mismatch"
    assert abs(recon_rtp - row["rtp"]) < 1e-9, f"{mode}: RTP {recon_rtp} != config {row['rtp']}"
    assert RTP_FLOOR - _EPS <= recon_rtp <= RTP_CEIL + _EPS, f"{mode}: RTP {recon_rtp} out of band"

    # Event <-> LUT cross-check on every book, collecting the crashPoints for the audit.
    n_books = n_win = 0
    cps, is_wins, payouts = [], [], []
    for bk in _read_books(mode):
        n_books += 1
        bid = bk["id"]
        evs = bk["events"]
        rnd = evs[0]
        assert rnd["type"] == "crashRound", f"{mode} {bid}: first event {rnd['type']}"
        assert rnd["target"] == cents, f"{mode} {bid}: target {rnd['target']} != {cents}"
        assert rnd["payoutMultiplier"] == cents, f"{mode} {bid}: payoutMultiplier != target"
        assert abs(rnd["winChance"] - W / N) < 1e-12, f"{mode} {bid}: winChance != W/N"
        fw = next(e for e in evs if e["type"] == "finalWin")
        wincaps = [e for e in evs if e["type"] == "wincap"]
        lut_pay = lut[bid]
        assert fw["amount"] == lut_pay, f"{mode} {bid}: finalWin {fw['amount']} != LUT {lut_pay}"
        assert bk["payoutMultiplier"] == lut_pay, f"{mode} {bid}: book payoutMultiplier != LUT"
        # The payout derives from the criteria, never from the crash point.
        assert rnd["isWin"] == (bk["criteria"] != "0"), f"{mode} {bid}: isWin != criteria"

        cps.append(rnd["crashPoint"])
        is_wins.append(lut_pay > 0)
        payouts.append(lut_pay)

        if lut_pay > 0:
            n_win += 1
            assert rnd["isWin"] is True and rnd["result"] == "Win", f"{mode} {bid}: win casing"
            assert fw["amount"] == cents, f"{mode} {bid}: win finalWin != {cents}"
            # Global cap 100x: only the top rung's payout reaches it.
            if is_top:
                assert len(wincaps) == 1 and wincaps[0]["amount"] == cents, f"{mode} {bid}: wincap"
                assert [e["type"] for e in evs] == ["crashRound", "wincap", "finalWin"], (
                    f"{mode} {bid}: win order"
                )
            else:
                assert not wincaps, f"{mode} {bid}: non-top-rung win emitted a wincap event"
                assert [e["type"] for e in evs] == ["crashRound", "finalWin"], (
                    f"{mode} {bid}: win order"
                )
        else:
            assert rnd["isWin"] is False and rnd["result"] == "Lose", f"{mode} {bid}: lose casing"
            assert fw["amount"] == 0, f"{mode} {bid}: lose finalWin != 0"
            assert not wincaps, f"{mode} {bid}: lose book has a wincap event"
            assert [e["type"] for e in evs] == ["crashRound", "finalWin"], f"{mode} {bid}: lose order"

    assert n_books == N, f"{mode}: {n_books} books != num_sims {N}"
    assert n_win == W, f"{mode}: {n_win} winning books != W {W}"

    crash = audit_crash_points(mode, row, cps, is_wins, payouts)

    return {
        "target": T,
        "targetCents": cents,
        "multiplier": T,
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
        "crash": crash,
    }


def main() -> None:
    config = GameConfig()
    rows = sorted(config.tiers, key=lambda r: r["payout_cents"])

    modes = {}
    rtps = []
    worst_z = 0.0
    for row in rows:
        entry = verify_mode(row)
        modes[f"crash_{row['payout_cents']}"] = entry
        rtps.append(entry["rtp"])
        zs = [abs(p["z"]) for p in entry["crash"]["law"]]
        worst_z = max([worst_z] + zs)
        print(
            f"  crash_{row['payout_cents']:<6} T={entry['target']:<6} "
            f"{entry['exactOdds']:>7}  RTP={entry['rtp']*100:.4f}%  "
            f"books={entry['numSims']:<6} win={entry['winBooks']:<5} "
            f"cp[{entry['crash']['minCrashPoint']}..{entry['crash']['maxCrashPoint']}] "
            f"distinct={entry['crash']['distinctWinCrashPoints']}/"
            f"{entry['crash']['distinctLoseCrashPoints']}  "
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
        "defaultMode": "crash_200",
        "disabledAutoplay": False,
        "ladder": [row["payout_cents"] for row in rows],
        # The crash law is the game's transparency claim: the win probability quoted for a
        # SELL AT is exactly this survival function read at that target.
        "crashLaw": {
            "survival": "rtp / x",
            "capRule": f"min({CRASH_CAP_MULTIPLE} * target, 10000x)",
            "unit": "integer hundredths",
            "note": (
                "crashPoint is certified in the book and consistent with the payout: "
                ">= target on a win, < target on a loss. It cannot alter the odds, which "
                "derive from the lookup table alone."
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
        f"worst survival-law deviation {worst_z:.2f} sigma)"
    )
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
