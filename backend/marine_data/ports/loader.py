"""Load validated port records into PostgreSQL/PostGIS."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from psycopg import Connection

from backend.marine_data.ports.transformer import PortRecord


UPSERT_PORT_SQL = """
INSERT INTO ports (
    source_id,
    name,
    country,
    port_type,
    latitude,
    longitude,
    location,
    source,
    updated_at
)
VALUES (
    %(source_id)s,
    %(name)s,
    %(country)s,
    %(port_type)s,
    %(latitude)s,
    %(longitude)s,
    ST_SetSRID(
        ST_MakePoint(%(longitude)s, %(latitude)s),
        4326
    )::geography,
    %(source)s,
    %(updated_at)s
)
ON CONFLICT (source, source_id)
DO UPDATE SET
    name = EXCLUDED.name,
    country = EXCLUDED.country,
    port_type = EXCLUDED.port_type,
    latitude = EXCLUDED.latitude,
    longitude = EXCLUDED.longitude,
    location = EXCLUDED.location,
    updated_at = EXCLUDED.updated_at;
"""


class DatabaseLoadError(RuntimeError):
    """Raised when validated records cannot be loaded."""


def record_to_parameters(record: PortRecord) -> dict[str, Any]:
    """Convert one PortRecord into parameterized SQL values."""
    return {
        "source_id": record.source_id,
        "name": record.name,
        "country": record.country,
        "port_type": record.port_type,
        "latitude": record.latitude,
        "longitude": record.longitude,
        "source": record.source,
        "updated_at": record.updated_at,
    }


def load_port_records(
    connection: Connection,
    records: Sequence[PortRecord],
) -> int:
    """Insert or update validated ports in the active transaction."""
    if not records:
        raise DatabaseLoadError("No validated port records to load.")

    parameters = [
        record_to_parameters(record)
        for record in records
    ]

    with connection.cursor() as cursor:
        cursor.executemany(UPSERT_PORT_SQL, parameters)

    return len(parameters)