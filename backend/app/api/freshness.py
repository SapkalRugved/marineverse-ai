"""Marine dataset freshness endpoint."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from backend.app.schemas.freshness import FreshnessResponse
from backend.app.services.freshness import (
    FreshnessQueryError,
    get_data_freshness,
)


router = APIRouter(
    prefix="/api/v1/freshness",
    tags=["monitoring"],
)


@router.get(
    "",
    response_model=FreshnessResponse,
    summary="Check marine dataset freshness",
)
def get_freshness() -> FreshnessResponse:
    """Return freshness status for ports, weather, and ocean."""
    try:
        report = get_data_freshness()

    except FreshnessQueryError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Data freshness is temporarily unavailable."
            ),
        ) from exc

    return FreshnessResponse.model_validate(report)