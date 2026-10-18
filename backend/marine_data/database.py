"""Shared PostgreSQL connection support for MarineVerse."""

from __future__ import annotations

import getpass
import os
from pathlib import Path
from typing import Any

import psycopg
from dotenv import load_dotenv
from psycopg import Connection


DEFAULT_DATABASE_HOST = "localhost"
DEFAULT_DATABASE_PORT = "5432"
DEFAULT_DATABASE_NAME = "marineverse"
DEFAULT_DATABASE_USER = "postgres"

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENVIRONMENT_FILE = PROJECT_ROOT / ".env"

load_dotenv(
    dotenv_path=ENVIRONMENT_FILE,
    override=False,
)


def get_connection_parameters(
    prompt_for_password: bool = True,
) -> dict[str, Any]:
    """Build connection parameters without storing credentials in code."""
    password = os.getenv("PGPASSWORD")

    if prompt_for_password and password is None:
        password = getpass.getpass("PostgreSQL password: ")

    parameters: dict[str, Any] = {
        "host": os.getenv(
            "PGHOST",
            DEFAULT_DATABASE_HOST,
        ),
        "port": os.getenv(
            "PGPORT",
            DEFAULT_DATABASE_PORT,
        ),
        "dbname": os.getenv(
            "PGDATABASE",
            DEFAULT_DATABASE_NAME,
        ),
        "user": os.getenv(
            "PGUSER",
            DEFAULT_DATABASE_USER,
        ),
    }

    if password:
        parameters["password"] = password

    sslmode = os.getenv("PGSSLMODE")
    if sslmode:
        allowed_modes = {
            "disable",
            "allow",
            "prefer",
            "require",
            "verify-ca",
            "verify-full",
        }
        if sslmode not in allowed_modes:
            raise ValueError("Invalid PGSSLMODE value.")
        parameters["sslmode"] = sslmode

    timeout = os.getenv("PGCONNECT_TIMEOUT")
    if timeout is not None:
        try:
            timeout_seconds = int(timeout)
        except ValueError as exc:
            raise ValueError(
                "PGCONNECT_TIMEOUT must be a positive integer."
            ) from exc

        if timeout_seconds <= 0:
            raise ValueError(
                "PGCONNECT_TIMEOUT must be a positive integer."
            )

        parameters["connect_timeout"] = timeout_seconds

    options = os.getenv("PGOPTIONS")
    if options:
        parameters["options"] = options

    return parameters


def connect_to_database(
    prompt_for_password: bool = True,
) -> Connection:
    """Open a PostgreSQL connection using project configuration."""
    return psycopg.connect(
        **get_connection_parameters(prompt_for_password)
    )
