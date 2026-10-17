"""Tests for ocean API endpoints."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.ocean import OceanQueryError


SAMPLE_OCEAN = {
    "ocean_id": 1,
    "valid_time": datetime(
        2026,
        10,
        8,
        21,
        tzinfo=timezone.utc,
    ),
    "latitude": 18.6666718,
    "longitude": 72.3333435,
    "depth_m": 0.494025,
    "current_u_mps": -0.238184,
    "current_v_mps": -0.005083,
    "current_speed_mps": 0.238238,
    "current_direction_deg": 268.777377,
    "sea_surface_temperature_c": 30.237095,
    "wave_height_m": 0.7,
    "wave_direction_deg": 238.14,
    "wave_period_s": 4.87,
    "is_forecast": False,
    "source": "copernicus-marine",
    "source_dataset": (
        "cmems_mod_glo_phy_anfc_0.083deg_PT1H-m+"
        "cmems_mod_glo_wav_anfc_0.083deg_PT3H-i"
    ),
    "ingested_at": datetime(
        2026,
        10,
        9,
        tzinfo=timezone.utc,
    ),
}


class ApiOceanTests(unittest.TestCase):
    """Verify ocean endpoint behavior."""

    @classmethod
    def setUpClass(cls) -> None:
        """Create one API test client."""
        cls.client = TestClient(app)

    @patch(
        "backend.app.api.ocean.list_ocean_conditions",
        return_value=[SAMPLE_OCEAN],
    )
    def test_list_ocean_conditions(
        self,
        list_ocean_mock,
    ) -> None:
        """Return ocean records in a response envelope."""
        response = self.client.get(
            "/api/v1/ocean?limit=10"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)
        self.assertEqual(
            response.json()["ocean"][0]["source"],
            "copernicus-marine",
        )

        list_ocean_mock.assert_called_once_with(
            source=None,
            source_dataset=None,
            is_forecast=None,
            start_time=None,
            end_time=None,
            minimum_depth_m=None,
            maximum_depth_m=None,
            minimum_latitude=None,
            maximum_latitude=None,
            minimum_longitude=None,
            maximum_longitude=None,
            latest_only=True,
            limit=10,
            offset=0,
        )

    @patch(
        "backend.app.api.ocean.list_ocean_conditions",
        return_value=[],
    )
    def test_filters_are_forwarded(
        self,
        list_ocean_mock,
    ) -> None:
        """Forward ocean filters to the service."""
        response = self.client.get(
            "/api/v1/ocean"
            "?source=copernicus-marine"
            "&is_forecast=false"
            "&minimum_depth_m=0"
            "&maximum_depth_m=1"
            "&minimum_latitude=18"
            "&maximum_latitude=20"
            "&minimum_longitude=72"
            "&maximum_longitude=73"
            "&latest_only=false"
            "&limit=25"
            "&offset=10"
        )

        self.assertEqual(response.status_code, 200)

        list_ocean_mock.assert_called_once_with(
            source="copernicus-marine",
            source_dataset=None,
            is_forecast=False,
            start_time=None,
            end_time=None,
            minimum_depth_m=0.0,
            maximum_depth_m=1.0,
            minimum_latitude=18.0,
            maximum_latitude=20.0,
            minimum_longitude=72.0,
            maximum_longitude=73.0,
            latest_only=False,
            limit=25,
            offset=10,
        )

    def test_invalid_depth_range(self) -> None:
        """Reject reversed depth bounds."""
        response = self.client.get(
            "/api/v1/ocean"
            "?minimum_depth_m=10"
            "&maximum_depth_m=1"
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json()["detail"],
            (
                "minimum_depth_m must not exceed "
                "maximum_depth_m."
            ),
        )

    def test_invalid_time_range(self) -> None:
        """Reject a reversed time range."""
        response = self.client.get(
            "/api/v1/ocean"
            "?start_time=2026-10-09T00:00:00Z"
            "&end_time=2026-10-08T00:00:00Z"
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json()["detail"],
            "start_time must not exceed end_time.",
        )

    @patch(
        "backend.app.api.ocean.list_ocean_conditions",
        side_effect=OceanQueryError(
            "Database unavailable."
        ),
    )
    def test_database_failure_returns_503(
        self,
        _list_ocean_mock,
    ) -> None:
        """Hide internal database errors from clients."""
        response = self.client.get("/api/v1/ocean")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {
                "detail": (
                    "Ocean data is temporarily unavailable."
                ),
            },
        )

    def test_openapi_contains_ocean_endpoint(self) -> None:
        """Publish the ocean endpoint in OpenAPI."""
        response = self.client.get("/openapi.json")

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "/api/v1/ocean",
            response.json()["paths"],
        )


if __name__ == "__main__":
    unittest.main()