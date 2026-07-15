"""Pydantic response models. The request body is the raw manifest dict — it is validated
by the SDK (``GameConfig``) via the --validate subprocess, not re-modeled here, so the API
never drifts from the manifest format the generator actually accepts."""

from typing import Optional

from pydantic import BaseModel, Field


class BuildAccepted(BaseModel):
    job_id: str
    game_id: str
    mode: str
    status: str


# --- POST /manifests: simplified box spec the backoffice sends ---

class PrizeSpec(BaseModel):
    name: str = Field(..., description="Display name, e.g. '$100 Voucher'.")
    payout: float = Field(..., description="Catalog payout multiplier (value at box price).")
    prob: float = Field(..., gt=0, le=1, description="Draw probability; all probs must sum to 1.0.")
    sku: Optional[str] = Field(None, description="Optional SKU key; auto P1..Pn if omitted.")


class BoxSpec(BaseModel):
    game_name: str
    provider_number: int
    provider_name: str
    box_cost: float = Field(..., gt=0, description="Box price in base-bet units.")
    prizes: list[PrizeSpec] = Field(..., min_length=1)
    cost_model: str = Field("unit", description="'unit' (ACP-valid, recommended) or 'box_cost'.")
    game_id: Optional[str] = Field(None, description="Override; else '<provider_number>_<slug(game_name)>'.")
    working_name: Optional[str] = None
    win_type: str = "scatter"
    num_sims: Optional[int] = Field(None, description="Override the fixed MANIFEST_NUM_SIMS.")
    build: Optional[dict] = Field(None, description="Override build-block knobs (merged).")


class ManifestResult(BaseModel):
    manifest: dict
    game_id: str
    num_sims: int
    rtp: float
    wincap: float
    # Present only when ?build=true.
    job: Optional[BuildAccepted] = None


class JobStatus(BaseModel):
    id: str
    game_id: str
    mode: str
    status: str
    publishable: bool
    created_at: str
    finished_at: Optional[str] = None
    error: Optional[str] = None
    files: list[str] = []
    local_available: bool = True
    # S3 deploy sub-state (only meaningful for prod builds when a bucket is configured).
    deploy_status: str = "skipped"
    deploy_error: Optional[str] = None
    s3_prefix: Optional[str] = None
    # Stable, savable paths for the backoffice. Each: {name, key, uri, url[, presigned_url]}.
    s3_files: list[dict] = []
    s3_zip: Optional[dict] = None
