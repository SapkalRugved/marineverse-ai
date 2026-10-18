
"""Tests for MarineVerse runtime storage path configuration."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.marine_data.storage import (
    DEFAULT_DATA_ROOT,
    resolve_data_directory,
    resolve_data_root,
)


class StorageTests(unittest.TestCase):
    """Verify storage precedence and safe directory resolution."""

    def test_repository_fallback(self) -> None:
        """Use existing repository storage when nothing is configured."""

        with patch.dict(
            os.environ,
            {"MARINEVERSE_DATA_DIR": ""},
        ):
            with self.assertRaises(ValueError):
                resolve_data_root()

        with patch.dict(
            os.environ,
            {},
            clear=True,
        ):
            self.assertEqual(
                resolve_data_root(),
                DEFAULT_DATA_ROOT,
            )

    def test_environment_root(self) -> None:
        """Use the configured external directory."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            with patch.dict(
                os.environ,
                {"MARINEVERSE_DATA_DIR": temporary_directory},
            ):
                self.assertEqual(
                    resolve_data_root(),
                    Path(temporary_directory).resolve(),
                )

    def test_explicit_root_overrides_environment(self) -> None:
        """Explicit roots take precedence over environment settings."""

        with tempfile.TemporaryDirectory() as explicit_directory:
            with tempfile.TemporaryDirectory() as environment_directory:
                with patch.dict(
                    os.environ,
                    {"MARINEVERSE_DATA_DIR": environment_directory},
                ):
                    self.assertEqual(
                        resolve_data_root(explicit_directory),
                        Path(explicit_directory).resolve(),
                    )

    def test_resolve_ais_directory(self) -> None:
        """Resolve a dataset directory below the root."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            result = resolve_data_directory(
                "raw",
                "ais",
                explicit_root=temporary_directory,
            )

            self.assertEqual(
                result,
                Path(temporary_directory).resolve()
                / "raw"
                / "ais",
            )

    def test_path_traversal_is_rejected(self) -> None:
        """Reject paths that escape the configured data root."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            with self.assertRaises(ValueError):
                resolve_data_directory(
                    "..",
                    "outside",
                    explicit_root=temporary_directory,
                )

    def test_empty_explicit_root_is_rejected(self) -> None:
        """Do not accept an empty explicit storage root."""

        with self.assertRaises(ValueError):
            resolve_data_root("")


if __name__ == "__main__":
    unittest.main()
