---
name: publish-stake-game
description: >-
  Build and publish a math-sdk game to the Stake Engine RGS/ACP. Use when
  preparing a game for production, generating publish_files, fixing ACP upload
  validation errors (e.g. "Base Mode Cost must be 1.0x", "Bet Level Validator: no
  valid levels"), running the run.py build pipeline for release, or verifying a
  build with execute_all_tests / rgs_verification. Covers reel-slot and
  direct-probability (mystery box) games.
---

# Publish a game to Stake Engine (RGS/ACP)

The RGS is a certified **replay** system: it serves pre-generated, hash-verified
books + lookup tables. A game's odds and payouts are **frozen at publish time** —
there is no live/API-driven odds swapping, and the published frontend artifact's CSP
blocks external fetches. "Dynamic" prize data can only be **build-time** (regenerate
→ re-verify → re-upload), never runtime.

Publishing = produce a compressed, format-checked build, then upload three files
from `games/<id>/library/publish_files/` via the **ACP dashboard**:
`index.json`, `books_<mode>.jsonl.zst`, `lookUpTable_<mode>_0.csv`.
(`uploads/aws_upload.py` is an alternate S3 path but ships with an empty
`BUCKET_NAME`; the ACP is the real channel.)

## Step 1 — Set production values in the game's `run.py`

| Setting | Production | Why |
|---|---|---|
| `compression` | `True` | `verify_books_and_payout_mults`/`execute_all_tests` reject non-`.jsonl.zst` books. A readable-JSON build cannot be format-checked or published. |
| `num_sims` | integer where **every criteria quota × num_sims is a whole number** | With the optimiser off, published odds == `round(num_sims × quota)`. For Cash Paradise, 100000 makes all quotas integral. |
| `run_format_checks` | `True` | Runs `execute_all_tests(config)` — the pre-publish gate. |

`run_analysis` stays `False` for direct-probability games (the slot analytics in
`utils/game_analytics/` assume base+freespin gametypes and raise on a single
gametype).

## Step 2 — Build

```sh
source env/bin/activate
rm -rf games/<id>/library          # optional: clean slate
make run GAME=<id>                  # create_books → generate_configs → execute_all_tests
```

Pass: `[FAST PATH] base: SHA-256 OK, payout hash OK, entries=<num_sims>`, no
`AssertionError`.

## Step 3 — The math rules the ACP enforces (the SDK does NOT)

These are not caught locally — they fail at ACP upload. Check them before shipping:

1. **Base/default bet mode cost multiplier must be exactly `1.0`.** RTP is computed
   as `EV ÷ cost` (`utils/analysis/distribution_functions.py::calculate_rtp`), so you
   **cannot** just flip cost to 1.0 — that turns an 85% game into ~420%. Payouts must
   be re-expressed as multipliers of a 1× bet; the real purchase price becomes the
   operator-set **bet level**, not the mode cost.
   - The `mystery_box` and `3_2_mystery_box_cash_paradise` games set
     `cost = box_cost` (e.g. 4.98 / 32.94) and therefore **fail this validator as
     authored**. The fix is a game-math change (see "Fixing a mystery-box game" below).
2. **Lookup-table payout format** (`utils/rgs_verification.py::verify_lookup_format`):
   each payout is an integer of "cents" (`payout×100`), `0` or `≥10`, and a multiple
   of `10` — i.e. non-zero payouts must be multiples of `0.1×`. Anything below `0.1×`
   must resolve to `0`.
3. **Bet levels** live in the **ACP dashboard** (bet-level template; Stake US needs a
   `us_` prefix), NOT in math-sdk. A missing template is "Bet Level Validator: no valid
   levels". The SDK only emits `minDenomination`/`betDenomination` from
   `config.min_denomination`.

## Step 4 — Verify

```sh
cd games/<id>/library
ls publish_files/                                            # index.json + books_*.jsonl.zst + lookUpTable_*_0.csv
wc -l publish_files/lookUpTable_<mode>_0.csv                 # == num_sims
python3 -c "import json;m=json.load(open('configs/config.json'))['bookShelfConfig'][0];print(m['cost'], m['bookLength'], m['rtp'])"
awk -F, '{print $3}' publish_files/lookUpTable_<mode>_0.csv | sort -n | uniq -c   # payout histogram == round(num_sims×prob)
```

`config.json` carries sha256 hashes of the published files; `execute_all_tests`
cross-checks book↔LUT payouts (fast path via `configs/books_<mode>.verification.json`).
Independent re-run: `python -m utils.rgs_verification -g <id>`.

Confirm base mode `cost: 1.0` in both `config.json` and `publish_files/index.json`.

## Step 5 — Upload

Upload the three `publish_files` in the ACP for `<id>`, mode `<mode>`. Then apply a
**bet-level template** in the ACP and set the purchase price as the bet level (clears
the Bet Level validator). If the config's declared `rtp` differs from the LUT-computed
RTP, the (optional) S3 uploader's interactive RTP check prompts for an override.

## Fixing a mystery-box game for the ACP (cost 1.0)

The box price can't be the mode cost. Re-express `payout = value ÷ box_cost` rounded to
the `0.1×` grid (sub-`0.1×` prizes → 0), set `BetMode(cost=1.0, ...)`, derive the
effective `wincap` as the max payout multiplier, and write the **achieved** EV as the
config `rtp`. The box's real price becomes the ACP bet level. Example worked build +
consequences (e.g. max-win rescales, small prizes zero out) are in
`games/3_2_mystery_box_cash_paradise/docs/PRODUCTION.md`.

## Direct-probability vs reel-slot games

Read the game's `readme.txt` + `run.py` first. Direct-probability games (mystery box)
draw one prize from a fixed odds table in `game_config.py`, disable
`run_optimization`, and have no board/reels/freespin — RTP comes from the authored
odds, not the Rust optimiser. Reel-slot games (the `template`, historically the
`0_0_*` samples) use reels, may run optimization, and `cost=1.0` is already the norm.
