"""Unit tests for OSM ports transformation."""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.marine_data.ports.transformer import (
    TransformationError,
    classify_port_type,
    map_element_to_port,
    transform_elements,
    transform_raw_file,
)


FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "osm_ports_sample.json"
)

TRANSFORMED_AT = datetime(
    2026,
    10,
    8,
    10,
    0,
    tzinfo=timezone.utc,
)


class PortsTransformerTests(unittest.TestCase):
    """Verify field mapping, validation and deduplication."""

    def make_node(
        self,
        *,
        element_id: int = 1,
        latitude: object = 18.949,
        longitude: object = 72.838,
        name: object = "Mumbai Port",
        extra_tags: dict[str, object] | None = None,
    ) -> dict[str, object]:
        """Create a small valid OSM node for one test."""
        tags: dict[str, object] = {
            "name": name,
            "harbour": "yes",
        }

        if extra_tags:
            tags.update(extra_tags)

        return {
            "type": "node",
            "id": element_id,
            "lat": latitude,
            "lon": longitude,
            "tags": tags,
        }

    def assert_rejected(self, element: object) -> None:
        """Verify one bad record is rejected beside one valid record."""
        result = transform_elements(
            [
                element,
                self.make_node(
                    element_id=9999,
                    name="Valid fallback port",
                ),
            ],
            TRANSFORMED_AT,
        )

        self.assertEqual(result.source_elements_read, 2)
        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.rejected_records, 1)
        self.assertEqual(result.duplicates_removed, 0)

    def test_node_mapping(self) -> None:
        element = self.make_node(
            element_id=101,
            name="  Mumbai Port  ",
            extra_tags={"addr:country": " IN "},
        )

        record = map_element_to_port(element, TRANSFORMED_AT)

        self.assertEqual(record.source_id, "node/101")
        self.assertEqual(record.name, "Mumbai Port")
        self.assertEqual(record.country, "IN")
        self.assertEqual(record.port_type, "harbour")
        self.assertEqual(record.latitude, 18.949)
        self.assertEqual(record.longitude, 72.838)
        self.assertEqual(record.source, "openstreetmap")
        self.assertEqual(record.updated_at, TRANSFORMED_AT)

    def test_way_center_mapping(self) -> None:
        element = {
            "type": "way",
            "id": 202,
            "center": {"lat": 15.4, "lon": 73.8},
            "tags": {
                "name": "Goa Marina",
                "leisure": "marina",
            },
        }

        record = map_element_to_port(element, TRANSFORMED_AT)

        self.assertEqual(record.source_id, "way/202")
        self.assertEqual(record.latitude, 15.4)
        self.assertEqual(record.longitude, 73.8)
        self.assertEqual(record.port_type, "marina")

    def test_relation_center_mapping(self) -> None:
        element = {
            "type": "relation",
            "id": 303,
            "center": {"lat": 9.97, "lon": 76.27},
            "tags": {
                "name": "Kochi Harbour",
                "seamark:type": "harbour",
            },
        }

        record = map_element_to_port(element, TRANSFORMED_AT)

        self.assertEqual(record.source_id, "relation/303")
        self.assertEqual(record.latitude, 9.97)
        self.assertEqual(record.longitude, 76.27)
        self.assertEqual(record.port_type, "harbour")

    def test_port_type_priorities(self) -> None:
        cases = [
            (
                {
                    "leisure": "marina",
                    "amenity": "ferry_terminal",
                    "industrial": "port",
                },
                "marina",
            ),
            (
                {
                    "amenity": "ferry_terminal",
                    "industrial": "port",
                },
                "ferry_terminal",
            ),
            (
                {
                    "seamark:harbour:category": "fishing_harbour",
                    "harbour": "yes",
                },
                "fishing_harbour",
            ),
            (
                {
                    "harbour": "yes",
                    "industrial": "port",
                },
                "harbour",
            ),
            ({"industrial": "port"}, "port"),
            ({"man_made": "pier"}, "pier"),
            ({"man_made": "quay"}, "quay"),
            (
                {"seamark:type": "harbour_basin"},
                "harbour_basin",
            ),
            (
                {"seamark:type": "harbour_facility"},
                "harbour_facility",
            ),
            ({}, "harbour"),
        ]

        for tags, expected_type in cases:
            with self.subTest(tags=tags):
                self.assertEqual(
                    classify_port_type(tags),
                    expected_type,
                )

    def test_blank_name_rejection(self) -> None:
        self.assert_rejected(self.make_node(name="   "))

    def test_invalid_latitude_rejection(self) -> None:
        self.assert_rejected(self.make_node(latitude=91))

    def test_invalid_longitude_rejection(self) -> None:
        self.assert_rejected(self.make_node(longitude=181))

    def test_nonfinite_coordinate_rejection(self) -> None:
        self.assert_rejected(
            self.make_node(latitude=float("nan"))
        )

    def test_missing_way_center_rejection(self) -> None:
        element = {
            "type": "way",
            "id": 404,
            "tags": {
                "name": "Missing Center Port",
                "harbour": "yes",
            },
        }

        self.assert_rejected(element)

    def test_missing_relation_center_rejection(self) -> None:
        element = {
            "type": "relation",
            "id": 405,
            "tags": {
                "name": "Missing Center Harbour",
                "seamark:type": "harbour",
            },
        }

        self.assert_rejected(element)

    def test_overlength_name_rejection(self) -> None:
        self.assert_rejected(self.make_node(name="P" * 201))

    def test_duplicate_osm_element_removal(self) -> None:
        duplicate = self.make_node(element_id=501)

        result = transform_elements(
            [duplicate, duplicate],
            TRANSFORMED_AT,
        )

        self.assertEqual(result.source_elements_read, 2)
        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.rejected_records, 0)
        self.assertEqual(result.duplicates_removed, 1)

    def test_zero_valid_records_is_failure(self) -> None:
        with self.assertRaises(TransformationError):
            transform_elements(
                [self.make_node(name=" ")],
                TRANSFORMED_AT,
            )

    def test_non_utc_timestamp_is_failure(self) -> None:
        non_utc = timezone(timedelta(hours=5, minutes=30))

        with self.assertRaises(TransformationError):
            transform_elements(
                [self.make_node()],
                datetime(2026, 10, 8, 15, 30, tzinfo=non_utc),
            )

    def test_fixture_transformation(self) -> None:
        result = transform_raw_file(
            FIXTURE_PATH,
            TRANSFORMED_AT,
        )

        self.assertEqual(result.source_elements_read, 5)
        self.assertEqual(len(result.records), 4)
        self.assertEqual(result.rejected_records, 0)
        self.assertEqual(result.duplicates_removed, 1)

        expected_types = [
            "marina",
            "ferry_terminal",
            "fishing_harbour",
            "port",
        ]
        actual_types = [
            record.port_type for record in result.records
        ]

        self.assertEqual(actual_types, expected_types)

    def test_fixture_is_valid_json(self) -> None:
        with FIXTURE_PATH.open("r", encoding="utf-8") as file:
            payload = json.load(file)

        self.assertIn("elements", payload)
        self.assertEqual(len(payload["elements"]), 5)


if __name__ == "__main__":
    unittest.main()