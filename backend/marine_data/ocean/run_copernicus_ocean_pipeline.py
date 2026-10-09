"""Run the complete audited Copernicus ocean ETL pipeline."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

import psycopg

from backend.marine_data.database import connect_to_database
from backend.marine_data.ingestion_runs import (
    IngestionRunError,
    complete_ingestion_run,
    fail_ingestion_run,
    start_ingestion_run,
)
from backend.marine_data.ocean.loader import (
    OceanDatabaseLoadError,
    load_ocean_records,
)
from backend.marine_data.ocean.retrieve_copernicus_ocean import (
    DEFAULT_MAX_LATITUDE,
    DEFAULT_MAX_LONGITUDE,
    DEFAULT_MIN_LATITUDE,
    DEFAULT_MIN_LONGITUDE,
    PHYSICS_DATASET,
    PHYSICS_VARIABLES,
    RAW_DIRECTORY,
    SOURCE,
    WAVE_DATASET,
    WAVE_VARIABLES,
    format_timestamp,
    parse_valid_time,
    retain_manifest,
    retrieve_subset,
    select_default_valid_time,
    validate_bounds,
)
from backend.marine_data.ocean.transformer import (
    OceanTransformationError,
    transform_raw_manifest,
)


PIPELINE = "ocean_copernicus_india"


def parse_arguments() -> argparse.Namespace:
    """Parse ocean pipeline options."""
    parser = argparse.ArgumentParser(
        description=(
            "Retrieve, transform and load near-real-time Copernicus "
            "ocean conditions."
        )
    )
    parser.add_argument(
        "--valid-time",
        type=parse_valid_time,
        help=(
            "UTC model time aligned to three hours. Defaults to the "
            "previous complete three-hour interval."
        ),
    )
    parser.add_argument(
        "--minimum-longitude",
        type=float,
        default=DEFAULT_MIN_LONGITUDE,
    )
    parser.add_argument(
        "--maximum-longitude",
        type=float,
        default=DEFAULT_MAX_LONGITUDE,
    )
    parser.add_argument(
        "--minimum-latitude",
        type=float,
        default=DEFAULT_MIN_LATITUDE,
    )
    parser.add_argument(
        "--maximum-latitude",
        type=float,
        default=DEFAULT_MAX_LATITUDE,
    )
    return parser.parse_args()


def main() -> int:
    """Run retrieval, transformation, loading and auditing."""
    arguments = parse_arguments()
    started_at = datetime.now(timezone.utc)

    connection = None
    run_id = None
    result = None

    try:
        validate_bounds(
            arguments.minimum_longitude,
            arguments.maximum_longitude,
            arguments.minimum_latitude,
            arguments.maximum_latitude,
        )

        valid_time = (
            arguments.valid_time
            if arguments.valid_time is not None
            else select_default_valid_time()
        )
        timestamp = format_timestamp(valid_time)
        retrieved_at = datetime.now(timezone.utc)

        RAW_DIRECTORY.mkdir(parents=True, exist_ok=True)

        physics_path = (
            RAW_DIRECTORY
            / f"copernicus_phy_india_{timestamp}.nc"
        )
        wave_path = (
            RAW_DIRECTORY
            / f"copernicus_wav_india_{timestamp}.nc"
        )

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
        print(f"Selected model time: {valid_time.isoformat()}")

        print("Retrieving Copernicus physics subset...")
        retrieve_subset(
            dataset_id=PHYSICS_DATASET,
            variables=PHYSICS_VARIABLES,
            output_path=physics_path,
            valid_time=valid_time,
            minimum_longitude=arguments.minimum_longitude,
            maximum_longitude=arguments.maximum_longitude,
            minimum_latitude=arguments.minimum_latitude,
            maximum_latitude=arguments.maximum_latitude,
        )

        print("Retrieving Copernicus wave subset...")
        retrieve_subset(
            dataset_id=WAVE_DATASET,
            variables=WAVE_VARIABLES,
            output_path=wave_path,
            valid_time=valid_time,
            minimum_longitude=arguments.minimum_longitude,
            maximum_longitude=arguments.maximum_longitude,
            minimum_latitude=arguments.minimum_latitude,
            maximum_latitude=arguments.maximum_latitude,
        )

        manifest_path = retain_manifest(
            physics_path=physics_path,
            wave_path=wave_path,
            valid_time=valid_time,
            retrieved_at=retrieved_at,
            minimum_longitude=arguments.minimum_longitude,
            maximum_longitude=arguments.maximum_longitude,
            minimum_latitude=arguments.minimum_latitude,
            maximum_latitude=arguments.maximum_latitude,
        )

        print(f"Raw manifest retained at: {manifest_path}")

        result = transform_raw_manifest(manifest_path)

        print(f"Source grid cells: {result.source_grid_cells}")
        print(f"Valid records prepared: {len(result.records)}")
        print(f"Rejected records: {result.rejected_records}")

        rows_processed = load_ocean_records(
            connection,
            result.records,
        )

        complete_ingestion_run(
            connection,
            run_id=run_id,
            records_read=result.source_grid_cells,
            records_written=rows_processed,
        )
        connection.commit()

        print("Copernicus ocean ETL completed successfully.")
        print(f"Rows processed: {rows_processed}")
        print(f"Ingestion run completed: {run_id}")
        return 0

    except Exception as exc:
        if connection is not None:
            try:
                connection.rollback()

                if run_id is not None:
                    records_read = (
                        result.source_grid_cells
                        if result is not None
                        else 0
                    )

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

        expected_error = isinstance(
            exc,
            (
                ValueError,
                OSError,
                OceanTransformationError,
                OceanDatabaseLoadError,
                IngestionRunError,
                psycopg.Error,
            ),
        )

        prefix = "ERROR" if expected_error else "UNEXPECTED ERROR"
        print(f"{prefix}: {exc}", file=sys.stderr)
        return 1

    finally:
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    raise SystemExit(main())