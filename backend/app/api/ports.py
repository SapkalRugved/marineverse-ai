"""Port data API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from backend.app.schemas.ports import (
    PortListResponse,
    PortResponse,
)
from backend.app.services.ports import (
    PortsQueryError,
    list_ports,
)


router = APIRouter(
    prefix="/api/v1/ports",
    tags=["ports"],
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
    response_model=PortListResponse,
    summary="List marine ports",
)
def get_ports(
    port_type: str | None = Query(
        default=None,
        min_length=1,
        max_length=50,
    ),
    name: str | None = Query(
        default=None,
        min_length=1,
        max_length=255,
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
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
    ),
) -> PortListResponse:
    """Return filtered ports from PostgreSQL/PostGIS."""
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
        records = list_ports(
            port_type=port_type,
            name=name,
            minimum_latitude=minimum_latitude,
            maximum_latitude=maximum_latitude,
            minimum_longitude=minimum_longitude,
            maximum_longitude=maximum_longitude,
            limit=limit,
        )

    except PortsQueryError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Port data is temporarily unavailable.",
        ) from exc

    ports = [
        PortResponse.model_validate(record)
        for record in records
    ]

    return PortListResponse(
        count=len(ports),
        ports=ports,
    )
