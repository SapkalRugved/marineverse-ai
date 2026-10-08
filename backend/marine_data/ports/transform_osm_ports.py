"""CLI for transforming a retained raw Overpass ports response."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from backend.marine_data.ports.transformer import (
    TransformationError,
    transform_raw_file,
)


SAMPLE_RECORD_LIMIT = 3


def parse_arguments() -> argparse.Namespace:
    """Parse the raw JSON filename supplied by the user."""
    parser = argparse.ArgumentParser(
        description=(
            "Transform raw OSM port elements into validated and "
            "deduplicated in-memory records."
        )
    )
    parser.add_argument(
        "raw_file",
        type=Path,
        help="Path to a retained Overpass JSON response.",
    )
    return parser.parse_args()


def main() -> int:
    """Transform one raw file and display its quality summary."""
    arguments = parse_arguments()

    try:
        result = transform_raw_file(arguments.raw_file)
    except TransformationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    valid_record_count = len(result.records)
    reconciled_count = (
        valid_record_count
        + result.rejected_records
        + result.duplicates_removed
    )

    if reconciled_count != result.source_elements_read:
        print(
            "ERROR: Transformation counts do not reconcile.",
            file=sys.stderr,
        )
        return 1

    print("OSM ports transformation completed successfully.")
    print(f"Source elements read: {result.source_elements_read}")
    print(f"Valid records: {valid_record_count}")
    print(f"Rejected records: {result.rejected_records}")
    print(f"Duplicates removed: {result.duplicates_removed}")
    print()
    print(
        "Sample transformed records "
        f"(maximum {SAMPLE_RECORD_LIMIT}):"
    )

    for record in result.records[:SAMPLE_RECORD_LIMIT]:
        print(
            json.dumps(
                record.to_display_dict(),
                ensure_ascii=False,
                indent=2,
            )
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())