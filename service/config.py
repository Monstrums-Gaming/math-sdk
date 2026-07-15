"""Service configuration, resolved once from environment variables (with .env support)."""

import os
from pathlib import Path

from dotenv import load_dotenv

# service/ sits at the repo root; the repo root is its parent.
REPO_ROOT = Path(__file__).resolve().parent.parent

# Load .env from the repo root if present (python-dotenv is already a project dep).
load_dotenv(REPO_ROOT / ".env")


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


class Settings:
    """Runtime configuration. All values come from the environment; sane defaults for
    everything except API_KEY (which is intentionally required — the service fails closed
    without it)."""

    # Shared secret the backoffice must send as the X-API-Key header. Unset => auth fails
    # closed (every /builds request is rejected) so the service is never accidentally open.
    API_KEY: str = os.environ.get("API_KEY", "")

    # Max builds running at once. Builds are CPU-heavy (multiprocess sims); keep this low.
    MAX_CONCURRENT_BUILDS: int = _int_env("MAX_CONCURRENT_BUILDS", 2)

    # Hard cap on a single build's wall-clock. A prod build is minutes; this guards a hang.
    BUILD_TIMEOUT_SECONDS: int = _int_env("BUILD_TIMEOUT_SECONDS", 1800)

    # Where per-job artifacts (snapshot publish files + publish.zip) are written.
    ARTIFACT_DIR: Path = Path(os.environ.get("ARTIFACT_DIR", REPO_ROOT / "service" / "artifacts"))

    # SQLite file backing the job registry (restart-durable job status). Defaults alongside
    # the artifacts (follows an ARTIFACT_DIR override); mount ARTIFACT_DIR on a volume to also
    # survive container recreation.
    JOBS_DB_PATH: Path = Path(os.environ.get("JOBS_DB_PATH", ARTIFACT_DIR / "jobs.db"))

    # The venv python that has the SDK installed; defaults to the repo's ./env.
    PYTHON_BIN: str = os.environ.get("PYTHON_BIN", str(REPO_ROOT / "env" / "bin" / "python"))

    # The dynamic generator entrypoint every build shells out to.
    RUN_PY: Path = REPO_ROOT / "games" / "mystery_box_dynamic" / "run.py"

    # Root of the per-game output trees (games/<game_id>/library/...).
    GAMES_DIR: Path = REPO_ROOT / "games"

    # Fixed num_sims for manifests assembled by POST /manifests. Prize odds must make
    # num_sims * prob an integer (i.e. every prob a multiple of 1/MANIFEST_NUM_SIMS).
    MANIFEST_NUM_SIMS: int = _int_env("MANIFEST_NUM_SIMS", 100000)

    # --- S3 deploy (optional) ---
    # When AWS_S3_BUCKET is set, a successful *prod* build auto-uploads its publish files
    # to s3://<bucket>/<S3_PREFIX><game_id>/. Unset => S3 upload is skipped (build still
    # succeeds and the zip is still downloadable). This is YOUR bucket for the backoffice —
    # it does NOT publish the game to the Stake Engine RGS (that is the ACP dashboard).
    AWS_S3_BUCKET: str = os.environ.get("AWS_S3_BUCKET", "")

    # Optional key prefix under the bucket, e.g. "mystery-box/". Leading slashes stripped.
    S3_PREFIX: str = os.environ.get("S3_PREFIX", "").lstrip("/")

    AWS_REGION: str = os.environ.get("AWS_REGION", "") or os.environ.get("AWS_DEFAULT_REGION", "")

    # Explicit credentials are optional — if unset, boto3's default chain (env vars, shared
    # config, or an IAM role) is used. Falls back to the repo's existing ACCESS_KEY/
    # SECRET_KEY names (uploads/.env style) for convenience.
    AWS_ACCESS_KEY_ID: str = os.environ.get("AWS_ACCESS_KEY_ID", "") or os.environ.get("ACCESS_KEY", "")
    AWS_SECRET_ACCESS_KEY: str = os.environ.get("AWS_SECRET_ACCESS_KEY", "") or os.environ.get("SECRET_KEY", "")

    # For S3-compatible stores (MinIO, LocalStack) — leave blank for real AWS.
    S3_ENDPOINT_URL: str = os.environ.get("S3_ENDPOINT_URL", "")

    # Seconds a presigned download URL stays valid (returned per uploaded file). 0 disables
    # presigning (only the stable url / s3:// uri are recorded).
    S3_PRESIGN_EXPIRY: int = _int_env("S3_PRESIGN_EXPIRY", 3600)

    # Stable base URL the backoffice saves & serves from — a CDN / custom domain in front of
    # the bucket, e.g. "https://cdn.example.com". Returned as each file's `url` (= base/key).
    # Unset => the S3 virtual-hosted HTTPS URL is used instead.
    S3_PUBLIC_BASE_URL: str = os.environ.get("S3_PUBLIC_BASE_URL", "")

    # When true, a successful S3 upload deletes the local build (games/<id>/ + the job's
    # publish files/zip) — the service becomes a stateless worker and S3 is the source of
    # truth. Default: on when a bucket is configured. A failed upload never deletes anything.
    EPHEMERAL_BUILDS: bool = (
        os.environ.get("EPHEMERAL_BUILDS", "").strip().lower() in ("1", "true", "yes", "on")
        if os.environ.get("EPHEMERAL_BUILDS")
        else bool(os.environ.get("AWS_S3_BUCKET"))
    )


settings = Settings()
