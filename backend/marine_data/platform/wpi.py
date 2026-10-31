"""Bounded acquisition and validation of NGA's public World Port Index CSV."""
from __future__ import annotations

import csv
import math
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from backend.marine_data.platform.pipeline import atomic_json, digest

URL = "https://msi.nga.mil/api/publications/download?key=16920959/SFH00000/UpdatedPub150.csv&type=view"
SOURCE = "nga-world-port-index"
MAX_BYTES = 20 * 1024 ** 2
REQUIRED = {"World Port Index Number", "Main Port Name", "Country Code", "Latitude", "Longitude"}


def rows(path: Path, stamp: datetime):
    """Keep WPI identity and supplied country label; never impersonate OSM."""
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not REQUIRED.issubset(reader.fieldnames or []):
            raise ValueError("Missing World Port Index columns")
        for index, row in enumerate(reader, 2):
            try:
                identity = Decimal(row["World Port Index Number"].strip())
                if not identity.is_finite() or identity <= 0 or identity != identity.to_integral_value():
                    raise ValueError("Invalid WPI identifier")
                name = row["Main Port Name"].strip()
                country = row["Country Code"].strip() or None
                if not name or len(name) > 200 or (country and len(country) > 100):
                    raise ValueError("Invalid WPI name or country label")
                lat, lon = float(row["Latitude"]), float(row["Longitude"])
                if not (math.isfinite(lat) and math.isfinite(lon)
                        and -90 <= lat <= 90 and -180 <= lon <= 180):
                    raise ValueError("Invalid WPI coordinates")
                yield index, {
                    "source_id": str(int(identity)), "name": name, "country": country,
                    "port_type": "port", "latitude": lat, "longitude": lon,
                    "source": SOURCE, "updated_at": stamp.isoformat(),
                    "timestamp_basis": "snapshot_ingestion; upstream per-port update time unavailable",
                    "country_basis": "NGA supplied Country Code label; not normalized ISO",
                    "directory_scope": "WPI ports, terminals and shipping facilities; not exhaustive",
                }, None
            except (ValueError, TypeError, AttributeError, InvalidOperation):
                yield index, None, "invalid WPI source row"


def download(root: Path):
    """One provider request, at most 20 MiB; retain each snapshot separately."""
    import requests
    directory = Path(root) / "raw" / "ports-wpi" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    directory.mkdir(parents=True)
    path = directory / "UpdatedPub150.csv"
    partial = path.with_suffix(".csv.tmp")
    try:
        with requests.get(URL, stream=True, timeout=(10, 60)) as response:
            response.raise_for_status()
            received = 0
            with partial.open("wb") as output:
                for chunk in response.iter_content(1024 * 1024):
                    received += len(chunk)
                    if received > MAX_BYTES:
                        raise ValueError("WPI download exceeds 20 MiB limit")
                    output.write(chunk)
        if not any(row for _, row, _ in rows(partial, datetime.now(timezone.utc))):
            raise ValueError("WPI response has no valid records")
        partial.replace(path)
        atomic_json(directory / "acquisition.json", {
            "source_url": URL, "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "bytes": path.stat().st_size, "sha256": digest(path),
            "coverage": "NGA worldwide directory; selected ports and facilities, not exhaustive or live",
        })
        return path
    finally:
        partial.unlink(missing_ok=True)
