"""Immutable Bronze, replayable Silver and three independent Gold marts.

Only a final atomic current.json replacement publishes a complete release.
No AWS calls, database migrations or fabricated records occur here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from backend.marine_data.platform.adapters import DATASETS, logical_key, transform
from backend.marine_data.storage import resolve_data_root

MARTS = ("objective1", "objective3", "objective4")
VERSION = "1"


def dumps(value):
    return json.dumps(
        value,
        default=lambda v: v.isoformat(),
        ensure_ascii=False,
        sort_keys=True,
        allow_nan=False,
        separators=(",", ":"),
    )


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    try:
        temporary.write_text(dumps(value) + "\n", encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def dataset_lock(root, dataset):
    """OS releases the lock after crashes; no stale-lock timeout guesses."""
    path = root / "locks" / (dataset + ".lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as lock:
        lock.seek(0)
        if sys.platform == "win32":
            import msvcrt

            if path.stat().st_size == 0:
                lock.write(b"0")
                lock.flush()
                lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            lock.seek(0)
            if sys.platform == "win32":
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock, fcntl.LOCK_UN)


def retain_bronze(root, dataset, source):
    """Content-addressed raw bundle; copy NetCDF dependencies beside manifest."""
    sources = [source]
    if dataset == "ocean":
        manifest = json.loads(source.read_text())
        for section in ("physics", "waves"):
            name = manifest[section]["file"]
            if Path(name).name != name:
                raise ValueError("Ocean dependency must be a sibling filename")
            sources.append(source.parent / name)
    files = [
        {"name": p.name, "sha256": digest(p), "bytes": p.stat().st_size}
        for p in sources
    ]
    if len({p.name for p in sources}) != len(sources):
        raise ValueError("Bronze bundle filenames collide")
    bundle_hash = hashlib.sha256(dumps(files).encode()).hexdigest()
    directory = root / "bronze" / dataset / bundle_hash
    directory.mkdir(parents=True, exist_ok=True)
    for path, metadata in zip(sources, files, strict=True):
        target = directory / path.name
        if target.exists() and digest(target) == metadata["sha256"]:
            continue
        if target.exists():
            raise ValueError("Existing Bronze content failed checksum")
        temporary = target.with_suffix(target.suffix + ".tmp")
        shutil.copyfile(path, temporary)
        if digest(temporary) != metadata["sha256"]:
            temporary.unlink()
            raise ValueError("Source changed during Bronze copy")
        temporary.replace(target)
    return directory / source.name, bundle_hash, files


def build_gold(silver, directory, provenance):
    """Build isolated consumer products; never infer navigational safety."""
    counts = {mart: 0 for mart in MARTS}
    database = sqlite3.connect(directory / "aggregates.sqlite")
    database.execute(
        "CREATE TABLE cells (day TEXT, lat INTEGER, lon INTEGER, source TEXT, agency TEXT, n INTEGER, wind REAL, wave REAL, pressure REAL, depth REAL, PRIMARY KEY(day,lat,lon,source,agency))"
    )
    try:
        with (
            (directory / "objective1.jsonl").open("w", encoding="utf-8") as twin,
            (directory / "objective3.jsonl").open("w", encoding="utf-8") as assistant,
            silver.open(encoding="utf-8") as records,
        ):
            for line in records:
                record = json.loads(line)
                lat, lon = record.get("latitude"), record.get("longitude")
                geometry = record.get("geometry") or (
                    {"type": "Point", "coordinates": [lon, lat]}
                    if lat is not None and lon is not None
                    else None
                )
                twin.write(
                    dumps(
                        {
                            "type": "Feature",
                            "geometry": geometry,
                            "properties": record,
                            "provenance": provenance,
                        }
                    )
                    + "\n"
                )
                # Typed facts for retrieval; source bytes and row ID remain traceable.
                assistant.write(
                    dumps(
                        {
                            "evidence_id": record["_record_id"],
                            "facts": record,
                            "provenance": provenance,
                        }
                    )
                    + "\n"
                )
                counts["objective1"] += 1
                counts["objective3"] += 1
                if lat is not None and lon is not None:
                    time = (
                        record.get("valid_time")
                        or record.get("observed_at")
                        or record.get("updated_at")
                    )
                    day = time[:10] if time else "unknown"
                    # Clamp exact north/east endpoints to final world grid cell.
                    cell = (
                        day,
                        min(89, math.floor(lat)),
                        min(179, math.floor(lon)),
                        record["source"],
                        record.get("wmo_agency") or "",
                    )
                    wind, wave, pressure = (
                        record.get(k)
                        for k in ("wind_speed_mps", "wave_height_m", "pressure_hpa")
                    )
                    database.execute(
                        """INSERT INTO cells VALUES (?,?,?,?,?,1,?,?,?,?)
                        ON CONFLICT(day,lat,lon,source,agency) DO UPDATE SET n=n+1,
                        wind=CASE WHEN excluded.wind IS NULL THEN wind WHEN wind IS NULL THEN excluded.wind ELSE max(wind,excluded.wind) END,
                        wave=CASE WHEN excluded.wave IS NULL THEN wave WHEN wave IS NULL THEN excluded.wave ELSE max(wave,excluded.wave) END,
                        pressure=CASE WHEN excluded.pressure IS NULL THEN pressure WHEN pressure IS NULL THEN excluded.pressure ELSE min(pressure,excluded.pressure) END,
                        depth=CASE WHEN excluded.depth IS NULL THEN depth WHEN depth IS NULL THEN excluded.depth ELSE min(depth,excluded.depth) END""",
                        (*cell, wind, wave, pressure, record.get("water_depth_m")),
                    )
        with (directory / "objective4.jsonl").open("w", encoding="utf-8") as support:
            with silver.open(encoding="utf-8") as records:
                for line in records:
                    record = json.loads(line)
                    if record.get("geometry"):
                        support.write(
                            dumps(
                                {
                                    "source_id": record["source_id"],
                                    "geometry": record["geometry"],
                                    "attributes": record["attributes"],
                                    "provenance": provenance,
                                    "interpretation": record["authority"],
                                }
                            )
                            + "\n"
                        )
                        counts["objective4"] += 1
            for row in database.execute(
                "SELECT * FROM cells ORDER BY day,lat,lon,source,agency"
            ):
                keys = (
                    "day_utc",
                    "cell_south",
                    "cell_west",
                    "source",
                    "wmo_agency",
                    "record_count",
                    "max_wind_speed_mps",
                    "max_wave_height_m",
                    "min_pressure_hpa",
                    "min_water_depth_m",
                )
                support.write(
                    dumps(
                        {
                            **dict(zip(keys, row)),
                            "provenance": provenance,
                            "cell_size_degrees": 1,
                            "coverage": "available_records_only",
                            "interpretation": "descriptive aggregates; no risk or safety classification",
                        }
                    )
                    + "\n"
                )
                counts["objective4"] += 1
    finally:
        database.close()
        (directory / "aggregates.sqlite").unlink(missing_ok=True)
    return counts


def run(
    dataset, source, *, source_url, coverage, root=None, max_rejection_fraction=0.05
):
    """Publish one dataset release only after every stage and gate succeeds."""
    if dataset not in DATASETS:
        raise ValueError("Unsupported dataset")
    if not 0 <= max_rejection_fraction <= 1:
        raise ValueError("Rejection fraction must be between zero and one")
    if not source_url.startswith("https://") or not coverage.strip():
        raise ValueError("HTTPS provenance URL and explicit coverage are required")
    root = resolve_data_root(root)
    with dataset_lock(root, dataset):
        stamp = datetime.now(timezone.utc)
        release = stamp.strftime("%Y%m%dT%H%M%S") + "-" + uuid4().hex[:12]
        directory = root / "silver" / dataset / release
        directory.mkdir(parents=True)
        report = {
            "release": release,
            "dataset": dataset,
            "contract_version": VERSION,
            "started_at": stamp.isoformat(),
            "status": "running",
            "source_url": source_url,
            "coverage": coverage,
            "worldwide_live_coverage": False,
            "read": 0,
            "accepted": 0,
            "rejected": 0,
            "duplicates": 0,
            "bounds": None,
            "minimum_time": None,
            "maximum_time": None,
            "missing_values": {},
            "max_rejection_fraction": max_rejection_fraction,
        }
        seen = sqlite3.connect(directory / "dedup.sqlite")
        seen.execute("CREATE TABLE identities (key TEXT PRIMARY KEY)")
        try:
            bronze, bundle_hash, files = retain_bronze(
                root, dataset, Path(source).resolve()
            )
            provenance = {
                "dataset": dataset,
                "source_url": source_url,
                "bronze_sha256": bundle_hash,
                "release": release,
                "contract_version": VERSION,
                "coverage": coverage,
            }
            report.update(bronze_sha256=bundle_hash, bronze_files=files)
            silver = directory / "records.jsonl"
            with (
                silver.open("w", encoding="utf-8") as output,
                (directory / "rejections.jsonl").open(
                    "w", encoding="utf-8"
                ) as quarantine,
            ):
                for row, record, error in transform(bronze, dataset, stamp):
                    report["read"] += 1
                    if error:
                        key = (
                            "duplicates"
                            if error == "duplicate removed by existing transformer"
                            else "rejected"
                        )
                        report[key] += 1
                        quarantine.write(dumps({"row": row, "reason": error}) + "\n")
                        continue
                    record = json.loads(dumps(record))
                    identity = dumps(logical_key(dataset, record))
                    if (
                        seen.execute(
                            "INSERT OR IGNORE INTO identities VALUES (?)", (identity,)
                        ).rowcount
                        == 0
                    ):
                        report["duplicates"] += 1
                        continue
                    record["_record_id"] = hashlib.sha256(
                        (dataset + identity).encode()
                    ).hexdigest()
                    record["_source_row"] = row
                    output.write(dumps(record) + "\n")
                    report["accepted"] += 1
                    for key, value in record.items():
                        if value is None:
                            report["missing_values"][key] = (
                                report["missing_values"].get(key, 0) + 1
                            )
                    lat, lon = record.get("latitude"), record.get("longitude")
                    if lat is not None and lon is not None:
                        bounds = report["bounds"] or [lon, lat, lon, lat]
                        report["bounds"] = [
                            min(bounds[0], lon),
                            min(bounds[1], lat),
                            max(bounds[2], lon),
                            max(bounds[3], lat),
                        ]
                    if record.get("geometry_bounds"):
                        west, south, east, north = record["geometry_bounds"]
                        bounds = report["bounds"] or [west, south, east, north]
                        report["bounds"] = [
                            min(bounds[0], west),
                            min(bounds[1], south),
                            max(bounds[2], east),
                            max(bounds[3], north),
                        ]
                    time = (
                        record.get("valid_time")
                        or record.get("observed_at")
                        or record.get("updated_at")
                    )
                    if time:
                        report["minimum_time"] = min(
                            report["minimum_time"] or time, time
                        )
                        report["maximum_time"] = max(
                            report["maximum_time"] or time, time
                        )
            report["rejection_fraction"] = report["rejected"] / max(1, report["read"])
            if (
                not report["accepted"]
                or report["rejection_fraction"] > max_rejection_fraction
            ):
                raise ValueError(
                    "Data quality gate failed; prior release remains current"
                )
            gold = root / "gold" / dataset / release
            gold.mkdir(parents=True)
            report["gold_counts"] = build_gold(silver, gold, provenance)
            report["products"] = {
                mart: {
                    "path": str((gold / (mart + ".jsonl")).relative_to(root)),
                    "sha256": digest(gold / (mart + ".jsonl")),
                    "records": report["gold_counts"][mart],
                }
                for mart in MARTS
            }
            report["silver_sha256"] = digest(silver)
            report["status"] = "success"
            report["completed_at"] = datetime.now(timezone.utc).isoformat()
            atomic_json(directory / "report.json", report)
            atomic_json(root / "catalog" / dataset / "current.json", report)
            return report
        except Exception as exc:
            report["status"] = "failed"
            report["error_type"] = type(exc).__name__
            report["completed_at"] = datetime.now(timezone.utc).isoformat()
            atomic_json(directory / "report.json", report)
            raise
        finally:
            seen.close()
            (directory / "dedup.sqlite").unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", choices=DATASETS)
    parser.add_argument("source", type=Path)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--coverage", required=True)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--max-rejection-fraction", type=float, default=0.05)
    args = parser.parse_args()
    from dotenv import load_dotenv
    from backend.marine_data.storage import PROJECT_ROOT

    load_dotenv(PROJECT_ROOT / ".env", override=False)
    try:
        report = run(
            args.dataset,
            args.source,
            source_url=args.source_url,
            coverage=args.coverage,
            root=args.data_root,
            max_rejection_fraction=args.max_rejection_fraction,
        )
        print(dumps(report))
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Pipeline failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
