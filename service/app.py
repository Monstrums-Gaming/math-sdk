"""Mystery-box build service — FastAPI app.

Endpoints (all /builds routes require the X-API-Key header):
  POST /builds?mode=prod|dev   body = manifest JSON -> validate, enqueue, 202 {job_id}
  GET  /builds/{job_id}        -> job status
  GET  /builds/{job_id}/download -> publish.zip (200 when succeeded)
  GET  /healthz                -> liveness (open)

A prod build produces the 3 ACP files (index.json, books_base.jsonl.zst,
lookUpTable_base_0.csv) plus config.json, zipped for download. A dev build is a fast,
non-publishable preview (1000 sims, uncompressed, no format checks).
"""

from pathlib import Path

from fastapi import Body, Depends, FastAPI, HTTPException, Query, status
from fastapi.responses import FileResponse, RedirectResponse

from service import builder, manifest_builder, s3
from service.auth import require_api_key
from service.config import settings
from service.jobs import registry
from service.schemas import BoxSpec, BuildAccepted, JobStatus, ManifestResult

DESCRIPTION = """\
Build Stake Engine **mystery-box** games from a JSON manifest and download the ACP publish
files (`index.json`, `books_base.jsonl.zst`, `lookUpTable_base_0.csv`, `config.json`).

**Auth:** every `/builds*` route requires the `X-API-Key` header. `/healthz` is open.

**Flow:** `POST /builds` validates the manifest and returns `202` with a `job_id`; poll
`GET /builds/{job_id}` until `succeeded`, then `GET /builds/{job_id}/download`.

Full reference: `service/API.md`. Manifest format: `games/mystery_box_dynamic/README.md`.
"""

TAGS = [
    {"name": "manifests", "description": "Assemble a full manifest from simplified box inputs."},
    {"name": "builds", "description": "Create builds, poll status, download publish files."},
    {"name": "health", "description": "Liveness."},
]

app = FastAPI(
    title="Mystery-box Build Service",
    description=DESCRIPTION,
    version="1.0.0",
    openapi_tags=TAGS,
)

# Documented error responses reused across the authenticated routes.
_AUTH_RESPONSES = {
    401: {"description": "Missing or invalid X-API-Key."},
    503: {"description": "Server has no API_KEY configured (fails closed)."},
}


@app.on_event("startup")
def _ensure_dirs() -> None:
    settings.ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/healthz", tags=["health"], summary="Liveness probe")
def healthz() -> dict:
    return {"status": "ok"}


@app.post(
    "/builds",
    response_model=BuildAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_api_key)],
    tags=["builds"],
    summary="Validate a manifest and enqueue a build",
    responses={
        **_AUTH_RESPONSES,
        202: {"description": "Manifest valid; build queued."},
        400: {"description": "Missing game_id or manifest failed validation."},
        409: {"description": "Prod game_id already built (pass overwrite=true)."},
    },
)
def create_build(
    manifest: dict = Body(..., description="The mystery-box manifest (see games/mystery_box_dynamic/manifests)."),
    mode: str = Query("prod", pattern="^(prod|dev)$", description="prod = full publishable build; dev = fast preview."),
    overwrite: bool = Query(False, description="Allow rebuilding a game_id that was already built (prod); also retries a failed S3 deploy."),
) -> BuildAccepted:
    game_id = manifest.get("game_id")
    if not game_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "manifest is missing 'game_id'.")

    # Fast pre-flight validation (no sims) so obvious authoring errors 400 immediately.
    ok, message = builder.validate_manifest(manifest)
    if not ok:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Invalid manifest: {message}")

    # Guard against silently clobbering an existing prod build (a backoffice typo).
    if mode == "prod" and not overwrite and builder.already_built(game_id):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"game_id '{game_id}' already has a prod build; pass overwrite=true to rebuild.",
        )

    job = builder.enqueue_build(manifest, mode=mode, publishable=(mode == "prod"))
    return BuildAccepted(job_id=job.id, game_id=job.game_id, mode=job.mode, status=job.status, num_sims=job.num_sims)


@app.post(
    "/manifests",
    response_model=ManifestResult,
    dependencies=[Depends(require_api_key)],
    tags=["manifests"],
    summary="Assemble (and optionally build) a manifest from simplified box inputs",
    responses={
        **_AUTH_RESPONSES,
        200: {"description": "Assembled + validated manifest (plus job when build=true)."},
        400: {"description": "Bad box spec or the assembled manifest failed validation."},
        409: {"description": "build=true, prod game_id already built (pass overwrite=true)."},
    },
)
def create_manifest(
    spec: BoxSpec,
    build: bool = Query(False, description="Also enqueue a build of the assembled manifest."),
    mode: str = Query("prod", pattern="^(prod|dev)$", description="Build mode when build=true."),
    overwrite: bool = Query(False, description="Allow rebuilding an existing prod game_id when build=true."),
) -> ManifestResult:
    # 1) Assemble the full manifest from the simplified box fields.
    try:
        manifest = manifest_builder.assemble_manifest(spec.model_dump())
    except manifest_builder.BuildError as err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(err))

    # 2) Validate it through the SDK (no sims) so any remaining invariant fails cleanly.
    ok, message = builder.validate_manifest(manifest)
    if not ok:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Assembled manifest invalid: {message}")

    result = ManifestResult(
        manifest=manifest,
        game_id=manifest["game_id"],
        num_sims=manifest["build"]["num_sims"],
        rtp=manifest["rtp"],
        wincap=manifest["wincap"],
    )

    # 3) Optionally build in the same call.
    if build:
        if mode == "prod" and not overwrite and builder.already_built(manifest["game_id"]):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"game_id '{manifest['game_id']}' already has a prod build; pass overwrite=true.",
            )
        job = builder.enqueue_build(manifest, mode=mode, publishable=(mode == "prod"))
        result.job = BuildAccepted(job_id=job.id, game_id=job.game_id, mode=job.mode, status=job.status, num_sims=job.num_sims)

    return result


@app.get(
    "/builds/{job_id}",
    response_model=JobStatus,
    dependencies=[Depends(require_api_key)],
    tags=["builds"],
    summary="Get build job status",
    responses={**_AUTH_RESPONSES, 404: {"description": "Unknown job_id."}},
)
def get_build(job_id: str) -> JobStatus:
    job = registry.get(job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown job_id.")
    return JobStatus(**job.to_public())


@app.get(
    "/builds/{job_id}/download",
    dependencies=[Depends(require_api_key)],
    tags=["builds"],
    summary="Download the publish files zip (local mode only)",
    response_class=FileResponse,
    responses={
        **_AUTH_RESPONSES,
        200: {"content": {"application/zip": {}}, "description": "Publish files zip."},
        404: {"description": "Unknown job_id."},
        409: {"description": "Not succeeded yet, or served from S3 (use s3_files / s3_zip)."},
    },
)
def download_build(job_id: str) -> FileResponse:
    """Convenience local download. In ephemeral (S3) mode the local zip is deleted after
    upload — fetch the stable paths from GET /builds/{job_id} (s3_files / s3_zip) instead."""
    job = registry.get(job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown job_id.")
    if job.status != "succeeded":
        raise HTTPException(status.HTTP_409_CONFLICT, f"job is '{job.status}', not ready.")
    if not job.local_available or not job.zip_path:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "build is stored in S3; get its paths from GET /builds/{job_id} (s3_files / s3_zip).",
        )
    return FileResponse(
        job.zip_path,
        media_type="application/zip",
        filename=f"{job.game_id}_publish.zip",
    )


@app.get(
    "/builds/{job_id}/events",
    dependencies=[Depends(require_api_key)],
    tags=["builds"],
    summary="Download the readable events sample (books_events.json)",
    responses={
        **_AUTH_RESPONSES,
        200: {"content": {"application/json": {}}, "description": "Readable events sample."},
        307: {"description": "Redirect to the sample's S3 URL (ephemeral mode)."},
        404: {"description": "Unknown job_id, or the build produced no events sample."},
        409: {"description": "Job not succeeded yet."},
    },
)
def download_events(job_id: str):
    """The readable ~100-round events sample for frontend/game devs — a dev aid delivered
    separately from the ACP publish set (never inside publish.zip). Streams the local file
    when available; in ephemeral (S3) mode redirects to its stable S3 URL."""
    job = registry.get(job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown job_id.")
    if job.status != "succeeded":
        raise HTTPException(status.HTTP_409_CONFLICT, f"job is '{job.status}', not ready.")
    # Prefer the durable S3 copy when present: it avoids a race with ephemeral cleanup deleting
    # the local file mid-request, and we re-presign fresh so the redirect target never expires
    # (falling back to the stable public URL). Serve the local file only in local/dev mode
    # (no bucket), where events_file is None.
    if job.events_file:
        key = job.events_file.get("key")
        target = (s3.presign(key) if key else None) or job.events_file.get("url")
        if target:
            return RedirectResponse(url=target, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    if job.events_path and Path(job.events_path).is_file():
        return FileResponse(
            job.events_path,
            media_type="application/json",
            filename=f"{job.game_id}_books_events.json",
        )
    raise HTTPException(status.HTTP_404_NOT_FOUND, "this build has no events sample.")
