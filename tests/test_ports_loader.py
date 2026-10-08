"""Integration tests for the PostgreSQL/PostGIS ports loader."""

from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from psycopg import Connection

from backend.marine_data.database import connect_to_database
from backend.marine_data.ports.loader import load_port_records
from backend.marine_data.ports.transformer import PortRecord


TEST_SOURCE = "openstreetmap"
TEST_SOURCE_ID = "node/999999999001"
TEST_TIME = datetime(
    2026,
    10,
    8,
    11,
    0,
    tzinfo=timezone.utc,
)


class PortsLoaderIntegrationTests(unittest.TestCase):
    """Verify insertion, PostGIS geography and idempotency."""

    connection: Connection

    @classmethod
    def setUpClass(cls) -> None:
        cls.connection = connect_to_database()

        with cls.connection.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM ports
                WHERE source = %s
                  AND source_id = %s;
                """,
                (TEST_SOURCE, TEST_SOURCE_ID),
            )

        cls.connection.commit()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.connection.rollback()

        with cls.connection.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM ports
                WHERE source = %s
                  AND source_id = %s;
                """,
                (TEST_SOURCE, TEST_SOURCE_ID),
            )

        cls.connection.commit()
        cls.connection.close()

    def setUp(self) -> None:
        self.connection.rollback()

    def tearDown(self) -> None:
        self.connection.rollback()

    def make_record(self) -> PortRecord:
        """Create one synthetic but contract-valid port."""
        return PortRecord(
            source_id=TEST_SOURCE_ID,
            name="MarineVerse Integration Test Port",
            country="India",
            port_type="harbour",
            latitude=18.949,
            longitude=72.838,
            source=TEST_SOURCE,
            updated_at=TEST_TIME,
        )

    def fetch_test_row(self) -> tuple[Any, ...]:
        """Fetch the synthetic test row from the active transaction."""
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    port_id,
                    source_id,
                    name,
                    latitude,
                    longitude,
                    ST_SRID(location::geometry),
                    ST_X(location::geometry),
                    ST_Y(location::geometry)
                FROM ports
                WHERE source = %s
                  AND source_id = %s;
                """,
                (TEST_SOURCE, TEST_SOURCE_ID),
            )
            row = cursor.fetchone()

        if row is None:
            self.fail("Expected integration-test port was not found.")

        return row

    def test_insert_creates_correct_postgis_point(self) -> None:
        record = self.make_record()

        rows_processed = load_port_records(
            self.connection,
            [record],
        )
        row = self.fetch_test_row()

        self.assertEqual(rows_processed, 1)
        self.assertEqual(row[1], TEST_SOURCE_ID)
        self.assertEqual(row[2], record.name)
        self.assertEqual(row[3], record.latitude)
        self.assertEqual(row[4], record.longitude)
        self.assertEqual(row[5], 4326)
        self.assertAlmostEqual(row[6], record.longitude)
        self.assertAlmostEqual(row[7], record.latitude)

    def test_identical_rerun_does_not_duplicate(self) -> None:
        record = self.make_record()

        load_port_records(self.connection, [record])
        first_row = self.fetch_test_row()

        load_port_records(self.connection, [record])
        second_row = self.fetch_test_row()

        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM ports
                WHERE source = %s
                  AND source_id = %s;
                """,
                (TEST_SOURCE, TEST_SOURCE_ID),
            )
            count = cursor.fetchone()[0]

        self.assertEqual(count, 1)
        self.assertEqual(first_row[0], second_row[0])

    def test_update_preserves_port_id(self) -> None:
        original_record = self.make_record()
        updated_record = replace(
            original_record,
            name="Updated Integration Test Port",
            latitude=19.001,
            longitude=72.901,
        )

        load_port_records(self.connection, [original_record])
        original_row = self.fetch_test_row()

        load_port_records(self.connection, [updated_record])
        updated_row = self.fetch_test_row()

        self.assertEqual(original_row[0], updated_row[0])
        self.assertEqual(
            updated_row[2],
            "Updated Integration Test Port",
        )
        self.assertEqual(updated_row[3], 19.001)
        self.assertEqual(updated_row[4], 72.901)
        self.assertAlmostEqual(updated_row[6], 72.901)
        self.assertAlmostEqual(updated_row[7], 19.001)


if __name__ == "__main__":
    unittest.main()