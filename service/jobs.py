"""SQLite-backed build-job registry.

Job status is persisted to a SQLite file (``settings.JOBS_DB_PATH``) so it survives a process
restart (uvicorn crash/reload) — unlike the previous in-memory dict. Each job is stored as a
single JSON blob (the whole ``Job`` dataclass), which keeps the schema stable when ``Job`` gains
a field. The downloadable artifacts still live on disk under ARTIFACT_DIR.

Scope: this is single-box durability. The connection is guarded by an in-process lock, which
does NOT coordinate across processes — so keep exactly one worker (see DEPLOY.md). Surviving a
container *recreate* additionally requires the DB path to be on a mounted volume. Multi-replica
/ HA remains the SQS + external-store path.
"""

import json
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field, asdict, fields as _dataclass_fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from service.config import settings


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
    num_sims: Optional[int] = None  # sims the build ran (dev forces 1000; prod uses build.num_sims)
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


_JOB_FIELDS = frozenset(f.name for f in _dataclass_fields(Job))


class JobRegistry:
    """SQLite-backed, thread-safe job store. Same API as the former in-memory registry:
    create/get/update/list return ``Job`` objects, so callers are unchanged."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self._db_path = Path(db_path or settings.JOBS_DB_PATH)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        # One connection shared across threads (serialized by _lock). WAL + a busy timeout keep
        # writes robust; check_same_thread=False because builds run in a ThreadPoolExecutor.
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS jobs "
            "(id TEXT PRIMARY KEY, created_at TEXT, data TEXT NOT NULL)"
        )
        self._conn.commit()

    @staticmethod
    def _to_job(data_json: str) -> Job:
        return Job(**json.loads(data_json))

    def create(self, game_id: str, mode: str, publishable: bool, num_sims: Optional[int] = None) -> Job:
        job = Job(id=uuid.uuid4().hex, game_id=game_id, mode=mode, publishable=publishable, num_sims=num_sims)
        with self._lock:
            self._conn.execute(
                "INSERT INTO jobs (id, created_at, data) VALUES (?, ?, ?)",
                (job.id, job.created_at, json.dumps(asdict(job))),
            )
            self._conn.commit()
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            row = self._conn.execute("SELECT data FROM jobs WHERE id = ?", (job_id,)).fetchone()
            return self._to_job(row[0]) if row else None

    def update(self, job_id: str, **fields) -> Optional[Job]:
        unknown = set(fields) - _JOB_FIELDS
        if unknown:
            raise ValueError(f"unknown Job field(s): {sorted(unknown)}")
        with self._lock:
            row = self._conn.execute("SELECT data FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if row is None:
                return None
            data = json.loads(row[0])
            data.update(fields)  # read-modify-write, same effect as the old setattr loop
            self._conn.execute(
                "UPDATE jobs SET data = ? WHERE id = ?", (json.dumps(data), job_id)
            )
            self._conn.commit()
            return Job(**data)

    def list(self) -> list[Job]:
        with self._lock:
            rows = self._conn.execute("SELECT data FROM jobs ORDER BY created_at").fetchall()
            return [self._to_job(r[0]) for r in rows]


registry = JobRegistry()
