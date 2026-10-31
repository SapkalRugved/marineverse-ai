"""Source adapters. Existing validated transformers remain authoritative."""

from __future__ import annotations

import csv
import json
import math
import re
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

IBTRACS_REQUIRED = {
    "SID",
    "SEASON",
    "BASIN",
    "ISO_TIME",
    "LAT",
    "LON",
    "WMO_WIND",
    "WMO_PRES",
    "WMO_AGENCY",
}
DATASETS = (
    "ibtracs",
    "ports",
    "weather",
    "ocean",
    "ais",
    "coastline",
    "land",
    "protected_zones",
    "bathymetry",
)


def number(value, minimum, maximum, *, optional=False):
    text = str(value).strip() if value is not None else ""
    if optional and text in {"", "-9999", "-9999.0"}:
        return None
    value = float(text)
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError("numeric value out of range")
    return value


def ibtracs_rows(path: Path):
    """Read global or basin v04 CSV; preserve NA basin and WMO agency."""
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not IBTRACS_REQUIRED.issubset(reader.fieldnames or []):
            raise ValueError("Missing required IBTrACS v04 columns")
        units = next(reader, None)
        if units is None or any(
            units.get(k, "").strip() != v
            for k, v in {
                "LAT": "degrees_north",
                "LON": "degrees_east",
                "WMO_WIND": "kts",
                "WMO_PRES": "mb",
            }.items()
        ):
            raise ValueError("IBTrACS units row absent or incompatible")
        for line, raw in enumerate(reader, 3):
            try:
                row = {k: (v or "").strip() for k, v in raw.items() if k is not None}
                if not re.fullmatch(r"\d{7}[NS]\d{5}", row["SID"]):
                    raise ValueError("invalid storm SID")
                if row["BASIN"] not in {"NA", "EP", "WP", "NI", "SI", "SP", "SA"}:
                    raise ValueError("invalid basin")
                stamp = datetime.strptime(row["ISO_TIME"], "%Y-%m-%d %H:%M:%S").replace(
                    tzinfo=timezone.utc
                )
                wind = number(row["WMO_WIND"], 0, 250, optional=True)
                pressure = number(row["WMO_PRES"], 800, 1100, optional=True)
                record = {
                    "storm_id": row["SID"],
                    "season": int(number(row["SEASON"], 1800, 2200)),
                    "basin": row["BASIN"],
                    "name": row.get("NAME") or None,
                    "valid_time": stamp.isoformat(),
                    "latitude": number(row["LAT"], -90, 90),
                    "longitude": (number(row["LON"], -360, 360) + 180) % 360 - 180,
                    "source_longitude": number(row["LON"], -360, 360),
                    "interpolation_flag": row.get("IFLAG") or None,
                    "wind_speed_mps": wind * 1852 / 3600 if wind is not None else None,
                    "pressure_hpa": pressure,
                    "wmo_agency": row["WMO_AGENCY"] or None,
                    # Wind averaging periods differ by agency; do not homogenize.
                    "wind_averaging_period": "agency_native",
                    "track_type": row.get("TRACK_TYPE") or None,
                    "nature": row.get("NATURE") or None,
                    "source": "noaa-ibtracs",
                    "source_dataset": "IBTrACS-v04r01",
                    "is_forecast": False,
                }
                yield line, record, None
            except (ValueError, KeyError, TypeError) as exc:
                yield line, None, str(exc)


def transform(path: Path, dataset: str, stamp: datetime):
    """Yield row number, normalized record, error; no synthetic fallback."""
    if dataset in {"coastline", "land", "protected_zones"}:
        from backend.marine_data.platform.geospatial import vector_rows

        yield from vector_rows(path, dataset)
        return
    if dataset == "bathymetry":
        from backend.marine_data.platform.geospatial import bathymetry_rows

        yield from bathymetry_rows(path)
        return
    if dataset == "ibtracs":
        yield from ibtracs_rows(path)
        return
    if dataset == "ports":
        from backend.marine_data.ports.transformer import (
            map_element_to_port,
            TransformationError,
        )

        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("remark"):
            raise ValueError("Overpass reported incomplete/error response")
        elements = payload.get("elements")
        if not isinstance(elements, list):
            raise ValueError("Missing OSM elements")
        for index, element in enumerate(elements, 1):
            try:
                record = map_element_to_port(element, stamp)
                # Existing transformer is regional. Unknown country stays NULL globally.
                country = element["tags"].get("addr:country", "").strip() or None
                record = replace(record, country=country)
                yield index, asdict(record), None
            except (TransformationError, TypeError, AttributeError, KeyError) as exc:
                yield index, None, str(exc)
        return
    if dataset == "weather":
        from backend.marine_data.weather.transformer import transform_raw_file

        result = transform_raw_file(path, ingested_at=stamp)
        records, rejected, duplicates = (
            result.records,
            result.rejected_records,
            result.duplicates_removed,
        )
    elif dataset == "ocean":
        from backend.marine_data.ocean.transformer import transform_raw_manifest

        result = transform_raw_manifest(path, ingested_at=stamp)
        records, rejected, duplicates = result.records, result.rejected_records, 0
    elif dataset == "ais":
        from backend.marine_data.ais.transformer import transform_capture

        result = transform_capture(json.loads(path.read_text()), ingested_at=stamp)
        records = (*result.vessel_records, *result.position_records)
        rejected, duplicates = result.rejected_events, result.duplicates_removed
    else:
        raise ValueError("Unknown dataset")
    source_read = getattr(
        result,
        "source_records_read",
        getattr(result, "source_grid_cells", getattr(result, "source_events_read", 0)),
    )
    yield (
        None,
        {
            "_adapter_quality": {
                "records_read": source_read,
                "rejected": rejected,
                "duplicates": duplicates,
                "ignored": getattr(result, "ignored_events", 0),
            }
        },
        None,
    )
    for record in records:
        # Legacy transformers return normalized records, not original row indices.
        yield None, asdict(record), None
    # Existing transformers expose aggregate rejections, not rejected row identities.
    for _ in range(rejected):
        yield None, None, "existing transformer rejected record (aggregate only)"
    for _ in range(duplicates):
        yield None, None, "duplicate removed by existing transformer"


def logical_key(dataset: str, record: dict):
    if dataset == "ibtracs":
        return [record["storm_id"], record["valid_time"], record["track_type"]]
    if dataset in {"ports", "coastline", "land", "protected_zones"}:
        return [record["source"], record["source_id"]]
    if dataset == "ais" and "observed_at" not in record:
        return ["vessel", record["mmsi"]]
    return [
        record.get(k)
        for k in (
            "source",
            "source_dataset",
            "mmsi",
            "observed_at",
            "valid_time",
            "latitude",
            "longitude",
            "depth_m",
            "is_forecast",
        )
    ]
