"""Tests for complete AISStream pipeline orchestration."""

from __future__ import annotations

import unittest
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from backend.marine_data.ais import run_aisstream_pipeline


CAPTURE_STARTED = datetime(
    2026,
    10,
    18,
    8,
    0,
    tzinfo=timezone.utc,
)
CAPTURE_COMPLETED = datetime(
    2026,
    10,
    18,
    8,
    2,
    tzinfo=timezone.utc,
)


class AisPipelineTests(unittest.TestCase):
    """Validate live AIS orchestration without network access."""

    def setUp(self) -> None:
        self.arguments = SimpleNamespace(
            duration_seconds=120,
            max_events=250,
        )
        self.connection = MagicMock()

    def enter_common_patches(
        self,
        stack: ExitStack,
        *,
        api_key: str = "test-api-key",
        run_id: int = 101,
    ) -> dict[str, MagicMock]:
        """Patch common configuration and database operations."""
        parse_mock = stack.enter_context(
            patch.object(
                run_aisstream_pipeline,
                "parse_arguments",
                return_value=self.arguments,
            )
        )
        load_dotenv_mock = stack.enter_context(
            patch.object(
                run_aisstream_pipeline,
                "load_dotenv",
            )
        )
        getenv_mock = stack.enter_context(
            patch.object(
                run_aisstream_pipeline.os,
                "getenv",
                return_value=api_key,
            )
        )
        connect_mock = stack.enter_context(
            patch.object(
                run_aisstream_pipeline,
                "connect_to_database",
                return_value=self.connection,
            )
        )
        start_mock = stack.enter_context(
            patch.object(
                run_aisstream_pipeline,
                "start_ingestion_run",
                return_value=run_id,
            )
        )
        complete_mock = stack.enter_context(
            patch.object(
                run_aisstream_pipeline,
                "complete_ingestion_run",
            )
        )
        fail_mock = stack.enter_context(
            patch.object(
                run_aisstream_pipeline,
                "fail_ingestion_run",
            )
        )

        return {
            "parse": parse_mock,
            "load_dotenv": load_dotenv_mock,
            "getenv": getenv_mock,
            "connect": connect_mock,
            "start": start_mock,
            "complete": complete_mock,
            "fail": fail_mock,
        }

    def test_count_ais_data_events(self) -> None:
        """Exclude subscription confirmations from source counts."""
        events = [
            {
                "event": {
                    "MessageType": (
                        "SubscriptionConfirmation"
                    )
                }
            },
            {
                "event": {
                    "MessageType": "PositionReport"
                }
            },
            {
                "event": {
                    "MessageType": "ShipStaticData"
                }
            },
        ]

        count = (
            run_aisstream_pipeline.count_ais_data_events(
                events
            )
        )

        self.assertEqual(count, 2)

    def test_no_data_capture_is_successful_noop(self) -> None:
        """A confirmed quiet window succeeds without DB rows."""
        events = [
            {
                "event": {
                    "MessageType": (
                        "SubscriptionConfirmation"
                    )
                }
            }
        ]

        with ExitStack() as stack:
            mocks = self.enter_common_patches(stack)

            capture_mock = stack.enter_context(
                patch.object(
                    run_aisstream_pipeline,
                    "capture_events",
                    return_value=(
                        events,
                        CAPTURE_STARTED,
                        CAPTURE_COMPLETED,
                    ),
                )
            )
            retain_mock = stack.enter_context(
                patch.object(
                    run_aisstream_pipeline,
                    "retain_capture",
                    return_value=Path("capture.json"),
                )
            )
            read_mock = stack.enter_context(
                patch.object(
                    run_aisstream_pipeline,
                    "read_capture",
                )
            )
            transform_mock = stack.enter_context(
                patch.object(
                    run_aisstream_pipeline,
                    "transform_capture",
                )
            )
            load_mock = stack.enter_context(
                patch.object(
                    run_aisstream_pipeline,
                    "load_ais_records",
                )
            )

            exit_code = run_aisstream_pipeline.main()

        self.assertEqual(exit_code, 0)
        capture_mock.assert_called_once()
        retain_mock.assert_called_once()
        read_mock.assert_not_called()
        transform_mock.assert_not_called()
        load_mock.assert_not_called()
        mocks["complete"].assert_called_once_with(
            self.connection,
            run_id=101,
            records_read=0,
            records_written=0,
        )
        mocks["fail"].assert_not_called()
        self.assertEqual(self.connection.commit.call_count, 2)
        self.connection.close.assert_called_once()

    def test_data_capture_is_transformed_and_loaded(self) -> None:
        """A live data window completes transformation and loading."""
        events = [
            {
                "event": {
                    "MessageType": (
                        "SubscriptionConfirmation"
                    )
                }
            },
            {
                "event": {
                    "MessageType": "PositionReport"
                }
            },
            {
                "event": {
                    "MessageType": "ShipStaticData"
                }
            },
            {
                "event": {
                    "MessageType": "PositionReport"
                }
            },
        ]
        transformation_result = SimpleNamespace(
            source_events_read=3,
            vessel_records=(object(), object(), object()),
            position_records=(object(), object()),
            rejected_events=0,
            ignored_events=1,
            duplicates_removed=0,
        )
        load_result = SimpleNamespace(
            vessels_processed=3,
            positions_received=2,
            positions_inserted=2,
            rows_written=5,
        )

        with ExitStack() as stack:
            mocks = self.enter_common_patches(stack)

            stack.enter_context(
                patch.object(
                    run_aisstream_pipeline,
                    "capture_events",
                    return_value=(
                        events,
                        CAPTURE_STARTED,
                        CAPTURE_COMPLETED,
                    ),
                )
            )
            stack.enter_context(
                patch.object(
                    run_aisstream_pipeline,
                    "retain_capture",
                    return_value=Path("capture.json"),
                )
            )
            stack.enter_context(
                patch.object(
                    run_aisstream_pipeline,
                    "read_capture",
                    return_value={"source": "aisstream"},
                )
            )
            transform_mock = stack.enter_context(
                patch.object(
                    run_aisstream_pipeline,
                    "transform_capture",
                    return_value=transformation_result,
                )
            )
            load_mock = stack.enter_context(
                patch.object(
                    run_aisstream_pipeline,
                    "load_ais_records",
                    return_value=load_result,
                )
            )

            exit_code = run_aisstream_pipeline.main()

        self.assertEqual(exit_code, 0)
        transform_mock.assert_called_once_with(
            {"source": "aisstream"},
            ingested_at=CAPTURE_COMPLETED,
        )
        load_mock.assert_called_once_with(
            self.connection,
            transformation_result.vessel_records,
            transformation_result.position_records,
        )
        mocks["complete"].assert_called_once_with(
            self.connection,
            run_id=101,
            records_read=3,
            records_written=5,
        )
        mocks["fail"].assert_not_called()
        self.assertEqual(self.connection.commit.call_count, 2)
        self.connection.close.assert_called_once()

    def test_missing_api_key_records_failed_run(self) -> None:
        """A missing key fails after creating an audit record."""
        with ExitStack() as stack:
            mocks = self.enter_common_patches(
                stack,
                api_key="",
            )
            capture_mock = stack.enter_context(
                patch.object(
                    run_aisstream_pipeline,
                    "capture_events",
                )
            )

            exit_code = run_aisstream_pipeline.main()

        self.assertEqual(exit_code, 1)
        capture_mock.assert_not_called()
        mocks["complete"].assert_not_called()
        mocks["fail"].assert_called_once_with(
            self.connection,
            run_id=101,
            records_read=0,
            error_message=(
                "AISSTREAM_API_KEY is not configured."
            ),
        )
        self.connection.rollback.assert_called_once()
        self.assertEqual(self.connection.commit.call_count, 2)
        self.connection.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()