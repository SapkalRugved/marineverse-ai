"""Transform raw OSM data and load valid ports into PostgreSQL."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg

from backend.marine_data.database import connect_to_database
from backend.marine_data.ingestion_runs import (
    IngestionRunError,
    complete_ingestion_run,
    fail_ingestion_run,
    start_ingestion_run,
)
from backend.marine_data.ports.loader import (
    DatabaseLoadError,
    load_port_records,
)
from backend.marine_data.ports.transformer import (
    TransformationError,
    transform_raw_file,
)


PIPELINE = "ports_osm_india"
SOURCE = "openstreetmap"


def parse_arguments() -> argparse.Namespace:
    """Parse the retained Overpass JSON filename."""
    parser = argparse.ArgumentParser(
        description=(
            "Transform retained OSM port data and load it into "
            "PostgreSQL/PostGIS."
        )
    )
    parser.add_argument(
        "raw_file",
        type=Path,
        help="Path to a retained Overpass JSON response.",
    )
    return parser.parse_args()


def main() -> int:
    """Run the audited ports transformation and database load."""
    arguments = parse_arguments()
    started_at = datetime.now(timezone.utc)

    connection = None
    run_id = None
    result = None

    try:
        print("Connecting to PostgreSQL...")
        connection = connect_to_database()

        run_id = start_ingestion_run(
            connection,
            pipeline=PIPELINE,
            source=SOURCE,
            started_at=started_at,
        )

        # Preserve the running audit row before processing begins.
        connection.commit()
        print(f"Ingestion run started: {run_id}")

        result = transform_raw_file(arguments.raw_file)

        print(f"Source elements read: {result.source_elements_read}")
        print(f"Valid records prepared: {len(result.records)}")
        print(f"Rejected records: {result.rejected_records}")
        print(f"Duplicates removed: {result.duplicates_removed}")

        rows_processed = load_port_records(
            connection,
            result.records,
        )

        complete_ingestion_run(
            connection,
            run_id=run_id,
            records_read=result.source_elements_read,
            records_written=rows_processed,
        )

        # The port upsert and successful audit update commit together.
        connection.commit()

        print("PostgreSQL ports load completed successfully.")
        print(f"Rows processed by upsert: {rows_processed}")
        print(f"Ingestion run completed: {run_id}")
        return 0

    except (
        TransformationError,
        DatabaseLoadError,
        IngestionRunError,
        psycopg.Error,
    ) as exc:
        if connection is not None:
            try:
                connection.rollback()

                if run_id is not None:
                    records_read = (
                        result.source_elements_read
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
                    f"ERROR: Could not record failed ingestion: "
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