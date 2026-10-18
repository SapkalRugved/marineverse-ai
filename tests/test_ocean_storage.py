
"""Test configurable Copernicus ocean raw storage."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from backend.marine_data.ocean import retrieve_copernicus_ocean as ocean


class OceanStorageTests(unittest.TestCase):

    def test_default_repository_fallback(self) -> None:
        """Use the existing directory when no override is supplied."""
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                ocean.resolve_ocean_raw_directory(),
                ocean.RAW_DIRECTORY,
            )

    def test_environment_data_root(self) -> None:
        """Resolve ocean files below the external data root."""
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(
                os.environ,
                {"MARINEVERSE_DATA_DIR": directory},
            ):
                result = ocean.resolve_ocean_raw_directory()

            self.assertEqual(
                result,
                Path(directory).resolve() / "raw" / "ocean",
            )

    def test_explicit_directory_wins(self) -> None:
        """Explicit destination overrides the environment."""
        with tempfile.TemporaryDirectory() as configured_root:
            with tempfile.TemporaryDirectory() as explicit_root:
                with patch.dict(
                    os.environ,
                    {"MARINEVERSE_DATA_DIR": configured_root},
                ):
                    result = ocean.resolve_ocean_raw_directory(
                        Path(explicit_root)
                    )

                self.assertEqual(
                    result,
                    Path(explicit_root).resolve(),
                )

    def test_manifest_is_colocated_with_netcdf(self) -> None:
        """Keep manifest references beside both NetCDF files."""
        valid_time = datetime(
            2026, 10, 18, 9, 0, tzinfo=timezone.utc
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            physics_path = root / "physics.nc"
            wave_path = root / "wave.nc"

            manifest_path = ocean.retain_manifest(
                physics_path=physics_path,
                wave_path=wave_path,
                valid_time=valid_time,
                retrieved_at=valid_time,
                minimum_longitude=65.0,
                maximum_longitude=100.0,
                minimum_latitude=5.0,
                maximum_latitude=25.0,
            )

            self.assertEqual(manifest_path.parent, root)
            self.assertTrue(manifest_path.is_file())

            manifest = json.loads(
                manifest_path.read_text(encoding="utf-8")
            )

            self.assertEqual(
                manifest["source"],
                ocean.SOURCE,
            )

    def test_separate_netcdf_directories_are_rejected(self) -> None:
        """Reject manifest creation for separated source files."""
        valid_time = datetime(
            2026, 10, 18, 9, 0, tzinfo=timezone.utc
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            with self.assertRaises(ValueError):
                ocean.retain_manifest(
                    physics_path=root / "physics" / "physics.nc",
                    wave_path=root / "waves" / "wave.nc",
                    valid_time=valid_time,
                    retrieved_at=valid_time,
                    minimum_longitude=65.0,
                    maximum_longitude=100.0,
                    minimum_latitude=5.0,
                    maximum_latitude=25.0,
                )


if __name__ == "__main__":
    unittest.main()
