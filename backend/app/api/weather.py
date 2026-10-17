"""Weather data API endpoints."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, status

from backend.app.schemas.weather import (
    WeatherListResponse,
    WeatherResponse,
)
from backend.app.services.weather import (
    WeatherQueryError,
    list_weather,
)


router = APIRouter(
    prefix="/api/v1/weather",
    tags=["weather"],
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
    response_model=WeatherListResponse,
    summary="List marine weather conditions",
)
def get_weather(
    source: str | None = Query(
        default=None,
        min_length=1,
        max_length=50,
    ),
    source_dataset: str | None = Query(
        default=None,
        min_length=1,
        max_length=100,
    ),
    is_forecast: bool | None = Query(default=None),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
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
        default=100,
        ge=1,
        le=500,
    ),
) -> WeatherListResponse:
    """Return filtered weather conditions from PostgreSQL."""
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
        records = list_weather(
            source=source,
            source_dataset=source_dataset,
            is_forecast=is_forecast,
            start_time=start_time,
            end_time=end_time,
            minimum_latitude=minimum_latitude,
            maximum_latitude=maximum_latitude,
            minimum_longitude=minimum_longitude,
            maximum_longitude=maximum_longitude,
            latest_only=latest_only,
            limit=limit,
        )

    except WeatherQueryError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Weather data is temporarily unavailable.",
        ) from exc

    weather = [
        WeatherResponse.model_validate(record)
        for record in records
    ]

    return WeatherListResponse(
        count=len(weather),
        weather=weather,
    )