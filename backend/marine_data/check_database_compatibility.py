
"""Read-only PostgreSQL/PostGIS compatibility check for MarineVerse."""

from __future__ import annotations

import json
import sys
from typing import Any

import psycopg

from backend.marine_data.database import connect_to_database


REQUIRED_TABLES = (
    "ports",
    "vessels",
    "vessel_positions",
    "weather_conditions",
    "ocean_conditions",
    "ingestion_runs",
)


def evaluate_compatibility(
    facts: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate database metadata without changing the database."""

    version = facts["postgres_version"]
    tables = set(facts["tables"])

    checks = {
        "postgresql_18_or_newer": version >= 180000,
        "postgis_installed": facts["postgis_version"] is not None,
        "postgis_types_visible": facts["geography_visible"],
        "frozen_tables_present": set(REQUIRED_TABLES) <= tables,
        "frozen_tables_readable": all(
            facts["read_permissions"].get(table, False)
            for table in REQUIRED_TABLES
        ),
    }

    return {
        "compatible": all(checks.values()),
        "checks": checks,
        "details": {
            "postgres_version_num": version,
            "postgis_version": facts["postgis_version"],
            "postgis_schema": facts["postgis_schema"],
            "search_path": facts["search_path"],
            "ssl_in_use": facts["ssl_in_use"],
            "missing_tables": sorted(
                set(REQUIRED_TABLES) - tables
            ),
        },
    }


def collect_database_facts(
    connection: psycopg.Connection,
) -> dict[str, Any]:
    """Collect catalog metadata inside a read-only transaction."""

    with connection.transaction():
        connection.execute("SET TRANSACTION READ ONLY")

        row = connection.execute(
            """
            SELECT
                current_setting('server_version_num')::integer,
                current_setting('search_path'),
                to_regtype('geography') IS NOT NULL
            """
        ).fetchone()

        extension = connection.execute(
            """
            SELECT e.extversion, n.nspname
            FROM pg_extension AS e
            JOIN pg_namespace AS n
              ON n.oid = e.extnamespace
            WHERE e.extname = 'postgis'
            """
        ).fetchone()

        rows = connection.execute(
            """
            SELECT tablename
            FROM pg_tables
            WHERE schemaname = 'public'
            """
        ).fetchall()

        permissions = connection.execute(
            """
            SELECT
                tablename,
                has_table_privilege(
                    format('%I.%I', schemaname, tablename),
                    'SELECT'
                )
            FROM pg_tables
            WHERE schemaname = 'public'
            """
        ).fetchall()

        ssl_row = connection.execute(
            """
            SELECT ssl
            FROM pg_stat_ssl
            WHERE pid = pg_backend_pid()
            """
        ).fetchone()

    return {
        "postgres_version": row[0],
        "search_path": row[1],
        "geography_visible": row[2],
        "postgis_version": extension[0] if extension else None,
        "postgis_schema": extension[1] if extension else None,
        "tables": [item[0] for item in rows],
        "read_permissions": dict(permissions),
        "ssl_in_use": ssl_row[0] if ssl_row else None,
    }


def main() -> int:
    """Print the compatibility report and return an exit status."""

    try:
        with connect_to_database(
            prompt_for_password=False
        ) as connection:
            facts = collect_database_facts(connection)

        report = evaluate_compatibility(facts)

        print(json.dumps(report, indent=2))
        return 0 if report["compatible"] else 1

    except (psycopg.Error, ValueError, OSError) as exc:
        print(
            f"Database compatibility check failed: {type(exc).__name__}",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
