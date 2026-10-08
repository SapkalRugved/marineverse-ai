"""Run the complete current-weather ETL pipeline."""

from __future__ import annotations

import sys
from datetime import datetime, timezone

import psycopg
import requests

from backend.marine_data.database import connect_to_database
from backend.marine_data.ingestion_runs import (
    IngestionRunError,
    complete_ingestion_run,
    fail_ingestion_run,
    start_ingestion_run,
)
from backend.marine_data.weather.loader import (
    WeatherDatabaseLoadError,
    load_weather_records,
)
from backend.marine_data.weather.retrieve_open_meteo_weather import (
    WeatherRetrievalError,
    read_port_locations_from_connection,
    retain_raw_response,
    retrieve_weather,
)
from backend.marine_data.weather.transformer import (
    WeatherTransformationError,
    transform_raw_file,
)


PIPELINE = "weather_open_meteo_ports"
SOURCE = "open-meteo"


def main() -> int:
    """Retrieve, retain, transform, load, and audit weather."""
    started_at = datetime.now(timezone.utc)

    connection = None
    run_id = None
    records_read = 0

    try:
        print("Connecting to PostgreSQL...")
        connection = connect_to_database()

        run_id = start_ingestion_run(
            connection,
            pipeline=PIPELINE,
            source=SOURCE,
            started_at=started_at,
        )
        connection.commit()

        print(f"Ingestion run started: {run_id}")

        locations = read_port_locations_from_connection(connection)

        # End the read-only database transaction before HTTP work.
        connection.commit()

        print(f"Port locations selected: {len(locations)}")

        raw_records = retrieve_weather(locations)
        records_read = len(raw_records)

        raw_file = retain_raw_response(
            locations,
            raw_records,
        )

        print(f"Raw response retained at: {raw_file}")

        result = transform_raw_file(raw_file)

        print(f"Source records read: {result.source_records_read}")
        print(f"Valid records prepared: {len(result.records)}")
        print(f"Rejected records: {result.rejected_records}")
        print(f"Duplicates removed: {result.duplicates_removed}")

        rows_processed = load_weather_records(
            connection,
            result.records,
        )

        complete_ingestion_run(
            connection,
            run_id=run_id,
            records_read=result.source_records_read,
            records_written=rows_processed,
        )

        connection.commit()

        print("Current-weather ETL completed successfully.")
        print(f"Rows processed: {rows_processed}")
        print(f"Ingestion run completed: {run_id}")
        return 0

    except (
        WeatherRetrievalError,
        WeatherTransformationError,
        WeatherDatabaseLoadError,
        IngestionRunError,
        requests.RequestException,
        psycopg.Error,
        OSError,
        ValueError,
    ) as exc:
        if connection is not None:
            try:
                connection.rollback()

                if run_id is not None:
                    fail_ingestion_run(
                        connection,
                        run_id=run_id,
                        records_read=records_read,
                        error_message=str(exc),
                    )
                    connection.commit()

            except (psycopg.Error, IngestionRunError) as audit_exc:
                print(
                    "ERROR: Could not record failed ingestion: "
                    f"{audit_exc}",
                    file=sys.stderr,
                )

        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    finally:
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    raise SystemExit(main())