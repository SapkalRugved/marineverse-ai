
"""Tests for local and cloud PostgreSQL connection configuration."""

import os
import unittest
from unittest.mock import patch

from backend.marine_data.database import get_connection_parameters


class DatabaseConfigurationTests(unittest.TestCase):

    def test_local_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            params = get_connection_parameters(
                prompt_for_password=False
            )

        self.assertEqual(params["host"], "localhost")
        self.assertEqual(params["port"], "5432")
        self.assertEqual(params["dbname"], "marineverse")
        self.assertNotIn("sslmode", params)

    def test_cloud_tls_parameters(self):
        with patch.dict(
            os.environ,
            {
                "PGHOST": "db.example.com",
                "PGPORT": "5432",
                "PGDATABASE": "postgres",
                "PGUSER": "marineverse_app",
                "PGSSLMODE": "verify-full",
                "PGCONNECT_TIMEOUT": "10",
            },
            clear=True,
        ):
            params = get_connection_parameters(
                prompt_for_password=False
            )

        self.assertEqual(params["host"], "db.example.com")
        self.assertEqual(params["sslmode"], "verify-full")
        self.assertEqual(params["connect_timeout"], 10)

    def test_invalid_timeout_is_rejected(self):
        with patch.dict(
            os.environ,
            {"PGCONNECT_TIMEOUT": "abc"},
            clear=True,
        ):
            with self.assertRaises(ValueError):
                get_connection_parameters(
                    prompt_for_password=False
                )

    def test_invalid_sslmode_is_rejected(self):
        with patch.dict(
            os.environ,
            {"PGSSLMODE": "unsafe-mode"},
            clear=True,
        ):
            with self.assertRaises(ValueError):
                get_connection_parameters(
                    prompt_for_password=False
                )

    def test_search_path_option(self):
        with patch.dict(
            os.environ,
            {"PGOPTIONS": "-c search_path=public"},
            clear=True,
        ):
            params = get_connection_parameters(
                prompt_for_password=False
            )

        self.assertEqual(
            params["options"],
            "-c search_path=public",
        )


if __name__ == "__main__":
    unittest.main()
