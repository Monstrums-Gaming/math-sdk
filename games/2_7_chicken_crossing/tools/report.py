"""Chicken Crossing (2_7) — ladder / RTP / max-win reports + LUT cross-check.

Standalone. Instantiates GameConfig (the source of truth) to print, per difficulty:
  * the full ladder table (step, cumSurv, rawMult, snapped, rho, book count),
  * the LUT payout cents,
  * the RTP report (step count, max mult, theoretical vs realised RTP),
  * the max-win frequency report (probability, 1-in-N hit rate, per-1M occurrences),
and, if a build exists under library/, cross-checks that the published LUT's distinct
payout cents + book counts match the config (a corroboration of the run.py
execute_all_tests book<->LUT hash verification).

Run from the math-sdk root:
    PYTHONPATH="$(pwd):games/2_7_chicken_crossing" env/bin/python games/2_7_chicken_crossing/tools/report.py
    (env NUM_SIMS / RTP_TARGET / GLOBAL_MAX_MULT are honoured, same as run.py)
"""

import csv
import os
import sys
from collections import Counter

_HERE = os.path.dirname(os.path.abspath(__file__))
_GAME_DIR = os.path.dirname(_HERE)
_ROOT = os.path.dirname(os.path.dirname(_GAME_DIR))
for p in (_ROOT, _GAME_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

import game_config as gc  # noqa: E402


def _fmt(x, w=10, d=5):
    return f"{x:>{w}.{d}f}"


def main() -> None:
    config = gc.GameConfig()
    num_sims = config.num_sims
    print("=" * 96)
    print(f"Chicken Crossing (2_7) — build report   game_id={config.game_id}")
    print(f"RTP_TARGET={gc.RTP_TARGET}   GLOBAL_MAX_MULT={gc.GLOBAL_MAX_MULT}   NUM_SIMS={num_sims}")
    print("=" * 96)

    lut_dir_candidates = [
        os.path.join(_GAME_DIR, "library", "publish_files"),
        os.path.join(_GAME_DIR, "library", "lookup_tables"),
    ]

    summary = []
    for name, p in config.mode_params.items():
        steps = p["steps"]
        counts = {int(c): n for c, n in p["payout_count"].items()}  # cents -> books
        top = steps[-1]
        top_cents = top["cents"]
        max_books = counts[top_cents]
        max_prob = max_books / num_sims
        realised = p["rtp"]

        print(f"\n### {name.upper()}  ({p['num_steps']} steps, max {top['snapped']}x)")
        print(f"{'step':>4} {'cumSurv':>10} {'rawMult':>11} {'snapped':>8} "
              f"{'rho':>9} {'q':>11} {'books':>9} {'LUTcents':>9}")
        for s in steps:
            cents = s["cents"]
            books = counts[cents]
            # q of this specific step (books are pooled across equal-payout steps).
            q_step = books / num_sims * (1.0 / len([x for x in steps if x["cents"] == cents]))
            print(f"{s['step']:>4} {_fmt(s['cumsurv'])} {_fmt(s['raw'],11)} "
                  f"{s['snapped']:>8.1f} {_fmt(s['rho'],9,5)} {_fmt(q_step,11,7)} "
                  f"{books:>9} {cents:>9}")
        loss = p["loss_count"]
        print(f"{'POP':>4} {'':>10} {'':>11} {0.0:>8.1f} {'':>9} "
              f"{loss/num_sims:>11.7f} {loss:>9} {0:>9}")

        # LUT payout cents (distinct, ascending) from config.
        lut_cents = sorted(set(list(counts.keys()) + [0]))
        print(f"LUT payout cents: {lut_cents}")

        # Max-win frequency report.
        hit_one_in = (1.0 / max_prob) if max_prob > 0 else float("inf")
        per_million = max_prob * 1_000_000
        print(f"max-win {top['snapped']}x: prob={max_prob:.3e}  hit-rate=1 in {hit_one_in:,.0f}  "
              f"expected {per_million:,.1f} per 1,000,000 sims")
        print(f"RTP: theoretical {gc.RTP_TARGET:.5f}  realised(after snap+rounding) {realised:.5f}")

        summary.append((name, p["num_steps"], top["snapped"], max_prob, hit_one_in,
                        gc.RTP_TARGET, realised, per_million))

        # Cross-check the built LUT if present.
        for d in lut_dir_candidates:
            for fn in (f"lookUpTable_{name}_0.csv", f"lookUpTable_{name}.csv"):
                fp = os.path.join(d, fn)
                if os.path.exists(fp):
                    lut_counts = Counter()
                    with open(fp) as fh:
                        for row in csv.reader(fh):
                            lut_counts[int(row[2])] += 1
                    expected = Counter(counts)
                    expected[0] = loss
                    ok = dict(lut_counts) == dict(expected)
                    print(f"LUT cross-check [{fn}]: {'OK' if ok else 'MISMATCH'} "
                          f"({sum(lut_counts.values())} books)")
                    if not ok:
                        print(f"  config={dict(sorted(expected.items()))}")
                        print(f"  lut   ={dict(sorted(lut_counts.items()))}")
                    break
            else:
                continue
            break

    print("\n" + "=" * 96)
    print("SUMMARY")
    print(f"{'mode':>10} {'steps':>6} {'maxMult':>9} {'maxWinProb':>12} "
          f"{'1-in':>14} {'RTP(th)':>8} {'RTP(real)':>10} {'maxWin/1M':>10}")
    for name, ns, mx, mp, hr, th, rl, pm in summary:
        print(f"{name:>10} {ns:>6} {mx:>9.1f} {mp:>12.3e} {hr:>14,.0f} "
              f"{th:>8.5f} {rl:>10.5f} {pm:>10.1f}")

    print("\n" + "!" * 96)
    print("WARNINGS (unsupported / non-default Stake Engine behaviour):")
    print("  1. PREDETERMINED SETTLEMENT: the book fixes the whole outcome incl. the cash-out")
    print("     step. Pressing 'Cash Out' CANNOT change the payout mid-round (do not rely on")
    print("     /bet/event to mutate the settled payout). Dynamic player cash-out stays DISABLED.")
    max_realised = max(s[6] for s in summary)
    if max_realised > 0.967 + 1e-9:
        print(f"  2. Realised RTP up to {max_realised:.5f} EXCEEDS the ACP per-mode ceiling of")
        print("     0.9670 and will FAIL the RTP validator. Set RTP_TARGET=0.965 (env or the")
        print("     constant) for a guaranteed ACP-valid build (0.967 as a target can round a")
        print("     hair over the ceiling; 0.965 leaves a safe integer-rounding margin).")
    else:
        print(f"  2. Realised RTP max {max_realised:.5f} is within the ACP 0.9670 ceiling (ACP-valid).")
    print("!" * 96)


if __name__ == "__main__":
    main()
