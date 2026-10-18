
"""Tests for MarineVerse database compatibility evaluation."""

import unittest

from backend.marine_data.check_database_compatibility import (
    REQUIRED_TABLES,
    evaluate_compatibility,
)


def sample_facts():
    return {
        "postgres_version": 180006,
        "search_path": '"$user", public',
        "geography_visible": True,
        "postgis_version": "3.6.2",
        "postgis_schema": "public",
        "tables": list(REQUIRED_TABLES),
        "read_permissions": {
            table: True for table in REQUIRED_TABLES
        },
        "ssl_in_use": False,
    }


class DatabaseCompatibilityTests(unittest.TestCase):

    def test_compatible_database(self):
        report = evaluate_compatibility(sample_facts())
        self.assertTrue(report["compatible"])

    def test_missing_table(self):
        facts = sample_facts()
        facts["tables"].remove("ocean_conditions")

        report = evaluate_compatibility(facts)

        self.assertFalse(report["compatible"])
        self.assertIn(
            "ocean_conditions",
            report["details"]["missing_tables"],
        )

    def test_missing_postgis(self):
        facts = sample_facts()
        facts["postgis_version"] = None
        facts["geography_visible"] = False

        report = evaluate_compatibility(facts)
        self.assertFalse(report["compatible"])

    def test_missing_read_permission(self):
        facts = sample_facts()
        facts["read_permissions"]["vessels"] = False

        report = evaluate_compatibility(facts)
        self.assertFalse(report["compatible"])

    def test_unsupported_postgresql_version(self):
        facts = sample_facts()
        facts["postgres_version"] = 170000

        report = evaluate_compatibility(facts)
        self.assertFalse(report["compatible"])


if __name__ == "__main__":
    unittest.main()
