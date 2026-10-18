"""Tests for the bounded AISStream probe."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from backend.marine_data.ais import probe_aisstream
from backend.marine_data.ais.probe_aisstream import (
    AisProbeError,
    build_subscription,
    decode_event,
    positive_integer,
    retain_capture,
)


class AisProbeTests(unittest.TestCase):
    """Validate non-network AISStream probe behavior."""

    def test_subscription_contains_required_filters(self) -> None:
        """Build the expected AISStream subscription."""
        subscription = build_subscription("temporary-test-key")

        self.assertEqual(
            subscription["APIKey"],
            "temporary-test-key",
        )
        self.assertEqual(
            subscription["BoundingBoxes"],
            probe_aisstream.BOUNDING_BOXES,
        )
        self.assertEqual(
            subscription["FilterMessageTypes"],
            probe_aisstream.MESSAGE_TYPES,
        )

    def test_binary_frame_is_decoded(self) -> None:
        """AISStream binary UTF-8 frames are supported."""
        event = decode_event(
            b'{"MessageType":"PositionReport"}'
        )

        self.assertEqual(
            event["MessageType"],
            "PositionReport",
        )

    def test_text_frame_is_decoded(self) -> None:
        """Text WebSocket frames are also supported."""
        event = decode_event(
            '{"MessageType":"ShipStaticData"}'
        )

        self.assertEqual(
            event["MessageType"],
            "ShipStaticData",
        )

    def test_non_object_frame_is_rejected(self) -> None:
        """A JSON array is not a valid AIS event."""
        with self.assertRaises(AisProbeError):
            decode_event("[]")

    def test_positive_integer(self) -> None:
        """Positive command-line limits are accepted."""
        self.assertEqual(positive_integer("60"), 60)

    def test_nonpositive_integer_is_rejected(self) -> None:
        """Zero and negative capture limits are rejected."""
        for value in ("0", "-1"):
            with self.subTest(value=value):
                with self.assertRaises(
                    argparse.ArgumentTypeError
                ):
                    positive_integer(value)

    def test_retained_capture_excludes_credentials(self) -> None:
        """Raw files contain subscription metadata, not API keys."""
        started_at = datetime(
            2026,
            10,
            18,
            4,
            30,
            tzinfo=timezone.utc,
        )
        completed_at = datetime(
            2026,
            10,
            18,
            4,
            31,
            tzinfo=timezone.utc,
        )
        events = [
            {
                "received_at": started_at.isoformat(),
                "event": {
                    "MessageType": (
                        "SubscriptionConfirmation"
                    ),
                },
            },
            {
                "received_at": completed_at.isoformat(),
                "event": {
                    "MessageType": "PositionReport",
                },
            },
        ]

        with tempfile.TemporaryDirectory() as directory:
            raw_directory = Path(directory)

            with patch.object(
                probe_aisstream,
                "RAW_DIRECTORY",
                raw_directory,
            ):
                output_path = retain_capture(
                    started_at=started_at,
                    completed_at=completed_at,
                    duration_seconds=60,
                    events=events,
                )

            payload_text = output_path.read_text(
                encoding="utf-8"
            )
            payload = json.loads(payload_text)

        self.assertEqual(
            output_path.name,
            "aisstream_india_probe_20261018T043000Z.json",
        )
        self.assertEqual(payload["event_count"], 2)
        self.assertEqual(payload["ais_event_count"], 1)
        self.assertNotIn("APIKey", payload_text)
        self.assertNotIn(
            "temporary-test-key",
            payload_text,
        )


    def test_environment_data_root_is_used(self) -> None:
        """Store AIS captures under the configured external data root."""

        started_at = datetime(
            2026, 10, 18, 4, 30, tzinfo=timezone.utc
        )

        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(
                os.environ,
                {"MARINEVERSE_DATA_DIR": directory},
            ):
                output = retain_capture(
                    started_at=started_at,
                    completed_at=started_at,
                    duration_seconds=60,
                    events=[],
                )

            expected = (
                Path(directory).resolve()
                / "raw"
                / "ais"
                / "aisstream_india_probe_20261018T043000Z.json"
            )

            self.assertEqual(output, expected)
            self.assertTrue(output.exists())

    def test_explicit_output_directory_overrides_environment(self) -> None:
        """Explicit capture directories take precedence."""

        started_at = datetime(
            2026, 10, 18, 4, 30, tzinfo=timezone.utc
        )

        with tempfile.TemporaryDirectory() as environment_root:
            with tempfile.TemporaryDirectory() as explicit_directory:
                with patch.dict(
                    os.environ,
                    {"MARINEVERSE_DATA_DIR": environment_root},
                ):
                    output = retain_capture(
                        started_at=started_at,
                        completed_at=started_at,
                        duration_seconds=60,
                        events=[],
                        output_directory=Path(explicit_directory),
                    )

                self.assertEqual(
                    output.parent,
                    Path(explicit_directory),
                )
                self.assertTrue(output.exists())

if __name__ == "__main__":
    unittest.main()