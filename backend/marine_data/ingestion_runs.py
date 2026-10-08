"""Track ETL pipeline executions in the ingestion_runs table."""

from __future__ import annotations

from datetime import datetime, timezone

from psycopg import Connection


START_RUN_SQL = """
INSERT INTO ingestion_runs (
    pipeline,
    source,
    started_at,
    status,
    records_read,
    records_written,
    error_message
)
VALUES (
    %(pipeline)s,
    %(source)s,
    %(started_at)s,
    'running',
    0,
    0,
    NULL
)
RETURNING run_id;
"""

COMPLETE_RUN_SQL = """
UPDATE ingestion_runs
SET
    completed_at = %(completed_at)s,
    status = 'success',
    records_read = %(records_read)s,
    records_written = %(records_written)s,
    error_message = NULL
WHERE run_id = %(run_id)s
RETURNING run_id;
"""

FAIL_RUN_SQL = """
UPDATE ingestion_runs
SET
    completed_at = %(completed_at)s,
    status = 'failed',
    records_read = %(records_read)s,
    records_written = 0,
    error_message = %(error_message)s
WHERE run_id = %(run_id)s
RETURNING run_id;
"""


class IngestionRunError(RuntimeError):
    """Raised when an ingestion audit record cannot be updated."""


def utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


def start_ingestion_run(
    connection: Connection,
    pipeline: str,
    source: str,
    started_at: datetime | None = None,
) -> int:
    """Create a running ingestion record and return its run ID."""
    parameters = {
        "pipeline": pipeline,
        "source": source,
        "started_at": started_at or utc_now(),
    }

    with connection.cursor() as cursor:
        cursor.execute(START_RUN_SQL, parameters)
        row = cursor.fetchone()

    if row is None:
        raise IngestionRunError("Ingestion run was not created.")

    return int(row[0])


def complete_ingestion_run(
    connection: Connection,
    run_id: int,
    records_read: int,
    records_written: int,
    completed_at: datetime | None = None,
) -> None:
    """Mark an ingestion run as successful."""
    parameters = {
        "run_id": run_id,
        "completed_at": completed_at or utc_now(),
        "records_read": records_read,
        "records_written": records_written,
    }

    with connection.cursor() as cursor:
        cursor.execute(COMPLETE_RUN_SQL, parameters)
        row = cursor.fetchone()

    if row is None:
        raise IngestionRunError(
            f"Ingestion run {run_id} was not found."
        )


def fail_ingestion_run(
    connection: Connection,
    run_id: int,
    records_read: int,
    error_message: str,
    completed_at: datetime | None = None,
) -> None:
    """Mark an ingestion run as failed."""
    parameters = {
        "run_id": run_id,
        "completed_at": completed_at or utc_now(),
        "records_read": records_read,
        "error_message": error_message,
    }

    with connection.cursor() as cursor:
        cursor.execute(FAIL_RUN_SQL, parameters)
        row = cursor.fetchone()

    if row is None:
        raise IngestionRunError(
            f"Ingestion run {run_id} was not found."
        )