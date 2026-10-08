"""Load validated weather records into PostgreSQL/PostGIS."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from psycopg import Connection

from backend.marine_data.weather.transformer import WeatherRecord


UPDATE_WEATHER_SQL = """
UPDATE weather_conditions
SET
    location = ST_SetSRID(
        ST_MakePoint(%(longitude)s, %(latitude)s),
        4326
    )::geography,
    air_temperature_c = %(air_temperature_c)s,
    pressure_hpa = %(pressure_hpa)s,
    precipitation_mm = %(precipitation_mm)s,
    wind_speed_mps = %(wind_speed_mps)s,
    wind_direction_deg = %(wind_direction_deg)s,
    wind_gust_mps = %(wind_gust_mps)s,
    ingested_at = %(ingested_at)s
WHERE source = %(source)s
  AND source_dataset = %(source_dataset)s
  AND valid_time = %(valid_time)s
  AND latitude = %(latitude)s
  AND longitude = %(longitude)s
  AND is_forecast = %(is_forecast)s
RETURNING weather_id;
"""

INSERT_WEATHER_SQL = """
INSERT INTO weather_conditions (
    valid_time,
    latitude,
    longitude,
    location,
    air_temperature_c,
    pressure_hpa,
    precipitation_mm,
    wind_speed_mps,
    wind_direction_deg,
    wind_gust_mps,
    is_forecast,
    source,
    source_dataset,
    ingested_at
)
VALUES (
    %(valid_time)s,
    %(latitude)s,
    %(longitude)s,
    ST_SetSRID(
        ST_MakePoint(%(longitude)s, %(latitude)s),
        4326
    )::geography,
    %(air_temperature_c)s,
    %(pressure_hpa)s,
    %(precipitation_mm)s,
    %(wind_speed_mps)s,
    %(wind_direction_deg)s,
    %(wind_gust_mps)s,
    %(is_forecast)s,
    %(source)s,
    %(source_dataset)s,
    %(ingested_at)s
)
RETURNING weather_id;
"""


class WeatherDatabaseLoadError(RuntimeError):
    """Raised when validated weather records cannot be loaded."""


def record_to_parameters(
    record: WeatherRecord,
) -> dict[str, Any]:
    """Convert one weather record into SQL parameters."""
    return {
        "valid_time": record.valid_time,
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
        "ingested_at": record.ingested_at,
    }


def load_weather_records(
    connection: Connection,
    records: Sequence[WeatherRecord],
) -> int:
    """Update or insert validated weather records."""
    if not records:
        raise WeatherDatabaseLoadError(
            "No validated weather records to load."
        )

    with connection.cursor() as cursor:
        for record in records:
            parameters = record_to_parameters(record)

            cursor.execute(UPDATE_WEATHER_SQL, parameters)
            existing_row = cursor.fetchone()

            if existing_row is None:
                cursor.execute(INSERT_WEATHER_SQL, parameters)

                if cursor.fetchone() is None:
                    raise WeatherDatabaseLoadError(
                        "Weather record was not inserted."
                    )

    return len(records)