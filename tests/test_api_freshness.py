"""Tests for the data-freshness API endpoint."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.freshness import FreshnessQueryError


CHECKED_AT = datetime(
    2026,
    10,
    18,
    tzinfo=timezone.utc,
)

SAMPLE_REPORT = {
    "status": "fresh",
    "checked_at": CHECKED_AT,
    "datasets": [
        {
            "dataset": "weather",
            "status": "fresh",
            "latest_valid_time": CHECKED_AT,
            "latest_ingested_at": CHECKED_AT,
            "last_successful_run_at": CHECKED_AT,
            "age_seconds": 0.0,
            "maximum_age_seconds": 1800,
        },
    ],
}


class ApiFreshnessTests(unittest.TestCase):
    """Verify freshness endpoint behavior."""

    @classmethod
    def setUpClass(cls) -> None:
        """Create one API test client."""
        cls.client = TestClient(app)

    @patch(
        "backend.app.api.freshness.get_data_freshness",
        return_value=SAMPLE_REPORT,
    )
    def test_freshness_endpoint(
        self,
        _freshness_mock,
    ) -> None:
        """Return dataset freshness information."""
        response = self.client.get(
            "/api/v1/freshness"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["status"],
            "fresh",
        )
        self.assertEqual(
            response.json()["datasets"][0]["dataset"],
            "weather",
        )

    @patch(
        "backend.app.api.freshness.get_data_freshness",
        side_effect=FreshnessQueryError(
            "Database unavailable."
        ),
    )
    def test_database_failure_returns_503(
        self,
        _freshness_mock,
    ) -> None:
        """Hide internal database failures."""
        response = self.client.get(
            "/api/v1/freshness"
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {
                "detail": (
                    "Data freshness is temporarily unavailable."
                ),
            },
        )

    def test_openapi_contains_freshness_endpoint(self) -> None:
        """Publish freshness monitoring in OpenAPI."""
        response = self.client.get("/openapi.json")

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "/api/v1/freshness",
            response.json()["paths"],
        )


if __name__ == "__main__":
    unittest.main()