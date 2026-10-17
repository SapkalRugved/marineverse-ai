"""Database queries for weather API endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row

from backend.marine_data.database import connect_to_database


SELECT_WEATHER_SQL = """
WITH filtered_weather AS (
    SELECT
        weather_id,
        valid_time,
        latitude,
        longitude,
        air_temperature_c,
        pressure_hpa,
        precipitation_mm,
        wind_speed_mps,
        wind_direction_deg,
        wind_gust_mps,
        is_forecast,
        source,
        source_dataset,
        ingested_at
    FROM weather_conditions
    WHERE (
        %(source)s::text IS NULL
        OR source = %(source)s::text
    )
    AND (
        %(source_dataset)s::text IS NULL
        OR source_dataset = %(source_dataset)s::text
    )
    AND (
        %(is_forecast)s::boolean IS NULL
        OR is_forecast = %(is_forecast)s::boolean
    )
    AND (
        %(start_time)s::timestamptz IS NULL
        OR valid_time >= %(start_time)s::timestamptz
    )
    AND (
        %(end_time)s::timestamptz IS NULL
        OR valid_time <= %(end_time)s::timestamptz
    )
    AND (
        %(minimum_latitude)s::double precision IS NULL
        OR latitude >= %(minimum_latitude)s::double precision
    )
    AND (
        %(maximum_latitude)s::double precision IS NULL
        OR latitude <= %(maximum_latitude)s::double precision
    )
    AND (
        %(minimum_longitude)s::double precision IS NULL
        OR longitude >= %(minimum_longitude)s::double precision
    )
    AND (
        %(maximum_longitude)s::double precision IS NULL
        OR longitude <= %(maximum_longitude)s::double precision
    )
)
SELECT
    weather_id,
    valid_time,
    latitude,
    longitude,
    air_temperature_c,
    pressure_hpa,
    precipitation_mm,
    wind_speed_mps,
    wind_direction_deg,
    wind_gust_mps,
    is_forecast,
    source,
    source_dataset,
    ingested_at
FROM filtered_weather
WHERE (
    %(latest_only)s::boolean = FALSE
    OR valid_time = (
        SELECT MAX(valid_time)
        FROM filtered_weather
    )
)
ORDER BY valid_time DESC, weather_id
LIMIT %(limit)s;
"""


class WeatherQueryError(RuntimeError):
    """Raised when weather conditions cannot be queried."""


def list_weather(
    *,
    source: str | None,
    source_dataset: str | None,
    is_forecast: bool | None,
    start_time: datetime | None,
    end_time: datetime | None,
    minimum_latitude: float | None,
    maximum_latitude: float | None,
    minimum_longitude: float | None,
    maximum_longitude: float | None,
    latest_only: bool,
    limit: int,
) -> list[dict[str, Any]]:
    """Return weather conditions matching supplied filters."""
    parameters = {
        "source": source,
        "source_dataset": source_dataset,
        "is_forecast": is_forecast,
        "start_time": start_time,
        "end_time": end_time,
        "minimum_latitude": minimum_latitude,
        "maximum_latitude": maximum_latitude,
        "minimum_longitude": minimum_longitude,
        "maximum_longitude": maximum_longitude,
        "latest_only": latest_only,
        "limit": limit,
    }

    try:
        with connect_to_database(
            prompt_for_password=False,
        ) as connection:
            with connection.cursor(
                row_factory=dict_row,
            ) as cursor:
                cursor.execute(
                    SELECT_WEATHER_SQL,
                    parameters,
                )
                rows = cursor.fetchall()

    except psycopg.Error as exc:
        raise WeatherQueryError(
            "Weather data could not be queried."
        ) from exc

    return [dict(row) for row in rows]