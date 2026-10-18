
"""Resolve MarineVerse runtime data storage locations."""

from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_ROOT = PROJECT_ROOT / "data"

DATA_ROOT_ENVIRONMENT_VARIABLE = "MARINEVERSE_DATA_DIR"


def resolve_data_root(
    explicit_root: str | Path | None = None,
) -> Path:
    """Resolve the runtime data root using the frozen precedence."""

    if explicit_root is not None:
        value = str(explicit_root).strip()

        if not value:
            raise ValueError("Explicit data root cannot be empty.")

        return Path(value).expanduser().resolve()

    configured_root = os.getenv(DATA_ROOT_ENVIRONMENT_VARIABLE)

    if configured_root is not None:
        value = configured_root.strip()

        if not value:
            raise ValueError(
                f"{DATA_ROOT_ENVIRONMENT_VARIABLE} cannot be empty."
            )

        return Path(value).expanduser().resolve()

    return DEFAULT_DATA_ROOT


def resolve_data_directory(
    *parts: str,
    explicit_root: str | Path | None = None,
) -> Path:
    """Resolve a directory within the configured data root."""

    root = resolve_data_root(explicit_root)

    directory = root.joinpath(*parts)

    if not directory.resolve().is_relative_to(root.resolve()):
        raise ValueError("Data directory must remain inside the data root.")

    return directory
