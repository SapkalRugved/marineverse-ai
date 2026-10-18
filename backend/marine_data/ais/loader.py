"""Bulk-load validated AIS records into PostgreSQL/PostGIS."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from psycopg import Connection

from backend.marine_data.ais.transformer import (
    VesselPositionRecord,
    VesselRecord,
)


AIS_LOAD_LOCK_SQL = """
SELECT pg_advisory_xact_lock(
    hashtext('marineverse:ais-load')
);
"""

CREATE_VESSELS_STAGE_SQL = """
CREATE TEMP TABLE ais_vessels_stage (
    mmsi bigint PRIMARY KEY,
    imo bigint,
    name character varying(200),
    ship_type character varying(100),
    length_m real,
    width_m real,
    source character varying(50) NOT NULL,
    updated_at timestamp with time zone NOT NULL
) ON COMMIT DROP;
"""

CREATE_POSITIONS_STAGE_SQL = """
CREATE TEMP TABLE ais_positions_stage (
    mmsi bigint NOT NULL,
    observed_at timestamp with time zone NOT NULL,
    latitude double precision NOT NULL,
    longitude double precision NOT NULL,
    speed_mps real,
    course_deg real,
    heading_deg real,
    navigation_status character varying(50),
    source character varying(50) NOT NULL,
    ingested_at timestamp with time zone NOT NULL,
    PRIMARY KEY (
        mmsi,
        observed_at,
        latitude,
        longitude,
        source
    )
) ON COMMIT DROP;
"""

COPY_VESSELS_STAGE_SQL = """
COPY ais_vessels_stage (
    mmsi,
    imo,
    name,
    ship_type,
    length_m,
    width_m,
    source,
    updated_at
)
FROM STDIN;
"""

COPY_POSITIONS_STAGE_SQL = """
COPY ais_positions_stage (
    mmsi,
    observed_at,
    latitude,
    longitude,
    speed_mps,
    course_deg,
    heading_deg,
    navigation_status,
    source,
    ingested_at
)
FROM STDIN;
"""

UPSERT_VESSELS_SQL = """
INSERT INTO vessels (
    mmsi,
    imo,
    name,
    ship_type,
    length_m,
    width_m,
    source,
    updated_at
)
SELECT
    stage.mmsi,
    stage.imo,
    stage.name,
    stage.ship_type,
    stage.length_m,
    stage.width_m,
    stage.source,
    stage.updated_at
FROM ais_vessels_stage AS stage
ON CONFLICT (mmsi)
DO UPDATE SET
    imo = COALESCE(EXCLUDED.imo, vessels.imo),
    name = CASE
        WHEN EXCLUDED.imo IS NOT NULL
          OR EXCLUDED.ship_type IS NOT NULL
          OR EXCLUDED.length_m IS NOT NULL
          OR EXCLUDED.width_m IS NOT NULL
        THEN COALESCE(EXCLUDED.name, vessels.name)
        ELSE COALESCE(vessels.name, EXCLUDED.name)
    END,
    ship_type = COALESCE(
        EXCLUDED.ship_type,
        vessels.ship_type
    ),
    length_m = COALESCE(
        EXCLUDED.length_m,
        vessels.length_m
    ),
    width_m = COALESCE(
        EXCLUDED.width_m,
        vessels.width_m
    ),
    source = EXCLUDED.source,
    updated_at = CASE
        WHEN vessels.updated_at IS NULL
          OR EXCLUDED.updated_at > vessels.updated_at
        THEN EXCLUDED.updated_at
        ELSE vessels.updated_at
    END;
"""

INSERT_POSITIONS_SQL = """
INSERT INTO vessel_positions (
    vessel_id,
    observed_at,
    latitude,
    longitude,
    location,
    speed_mps,
    course_deg,
    heading_deg,
    navigation_status,
    source,
    ingested_at
)
SELECT
    vessel.vessel_id,
    stage.observed_at,
    stage.latitude,
    stage.longitude,
    ST_SetSRID(
        ST_MakePoint(
            stage.longitude,
            stage.latitude
        ),
        4326
    )::geography,
    stage.speed_mps,
    stage.course_deg,
    stage.heading_deg,
    stage.navigation_status,
    stage.source,
    stage.ingested_at
FROM ais_positions_stage AS stage
JOIN vessels AS vessel
  ON vessel.mmsi = stage.mmsi
WHERE NOT EXISTS (
    SELECT 1
    FROM vessel_positions AS existing
    WHERE existing.vessel_id = vessel.vessel_id
      AND existing.observed_at = stage.observed_at
      AND existing.latitude = stage.latitude
      AND existing.longitude = stage.longitude
      AND existing.source = stage.source
);
"""


class AisDatabaseLoadError(RuntimeError):
    """Raised when validated AIS records cannot be loaded."""


@dataclass(frozen=True, slots=True)
class AisLoadResult:
    """Counts produced by one atomic AIS database load."""

    vessels_processed: int
    positions_received: int
    positions_inserted: int

    @property
    def rows_written(self) -> int:
        """Return vessel upserts plus new position inserts."""
        return self.vessels_processed + self.positions_inserted


def vessel_record_to_row(
    record: VesselRecord,
) -> tuple[Any, ...]:
    """Convert a vessel into a PostgreSQL COPY row."""
    return (
        record.mmsi,
        record.imo,
        record.name,
        record.ship_type,
        record.length_m,
        record.width_m,
        record.source,
        record.updated_at,
    )


def position_record_to_row(
    record: VesselPositionRecord,
) -> tuple[Any, ...]:
    """Convert a vessel position into a PostgreSQL COPY row."""
    return (
        record.mmsi,
        record.observed_at,
        record.latitude,
        record.longitude,
        record.speed_mps,
        record.course_deg,
        record.heading_deg,
        record.navigation_status,
        record.source,
        record.ingested_at,
    )


def validate_record_relationships(
    vessel_records: Sequence[VesselRecord],
    position_records: Sequence[VesselPositionRecord],
) -> None:
    """Ensure every staged position has a staged vessel."""
    vessel_mmsis = {
        record.mmsi
        for record in vessel_records
    }
    position_mmsis = {
        record.mmsi
        for record in position_records
    }

    missing_mmsis = position_mmsis - vessel_mmsis

    if missing_mmsis:
        formatted = ", ".join(
            str(mmsi)
            for mmsi in sorted(missing_mmsis)
        )
        raise AisDatabaseLoadError(
            "Positions reference unstaged MMSIs: "
            f"{formatted}"
        )


def load_ais_records(
    connection: Connection,
    vessel_records: Sequence[VesselRecord],
    position_records: Sequence[VesselPositionRecord],
) -> AisLoadResult:
    """Atomically upsert vessels and insert new positions."""
    if not vessel_records:
        raise AisDatabaseLoadError(
            "No validated vessel records to load."
        )

    validate_record_relationships(
        vessel_records,
        position_records,
    )

    with connection.cursor() as cursor:
        cursor.execute(AIS_LOAD_LOCK_SQL)
        cursor.execute(CREATE_VESSELS_STAGE_SQL)
        cursor.execute(CREATE_POSITIONS_STAGE_SQL)

        with cursor.copy(COPY_VESSELS_STAGE_SQL) as copy:
            for record in vessel_records:
                copy.write_row(
                    vessel_record_to_row(record)
                )

        with cursor.copy(COPY_POSITIONS_STAGE_SQL) as copy:
            for record in position_records:
                copy.write_row(
                    position_record_to_row(record)
                )

        cursor.execute(UPSERT_VESSELS_SQL)
        cursor.execute(INSERT_POSITIONS_SQL)
        positions_inserted = cursor.rowcount

    return AisLoadResult(
        vessels_processed=len(vessel_records),
        positions_received=len(position_records),
        positions_inserted=positions_inserted,
    )