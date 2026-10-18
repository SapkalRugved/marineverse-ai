"""Database queries and calculations for data freshness."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import psycopg
from psycopg.rows import dict_row

from backend.marine_data.database import connect_to_database


FRESHNESS_THRESHOLDS_SECONDS = {
    "ports": 30 * 24 * 60 * 60,
    "weather": 30 * 60,
    "ocean": 9 * 60 * 60,
    "ais": 30 * 60,
}

SELECT_FRESHNESS_SQL = """
SELECT *
FROM (
    SELECT
        'ports'::text AS dataset,
        NULL::timestamptz AS latest_valid_time,
        MAX(updated_at) AS latest_ingested_at,
        (
            SELECT MAX(completed_at)
            FROM ingestion_runs
            WHERE pipeline = 'ports_osm_india'
              AND status = 'success'
        ) AS last_successful_run_at
    FROM ports

    UNION ALL

    SELECT
        'ais'::text AS dataset,
        MAX(observed_at) AS latest_valid_time,
        MAX(ingested_at) AS latest_ingested_at,
        (
            SELECT MAX(completed_at)
            FROM ingestion_runs
            WHERE pipeline = 'aisstream_india'
              AND status = 'success'
        ) AS last_successful_run_at
    FROM vessel_positions
    WHERE source = 'aisstream'

    UNION ALL

    SELECT
        'weather'::text AS dataset,
        MAX(valid_time) AS latest_valid_time,
        MAX(ingested_at) AS latest_ingested_at,
        (
            SELECT MAX(completed_at)
            FROM ingestion_runs
            WHERE pipeline = 'weather_open_meteo_ports'
              AND status = 'success'
        ) AS last_successful_run_at
    FROM weather_conditions

    UNION ALL

    SELECT
        'ocean'::text AS dataset,
        MAX(valid_time) AS latest_valid_time,
        MAX(ingested_at) AS latest_ingested_at,
        (
            SELECT MAX(completed_at)
            FROM ingestion_runs
            WHERE pipeline = 'ocean_copernicus_india'
              AND status = 'success'
        ) AS last_successful_run_at
    FROM ocean_conditions
) AS freshness
ORDER BY dataset;
"""


class FreshnessQueryError(RuntimeError):
    """Raised when dataset freshness cannot be determined."""


def calculate_dataset_freshness(
    row: dict[str, Any],
    checked_at: datetime,
) -> dict[str, Any]:
    """Calculate freshness status for one dataset."""
    dataset = row["dataset"]
    maximum_age_seconds = (
        FRESHNESS_THRESHOLDS_SECONDS[dataset]
    )

    reference_time = (
        row.get("latest_valid_time")
        or row.get("latest_ingested_at")
        or row.get("last_successful_run_at")
    )

    if reference_time is None:
        age_seconds = None
        freshness_status = "missing"
    else:
        age_seconds = max(
            0.0,
            (checked_at - reference_time).total_seconds(),
        )
        freshness_status = (
            "fresh"
            if age_seconds <= maximum_age_seconds
            else "stale"
        )

    return {
        "dataset": dataset,
        "status": freshness_status,
        "latest_valid_time": row.get(
            "latest_valid_time"
        ),
        "latest_ingested_at": row.get(
            "latest_ingested_at"
        ),
        "last_successful_run_at": row.get(
            "last_successful_run_at"
        ),
        "age_seconds": age_seconds,
        "maximum_age_seconds": maximum_age_seconds,
    }


def build_freshness_report(
    rows: list[dict[str, Any]],
    checked_at: datetime,
) -> dict[str, Any]:
    """Build the complete freshness response."""
    datasets = [
        calculate_dataset_freshness(
            row,
            checked_at,
        )
        for row in rows
    ]

    statuses = {
        dataset["status"]
        for dataset in datasets
    }

    if "missing" in statuses:
        overall_status = "missing"
    elif "stale" in statuses:
        overall_status = "stale"
    else:
        overall_status = "fresh"

    return {
        "status": overall_status,
        "checked_at": checked_at,
        "datasets": datasets,
    }


def get_data_freshness() -> dict[str, Any]:
    """Query timestamps and calculate dataset freshness."""
    try:
        with connect_to_database(
            prompt_for_password=False,
        ) as connection:
            with connection.cursor(
                row_factory=dict_row,
            ) as cursor:
                cursor.execute(SELECT_FRESHNESS_SQL)
                rows = cursor.fetchall()

    except psycopg.Error as exc:
        raise FreshnessQueryError(
            "Data freshness could not be queried."
        ) from exc

    checked_at = datetime.now(timezone.utc)

    return build_freshness_report(
        [dict(row) for row in rows],
        checked_at,
    )