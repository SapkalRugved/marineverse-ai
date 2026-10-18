"""Transform and load a retained AISStream capture."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg

from backend.marine_data.ais.loader import (
    AisDatabaseLoadError,
    load_ais_records,
)
from backend.marine_data.ais.transformer import (
    AisTransformationError,
    transform_capture,
)
from backend.marine_data.database import connect_to_database
from backend.marine_data.ingestion_runs import (
    IngestionRunError,
    complete_ingestion_run,
    fail_ingestion_run,
    start_ingestion_run,
)


PIPELINE = "aisstream_india"
SOURCE = "aisstream"


class AisCaptureReadError(RuntimeError):
    """Raised when a retained AIS capture cannot be read."""


def parse_arguments() -> argparse.Namespace:
    """Parse the retained AISStream capture filename."""
    parser = argparse.ArgumentParser(
        description=(
            "Transform a retained AISStream capture and load "
            "vessels and positions into PostgreSQL/PostGIS."
        )
    )
    parser.add_argument(
        "capture",
        type=Path,
        help="Path to a retained AISStream capture JSON file.",
    )
    return parser.parse_args()


def read_capture(path: Path) -> Any:
    """Read a retained UTF-8 AISStream JSON capture."""
    try:
        with path.open(
            "r",
            encoding="utf-8",
        ) as capture_file:
            return json.load(capture_file)

    except OSError as exc:
        raise AisCaptureReadError(
            f"Could not read AIS capture: {path}"
        ) from exc
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise AisCaptureReadError(
            f"AIS capture is not valid UTF-8 JSON: {path}"
        ) from exc


def main() -> int:
    """Run the audited AIS transformation and database load."""
    arguments = parse_arguments()
    started_at = datetime.now(timezone.utc)

    connection = None
    run_id = None
    transformation_result = None

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

        payload = read_capture(arguments.capture)
        transformation_result = transform_capture(
            payload,
            ingested_at=started_at,
        )

        print(
            "Source AIS events read: "
            f"{transformation_result.source_events_read}"
        )
        print(
            "Vessel records prepared: "
            f"{len(transformation_result.vessel_records)}"
        )
        print(
            "Position records prepared: "
            f"{len(transformation_result.position_records)}"
        )
        print(
            "Rejected events: "
            f"{transformation_result.rejected_events}"
        )
        print(
            "Ignored control events: "
            f"{transformation_result.ignored_events}"
        )
        print(
            "Duplicate positions removed: "
            f"{transformation_result.duplicates_removed}"
        )

        load_result = load_ais_records(
            connection,
            transformation_result.vessel_records,
            transformation_result.position_records,
        )

        complete_ingestion_run(
            connection,
            run_id=run_id,
            records_read=(
                transformation_result.source_events_read
            ),
            records_written=load_result.rows_written,
        )
        connection.commit()

        print("AISStream load completed successfully.")
        print(
            "Vessels processed: "
            f"{load_result.vessels_processed}"
        )
        print(
            "Positions received: "
            f"{load_result.positions_received}"
        )
        print(
            "New positions inserted: "
            f"{load_result.positions_inserted}"
        )
        print(
            "Database rows written: "
            f"{load_result.rows_written}"
        )
        print(f"Ingestion run completed: {run_id}")
        return 0

    except (
        AisCaptureReadError,
        AisTransformationError,
        AisDatabaseLoadError,
        IngestionRunError,
        psycopg.Error,
    ) as exc:
        if connection is not None:
            try:
                connection.rollback()

                if run_id is not None:
                    records_read = (
                        transformation_result.source_events_read
                        if transformation_result is not None
                        else 0
                    )

                    fail_ingestion_run(
                        connection,
                        run_id=run_id,
                        records_read=records_read,
                        error_message=str(exc),
                    )
                    connection.commit()

            except (
                psycopg.Error,
                IngestionRunError,
            ) as audit_exc:
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