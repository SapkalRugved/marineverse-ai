"""Run scheduled MarineVerse pipelines with overlap protection."""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg import Connection

from backend.marine_data.database import connect_to_database


PROJECT_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class PipelineDefinition:
    """Configuration for one scheduled pipeline."""

    name: str
    module: str
    advisory_lock_id: int


PIPELINES = {
    "weather": PipelineDefinition(
        name="weather",
        module=(
            "backend.marine_data.weather."
            "run_open_meteo_weather_pipeline"
        ),
        advisory_lock_id=17001,
    ),
    "ocean": PipelineDefinition(
        name="ocean",
        module=(
            "backend.marine_data.ocean."
            "run_copernicus_ocean_pipeline"
        ),
        advisory_lock_id=17002,
    ),
    "ais": PipelineDefinition(
        name="ais",
        module=(
            "backend.marine_data.ais."
            "run_aisstream_pipeline"
        ),
        advisory_lock_id=17003,
    ),
}


class ScheduledPipelineError(RuntimeError):
    """Raised when a scheduled pipeline cannot be started."""


def acquire_pipeline_lock(
    connection: Connection,
    lock_id: int,
) -> bool:
    """Try to acquire a PostgreSQL session advisory lock."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_try_advisory_lock(%s);",
            (lock_id,),
        )
        row = cursor.fetchone()

    return bool(row and row[0])


def release_pipeline_lock(
    connection: Connection,
    lock_id: int,
) -> None:
    """Release a PostgreSQL session advisory lock."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_advisory_unlock(%s);",
            (lock_id,),
        )


def run_scheduled_pipeline(pipeline_name: str) -> int:
    """Execute one configured pipeline unless it is already running."""
    try:
        definition = PIPELINES[pipeline_name]
    except KeyError as exc:
        raise ScheduledPipelineError(
            f"Unknown scheduled pipeline: {pipeline_name}"
        ) from exc

    started_at = datetime.now(timezone.utc)

    print(
        f"Scheduled pipeline requested: {definition.name}"
    )
    print(f"Scheduler start time: {started_at.isoformat()}")
    print("Acquiring pipeline lock...")

    with connect_to_database(
        prompt_for_password=False,
    ) as connection:
        acquired = acquire_pipeline_lock(
            connection,
            definition.advisory_lock_id,
        )

        if not acquired:
            print(
                f"Pipeline '{definition.name}' is already running. "
                "This execution will be skipped."
            )
            return 0

        try:
            print(
                f"Starting module: {definition.module}"
            )

            completed_process = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    definition.module,
                ],
                cwd=PROJECT_ROOT,
                check=False,
            )

            if completed_process.returncode != 0:
                print(
                    f"Pipeline '{definition.name}' failed with "
                    f"exit code {completed_process.returncode}.",
                    file=sys.stderr,
                )
                return completed_process.returncode

            completed_at = datetime.now(timezone.utc)
            print(
                f"Pipeline '{definition.name}' completed at "
                f"{completed_at.isoformat()}."
            )
            return 0

        finally:
            release_pipeline_lock(
                connection,
                definition.advisory_lock_id,
            )
            print("Pipeline lock released.")


def parse_arguments() -> argparse.Namespace:
    """Parse the pipeline selected by the scheduler."""
    parser = argparse.ArgumentParser(
        description=(
            "Run one MarineVerse ETL pipeline with "
            "PostgreSQL advisory-lock protection."
        )
    )
    parser.add_argument(
        "pipeline",
        choices=sorted(PIPELINES),
        help="Scheduled pipeline to execute.",
    )
    return parser.parse_args()


def main() -> int:
    """Run the selected scheduled pipeline."""
    arguments = parse_arguments()

    try:
        return run_scheduled_pipeline(
            arguments.pipeline
        )

    except (
        ScheduledPipelineError,
        psycopg.Error,
        OSError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())