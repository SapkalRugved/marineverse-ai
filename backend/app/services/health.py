"""Readiness checks for API dependencies."""

from __future__ import annotations

import psycopg

from backend.marine_data.database import connect_to_database


def database_is_ready() -> bool:
    """Return whether PostgreSQL accepts a simple query."""
    try:
        with connect_to_database(
            prompt_for_password=False,
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1;")
                result = cursor.fetchone()

        return result == (1,)

    except psycopg.Error:
        return False
