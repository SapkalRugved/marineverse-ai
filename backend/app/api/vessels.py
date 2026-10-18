"""AIS vessel data API endpoints."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, status

from backend.app.schemas.vessels import (
    VesselListResponse,
    VesselResponse,
)
from backend.app.services.vessels import (
    VesselsQueryError,
    list_vessels,
)


router = APIRouter(
    prefix="/api/v1/vessels",
    tags=["vessels"],
)


def validate_coordinate_range(
    minimum: float | None,
    maximum: float | None,
    coordinate_name: str,
) -> None:
    """Reject a coordinate range whose minimum exceeds its maximum."""
    if (
        minimum is not None
        and maximum is not None
        and minimum > maximum
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"minimum_{coordinate_name} must not exceed "
                f"maximum_{coordinate_name}."
            ),
        )


@router.get(
    "",
    response_model=VesselListResponse,
    summary="List vessels with latest positions",
)
def get_vessels(
    mmsi: int | None = Query(
        default=None,
        ge=100000000,
        le=999999999,
    ),
    name: str | None = Query(
        default=None,
        min_length=1,
        max_length=200,
    ),
    ship_type: str | None = Query(
        default=None,
        min_length=1,
        max_length=100,
    ),
    source: str | None = Query(
        default=None,
        min_length=1,
        max_length=50,
    ),
    minimum_latitude: float | None = Query(
        default=None,
        ge=-90,
        le=90,
    ),
    maximum_latitude: float | None = Query(
        default=None,
        ge=-90,
        le=90,
    ),
    minimum_longitude: float | None = Query(
        default=None,
        ge=-180,
        le=180,
    ),
    maximum_longitude: float | None = Query(
        default=None,
        ge=-180,
        le=180,
    ),
    observed_after: datetime | None = Query(
        default=None,
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
    ),
) -> VesselListResponse:
    """Return vessels and their latest stored positions."""
    validate_coordinate_range(
        minimum_latitude,
        maximum_latitude,
        "latitude",
    )
    validate_coordinate_range(
        minimum_longitude,
        maximum_longitude,
        "longitude",
    )

    try:
        records = list_vessels(
            mmsi=mmsi,
            name=name,
            ship_type=ship_type,
            source=source,
            minimum_latitude=minimum_latitude,
            maximum_latitude=maximum_latitude,
            minimum_longitude=minimum_longitude,
            maximum_longitude=maximum_longitude,
            observed_after=observed_after,
            limit=limit,
        )

    except VesselsQueryError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Vessel data is temporarily unavailable.",
        ) from exc

    vessels = [
        VesselResponse.model_validate(record)
        for record in records
    ]

    return VesselListResponse(
        count=len(vessels),
        vessels=vessels,
    )
