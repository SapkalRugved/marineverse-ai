"""Tests for weather API endpoints."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.weather import WeatherQueryError


SAMPLE_WEATHER = {
    "weather_id": 1,
    "valid_time": datetime(
        2026,
        10,
        8,
        18,
        45,
        tzinfo=timezone.utc,
    ),
    "latitude": 18.9447587,
    "longitude": 72.9470922,
    "air_temperature_c": 27.5,
    "pressure_hpa": 1013.2,
    "precipitation_mm": 0.0,
    "wind_speed_mps": 1.42,
    "wind_direction_deg": 51.0,
    "wind_gust_mps": 2.3,
    "is_forecast": False,
    "source": "open-meteo",
    "source_dataset": "best_match_current",
    "ingested_at": datetime(
        2026,
        10,
        8,
        18,
        56,
        tzinfo=timezone.utc,
    ),
}


class ApiWeatherTests(unittest.TestCase):
    """Verify weather endpoint behavior."""

    @classmethod
    def setUpClass(cls) -> None:
        """Create one API test client."""
        cls.client = TestClient(app)

    @patch(
        "backend.app.api.weather.list_weather",
        return_value=[SAMPLE_WEATHER],
    )
    def test_list_weather(self, list_weather_mock) -> None:
        """Return weather records in a response envelope."""
        response = self.client.get(
            "/api/v1/weather?limit=10"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)
        self.assertEqual(
            response.json()["weather"][0]["source"],
            "open-meteo",
        )

        list_weather_mock.assert_called_once_with(
            source=None,
            source_dataset=None,
            is_forecast=None,
            start_time=None,
            end_time=None,
            minimum_latitude=None,
            maximum_latitude=None,
            minimum_longitude=None,
            maximum_longitude=None,
            latest_only=True,
            limit=10,
        )

    @patch(
        "backend.app.api.weather.list_weather",
        return_value=[],
    )
    def test_filters_are_forwarded(
        self,
        list_weather_mock,
    ) -> None:
        """Forward weather filters to the service."""
        response = self.client.get(
            "/api/v1/weather"
            "?source=open-meteo"
            "&source_dataset=best_match_current"
            "&is_forecast=false"
            "&minimum_latitude=18"
            "&maximum_latitude=20"
            "&minimum_longitude=72"
            "&maximum_longitude=73"
            "&latest_only=false"
            "&limit=25"
        )

        self.assertEqual(response.status_code, 200)

        list_weather_mock.assert_called_once_with(
            source="open-meteo",
            source_dataset="best_match_current",
            is_forecast=False,
            start_time=None,
            end_time=None,
            minimum_latitude=18.0,
            maximum_latitude=20.0,
            minimum_longitude=72.0,
            maximum_longitude=73.0,
            latest_only=False,
            limit=25,
        )

    def test_invalid_coordinate_range(self) -> None:
        """Reject reversed geographic bounds."""
        response = self.client.get(
            "/api/v1/weather"
            "?minimum_longitude=80"
            "&maximum_longitude=70"
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json()["detail"],
            (
                "minimum_longitude must not exceed "
                "maximum_longitude."
            ),
        )

    def test_invalid_time_range(self) -> None:
        """Reject a reversed time range."""
        response = self.client.get(
            "/api/v1/weather"
            "?start_time=2026-10-09T00:00:00Z"
            "&end_time=2026-10-08T00:00:00Z"
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json()["detail"],
            "start_time must not exceed end_time.",
        )

    @patch(
        "backend.app.api.weather.list_weather",
        side_effect=WeatherQueryError(
            "Database unavailable."
        ),
    )
    def test_database_failure_returns_503(
        self,
        _list_weather_mock,
    ) -> None:
        """Hide internal database errors from clients."""
        response = self.client.get("/api/v1/weather")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {
                "detail": (
                    "Weather data is temporarily unavailable."
                ),
            },
        )

    def test_openapi_contains_weather_endpoint(self) -> None:
        """Publish the weather endpoint in OpenAPI."""
        response = self.client.get("/openapi.json")

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "/api/v1/weather",
            response.json()["paths"],
        )


if __name__ == "__main__":
    unittest.main()