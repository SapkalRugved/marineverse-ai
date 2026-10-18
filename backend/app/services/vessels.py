"""Database queries for AIS vessel API endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row

from backend.marine_data.database import connect_to_database


SELECT_VESSELS_SQL = """
SELECT
    vessel.vessel_id,
    vessel.mmsi,
    vessel.imo,
    vessel.name,
    vessel.ship_type,
    vessel.length_m,
    vessel.width_m,
    vessel.source AS vessel_source,
    vessel.updated_at,
    latest_position.position_id AS latest_position_id,
    latest_position.observed_at AS latest_observed_at,
    latest_position.latitude AS latest_latitude,
    latest_position.longitude AS latest_longitude,
    latest_position.speed_mps AS latest_speed_mps,
    latest_position.course_deg AS latest_course_deg,
    latest_position.heading_deg AS latest_heading_deg,
    latest_position.navigation_status
        AS latest_navigation_status,
    latest_position.source AS latest_position_source,
    latest_position.ingested_at AS latest_ingested_at
FROM vessels AS vessel
LEFT JOIN LATERAL (
    SELECT
        position.position_id,
        position.observed_at,
        position.latitude,
        position.longitude,
        position.speed_mps,
        position.course_deg,
        position.heading_deg,
        position.navigation_status,
        position.source,
        position.ingested_at
    FROM vessel_positions AS position
    WHERE position.vessel_id = vessel.vessel_id
    ORDER BY
        position.observed_at DESC NULLS LAST,
        position.position_id DESC
    LIMIT 1
) AS latest_position
    ON TRUE
WHERE (
    %(mmsi)s::bigint IS NULL
    OR vessel.mmsi = %(mmsi)s::bigint
)
AND (
    %(name)s::text IS NULL
    OR vessel.name ILIKE '%%' || %(name)s::text || '%%'
)
AND (
    %(ship_type)s::text IS NULL
    OR vessel.ship_type = %(ship_type)s::text
)
AND (
    %(source)s::text IS NULL
    OR vessel.source = %(source)s::text
)
AND (
    %(minimum_latitude)s::double precision IS NULL
    OR latest_position.latitude
        >= %(minimum_latitude)s::double precision
)
AND (
    %(maximum_latitude)s::double precision IS NULL
    OR latest_position.latitude
        <= %(maximum_latitude)s::double precision
)
AND (
    %(minimum_longitude)s::double precision IS NULL
    OR latest_position.longitude
        >= %(minimum_longitude)s::double precision
)
AND (
    %(maximum_longitude)s::double precision IS NULL
    OR latest_position.longitude
        <= %(maximum_longitude)s::double precision
)
AND (
    %(observed_after)s::timestamptz IS NULL
    OR latest_position.observed_at
        >= %(observed_after)s::timestamptz
)
ORDER BY
    latest_position.observed_at DESC NULLS LAST,
    vessel.mmsi NULLS LAST,
    vessel.vessel_id
LIMIT %(limit)s;
"""


class VesselsQueryError(RuntimeError):
    """Raised when vessel data cannot be queried."""


def build_vessel_record(
    row: dict[str, Any],
) -> dict[str, Any]:
    """Convert a joined database row into the API structure."""
    latest_position = None

    if row["latest_position_id"] is not None:
        latest_position = {
            "position_id": row["latest_position_id"],
            "observed_at": row["latest_observed_at"],
            "latitude": row["latest_latitude"],
            "longitude": row["latest_longitude"],
            "speed_mps": row["latest_speed_mps"],
            "course_deg": row["latest_course_deg"],
            "heading_deg": row["latest_heading_deg"],
            "navigation_status": (
                row["latest_navigation_status"]
            ),
            "source": row["latest_position_source"],
            "ingested_at": row["latest_ingested_at"],
        }

    return {
        "vessel_id": row["vessel_id"],
        "mmsi": row["mmsi"],
        "imo": row["imo"],
        "name": row["name"],
        "ship_type": row["ship_type"],
        "length_m": row["length_m"],
        "width_m": row["width_m"],
        "source": row["vessel_source"],
        "updated_at": row["updated_at"],
        "latest_position": latest_position,
    }


def list_vessels(
    *,
    mmsi: int | None,
    name: str | None,
    ship_type: str | None,
    source: str | None,
    minimum_latitude: float | None,
    maximum_latitude: float | None,
    minimum_longitude: float | None,
    maximum_longitude: float | None,
    observed_after: datetime | None,
    limit: int,
) -> list[dict[str, Any]]:
    """Return vessels and their newest stored positions."""
    parameters = {
        "mmsi": mmsi,
        "name": name,
        "ship_type": ship_type,
        "source": source,
        "minimum_latitude": minimum_latitude,
        "maximum_latitude": maximum_latitude,
        "minimum_longitude": minimum_longitude,
        "maximum_longitude": maximum_longitude,
        "observed_after": observed_after,
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
                    SELECT_VESSELS_SQL,
                    parameters,
                )
                rows = cursor.fetchall()

    except psycopg.Error as exc:
        raise VesselsQueryError(
            "Vessel data could not be queried."
        ) from exc

    return [
        build_vessel_record(dict(row))
        for row in rows
    ]
