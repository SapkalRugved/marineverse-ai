"""Retrieve current weather for OSM port locations from Open-Meteo."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from backend.marine_data.database import connect_to_database


API_URL = "https://api.open-meteo.com/v1/forecast"
SOURCE = "open-meteo"
SOURCE_DATASET = "best_match_current"
BATCH_SIZE = 10
REQUEST_TIMEOUT = (10, 60)

CURRENT_VARIABLES = (
    "temperature_2m",
    "pressure_msl",
    "precipitation",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
)

PORT_LOCATIONS_SQL = """
SELECT
    source_id,
    name,
    latitude,
    longitude
FROM ports
WHERE source = 'openstreetmap'
  AND port_type = 'port'
  AND latitude IS NOT NULL
  AND longitude IS NOT NULL
ORDER BY port_id;
"""

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RAW_DIRECTORY = PROJECT_ROOT / "data" / "raw" / "weather"


class WeatherRetrievalError(RuntimeError):
    """Raised when current weather data cannot be retrieved."""


def create_http_session() -> requests.Session:
    """Create an HTTP session with retries for temporary API failures."""
    retry_policy = Retry(
        total=4,
        connect=4,
        read=4,
        status=4,
        backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
    )

    adapter = HTTPAdapter(max_retries=retry_policy)
    session = requests.Session()
    session.mount("https://", adapter)
    return session


def read_port_locations() -> list[dict[str, Any]]:
    """Read OSM locations classified as ports from PostgreSQL."""
    print("Connecting to PostgreSQL...")

    with connect_to_database() as connection:
        with connection.cursor() as cursor:
            cursor.execute(PORT_LOCATIONS_SQL)
            rows = cursor.fetchall()

    locations = [
        {
            "source_id": row[0],
            "name": row[1],
            "latitude": float(row[2]),
            "longitude": float(row[3]),
        }
        for row in rows
    ]

    if not locations:
        raise WeatherRetrievalError(
            "No OpenStreetMap port locations were found."
        )

    return locations


def split_batches(
    locations: list[dict[str, Any]],
) -> list[list[dict[str, Any]]]:
    """Split port locations into API request batches."""
    return [
        locations[index:index + BATCH_SIZE]
        for index in range(0, len(locations), BATCH_SIZE)
    ]


def fetch_batch(
    session: requests.Session,
    locations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Retrieve current weather for one batch of port locations."""
    parameters = {
        "latitude": ",".join(
            str(location["latitude"])
            for location in locations
        ),
        "longitude": ",".join(
            str(location["longitude"])
            for location in locations
        ),
        "current": ",".join(CURRENT_VARIABLES),
        "temperature_unit": "celsius",
        "wind_speed_unit": "ms",
        "precipitation_unit": "mm",
        "timezone": "UTC",
        "cell_selection": "nearest",
    }

    response = session.get(
        API_URL,
        params=parameters,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()

    responses = payload if isinstance(payload, list) else [payload]

    if len(responses) != len(locations):
        raise WeatherRetrievalError(
            "Open-Meteo response count did not match the "
            "requested location count."
        )

    batch_records = []

    for location, weather_response in zip(
        locations,
        responses,
        strict=True,
    ):
        current = weather_response.get("current")

        if not isinstance(current, dict) or not current.get("time"):
            raise WeatherRetrievalError(
                "Open-Meteo response did not contain current weather "
                f"for {location['name']}."
            )

        batch_records.append(
            {
                "requested_location": location,
                "api_response": weather_response,
            }
        )

    return batch_records


def retrieve_weather(
    locations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Retrieve current weather for all selected ports."""
    records: list[dict[str, Any]] = []

    with create_http_session() as session:
        batches = split_batches(locations)

        for batch_number, batch in enumerate(batches, start=1):
            print(
                f"Retrieving batch {batch_number}/{len(batches)} "
                f"({len(batch)} locations)..."
            )
            records.extend(fetch_batch(session, batch))

    return records


def retain_raw_response(
    locations: list[dict[str, Any]],
    records: list[dict[str, Any]],
) -> Path:
    """Write the complete retrieval envelope atomically."""
    retrieved_at = datetime.now(timezone.utc)
    timestamp = retrieved_at.strftime("%Y%m%dT%H%M%SZ")

    RAW_DIRECTORY.mkdir(parents=True, exist_ok=True)

    output_path = (
        RAW_DIRECTORY
        / f"open_meteo_current_ports_{timestamp}.json"
    )
    temporary_path = output_path.with_suffix(".json.tmp")

    envelope = {
        "source": SOURCE,
        "source_dataset": SOURCE_DATASET,
        "retrieved_at": retrieved_at.isoformat(),
        "location_selection": {
            "source": "openstreetmap",
            "port_type": "port",
            "location_count": len(locations),
        },
        "records": records,
    }

    with temporary_path.open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as output_file:
        json.dump(
            envelope,
            output_file,
            ensure_ascii=False,
            indent=2,
        )
        output_file.write("\n")

    temporary_path.replace(output_path)
    return output_path


def main() -> int:
    """Retrieve and retain current weather for OSM port locations."""
    try:
        locations = read_port_locations()
        print(f"Port locations selected: {len(locations)}")

        records = retrieve_weather(locations)
        output_path = retain_raw_response(locations, records)

        print("Open-Meteo weather retrieval completed successfully.")
        print(f"Weather records received: {len(records)}")
        print(f"Raw response retained at: {output_path}")
        return 0

    except (
        WeatherRetrievalError,
        requests.RequestException,
        psycopg.Error,
        OSError,
        ValueError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())