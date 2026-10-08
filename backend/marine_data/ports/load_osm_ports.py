"""Transform raw OSM data and load valid ports into PostgreSQL."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import psycopg

from backend.marine_data.database import connect_to_database
from backend.marine_data.ports.loader import (
    DatabaseLoadError,
    load_port_records,
)
from backend.marine_data.ports.transformer import (
    TransformationError,
    transform_raw_file,
)


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
    """Run transformation and one atomic database load."""
    arguments = parse_arguments()

    try:
        result = transform_raw_file(arguments.raw_file)

        print(f"Source elements read: {result.source_elements_read}")
        print(f"Valid records prepared: {len(result.records)}")
        print(f"Rejected records: {result.rejected_records}")
        print(f"Duplicates removed: {result.duplicates_removed}")
        print("Connecting to PostgreSQL...")

        with connect_to_database() as connection:
            rows_processed = load_port_records(
                connection,
                result.records,
            )

        print("PostgreSQL ports load completed successfully.")
        print(f"Rows processed by upsert: {rows_processed}")
        return 0

    except (
        TransformationError,
        DatabaseLoadError,
        psycopg.Error,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())