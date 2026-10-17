"""Database queries for port API endpoints."""

from __future__ import annotations

from typing import Any

import psycopg
from psycopg.rows import dict_row

from backend.marine_data.database import connect_to_database


SELECT_PORTS_SQL = """
SELECT
    port_id,
    source_id,
    name,
    country,
    port_type,
    latitude,
    longitude,
    source,
    updated_at
FROM ports
WHERE (
    %(port_type)s::text IS NULL
    OR port_type = %(port_type)s::text
)
AND (
    %(name)s::text IS NULL
    OR name ILIKE '%%' || %(name)s::text || '%%'
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
ORDER BY name NULLS LAST, port_id
LIMIT %(limit)s;
"""


class PortsQueryError(RuntimeError):
    """Raised when ports cannot be queried."""


def list_ports(
    *,
    port_type: str | None,
    name: str | None,
    minimum_latitude: float | None,
    maximum_latitude: float | None,
    minimum_longitude: float | None,
    maximum_longitude: float | None,
    limit: int,
) -> list[dict[str, Any]]:
    """Return ports matching the supplied filters."""
    parameters = {
        "port_type": port_type,
        "name": name,
        "minimum_latitude": minimum_latitude,
        "maximum_latitude": maximum_latitude,
        "minimum_longitude": minimum_longitude,
        "maximum_longitude": maximum_longitude,
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
                    SELECT_PORTS_SQL,
                    parameters,
                )
                rows = cursor.fetchall()

    except psycopg.Error as exc:
        raise PortsQueryError(
            "Port data could not be queried."
        ) from exc

    return [dict(row) for row in rows]
