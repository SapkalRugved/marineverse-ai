"""Tests for AIS vessel API endpoints."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.vessels import VesselsQueryError


OBSERVED_AT = datetime(
    2026,
    10,
    18,
    12,
    0,
    tzinfo=timezone.utc,
)

SAMPLE_VESSEL = {
    "vessel_id": 1,
    "mmsi": 419001342,
    "imo": 9876543,
    "name": "OCEAN BLISS",
    "ship_type": "cargo",
    "length_m": 120.5,
    "width_m": 20.0,
    "source": "aisstream",
    "updated_at": OBSERVED_AT,
    "latest_position": {
        "position_id": 10,
        "observed_at": OBSERVED_AT,
        "latitude": 13.1071,
        "longitude": 80.3011,
        "speed_mps": 0.77,
        "course_deg": 27.3,
        "heading_deg": 28.0,
        "navigation_status": "underway_using_engine",
        "source": "aisstream",
        "ingested_at": OBSERVED_AT,
    },
}


class ApiVesselsTests(unittest.TestCase):
    """Verify vessel endpoint behavior."""

    @classmethod
    def setUpClass(cls) -> None:
        """Create one API test client."""
        cls.client = TestClient(app)

    @patch(
        "backend.app.api.vessels.list_vessels",
        return_value=[SAMPLE_VESSEL],
    )
    def test_list_vessels(
        self,
        list_vessels_mock,
    ) -> None:
        """Return vessels with nested latest positions."""
        response = self.client.get(
            "/api/v1/vessels?limit=10"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)

        vessel = response.json()["vessels"][0]

        self.assertEqual(vessel["mmsi"], 419001342)
        self.assertEqual(vessel["name"], "OCEAN BLISS")
        self.assertEqual(
            vessel["latest_position"]["latitude"],
            13.1071,
        )

        list_vessels_mock.assert_called_once_with(
            mmsi=None,
            name=None,
            ship_type=None,
            source=None,
            minimum_latitude=None,
            maximum_latitude=None,
            minimum_longitude=None,
            maximum_longitude=None,
            observed_after=None,
            limit=10,
        )

    @patch(
        "backend.app.api.vessels.list_vessels",
        return_value=[],
    )
    def test_filters_are_forwarded(
        self,
        list_vessels_mock,
    ) -> None:
        """Forward vessel filters to the database service."""
        response = self.client.get(
            "/api/v1/vessels"
            "?mmsi=419001342"
            "&name=Ocean"
            "&ship_type=cargo"
            "&source=aisstream"
            "&minimum_latitude=10"
            "&maximum_latitude=15"
            "&minimum_longitude=75"
            "&maximum_longitude=85"
            "&observed_after=2026-10-18T10:00:00Z"
            "&limit=25"
        )

        self.assertEqual(response.status_code, 200)

        list_vessels_mock.assert_called_once_with(
            mmsi=419001342,
            name="Ocean",
            ship_type="cargo",
            source="aisstream",
            minimum_latitude=10.0,
            maximum_latitude=15.0,
            minimum_longitude=75.0,
            maximum_longitude=85.0,
            observed_after=datetime(
                2026,
                10,
                18,
                10,
                0,
                tzinfo=timezone.utc,
            ),
            limit=25,
        )

    def test_invalid_coordinate_range(self) -> None:
        """Reject reversed geographic bounds."""
        response = self.client.get(
            "/api/v1/vessels"
            "?minimum_latitude=20"
            "&maximum_latitude=18"
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json()["detail"],
            (
                "minimum_latitude must not exceed "
                "maximum_latitude."
            ),
        )

    def test_invalid_mmsi_is_rejected(self) -> None:
        """Reject an MMSI outside the nine-digit range."""
        response = self.client.get(
            "/api/v1/vessels?mmsi=12345"
        )

        self.assertEqual(response.status_code, 422)

    @patch(
        "backend.app.api.vessels.list_vessels",
        side_effect=VesselsQueryError(
            "Database unavailable."
        ),
    )
    def test_database_failure_returns_503(
        self,
        _list_vessels_mock,
    ) -> None:
        """Hide internal database errors from clients."""
        response = self.client.get("/api/v1/vessels")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {
                "detail": (
                    "Vessel data is temporarily unavailable."
                ),
            },
        )

    def test_openapi_contains_vessels_endpoint(self) -> None:
        """Publish the vessel endpoint in OpenAPI."""
        response = self.client.get("/openapi.json")

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "/api/v1/vessels",
            response.json()["paths"],
        )


if __name__ == "__main__":
    unittest.main()
