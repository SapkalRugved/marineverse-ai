
"""Tests for configurable Open-Meteo raw response storage."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.marine_data.weather import retrieve_open_meteo_weather as weather


class WeatherStorageTests(unittest.TestCase):
    """Validate weather storage precedence and retained JSON."""

    def setUp(self) -> None:
        self.locations = [
            {
                "source_id": "test-port",
                "name": "Test Port",
                "latitude": 18.95,
                "longitude": 72.85,
            }
        ]
        self.records = [
            {
                "requested_location": self.locations[0],
                "api_response": {
                    "current": {"time": "2026-10-18T18:00"}
                },
            }
        ]

    def test_repository_fallback(self) -> None:
        """Preserve the existing raw directory by default."""

        with tempfile.TemporaryDirectory() as directory:
            expected_directory = Path(directory) / "legacy-weather"

            with patch.dict(os.environ, {}, clear=True):
                with patch.object(
                    weather,
                    "RAW_DIRECTORY",
                    expected_directory,
                ):
                    result = weather.retain_raw_response(
                        self.locations,
                        self.records,
                    )

            self.assertEqual(result.parent, expected_directory)
            self.assertTrue(result.exists())

    def test_environment_data_root(self) -> None:
        """Store raw weather files under the configured data root."""

        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(
                os.environ,
                {"MARINEVERSE_DATA_DIR": directory},
            ):
                result = weather.retain_raw_response(
                    self.locations,
                    self.records,
                )

            expected_directory = (
                Path(directory).resolve() / "raw" / "weather"
            )

            self.assertEqual(result.parent, expected_directory)
            self.assertTrue(result.exists())

            payload = json.loads(result.read_text(encoding="utf-8"))
            self.assertEqual(payload["source"], "open-meteo")
            self.assertEqual(payload["records"], self.records)

    def test_explicit_directory_overrides_environment(self) -> None:
        """Allow the caller to supply the final output directory."""

        with tempfile.TemporaryDirectory() as configured_root:
            with tempfile.TemporaryDirectory() as explicit_directory:
                with patch.dict(
                    os.environ,
                    {"MARINEVERSE_DATA_DIR": configured_root},
                ):
                    result = weather.retain_raw_response(
                        self.locations,
                        self.records,
                        output_directory=Path(explicit_directory),
                    )

                self.assertEqual(
                    result.parent,
                    Path(explicit_directory),
                )
                self.assertTrue(result.exists())


if __name__ == "__main__":
    unittest.main()
