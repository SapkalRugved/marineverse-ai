"""Transform and load retained Copernicus ocean data."""

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
from backend.marine_data.ocean.loader import (
    OceanDatabaseLoadError,
    load_ocean_records,
)
from backend.marine_data.ocean.transformer import (
    OceanTransformationError,
    transform_raw_manifest,
)


PIPELINE = "ocean_copernicus_india"
SOURCE = "copernicus-marine"


def parse_arguments() -> argparse.Namespace:
    """Parse the retained Copernicus manifest filename."""
    parser = argparse.ArgumentParser(
        description=(
            "Transform retained Copernicus ocean data and load it "
            "into PostgreSQL/PostGIS."
        )
    )
    parser.add_argument(
        "manifest",
        type=Path,
        help="Path to a retained Copernicus manifest JSON file.",
    )
    return parser.parse_args()


def main() -> int:
    """Run the audited ocean transformation and load."""
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
        connection.commit()

        print(f"Ingestion run started: {run_id}")

        result = transform_raw_manifest(arguments.manifest)

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

        print("Ocean load completed successfully.")
        print(f"Rows processed: {rows_processed}")
        print(f"Ingestion run completed: {run_id}")
        return 0

    except (
        OceanTransformationError,
        OceanDatabaseLoadError,
        IngestionRunError,
        psycopg.Error,
    ) as exc:
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

        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    finally:
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    raise SystemExit(main())