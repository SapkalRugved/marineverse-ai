"""Tests for AIS vessel database queries."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import psycopg

from backend.app.services.vessels import (
    VesselsQueryError,
    build_vessel_record,
    list_vessels,
)


def make_vessel_row(
    *,
    latest_position_id: int | None = 20,
) -> dict[str, object]:
    """Return one representative joined vessel row."""
    return {
        "vessel_id": 10,
        "mmsi": 419001342,
        "imo": 9876543,
        "name": "OCEAN BLISS",
        "ship_type": "cargo",
        "length_m": 120.5,
        "width_m": 20.0,
        "vessel_source": "aisstream",
        "updated_at": None,
        "latest_position_id": latest_position_id,
        "latest_observed_at": None,
        "latest_latitude": 13.1071,
        "latest_longitude": 80.3011,
        "latest_speed_mps": 0.77,
        "latest_course_deg": 27.3,
        "latest_heading_deg": 28.0,
        "latest_navigation_status": (
            "underway_using_engine"
        ),
        "latest_position_source": "aisstream",
        "latest_ingested_at": None,
    }


class VesselServiceTests(unittest.TestCase):
    """Verify vessel query and response mapping behavior."""

    def test_builds_nested_latest_position(self) -> None:
        """Map the joined position into a nested structure."""
        record = build_vessel_record(make_vessel_row())

        self.assertEqual(record["vessel_id"], 10)
        self.assertEqual(record["mmsi"], 419001342)
        self.assertEqual(record["name"], "OCEAN BLISS")

        position = record["latest_position"]

        self.assertIsNotNone(position)
        assert position is not None
        self.assertEqual(position["position_id"], 20)
        self.assertEqual(position["latitude"], 13.1071)
        self.assertEqual(position["longitude"], 80.3011)
        self.assertEqual(
            position["navigation_status"],
            "underway_using_engine",
        )

    def test_vessel_without_position_maps_to_none(self) -> None:
        """Preserve vessels that have no stored positions."""
        row = make_vessel_row(latest_position_id=None)

        record = build_vessel_record(row)

        self.assertIsNone(record["latest_position"])

    @patch(
        "backend.app.services.vessels."
        "connect_to_database"
    )
    def test_list_vessels_uses_parameterized_query(
        self,
        connect_mock: MagicMock,
    ) -> None:
        """Execute the latest-position query with filters."""
        connection = (
            connect_mock.return_value.__enter__.return_value
        )
        cursor = (
            connection.cursor.return_value
            .__enter__.return_value
        )
        cursor.fetchall.return_value = [make_vessel_row()]

        records = list_vessels(
            mmsi=419001342,
            name="ocean",
            ship_type="cargo",
            source="aisstream",
            minimum_latitude=10.0,
            maximum_latitude=15.0,
            minimum_longitude=75.0,
            maximum_longitude=85.0,
            observed_after=None,
            limit=5,
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["mmsi"], 419001342)

        query, parameters = cursor.execute.call_args.args

        self.assertIn("LEFT JOIN LATERAL", query)
        self.assertEqual(parameters["mmsi"], 419001342)
        self.assertEqual(parameters["name"], "ocean")
        self.assertEqual(parameters["source"], "aisstream")
        self.assertEqual(parameters["limit"], 5)

        connect_mock.assert_called_once_with(
            prompt_for_password=False,
        )

    @patch(
        "backend.app.services.vessels."
        "connect_to_database"
    )
    def test_database_failure_is_wrapped(
        self,
        connect_mock: MagicMock,
    ) -> None:
        """Convert psycopg failures into a service error."""
        connect_mock.side_effect = psycopg.OperationalError(
            "database unavailable"
        )

        with self.assertRaises(VesselsQueryError):
            list_vessels(
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


if __name__ == "__main__":
    unittest.main()
