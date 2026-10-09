"""Tests for Copernicus ocean transformation."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import xarray as xr

from backend.marine_data.ocean.retrieve_copernicus_ocean import (
    PHYSICS_DATASET,
    SOURCE,
    WAVE_DATASET,
)
from backend.marine_data.ocean.transformer import (
    OceanTransformationError,
    calculate_current_direction,
    transform_raw_manifest,
)


VALID_TIME = "2026-10-07T12:00:00+00:00"
RETRIEVED_AT = "2026-10-08T12:00:00+00:00"


def write_fixture(
    directory: Path,
    *,
    invalid_temperature: bool = False,
    temperature_unit: str = "degrees_C",
    wave_time: str = "2026-10-07T12:00:00",
    wave_coordinate_offset: float = 0.0,
    source: str = SOURCE,
    retrieved_at: str = RETRIEVED_AT,
) -> Path:
    """Create temporary physics, wave and manifest fixtures."""
    physics_path = directory / "physics.nc"
    wave_path = directory / "waves.nc"
    manifest_path = directory / "manifest.json"

    latitudes = np.array([18.0, 18.1])
    longitudes = np.array([72.0, 72.1])

    temperatures = np.full((1, 1, 2, 2), 25.0)

    if invalid_temperature:
        temperatures[0, 0, 0, 0] = np.nan

    physics = xr.Dataset(
        data_vars={
            "thetao": (
                ("time", "depth", "latitude", "longitude"),
                temperatures,
                {"units": temperature_unit},
            ),
            "uo": (
                ("time", "depth", "latitude", "longitude"),
                np.array(
                    [[[[1.0, 0.0], [-1.0, 0.0]]]]
                ),
                {"units": "m s-1"},
            ),
            "vo": (
                ("time", "depth", "latitude", "longitude"),
                np.array(
                    [[[[0.0, 1.0], [0.0, -1.0]]]]
                ),
                {"units": "m s-1"},
            ),
        },
        coords={
            "time": np.array(
                ["2026-10-07T12:00:00"],
                dtype="datetime64[ns]",
            ),
            "depth": np.array([0.494025]),
            "latitude": latitudes,
            "longitude": longitudes,
        },
    )

    wave = xr.Dataset(
        data_vars={
            "VHM0": (
                ("time", "latitude", "longitude"),
                np.full((1, 2, 2), 1.5),
                {"units": "m"},
            ),
            "VMDR": (
                ("time", "latitude", "longitude"),
                np.full((1, 2, 2), 240.0),
                {"units": "degree"},
            ),
            "VTM02": (
                ("time", "latitude", "longitude"),
                np.full((1, 2, 2), 6.0),
                {"units": "s"},
            ),
        },
        coords={
            "time": np.array(
                [wave_time],
                dtype="datetime64[ns]",
            ),
            "latitude": latitudes + wave_coordinate_offset,
            "longitude": longitudes + wave_coordinate_offset,
        },
    )

    physics.to_netcdf(physics_path, engine="h5netcdf")
    wave.to_netcdf(wave_path, engine="h5netcdf")

    manifest = {
        "source": source,
        "retrieved_at": retrieved_at,
        "valid_time": VALID_TIME,
        "physics": {
            "dataset_id": PHYSICS_DATASET,
            "variables": ["thetao", "uo", "vo"],
            "file": physics_path.name,
        },
        "waves": {
            "dataset_id": WAVE_DATASET,
            "variables": ["VHM0", "VMDR", "VTM02"],
            "file": wave_path.name,
        },
    }

    manifest_path.write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )

    return manifest_path


class OceanTransformerTests(unittest.TestCase):
    """Test unified physics and wave transformation."""

    def test_valid_grid_transformation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            manifest = write_fixture(Path(temporary_directory))

            ingested_at = datetime(
                2026,
                10,
                8,
                13,
                0,
                tzinfo=timezone.utc,
            )

            result = transform_raw_manifest(
                manifest,
                ingested_at=ingested_at,
            )

        self.assertEqual(result.source_grid_cells, 4)
        self.assertEqual(len(result.records), 4)
        self.assertEqual(result.rejected_records, 0)

        first = result.records[0]

        self.assertEqual(first.valid_time.hour, 12)
        self.assertAlmostEqual(first.latitude, 18.0)
        self.assertAlmostEqual(first.longitude, 72.0)
        self.assertAlmostEqual(first.depth_m, 0.494025)
        self.assertAlmostEqual(first.current_u_mps, 1.0)
        self.assertAlmostEqual(first.current_v_mps, 0.0)
        self.assertAlmostEqual(first.current_speed_mps, 1.0)
        self.assertAlmostEqual(first.current_direction_deg, 90.0)
        self.assertAlmostEqual(first.sea_surface_temperature_c, 25.0)
        self.assertAlmostEqual(first.wave_height_m, 1.5)
        self.assertAlmostEqual(first.wave_direction_deg, 240.0)
        self.assertAlmostEqual(first.wave_period_s, 6.0)
        self.assertFalse(first.is_forecast)
        self.assertEqual(first.source, SOURCE)
        self.assertEqual(first.ingested_at, ingested_at)

    def test_cardinal_current_directions(self) -> None:
        cases = (
            ((0.0, 1.0), 0.0),
            ((1.0, 0.0), 90.0),
            ((0.0, -1.0), 180.0),
            ((-1.0, 0.0), 270.0),
        )

        for velocities, expected in cases:
            with self.subTest(velocities=velocities):
                self.assertAlmostEqual(
                    calculate_current_direction(*velocities),
                    expected,
                )

    def test_forecast_flag(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            manifest = write_fixture(
                Path(temporary_directory),
                retrieved_at="2026-10-07T09:00:00+00:00",
            )

            result = transform_raw_manifest(manifest)

        self.assertTrue(result.records[0].is_forecast)

    def test_invalid_cell_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            manifest = write_fixture(
                Path(temporary_directory),
                invalid_temperature=True,
            )

            result = transform_raw_manifest(manifest)

        self.assertEqual(result.source_grid_cells, 4)
        self.assertEqual(len(result.records), 3)
        self.assertEqual(result.rejected_records, 1)

    def test_nearby_wave_grid_is_aligned(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            manifest = write_fixture(
                Path(temporary_directory),
                wave_coordinate_offset=0.01,
            )

            result = transform_raw_manifest(manifest)

        self.assertEqual(len(result.records), 4)
        self.assertEqual(result.rejected_records, 0)

    def test_distant_wave_grid_produces_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            manifest = write_fixture(
                Path(temporary_directory),
                wave_coordinate_offset=1.0,
            )

            with self.assertRaises(OceanTransformationError):
                transform_raw_manifest(manifest)

    def test_incorrect_unit_is_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            manifest = write_fixture(
                Path(temporary_directory),
                temperature_unit="kelvin",
            )

            with self.assertRaises(OceanTransformationError):
                transform_raw_manifest(manifest)

    def test_mismatched_times_are_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            manifest = write_fixture(
                Path(temporary_directory),
                wave_time="2026-10-07T15:00:00",
            )

            with self.assertRaises(OceanTransformationError):
                transform_raw_manifest(manifest)

    def test_incorrect_manifest_source_is_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            manifest = write_fixture(
                Path(temporary_directory),
                source="incorrect-source",
            )

            with self.assertRaises(OceanTransformationError):
                transform_raw_manifest(manifest)


if __name__ == "__main__":
    unittest.main()