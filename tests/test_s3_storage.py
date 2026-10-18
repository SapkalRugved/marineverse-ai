
"""Tests for optional MarineVerse S3 upload planning."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from backend.marine_data.s3_storage import (
    plan_uploads,
    upload_files,
)


class S3StorageTests(unittest.TestCase):

    def test_ocean_files_keep_relative_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ocean = root / "raw" / "ocean"
            ocean.mkdir(parents=True)

            (ocean / "manifest.json").write_text("{}")
            (ocean / "currents.nc").write_bytes(b"sample")

            uploads = plan_uploads(
                ocean,
                data_root=root,
            )

            keys = {key for _, key in uploads}

            self.assertEqual(
                keys,
                {
                    "raw/ocean/manifest.json",
                    "raw/ocean/currents.nc",
                },
            )

    def test_source_outside_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            with tempfile.TemporaryDirectory() as outside:
                source = Path(outside) / "example.json"
                source.write_text("{}")

                with self.assertRaises(ValueError):
                    plan_uploads(source, data_root=root)

    def test_invalid_prefix_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / "example.json"
            file.write_text("{}")

            with self.assertRaises(ValueError):
                plan_uploads(
                    file,
                    data_root=temp,
                    prefix="../outside",
                )

    def test_dry_run_does_not_call_aws(self):
        fake_client = Mock()

        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / "example.json"
            file.write_text("{}")

            uploads = plan_uploads(
                file,
                data_root=temp,
            )

            count = upload_files(
                uploads,
                bucket="test-bucket",
                execute=False,
                s3_client=fake_client,
            )

            self.assertEqual(count, 1)
            fake_client.upload_file.assert_not_called()

    def test_explicit_upload_uses_client(self):
        fake_client = Mock()

        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / "example.json"
            file.write_text("{}")

            uploads = plan_uploads(
                file,
                data_root=temp,
            )

            count = upload_files(
                uploads,
                bucket="test-bucket",
                execute=True,
                s3_client=fake_client,
            )

            self.assertEqual(count, 1)
            fake_client.upload_file.assert_called_once_with(
                str(file.resolve()),
                "test-bucket",
                "example.json",
            )

    def test_execute_requires_bucket(self):
        with self.assertRaises(ValueError):
            upload_files(
                [],
                bucket="",
                execute=True,
                s3_client=Mock(),
            )


if __name__ == "__main__":
    unittest.main()
