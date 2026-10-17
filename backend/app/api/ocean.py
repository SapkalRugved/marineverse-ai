"""Ocean data API endpoints."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, status

from backend.app.schemas.ocean import (
    OceanListResponse,
    OceanResponse,
)
from backend.app.services.ocean import (
    OceanQueryError,
    list_ocean_conditions,
)


router = APIRouter(
    prefix="/api/v1/ocean",
    tags=["ocean"],
)


def validate_range(
    minimum: float | None,
    maximum: float | None,
    range_name: str,
) -> None:
    """Reject a numeric range whose minimum exceeds its maximum."""
    if (
        minimum is not None
        and maximum is not None
        and minimum > maximum
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"minimum_{range_name} must not exceed "
                f"maximum_{range_name}."
            ),
        )


@router.get(
    "",
    response_model=OceanListResponse,
    summary="List marine ocean conditions",
)
def get_ocean_conditions(
    source: str | None = Query(
        default=None,
        min_length=1,
        max_length=50,
    ),
    source_dataset: str | None = Query(
        default=None,
        min_length=1,
        max_length=150,
    ),
    is_forecast: bool | None = Query(default=None),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    minimum_depth_m: float | None = Query(
        default=None,
        ge=0,
    ),
    maximum_depth_m: float | None = Query(
        default=None,
        ge=0,
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
    latest_only: bool = Query(default=True),
    limit: int = Query(
        default=500,
        ge=1,
        le=5000,
    ),
    offset: int = Query(
        default=0,
        ge=0,
    ),
) -> OceanListResponse:
    """Return filtered Copernicus ocean conditions."""
    validate_range(
        minimum_depth_m,
        maximum_depth_m,
        "depth_m",
    )
    validate_range(
        minimum_latitude,
        maximum_latitude,
        "latitude",
    )
    validate_range(
        minimum_longitude,
        maximum_longitude,
        "longitude",
    )

    if (
        start_time is not None
        and end_time is not None
        and start_time > end_time
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="start_time must not exceed end_time.",
        )

    try:
        records = list_ocean_conditions(
            source=source,
            source_dataset=source_dataset,
            is_forecast=is_forecast,
            start_time=start_time,
            end_time=end_time,
            minimum_depth_m=minimum_depth_m,
            maximum_depth_m=maximum_depth_m,
            minimum_latitude=minimum_latitude,
            maximum_latitude=maximum_latitude,
            minimum_longitude=minimum_longitude,
            maximum_longitude=maximum_longitude,
            latest_only=latest_only,
            limit=limit,
            offset=offset,
        )

    except OceanQueryError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ocean data is temporarily unavailable.",
        ) from exc

    ocean = [
        OceanResponse.model_validate(record)
        for record in records
    ]

    return OceanListResponse(
        count=len(ocean),
        ocean=ocean,
    )