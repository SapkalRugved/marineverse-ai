"""Tests for scheduled pipeline execution."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from backend.marine_data.automation.runner import (
    PIPELINES,
    ScheduledPipelineError,
    run_scheduled_pipeline,
)


class AutomationRunnerTests(unittest.TestCase):
    """Verify pipeline dispatch and locking."""

    @patch(
        "backend.marine_data.automation.runner."
        "release_pipeline_lock"
    )
    @patch(
        "backend.marine_data.automation.runner."
        "acquire_pipeline_lock",
        return_value=True,
    )
    @patch(
        "backend.marine_data.automation.runner."
        "subprocess.run"
    )
    @patch(
        "backend.marine_data.automation.runner."
        "connect_to_database"
    )
    def test_weather_pipeline_execution(
        self,
        connect_mock,
        subprocess_mock,
        _acquire_mock,
        release_mock,
    ) -> None:
        """Run the configured weather module."""
        connection = MagicMock()
        connect_mock.return_value.__enter__.return_value = (
            connection
        )
        subprocess_mock.return_value.returncode = 0

        result = run_scheduled_pipeline("weather")

        self.assertEqual(result, 0)
        command = subprocess_mock.call_args.args[0]
        self.assertEqual(command[0], __import__("sys").executable)
        self.assertEqual(command[1], "-m")
        self.assertEqual(
            command[2],
            PIPELINES["weather"].module,
        )
        release_mock.assert_called_once_with(
            connection,
            PIPELINES["weather"].advisory_lock_id,
        )

    @patch(
        "backend.marine_data.automation.runner."
        "release_pipeline_lock"
    )
    @patch(
        "backend.marine_data.automation.runner."
        "acquire_pipeline_lock",
        return_value=False,
    )
    @patch(
        "backend.marine_data.automation.runner."
        "subprocess.run"
    )
    @patch(
        "backend.marine_data.automation.runner."
        "connect_to_database"
    )
    def test_overlapping_pipeline_is_skipped(
        self,
        connect_mock,
        subprocess_mock,
        _acquire_mock,
        release_mock,
    ) -> None:
        """Skip execution when another instance holds the lock."""
        connect_mock.return_value.__enter__.return_value = (
            MagicMock()
        )

        result = run_scheduled_pipeline("ocean")

        self.assertEqual(result, 0)
        subprocess_mock.assert_not_called()
        release_mock.assert_not_called()

    @patch(
        "backend.marine_data.automation.runner."
        "release_pipeline_lock"
    )
    @patch(
        "backend.marine_data.automation.runner."
        "acquire_pipeline_lock",
        return_value=True,
    )
    @patch(
        "backend.marine_data.automation.runner."
        "subprocess.run"
    )
    @patch(
        "backend.marine_data.automation.runner."
        "connect_to_database"
    )
    def test_failed_pipeline_returns_exit_code(
        self,
        connect_mock,
        subprocess_mock,
        _acquire_mock,
        release_mock,
    ) -> None:
        """Return the child pipeline failure code."""
        connection = MagicMock()
        connect_mock.return_value.__enter__.return_value = (
            connection
        )
        subprocess_mock.return_value.returncode = 7

        result = run_scheduled_pipeline("weather")

        self.assertEqual(result, 7)
        release_mock.assert_called_once()

    def test_unknown_pipeline_is_rejected(self) -> None:
        """Reject an unconfigured pipeline name."""
        with self.assertRaises(ScheduledPipelineError):
            run_scheduled_pipeline("unknown")


if __name__ == "__main__":
    unittest.main()