"""Integration tests for ingestion run audit logging."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from backend.marine_data.database import connect_to_database
from backend.marine_data.ingestion_runs import (
    complete_ingestion_run,
    fail_ingestion_run,
    start_ingestion_run,
)


TEST_PIPELINE = "test_ingestion_runs"
TEST_SOURCE = "integration_test"


class IngestionRunsIntegrationTests(unittest.TestCase):
    """Verify ingestion run state transitions in PostgreSQL."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.connection = connect_to_database()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.connection.rollback()

        with cls.connection.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM ingestion_runs
                WHERE pipeline = %s
                  AND source = %s;
                """,
                (TEST_PIPELINE, TEST_SOURCE),
            )

        cls.connection.commit()
        cls.connection.close()

    def setUp(self) -> None:
        self.connection.rollback()

        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM ingestion_runs
                WHERE pipeline = %s
                  AND source = %s;
                """,
                (TEST_PIPELINE, TEST_SOURCE),
            )

        self.connection.commit()

    def fetch_run(self, run_id: int) -> tuple:
        """Fetch one audit record by primary key."""
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    pipeline,
                    source,
                    status,
                    records_read,
                    records_written,
                    error_message,
                    started_at,
                    completed_at
                FROM ingestion_runs
                WHERE run_id = %s;
                """,
                (run_id,),
            )
            row = cursor.fetchone()

        self.assertIsNotNone(row)
        return row

    def test_successful_run_transition(self) -> None:
        started_at = datetime(
            2026, 10, 8, 12, 0, tzinfo=timezone.utc
        )
        completed_at = datetime(
            2026, 10, 8, 12, 1, tzinfo=timezone.utc
        )

        run_id = start_ingestion_run(
            self.connection,
            TEST_PIPELINE,
            TEST_SOURCE,
            started_at,
        )
        self.connection.commit()

        complete_ingestion_run(
            self.connection,
            run_id,
            records_read=100,
            records_written=75,
            completed_at=completed_at,
        )
        self.connection.commit()

        row = self.fetch_run(run_id)

        self.assertEqual(TEST_PIPELINE, row[0])
        self.assertEqual(TEST_SOURCE, row[1])
        self.assertEqual("success", row[2])
        self.assertEqual(100, row[3])
        self.assertEqual(75, row[4])
        self.assertIsNone(row[5])
        self.assertEqual(started_at, row[6])
        self.assertEqual(completed_at, row[7])

    def test_failed_run_transition(self) -> None:
        run_id = start_ingestion_run(
            self.connection,
            TEST_PIPELINE,
            TEST_SOURCE,
        )
        self.connection.commit()

        fail_ingestion_run(
            self.connection,
            run_id,
            records_read=25,
            error_message="Synthetic ingestion failure",
        )
        self.connection.commit()

        row = self.fetch_run(run_id)

        self.assertEqual("failed", row[2])
        self.assertEqual(25, row[3])
        self.assertEqual(0, row[4])
        self.assertEqual(
            "Synthetic ingestion failure",
            row[5],
        )
        self.assertIsNotNone(row[7])


if __name__ == "__main__":
    unittest.main()