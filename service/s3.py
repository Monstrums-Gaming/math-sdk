"""Optional S3 deploy: push a completed prod build's publish files to your own bucket.

This is a delivery/storage helper for your backoffice — it uploads to
``s3://<AWS_S3_BUCKET>/<S3_PREFIX><game_id>/``. It does NOT publish the game to the Stake
Engine RGS (that goes through the ACP dashboard). Uploading is best-effort: a failure here
is reported on the job but never invalidates the on-disk build artifact.

boto3 is already a project dependency (used by uploads/aws_upload.py).
"""

from pathlib import Path
from typing import Optional

import boto3

from service.config import settings

# Content types so browsers / the backoffice get sane headers straight from S3.
_CONTENT_TYPES = {
    ".json": "application/json",
    ".csv": "text/csv",
    ".zst": "application/zstd",
    ".jsonl": "application/x-ndjson",
}


def s3_enabled() -> bool:
    """True when a target bucket is configured; otherwise deploy is skipped."""
    return bool(settings.AWS_S3_BUCKET)


def _content_type(name: str) -> str:
    # ".jsonl.zst" -> ".zst"; plain suffix otherwise.
    return _CONTENT_TYPES.get(Path(name).suffix, "application/octet-stream")


def _client():
    """Build an S3 client. Explicit creds are used if provided, else boto3's default
    credential chain (env vars / shared config / IAM role)."""
    kwargs: dict = {}
    if settings.AWS_REGION:
        kwargs["region_name"] = settings.AWS_REGION
    if settings.S3_ENDPOINT_URL:
        kwargs["endpoint_url"] = settings.S3_ENDPOINT_URL
    if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
        kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
        kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY
    return boto3.client("s3", **kwargs)


def key_prefix(game_id: str) -> str:
    """S3 key prefix for a game: ``<S3_PREFIX><game_id>/``. Tolerates an S3_PREFIX with or
    without a trailing slash so ``math-sdk`` and ``math-sdk/`` behave identically."""
    prefix = settings.S3_PREFIX
    if prefix and not prefix.endswith("/"):
        prefix += "/"
    return f"{prefix}{game_id}/"


def public_url(key: str) -> str:
    """A stable, savable URL for an object key — what the backoffice stores. Uses
    S3_PUBLIC_BASE_URL (a CDN / custom domain, e.g. https://cdn.example.com) if set,
    else the S3 virtual-hosted HTTPS URL. Stable (non-expiring), unlike a presigned URL."""
    base = settings.S3_PUBLIC_BASE_URL.rstrip("/")
    if base:
        return f"{base}/{key}"
    region = settings.AWS_REGION or "us-east-1"
    return f"https://{settings.AWS_S3_BUCKET}.s3.{region}.amazonaws.com/{key}"


def _file_entry(client, name: str, bucket: str, key: str) -> dict:
    """Describe one uploaded object for the backoffice to save."""
    entry = {"name": name, "key": key, "uri": f"s3://{bucket}/{key}", "url": public_url(key)}
    if settings.S3_PRESIGN_EXPIRY > 0:
        entry["presigned_url"] = client.generate_presigned_url(
            "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=settings.S3_PRESIGN_EXPIRY
        )
    return entry


def upload_build(
    game_id: str,
    publish_dir: Path,
    zip_path: Optional[Path] = None,
    sample_path: Optional[Path] = None,
) -> dict:
    """Upload a build's publish files (and optionally the zip + the readable events sample)
    to the bucket under the game's prefix. Returns stable, savable paths:

        {bucket, prefix: "s3://bucket/prefix/", files: [{name,key,uri,url[,presigned_url]}],
         zip: {...} | None, sample: {...} | None}

    ``sample`` is the dev-facing books_events.json, uploaded alongside but reported separately
    from the ACP ``files``. Raises on any AWS/network error (caller records a deploy failure).
    """
    bucket = settings.AWS_S3_BUCKET
    prefix = key_prefix(game_id)
    client = _client()

    files = []
    for path in sorted(p for p in publish_dir.iterdir() if p.is_file()):
        key = prefix + path.name
        client.upload_file(str(path), bucket, key, ExtraArgs={"ContentType": _content_type(path.name)})
        files.append(_file_entry(client, path.name, bucket, key))

    zip_entry = None
    if zip_path is not None and Path(zip_path).is_file():
        zp = Path(zip_path)
        key = prefix + zp.name
        client.upload_file(str(zp), bucket, key, ExtraArgs={"ContentType": "application/zip"})
        zip_entry = _file_entry(client, zp.name, bucket, key)

    sample_entry = None
    if sample_path is not None and Path(sample_path).is_file():
        sp = Path(sample_path)
        key = prefix + sp.name
        client.upload_file(str(sp), bucket, key, ExtraArgs={"ContentType": _content_type(sp.name)})
        sample_entry = _file_entry(client, sp.name, bucket, key)

    return {
        "bucket": bucket,
        "prefix": f"s3://{bucket}/{prefix}",
        "files": files,
        "zip": zip_entry,
        "sample": sample_entry,
    }


def presign(key: str) -> Optional[str]:
    """A FRESH presigned GET URL for an object key, minted on demand (so it can't be stale
    like one stored at build time). Returns None if presigning is disabled
    (S3_PRESIGN_EXPIRY <= 0) or on any error, so callers fall back to the stable public URL."""
    if settings.S3_PRESIGN_EXPIRY <= 0:
        return None
    try:
        return _client().generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.AWS_S3_BUCKET, "Key": key},
            ExpiresIn=settings.S3_PRESIGN_EXPIRY,
        )
    except Exception:
        return None


def object_exists(game_id: str) -> bool:
    """True if this game's publish files already exist in the bucket (checks index.json).
    Used by the overwrite guard once local files are deleted. Best-effort: any error
    (missing object, transient failure) returns False so a build is never wrongly blocked."""
    try:
        _client().head_object(Bucket=settings.AWS_S3_BUCKET, Key=key_prefix(game_id) + "index.json")
        return True
    except Exception:
        return False
