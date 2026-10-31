"""Tests for worldwide cyclone normalization, using synthetic fixtures only."""
import csv
import json
import tempfile
import unittest
from pathlib import Path

from backend.marine_data.cyclones.ibtracs_silver import _transform, build


class GlobalIbtracsSilverTests(unittest.TestCase):
    def test_normalization(self):
        row = {
            "SID": "2000123N01234", "SEASON": "2000", "BASIN": "WP",
            "ISO_TIME": "2000-07-01 12:00:00", "LAT": "12.5", "LON": "190",
            "WMO_WIND": "20", "WMO_PRES": "990", "NAME": "TEST",
        }
        clean = _transform(row)
        self.assertEqual(clean["longitude"], -170.0)
        self.assertEqual(clean["latitude"], 12.5)
        self.assertAlmostEqual(clean["wind_speed_ms"], 10.28888)
        self.assertEqual(clean["pressure_hpa"], 990.0)
        self.assertEqual(clean["observed_at_utc"].isoformat(), "2000-07-01T12:00:00+00:00")

    def test_invalid_latitude_is_rejected(self):
        with self.assertRaises(ValueError):
            _transform({
                "SID": "X", "SEASON": "2000", "BASIN": "NA",
                "ISO_TIME": "2000-01-01 00:00:00", "LAT": "91", "LON": "-10",
            })

    def test_missing_wind_and_pressure_are_null(self):
        clean = _transform({
            "SID": "X", "SEASON": "2000", "BASIN": "NA",
            "ISO_TIME": "2000-01-01 00:00:00", "LAT": "10", "LON": "20",
        })
        self.assertIsNone(clean["wind_speed_ms"])
        self.assertIsNone(clean["pressure_hpa"])

    def test_end_to_end_parquet_and_quality_report(self):
        import pyarrow.parquet as pq
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "all.csv"
            destination = root / "processed" / "global_cyclone_tracks.parquet"
            with source.open("w", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                writer.writerow(["SID", "SEASON", "BASIN", "ISO_TIME", "LAT", "LON", "WMO_WIND", "WMO_PRES", "NAME"])
                writer.writerow(["", "Year", "", "", "degrees_north", "degrees_east", "kts", "mb", ""])
                writer.writerow(["S1", "2020", "NI", "2020-01-01 00:00:00", "15", "75", "25", "", "ONE"])
                writer.writerow(["S2", "2020", "WP", "2020-01-02 00:00:00", "5", "200", "", "1000", "TWO"])
                writer.writerow(["S3", "2020", "NI", "2020-01-02 00:00:00", "999", "20", "", "", "BAD"])
            report = build(source, destination, chunk_size=1)
            self.assertEqual(report["total_observation_rows"], 3)
            self.assertEqual(report["accepted_rows"], 2)
            self.assertEqual(report["rejected_rows"], 1)
            self.assertEqual(report["basin_distribution"], {"NI": 1, "WP": 1})
            rows = pq.read_table(destination).to_pylist()
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[1]["longitude"], -160.0)
            self.assertTrue((destination.parent / "quality_report.json").exists())
            self.assertEqual(json.loads((destination.parent / "quality_report.json").read_text())["source_sha256"], report["source_sha256"])
            self.assertTrue(source.exists())


if __name__ == "__main__":
    unittest.main()
