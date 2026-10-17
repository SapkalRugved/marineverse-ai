"""Tests for API health and readiness endpoints."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.main import app


class ApiHealthTests(unittest.TestCase):
    """Verify liveness, readiness, and API documentation."""

    @classmethod
    def setUpClass(cls) -> None:
        """Create one test client for this test class."""
        cls.client = TestClient(app)

    def test_health_endpoint(self) -> None:
        """Liveness must not depend on PostgreSQL."""
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "status": "ok",
                "service": "marineverse-api",
                "version": "0.1.0",
            },
        )

    @patch(
        "backend.app.api.health.database_is_ready",
        return_value=True,
    )
    def test_ready_endpoint_when_database_is_available(
        self,
        _database_check,
    ) -> None:
        """Readiness succeeds when PostgreSQL is available."""
        response = self.client.get("/ready")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "status": "ready",
                "database": "postgresql",
            },
        )

    @patch(
        "backend.app.api.health.database_is_ready",
        return_value=False,
    )
    def test_ready_endpoint_when_database_is_unavailable(
        self,
        _database_check,
    ) -> None:
        """Readiness fails without exposing connection details."""
        response = self.client.get("/ready")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {
                "detail": "Database is not ready.",
            },
        )

    def test_openapi_contains_health_endpoints(self) -> None:
        """OpenAPI documentation includes operational endpoints."""
        response = self.client.get("/openapi.json")

        self.assertEqual(response.status_code, 200)

        paths = response.json()["paths"]
        self.assertIn("/health", paths)
        self.assertIn("/ready", paths)


if __name__ == "__main__":
    unittest.main()
