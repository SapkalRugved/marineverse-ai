"""Build a worldwide IBTrACS Silver Parquet dataset from the official ALL CSV.

Run from repository root:
    python -m backend.marine_data.cyclones.ibtracs_silver \
        --input data/raw/cyclones/ibtracs/ibtracs.ALL.list.v04r01.csv \
        --output data/processed/cyclones/ibtracs/global_cyclone_tracks.parquet

The original Bronze CSV is never modified. No AWS credentials are required.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REQUIRED = {"SID", "SEASON", "BASIN", "ISO_TIME", "LAT", "LON"}
SCHEMA_VERSION = "1.0"
KNOT_TO_MS = 0.514444


def _optional_number(value: str) -> float | None:
    value = (value or "").strip()
    if not value:
        return None
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Non-finite number")
    return number


def _utc(value: str) -> datetime:
    value = value.strip()
    if not value:
        raise ValueError("Missing timestamp")
    result = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    return result.replace(tzinfo=timezone.utc)


def _transform(row: dict[str, str]) -> dict:
    sid = row["SID"].strip()
    if not sid:
        raise ValueError("Missing storm SID")
    lat = _optional_number(row["LAT"])
    lon = _optional_number(row["LON"])
    if lat is None or lon is None or not (-90 <= lat <= 90) or not (-180 <= lon <= 360):
        raise ValueError("Missing or invalid geographic coordinates")
    # Some providers use 0..360 longitude; normalize to [-180, 180).
    lon = (lon + 180) % 360 - 180
    season = int(row["SEASON"].strip())
    if not (1800 <= season <= 2200):
        raise ValueError("Invalid season")
    wind_knots = _optional_number(row.get("WMO_WIND", ""))
    pressure_hpa = _optional_number(row.get("WMO_PRES", ""))
    if wind_knots is not None and wind_knots < 0:
        raise ValueError("Negative wind")
    if pressure_hpa is not None and pressure_hpa <= 0:
        raise ValueError("Nonpositive pressure")
    return {
        "storm_id": sid,
        "season": season,
        "basin": row["BASIN"].strip() or None,
        "name": row.get("NAME", "").strip() or None,
        "observed_at_utc": _utc(row["ISO_TIME"]),
        "latitude": lat,
        "longitude": lon,
        "wind_speed_ms": round(wind_knots * KNOT_TO_MS, 5) if wind_knots is not None else None,
        "pressure_hpa": pressure_hpa,
        "source": "NOAA_IBTrACS_v04r01_ALL",
    }


def _schema(pa):
    return pa.schema([
        pa.field("storm_id", pa.string(), nullable=False),
        pa.field("season", pa.int32(), nullable=False),
        pa.field("basin", pa.string()),
        pa.field("name", pa.string()),
        pa.field("observed_at_utc", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("latitude", pa.float64(), nullable=False),
        pa.field("longitude", pa.float64(), nullable=False),
        pa.field("wind_speed_ms", pa.float64()),
        pa.field("pressure_hpa", pa.float64()),
        pa.field("source", pa.string(), nullable=False),
    ])


def build(input_path: Path, output_path: Path, chunk_size: int = 25_000) -> dict:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError("Install Silver dependencies: python -m pip install -r requirements-silver.txt") from exc

    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")
    input_path = Path(input_path)
    output_path = Path(output_path)
    if input_path.resolve() == output_path.resolve():
        raise ValueError("Input and output paths must differ")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_name(output_path.name + ".partial")
    report_path = output_path.with_name("quality_report.json")
    schema = _schema(pa)
    stats = Counter()
    basins = Counter()
    seasons = set()
    rejected_examples = []
    source_hash = hashlib.sha256()
    with input_path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            source_hash.update(block)

    writer = None
    buffer = []
    try:
        with input_path.open("r", newline="", encoding="utf-8-sig") as source:
            reader = csv.DictReader(source)
            if not REQUIRED.issubset(set(reader.fieldnames or [])):
                raise ValueError(f"Missing columns: {sorted(REQUIRED - set(reader.fieldnames or []))}")
            # IBTrACS row 2 is units, not an observation.
            if next(reader, None) is None:
                raise ValueError("IBTrACS CSV has no units row")
            for line_number, row in enumerate(reader, start=3):
                stats["total_observation_rows"] += 1
                try:
                    if None in row:
                        raise ValueError("Malformed CSV row")
                    clean = _transform(row)
                except (ValueError, TypeError, OverflowError) as exc:
                    stats["rejected_rows"] += 1
                    if len(rejected_examples) < 10:
                        rejected_examples.append({"line": line_number, "reason": str(exc)})
                    continue
                buffer.append(clean)
                stats["accepted_rows"] += 1
                if clean["wind_speed_ms"] is None:
                    stats["missing_wind_rows"] += 1
                if clean["pressure_hpa"] is None:
                    stats["missing_pressure_rows"] += 1
                basins[clean["basin"] or "UNKNOWN"] += 1
                seasons.add(clean["season"])
                if len(buffer) >= chunk_size:
                    if writer is None:
                        writer = pq.ParquetWriter(temp_path, schema=schema, compression="snappy")
                    writer.write_table(pa.Table.from_pylist(buffer, schema=schema))
                    buffer.clear()
            if buffer:
                if writer is None:
                    writer = pq.ParquetWriter(temp_path, schema=schema, compression="snappy")
                writer.write_table(pa.Table.from_pylist(buffer, schema=schema))
                buffer.clear()
        if writer is None:
            raise ValueError("No valid observations in source file")
    except Exception:
        if writer is not None:
            writer.close()
            writer = None
        temp_path.unlink(missing_ok=True)
        raise
    finally:
        if writer is not None:
            writer.close()

    os.replace(temp_path, output_path)
    report = {
        "schema_version": SCHEMA_VERSION,
        "dataset": "NOAA IBTrACS v04r01 ALL (worldwide)",
        "source_file": input_path.name,
        "source_sha256": source_hash.hexdigest(),
        "output_file": output_path.name,
        "coordinate_reference_system": "EPSG:4326",
        "timestamp_timezone": "UTC",
        "longitude_convention": "[-180, 180)",
        "wind_speed_unit": "m/s",
        "pressure_unit": "hPa",
        "total_observation_rows": stats["total_observation_rows"],
        "accepted_rows": stats["accepted_rows"],
        "rejected_rows": stats["rejected_rows"],
        "missing_wind_rows": stats["missing_wind_rows"],
        "missing_pressure_rows": stats["missing_pressure_rows"],
        "basin_distribution": dict(sorted(basins.items())),
        "season_min": min(seasons),
        "season_max": max(seasons),
        "rejection_examples": rejected_examples,
        "note": "Season may be labelled by following calendar year in Southern Hemisphere. "
                "WMO wind/pressure are nullable; missing values must never be fabricated.",
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--chunk-size", type=int, default=25_000)
    args = parser.parse_args()
    print(json.dumps(build(args.input, args.output, args.chunk_size), indent=2))


if __name__ == "__main__":
    main()
