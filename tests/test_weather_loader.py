"""Integration tests for loading weather into PostGIS."""

from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from backend.marine_data.database import connect_to_database
from backend.marine_data.weather.loader import load_weather_records
from backend.marine_data.weather.transformer import WeatherRecord


TEST_SOURCE = "weather-loader-test"
TEST_DATASET = "integration-test"


class WeatherLoaderIntegrationTests(unittest.TestCase):
    """Verify weather inserts, updates, and geography."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.connection = connect_to_database()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.connection.rollback()

        with cls.connection.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM weather_conditions
                WHERE source = %s
                  AND source_dataset = %s;
                """,
                (TEST_SOURCE, TEST_DATASET),
            )

        cls.connection.commit()
        cls.connection.close()

    def setUp(self) -> None:
        self.connection.rollback()

        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM weather_conditions
                WHERE source = %s
                  AND source_dataset = %s;
                """,
                (TEST_SOURCE, TEST_DATASET),
            )

        self.connection.commit()

        self.record = WeatherRecord(
            valid_time=datetime(
                2026,
                10,
                8,
                18,
                45,
                tzinfo=timezone.utc,
            ),
            latitude=18.9447587,
            longitude=72.9470922,
            air_temperature_c=27.5,
            pressure_hpa=1013.2,
            precipitation_mm=0.0,
            wind_speed_mps=1.42,
            wind_direction_deg=51.0,
            wind_gust_mps=2.3,
            is_forecast=False,
            source=TEST_SOURCE,
            source_dataset=TEST_DATASET,
            ingested_at=datetime(
                2026,
                10,
                8,
                19,
                0,
                tzinfo=timezone.utc,
            ),
        )

    def fetch_identity(self) -> tuple[int, int]:
        """Return the record count and stable weather ID."""
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*), MIN(weather_id)
                FROM weather_conditions
                WHERE source = %s
                  AND source_dataset = %s;
                """,
                (TEST_SOURCE, TEST_DATASET),
            )
            row = cursor.fetchone()

        self.assertIsNotNone(row)
        return int(row[0]), int(row[1])

    def test_insert_creates_correct_postgis_point(self) -> None:
        processed = load_weather_records(
            self.connection,
            [self.record],
        )
        self.connection.commit()

        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    ST_SRID(location::geometry),
                    ST_X(location::geometry),
                    ST_Y(location::geometry)
                FROM weather_conditions
                WHERE source = %s
                  AND source_dataset = %s;
                """,
                (TEST_SOURCE, TEST_DATASET),
            )
            row = cursor.fetchone()

        self.assertEqual(1, processed)
        self.assertIsNotNone(row)
        self.assertEqual(4326, row[0])
        self.assertAlmostEqual(
            self.record.longitude,
            row[1],
        )
        self.assertAlmostEqual(
            self.record.latitude,
            row[2],
        )

    def test_identical_rerun_does_not_duplicate(self) -> None:
        load_weather_records(self.connection, [self.record])
        self.connection.commit()
        first_count, first_id = self.fetch_identity()

        load_weather_records(self.connection, [self.record])
        self.connection.commit()
        second_count, second_id = self.fetch_identity()

        self.assertEqual(1, first_count)
        self.assertEqual(1, second_count)
        self.assertEqual(first_id, second_id)

    def test_update_preserves_weather_id(self) -> None:
        load_weather_records(self.connection, [self.record])
        self.connection.commit()
        _, original_id = self.fetch_identity()

        changed_record = replace(
            self.record,
            air_temperature_c=28.75,
            pressure_hpa=1012.4,
            ingested_at=(
                self.record.ingested_at
                + timedelta(minutes=15)
            ),
        )

        load_weather_records(
            self.connection,
            [changed_record],
        )
        self.connection.commit()

        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    weather_id,
                    air_temperature_c,
                    pressure_hpa,
                    ingested_at
                FROM weather_conditions
                WHERE source = %s
                  AND source_dataset = %s;
                """,
                (TEST_SOURCE, TEST_DATASET),
            )
            row = cursor.fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(original_id, row[0])
        self.assertAlmostEqual(28.75, row[1])
        self.assertAlmostEqual(1012.4, row[2])
        self.assertEqual(changed_record.ingested_at, row[3])


if __name__ == "__main__":
    unittest.main()