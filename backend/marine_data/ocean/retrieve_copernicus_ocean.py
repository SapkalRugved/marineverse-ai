"""Retrieve near-real-time ocean conditions from Copernicus Marine."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Sequence

import copernicusmarine


SOURCE = "copernicus-marine"

PHYSICS_DATASET = "cmems_mod_glo_phy_anfc_0.083deg_PT1H-m"
WAVE_DATASET = "cmems_mod_glo_wav_anfc_0.083deg_PT3H-i"

PHYSICS_VARIABLES = ("thetao", "uo", "vo")
WAVE_VARIABLES = ("VHM0", "VMDR", "VTM02")

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RAW_DIRECTORY = PROJECT_ROOT / "data" / "raw" / "ocean"

DEFAULT_MIN_LONGITUDE = 65.0
DEFAULT_MAX_LONGITUDE = 100.0
DEFAULT_MIN_LATITUDE = 5.0
DEFAULT_MAX_LATITUDE = 25.0


class OceanRetrievalError(RuntimeError):
    """Raised when Copernicus ocean data cannot be retrieved."""


def select_default_valid_time(
    current_time: datetime | None = None,
) -> datetime:
    """Select the previous complete three-hour Copernicus interval."""
    now = current_time or datetime.now(timezone.utc)

    if now.tzinfo is None:
        raise ValueError("Current time must include timezone information.")

    candidate = now.astimezone(timezone.utc) - timedelta(hours=3)
    aligned_hour = (candidate.hour // 3) * 3

    return candidate.replace(
        hour=aligned_hour,
        minute=0,
        second=0,
        microsecond=0,
    )


def parse_valid_time(value: str) -> datetime:
    """Parse a timezone-aware ISO-8601 timestamp."""
    normalized = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)

    if parsed.tzinfo is None:
        raise ValueError(
            "Valid time must include a timezone, such as Z or +00:00."
        )

    parsed = parsed.astimezone(timezone.utc)

    if parsed.minute or parsed.second or parsed.microsecond:
        raise ValueError("Valid time must use a complete model hour.")

    if parsed.hour % 3:
        raise ValueError(
            "Valid time must align to a three-hour wave interval."
        )

    return parsed


def validate_bounds(
    minimum_longitude: float,
    maximum_longitude: float,
    minimum_latitude: float,
    maximum_latitude: float,
) -> None:
    """Validate requested geographic bounds."""
    if not -180 <= minimum_longitude < maximum_longitude <= 180:
        raise ValueError("Invalid longitude bounds.")

    if not -90 <= minimum_latitude < maximum_latitude <= 90:
        raise ValueError("Invalid latitude bounds.")


def format_timestamp(value: datetime) -> str:
    """Format a UTC timestamp for filenames."""
    return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def retrieve_subset(
    *,
    dataset_id: str,
    variables: Sequence[str],
    output_path: Path,
    valid_time: datetime,
    minimum_longitude: float,
    maximum_longitude: float,
    minimum_latitude: float,
    maximum_latitude: float,
) -> Path:
    """Download one Copernicus NetCDF subset."""
    copernicusmarine.subset(
        dataset_id=dataset_id,
        variables=list(variables),
        minimum_longitude=minimum_longitude,
        maximum_longitude=maximum_longitude,
        minimum_latitude=minimum_latitude,
        maximum_latitude=maximum_latitude,
        start_datetime=valid_time,
        end_datetime=valid_time,
        coordinates_selection_method="nearest",
        output_directory=output_path.parent,
        output_filename=output_path.name,
        overwrite=True,
        disable_progress_bar=True,
    )

    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise OceanRetrievalError(
            f"Copernicus did not create a valid file: {output_path}"
        )

    return output_path


def retain_manifest(
    *,
    physics_path: Path,
    wave_path: Path,
    valid_time: datetime,
    retrieved_at: datetime,
    minimum_longitude: float,
    maximum_longitude: float,
    minimum_latitude: float,
    maximum_latitude: float,
) -> Path:
    """Retain metadata describing the two raw Copernicus subsets."""
    timestamp = format_timestamp(valid_time)
    output_path = (
        RAW_DIRECTORY
        / f"copernicus_ocean_india_{timestamp}_manifest.json"
    )
    temporary_path = output_path.with_suffix(".json.tmp")

    manifest = {
        "source": SOURCE,
        "retrieved_at": retrieved_at.isoformat(),
        "valid_time": valid_time.isoformat(),
        "bounds": {
            "minimum_longitude": minimum_longitude,
            "maximum_longitude": maximum_longitude,
            "minimum_latitude": minimum_latitude,
            "maximum_latitude": maximum_latitude,
        },
        "physics": {
            "dataset_id": PHYSICS_DATASET,
            "variables": list(PHYSICS_VARIABLES),
            "file": physics_path.name,
        },
        "waves": {
            "dataset_id": WAVE_DATASET,
            "variables": list(WAVE_VARIABLES),
            "file": wave_path.name,
        },
    }

    with temporary_path.open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as output_file:
        json.dump(manifest, output_file, ensure_ascii=False, indent=2)
        output_file.write("\n")

    temporary_path.replace(output_path)
    return output_path


def parse_arguments() -> argparse.Namespace:
    """Parse retrieval options."""
    parser = argparse.ArgumentParser(
        description=(
            "Retrieve Copernicus surface currents, temperature and "
            "wave conditions for the Indian marine region."
        )
    )
    parser.add_argument(
        "--valid-time",
        type=parse_valid_time,
        help=(
            "UTC model time aligned to three hours, for example "
            "2026-10-07T12:00:00Z. Defaults to the previous complete "
            "three-hour interval."
        ),
    )
    parser.add_argument(
        "--minimum-longitude",
        type=float,
        default=DEFAULT_MIN_LONGITUDE,
    )
    parser.add_argument(
        "--maximum-longitude",
        type=float,
        default=DEFAULT_MAX_LONGITUDE,
    )
    parser.add_argument(
        "--minimum-latitude",
        type=float,
        default=DEFAULT_MIN_LATITUDE,
    )
    parser.add_argument(
        "--maximum-latitude",
        type=float,
        default=DEFAULT_MAX_LATITUDE,
    )
    return parser.parse_args()


def main() -> int:
    """Retrieve physics and wave subsets plus a metadata manifest."""
    arguments = parse_arguments()

    try:
        validate_bounds(
            arguments.minimum_longitude,
            arguments.maximum_longitude,
            arguments.minimum_latitude,
            arguments.maximum_latitude,
        )

        valid_time = (
            arguments.valid_time
            if arguments.valid_time is not None
            else select_default_valid_time()
        )
        retrieved_at = datetime.now(timezone.utc)
        timestamp = format_timestamp(valid_time)

        RAW_DIRECTORY.mkdir(parents=True, exist_ok=True)

        physics_path = (
            RAW_DIRECTORY
            / f"copernicus_phy_india_{timestamp}.nc"
        )
        wave_path = (
            RAW_DIRECTORY
            / f"copernicus_wav_india_{timestamp}.nc"
        )

        print(f"Selected model time: {valid_time.isoformat()}")
        print("Retrieving Copernicus physics subset...")

        retrieve_subset(
            dataset_id=PHYSICS_DATASET,
            variables=PHYSICS_VARIABLES,
            output_path=physics_path,
            valid_time=valid_time,
            minimum_longitude=arguments.minimum_longitude,
            maximum_longitude=arguments.maximum_longitude,
            minimum_latitude=arguments.minimum_latitude,
            maximum_latitude=arguments.maximum_latitude,
        )

        print("Retrieving Copernicus wave subset...")

        retrieve_subset(
            dataset_id=WAVE_DATASET,
            variables=WAVE_VARIABLES,
            output_path=wave_path,
            valid_time=valid_time,
            minimum_longitude=arguments.minimum_longitude,
            maximum_longitude=arguments.maximum_longitude,
            minimum_latitude=arguments.minimum_latitude,
            maximum_latitude=arguments.maximum_latitude,
        )

        manifest_path = retain_manifest(
            physics_path=physics_path,
            wave_path=wave_path,
            valid_time=valid_time,
            retrieved_at=retrieved_at,
            minimum_longitude=arguments.minimum_longitude,
            maximum_longitude=arguments.maximum_longitude,
            minimum_latitude=arguments.minimum_latitude,
            maximum_latitude=arguments.maximum_latitude,
        )

        print("Copernicus ocean retrieval completed successfully.")
        print(f"Physics file: {physics_path}")
        print(f"Wave file: {wave_path}")
        print(f"Manifest file: {manifest_path}")
        return 0

    except (OceanRetrievalError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(
            f"ERROR: Copernicus retrieval failed: {exc}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())