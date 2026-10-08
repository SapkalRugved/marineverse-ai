"""Shared PostgreSQL connection support for MarineVerse pipelines."""

from __future__ import annotations

import getpass
import os
from typing import Any

import psycopg
from psycopg import Connection


DEFAULT_DATABASE_HOST = "localhost"
DEFAULT_DATABASE_PORT = "5432"
DEFAULT_DATABASE_NAME = "marineverse"
DEFAULT_DATABASE_USER = "postgres"


def get_connection_parameters(
    prompt_for_password: bool = True,
) -> dict[str, Any]:
    """Build connection parameters without storing credentials."""
    password = os.getenv("PGPASSWORD")

    if prompt_for_password and password is None:
        password = getpass.getpass("PostgreSQL password: ")

    parameters: dict[str, Any] = {
        "host": os.getenv("PGHOST", DEFAULT_DATABASE_HOST),
        "port": os.getenv("PGPORT", DEFAULT_DATABASE_PORT),
        "dbname": os.getenv("PGDATABASE", DEFAULT_DATABASE_NAME),
        "user": os.getenv("PGUSER", DEFAULT_DATABASE_USER),
    }

    if password:
        parameters["password"] = password

    return parameters


def connect_to_database(
    prompt_for_password: bool = True,
) -> Connection:
    """Open a PostgreSQL connection using project defaults."""
    return psycopg.connect(
        **get_connection_parameters(prompt_for_password)
    )