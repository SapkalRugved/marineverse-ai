"""Transform captured AISStream events into validated records."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


SOURCE = "aisstream"
KNOTS_TO_METRES_PER_SECOND = 0.514444

POSITION_MESSAGE_TYPES = {
    "PositionReport",
    "StandardClassBPositionReport",
    "ExtendedClassBPositionReport",
}

NAVIGATION_STATUSES = {
    0: "underway_using_engine",
    1: "at_anchor",
    2: "not_under_command",
    3: "restricted_manoeuvrability",
    4: "constrained_by_draught",
    5: "moored",
    6: "aground",
    7: "engaged_in_fishing",
    8: "underway_sailing",
    14: "ais_sart",
    15: "undefined",
}

AISSTREAM_TIME_PATTERN = re.compile(
    r"^(?P<base>\d{4}-\d{2}-\d{2} "
    r"\d{2}:\d{2}:\d{2})"
    r"(?:\.(?P<fraction>\d+))? "
    r"(?P<offset>[+-]\d{4}) UTC$"
)


class AisTransformationError(RuntimeError):
    """Raised when an AIS capture cannot be transformed."""


@dataclass(frozen=True, slots=True)
class VesselRecord:
    """A validated vessel suitable for the vessels table."""

    mmsi: int
    imo: int | None
    name: str | None
    ship_type: str | None
    length_m: float | None
    width_m: float | None
    source: str
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class VesselPositionRecord:
    """A validated position awaiting vessel ID resolution."""

    mmsi: int
    observed_at: datetime
    latitude: float
    longitude: float
    speed_mps: float | None
    course_deg: float | None
    heading_deg: float | None
    navigation_status: str | None
    source: str
    ingested_at: datetime


@dataclass(frozen=True, slots=True)
class AisTransformationResult:
    """Summary and records produced from one raw capture."""

    source_events_read: int
    vessel_records: tuple[VesselRecord, ...]
    position_records: tuple[VesselPositionRecord, ...]
    rejected_events: int
    ignored_events: int
    duplicates_removed: int


def parse_aisstream_time(value: Any) -> datetime:
    """Parse AISStream's nanosecond UTC timestamp."""
    if not isinstance(value, str) or not value.strip():
        raise AisTransformationError(
            "AIS event timestamp is missing."
        )

    timestamp_text = value.strip()
    match = AISSTREAM_TIME_PATTERN.fullmatch(timestamp_text)

    if match:
        fraction = match.group("fraction") or ""
        microseconds = (fraction + "000000")[:6]

        parsed = datetime.strptime(
            (
                f"{match.group('base')}."
                f"{microseconds} "
                f"{match.group('offset')}"
            ),
            "%Y-%m-%d %H:%M:%S.%f %z",
        )
        return parsed.astimezone(timezone.utc)

    try:
        parsed = datetime.fromisoformat(
            timestamp_text.replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise AisTransformationError(
            f"Invalid AIS event timestamp: {timestamp_text}"
        ) from exc

    if parsed.tzinfo is None:
        raise AisTransformationError(
            "AIS event timestamp must include a timezone."
        )

    return parsed.astimezone(timezone.utc)


def require_mapping(
    value: Any,
    field_name: str,
) -> dict[str, Any]:
    """Require a JSON object."""
    if not isinstance(value, dict):
        raise AisTransformationError(
            f"{field_name} must be a JSON object."
        )

    return value


def require_integer(value: Any, field_name: str) -> int:
    """Require an integer without accepting booleans."""
    if isinstance(value, bool):
        raise AisTransformationError(
            f"{field_name} must be an integer."
        )

    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise AisTransformationError(
            f"{field_name} must be an integer."
        ) from exc

    return parsed


def require_number(value: Any, field_name: str) -> float:
    """Require a finite numeric value."""
    if isinstance(value, bool):
        raise AisTransformationError(
            f"{field_name} must be numeric."
        )

    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise AisTransformationError(
            f"{field_name} must be numeric."
        ) from exc

    if not math.isfinite(parsed):
        raise AisTransformationError(
            f"{field_name} must be finite."
        )

    return parsed


def validate_mmsi(value: Any) -> int:
    """Validate a nine-digit maritime mobile service identity."""
    mmsi = require_integer(value, "MMSI")

    if not 100_000_000 <= mmsi <= 999_999_999:
        raise AisTransformationError(
            "MMSI must contain nine digits."
        )

    return mmsi


def optional_text(
    value: Any,
    *,
    field_name: str,
    maximum_length: int,
) -> str | None:
    """Normalize an optional bounded text value."""
    if value is None:
        return None

    normalized = str(value).strip()

    if not normalized:
        return None

    if len(normalized) > maximum_length:
        raise AisTransformationError(
            f"{field_name} exceeds {maximum_length} characters."
        )

    return normalized


def ship_type_name(value: Any) -> str | None:
    """Map an AIS ship-type code into a stable category."""
    if value is None:
        return None

    code = require_integer(value, "Ship type")

    if code == 0:
        return None
    if 20 <= code <= 29:
        return "wing_in_ground"
    if code == 30:
        return "fishing"
    if code in {31, 32}:
        return "towing"
    if code == 33:
        return "dredging"
    if code == 34:
        return "diving_operations"
    if code == 35:
        return "military"
    if code == 36:
        return "sailing"
    if code == 37:
        return "pleasure_craft"
    if 40 <= code <= 49:
        return "high_speed_craft"
    if code == 50:
        return "pilot_vessel"
    if code == 51:
        return "search_and_rescue"
    if code == 52:
        return "tug"
    if code == 53:
        return "port_tender"
    if code == 54:
        return "anti_pollution"
    if code == 55:
        return "law_enforcement"
    if code == 58:
        return "medical_transport"
    if 60 <= code <= 69:
        return "passenger"
    if 70 <= code <= 79:
        return "cargo"
    if 80 <= code <= 89:
        return "tanker"
    if 90 <= code <= 99:
        return "other"

    return f"ais_type_{code}"


def parse_dimensions(
    value: Any,
) -> tuple[float | None, float | None]:
    """Calculate vessel length and width from AIS dimensions."""
    if value is None:
        return None, None

    dimensions = require_mapping(value, "Dimension")

    a = require_number(dimensions.get("A", 0), "Dimension.A")
    b = require_number(dimensions.get("B", 0), "Dimension.B")
    c = require_number(dimensions.get("C", 0), "Dimension.C")
    d = require_number(dimensions.get("D", 0), "Dimension.D")

    if min(a, b, c, d) < 0:
        raise AisTransformationError(
            "Vessel dimensions cannot be negative."
        )

    length = a + b
    width = c + d

    return (
        length if length > 0 else None,
        width if width > 0 else None,
    )


def validate_event_identity(
    metadata: dict[str, Any],
    message: dict[str, Any],
) -> int:
    """Require metadata and message-body MMSIs to agree."""
    metadata_mmsi = validate_mmsi(metadata.get("MMSI"))
    message_mmsi = validate_mmsi(message.get("UserID"))

    if metadata_mmsi != message_mmsi:
        raise AisTransformationError(
            "AIS metadata and message MMSIs do not match."
        )

    return metadata_mmsi


def transform_static_event(
    event: dict[str, Any],
) -> VesselRecord:
    """Transform one ShipStaticData event."""
    metadata = require_mapping(
        event.get("MetaData"),
        "MetaData",
    )
    message_envelope = require_mapping(
        event.get("Message"),
        "Message",
    )
    message = require_mapping(
        message_envelope.get("ShipStaticData"),
        "Message.ShipStaticData",
    )

    if message.get("Valid") is not True:
        raise AisTransformationError(
            "ShipStaticData message is not valid."
        )

    mmsi = validate_event_identity(metadata, message)
    updated_at = parse_aisstream_time(
        metadata.get("time_utc")
    )

    raw_imo = require_integer(
        message.get("ImoNumber", 0),
        "IMO number",
    )
    imo = raw_imo if raw_imo > 0 else None

    if imo is not None and imo > 9_999_999:
        raise AisTransformationError(
            "IMO number exceeds seven digits."
        )

    name = optional_text(
        message.get("Name") or metadata.get("ShipName"),
        field_name="Vessel name",
        maximum_length=200,
    )
    length_m, width_m = parse_dimensions(
        message.get("Dimension")
    )

    return VesselRecord(
        mmsi=mmsi,
        imo=imo,
        name=name,
        ship_type=ship_type_name(message.get("Type")),
        length_m=length_m,
        width_m=width_m,
        source=SOURCE,
        updated_at=updated_at,
    )


def optional_course(value: Any) -> float | None:
    """Validate course over ground, including AIS sentinel 360."""
    course = require_number(value, "Course over ground")

    if course == 360:
        return None

    if not 0 <= course < 360:
        raise AisTransformationError(
            "Course over ground is outside 0-359.9 degrees."
        )

    return course


def optional_heading(value: Any) -> float | None:
    """Validate heading, including AIS sentinel 511."""
    heading = require_number(value, "True heading")

    if heading == 511:
        return None

    if not 0 <= heading < 360:
        raise AisTransformationError(
            "True heading is outside 0-359 degrees."
        )

    return heading


def optional_speed_mps(value: Any) -> float | None:
    """Convert AIS speed over ground from knots to m/s."""
    speed_knots = require_number(value, "Speed over ground")

    if speed_knots == 102.3:
        return None

    if not 0 <= speed_knots <= 102.2:
        raise AisTransformationError(
            "Speed over ground is outside the AIS range."
        )

    return speed_knots * KNOTS_TO_METRES_PER_SECOND


def transform_position_event(
    event: dict[str, Any],
    *,
    ingested_at: datetime,
) -> VesselPositionRecord:
    """Transform one supported AIS position event."""
    message_type = event.get("MessageType")

    if message_type not in POSITION_MESSAGE_TYPES:
        raise AisTransformationError(
            f"Unsupported position message: {message_type}"
        )

    metadata = require_mapping(
        event.get("MetaData"),
        "MetaData",
    )
    message_envelope = require_mapping(
        event.get("Message"),
        "Message",
    )
    message = require_mapping(
        message_envelope.get(message_type),
        f"Message.{message_type}",
    )

    if message.get("Valid") is not True:
        raise AisTransformationError(
            f"{message_type} message is not valid."
        )

    mmsi = validate_event_identity(metadata, message)
    observed_at = parse_aisstream_time(
        metadata.get("time_utc")
    )

    latitude = require_number(
        message.get("Latitude"),
        "Latitude",
    )
    longitude = require_number(
        message.get("Longitude"),
        "Longitude",
    )

    if not -90 <= latitude <= 90:
        raise AisTransformationError(
            "Latitude is outside -90 to 90."
        )

    if not -180 <= longitude <= 180:
        raise AisTransformationError(
            "Longitude is outside -180 to 180."
        )

    navigation_status = None
    raw_navigation_status = message.get(
        "NavigationalStatus"
    )

    if raw_navigation_status is not None:
        status_code = require_integer(
            raw_navigation_status,
            "Navigational status",
        )
        navigation_status = NAVIGATION_STATUSES.get(
            status_code,
            f"ais_status_{status_code}",
        )

    return VesselPositionRecord(
        mmsi=mmsi,
        observed_at=observed_at,
        latitude=latitude,
        longitude=longitude,
        speed_mps=optional_speed_mps(
            message.get("Sog")
        ),
        course_deg=optional_course(
            message.get("Cog")
        ),
        heading_deg=optional_heading(
            message.get("TrueHeading")
        ),
        navigation_status=navigation_status,
        source=SOURCE,
        ingested_at=ingested_at,
    )


def stub_vessel_from_position(
    event: dict[str, Any],
    position: VesselPositionRecord,
) -> VesselRecord:
    """Create the vessel required by a position-only message."""
    metadata = require_mapping(
        event.get("MetaData"),
        "MetaData",
    )

    return VesselRecord(
        mmsi=position.mmsi,
        imo=None,
        name=optional_text(
            metadata.get("ShipName"),
            field_name="Vessel name",
            maximum_length=200,
        ),
        ship_type=None,
        length_m=None,
        width_m=None,
        source=SOURCE,
        updated_at=position.observed_at,
    )


def transform_capture(
    payload: Any,
    *,
    ingested_at: datetime | None = None,
) -> AisTransformationResult:
    """Transform an AISStream capture envelope."""
    envelope = require_mapping(payload, "Capture")

    if envelope.get("source") != SOURCE:
        raise AisTransformationError(
            "Capture source must be aisstream."
        )

    events = envelope.get("events")

    if not isinstance(events, list):
        raise AisTransformationError(
            "Capture events must be a list."
        )

    load_time = ingested_at or datetime.now(timezone.utc)

    if load_time.tzinfo is None:
        raise AisTransformationError(
            "Ingestion time must include a timezone."
        )

    load_time = load_time.astimezone(timezone.utc)

    vessels: dict[int, VesselRecord] = {}
    positions: list[VesselPositionRecord] = []
    position_keys: set[tuple[Any, ...]] = set()

    source_events_read = 0
    rejected_events = 0
    ignored_events = 0
    duplicates_removed = 0

    for captured_event in events:
        try:
            wrapper = require_mapping(
                captured_event,
                "Captured event",
            )
            event = require_mapping(
                wrapper.get("event"),
                "Captured event.event",
            )
            message_type = event.get("MessageType")

            if message_type == "SubscriptionConfirmation":
                ignored_events += 1
                continue

            source_events_read += 1

            if message_type == "ShipStaticData":
                vessel = transform_static_event(event)
                existing = vessels.get(vessel.mmsi)

                if existing is not None:
                    vessel = VesselRecord(
                        mmsi=vessel.mmsi,
                        imo=vessel.imo or existing.imo,
                        name=vessel.name or existing.name,
                        ship_type=(
                            vessel.ship_type
                            or existing.ship_type
                        ),
                        length_m=(
                            vessel.length_m
                            if vessel.length_m is not None
                            else existing.length_m
                        ),
                        width_m=(
                            vessel.width_m
                            if vessel.width_m is not None
                            else existing.width_m
                        ),
                        source=SOURCE,
                        updated_at=max(
                            vessel.updated_at,
                            existing.updated_at,
                        ),
                    )

                vessels[vessel.mmsi] = vessel
                continue

            if message_type in POSITION_MESSAGE_TYPES:
                position = transform_position_event(
                    event,
                    ingested_at=load_time,
                )

                position_key = (
                    position.mmsi,
                    position.observed_at,
                    position.latitude,
                    position.longitude,
                )

                if position_key in position_keys:
                    duplicates_removed += 1
                    continue

                position_keys.add(position_key)
                positions.append(position)

                existing = vessels.get(position.mmsi)
                stub = stub_vessel_from_position(
                    event,
                    position,
                )

                if existing is None:
                    vessels[position.mmsi] = stub
                elif position.observed_at > existing.updated_at:
                    vessels[position.mmsi] = VesselRecord(
                        mmsi=existing.mmsi,
                        imo=existing.imo,
                        name=existing.name or stub.name,
                        ship_type=existing.ship_type,
                        length_m=existing.length_m,
                        width_m=existing.width_m,
                        source=SOURCE,
                        updated_at=position.observed_at,
                    )

                continue

            rejected_events += 1

        except AisTransformationError:
            rejected_events += 1

    if not vessels and not positions:
        raise AisTransformationError(
            "Capture contained no valid AIS records."
        )

    positions.sort(
        key=lambda record: (
            record.observed_at,
            record.mmsi,
        )
    )

    return AisTransformationResult(
        source_events_read=source_events_read,
        vessel_records=tuple(
            sorted(
                vessels.values(),
                key=lambda record: record.mmsi,
            )
        ),
        position_records=tuple(positions),
        rejected_events=rejected_events,
        ignored_events=ignored_events,
        duplicates_removed=duplicates_removed,
    )