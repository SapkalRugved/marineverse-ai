
"""Tests for configurable OpenStreetMap ports raw storage."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.marine_data.ports import retrieve_osm_ports as ports


class PortsStorageTests(unittest.TestCase):
    """Verify storage precedence and existing JSON retention."""

    def test_repository_fallback(self) -> None:
        """Use legacy repository storage when not configured."""

        with patch.dict(os.environ, {}, clear=True):
            result = ports.build_output_path()

        self.assertEqual(
            result.parent,
            ports.RAW_OUTPUT_DIRECTORY,
        )
        self.assertTrue(
            result.name.startswith("osm_ports_india_")
        )
        self.assertEqual(result.suffix, ".json")

    def test_environment_data_root(self) -> None:
        """Use the external data root when configured."""

        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(
                os.environ,
                {"MARINEVERSE_DATA_DIR": directory},
            ):
                result = ports.build_output_path()

            expected_directory = (
                Path(directory).resolve() / "raw" / "ports"
            )

            self.assertEqual(result.parent, expected_directory)

    def test_explicit_directory_overrides_environment(self) -> None:
        """Explicit output directory has highest precedence."""

        with tempfile.TemporaryDirectory() as environment_root:
            with tempfile.TemporaryDirectory() as explicit_directory:
                with patch.dict(
                    os.environ,
                    {"MARINEVERSE_DATA_DIR": environment_root},
                ):
                    result = ports.build_output_path(
                        Path(explicit_directory)
                    )

                self.assertEqual(
                    result.parent,
                    Path(explicit_directory),
                )

    def test_retain_raw_response_preserves_json(self) -> None:
        """Write unchanged Overpass JSON to the selected location."""

        payload = {
            "version": 0.6,
            "elements": [
                {
                    "type": "node",
                    "id": 123,
                    "lat": 18.95,
                    "lon": 72.85,
                    "tags": {
                        "name": "Test Port",
                        "harbour": "yes",
                    },
                }
            ],
        }

        with tempfile.TemporaryDirectory() as directory:
            output_file = Path(directory) / "raw" / "ports.json"

            ports.retain_raw_response(payload, output_file)

            self.assertTrue(output_file.is_file())
            self.assertFalse(
                output_file.with_suffix(".json.tmp").exists()
            )

            retained = json.loads(
                output_file.read_text(encoding="utf-8")
            )

            self.assertEqual(retained, payload)


if __name__ == "__main__":
    unittest.main()
