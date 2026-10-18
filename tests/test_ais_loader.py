"""Integration tests for the AIS PostgreSQL/PostGIS loader."""

from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from backend.marine_data.ais.loader import (
    AisDatabaseLoadError,
    load_ais_records,
)
from backend.marine_data.ais.transformer import (
    VesselPositionRecord,
    VesselRecord,
)
from backend.marine_data.database import connect_to_database


class AisLoaderIntegrationTests(unittest.TestCase):
    """Verify atomic and idempotent AIS database loading."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.connection = connect_to_database()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.connection.close()

    def setUp(self) -> None:
        self.mmsi = (
            900_000_000
            + uuid4().int % 99_999_999
        )
        self.source = "integration-test-ais"
        self.updated_at = datetime(
            2026,
            10,
            18,
            5,
            0,
            tzinfo=timezone.utc,
        )

        self.vessel = VesselRecord(
            mmsi=self.mmsi,
            imo=9_936_989,
            name="INTEGRATION TEST VESSEL",
            ship_type="cargo",
            length_m=199.0,
            width_m=35.0,
            source=self.source,
            updated_at=self.updated_at,
        )

        self.position = VesselPositionRecord(
            mmsi=self.mmsi,
            observed_at=datetime(
                2026,
                10,
                18,
                4,
                59,
                tzinfo=timezone.utc,
            ),
            latitude=18.9448,
            longitude=72.9471,
            speed_mps=5.14444,
            course_deg=180.0,
            heading_deg=179.0,
            navigation_status="underway_using_engine",
            source=self.source,
            ingested_at=self.updated_at,
        )

        self.delete_test_records()

    def tearDown(self) -> None:
        self.connection.rollback()
        self.delete_test_records()

    def delete_test_records(self) -> None:
        """Delete positions before their referenced vessel."""
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM vessel_positions
                WHERE vessel_id IN (
                    SELECT vessel_id
                    FROM vessels
                    WHERE mmsi = %s
                );
                """,
                (self.mmsi,),
            )
            cursor.execute(
                """
                DELETE FROM vessels
                WHERE mmsi = %s;
                """,
                (self.mmsi,),
            )

        self.connection.commit()

    def test_insert_creates_correct_postgis_point(self) -> None:
        """Insert a vessel and its geographic position."""
        result = load_ais_records(
            self.connection,
            [self.vessel],
            [self.position],
        )
        self.connection.commit()

        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    vessel.mmsi,
                    position.latitude,
                    position.longitude,
                    ST_X(position.location::geometry),
                    ST_Y(position.location::geometry),
                    ST_SRID(position.location::geometry)
                FROM vessel_positions AS position
                JOIN vessels AS vessel
                  ON vessel.vessel_id = position.vessel_id
                WHERE vessel.mmsi = %s;
                """,
                (self.mmsi,),
            )
            row = cursor.fetchone()

        self.assertEqual(result.vessels_processed, 1)
        self.assertEqual(result.positions_received, 1)
        self.assertEqual(result.positions_inserted, 1)
        self.assertEqual(result.rows_written, 2)

        self.assertIsNotNone(row)
        self.assertEqual(row[0], self.mmsi)
        self.assertAlmostEqual(
            row[1],
            self.position.latitude,
        )
        self.assertAlmostEqual(
            row[2],
            self.position.longitude,
        )
        self.assertAlmostEqual(
            row[3],
            self.position.longitude,
        )
        self.assertAlmostEqual(
            row[4],
            self.position.latitude,
        )
        self.assertEqual(row[5], 4326)

    def test_identical_rerun_does_not_duplicate_position(
        self,
    ) -> None:
        """A retained capture can be loaded repeatedly."""
        first_result = load_ais_records(
            self.connection,
            [self.vessel],
            [self.position],
        )
        self.connection.commit()

        second_result = load_ais_records(
            self.connection,
            [self.vessel],
            [self.position],
        )
        self.connection.commit()

        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM vessel_positions AS position
                JOIN vessels AS vessel
                  ON vessel.vessel_id = position.vessel_id
                WHERE vessel.mmsi = %s;
                """,
                (self.mmsi,),
            )
            position_count = cursor.fetchone()[0]

        self.assertEqual(first_result.positions_inserted, 1)
        self.assertEqual(second_result.positions_inserted, 0)
        self.assertEqual(position_count, 1)

    def test_static_data_enriches_stub_and_preserves_id(
        self,
    ) -> None:
        """Static AIS data enriches a position-only vessel."""
        stub = VesselRecord(
            mmsi=self.mmsi,
            imo=None,
            name="POSITION NAME",
            ship_type=None,
            length_m=None,
            width_m=None,
            source=self.source,
            updated_at=self.updated_at,
        )

        load_ais_records(
            self.connection,
            [stub],
            [self.position],
        )
        self.connection.commit()

        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT vessel_id
                FROM vessels
                WHERE mmsi = %s;
                """,
                (self.mmsi,),
            )
            original_vessel_id = cursor.fetchone()[0]

        static_record = replace(
            self.vessel,
            updated_at=(
                self.updated_at + timedelta(minutes=5)
            ),
        )

        result = load_ais_records(
            self.connection,
            [static_record],
            [],
        )
        self.connection.commit()

        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    vessel_id,
                    imo,
                    name,
                    ship_type,
                    length_m,
                    width_m
                FROM vessels
                WHERE mmsi = %s;
                """,
                (self.mmsi,),
            )
            row = cursor.fetchone()

        self.assertEqual(result.positions_inserted, 0)
        self.assertEqual(row[0], original_vessel_id)
        self.assertEqual(row[1], self.vessel.imo)
        self.assertEqual(row[2], self.vessel.name)
        self.assertEqual(row[3], "cargo")
        self.assertAlmostEqual(row[4], 199.0)
        self.assertAlmostEqual(row[5], 35.0)

    def test_stub_does_not_erase_static_data(self) -> None:
        """Later position-only stubs preserve known details."""
        load_ais_records(
            self.connection,
            [self.vessel],
            [],
        )
        self.connection.commit()

        later_stub = VesselRecord(
            mmsi=self.mmsi,
            imo=None,
            name="TEMPORARY POSITION NAME",
            ship_type=None,
            length_m=None,
            width_m=None,
            source=self.source,
            updated_at=(
                self.updated_at + timedelta(minutes=10)
            ),
        )

        load_ais_records(
            self.connection,
            [later_stub],
            [],
        )
        self.connection.commit()

        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    imo,
                    name,
                    ship_type,
                    length_m,
                    width_m,
                    updated_at
                FROM vessels
                WHERE mmsi = %s;
                """,
                (self.mmsi,),
            )
            row = cursor.fetchone()

        self.assertEqual(row[0], self.vessel.imo)
        self.assertEqual(row[1], self.vessel.name)
        self.assertEqual(row[2], self.vessel.ship_type)
        self.assertAlmostEqual(row[3], 199.0)
        self.assertAlmostEqual(row[4], 35.0)
        self.assertEqual(
            row[5],
            later_stub.updated_at,
        )

    def test_position_requires_staged_vessel(self) -> None:
        """Reject unresolved position-to-vessel relationships."""
        different_position = replace(
            self.position,
            mmsi=self.mmsi + 1,
        )

        with self.assertRaises(AisDatabaseLoadError):
            load_ais_records(
                self.connection,
                [self.vessel],
                [different_position],
            )

    def test_empty_vessel_records_is_failure(self) -> None:
        """An empty AIS load must not silently succeed."""
        with self.assertRaises(AisDatabaseLoadError):
            load_ais_records(
                self.connection,
                [],
                [],
            )


if __name__ == "__main__":
    unittest.main()