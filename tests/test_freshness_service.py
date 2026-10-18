"""Tests for marine dataset freshness calculations."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from backend.app.services.freshness import (
    SELECT_FRESHNESS_SQL,
    build_freshness_report,
    calculate_dataset_freshness,
)


CHECKED_AT = datetime(
    2026,
    10,
    18,
    tzinfo=timezone.utc,
)


class FreshnessServiceTests(unittest.TestCase):
    """Verify freshness status calculations."""

    def test_fresh_dataset(self) -> None:
        """Classify data inside its freshness threshold."""
        result = calculate_dataset_freshness(
            {
                "dataset": "weather",
                "latest_valid_time": (
                    CHECKED_AT - timedelta(minutes=10)
                ),
                "latest_ingested_at": CHECKED_AT,
                "last_successful_run_at": CHECKED_AT,
            },
            CHECKED_AT,
        )

        self.assertEqual(result["status"], "fresh")
        self.assertEqual(result["age_seconds"], 600.0)

    def test_stale_dataset(self) -> None:
        """Classify data older than its threshold."""
        result = calculate_dataset_freshness(
            {
                "dataset": "ocean",
                "latest_valid_time": (
                    CHECKED_AT - timedelta(hours=10)
                ),
                "latest_ingested_at": CHECKED_AT,
                "last_successful_run_at": CHECKED_AT,
            },
            CHECKED_AT,
        )

        self.assertEqual(result["status"], "stale")

    def test_missing_dataset(self) -> None:
        """Classify a dataset without timestamps as missing."""
        result = calculate_dataset_freshness(
            {
                "dataset": "ports",
                "latest_valid_time": None,
                "latest_ingested_at": None,
                "last_successful_run_at": None,
            },
            CHECKED_AT,
        )

        self.assertEqual(result["status"], "missing")
        self.assertIsNone(result["age_seconds"])

    def test_overall_status_uses_worst_status(self) -> None:
        """Report stale when any dataset is stale."""
        rows = [
            {
                "dataset": "ports",
                "latest_valid_time": None,
                "latest_ingested_at": CHECKED_AT,
                "last_successful_run_at": CHECKED_AT,
            },
            {
                "dataset": "weather",
                "latest_valid_time": (
                    CHECKED_AT - timedelta(hours=1)
                ),
                "latest_ingested_at": CHECKED_AT,
                "last_successful_run_at": CHECKED_AT,
            },
        ]

        report = build_freshness_report(
            rows,
            CHECKED_AT,
        )

        self.assertEqual(report["status"], "stale")


    def test_fresh_ais_dataset(self) -> None:
        """Classify recent AIS positions as fresh."""
        result = calculate_dataset_freshness(
            {
                "dataset": "ais",
                "latest_valid_time": (
                    CHECKED_AT - timedelta(minutes=20)
                ),
                "latest_ingested_at": CHECKED_AT,
                "last_successful_run_at": CHECKED_AT,
            },
            CHECKED_AT,
        )

        self.assertEqual(result["status"], "fresh")
        self.assertEqual(
            result["maximum_age_seconds"],
            1800,
        )

    def test_stale_ais_dataset(self) -> None:
        """Classify old AIS positions as stale."""
        result = calculate_dataset_freshness(
            {
                "dataset": "ais",
                "latest_valid_time": (
                    CHECKED_AT - timedelta(minutes=31)
                ),
                "latest_ingested_at": CHECKED_AT,
                "last_successful_run_at": CHECKED_AT,
            },
            CHECKED_AT,
        )

        self.assertEqual(result["status"], "stale")
        self.assertEqual(result["age_seconds"], 1860.0)

    def test_ais_query_uses_live_positions(self) -> None:
        """Read freshness from live AIS positions and runs."""
        self.assertIn(
            "'ais'::text AS dataset",
            SELECT_FRESHNESS_SQL,
        )
        self.assertIn(
            "FROM vessel_positions",
            SELECT_FRESHNESS_SQL,
        )
        self.assertIn(
            "WHERE source = 'aisstream'",
            SELECT_FRESHNESS_SQL,
        )
        self.assertIn(
            "pipeline = 'aisstream_india'",
            SELECT_FRESHNESS_SQL,
        )

if __name__ == "__main__":
    unittest.main()