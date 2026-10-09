"""Bulk-load validated Copernicus ocean records into PostGIS."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from psycopg import Connection

from backend.marine_data.ocean.transformer import OceanRecord


CREATE_STAGE_SQL = """
CREATE TEMP TABLE ocean_conditions_stage (
    valid_time timestamp with time zone NOT NULL,
    latitude double precision NOT NULL,
    longitude double precision NOT NULL,
    depth_m real NOT NULL,
    current_u_mps real NOT NULL,
    current_v_mps real NOT NULL,
    current_speed_mps real NOT NULL,
    current_direction_deg real NOT NULL,
    sea_surface_temperature_c real NOT NULL,
    wave_height_m real NOT NULL,
    wave_direction_deg real NOT NULL,
    wave_period_s real NOT NULL,
    is_forecast boolean NOT NULL,
    source character varying(50) NOT NULL,
    source_dataset character varying(150) NOT NULL,
    ingested_at timestamp with time zone NOT NULL,
    PRIMARY KEY (
        source,
        source_dataset,
        valid_time,
        latitude,
        longitude,
        depth_m,
        is_forecast
    )
) ON COMMIT DROP;
"""

COPY_STAGE_SQL = """
COPY ocean_conditions_stage (
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
)
FROM STDIN;
"""

UPDATE_OCEAN_SQL = """
UPDATE ocean_conditions AS target
SET
    location = ST_SetSRID(
        ST_MakePoint(stage.longitude, stage.latitude),
        4326
    )::geography,
    current_u_mps = stage.current_u_mps,
    current_v_mps = stage.current_v_mps,
    current_speed_mps = stage.current_speed_mps,
    current_direction_deg = stage.current_direction_deg,
    sea_surface_temperature_c =
        stage.sea_surface_temperature_c,
    wave_height_m = stage.wave_height_m,
    wave_direction_deg = stage.wave_direction_deg,
    wave_period_s = stage.wave_period_s,
    ingested_at = stage.ingested_at
FROM ocean_conditions_stage AS stage
WHERE target.source = stage.source
  AND target.source_dataset = stage.source_dataset
  AND target.valid_time = stage.valid_time
  AND target.latitude = stage.latitude
  AND target.longitude = stage.longitude
  AND target.depth_m = stage.depth_m
  AND target.is_forecast = stage.is_forecast;
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
SELECT
    stage.valid_time,
    stage.latitude,
    stage.longitude,
    ST_SetSRID(
        ST_MakePoint(stage.longitude, stage.latitude),
        4326
    )::geography,
    stage.depth_m,
    stage.current_u_mps,
    stage.current_v_mps,
    stage.current_speed_mps,
    stage.current_direction_deg,
    stage.sea_surface_temperature_c,
    stage.wave_height_m,
    stage.wave_direction_deg,
    stage.wave_period_s,
    stage.is_forecast,
    stage.source,
    stage.source_dataset,
    stage.ingested_at
FROM ocean_conditions_stage AS stage
WHERE NOT EXISTS (
    SELECT 1
    FROM ocean_conditions AS target
    WHERE target.source = stage.source
      AND target.source_dataset = stage.source_dataset
      AND target.valid_time = stage.valid_time
      AND target.latitude = stage.latitude
      AND target.longitude = stage.longitude
      AND target.depth_m = stage.depth_m
      AND target.is_forecast = stage.is_forecast
);
"""


class OceanDatabaseLoadError(RuntimeError):
    """Raised when validated ocean records cannot be loaded."""


def record_to_row(record: OceanRecord) -> tuple[Any, ...]:
    """Convert one ocean record into a PostgreSQL COPY row."""
    return (
        record.valid_time,
        record.latitude,
        record.longitude,
        record.depth_m,
        record.current_u_mps,
        record.current_v_mps,
        record.current_speed_mps,
        record.current_direction_deg,
        record.sea_surface_temperature_c,
        record.wave_height_m,
        record.wave_direction_deg,
        record.wave_period_s,
        record.is_forecast,
        record.source,
        record.source_dataset,
        record.ingested_at,
    )


def load_ocean_records(
    connection: Connection,
    records: Sequence[OceanRecord],
) -> int:
    """Bulk update or insert validated ocean records."""
    if not records:
        raise OceanDatabaseLoadError(
            "No validated ocean records to load."
        )

    with connection.cursor() as cursor:
        cursor.execute(CREATE_STAGE_SQL)

        with cursor.copy(COPY_STAGE_SQL) as copy:
            for record in records:
                copy.write_row(record_to_row(record))

        cursor.execute(UPDATE_OCEAN_SQL)
        cursor.execute(INSERT_OCEAN_SQL)

    return len(records)