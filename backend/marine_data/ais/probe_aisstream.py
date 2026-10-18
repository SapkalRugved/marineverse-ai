"""Capture a short raw AISStream sample without changing PostgreSQL."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from websockets.exceptions import WebSocketException
from websockets.sync.client import connect
from backend.marine_data.storage import resolve_data_directory

STREAM_URL = "wss://stream.aisstream.io/v0/stream"
SOURCE = "aisstream"

BOUNDING_BOXES = [
    [
        [5.0, 65.0],
        [25.0, 100.0],
    ]
]

MESSAGE_TYPES = [
    "PositionReport",
    "StandardClassBPositionReport",
    "ExtendedClassBPositionReport",
    "ShipStaticData",
    "StaticDataReport",
]

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RAW_DIRECTORY = PROJECT_ROOT / "data" / "raw" / "ais"


class AisProbeError(RuntimeError):
    """Raised when an AISStream probe cannot be completed."""


def positive_integer(value: str) -> int:
    """Parse a strictly positive command-line integer."""
    parsed_value = int(value)

    if parsed_value <= 0:
        raise argparse.ArgumentTypeError(
            "Value must be greater than zero."
        )

    return parsed_value


def parse_arguments() -> argparse.Namespace:
    """Parse probe duration and event limit."""
    parser = argparse.ArgumentParser(
        description=(
            "Capture a bounded raw AISStream sample for the "
            "Indian maritime region."
        )
    )
    parser.add_argument(
        "--duration-seconds",
        type=positive_integer,
        default=60,
        help="Maximum capture duration. Default: 60 seconds.",
    )
    parser.add_argument(
        "--max-events",
        type=positive_integer,
        default=250,
        help="Maximum retained events. Default: 250.",
    )
    return parser.parse_args()


def build_subscription(api_key: str) -> dict[str, Any]:
    """Build the AISStream subscription without logging the key."""
    return {
        "APIKey": api_key,
        "BoundingBoxes": BOUNDING_BOXES,
        "FilterMessageTypes": MESSAGE_TYPES,
    }


def decode_event(frame: str | bytes) -> dict[str, Any]:
    """Decode one binary or text WebSocket frame."""
    if isinstance(frame, bytes):
        payload_text = frame.decode("utf-8")
    elif isinstance(frame, str):
        payload_text = frame
    else:
        raise AisProbeError(
            f"Unsupported WebSocket frame type: {type(frame)!r}"
        )

    event = json.loads(payload_text)

    if not isinstance(event, dict):
        raise AisProbeError(
            "AISStream frame did not contain a JSON object."
        )

    return event


def retain_capture(
    *,
    started_at: datetime,
    completed_at: datetime,
    duration_seconds: int,
    events: list[dict[str, Any]],
    output_directory: Path | None = None,
) -> Path:
    """Retain a bounded AIS capture atomically without credentials."""

    if output_directory is not None:
        target_directory = Path(output_directory)
    elif os.getenv("MARINEVERSE_DATA_DIR") is not None:
        target_directory = resolve_data_directory("raw", "ais")
    else:
        target_directory = RAW_DIRECTORY

    target_directory.mkdir(parents=True, exist_ok=True)

    timestamp = started_at.strftime("%Y%m%dT%H%M%SZ")
    output_path = (
        target_directory
        / f"aisstream_india_probe_{timestamp}.json"
    )
    temporary_path = output_path.with_suffix(".json.tmp")

    ais_event_count = sum(
        1
        for captured_event in events
        if captured_event["event"].get("MessageType")
        != "SubscriptionConfirmation"
    )

    envelope = {
        "source": SOURCE,
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "requested_duration_seconds": duration_seconds,
        "subscription": {
            "bounding_boxes": BOUNDING_BOXES,
            "message_types": MESSAGE_TYPES,
        },
        "event_count": len(events),
        "ais_event_count": ais_event_count,
        "events": events,
    }

    with temporary_path.open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as output_file:
        json.dump(
            envelope,
            output_file,
            ensure_ascii=False,
            indent=2,
        )
        output_file.write("\n")

    temporary_path.replace(output_path)

    return output_path

def capture_events(
    *,
    api_key: str,
    duration_seconds: int,
    max_events: int,
) -> tuple[list[dict[str, Any]], datetime, datetime]:
    """Capture a bounded set of real AISStream events."""
    started_at = datetime.now(timezone.utc)
    deadline = time.monotonic() + duration_seconds
    captured_events: list[dict[str, Any]] = []
    confirmation_received = False

    with connect(
        STREAM_URL,
        compression="deflate",
        open_timeout=10,
        ping_interval=20,
        ping_timeout=20,
        close_timeout=10,
        max_size=2 * 1024 * 1024,
    ) as websocket:
        websocket.send(
            json.dumps(build_subscription(api_key))
        )

        while (
            time.monotonic() < deadline
            and len(captured_events) < max_events
        ):
            remaining_seconds = deadline - time.monotonic()

            try:
                frame = websocket.recv(
                    timeout=min(5.0, remaining_seconds)
                )
            except TimeoutError:
                continue

            received_at = datetime.now(timezone.utc)
            event = decode_event(frame)
            message_type = event.get("MessageType")

            if message_type == "SubscriptionConfirmation":
                confirmation_received = True

            captured_events.append({
                "received_at": received_at.isoformat(),
                "event": event,
            })

    completed_at = datetime.now(timezone.utc)

    if not confirmation_received:
        raise AisProbeError(
            "AISStream did not confirm the subscription."
        )

    return captured_events, started_at, completed_at


def main() -> int:
    """Run the bounded AISStream probe."""
    arguments = parse_arguments()

    load_dotenv(PROJECT_ROOT / ".env")
    api_key = os.getenv("AISSTREAM_API_KEY", "").strip()

    if not api_key:
        print(
            "ERROR: AISSTREAM_API_KEY is not configured.",
            file=sys.stderr,
        )
        return 1

    try:
        events, started_at, completed_at = capture_events(
            api_key=api_key,
            duration_seconds=arguments.duration_seconds,
            max_events=arguments.max_events,
        )

        output_path = retain_capture(
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=arguments.duration_seconds,
            events=events,
        )

        ais_event_count = sum(
            1
            for captured_event in events
            if captured_event["event"].get("MessageType")
            != "SubscriptionConfirmation"
        )

        print("AISStream probe completed successfully.")
        print(f"Total events retained: {len(events)}")
        print(f"AIS data events retained: {ais_event_count}")
        print(f"Raw capture retained at: {output_path}")

        if ais_event_count == 0:
            print(
                "WARNING: Subscription succeeded, but no AIS "
                "data events arrived during the probe."
            )

        return 0

    except (
        AisProbeError,
        WebSocketException,
        OSError,
        UnicodeError,
        ValueError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())