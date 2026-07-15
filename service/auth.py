"""API-key authentication for the build routes."""

import hmac

from fastapi import Header, HTTPException, status

from service.config import settings


async def require_api_key(x_api_key: str = Header(default="")) -> None:
    """FastAPI dependency: reject any request whose X-API-Key header doesn't match the
    configured API_KEY. Fails closed — if API_KEY is unset the service refuses all builds
    rather than running open."""
    if not settings.API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Server misconfigured: API_KEY is not set.",
        )
    # Constant-time compare to avoid leaking the key length/content via timing.
    if not x_api_key or not hmac.compare_digest(x_api_key, settings.API_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key.",
        )
