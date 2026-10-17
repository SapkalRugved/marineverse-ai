"""Tests for marine dataset freshness calculations."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from backend.app.services.freshness import (
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


if __name__ == "__main__":
    unittest.main()