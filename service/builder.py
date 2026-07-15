"""Build execution: validate a manifest, shell out to the dynamic generator, snapshot the
publish files, and zip them per job.

Why subprocess and not an in-process import: ``run.py`` -> ``create_books`` spawns
``multiprocessing.Process`` workers. Running that inside the ASGI server process is
fragile; shelling out (exactly as ``build.sh`` does) keeps the build fully isolated.
"""

import contextlib
import fcntl
import json
import os
import shutil
import subprocess
import tempfile
import threading
import zipfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from service import s3
from service.config import settings
from service.jobs import Job, registry

# The three files uploaded to the ACP live here; we zip the whole publish_files dir so
# config.json (with the sha256 hashes) travels with them.
_PUBLISH_SUBPATH = ("library", "publish_files")
# The readable dev events sample (books_events_base.json) lives OUTSIDE publish_files so the
# ACP set stays clean; delivered as its own artifact (never in publish.zip).
_SAMPLE_SUBPATH = ("library", "samples", "books_events_base.json")
_SAMPLE_DOWNLOAD_NAME = "books_events.json"  # name in the job dir / S3 / download

# Bounded worker pool for builds + one lock per game_id so two builds of the SAME game
# never write games/<id>/library concurrently. Different games build in parallel.
_pool = ThreadPoolExecutor(max_workers=settings.MAX_CONCURRENT_BUILDS, thread_name_prefix="build")
_game_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)
_game_locks_guard = threading.Lock()

# Cross-process lockfiles live here (one per effective game id). The in-process threading
# lock only serializes builds within a single worker; concurrent builds of the same game from
# another worker, a service restart, or a stray manual build.sh would otherwise write
# games/<id>/library at the same time and corrupt each other (books written by one process,
# LUT by another -> "Book payouts != LUT payouts" hash mismatch). An fcntl.flock on a per-game
# lockfile serializes them across processes too.
_LOCK_DIR = settings.ARTIFACT_DIR / ".locks"


def _game_lock(game_id: str) -> threading.Lock:
    with _game_locks_guard:
        return _game_locks[game_id]


@contextlib.contextmanager
def _game_build_lock(eff_id: str):
    """Serialize builds of one game id across BOTH threads (in-process) and processes.

    Holds the in-process threading lock and an exclusive fcntl.flock on
    ARTIFACT_DIR/.locks/<eff_id>.lock for the duration, so no two builds ever share the
    games/<eff_id>/ output tree regardless of worker count."""
    _LOCK_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = _LOCK_DIR / f"{_safe_lock_name(eff_id)}.lock"
    with _game_lock(eff_id):
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)


def _safe_lock_name(eff_id: str) -> str:
    """A filesystem-safe lockfile stem (game ids are already tame, but never build a path
    from an unsanitized id)."""
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in eff_id) or "game"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mode_env(mode: str) -> dict[str, str]:
    """Env overrides run.py honours, per build mode. prod leaves everything to the
    manifest's build block; dev is a fast, non-publishable preview isolated under a
    ``_dev`` game-id suffix so it never clobbers a prod build's on-disk output."""
    if mode == "dev":
        return {
            "NUM_SIMS": "1000",
            "COMPRESSION": "false",
            "RUN_FORMAT_CHECKS": "false",
            "GAME_ID_SUFFIX": "_dev",
        }
    return {"GAME_ID_SUFFIX": ""}  # prod: manifest build values, no suffix


def effective_game_id(manifest_game_id: str, mode: str) -> str:
    """The on-disk game id (and published gameID) for a given mode."""
    return manifest_game_id + ("_dev" if mode == "dev" else "")


def publish_dir_for(game_id: str) -> Path:
    """games/<game_id>/library/publish_files."""
    return settings.GAMES_DIR.joinpath(game_id, *_PUBLISH_SUBPATH)


def sample_events_src(game_id: str) -> Path:
    """games/<game_id>/library/samples/books_events_base.json (may not exist if disabled)."""
    return settings.GAMES_DIR.joinpath(game_id, *_SAMPLE_SUBPATH)


def already_built(manifest_game_id: str) -> bool:
    """True if a prior prod build already produced publish files for this game_id. When a
    bucket is configured the local files may have been ephemerally deleted, so check S3;
    otherwise check the local publish_files (not the bare dir — a --validate call creates
    games/<id>/reels/ as a side effect but never publish_files)."""
    if s3.s3_enabled():
        return s3.object_exists(manifest_game_id)
    return publish_dir_for(manifest_game_id).joinpath("index.json").is_file()


def validate_manifest(manifest: dict) -> tuple[bool, str]:
    """Fast pre-flight: run ``run.py --validate`` (no sims). Returns (ok, message)."""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=True) as tmp:
        json.dump(manifest, tmp)
        tmp.flush()
        proc = subprocess.run(
            [settings.PYTHON_BIN, str(settings.RUN_PY), "--validate", "--manifest", tmp.name],
            cwd=str(settings.GAMES_DIR.parent),
            capture_output=True,
            text=True,
            timeout=120,
        )
    if proc.returncode == 0:
        return True, (proc.stdout.strip() or "valid")
    # run.py prints "[validate] INVALID: <reason>" to stderr on an authoring error.
    return False, _last_line(proc.stderr) or _last_line(proc.stdout) or "manifest validation failed"


def enqueue_build(manifest: dict, mode: str, publishable: bool) -> Job:
    """Create a job and schedule the build on the pool. Returns immediately."""
    job = registry.create(game_id=manifest["game_id"], mode=mode, publishable=publishable)
    _pool.submit(_run_job, job.id, manifest, mode)
    return job


def _run_job(job_id: str, manifest: dict, mode: str) -> None:
    """Worker body: serialize per game, build, snapshot, zip, record status."""
    manifest_game_id = manifest["game_id"]
    eff_id = effective_game_id(manifest_game_id, mode)
    registry.update(job_id, status="running")

    with _game_build_lock(eff_id):
        job_dir = settings.ARTIFACT_DIR / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = job_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        env = _build_env(mode)
        try:
            proc = subprocess.run(
                [settings.PYTHON_BIN, str(settings.RUN_PY), "--manifest", str(manifest_path)],
                cwd=str(settings.GAMES_DIR.parent),
                env=env,
                capture_output=True,
                text=True,
                timeout=settings.BUILD_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            registry.update(
                job_id, status="failed", finished_at=_now_iso(),
                error=f"build exceeded {settings.BUILD_TIMEOUT_SECONDS}s timeout",
            )
            return

        # Persist the build log for debugging regardless of outcome.
        (job_dir / "build.log").write_text(
            (proc.stdout or "") + "\n--- STDERR ---\n" + (proc.stderr or ""), encoding="utf-8"
        )

        if proc.returncode != 0:
            registry.update(
                job_id, status="failed", finished_at=_now_iso(),
                error=_last_line(proc.stderr) or f"build exited {proc.returncode}",
            )
            return

        try:
            files = _snapshot_and_zip(eff_id, job_dir)
        except FileNotFoundError as err:
            registry.update(job_id, status="failed", finished_at=_now_iso(), error=str(err))
            return

        # Snapshot the readable events sample separately (kept out of publish.zip).
        sample_local = _snapshot_sample_events(eff_id, job_dir)

        # The build artifact is now captured; the build has succeeded regardless of what
        # the S3 deploy does next. Deploy + cleanup stay inside the per-game lock so a
        # concurrent same-game build can't overwrite games/<eff_id> mid-upload.
        registry.update(
            job_id, status="succeeded", finished_at=_now_iso(),
            files=files, zip_path=str(job_dir / "publish.zip"),
            events_path=str(sample_local) if sample_local else None,
        )
        uploaded = _maybe_deploy(job_id, manifest_game_id, mode, job_dir, sample_local)
        _cleanup_after_build(job_id, eff_id, job_dir, uploaded)


def _maybe_deploy(job_id: str, game_id: str, mode: str, job_dir: Path, sample_local: Optional[Path]) -> bool:
    """Best-effort S3 upload of a successful prod build's publish files + zip + events sample.
    Returns True only on a fully successful upload. Never fails the job — records the outcome in
    the deploy_* fields so a bucket misconfig can be retried (via overwrite=true) without loss."""
    if mode != "prod" or not s3.s3_enabled():
        return False  # dev preview, or no bucket configured -> stays "skipped"
    try:
        result = s3.upload_build(
            game_id, job_dir / "publish_files", job_dir / "publish.zip", sample_path=sample_local
        )
        registry.update(
            job_id, deploy_status="uploaded",
            s3_prefix=result["prefix"], s3_files=result["files"], s3_zip=result["zip"],
            events_file=result.get("sample"),
        )
        return True
    except Exception as err:  # boto3/network/credentials — keep the build succeeded
        registry.update(job_id, deploy_status="failed", deploy_error=f"{type(err).__name__}: {err}")
        return False


def _snapshot_sample_events(eff_id: str, job_dir: Path) -> Optional[Path]:
    """Copy the build's readable events sample into the job dir as books_events.json so it
    survives ephemeral cleanup of games/<eff_id>/. Returns the copy's path, or None when the
    build produced no sample (SAMPLE_EVENTS=0). Deliberately NOT added to publish.zip."""
    src = sample_events_src(eff_id)
    if not src.is_file():
        return None
    dest = job_dir / _SAMPLE_DOWNLOAD_NAME
    shutil.copy2(src, dest)
    return dest


def _cleanup_after_build(job_id: str, eff_id: str, job_dir: Path, uploaded: bool) -> None:
    """In ephemeral mode, once a build is safely in S3, delete the local copies to keep the
    worker stateless: the whole generated games/<eff_id>/ tree and the job's publish files
    + zip (keeping the tiny manifest.json + build.log for debugging). A failed/absent upload
    deletes nothing — the local artifact stays the source of truth."""
    if not (settings.EPHEMERAL_BUILDS and uploaded):
        return
    shutil.rmtree(settings.GAMES_DIR / eff_id, ignore_errors=True)
    shutil.rmtree(job_dir / "publish_files", ignore_errors=True)
    (job_dir / "publish.zip").unlink(missing_ok=True)
    # The events sample is now in S3 (events_file); drop the local copy + its server path.
    (job_dir / _SAMPLE_DOWNLOAD_NAME).unlink(missing_ok=True)
    registry.update(job_id, local_available=False, zip_path=None, events_path=None)


def _build_env(mode: str) -> dict[str, str]:
    env = os.environ.copy()
    env.update(_mode_env(mode))
    return env


def _snapshot_and_zip(eff_id: str, job_dir: Path) -> list[str]:
    """Copy the built publish files into the job dir and zip them. Snapshotting here means
    a later build of the same game can't overwrite this job's downloadable artifact."""
    src = publish_dir_for(eff_id)
    if not src.is_dir():
        raise FileNotFoundError(f"expected publish files at {src}, but none were produced")

    snapshot = job_dir / "publish_files"
    if snapshot.exists():
        shutil.rmtree(snapshot)
    shutil.copytree(src, snapshot)

    files = sorted(p.name for p in snapshot.iterdir() if p.is_file())
    zip_path = job_dir / "publish.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in files:
            zf.write(snapshot / name, arcname=name)
    return files


def _last_line(text: Optional[str]) -> str:
    if not text:
        return ""
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    return lines[-1] if lines else ""
