"""Integration tests for the Copernicus ocean database loader."""

from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from backend.marine_data.database import connect_to_database
from backend.marine_data.ocean.loader import load_ocean_records
from backend.marine_data.ocean.transformer import OceanRecord


class OceanLoaderIntegrationTests(unittest.TestCase):
    """Verify idempotent PostGIS ocean loading."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.connection = connect_to_database()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.connection.close()

    def setUp(self) -> None:
        self.source = "integration-test"
        self.source_dataset = f"ocean-test-{uuid4()}"

        self.record = OceanRecord(
            valid_time=datetime(
                2026,
                10,
                7,
                12,
                0,
                tzinfo=timezone.utc,
            ),
            latitude=18.75,
            longitude=72.35,
            depth_m=0.5,
            current_u_mps=0.3,
            current_v_mps=0.4,
            current_speed_mps=0.5,
            current_direction_deg=36.8698976,
            sea_surface_temperature_c=28.5,
            wave_height_m=1.2,
            wave_direction_deg=240.0,
            wave_period_s=6.5,
            is_forecast=False,
            source=self.source,
            source_dataset=self.source_dataset,
            ingested_at=datetime.now(timezone.utc),
        )

        self.delete_test_records()

    def tearDown(self) -> None:
        self.connection.rollback()
        self.delete_test_records()

    def delete_test_records(self) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM ocean_conditions
                WHERE source = %s
                  AND source_dataset = %s;
                """,
                (self.source, self.source_dataset),
            )

        self.connection.commit()

    def test_insert_creates_correct_postgis_point(self) -> None:
        processed = load_ocean_records(
            self.connection,
            [self.record],
        )
        self.connection.commit()

        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    latitude,
                    longitude,
                    ST_X(location::geometry),
                    ST_Y(location::geometry),
                    ST_SRID(location::geometry)
                FROM ocean_conditions
                WHERE source = %s
                  AND source_dataset = %s;
                """,
                (self.source, self.source_dataset),
            )
            row = cursor.fetchone()

        self.assertEqual(processed, 1)
        self.assertIsNotNone(row)
        self.assertAlmostEqual(row[0], self.record.latitude)
        self.assertAlmostEqual(row[1], self.record.longitude)
        self.assertAlmostEqual(row[2], self.record.longitude)
        self.assertAlmostEqual(row[3], self.record.latitude)
        self.assertEqual(row[4], 4326)

    def test_identical_rerun_does_not_duplicate(self) -> None:
        load_ocean_records(self.connection, [self.record])
        self.connection.commit()

        load_ocean_records(self.connection, [self.record])
        self.connection.commit()

        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM ocean_conditions
                WHERE source = %s
                  AND source_dataset = %s;
                """,
                (self.source, self.source_dataset),
            )
            count = cursor.fetchone()[0]

        self.assertEqual(count, 1)

    def test_update_preserves_ocean_id(self) -> None:
        load_ocean_records(self.connection, [self.record])
        self.connection.commit()

        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT ocean_id
                FROM ocean_conditions
                WHERE source = %s
                  AND source_dataset = %s;
                """,
                (self.source, self.source_dataset),
            )
            original_id = cursor.fetchone()[0]

        updated_record = replace(
            self.record,
            wave_height_m=2.75,
            sea_surface_temperature_c=29.25,
            ingested_at=(
                self.record.ingested_at + timedelta(minutes=5)
            ),
        )

        load_ocean_records(
            self.connection,
            [updated_record],
        )
        self.connection.commit()

        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    ocean_id,
                    wave_height_m,
                    sea_surface_temperature_c
                FROM ocean_conditions
                WHERE source = %s
                  AND source_dataset = %s;
                """,
                (self.source, self.source_dataset),
            )
            row = cursor.fetchone()

        self.assertEqual(row[0], original_id)
        self.assertAlmostEqual(row[1], 2.75)
        self.assertAlmostEqual(row[2], 29.25)


if __name__ == "__main__":
    unittest.main()