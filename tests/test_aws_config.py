
import os
import unittest
from unittest.mock import patch

from backend.marine_data.aws_config import get_aws_config


class AWSConfigTests(unittest.TestCase):
    def test_default_config(self):
        with patch.dict(os.environ, {}, clear=True):
            config = get_aws_config()
        self.assertEqual(config["region"], "ap-south-1")
        self.assertFalse(config["storage_ready"])

    def test_valid_bucket(self):
        with patch.dict(
            os.environ,
            {
                "AWS_REGION": "ap-south-1",
                "MARINEVERSE_S3_BUCKET": "marineverse-stage-example-123",
            },
            clear=True,
        ):
            config = get_aws_config()
        self.assertTrue(config["storage_ready"])

    def test_invalid_bucket(self):
        with patch.dict(
            os.environ,
            {"MARINEVERSE_S3_BUCKET": "Invalid_Bucket"},
            clear=True,
        ):
            with self.assertRaises(ValueError):
                get_aws_config()

    def test_invalid_region(self):
        with patch.dict(
            os.environ,
            {"AWS_REGION": "invalid"},
            clear=True,
        ):
            with self.assertRaises(ValueError):
                get_aws_config()


if __name__ == "__main__":
    unittest.main()
