"""Tests for automated data-retention policies."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from backend.marine_data.automation.retention import (
    POLICIES,
    execute_retention,
)


CHECKED_AT = datetime(
    2026,
    10,
    18,
    tzinfo=timezone.utc,
)


class AutomationRetentionTests(unittest.TestCase):
    """Verify safe retention behavior."""

    def create_connection(
        self,
        counts: list[int],
    ) -> tuple[MagicMock, MagicMock]:
        """Create a mocked database connection and cursor."""
        connection = MagicMock()
        cursor = MagicMock()

        connection.cursor.return_value.__enter__.return_value = (
            cursor
        )
        cursor.fetchone.side_effect = [
            (count,)
            for count in counts
        ]
        cursor.rowcount = 5

        return connection, cursor

    def test_balanced_retention_periods(self) -> None:
        """Use selected weather and ocean retention periods."""
        policies = {
            policy.dataset: policy.retention_days
            for policy in POLICIES
        }

        self.assertEqual(policies["weather"], 30)
        self.assertEqual(policies["ocean"], 14)

    def test_dry_run_does_not_delete(self) -> None:
        """Default evaluation must not delete records."""
        connection, cursor = self.create_connection(
            [12, 34]
        )

        results = execute_retention(
            connection,
            checked_at=CHECKED_AT,
            apply_changes=False,
        )

        self.assertEqual(
            [result["candidate_records"] for result in results],
            [12, 34],
        )
        self.assertEqual(
            [result["deleted_records"] for result in results],
            [0, 0],
        )
        self.assertEqual(cursor.execute.call_count, 2)

        for call in cursor.execute.call_args_list:
            self.assertNotIn(
                "DELETE",
                call.args[0].upper(),
            )

    def test_apply_executes_deletions(self) -> None:
        """Explicit apply mode executes retention deletion."""
        connection, cursor = self.create_connection(
            [5, 8]
        )

        results = execute_retention(
            connection,
            checked_at=CHECKED_AT,
            apply_changes=True,
        )

        self.assertEqual(cursor.execute.call_count, 4)
        self.assertTrue(
            all(result["applied"] for result in results)
        )
        self.assertTrue(
            all(
                result["deleted_records"] == 5
                for result in results
            )
        )

    def test_latest_snapshot_is_protected(self) -> None:
        """Every delete query must preserve the newest snapshot."""
        for policy in POLICIES:
            normalized_sql = " ".join(
                policy.delete_sql.split()
            ).upper()

            self.assertIn(
                "SELECT MAX(VALID_TIME)",
                normalized_sql,
            )


if __name__ == "__main__":
    unittest.main()