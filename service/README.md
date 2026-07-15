# Mystery-box Build Service

A thin HTTP API around the dynamic mystery-box generator
(`games/mystery_box_dynamic/`). Your backoffice POSTs a mystery-box **manifest**, the
service builds the game, and you download the ACP publish files as a zip.

It is a **wrapper, not a replacement**: every build shells out to the same
`games/mystery_box_dynamic/run.py` a manual `./build.sh` uses, so a service build and a
manual build of the same manifest produce identical files. The manual workflow
(`./build.sh dev|prod`, `make build_all_dynamic`) is unchanged.

## Run it

```sh
make setup                       # once — creates ./env with fastapi + uvicorn
API_KEY=changeme ./service/run_service.sh          # http://0.0.0.0:8000
# or
docker build -f service/Dockerfile -t mysterybox-build-service .
docker run -e API_KEY=changeme -p 8000:8000 mysterybox-build-service
```

### Configuration (env vars)

| Var | Default | Purpose |
|-----|---------|---------|
| `API_KEY` | *(required)* | Shared secret; sent by the caller as `X-API-Key`. Unset ⇒ all builds rejected (fails closed). |
| `MAX_CONCURRENT_BUILDS` | `2` | Builds running at once (CPU-heavy — keep low). |
| `BUILD_TIMEOUT_SECONDS` | `1800` | Hard cap on one build's wall-clock. |
| `ARTIFACT_DIR` | `service/artifacts/` | Where per-job snapshots + zips are written. |
| `PYTHON_BIN` | repo `env/bin/python` | The venv python that runs the build. |
| `AWS_S3_BUCKET` | *(unset)* | Set to auto-upload each **prod** build to your own bucket (see S3 deploy below). Unset ⇒ upload skipped. |
| `S3_PREFIX` | `""` | Optional key prefix under the bucket, e.g. `mystery-box/`. |
| `AWS_REGION` / `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | boto3 default chain | Creds; if omitted, boto3 uses env/shared-config/IAM role. |
| `S3_ENDPOINT_URL` | *(unset)* | Only for S3-compatible stores (MinIO/LocalStack). |
| `S3_PRESIGN_EXPIRY` | `3600` | Seconds a presigned download URL stays valid; `0` disables presigning. |

## API

Full reference: **[`service/API.md`](API.md)**. Interactive docs on the running service:
Swagger UI at `/docs`, ReDoc at `/redoc`, OpenAPI spec at `/openapi.json`.
Laravel backoffice integration (API client, queued job, DB schema, error handling):
**[`BACKOFFICE_INTEGRATION.md`](BACKOFFICE_INTEGRATION.md)**.

All `/builds` and `/manifests` routes require the `X-API-Key` header. `/healthz` is open.

### Two ways to supply the manifest

1. **Full manifest** → `POST /builds` with a complete manifest JSON body (same shape as
   `games/mystery_box_dynamic/manifests/*.json`).
2. **Simplified box** → `POST /manifests` with just name/price/prize-rows; the service
   assembles the full manifest (auto `game_id`, `criteria`, `wincap`, `rtp`, `num_sims`),
   validates it, and returns it — add `?build=true` to build in the same call. This is the
   path a backoffice "create a mystery box" form should use. See [`API.md`](API.md).

### `POST /builds?mode=prod|dev`

Body = the manifest JSON (same shape as `games/mystery_box_dynamic/manifests/*.json`).
The manifest is validated synchronously (no sims); an authoring error returns `400` with
the reason. On success a job is queued and the endpoint returns `202`:

```json
{ "job_id": "a1b2…", "game_id": "3_2_cash_paradise_unit", "mode": "prod", "status": "queued" }
```

- `mode=prod` (default): full build from the manifest's `build` block (compressed,
  format-checked) — **publishable**. Refuses to clobber a game that already has a prod
  build unless `overwrite=true`.
- `mode=dev`: fast preview (1000 sims, uncompressed, no format checks), isolated under a
  `_dev` game-id suffix — **not publishable**.

### `GET /builds/{job_id}`

```json
{ "id": "a1b2…", "game_id": "3_2_cash_paradise_unit", "mode": "prod",
  "status": "succeeded", "publishable": true, "created_at": "…", "finished_at": "…",
  "error": null, "files": ["index.json", "books_base.jsonl.zst", "lookUpTable_base_0.csv", "config.json"],
  "local_available": false,
  "deploy_status": "uploaded",
  "s3_prefix": "s3://juice-cdn/math-sdk/3_2_cash_paradise_unit/",
  "s3_files": [
    { "name": "index.json", "key": "math-sdk/3_2_cash_paradise_unit/index.json",
      "uri": "s3://juice-cdn/math-sdk/3_2_cash_paradise_unit/index.json",
      "url": "https://cdn.example.com/math-sdk/3_2_cash_paradise_unit/index.json" }
  ],
  "s3_zip": { "name": "publish.zip", "url": "https://cdn.example.com/…/publish.zip", "…": "…" } }
```

`status`: `queued → running → succeeded | failed`. On `failed`, `error` carries the
one-line build reason. **The backoffice saves each `s3_files[].url`** (stable, non-expiring)
— that is the "file path" to store against the box.

### `GET /builds/{job_id}/download`

Convenience **local** download of `publish.zip`, for local mode (no S3) or dev. In ephemeral
mode the local zip is deleted after upload, so this returns `409` — fetch the S3 paths from
`GET /builds/{job_id}` (`s3_files` / `s3_zip`) instead.

## Ephemeral builds (stateless worker)

When `AWS_S3_BUCKET` is set, **`EPHEMERAL_BUILDS` defaults on**: a successful prod build
uploads to S3 and then **deletes the local build** (`games/<id>/` + the job's zip). S3 is the
source of truth; the API returns stable `url`s the backoffice stores. Safety: a failed upload
deletes nothing (`deploy_status: "failed"`, local retained, retry with `overwrite=true`). Set
`EPHEMERAL_BUILDS=false` to also keep local copies. The overwrite guard checks S3 in this mode.

Presigned URLs (`s3_files[].presigned_url`, when `S3_PRESIGN_EXPIRY > 0`) are a bonus for
fetching a *private* object directly — but they expire, so don't store them; store `url`.

## Backoffice integration (curl)

```sh
KEY=changeme
BASE=http://localhost:8000

# 1) kick off a prod build
JOB=$(curl -s -X POST "$BASE/builds?mode=prod" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  --data @games/mystery_box_dynamic/manifests/cash_paradise_unit.json \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["job_id"])')

# 2) poll until it finishes
until [ "$(curl -s -H "X-API-Key: $KEY" "$BASE/builds/$JOB" \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["status"])')" != "running" ]; do sleep 3; done

# 3) read the S3 file paths to save (ephemeral mode) …
curl -s -H "X-API-Key: $KEY" "$BASE/builds/$JOB" \
  | python3 -c 'import sys,json;[print(f["url"]) for f in json.load(sys.stdin)["s3_files"]]'
# … or download the local zip (local mode only)
curl -s -H "X-API-Key: $KEY" "$BASE/builds/$JOB/download" -o publish.zip
```

Then upload the three files from `publish.zip` via the ACP dashboard (see the
`publish-stake-game` skill and `games/3_2_mystery_box_cash_paradise/docs/PRODUCTION.md`).
Set the box price as the ACP **bet level** (the `unit` cost model bakes the RTP into 1×
multipliers).

## S3 deploy (optional — your own bucket)

Set `AWS_S3_BUCKET` and a **successful prod build auto-uploads** its publish files to
`s3://<bucket>/<S3_PREFIX><game_id>/`, so your backoffice can pull them from S3 instead of
the zip endpoint. Dev builds never upload.

> This uploads to **your** bucket for storage/delivery. It does **not** publish the game to
> the Stake Engine RGS — that is still the ACP dashboard.

The upload is **best-effort and decoupled from the build**: if S3 fails (bad creds, wrong
bucket), the job stays `succeeded` and the zip is still downloadable — only the deploy
sub-state records the failure. The job status carries:

```json
{ "status": "succeeded",
  "deploy_status": "uploaded",              // "skipped" (no bucket / dev) | "uploaded" | "failed"
  "deploy_error": null,
  "s3_prefix": "s3://my-bucket/mystery-box/3_2_cash_paradise_unit/",
  "s3_uris": ["s3://my-bucket/mystery-box/3_2_cash_paradise_unit/index.json", "..."],
  "s3_urls": { "index.json": "https://…presigned…", "...": "..." } }
```

`s3_urls` are presigned GET URLs (valid `S3_PRESIGN_EXPIRY` seconds) so the backoffice can
download straight from S3 without AWS credentials. To **retry** a failed deploy, re-run the
build with `overwrite=true`.

## Notes / limits

- **Single instance.** Job records are in memory (artifacts persist on disk under
  `ARTIFACT_DIR`); a restart loses status history but not finished zips. Move to
  SQLite/Redis before running multiple replicas.
- **`provider_number`** in the manifest must be your real ACP-assigned studio id before
  the final prod build you upload (the samples ship a placeholder `3`).
- For an ACP-valid build use `cost_model: "unit"` in the manifest — `box_cost` builds
  fail the ACP "cost must be 1.0" validator.
