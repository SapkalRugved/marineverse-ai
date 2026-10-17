"""Database queries for ocean API endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row

from backend.marine_data.database import connect_to_database


SELECT_OCEAN_SQL = """
WITH filtered_ocean AS (
    SELECT
        ocean_id,
        valid_time,
        latitude,
        longitude,
        depth_m,
        current_u_mps,
        current_v_mps,
        current_speed_mps,
        current_direction_deg,
        sea_surface_temperature_c,
        wave_height_m,
        wave_direction_deg,
        wave_period_s,
        is_forecast,
        source,
        source_dataset,
        ingested_at
    FROM ocean_conditions
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
        %(minimum_depth_m)s::real IS NULL
        OR depth_m >= %(minimum_depth_m)s::real
    )
    AND (
        %(maximum_depth_m)s::real IS NULL
        OR depth_m <= %(maximum_depth_m)s::real
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
    ocean_id,
    valid_time,
    latitude,
    longitude,
    depth_m,
    current_u_mps,
    current_v_mps,
    current_speed_mps,
    current_direction_deg,
    sea_surface_temperature_c,
    wave_height_m,
    wave_direction_deg,
    wave_period_s,
    is_forecast,
    source,
    source_dataset,
    ingested_at
FROM filtered_ocean
WHERE (
    %(latest_only)s::boolean = FALSE
    OR valid_time = (
        SELECT MAX(valid_time)
        FROM filtered_ocean
    )
)
ORDER BY valid_time DESC, latitude, longitude, ocean_id
LIMIT %(limit)s
OFFSET %(offset)s;
"""


class OceanQueryError(RuntimeError):
    """Raised when ocean conditions cannot be queried."""


def list_ocean_conditions(
    *,
    source: str | None,
    source_dataset: str | None,
    is_forecast: bool | None,
    start_time: datetime | None,
    end_time: datetime | None,
    minimum_depth_m: float | None,
    maximum_depth_m: float | None,
    minimum_latitude: float | None,
    maximum_latitude: float | None,
    minimum_longitude: float | None,
    maximum_longitude: float | None,
    latest_only: bool,
    limit: int,
    offset: int,
) -> list[dict[str, Any]]:
    """Return ocean conditions matching supplied filters."""
    parameters = {
        "source": source,
        "source_dataset": source_dataset,
        "is_forecast": is_forecast,
        "start_time": start_time,
        "end_time": end_time,
        "minimum_depth_m": minimum_depth_m,
        "maximum_depth_m": maximum_depth_m,
        "minimum_latitude": minimum_latitude,
        "maximum_latitude": maximum_latitude,
        "minimum_longitude": minimum_longitude,
        "maximum_longitude": maximum_longitude,
        "latest_only": latest_only,
        "limit": limit,
        "offset": offset,
    }

    try:
        with connect_to_database(
            prompt_for_password=False,
        ) as connection:
            with connection.cursor(
                row_factory=dict_row,
            ) as cursor:
                cursor.execute(
                    SELECT_OCEAN_SQL,
                    parameters,
                )
                rows = cursor.fetchall()

    except psycopg.Error as exc:
        raise OceanQueryError(
            "Ocean data could not be queried."
        ) from exc

    return [dict(row) for row in rows]