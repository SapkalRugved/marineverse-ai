"""Transform retained Open-Meteo responses into weather records."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SOURCE = "open-meteo"
SOURCE_DATASET = "best_match_current"

REQUIRED_UNITS = {
    "temperature_2m": "°C",
    "pressure_msl": "hPa",
    "precipitation": "mm",
    "wind_speed_10m": "m/s",
    "wind_direction_10m": "°",
    "wind_gusts_10m": "m/s",
}


class WeatherTransformationError(RuntimeError):
    """Raised when retained weather data cannot be transformed."""


class WeatherRecordValidationError(ValueError):
    """Raised when one weather record is invalid."""


@dataclass(frozen=True, slots=True)
class WeatherRecord:
    """One normalized weather condition."""

    valid_time: datetime
    latitude: float
    longitude: float
    air_temperature_c: float
    pressure_hpa: float
    precipitation_mm: float
    wind_speed_mps: float
    wind_direction_deg: float
    wind_gust_mps: float
    is_forecast: bool
    source: str
    source_dataset: str
    ingested_at: datetime


@dataclass(frozen=True, slots=True)
class WeatherTransformationResult:
    """Summary and output of one transformation."""

    records: tuple[WeatherRecord, ...]
    source_records_read: int
    rejected_records: int
    duplicates_removed: int


def require_utc(value: datetime, field_name: str) -> datetime:
    """Require a timezone-aware UTC timestamp."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise WeatherTransformationError(
            f"{field_name} must be timezone-aware."
        )

    if value.utcoffset().total_seconds() != 0:
        raise WeatherTransformationError(
            f"{field_name} must use UTC."
        )

    return value.astimezone(timezone.utc)


def parse_valid_time(value: Any) -> datetime:
    """Parse an Open-Meteo UTC ISO-8601 valid time."""
    if not isinstance(value, str) or not value.strip():
        raise WeatherRecordValidationError(
            "Current weather time is missing."
        )

    try:
        parsed = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise WeatherRecordValidationError(
            "Current weather time is invalid."
        ) from exc

    # Open-Meteo returns a timezone-free string when timezone=UTC.
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    if parsed.utcoffset() is None:
        raise WeatherRecordValidationError(
            "Current weather time has no UTC offset."
        )

    return parsed.astimezone(timezone.utc)


def require_number(
    mapping: dict[str, Any],
    key: str,
    minimum: float,
    maximum: float,
) -> float:
    """Read and range-check one numeric field."""
    value = mapping.get(key)

    if isinstance(value, bool) or not isinstance(
        value,
        (int, float),
    ):
        raise WeatherRecordValidationError(
            f"{key} must be numeric."
        )

    number = float(value)

    if not math.isfinite(number):
        raise WeatherRecordValidationError(
            f"{key} must be finite."
        )

    if number < minimum or number > maximum:
        raise WeatherRecordValidationError(
            f"{key} is outside the accepted range."
        )

    return number


def validate_units(units: Any) -> None:
    """Require the exact units used by the frozen schema."""
    if not isinstance(units, dict):
        raise WeatherRecordValidationError(
            "Current weather units are missing."
        )

    for field_name, expected_unit in REQUIRED_UNITS.items():
        if units.get(field_name) != expected_unit:
            raise WeatherRecordValidationError(
                f"{field_name} must use {expected_unit}."
            )


def transform_record(
    raw_record: Any,
    ingested_at: datetime,
) -> WeatherRecord:
    """Transform one raw Open-Meteo location response."""
    if not isinstance(raw_record, dict):
        raise WeatherRecordValidationError(
            "Weather record must be an object."
        )

    requested = raw_record.get("requested_location")
    response = raw_record.get("api_response")

    if not isinstance(requested, dict):
        raise WeatherRecordValidationError(
            "Requested location is missing."
        )

    if not isinstance(response, dict):
        raise WeatherRecordValidationError(
            "API response is missing."
        )

    if response.get("utc_offset_seconds") != 0:
        raise WeatherRecordValidationError(
            "API response must use UTC."
        )

    units = response.get("current_units")
    current = response.get("current")

    validate_units(units)

    if not isinstance(current, dict):
        raise WeatherRecordValidationError(
            "Current weather values are missing."
        )

    latitude = require_number(
        requested,
        "latitude",
        -90.0,
        90.0,
    )
    longitude = require_number(
        requested,
        "longitude",
        -180.0,
        180.0,
    )

    return WeatherRecord(
        valid_time=parse_valid_time(current.get("time")),
        latitude=latitude,
        longitude=longitude,
        air_temperature_c=require_number(
            current,
            "temperature_2m",
            -100.0,
            70.0,
        ),
        pressure_hpa=require_number(
            current,
            "pressure_msl",
            800.0,
            1100.0,
        ),
        precipitation_mm=require_number(
            current,
            "precipitation",
            0.0,
            1000.0,
        ),
        wind_speed_mps=require_number(
            current,
            "wind_speed_10m",
            0.0,
            150.0,
        ),
        wind_direction_deg=require_number(
            current,
            "wind_direction_10m",
            0.0,
            360.0,
        ),
        wind_gust_mps=require_number(
            current,
            "wind_gusts_10m",
            0.0,
            200.0,
        ),
        is_forecast=False,
        source=SOURCE,
        source_dataset=SOURCE_DATASET,
        ingested_at=ingested_at,
    )


def transform_payload(
    payload: Any,
    ingested_at: datetime | None = None,
) -> WeatherTransformationResult:
    """Transform one retained Open-Meteo response envelope."""
    if not isinstance(payload, dict):
        raise WeatherTransformationError(
            "Weather payload must be a JSON object."
        )

    if payload.get("source") != SOURCE:
        raise WeatherTransformationError(
            f"Weather source must be {SOURCE}."
        )

    if payload.get("source_dataset") != SOURCE_DATASET:
        raise WeatherTransformationError(
            f"Source dataset must be {SOURCE_DATASET}."
        )

    raw_records = payload.get("records")

    if not isinstance(raw_records, list) or not raw_records:
        raise WeatherTransformationError(
            "Weather payload contains no records."
        )

    transformation_time = require_utc(
        ingested_at or datetime.now(timezone.utc),
        "ingested_at",
    )

    records: list[WeatherRecord] = []
    seen_keys: set[tuple[Any, ...]] = set()
    rejected_records = 0
    duplicates_removed = 0

    for raw_record in raw_records:
        try:
            record = transform_record(
                raw_record,
                transformation_time,
            )
        except WeatherRecordValidationError:
            rejected_records += 1
            continue

        deduplication_key = (
            record.source,
            record.source_dataset,
            record.valid_time,
            record.latitude,
            record.longitude,
        )

        if deduplication_key in seen_keys:
            duplicates_removed += 1
            continue

        seen_keys.add(deduplication_key)
        records.append(record)

    if not records:
        raise WeatherTransformationError(
            "Transformation produced zero valid weather records."
        )

    return WeatherTransformationResult(
        records=tuple(records),
        source_records_read=len(raw_records),
        rejected_records=rejected_records,
        duplicates_removed=duplicates_removed,
    )


def transform_raw_file(
    raw_file: Path,
    ingested_at: datetime | None = None,
) -> WeatherTransformationResult:
    """Read and transform a retained Open-Meteo JSON file."""
    try:
        with raw_file.open("r", encoding="utf-8") as input_file:
            payload = json.load(input_file)
    except (OSError, json.JSONDecodeError) as exc:
        raise WeatherTransformationError(
            f"Could not read weather file: {raw_file}"
        ) from exc

    return transform_payload(payload, ingested_at)