"""Tests for AISStream event transformation."""

from __future__ import annotations

import copy
import unittest
from datetime import datetime, timezone

from backend.marine_data.ais.transformer import (
    AisTransformationError,
    KNOTS_TO_METRES_PER_SECOND,
    parse_aisstream_time,
    transform_capture,
)


INGESTED_AT = datetime(
    2026,
    10,
    18,
    5,
    0,
    tzinfo=timezone.utc,
)

MMSI = 563_192_600


def metadata(
    *,
    mmsi: int = MMSI,
    timestamp: str = (
        "2026-10-18 04:33:02.291670819 +0000 UTC"
    ),
) -> dict:
    """Build representative AISStream metadata."""
    return {
        "MMSI": mmsi,
        "MMSI_String": str(mmsi),
        "ShipName": "TEST VESSEL",
        "latitude": 13.09484,
        "longitude": 80.30185,
        "time_utc": timestamp,
    }


def position_event(
    *,
    mmsi: int = MMSI,
    latitude: float = 13.094836666666668,
    longitude: float = 80.30184666666668,
    message_type: str = "PositionReport",
) -> dict:
    """Build a supported AIS position event."""
    body = {
        "MessageID": 1,
        "RepeatIndicator": 0,
        "UserID": mmsi,
        "Valid": True,
        "Sog": 10.0,
        "Longitude": longitude,
        "Latitude": latitude,
        "Cog": 292.4,
        "TrueHeading": 203,
        "Timestamp": 2,
    }

    if message_type == "PositionReport":
        body["NavigationalStatus"] = 5

    return {
        "received_at": "2026-10-18T04:33:03+00:00",
        "event": {
            "MetaData": metadata(mmsi=mmsi),
            "MessageType": message_type,
            "Message": {
                message_type: body,
            },
        },
    }


def static_event(
    *,
    mmsi: int = MMSI,
) -> dict:
    """Build a representative ShipStaticData event."""
    return {
        "received_at": "2026-10-18T04:33:03+00:00",
        "event": {
            "MetaData": metadata(mmsi=mmsi),
            "MessageType": "ShipStaticData",
            "Message": {
                "ShipStaticData": {
                    "AisVersion": 2,
                    "CallSign": "TEST123",
                    "Destination": "CHENNAI",
                    "Dimension": {
                        "A": 181,
                        "B": 18,
                        "C": 12,
                        "D": 23,
                    },
                    "Dte": False,
                    "Eta": {
                        "Day": 0,
                        "Hour": 0,
                        "Minute": 0,
                        "Month": 0,
                    },
                    "FixType": 1,
                    "ImoNumber": 9_936_989,
                    "MaximumStaticDraught": 10.5,
                    "MessageID": 5,
                    "Name": "TEST VESSEL",
                    "RepeatIndicator": 0,
                    "Spare": False,
                    "Type": 71,
                    "UserID": mmsi,
                    "Valid": True,
                },
            },
        },
    }


def confirmation_event() -> dict:
    """Build a subscription confirmation event."""
    return {
        "received_at": "2026-10-18T04:32:43+00:00",
        "event": {
            "MessageType": "SubscriptionConfirmation",
            "Message": "Subscription confirmed",
        },
    }


def capture(*events: dict) -> dict:
    """Build a raw capture envelope."""
    return {
        "source": "aisstream",
        "events": list(events),
    }


class AisTransformerTests(unittest.TestCase):
    """Validate AISStream transformation rules."""

    def test_nanosecond_timestamp_is_converted_to_utc(self) -> None:
        """AISStream nanoseconds are safely reduced to microseconds."""
        parsed = parse_aisstream_time(
            "2026-10-18 04:32:55.920366886 +0000 UTC"
        )

        self.assertEqual(
            parsed,
            datetime(
                2026,
                10,
                18,
                4,
                32,
                55,
                920366,
                tzinfo=timezone.utc,
            ),
        )

    def test_valid_capture_mapping(self) -> None:
        """Map static and position messages into frozen records."""
        result = transform_capture(
            capture(
                confirmation_event(),
                position_event(),
                static_event(),
            ),
            ingested_at=INGESTED_AT,
        )

        self.assertEqual(result.source_events_read, 2)
        self.assertEqual(result.ignored_events, 1)
        self.assertEqual(result.rejected_events, 0)
        self.assertEqual(result.duplicates_removed, 0)
        self.assertEqual(len(result.vessel_records), 1)
        self.assertEqual(len(result.position_records), 1)

        vessel = result.vessel_records[0]
        self.assertEqual(vessel.mmsi, MMSI)
        self.assertEqual(vessel.imo, 9_936_989)
        self.assertEqual(vessel.name, "TEST VESSEL")
        self.assertEqual(vessel.ship_type, "cargo")
        self.assertEqual(vessel.length_m, 199.0)
        self.assertEqual(vessel.width_m, 35.0)
        self.assertEqual(vessel.source, "aisstream")

        position = result.position_records[0]
        self.assertEqual(position.mmsi, MMSI)
        self.assertAlmostEqual(
            position.speed_mps,
            10.0 * KNOTS_TO_METRES_PER_SECOND,
        )
        self.assertEqual(position.course_deg, 292.4)
        self.assertEqual(position.heading_deg, 203.0)
        self.assertEqual(
            position.navigation_status,
            "moored",
        )
        self.assertEqual(position.ingested_at, INGESTED_AT)

    def test_position_creates_stub_vessel(self) -> None:
        """A position remains loadable before static data arrives."""
        result = transform_capture(
            capture(position_event()),
            ingested_at=INGESTED_AT,
        )

        self.assertEqual(len(result.vessel_records), 1)
        vessel = result.vessel_records[0]

        self.assertEqual(vessel.mmsi, MMSI)
        self.assertEqual(vessel.name, "TEST VESSEL")
        self.assertIsNone(vessel.imo)
        self.assertIsNone(vessel.ship_type)
        self.assertIsNone(vessel.length_m)
        self.assertIsNone(vessel.width_m)

    def test_ais_unavailable_sentinels_become_null(self) -> None:
        """Unavailable AIS motion values are not stored as facts."""
        event = position_event()
        body = event["event"]["Message"]["PositionReport"]
        body["Sog"] = 102.3
        body["Cog"] = 360
        body["TrueHeading"] = 511

        result = transform_capture(
            capture(event),
            ingested_at=INGESTED_AT,
        )
        position = result.position_records[0]

        self.assertIsNone(position.speed_mps)
        self.assertIsNone(position.course_deg)
        self.assertIsNone(position.heading_deg)

    def test_duplicate_position_is_removed(self) -> None:
        """An identical event is retained only once."""
        event = position_event()

        result = transform_capture(
            capture(event, copy.deepcopy(event)),
            ingested_at=INGESTED_AT,
        )

        self.assertEqual(len(result.position_records), 1)
        self.assertEqual(result.duplicates_removed, 1)

    def test_invalid_coordinate_is_rejected(self) -> None:
        """Invalid coordinates do not block other valid records."""
        invalid_position = position_event(latitude=91.0)

        result = transform_capture(
            capture(static_event(), invalid_position),
            ingested_at=INGESTED_AT,
        )

        self.assertEqual(len(result.vessel_records), 1)
        self.assertEqual(len(result.position_records), 0)
        self.assertEqual(result.rejected_events, 1)

    def test_mismatched_mmsi_is_rejected(self) -> None:
        """Metadata and message MMSIs must identify one vessel."""
        invalid_position = position_event()
        body = invalid_position["event"]["Message"][
            "PositionReport"
        ]
        body["UserID"] = 305_567_000

        result = transform_capture(
            capture(static_event(), invalid_position),
            ingested_at=INGESTED_AT,
        )

        self.assertEqual(len(result.position_records), 0)
        self.assertEqual(result.rejected_events, 1)

    def test_class_b_position_is_supported(self) -> None:
        """Class B position reports use the common mapping."""
        event = position_event(
            message_type="StandardClassBPositionReport"
        )

        result = transform_capture(
            capture(event),
            ingested_at=INGESTED_AT,
        )

        self.assertEqual(len(result.position_records), 1)
        self.assertIsNone(
            result.position_records[0].navigation_status
        )

    def test_wrong_source_is_failure(self) -> None:
        """Reject envelopes from an unknown source."""
        payload = capture(position_event())
        payload["source"] = "unknown"

        with self.assertRaises(AisTransformationError):
            transform_capture(
                payload,
                ingested_at=INGESTED_AT,
            )

    def test_naive_ingestion_time_is_failure(self) -> None:
        """Ingestion timestamps must be timezone aware."""
        with self.assertRaises(AisTransformationError):
            transform_capture(
                capture(position_event()),
                ingested_at=datetime(2026, 10, 18, 5, 0),
            )

    def test_zero_valid_records_is_failure(self) -> None:
        """A confirmation alone is not a usable AIS capture."""
        with self.assertRaises(AisTransformationError):
            transform_capture(
                capture(confirmation_event()),
                ingested_at=INGESTED_AT,
            )


if __name__ == "__main__":
    unittest.main()