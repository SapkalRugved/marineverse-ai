"""Run the complete live AISStream ingestion pipeline."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

import psycopg
from dotenv import load_dotenv
from websockets.exceptions import WebSocketException

from backend.marine_data.ais.load_aisstream_capture import (
    AisCaptureReadError,
    read_capture,
)
from backend.marine_data.ais.loader import (
    AisDatabaseLoadError,
    load_ais_records,
)
from backend.marine_data.ais.probe_aisstream import (
    PROJECT_ROOT,
    AisProbeError,
    capture_events,
    positive_integer,
    retain_capture,
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


class AisPipelineError(RuntimeError):
    """Raised when the complete live AIS pipeline cannot run."""


def parse_arguments() -> argparse.Namespace:
    """Parse bounded live-capture settings."""
    parser = argparse.ArgumentParser(
        description=(
            "Capture live Indian-water AIS events and load them "
            "into PostgreSQL/PostGIS."
        )
    )
    parser.add_argument(
        "--duration-seconds",
        type=positive_integer,
        default=300,
        help="Maximum live capture duration. Default: 300.",
    )
    parser.add_argument(
        "--max-events",
        type=positive_integer,
        default=2000,
        help="Maximum events retained per run. Default: 2000.",
    )
    return parser.parse_args()


def count_ais_data_events(
    events: list[dict],
) -> int:
    """Count non-control events for failure auditing."""
    return sum(
        1
        for captured_event in events
        if captured_event.get("event", {}).get("MessageType")
        != "SubscriptionConfirmation"
    )


def main() -> int:
    """Run one audited live AIS capture and load."""
    arguments = parse_arguments()
    started_at = datetime.now(timezone.utc)

    connection = None
    run_id = None
    captured_events: list[dict] = []
    transformation_result = None

    try:
        load_dotenv(PROJECT_ROOT / ".env")
        api_key = os.getenv(
            "AISSTREAM_API_KEY",
            "",
        ).strip()

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

        if not api_key:
            raise AisPipelineError(
                "AISSTREAM_API_KEY is not configured."
            )

        print(
            "Capturing live AISStream events for up to "
            f"{arguments.duration_seconds} seconds..."
        )

        (
            captured_events,
            capture_started_at,
            capture_completed_at,
        ) = capture_events(
            api_key=api_key,
            duration_seconds=arguments.duration_seconds,
            max_events=arguments.max_events,
        )

        capture_path = retain_capture(
            started_at=capture_started_at,
            completed_at=capture_completed_at,
            duration_seconds=arguments.duration_seconds,
            events=captured_events,
        )

        print(f"Raw AIS capture retained at: {capture_path}")

        data_event_count = count_ais_data_events(
            captured_events
        )

        if data_event_count == 0:
            complete_ingestion_run(
                connection,
                run_id=run_id,
                records_read=0,
                records_written=0,
            )
            connection.commit()

            print(
                "AISStream subscription succeeded, but no "
                "vessel broadcasts arrived during this window."
            )
            print("No database records were written.")
            print(f"Ingestion run completed: {run_id}")
            return 0

        payload = read_capture(capture_path)

        transformation_result = transform_capture(
            payload,
            ingested_at=capture_completed_at,
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

        print("Live AISStream pipeline completed successfully.")
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
        AisPipelineError,
        AisProbeError,
        AisCaptureReadError,
        AisTransformationError,
        AisDatabaseLoadError,
        IngestionRunError,
        WebSocketException,
        psycopg.Error,
        OSError,
        UnicodeError,
        ValueError,
    ) as exc:
        if connection is not None:
            try:
                connection.rollback()

                if run_id is not None:
                    if transformation_result is not None:
                        records_read = (
                            transformation_result
                            .source_events_read
                        )
                    else:
                        records_read = count_ais_data_events(
                            captured_events
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
