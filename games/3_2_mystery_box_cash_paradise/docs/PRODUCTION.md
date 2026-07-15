# Cash Paradise (3_2) — Production Runbook

How to produce and verify a publishable RGS build for **Cash Paradise**, and hand
it to the Stake Engine ACP.

Cash Paradise is a direct-probability "mystery box" game — one box open reveals one
cash-voucher prize from a fixed odds table in `game_config.py`. There is **no reel
board, no free spins, and no Rust optimiser** (`game_optimization.py` is a disabled
stub). RTP is set entirely by the authored odds and the box cost, so a production
build is just: run sims → generate configs → format-check → publish.

---

## TL;DR

```sh
source env/bin/activate                                   # from repo root
rm -rf games/3_2_mystery_box_cash_paradise/library        # clean slate (optional)
make run GAME=3_2_mystery_box_cash_paradise               # build + verify
```

Then upload the 3 files in `library/publish_files/` to the Stake Engine ACP.

---

## 1. Prerequisites

- Python ≥ 3.12 and the project venv. If you haven't set it up:
  ```sh
  make setup            # creates ./env, installs requirements + editable package
  source env/bin/activate
  ```
- No Rust/Cargo needed — the optimiser is off for this game.
- No AWS credentials needed for a **build** (only for the optional S3 upload path,
  see §6).

## 2. Production settings in `run.py`

`games/3_2_mystery_box_cash_paradise/run.py` must hold these **production** values
(as opposed to smoke-test values):

| Setting | Production | Smoke test | Why |
|---|---|---|---|
| `compression` | `True` | `False` | RGS requires compressed `books_base.jsonl.zst`; format checks reject readable JSON. |
| `num_sims` | `int(100000)` | e.g. `int(50)` | At 100k every quota is an exact integer book count, so published odds match the table exactly. |
| `run_conditions["run_format_checks"]` | `True` | `False` | Runs `execute_all_tests` — the pre-publish RGS validation gate. |

`run_analysis` stays `False` — the slot analytics assume a base+freespin game and
raise on this single-gametype game.

### The 100k quota constraint

The smallest prize probability is `0.00200` (CP9). `num_sims` must make every
`num_sims × prob` an exact integer. 100,000 gives:

```
CP1 0.302 → 30200    CP4 0.05 → 5000    CP7 0.01  → 1000
CP2 0.28  → 28000    CP5 0.05 → 5000    CP8 0.006 → 600
CP3 0.25  → 25000    CP6 0.05 → 5000    CP9 0.002 → 200
```

Use only multiples of 500 for `num_sims` if you ever change it; anything else
distorts the published odds.

## 3. Build

```sh
source env/bin/activate

# Optional but recommended: remove any prior/smoke artifacts for a clean tree.
rm -rf games/3_2_mystery_box_cash_paradise/library

make run GAME=3_2_mystery_box_cash_paradise
# equivalent to: python games/3_2_mystery_box_cash_paradise/run.py
```

This runs, in order: `create_books` (100k, compressed) → `generate_configs`
(writes `config.json`, `index.json`, FE config, sidecars) → `execute_all_tests`
(format checks).

**Expected tail of the output:**

```
Thread 0 finished with 0.86x RTP. ...
Saving books / force files / LUTs for 3_2_mystery_box_cash_paradise in base
Wrote verification file: .../configs/books_base.verification.json
[FAST PATH] Using verification sidecar for base
[FAST PATH] base: SHA-256 OK, payout hash OK, entries=100000
Compression is enabled, skipping formatting.
```

The per-thread RTP printouts (~0.83–0.86) are per-batch sample noise; the true
authored RTP is **84.90%**. Any `AssertionError` means the build failed — do not
publish.

## 4. Verify the build

```sh
cd games/3_2_mystery_box_cash_paradise/library

# a) The 3 required publish files exist and are compressed
ls -la publish_files/
#   index.json, books_base.jsonl.zst, lookUpTable_base_0.csv

# b) Lookup table has one row per sim
wc -l publish_files/lookUpTable_base_0.csv          # 100000

# c) Config declares 100k and its hashes match the sidecar
python3 -c "import json;m=json.load(open('configs/config.json'))['bookShelfConfig'][0];print(m['bookLength'], m['booksFile']['sha256'])"
cat configs/books_base.verification.json            # num_entries 100000, same file_hash

# d) LUT file hash matches config
shasum -a 256 publish_files/lookUpTable_base_0.csv   # == config tables[0].sha256

# e) Odds spot-check — payout(cents) → count must match the authored table
awk -F, '{print $3}' publish_files/lookUpTable_base_0.csv | sort -n | uniq -c
#   30200 0 | 28000 10 | 25000 100 | 5000 200 | 5000 500 | 5000 1000 | 1000 5000 | 600 10000 | 200 100000
```

Optional independent re-run of the format checks:

```sh
# from repo root, venv active
python -m utils.rgs_verification -g 3_2_mystery_box_cash_paradise
```

## 5. Publish (Stake Engine ACP — recommended)

Upload these three files from `library/publish_files/` in the game's ACP dashboard:

- `index.json`
- `books_base.jsonl.zst`
- `lookUpTable_base_0.csv`

These are the only files the RGS requires for a single-mode game.

## 6. Publish (built-in S3 uploader — alternate, not currently wired)

The repo ships `uploads/aws_upload.py`, but the ACP is the canonical path and the
S3 route needs setup first:

1. Set `BUCKET_NAME` in `uploads/aws_constants.py` (currently `""`).
2. Put valid `ACCESS_KEY` / `SECRET_KEY` in `uploads/.env`.
3. Add an `upload_data` stage to this game's `run.py` (it has none today), e.g.:
   ```python
   from uploads.aws_upload import upload_to_aws
   ...
   if run_conditions.get("upload_data"):
       upload_items = {"books": True, "lookup_tables": True,
                       "force_files": True, "config_files": True}
       upload_to_aws(gamestate, ["base"], upload_items)
   ```

Heads-up: `upload_to_aws` runs an **interactive** RTP check that compares the LUT
RTP (~0.849) against `config.json` `rtp` (0.85) and prompts `Upload anyway? (y/n)`.
This is expected — the true RTP is 84.90% while `self.rtp` is set to 0.85. It also
re-verifies file SHA-256/length against `config.json` before pushing.

## 7. What "production" changes vs a smoke test

To go back to a fast local smoke test, set in `run.py`: `compression = False`,
`num_sims = int(50)` (or any small multiple of 500 to keep odds exact),
`run_format_checks = False`. Smoke builds emit a readable `books_base.json` and
**cannot** be published — always rebuild with the production settings in §2 before
handing anything to the ACP.

## Reference

- Prize table / odds / RTP derivation: `../readme.txt` and `../game_config.py`
- RGS file-format spec: `docs/rgs_docs/data_format.md` (repo root)
- Upload notes: `docs/math_docs/uploads_section/upload_info.md` (repo root)
