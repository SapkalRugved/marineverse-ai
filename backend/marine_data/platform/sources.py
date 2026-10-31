"""Explicit real-data downloads and worldwide acquisition plans.

Downloads never publish coverage claims. Plans are cheap; execution is explicit.
"""

from __future__ import annotations
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from backend.marine_data.platform.pipeline import atomic_json, digest
from backend.marine_data.storage import resolve_data_root

NOAA_BASE = "https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs/v04r01/access/csv/"


def download_ibtracs(root, period="ALL"):
    """Retain a new download; never overwrite the user's validated raw file."""
    from backend.marine_data.weather.retrieve_open_meteo_weather import (
        create_http_session,
    )

    if period not in {"ALL", "since1980", "last3years"}:
        raise ValueError("Unsupported NOAA period")
    name = f"ibtracs.{period}.list.v04r01.csv"
    directory = (
        resolve_data_root(root)
        / "raw"
        / "ibtracs"
        / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    )
    directory.mkdir(parents=True)
    path = directory / name
    temporary = path.with_suffix(".csv.tmp")
    try:
        with (
            create_http_session() as session,
            session.get(NOAA_BASE + name, stream=True, timeout=(15, 120)) as response,
        ):
            response.raise_for_status()
            with temporary.open("wb") as out:
                for chunk in response.iter_content(1024 * 1024):
                    out.write(chunk)
        from backend.marine_data.platform.adapters import ibtracs_rows

        # Validate header/units and require at least one normalized observation.
        if not any(record for _, record, _ in ibtracs_rows(temporary)):
            raise ValueError("NOAA download contained no valid observations")
        temporary.replace(path)
        atomic_json(
            directory / "acquisition.json",
            {
                "source_url": NOAA_BASE + name,
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "sha256": digest(path),
                "bytes": path.stat().st_size,
                "scope": f"global tropical cyclone best tracks; period={period}; not live alerts",
            },
        )
        return path
    finally:
        temporary.unlink(missing_ok=True)


def tiles(size=30):
    """Non-overlapping world bounds; antimeridian split at -180/180."""
    if size not in {5, 10, 15, 30}:
        raise ValueError("Tile size must divide the world into bounded jobs")
    return [
        {
            "id": f"{south:+03d}_{west:+04d}",
            "south": south,
            "north": south + size,
            "west": west,
            "east": west + size,
        }
        for south in range(-90, 90, size)
        for west in range(-180, 180, size)
    ]


def osm_query(tile):
    bounds = ",".join(str(tile[k]) for k in ("south", "west", "north", "east"))
    return f"""[out:json][timeout:180];(
      nwr["industrial"="port"]({bounds});
      nwr["seamark:harbour:category"="port"]({bounds});
      nwr["harbour"="yes"]({bounds});
      nwr["seamark:type"="harbour"]({bounds});
    );out center tags;"""


def _retrieve_ports(root, size=30):
    """Checkpoint tiles; fail closed on any HTTP or Overpass error.

    A complete combined snapshot feeds the normal ports adapter. Empty tiles
    are successful only when Overpass returns a valid, error-free response.
    """
    from backend.marine_data.ports.retrieve_osm_ports import OVERPASS_URL, USER_AGENT
    from backend.marine_data.weather.retrieve_open_meteo_weather import (
        create_http_session,
    )

    directory = resolve_data_root(root) / "raw" / "ports-worldwide" / f"pending-{size}"
    directory.mkdir(parents=True, exist_ok=True)
    elements, receipts = [], []
    with create_http_session() as session:
        for tile in tiles(size):
            path = directory / f"tile-{size}-{tile['id']}.json"
            if not path.exists():
                response = session.post(
                    OVERPASS_URL,
                    data={"data": osm_query(tile)},
                    headers={"User-Agent": USER_AGENT},
                    timeout=(15, 240),
                )
                response.raise_for_status()
                payload = response.json()
                if (
                    not isinstance(payload, dict)
                    or payload.get("remark")
                    or not isinstance(payload.get("elements"), list)
                ):
                    raise ValueError(f"Incomplete Overpass response for {tile['id']}")
                atomic_json(
                    path,
                    {
                        "tile": tile,
                        "retrieved_at": datetime.now(timezone.utc).isoformat(),
                        "response": payload,
                    },
                )
            receipt = json.loads(path.read_text())
            if receipt["tile"] != tile or receipt["response"].get("remark"):
                raise ValueError("Invalid cached tile; inspect/remove it before retry")
            elements.extend(receipt["response"]["elements"])
            receipts.append(
                {
                    "tile": tile,
                    "sha256": digest(path),
                    "retrieved_at": receipt["retrieved_at"],
                }
            )
    output = directory / (
        "snapshot-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json"
    )
    atomic_json(
        output,
        {
            "elements": elements,
            "source_url": OVERPASS_URL,
            "tiles": receipts,
            "coverage": "worldwide query completed; OSM features are incomplete and not authoritative",
        },
    )
    completed = directory.with_name(
        "complete-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    )
    directory.rename(completed)
    return completed / output.name


def retrieve_ports(root, size=30):
    from backend.marine_data.platform.pipeline import dataset_lock

    resolved = resolve_data_root(root)
    with dataset_lock(resolved, "ports-download"):
        return _retrieve_ports(resolved, size)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", choices=("ibtracs", "ports", "ports-wpi"))
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--data-root", type=Path)
    parser.add_argument(
        "--period", choices=("ALL", "since1980", "last3years"), default="ALL"
    )
    parser.add_argument("--tile-size", type=int, default=30)
    args = parser.parse_args()
    if not args.execute:
        print(
            json.dumps(
                {
                    "source": args.source,
                    "execute": False,
                    "url": NOAA_BASE + f"ibtracs.{args.period}.list.v04r01.csv"
                    if args.source == "ibtracs"
                    else None,
                    "tiles": tiles(args.tile_size) if args.source == "ports" else [],
                    "maximum_download_bytes": 20 * 1024 ** 2 if args.source == "ports-wpi" else None,
                }
            )
        )
        return 0
    if args.source == "ports-wpi":
        from backend.marine_data.platform.wpi import download
        path = download(resolve_data_root(args.data_root))
    elif args.source == "ibtracs":
        path = download_ibtracs(args.data_root, args.period)
    else:
        path = retrieve_ports(args.data_root, args.tile_size)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
