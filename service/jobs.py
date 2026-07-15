"""In-memory build-job registry.

Single-instance store: jobs live in a dict guarded by a lock; the downloadable artifacts
live on disk under ARTIFACT_DIR. On process restart the in-memory records are lost but the
zips persist — acceptable for a single internal service. Swap for SQLite/Redis if the
service ever needs to scale horizontally or survive restarts with full status history.
"""

import threading
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Job:
    """A single build request and its lifecycle state."""

    id: str
    game_id: str          # manifest game_id (the published gameID for a prod build)
    mode: str             # "prod" | "dev"
    status: str = "queued"  # queued -> running -> succeeded | failed
    publishable: bool = False  # only prod builds that ran format checks are publishable
    created_at: str = field(default_factory=_now_iso)
    finished_at: Optional[str] = None
    error: Optional[str] = None       # one-line failure reason (build stderr tail)
    files: list[str] = field(default_factory=list)  # publish file names
    zip_path: Optional[str] = None    # absolute path to publish.zip (None once ephemerally deleted)
    local_available: bool = True      # False after ephemeral cleanup removes local files

    # Dev-facing readable events sample (books_events.json) — a SEPARATE artifact from the ACP
    # publish set (never in publish.zip). events_path is the server-local copy (for /events in
    # local mode); events_file is its stable S3 descriptor {name,key,uri,url} once uploaded.
    events_path: Optional[str] = None
    events_file: Optional[dict] = None

    # --- S3 deploy sub-state (independent of build status) ---
    # "skipped" (no bucket / dev build) | "uploaded" | "failed". A deploy failure never
    # flips the build to failed — the on-disk artifact is still valid.
    deploy_status: str = "skipped"
    deploy_error: Optional[str] = None
    s3_prefix: Optional[str] = None            # "s3://<bucket>/<prefix>/"
    # Stable, savable paths the backoffice stores. Each: {name, key, uri, url[, presigned_url]}.
    s3_files: list[dict] = field(default_factory=list)
    s3_zip: Optional[dict] = None              # same shape, for the publish.zip

    def to_public(self) -> dict:
        """Serializable status view (drops server-local paths)."""
        data = asdict(self)
        data.pop("zip_path", None)
        data.pop("events_path", None)  # server-local path; the public view carries events_file
        return data


class JobRegistry:
    """Thread-safe job store."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, game_id: str, mode: str, publishable: bool) -> Job:
        job = Job(id=uuid.uuid4().hex, game_id=game_id, mode=mode, publishable=publishable)
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job_id: str, **fields) -> Optional[Job]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            for key, value in fields.items():
                setattr(job, key, value)
            return job

    def list(self) -> list[Job]:
        with self._lock:
            return list(self._jobs.values())


registry = JobRegistry()
