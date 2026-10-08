"""Transform retained Copernicus ocean subsets."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.marine_data.ocean.transformer import (
    OceanTransformationError,
    transform_raw_manifest,
)


def parse_arguments() -> argparse.Namespace:
    """Parse the retained Copernicus manifest filename."""
    parser = argparse.ArgumentParser(
        description=(
            "Transform retained Copernicus physics and wave subsets."
        )
    )
    parser.add_argument(
        "manifest",
        type=Path,
        help="Path to a retained Copernicus manifest JSON file.",
    )
    return parser.parse_args()


def json_default(value: Any) -> str:
    """Serialize supported non-JSON values."""
    if isinstance(value, datetime):
        return value.isoformat()

    raise TypeError(f"Cannot serialize {type(value).__name__}.")


def main() -> int:
    """Transform and summarize retained ocean data."""
    arguments = parse_arguments()

    try:
        result = transform_raw_manifest(arguments.manifest)

        print(
            f"Source grid cells: {result.source_grid_cells}"
        )
        print(f"Valid records: {len(result.records)}")
        print(f"Rejected records: {result.rejected_records}")

        print("\nSample transformed records (maximum 3):")

        for record in result.records[:3]:
            print(
                json.dumps(
                    asdict(record),
                    default=json_default,
                    ensure_ascii=False,
                    indent=2,
                )
            )

        return 0

    except OceanTransformationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())