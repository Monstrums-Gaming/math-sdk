# Mystery-box Build Service — API Reference

HTTP API to build a Stake Engine mystery-box game from a JSON manifest and download the ACP
publish files. Backoffice-facing.

- **Interactive docs** (auto-generated, always in sync with the running version):
  - Swagger UI: `GET /docs`
  - ReDoc: `GET /redoc`
  - OpenAPI spec: `GET /openapi.json`
- **Overview / deploy / env config:** see `service/README.md`.
- **Manifest format:** see `games/mystery_box_dynamic/README.md` and the samples in
  `games/mystery_box_dynamic/manifests/`.

---

## Base URL & versioning

```
http://<host>:<port>
```
Default `0.0.0.0:8000` (override with `HOST`/`PORT`). No path prefix; API version is `1.0.0`
(reported in `/openapi.json`).

## Authentication

Every `/builds*` route requires a shared secret in a header. `/healthz`, `/docs`, `/redoc`
and `/openapi.json` are open.

```
X-API-Key: <API_KEY>
```

`API_KEY` is set via env / `.env` (see `service/README.md`). Failure modes:

| Condition | Status | Body |
|-----------|--------|------|
| Missing or wrong key | `401` | `{"detail":"Invalid or missing X-API-Key."}` |
| Server has no `API_KEY` configured | `503` | `{"detail":"Server misconfigured: API_KEY is not set."}` (fails closed) |

---

## Endpoints

### `GET /healthz`

Liveness probe. No auth.

**200**
```json
{ "status": "ok" }
```

---

### `POST /manifests`

Assemble a **full manifest** from **simplified box inputs** (name, price, prize rows), so the
backoffice never hand-writes manifest JSON. The service derives `game_id`, per-prize
`criteria`, `wincap`, `rtp`, and a fixed `num_sims`, then validates the result. Optionally
builds it in the same call.

**Query parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `build` | bool | `false` | Also enqueue a build of the assembled manifest. |
| `mode` | `prod` \| `dev` | `prod` | Build mode when `build=true`. |
| `overwrite` | bool | `false` | Allow rebuilding an existing prod `game_id` when `build=true`. |

**Request body** — `BoxSpec`:

```jsonc
{
  "game_name": "Lucky Dip",
  "provider_number": 3,
  "provider_name": "monstrum",
  "box_cost": 2.00,
  "cost_model": "unit",              // default "unit" (ACP-valid); or "box_cost"
  "prizes": [                         // 'payout' = catalog multiplier (value at box price)
    { "name": "Nothing",      "payout": 0,   "prob": 0.65 },
    { "name": "$1 Prize",     "payout": 1,   "prob": 0.28 },
    { "name": "$200 Jackpot", "payout": 200, "prob": 0.005 }
  ]
  // optional: game_id, working_name, win_type, num_sims, build{}
}
```

**What the service derives** (you don't send these):
- `game_id` → `<provider_number>_<slug(game_name)>` unless you pass one.
- `criteria` → highest-paying prize = `"wincap"`; any prize that snaps to 0 on the RGS
  `0.1×` grid = `"0"`; every other distinct payout gets its own bucket.
- `wincap` = max catalog payout; `rtp` = expected payout ÷ cost (must be `< 1.0`).
- `num_sims` = `MANIFEST_NUM_SIMS` (default `100000`) — so every `prob` must be a multiple
  of `1/100000`.

**Responses**

| Status | When | Body |
|--------|------|------|
| `200` | Assembled + validated | `ManifestResult` (below) |
| `400` | Bad box spec (RTP ≥ 1.0, no paying prize, …) or the assembled manifest failed SDK validation (probs ≠ 1.0, non-integral quota) | `{"detail":"…"}` |
| `409` | `build=true`, prod `game_id` already built, no `overwrite` | `{"detail":"…"}` |

**`ManifestResult` (200)**
```json
{
  "manifest": { "...": "the full manifest you could also POST to /builds" },
  "game_id": "3_lucky_dip",
  "num_sims": 100000,
  "rtp": 0.89,
  "wincap": 200.0,
  "job": { "job_id": "…", "game_id": "3_lucky_dip", "mode": "prod", "status": "queued" }
}
```
`job` is present only when `build=true`. Otherwise take `manifest` and `POST /builds` it
later (e.g. after the admin reviews it).

---

### `POST /builds`

Validate a manifest and enqueue a build. Returns immediately (`202`) with a `job_id`; the
build runs asynchronously — poll `GET /builds/{job_id}`.

**Query parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `mode` | `prod` \| `dev` | `prod` | `prod` = full build from the manifest's `build` block (compressed, format-checked, **publishable**, may auto-deploy to S3). `dev` = fast preview (1000 sims, uncompressed, no checks, `_dev` game-id suffix, **not** publishable, never deploys). |
| `overwrite` | bool | `false` | Prod only. Allow rebuilding a `game_id` that already has a prod build (otherwise `409`). Also the way to **retry** a failed S3 deploy. |

**Request body** — the manifest JSON (same shape as
`games/mystery_box_dynamic/manifests/*.json`). Validated synchronously (no sims) before a
job is created.

```jsonc
{
  "game_id": "3_2_cash_paradise_unit",
  "provider_number": 3,
  "provider_name": "monstrum",
  "game_name": "Cash Paradise",
  "box_cost": 4.98,
  "rtp": 0.85,
  "cost_model": "unit",
  "wincap": 1000,
  "build": { "num_sims": 100000, "compression": true, "run_format_checks": true },
  "prizes": {
    "P1": { "name": "$0.01 Voucher", "payout": 0.01, "prob": 0.302, "criteria": "0" },
    "P9": { "name": "$1000 Voucher", "payout": 1000, "prob": 0.002, "criteria": "wincap" }
  }
}
```

**Responses**

| Status | When | Body |
|--------|------|------|
| `202 Accepted` | Manifest valid, job queued | `BuildAccepted` (below) |
| `400 Bad Request` | Missing `game_id`, or manifest fails validation (probs ≠ 1.0, non-integral `num_sims × prob`, RGS-grid violation, etc.) | `{"detail":"Invalid manifest: <reason>"}` |
| `401` / `503` | Auth (see above) | — |
| `409 Conflict` | `mode=prod`, `game_id` already built, `overwrite` not set | `{"detail":"game_id '…' already has a prod build; pass overwrite=true to rebuild."}` |

**`BuildAccepted` (202)**
```json
{ "job_id": "a1b2c3d4e5f6…", "game_id": "3_2_cash_paradise_unit", "mode": "prod", "status": "queued" }
```

---

### `GET /builds/{job_id}`

Job status. Poll until `status` is `succeeded` or `failed`.

**Responses**

| Status | Body |
|--------|------|
| `200` | `JobStatus` (below) |
| `404` | `{"detail":"unknown job_id."}` |

**`JobStatus`**

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Job id. |
| `game_id` | string | Manifest `game_id` (the published `gameID` for a prod build). |
| `mode` | string | `prod` \| `dev`. |
| `status` | string | `queued` → `running` → `succeeded` \| `failed`. |
| `publishable` | bool | True only for prod builds (format-checked, compressed). |
| `created_at` / `finished_at` | ISO-8601 string / null | Timestamps (UTC). |
| `error` | string \| null | One-line build failure reason when `status=failed`. |
| `files` | string[] | Publish file names. |
| `local_available` | bool | Whether the local zip still exists. `false` after ephemeral cleanup (files are in S3). |
| `deploy_status` | string | S3 deploy sub-state: `skipped` (no bucket / dev) \| `uploaded` \| `failed`. Independent of `status`. |
| `deploy_error` | string \| null | One-line S3 failure reason when `deploy_status=failed`. |
| `s3_prefix` | string \| null | `s3://<bucket>/<prefix>/` the files were uploaded under. |
| `s3_files` | object[] | **The paths the backoffice saves.** Each: `{name, key, uri, url[, presigned_url]}` — `url` is stable (CDN / S3 https). |
| `s3_zip` | object \| null | Same shape, for the `publish.zip`. |
| `events_file` | object \| null | Readable events sample (`books_events.json`) descriptor `{name, key, uri, url[, presigned_url]}` when uploaded to S3; `null` in local mode (fetch via `GET /builds/{id}/events`) or when disabled (`SAMPLE_EVENTS=0`). A **dev aid**, delivered separately from the ACP set. |

Each `s3_files` entry: `name` (filename), `key` (S3 object key), `uri` (`s3://…`), `url`
(**stable, savable** — from `S3_PUBLIC_BASE_URL` or the S3 https URL), and `presigned_url`
(only if `S3_PRESIGN_EXPIRY > 0`; **expires**, so don't store it).

**Succeeded, ephemeral S3 deploy** (local deleted; save the `url`s)
```json
{
  "id": "a1b2c3…", "game_id": "3_2_cash_paradise_unit", "mode": "prod",
  "status": "succeeded", "publishable": true, "local_available": false,
  "error": null,
  "files": ["books_base.jsonl.zst", "index.json", "lookUpTable_base_0.csv", "config.json"],
  "deploy_status": "uploaded",
  "s3_prefix": "s3://juice-cdn/math-sdk/3_2_cash_paradise_unit/",
  "s3_files": [
    { "name": "index.json",
      "key": "math-sdk/3_2_cash_paradise_unit/index.json",
      "uri": "s3://juice-cdn/math-sdk/3_2_cash_paradise_unit/index.json",
      "url": "https://cdn.example.com/math-sdk/3_2_cash_paradise_unit/index.json" }
  ],
  "s3_zip": { "name": "publish.zip", "key": "…/publish.zip", "uri": "s3://…", "url": "https://…/publish.zip" }
}
```

**Failed build**
```json
{ "id": "…", "status": "failed", "error": "num_sims (100000) x quota for criteria '0' … is not an integer",
  "files": [], "deploy_status": "skipped" }
```

**Succeeded build, failed deploy** (local retained — `local_available: true`, downloadable)
```json
{ "id": "…", "status": "succeeded", "local_available": true, "deploy_status": "failed",
  "deploy_error": "ClientError: An error occurred (AccessDenied) …" }
```

---

### `GET /builds/{job_id}/download`

**Local mode only.** Streams `publish.zip` (`application/zip`) when the job succeeded and
`local_available` is `true`. In ephemeral (S3) mode the local zip is deleted after upload,
so this returns `409` — read `s3_files` / `s3_zip` from `GET /builds/{job_id}` instead. The
zip contains `index.json`, `books_base.jsonl.zst` (prod only), `lookUpTable_base_0.csv`,
`config.json`. It does **not** contain `books_events.json` (that's a separate artifact —
see below).

---

### `GET /builds/{job_id}/events`

The **readable events sample** (`books_events.json`) — a coverage-first slice (~100 rounds,
one per distinct prize/`criteria`) for frontend/game devs to inspect the per-round event
stream. Delivered separately from the ACP publish set (never inside `publish.zip`).

- **Local mode:** streams the JSON file (`application/json`, `200`).
- **Ephemeral (S3) mode:** `307` redirect to the sample's S3 URL (the local copy is deleted
  after upload; the stable descriptor is also in `events_file` on `GET /builds/{job_id}`).

**Responses**

| Status | Meaning |
|--------|---------|
| `200` | Readable events JSON (local mode). |
| `307` | Redirect to the S3 URL (ephemeral mode). |
| `404` | Unknown `job_id`, or the build produced no sample (`SAMPLE_EVENTS=0`). |
| `409` | Job not `succeeded` yet. |

**Responses**

| Status | When |
|--------|------|
| `200` | Local mode, job `succeeded`; streams the zip. |
| `404` | Unknown `job_id`. |
| `409` | Not `succeeded` yet, or ephemeral mode (local deleted — use `s3_files`/`s3_zip`). |

---

## Job lifecycle

```
POST /builds ─202─> queued ─> running ─> succeeded ─> (prod + bucket) upload ─> uploaded ─> [ephemeral] delete local
                                     └─> failed                        (else)     skipped         (keep local)
                                                                       (err)      failed  ─────────(keep local)
```

- **Build status** (`status`) and **deploy status** (`deploy_status`) are independent: an S3
  upload failure leaves `status=succeeded`, `local_available=true` (the zip is still
  downloadable), and only sets `deploy_status=failed`.
- **Ephemeral mode** (`EPHEMERAL_BUILDS`, default on when a bucket is set): a successful
  upload deletes the local build; the backoffice saves `s3_files[].url`. A failed upload
  keeps everything local.
- Retry a failed deploy by re-POSTing the same manifest with `overwrite=true`.

## Error format

All errors use FastAPI's standard shape:
```json
{ "detail": "<human-readable reason>" }
```
Validation errors from the request layer (e.g. an unparseable body or bad `mode` value) return
`422` with FastAPI's structured `detail` array; manifest-content errors return `400` with a
single-string `detail`.

---

## End-to-end example (curl)

```sh
KEY=your-api-key
BASE=http://localhost:8000

# 1) enqueue a prod build
JOB=$(curl -s -X POST "$BASE/builds?mode=prod" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  --data @games/mystery_box_dynamic/manifests/cash_paradise_unit.json \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["job_id"])')

# 2) poll until it settles
until S=$(curl -s -H "X-API-Key: $KEY" "$BASE/builds/$JOB" \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["status"])'); [ "$S" = succeeded ] || [ "$S" = failed ]; do
  sleep 3
done
echo "status=$S"

# 3a) EPHEMERAL (S3) mode — save the stable file paths
curl -s -H "X-API-Key: $KEY" "$BASE/builds/$JOB" \
  | python3 -c 'import sys,json;[print(f["url"]) for f in json.load(sys.stdin)["s3_files"]]'

# 3b) LOCAL mode — download the zip
curl -s -H "X-API-Key: $KEY" "$BASE/builds/$JOB/download" -o publish.zip
```

Then upload the three files via the Stake **ACP dashboard** (the only way to make the game
live) — from the saved S3 URLs (ephemeral mode) or from `publish.zip` (local mode). See
`service/README.md`.
