"""Load validated Copernicus ocean records into PostgreSQL/PostGIS."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from psycopg import Connection

from backend.marine_data.ocean.transformer import OceanRecord


UPDATE_OCEAN_SQL = """
UPDATE ocean_conditions
SET
    location = ST_SetSRID(
        ST_MakePoint(%(longitude)s, %(latitude)s),
        4326
    )::geography,
    current_u_mps = %(current_u_mps)s,
    current_v_mps = %(current_v_mps)s,
    current_speed_mps = %(current_speed_mps)s,
    current_direction_deg = %(current_direction_deg)s,
    sea_surface_temperature_c = %(sea_surface_temperature_c)s,
    wave_height_m = %(wave_height_m)s,
    wave_direction_deg = %(wave_direction_deg)s,
    wave_period_s = %(wave_period_s)s,
    ingested_at = %(ingested_at)s
WHERE source = %(source)s
  AND source_dataset = %(source_dataset)s
  AND valid_time = %(valid_time)s
  AND latitude = %(latitude)s
  AND longitude = %(longitude)s
  AND depth_m = %(depth_m)s
  AND is_forecast = %(is_forecast)s
RETURNING ocean_id;
"""

INSERT_OCEAN_SQL = """
INSERT INTO ocean_conditions (
    valid_time,
    latitude,
    longitude,
    location,
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
)
VALUES (
    %(valid_time)s,
    %(latitude)s,
    %(longitude)s,
    ST_SetSRID(
        ST_MakePoint(%(longitude)s, %(latitude)s),
        4326
    )::geography,
    %(depth_m)s,
    %(current_u_mps)s,
    %(current_v_mps)s,
    %(current_speed_mps)s,
    %(current_direction_deg)s,
    %(sea_surface_temperature_c)s,
    %(wave_height_m)s,
    %(wave_direction_deg)s,
    %(wave_period_s)s,
    %(is_forecast)s,
    %(source)s,
    %(source_dataset)s,
    %(ingested_at)s
)
RETURNING ocean_id;
"""


class OceanDatabaseLoadError(RuntimeError):
    """Raised when validated ocean records cannot be loaded."""


def record_to_parameters(
    record: OceanRecord,
) -> dict[str, Any]:
    """Convert one ocean record into SQL parameters."""
    return {
        "valid_time": record.valid_time,
        "latitude": record.latitude,
        "longitude": record.longitude,
        "depth_m": record.depth_m,
        "current_u_mps": record.current_u_mps,
        "current_v_mps": record.current_v_mps,
        "current_speed_mps": record.current_speed_mps,
        "current_direction_deg": record.current_direction_deg,
        "sea_surface_temperature_c": (
            record.sea_surface_temperature_c
        ),
        "wave_height_m": record.wave_height_m,
        "wave_direction_deg": record.wave_direction_deg,
        "wave_period_s": record.wave_period_s,
        "is_forecast": record.is_forecast,
        "source": record.source,
        "source_dataset": record.source_dataset,
        "ingested_at": record.ingested_at,
    }


def load_ocean_records(
    connection: Connection,
    records: Sequence[OceanRecord],
) -> int:
    """Update or insert validated ocean records."""
    if not records:
        raise OceanDatabaseLoadError(
            "No validated ocean records to load."
        )

    with connection.cursor() as cursor:
        for record in records:
            parameters = record_to_parameters(record)

            cursor.execute(UPDATE_OCEAN_SQL, parameters)
            existing_row = cursor.fetchone()

            if existing_row is None:
                cursor.execute(INSERT_OCEAN_SQL, parameters)

                if cursor.fetchone() is None:
                    raise OceanDatabaseLoadError(
                        "Ocean record was not inserted."
                    )

    return len(records)