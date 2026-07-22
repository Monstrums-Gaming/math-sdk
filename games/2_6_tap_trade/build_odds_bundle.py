"""Post-build verifier + odds-bundle emitter for Tap Trade (2_6).

Run AFTER a prod build (COMPRESSION=1 RUN_FORMAT_CHECKS=1). Re-verifies every
published artifact against the authoritative GameConfig, then emits `odds_bundle.json`
(consumed by frontend_demo/build_demo_data.py and any future web app). Kept OUT of
publish_files/ (it is not an RGS artifact).

Per mode it asserts, against publish_files/lookUpTable_<mode>_0.csv +
books_<mode>.jsonl.zst:
  * uniform LUT weights (1 per book);
  * payout set == {0, M*100 cents} exactly;
  * winning-row count == a, total rows == b (= num_sims);
  * recomputed RTP == (a/b)*M == config RTP (in [96.00%, 96.70%]);
  * every book: cellCall result/isWin/payoutMultiplier casing, finalWin.amount == LUT
    payout, win books emit `cellCall -> wincap -> finalWin` (wincap.amount == payout),
    lose books emit `cellCall -> finalWin` (no wincap).

Usage:  PYTHONPATH="$PWD" ./env/bin/python games/2_6_tap_trade/build_odds_bundle.py
"""

import io
import json
import os
import sys

import zstandard as zstd

_HERE = os.path.dirname(os.path.abspath(__file__))
_LIB = os.path.join(_HERE, "library")
_PUBLISH = os.path.join(_LIB, "publish_files")
sys.path.insert(0, _HERE)

from game_config import GameConfig, RTP_FLOOR, RTP_CEIL  # noqa: E402

_EPS = 1e-9


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


def verify_mode(row: dict) -> dict:
    """Verify one ladder mode's artifacts; return its odds-bundle entry."""
    cents = row["payout_cents"]
    mode = f"call_{cents}"
    M, W, N = row["multiplier"], row["W"], row["N"]

    lut = _read_lut(mode)
    assert len(lut) == N, f"{mode}: LUT has {len(lut)} rows != num_sims {N}"
    payset = set(lut.values())
    assert payset <= {0, cents}, f"{mode}: unexpected payouts {payset - {0, cents}}"
    win_rows = sum(1 for p in lut.values() if p == cents)
    assert win_rows == W, f"{mode}: {win_rows} winning rows != a {W}"
    assert sum(1 for p in lut.values() if p == 0) == N - W, f"{mode}: lose-row count off"

    recon_rtp = sum(lut.values()) / 100.0 / N
    assert abs(recon_rtp - (W / N) * M) < 1e-9, f"{mode}: RTP recompute mismatch"
    assert abs(recon_rtp - row["rtp"]) < 1e-9, f"{mode}: RTP {recon_rtp} != config {row['rtp']}"
    assert RTP_FLOOR - _EPS <= recon_rtp <= RTP_CEIL + _EPS, f"{mode}: RTP {recon_rtp} out of band"

    # Event <-> LUT cross-check on every book.
    n_books = n_win = 0
    for b in _read_books(mode):
        n_books += 1
        bid = b["id"]
        evs = b["events"]
        cell = evs[0]
        assert cell["type"] == "cellCall", f"{mode} {bid}: first event {cell['type']}"
        assert cell["payoutMultiplier"] == cents, f"{mode} {bid}: cellCall payoutMultiplier"
        fw = next(e for e in evs if e["type"] == "finalWin")
        wincaps = [e for e in evs if e["type"] == "wincap"]
        lut_pay = lut[bid]
        assert fw["amount"] == lut_pay, f"{mode} {bid}: finalWin {fw['amount']} != LUT {lut_pay}"
        assert b["payoutMultiplier"] == lut_pay, f"{mode} {bid}: book payoutMultiplier != LUT"
        if lut_pay > 0:
            n_win += 1
            assert cell["isWin"] is True and cell["result"] == "Win", f"{mode} {bid}: win casing"
            assert fw["amount"] == cents, f"{mode} {bid}: win finalWin != {cents}"
            assert len(wincaps) == 1 and wincaps[0]["amount"] == cents, f"{mode} {bid}: wincap"
            assert [e["type"] for e in evs] == ["cellCall", "wincap", "finalWin"], f"{mode} {bid}: win order"
        else:
            assert cell["isWin"] is False and cell["result"] == "Lose", f"{mode} {bid}: lose casing"
            assert fw["amount"] == 0, f"{mode} {bid}: lose finalWin != 0"
            assert not wincaps, f"{mode} {bid}: lose book has a wincap event"
            assert [e["type"] for e in evs] == ["cellCall", "finalWin"], f"{mode} {bid}: lose order"
    assert n_books == N, f"{mode}: {n_books} books != num_sims {N}"
    assert n_win == W, f"{mode}: {n_win} winning books != a {W}"

    return {
        "multiplier": M,
        "multiplierCents": cents,
        "winChance": W / N,
        "rtp": recon_rtp,
        "numSims": N,
        "outcomes": [
            {"payoutCents": cents, "weight": W},
            {"payoutCents": 0, "weight": N - W},
        ],
    }


def main() -> None:
    config = GameConfig()
    rows = sorted(config.tiers, key=lambda r: r["payout_cents"])

    modes = {}
    rtps = []
    for row in rows:
        entry = verify_mode(row)
        modes[f"call_{row['payout_cents']}"] = entry
        rtps.append(entry["rtp"])
        print(f"  call_{row['payout_cents']:<6} M={entry['multiplier']:<5} "
              f"a/b={row['W']}/{row['N']}  RTP={entry['rtp']*100:.2f}%  OK")

    spread = max(rtps) - min(rtps)
    assert spread <= 0.01 + _EPS, f"cross-mode RTP spread {spread} > 1%"

    bundle = {
        "game_id": config.game_id,
        "rtpMin": min(rtps),
        "rtpMax": max(rtps),
        "ladder": [row["payout_cents"] for row in rows],
        "modes": modes,
    }

    out_path = os.path.join(_LIB, "odds_bundle.json")
    assert not out_path.startswith(_PUBLISH), "odds_bundle.json must stay out of publish_files/"
    with open(out_path, "w") as f:
        json.dump(bundle, f, indent=2)

    print(f"\nALL {len(modes)} MODES VERIFIED  (RTP {min(rtps)*100:.2f}-{max(rtps)*100:.2f}%, "
          f"spread {spread*100:.4f}%)")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
