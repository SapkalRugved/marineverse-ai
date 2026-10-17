"""Tests for port API endpoints."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.ports import PortsQueryError


SAMPLE_PORT = {
    "port_id": 1,
    "source_id": "way/49499133",
    "name": "Jawaharlal Nehru Port",
    "country": "India",
    "port_type": "port",
    "latitude": 18.9447587,
    "longitude": 72.9470922,
    "source": "openstreetmap",
    "updated_at": datetime(
        2026,
        10,
        8,
        tzinfo=timezone.utc,
    ),
}


class ApiPortsTests(unittest.TestCase):
    """Verify port endpoint behavior."""

    @classmethod
    def setUpClass(cls) -> None:
        """Create one API test client."""
        cls.client = TestClient(app)

    @patch(
        "backend.app.api.ports.list_ports",
        return_value=[SAMPLE_PORT],
    )
    def test_list_ports(self, list_ports_mock) -> None:
        """Return port records in a response envelope."""
        response = self.client.get(
            "/api/v1/ports?limit=10"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)
        self.assertEqual(
            response.json()["ports"][0]["name"],
            "Jawaharlal Nehru Port",
        )

        list_ports_mock.assert_called_once_with(
            port_type=None,
            name=None,
            minimum_latitude=None,
            maximum_latitude=None,
            minimum_longitude=None,
            maximum_longitude=None,
            limit=10,
        )

    @patch(
        "backend.app.api.ports.list_ports",
        return_value=[],
    )
    def test_filters_are_forwarded(
        self,
        list_ports_mock,
    ) -> None:
        """Forward API filters to the database service."""
        response = self.client.get(
            "/api/v1/ports"
            "?port_type=port"
            "&name=Mumbai"
            "&minimum_latitude=18"
            "&maximum_latitude=20"
            "&minimum_longitude=72"
            "&maximum_longitude=73"
            "&limit=25"
        )

        self.assertEqual(response.status_code, 200)

        list_ports_mock.assert_called_once_with(
            port_type="port",
            name="Mumbai",
            minimum_latitude=18.0,
            maximum_latitude=20.0,
            minimum_longitude=72.0,
            maximum_longitude=73.0,
            limit=25,
        )

    def test_invalid_coordinate_range(self) -> None:
        """Reject reversed geographic bounds."""
        response = self.client.get(
            "/api/v1/ports"
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

    @patch(
        "backend.app.api.ports.list_ports",
        side_effect=PortsQueryError(
            "Database unavailable."
        ),
    )
    def test_database_failure_returns_503(
        self,
        _list_ports_mock,
    ) -> None:
        """Hide internal database errors from clients."""
        response = self.client.get("/api/v1/ports")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {
                "detail": (
                    "Port data is temporarily unavailable."
                ),
            },
        )

    def test_openapi_contains_ports_endpoint(self) -> None:
        """Publish the port endpoint in OpenAPI."""
        response = self.client.get("/openapi.json")

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "/api/v1/ports",
            response.json()["paths"],
        )


if __name__ == "__main__":
    unittest.main()
