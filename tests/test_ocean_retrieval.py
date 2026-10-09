"""Tests for Copernicus ocean retrieval helpers."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from backend.marine_data.ocean.retrieve_copernicus_ocean import (
    format_timestamp,
    parse_valid_time,
    select_default_valid_time,
    validate_bounds,
)


class OceanRetrievalTests(unittest.TestCase):
    """Test deterministic retrieval helper behaviour."""

    def test_default_time_uses_previous_three_hour_interval(self) -> None:
        current_time = datetime(
            2026,
            10,
            8,
            22,
            17,
            tzinfo=timezone.utc,
        )

        result = select_default_valid_time(current_time)

        self.assertEqual(
            result,
            datetime(
                2026,
                10,
                8,
                18,
                0,
                tzinfo=timezone.utc,
            ),
        )

    def test_default_time_handles_previous_day(self) -> None:
        current_time = datetime(
            2026,
            10,
            8,
            2,
            30,
            tzinfo=timezone.utc,
        )

        result = select_default_valid_time(current_time)

        self.assertEqual(
            result,
            datetime(
                2026,
                10,
                7,
                21,
                0,
                tzinfo=timezone.utc,
            ),
        )

    def test_default_time_rejects_naive_datetime(self) -> None:
        with self.assertRaises(ValueError):
            select_default_valid_time(datetime(2026, 10, 8, 12))

    def test_parse_valid_time_converts_to_utc(self) -> None:
        result = parse_valid_time("2026-10-07T17:30:00+05:30")

        self.assertEqual(
            result,
            datetime(
                2026,
                10,
                7,
                12,
                0,
                tzinfo=timezone.utc,
            ),
        )

    def test_parse_valid_time_rejects_unaligned_hour(self) -> None:
        with self.assertRaises(ValueError):
            parse_valid_time("2026-10-07T13:00:00Z")

    def test_parse_valid_time_requires_timezone(self) -> None:
        with self.assertRaises(ValueError):
            parse_valid_time("2026-10-07T12:00:00")

    def test_validate_bounds_accepts_india_region(self) -> None:
        validate_bounds(65.0, 100.0, 5.0, 25.0)

    def test_validate_bounds_rejects_invalid_ranges(self) -> None:
        invalid_bounds = (
            (100.0, 65.0, 5.0, 25.0),
            (-181.0, 100.0, 5.0, 25.0),
            (65.0, 181.0, 5.0, 25.0),
            (65.0, 100.0, 25.0, 5.0),
            (65.0, 100.0, -91.0, 25.0),
            (65.0, 100.0, 5.0, 91.0),
        )

        for bounds in invalid_bounds:
            with self.subTest(bounds=bounds):
                with self.assertRaises(ValueError):
                    validate_bounds(*bounds)

    def test_filename_timestamp_is_utc(self) -> None:
        value = datetime(
            2026,
            10,
            7,
            17,
            30,
            tzinfo=timezone.utc,
        )

        self.assertEqual(
            format_timestamp(value),
            "20261007T173000Z",
        )


if __name__ == "__main__":
    unittest.main()