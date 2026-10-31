"""Fetch real public sources then publish the three consumer marts."""

import argparse
import json
from pathlib import Path
from dotenv import load_dotenv

from backend.marine_data.platform.pipeline import run
from backend.marine_data.platform.sources import (
    download_ibtracs,
    retrieve_ports,
    NOAA_BASE,
)
from backend.marine_data.storage import resolve_data_root, PROJECT_ROOT


def _refresh(dataset, root=None):
    root = resolve_data_root(root)
    if dataset == "ibtracs":
        path = download_ibtracs(root)
        return run(
            dataset,
            path,
            source_url=NOAA_BASE + "ibtracs.ALL.list.v04r01.csv",
            coverage="Global NOAA tropical cyclone archive, historical and provisional; not live alerts",
            root=root,
        )
    if dataset == "ports":
        path = retrieve_ports(root)
        return run(
            dataset,
            path,
            source_url="https://overpass-api.de/api/interpreter",
            coverage="Worldwide OSM harbour/port tile queries; incomplete volunteered source coverage",
            root=root,
        )
    if dataset == "weather":
        from backend.marine_data.weather.retrieve_open_meteo_weather import (
            retrieve_weather,
            retain_raw_response,
        )

        report_path = root / "catalog" / "ports" / "current.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        records_path = root / "silver" / "ports" / report["release"] / "records.jsonl"
        locations = []
        seen = set()
        with records_path.open(encoding="utf-8") as records:
            for line in records:
                record = json.loads(line)
                coordinates = (record["latitude"], record["longitude"])
                if record["port_type"] == "port" and coordinates not in seen:
                    seen.add(coordinates)
                    locations.append(
                        {
                            k: record[k]
                            for k in ("source_id", "name", "latitude", "longitude")
                        }
                    )
        if not locations:
            raise ValueError("No normalized worldwide port locations available")
        raw = retrieve_weather(locations)
        path = retain_raw_response(
            locations, raw, output_directory=root / "raw" / "weather"
        )
        # Record exact upstream port release in the raw envelope for lineage.
        envelope = json.loads(path.read_text(encoding="utf-8"))
        envelope["ports_release"] = report["release"]
        from backend.marine_data.platform.pipeline import atomic_json

        atomic_json(path, envelope)
        return run(
            dataset,
            path,
            source_url="https://api.open-meteo.com/v1/forecast",
            coverage=f"Open-Meteo current model weather at {len(locations)} available OSM port coordinates; ports release {report['release']}",
            root=root,
        )
    raise ValueError("Unsupported automatic refresh source")


def refresh(dataset, root=None):
    from backend.marine_data.platform.pipeline import dataset_lock

    if dataset not in {"ibtracs", "ports", "weather"}:
        raise ValueError("Unsupported automatic refresh source")
    root = resolve_data_root(root)
    with dataset_lock(root, "refresh-" + dataset):
        return _refresh(dataset, root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", choices=("ibtracs", "ports", "weather"))
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    if not args.execute:
        print(
            json.dumps(
                {
                    "dataset": args.dataset,
                    "execute": False,
                    "requires_network": True,
                    "note": "Review provider quotas and coverage before scheduling worldwide refresh",
                }
            )
        )
        return 0
    print(json.dumps(refresh(args.dataset, args.data_root)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
