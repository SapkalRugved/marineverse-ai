"""Transform raw OpenStreetMap elements into validated port records."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


SUPPORTED_ELEMENT_TYPES = {"node", "way", "relation"}

SOURCE_NAME = "openstreetmap"
DEFAULT_COUNTRY = "India"

MAX_NAME_LENGTH = 200
MAX_COUNTRY_LENGTH = 100
MAX_PORT_TYPE_LENGTH = 50


class TransformationError(ValueError):
    """Raised when raw OSM data cannot satisfy the ports contract."""


@dataclass(frozen=True, slots=True)
class PortRecord:
    """One validated record ready for the PostgreSQL ports table."""

    source_id: str
    name: str
    country: str
    port_type: str
    latitude: float
    longitude: float
    source: str
    updated_at: datetime

    def to_display_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation for CLI output."""
        return {
            "source_id": self.source_id,
            "name": self.name,
            "country": self.country,
            "port_type": self.port_type,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "source": self.source,
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class TransformationResult:
    """Records and data-quality counts from one transformation."""

    records: list[PortRecord]
    source_elements_read: int
    rejected_records: int
    duplicates_removed: int


def load_raw_elements(raw_file: Path) -> list[Any]:
    """Read the retained Overpass JSON and return its elements list."""
    try:
        with raw_file.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except OSError as exc:
        raise TransformationError(
            f"Could not read raw file: {raw_file}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise TransformationError(
            f"Raw file is not valid JSON: {raw_file}"
        ) from exc

    if not isinstance(payload, dict):
        raise TransformationError("Raw payload must be a JSON object.")

    elements = payload.get("elements")

    if not isinstance(elements, list):
        raise TransformationError(
            "Raw payload must contain an elements list."
        )

    if not elements:
        raise TransformationError(
            "Raw payload contains zero OSM elements."
        )

    return elements


def get_osm_identity(element: dict[str, Any]) -> tuple[str, int]:
    """Validate and return the OSM element type and numeric ID."""
    element_type = element.get("type")
    element_id = element.get("id")

    if element_type not in SUPPORTED_ELEMENT_TYPES:
        raise TransformationError(
            f"Unsupported OSM element type: {element_type!r}."
        )

    if (
        isinstance(element_id, bool)
        or not isinstance(element_id, int)
        or element_id <= 0
    ):
        raise TransformationError(
            "OSM element ID must be a positive integer."
        )

    return element_type, element_id


def parse_coordinate(
    value: Any,
    field_name: str,
    minimum: float,
    maximum: float,
) -> float:
    """Convert and validate one latitude or longitude value."""
    if isinstance(value, bool):
        raise TransformationError(f"{field_name} must be numeric.")

    try:
        coordinate = float(value)
    except (TypeError, ValueError) as exc:
        raise TransformationError(
            f"{field_name} must be numeric."
        ) from exc

    if not math.isfinite(coordinate):
        raise TransformationError(f"{field_name} must be finite.")

    if not minimum <= coordinate <= maximum:
        raise TransformationError(
            f"{field_name} must be between {minimum} and {maximum}."
        )

    return coordinate


def extract_coordinates(
    element: dict[str, Any],
    element_type: str,
) -> tuple[float, float]:
    """Extract node coordinates or a way/relation centre."""
    if element_type == "node":
        latitude_value = element.get("lat")
        longitude_value = element.get("lon")
    else:
        center = element.get("center")

        if not isinstance(center, dict):
            raise TransformationError(
                f"{element_type} element has no center object."
            )

        latitude_value = center.get("lat")
        longitude_value = center.get("lon")

    latitude = parse_coordinate(
        latitude_value,
        "latitude",
        -90.0,
        90.0,
    )
    longitude = parse_coordinate(
        longitude_value,
        "longitude",
        -180.0,
        180.0,
    )

    return latitude, longitude


def classify_port_type(tags: dict[str, Any]) -> str:
    """Classify an OSM feature using the frozen priority order."""
    if tags.get("leisure") == "marina":
        return "marina"

    if tags.get("amenity") == "ferry_terminal":
        return "ferry_terminal"

    if (
        tags.get("seamark:harbour:category")
        == "fishing_harbour"
    ):
        return "fishing_harbour"

    if (
        tags.get("harbour") == "yes"
        or tags.get("seamark:type") == "harbour"
    ):
        return "harbour"

    if (
        tags.get("industrial") == "port"
        or tags.get("seamark:harbour:category") == "port"
    ):
        return "port"

    if tags.get("man_made") == "pier":
        return "pier"

    if tags.get("man_made") == "quay":
        return "quay"

    if tags.get("seamark:type") == "harbour_basin":
        return "harbour_basin"

    if tags.get("seamark:type") == "harbour_facility":
        return "harbour_facility"

    return "harbour"


def clean_name(tags: dict[str, Any]) -> str:
    """Return a trimmed OSM name that fits the frozen schema."""
    raw_name = tags.get("name")

    if not isinstance(raw_name, str):
        raise TransformationError(
            "OSM element does not contain a string name."
        )

    name = raw_name.strip()

    if not name:
        raise TransformationError("OSM element name is blank.")

    if len(name) > MAX_NAME_LENGTH:
        raise TransformationError(
            f"OSM name exceeds {MAX_NAME_LENGTH} characters."
        )

    return name


def clean_country(tags: dict[str, Any]) -> str:
    """Use a valid addr:country value or the India fallback."""
    raw_country = tags.get("addr:country")

    if isinstance(raw_country, str):
        country = raw_country.strip()

        if country:
            if len(country) > MAX_COUNTRY_LENGTH:
                raise TransformationError(
                    "Country exceeds schema length."
                )

            return country

    return DEFAULT_COUNTRY


def validate_port_record(record: PortRecord) -> None:
    """Verify that a transformed record matches the frozen contract."""
    if not record.source_id:
        raise TransformationError("source_id must not be blank.")

    if not record.name or len(record.name) > MAX_NAME_LENGTH:
        raise TransformationError("Mapped name is invalid.")

    if len(record.country) > MAX_COUNTRY_LENGTH:
        raise TransformationError("Mapped country is invalid.")

    if len(record.port_type) > MAX_PORT_TYPE_LENGTH:
        raise TransformationError("Mapped port_type is invalid.")

    parse_coordinate(record.latitude, "latitude", -90.0, 90.0)
    parse_coordinate(record.longitude, "longitude", -180.0, 180.0)

    if record.source != SOURCE_NAME:
        raise TransformationError(
            f"source must equal {SOURCE_NAME!r}."
        )

    if record.updated_at.tzinfo is None:
        raise TransformationError("updated_at must be timezone-aware.")

    if record.updated_at.utcoffset() != timedelta(0):
        raise TransformationError("updated_at must use UTC.")


def map_element_to_port(
    element: dict[str, Any],
    transformed_at: datetime,
) -> PortRecord:
    """Map one valid OSM element into a PortRecord."""
    if not isinstance(element, dict):
        raise TransformationError("OSM element must be an object.")

    element_type, element_id = get_osm_identity(element)

    tags = element.get("tags")

    if not isinstance(tags, dict):
        raise TransformationError(
            "OSM element tags must be an object."
        )

    latitude, longitude = extract_coordinates(element, element_type)

    record = PortRecord(
        source_id=f"{element_type}/{element_id}",
        name=clean_name(tags),
        country=clean_country(tags),
        port_type=classify_port_type(tags),
        latitude=latitude,
        longitude=longitude,
        source=SOURCE_NAME,
        updated_at=transformed_at,
    )

    validate_port_record(record)
    return record


def transform_elements(
    elements: list[Any],
    transformed_at: datetime | None = None,
) -> TransformationResult:
    """Transform, validate and deduplicate raw OSM elements."""
    if transformed_at is None:
        transformed_at = datetime.now(timezone.utc)

    if (
        transformed_at.tzinfo is None
        or transformed_at.utcoffset() != timedelta(0)
    ):
        raise TransformationError(
            "Transformation timestamp must be timezone-aware UTC."
        )

    records: list[PortRecord] = []
    seen_identifiers: set[tuple[str, int]] = set()

    rejected_records = 0
    duplicates_removed = 0

    for element in elements:
        try:
            if not isinstance(element, dict):
                raise TransformationError(
                    "OSM element must be an object."
                )

            identity = get_osm_identity(element)

            if identity in seen_identifiers:
                duplicates_removed += 1
                continue

            record = map_element_to_port(element, transformed_at)
        except TransformationError:
            rejected_records += 1
            continue

        seen_identifiers.add(identity)
        records.append(record)

    if not records:
        raise TransformationError(
            "Transformation produced zero valid port records."
        )

    return TransformationResult(
        records=records,
        source_elements_read=len(elements),
        rejected_records=rejected_records,
        duplicates_removed=duplicates_removed,
    )


def transform_raw_file(
    raw_file: Path,
    transformed_at: datetime | None = None,
) -> TransformationResult:
    """Load and transform one retained Overpass JSON file."""
    elements = load_raw_elements(raw_file)
    return transform_elements(elements, transformed_at)