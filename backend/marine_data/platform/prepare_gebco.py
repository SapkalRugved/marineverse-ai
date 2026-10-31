"""Prepare genuine GEBCO ZIP into a clearly labeled bounded-resolution NetCDF.

Source archive is retained unchanged. Selects *original grid points* using a
declared stride, never interpolates or invents depths. Preview is read-only.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
import tempfile
from pathlib import Path
from zipfile import ZipFile

from backend.marine_data.storage import resolve_data_root
from backend.marine_data.platform.pipeline import run, digest

MAX_CELLS = 1_800_000
SOURCE_URL = "https://www.gebco.net/data_and_products/gridded_bathymetry_data/"


def locate_member(archive: ZipFile):
    nc = [entry for entry in archive.infolist()
          if not entry.is_dir() and entry.filename.lower().endswith(".nc")]
    if len(nc) != 1:
        raise ValueError("GEBCO ZIP must contain exactly one NetCDF grid")
    member = nc[0]
    if member.file_size > 2 * 1024 ** 3:
        raise ValueError("GEBCO uncompressed NetCDF exceeds preparation limit")
    return member


def geometry(path: Path) -> dict:
    import xarray as xr
    with xr.open_dataset(path) as source:
        required = {"lat", "lon", "elevation"}
        if not required.issubset(source.variables):
            raise ValueError("GEBCO NetCDF missing lat/lon/elevation")
        elev = source["elevation"]
        if set(elev.dims) != {"lat", "lon"}:
            raise ValueError("GEBCO elevation must use 2D lat/lon grid")
        if source["lat"].attrs.get("units") != "degrees_north":
            raise ValueError("Unexpected latitude units")
        if source["lon"].attrs.get("units") != "degrees_east":
            raise ValueError("Unexpected longitude units")
        if elev.attrs.get("units") not in {"m", "meters", "metres"}:
            raise ValueError("Unexpected elevation units")
        lat, lon = source.sizes["lat"], source.sizes["lon"]
        stride = max(1, math.ceil(math.sqrt(lat * lon / MAX_CELLS)))
        while math.ceil(lat / stride) * math.ceil(lon / stride) > MAX_CELLS:
            stride += 1
        return {
            "source_cells": lat * lon,
            "selected_cells": math.ceil(lat / stride) * math.ceil(lon / stride),
            "sample_stride": stride,
            "resolution_reduced": stride > 1,
            "source_bounds": [
                float(source["lon"].min().item()),
                float(source["lat"].min().item()),
                float(source["lon"].max().item()),
                float(source["lat"].max().item()),
            ],
        }


def prepare(archive_path: Path, root: Path, *, execute=False, publish=False):
    if publish and not execute:
        raise ValueError("--publish requires --execute")
    archive_path = Path(archive_path).resolve()
    root = Path(root).resolve()
    if not archive_path.is_file():
        raise FileNotFoundError("GEBCO source archive not found")
    if not archive_path.is_relative_to(root):
        raise ValueError("GEBCO archive must be under the data root")
    # Temp copy uses safe basename rather than extracting arbitrary archive paths.
    with ZipFile(archive_path) as archive:
        member = locate_member(archive)
        with tempfile.TemporaryDirectory() as scratch:
            src = Path(scratch) / "source.nc"
            with archive.open(member) as opened, src.open("wb") as dest:
                shutil.copyfileobj(opened, dest)
            info = geometry(src)
            result = {
                "source": str(archive_path.relative_to(root)),
                **info,
                "execute": execute,
                "publish_requested": publish,
                "coverage": "retained GEBCO subset only; not global bathymetry",
            }
            if not execute:
                return result

            import xarray as xr
            output = root / "raw" / "bathymetry" / "prepared"
            output.mkdir(parents=True, exist_ok=True)
            # Stable per-source checksum and stride for idempotent output.
            name = f"gebco_bounded_{digest(archive_path)[:16]}_s{info['sample_stride']}.nc"
            destination = output / name
            if destination.exists():
                # No destructive overwrite of a previously prepared file.
                geometry(destination)
            else:
                temporary = output / (name + ".tmp")
                try:
                    with xr.open_dataset(src) as grid:
                        stride = info["sample_stride"]
                        chosen = grid.isel(lat=slice(None, None, stride),
                                           lon=slice(None, None, stride))
                        chosen = chosen.copy()
                        chosen.attrs["title"] = (
                            f"GEBCO original-grid subset sampled at every {stride}th "
                            "cell; NOT navigation chart datum"
                        )
                        chosen.attrs["source_grid_cells"] = str(info["source_cells"])
                        chosen.attrs["sampling_stride"] = str(stride)
                        chosen.to_netcdf(temporary)
                    temporary.replace(destination)
                finally:
                    temporary.unlink(missing_ok=True)

            result["prepared_path"] = str(destination.relative_to(root))
            if publish:
                report = run(
                    "bathymetry", destination, root=root, source_url=SOURCE_URL,
                    coverage=(
                        f"GEBCO retained regional subset; original grid every "
                        f"{info['sample_stride']} cells, {info['selected_cells']} sampled; "
                        "source elevation positive upward, not chart datum, not global"
                    ),
                )
                result["publication"] = {
                    "status": report["status"],
                    "accepted": report["accepted"],
                    "rejected": report["rejected"],
                    "gold_counts": report["gold_counts"],
                }
            return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    root = resolve_data_root(args.data_root)
    if args.archive is not None:
        source = args.archive
    else:
        candidates = sorted((root / "raw" / "geospatial" / "gebco").glob("*.zip"))
        if len(candidates) != 1:
            print("Expected exactly one retained GEBCO ZIP; specify --archive",
                  file=sys.stderr)
            return 1
        source = candidates[0]
    try:
        outcome = prepare(source, root, execute=args.execute, publish=args.publish)
        print(json.dumps(outcome, indent=2))
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"GEBCO preparation failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
