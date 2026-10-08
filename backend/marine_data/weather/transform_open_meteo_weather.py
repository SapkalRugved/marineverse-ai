"""Transform and inspect retained Open-Meteo weather data."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from backend.marine_data.weather.transformer import (
    WeatherTransformationError,
    transform_raw_file,
)


def parse_arguments() -> argparse.Namespace:
    """Parse the retained weather filename."""
    parser = argparse.ArgumentParser(
        description="Transform retained Open-Meteo weather data."
    )
    parser.add_argument(
        "raw_file",
        type=Path,
        help="Path to a retained Open-Meteo JSON response.",
    )
    return parser.parse_args()


def main() -> int:
    """Transform weather data and print a small sample."""
    arguments = parse_arguments()

    try:
        result = transform_raw_file(arguments.raw_file)

        print(f"Source records read: {result.source_records_read}")
        print(f"Valid records: {len(result.records)}")
        print(f"Rejected records: {result.rejected_records}")
        print(f"Duplicates removed: {result.duplicates_removed}")
        print("")
        print("Sample transformed records (maximum 3):")

        for record in result.records[:3]:
            sample = {
                "valid_time": record.valid_time.isoformat(),
                "latitude": record.latitude,
                "longitude": record.longitude,
                "air_temperature_c": record.air_temperature_c,
                "pressure_hpa": record.pressure_hpa,
                "precipitation_mm": record.precipitation_mm,
                "wind_speed_mps": record.wind_speed_mps,
                "wind_direction_deg": record.wind_direction_deg,
                "wind_gust_mps": record.wind_gust_mps,
                "is_forecast": record.is_forecast,
                "source": record.source,
                "source_dataset": record.source_dataset,
                "ingested_at": record.ingested_at.isoformat(),
            }
            print(json.dumps(sample, indent=2))

        return 0

    except WeatherTransformationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())