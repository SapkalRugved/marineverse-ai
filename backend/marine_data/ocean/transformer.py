"""Transform Copernicus NetCDF subsets into validated ocean records."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import xarray as xr

from backend.marine_data.ocean.retrieve_copernicus_ocean import (
    PHYSICS_DATASET,
    PHYSICS_VARIABLES,
    SOURCE,
    WAVE_DATASET,
    WAVE_VARIABLES,
)


SOURCE_DATASET = f"{PHYSICS_DATASET}+{WAVE_DATASET}"
GRID_TOLERANCE_DEGREES = 0.05

EXPECTED_UNITS = {
    "thetao": "degrees_C",
    "uo": "m s-1",
    "vo": "m s-1",
    "VHM0": "m",
    "VMDR": "degree",
    "VTM02": "s",
}


class OceanTransformationError(RuntimeError):
    """Raised when raw Copernicus data cannot be transformed."""


@dataclass(frozen=True, slots=True)
class OceanRecord:
    """Validated ocean-condition record."""

    valid_time: datetime
    latitude: float
    longitude: float
    depth_m: float
    current_u_mps: float
    current_v_mps: float
    current_speed_mps: float
    current_direction_deg: float
    sea_surface_temperature_c: float
    wave_height_m: float
    wave_direction_deg: float
    wave_period_s: float
    is_forecast: bool
    source: str
    source_dataset: str
    ingested_at: datetime


@dataclass(frozen=True, slots=True)
class OceanTransformationResult:
    """Summary and records produced by one transformation."""

    records: list[OceanRecord]
    source_grid_cells: int
    rejected_records: int


def parse_utc_datetime(value: str, field_name: str) -> datetime:
    """Parse one timezone-aware timestamp and normalize it to UTC."""
    try:
        parsed = datetime.fromisoformat(
            value.strip().replace("Z", "+00:00")
        )
    except (AttributeError, ValueError) as exc:
        raise OceanTransformationError(
            f"{field_name} is not a valid ISO-8601 timestamp."
        ) from exc

    if parsed.tzinfo is None:
        raise OceanTransformationError(
            f"{field_name} must include timezone information."
        )

    return parsed.astimezone(timezone.utc)


def coordinate_time_to_datetime(value: np.datetime64) -> datetime:
    """Convert a NumPy datetime coordinate into UTC."""
    if np.isnat(value):
        raise OceanTransformationError(
            "NetCDF time coordinate cannot be NaT."
        )

    seconds = value.astype("datetime64[s]").astype(np.int64)
    return datetime.fromtimestamp(int(seconds), timezone.utc)


def require_single_time(dataset: xr.Dataset, name: str) -> datetime:
    """Read and validate the single time coordinate."""
    if "time" not in dataset.coords:
        raise OceanTransformationError(
            f"{name} dataset has no time coordinate."
        )

    if dataset.sizes.get("time") != 1:
        raise OceanTransformationError(
            f"{name} dataset must contain exactly one time value."
        )

    return coordinate_time_to_datetime(
        np.asarray(dataset["time"].values)[0]
    )


def require_variables(
    dataset: xr.Dataset,
    variables: tuple[str, ...],
    name: str,
) -> None:
    """Require expected variables and exact units."""
    for variable_name in variables:
        if variable_name not in dataset.data_vars:
            raise OceanTransformationError(
                f"{name} dataset is missing {variable_name}."
            )

        actual_unit = dataset[variable_name].attrs.get("units")
        expected_unit = EXPECTED_UNITS[variable_name]

        if actual_unit != expected_unit:
            raise OceanTransformationError(
                f"{variable_name} unit must be {expected_unit!r}; "
                f"received {actual_unit!r}."
            )


def read_surface_array(
    dataset: xr.Dataset,
    variable_name: str,
) -> np.ndarray:
    """Read one variable as a latitude-by-longitude surface array."""
    variable = dataset[variable_name]

    if "time" in variable.dims:
        variable = variable.isel(time=0)

    if "depth" in variable.dims:
        if variable.sizes["depth"] != 1:
            raise OceanTransformationError(
                f"{variable_name} must contain exactly one depth."
            )
        variable = variable.isel(depth=0)

    required_dimensions = {"latitude", "longitude"}

    if not required_dimensions.issubset(variable.dims):
        raise OceanTransformationError(
            f"{variable_name} is missing latitude or longitude."
        )

    return np.asarray(
        variable.transpose("latitude", "longitude").values,
        dtype=float,
    )


def calculate_current_direction(
    eastward_velocity: float,
    northward_velocity: float,
) -> float:
    """Calculate current-to direction clockwise from true north."""
    direction = math.degrees(
        math.atan2(eastward_velocity, northward_velocity)
    )
    return direction % 360.0


def transform_raw_manifest(
    manifest_path: Path,
    *,
    ingested_at: datetime | None = None,
) -> OceanTransformationResult:
    """Transform one physics/wave manifest into ocean records."""
    try:
        manifest = json.loads(
            manifest_path.read_text(encoding="utf-8")
        )
    except OSError as exc:
        raise OceanTransformationError(
            f"Could not read manifest: {manifest_path}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise OceanTransformationError(
            f"Manifest is not valid JSON: {manifest_path}"
        ) from exc

    if manifest.get("source") != SOURCE:
        raise OceanTransformationError(
            f"Manifest source must be {SOURCE!r}."
        )

    valid_time = parse_utc_datetime(
        manifest.get("valid_time"),
        "valid_time",
    )
    retrieved_at = parse_utc_datetime(
        manifest.get("retrieved_at"),
        "retrieved_at",
    )

    physics_metadata = manifest.get("physics")
    wave_metadata = manifest.get("waves")

    if not isinstance(physics_metadata, dict):
        raise OceanTransformationError(
            "Manifest physics metadata is missing."
        )

    if not isinstance(wave_metadata, dict):
        raise OceanTransformationError(
            "Manifest wave metadata is missing."
        )

    if physics_metadata.get("dataset_id") != PHYSICS_DATASET:
        raise OceanTransformationError(
            "Manifest physics dataset ID is incorrect."
        )

    if wave_metadata.get("dataset_id") != WAVE_DATASET:
        raise OceanTransformationError(
            "Manifest wave dataset ID is incorrect."
        )

    physics_path = manifest_path.parent / physics_metadata["file"]
    wave_path = manifest_path.parent / wave_metadata["file"]

    transformed_at = ingested_at or datetime.now(timezone.utc)

    if transformed_at.tzinfo is None:
        raise OceanTransformationError(
            "ingested_at must include timezone information."
        )

    transformed_at = transformed_at.astimezone(timezone.utc)

    try:
        with (
            xr.open_dataset(physics_path) as physics_dataset,
            xr.open_dataset(wave_path) as wave_dataset,
        ):
            require_variables(
                physics_dataset,
                PHYSICS_VARIABLES,
                "Physics",
            )
            require_variables(
                wave_dataset,
                WAVE_VARIABLES,
                "Wave",
            )

            physics_time = require_single_time(
                physics_dataset,
                "Physics",
            )
            wave_time = require_single_time(
                wave_dataset,
                "Wave",
            )

            if physics_time != wave_time:
                raise OceanTransformationError(
                    "Physics and wave timestamps do not match."
                )

            if physics_time != valid_time:
                raise OceanTransformationError(
                    "NetCDF time does not match manifest valid_time."
                )

            if "depth" not in physics_dataset.coords:
                raise OceanTransformationError(
                    "Physics dataset has no depth coordinate."
                )

            if physics_dataset.sizes.get("depth") != 1:
                raise OceanTransformationError(
                    "Physics dataset must contain one surface depth."
                )

            depth_m = float(
                np.asarray(physics_dataset["depth"].values)[0]
            )

            if not math.isfinite(depth_m) or depth_m < 0:
                raise OceanTransformationError(
                    "Physics depth is invalid."
                )

            physics_latitudes = np.asarray(
                physics_dataset["latitude"].values,
                dtype=float,
            )
            physics_longitudes = np.asarray(
                physics_dataset["longitude"].values,
                dtype=float,
            )

            if len(np.unique(physics_latitudes)) != len(
                physics_latitudes
            ):
                raise OceanTransformationError(
                    "Physics latitude coordinates contain duplicates."
                )

            if len(np.unique(physics_longitudes)) != len(
                physics_longitudes
            ):
                raise OceanTransformationError(
                    "Physics longitude coordinates contain duplicates."
                )

            aligned_waves = wave_dataset.reindex(
                latitude=physics_dataset["latitude"],
                longitude=physics_dataset["longitude"],
                method="nearest",
                tolerance=GRID_TOLERANCE_DEGREES,
            )

            temperature = read_surface_array(
                physics_dataset,
                "thetao",
            )
            current_u = read_surface_array(
                physics_dataset,
                "uo",
            )
            current_v = read_surface_array(
                physics_dataset,
                "vo",
            )
            wave_height = read_surface_array(
                aligned_waves,
                "VHM0",
            )
            wave_direction = read_surface_array(
                aligned_waves,
                "VMDR",
            )
            wave_period = read_surface_array(
                aligned_waves,
                "VTM02",
            )

    except OSError as exc:
        raise OceanTransformationError(
            "Could not open a Copernicus NetCDF file."
        ) from exc

    latitude_grid, longitude_grid = np.meshgrid(
        physics_latitudes,
        physics_longitudes,
        indexing="ij",
    )

    source_grid_cells = int(latitude_grid.size)

    valid_mask = (
        np.isfinite(latitude_grid)
        & np.isfinite(longitude_grid)
        & np.isfinite(temperature)
        & np.isfinite(current_u)
        & np.isfinite(current_v)
        & np.isfinite(wave_height)
        & np.isfinite(wave_direction)
        & np.isfinite(wave_period)
        & (latitude_grid >= -90)
        & (latitude_grid <= 90)
        & (longitude_grid >= -180)
        & (longitude_grid <= 180)
        & (temperature >= -5)
        & (temperature <= 50)
        & (np.abs(current_u) <= 10)
        & (np.abs(current_v) <= 10)
        & (wave_height >= 0)
        & (wave_height <= 50)
        & (wave_direction >= 0)
        & (wave_direction <= 360)
        & (wave_period > 0)
        & (wave_period <= 60)
    )

    records: list[OceanRecord] = []

    for latitude_index, longitude_index in zip(
        *np.nonzero(valid_mask),
        strict=True,
    ):
        u_value = float(current_u[latitude_index, longitude_index])
        v_value = float(current_v[latitude_index, longitude_index])

        records.append(
            OceanRecord(
                valid_time=valid_time,
                latitude=float(
                    latitude_grid[
                        latitude_index,
                        longitude_index,
                    ]
                ),
                longitude=float(
                    longitude_grid[
                        latitude_index,
                        longitude_index,
                    ]
                ),
                depth_m=depth_m,
                current_u_mps=u_value,
                current_v_mps=v_value,
                current_speed_mps=math.hypot(u_value, v_value),
                current_direction_deg=calculate_current_direction(
                    u_value,
                    v_value,
                ),
                sea_surface_temperature_c=float(
                    temperature[
                        latitude_index,
                        longitude_index,
                    ]
                ),
                wave_height_m=float(
                    wave_height[
                        latitude_index,
                        longitude_index,
                    ]
                ),
                wave_direction_deg=(
                    float(
                        wave_direction[
                            latitude_index,
                            longitude_index,
                        ]
                    )
                    % 360.0
                ),
                wave_period_s=float(
                    wave_period[
                        latitude_index,
                        longitude_index,
                    ]
                ),
                is_forecast=valid_time > retrieved_at,
                source=SOURCE,
                source_dataset=SOURCE_DATASET,
                ingested_at=transformed_at,
            )
        )

    if not records:
        raise OceanTransformationError(
            "Transformation produced zero valid ocean records."
        )

    return OceanTransformationResult(
        records=records,
        source_grid_cells=source_grid_cells,
        rejected_records=source_grid_cells - len(records),
    )