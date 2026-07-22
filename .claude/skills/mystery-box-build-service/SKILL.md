---
name: mystery-box-build-service
description: >-
  Run or drive the FastAPI build service (service/) that wraps the dynamic
  mystery-box generator over HTTP so a backoffice can build a box and download its
  ACP publish files. Use when starting the service, calling its endpoints (POST
  /builds vs POST /manifests, polling GET /builds/{id}, downloading the zip),
  configuring auth / S3 deploy / ephemeral builds, or debugging job/lock/persistence
  behaviour. Primary docs live in service/README.md, service/API.md,
  service/DEPLOY.md and service/BACKOFFICE_INTEGRATION.md — this skill is the
  orientation + gotchas layer over them. Complements mystery-box-manifest (author the
  manifest body) and publish-stake-game (the ACP upload, which the service does NOT do).
---

# Drive the mystery-box build service (`service/`)

A thin **FastAPI** HTTP API around `games/mystery_box_dynamic/`. A backoffice POSTs a
mystery-box **manifest**, the service builds the game and exposes the ACP publish
files as a zip (and optionally deploys them to your own S3). It is a **wrapper, not a
replacement**: every build shells out to the same `games/mystery_box_dynamic/run.py`
that `./build.sh` uses, so a service build and a manual build of the same manifest
produce **identical** files. The manual path is unchanged.

**Authoritative docs (read these for detail):** `service/README.md` (config +
overview), `service/API.md` (full route reference; live Swagger at `/docs`),
`service/DEPLOY.md`, `service/BACKOFFICE_INTEGRATION.md` (Laravel client, queued job,
DB schema). This skill orients you and lists the traps.

## Run it

```sh
make setup                                   # once — venv with fastapi + uvicorn
API_KEY=changeme ./service/run_service.sh    # http://0.0.0.0:8000
# or Docker:
docker build -f service/Dockerfile -t mysterybox-build-service .
docker run -e API_KEY=changeme -p 8000:8000 mysterybox-build-service
```

`API_KEY` is **required** and fails closed — unset ⇒ every build is rejected. Callers
send it as the `X-API-Key` header. `/healthz` is open; all `/builds` and `/manifests`
routes require the key.

## The two ways to supply a manifest

1. **Full manifest** → `POST /builds?mode=prod|dev` with a complete manifest JSON body
   (same shape as `games/mystery_box_dynamic/manifests/*.json` — see the
   **`mystery-box-manifest`** skill).
2. **Simplified box** → `POST /manifests` with just name / price / prize-rows; the
   service assembles the full manifest (auto `game_id`, per-prize `criteria`,
   `wincap`, `rtp`, `num_sims`), validates it, and returns it. Add `?build=true` to
   build in the same call. **This is the path a backoffice "create a box" form uses.**

## Async job lifecycle

```
POST /builds?mode=prod|dev   → validates synchronously (400 on bad manifest, via
                               run.py --validate), else 202 { job_id, game_id, status }
GET  /builds/{job_id}        → status: queued → running → succeeded | failed
                               (+ files[], deploy_status, s3_files[] when deployed)
GET  /builds/{job_id}/download → the publish zip, once succeeded (409 in ephemeral mode)
```

- **`mode=prod`** (default): full compressed, format-checked, **publishable** build
  from the manifest's `build` block. Refuses to clobber a game with an existing prod
  build unless `overwrite=true`.
- **`mode=dev`**: fast preview (1000 sims, uncompressed, no checks), isolated under a
  `_dev` game-id suffix — **not publishable**.

## What actually matters when operating it

- **Single-worker by design.** Job status is persisted to **SQLite**
  (`ARTIFACT_DIR/jobs.db`) via one connection + an in-process lock, so run **one**
  worker. Mount `ARTIFACT_DIR` on a volume (deploy uses `-v mbs-data:/app/service/artifacts`)
  so jobs + artifacts survive a container recreate.
- **Per-`game_id` serialization is mandatory.** Same-game builds are serialized by an
  in-process lock **and** a cross-process `fcntl.flock` on
  `service/artifacts/.locks/<id>.lock`. Two concurrent unserialized builds of the same
  `game_id` share the `games/<id>/library/` tree and **corrupt each other**, surfacing
  as a book↔LUT **"Payout hash mismatch"**. Do not bypass the lock.
- **Never call `create_books` in-process** — it spawns `multiprocessing.Process`
  workers. The service always **subprocesses `run.py`** (as `build.sh` does).
  `GAME_ID_SUFFIX` is **not** used for prod isolation (it would leak into the
  published `gameID`); the lock provides isolation instead.
- **Optional S3 deploy** (`AWS_S3_BUCKET` set): a successful **prod** build
  auto-uploads its publish files + zip to `s3://<bucket>/<S3_PREFIX><game_id>/` and
  returns savable URLs in the job status. Best-effort — a failure leaves the build
  `succeeded` with `deploy_status:"failed"` (never loses the artifact); no bucket ⇒
  `"skipped"`. **This is delivery to your bucket, NOT Stake RGS publishing** (still
  the ACP dashboard — see `publish-stake-game`).
- **Ephemeral builds** (`EPHEMERAL_BUILDS`, default **on** when a bucket is set):
  after a successful upload the local build + job zip are **deleted** (S3 is the
  source of truth). Then `/download` **409s** and `already_built` checks S3
  (`HeadObject`) instead of local disk. A failed upload deletes nothing.
- **Config knobs** (env): `MAX_CONCURRENT_BUILDS` (default 2, CPU-heavy — keep low),
  `BUILD_TIMEOUT_SECONDS` (1800), `ARTIFACT_DIR`, `PYTHON_BIN`, plus the `S3_*` /
  `AWS_*` set. Full table in `service/README.md`.

## Gotchas

- **Fails closed on missing `API_KEY`** — set it or every build 401/rejects.
- **Verify S3 wiring** with stubbed boto3 (`service/s3.py::_client`) or LocalStack via `S3_ENDPOINT_URL` before trusting deploy URLs.
- The service **does not publish to Stake** — it delivers to your bucket / a zip; the ACP dashboard upload is a separate, human step.

## Related skills

- **`mystery-box-manifest`** — author/validate the manifest body the service consumes (`cost_model: unit` for ACP validity, integrality rule).
- **`publish-stake-game`** — take the resulting `publish_files` to the ACP dashboard and set the bet level.
