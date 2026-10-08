"""Tests for Open-Meteo weather transformation."""

from __future__ import annotations

import copy
import unittest
from datetime import datetime, timedelta, timezone

from backend.marine_data.weather.transformer import (
    WeatherTransformationError,
    transform_payload,
)


class WeatherTransformerTests(unittest.TestCase):
    """Verify weather normalization and validation."""

    def setUp(self) -> None:
        self.ingested_at = datetime(
            2026,
            10,
            8,
            19,
            0,
            tzinfo=timezone.utc,
        )

        self.payload = {
            "source": "open-meteo",
            "source_dataset": "best_match_current",
            "records": [
                {
                    "requested_location": {
                        "source_id": "way/49499133",
                        "name": "Jawaharlal Nehru Port",
                        "latitude": 18.9447587,
                        "longitude": 72.9470922,
                    },
                    "api_response": {
                        "latitude": 18.945517,
                        "longitude": 72.975365,
                        "utc_offset_seconds": 0,
                        "current_units": {
                            "time": "iso8601",
                            "interval": "seconds",
                            "temperature_2m": "\u00b0C",
                            "pressure_msl": "hPa",
                            "precipitation": "mm",
                            "wind_speed_10m": "m/s",
                            "wind_direction_10m": "\u00b0",
                            "wind_gusts_10m": "m/s",
                        },
                        "current": {
                            "time": "2026-10-08T18:45",
                            "interval": 900,
                            "temperature_2m": 27.5,
                            "pressure_msl": 1013.2,
                            "precipitation": 0.0,
                            "wind_speed_10m": 1.42,
                            "wind_direction_10m": 51,
                            "wind_gusts_10m": 2.3,
                        },
                    },
                }
            ],
        }

    def transform(self, payload=None):
        return transform_payload(
            payload or self.payload,
            self.ingested_at,
        )

    def test_valid_record_mapping(self) -> None:
        result = self.transform()
        record = result.records[0]

        self.assertEqual(1, result.source_records_read)
        self.assertEqual(1, len(result.records))
        self.assertEqual(0, result.rejected_records)
        self.assertEqual(0, result.duplicates_removed)
        self.assertEqual(27.5, record.air_temperature_c)
        self.assertEqual(1013.2, record.pressure_hpa)
        self.assertEqual(1.42, record.wind_speed_mps)
        self.assertFalse(record.is_forecast)
        self.assertEqual("open-meteo", record.source)
        self.assertEqual(
            "best_match_current",
            record.source_dataset,
        )

    def test_requested_coordinates_are_used(self) -> None:
        record = self.transform().records[0]

        self.assertEqual(18.9447587, record.latitude)
        self.assertEqual(72.9470922, record.longitude)

    def test_valid_time_is_utc(self) -> None:
        record = self.transform().records[0]

        self.assertEqual(timezone.utc, record.valid_time.tzinfo)
        self.assertEqual(
            datetime(
                2026,
                10,
                8,
                18,
                45,
                tzinfo=timezone.utc,
            ),
            record.valid_time,
        )

    def test_wrong_unit_is_rejected(self) -> None:
        payload = copy.deepcopy(self.payload)
        payload["records"][0]["api_response"][
            "current_units"
        ]["wind_speed_10m"] = "km/h"

        with self.assertRaises(WeatherTransformationError):
            self.transform(payload)

    def test_nonzero_api_utc_offset_is_rejected(self) -> None:
        payload = copy.deepcopy(self.payload)
        payload["records"][0]["api_response"][
            "utc_offset_seconds"
        ] = 19800

        with self.assertRaises(WeatherTransformationError):
            self.transform(payload)

    def test_invalid_coordinates_are_rejected(self) -> None:
        payload = copy.deepcopy(self.payload)
        payload["records"][0]["requested_location"][
            "latitude"
        ] = 91.0

        with self.assertRaises(WeatherTransformationError):
            self.transform(payload)

    def test_negative_precipitation_is_rejected(self) -> None:
        payload = copy.deepcopy(self.payload)
        payload["records"][0]["api_response"]["current"][
            "precipitation"
        ] = -1.0

        with self.assertRaises(WeatherTransformationError):
            self.transform(payload)

    def test_invalid_wind_direction_is_rejected(self) -> None:
        payload = copy.deepcopy(self.payload)
        payload["records"][0]["api_response"]["current"][
            "wind_direction_10m"
        ] = 361

        with self.assertRaises(WeatherTransformationError):
            self.transform(payload)

    def test_duplicate_weather_record_is_removed(self) -> None:
        payload = copy.deepcopy(self.payload)
        payload["records"].append(
            copy.deepcopy(payload["records"][0])
        )

        result = self.transform(payload)

        self.assertEqual(2, result.source_records_read)
        self.assertEqual(1, len(result.records))
        self.assertEqual(1, result.duplicates_removed)

    def test_invalid_record_is_counted_when_valid_exists(self) -> None:
        payload = copy.deepcopy(self.payload)
        invalid_record = copy.deepcopy(payload["records"][0])
        invalid_record["api_response"]["current"][
            "pressure_msl"
        ] = 2000
        payload["records"].append(invalid_record)

        result = self.transform(payload)

        self.assertEqual(2, result.source_records_read)
        self.assertEqual(1, len(result.records))
        self.assertEqual(1, result.rejected_records)

    def test_non_utc_ingestion_time_is_failure(self) -> None:
        non_utc = datetime.now(
            timezone(timedelta(hours=5, minutes=30))
        )

        with self.assertRaises(WeatherTransformationError):
            transform_payload(self.payload, non_utc)

    def test_empty_records_is_failure(self) -> None:
        payload = copy.deepcopy(self.payload)
        payload["records"] = []

        with self.assertRaises(WeatherTransformationError):
            self.transform(payload)


if __name__ == "__main__":
    unittest.main()