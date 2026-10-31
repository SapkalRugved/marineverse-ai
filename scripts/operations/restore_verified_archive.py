"""Restore only authenticated-by-receipt published files from a data ZIP.

Never unpacks arbitrary members, overwrites a data root or enables jobs.
Archive receipts and Bronze/Silver/Gold are audited before atomic promotion.
No AWS or network access is required.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
from zipfile import ZipFile

from backend.marine_data.platform.adapters import DATASETS
from backend.marine_data.platform.pipeline import MARTS
from backend.marine_data.platform.verify import audit_release

MAX_BYTES = 8 * 1024**3
MAX_FILES = 200


def canonical_members(archive: ZipFile) -> tuple[dict, list[str]]:
    names = archive.namelist()
    if len(names) > MAX_FILES or len(names) != len(set(names)):
        raise ValueError("Unsafe archive member count or duplicate names")
    if sum(item.file_size for item in archive.infolist()) > MAX_BYTES:
        raise ValueError("Archive exceeds bounded extraction limit")
    # Load only explicitly expected catalog metadata; ignore transient files.
    catalog_names = sorted(name for name in names
                           if name.startswith("catalog/") and name.endswith("/current.json"))
    if not catalog_names:
        raise ValueError("No published dataset catalog")
    receipts = {}
    approved = []
    for pointer in catalog_names:
        parts = pointer.split("/")
        if len(parts) != 3 or parts[1] not in DATASETS:
            raise ValueError("Unexpected dataset catalog")
        dataset = parts[1]
        receipt = json.loads(archive.read(pointer))
        if receipt.get("dataset") != dataset or receipt.get("status") != "success":
            raise ValueError("Invalid dataset receipt")
        release = receipt["release"]
        if (not isinstance(release, str) or not release
                or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in release)):
            raise ValueError("Invalid release identifier")
        bundle = receipt["bronze_sha256"]
        if not isinstance(bundle, str) or len(bundle) != 64 or any(c not in "0123456789abcdef" for c in bundle):
            raise ValueError("Invalid Bronze identifier")
        expected = [pointer]
        expected.extend(f"bronze/{dataset}/{bundle}/{entry['name']}" for entry in receipt["bronze_files"])
        expected.extend(f"silver/{dataset}/{release}/{name}" for name in
                        ("records.jsonl", "rejections.jsonl", "report.json"))
        expected.extend(f"gold/{dataset}/{release}/{mart}.jsonl" for mart in MARTS)
        for item in expected:
            normalized = Path(item)
            if (normalized.as_posix() != item or normalized.is_absolute()
                    or ".." in normalized.parts or "\\" in item
                    or item not in names or archive.getinfo(item).is_dir()):
                raise ValueError("Missing or unsafe canonical release file")
        receipts[dataset] = receipt
        approved.extend(expected)
    if len(approved) != len(set(approved)):
        raise ValueError("Duplicate canonical publication paths")
    return receipts, approved


def restore(archive_path: Path, destination: Path) -> dict:
    archive_path = Path(archive_path).resolve()
    destination = Path(destination).resolve()
    if destination.exists():
        raise FileExistsError("Destination already exists; refusing overwrite")
    if not destination.parent.is_dir():
        raise ValueError("Destination parent must exist")
    with ZipFile(archive_path) as archive:
        receipts, members = canonical_members(archive)
        with tempfile.TemporaryDirectory(prefix=".marineverse-restore-", dir=destination.parent) as tempdir:
            stage = Path(tempdir)
            for name in members:
                target = stage / name
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(name) as stream, target.open("wb") as output:
                    shutil.copyfileobj(stream, output, length=1024 * 1024)
            checks = {dataset: audit_release(stage, dataset) for dataset in receipts}
            if not all(check.get("verified") for check in checks.values()):
                raise ValueError("Published data integrity or lineage validation failed")
            # No shell commands, no symlinks, and no pre-existing destination.
            stage.rename(destination)
            # TemporaryDirectory cleanup handles the now-empty temporary path.
    return {"verified": True, "restored_datasets": sorted(receipts),
            "published_records": {name: checks[name]["accepted"] for name in checks},
            "excluded_nonpublication_entries": len(archive.namelist()) - len(members)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = restore(args.archive, args.destination)
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        print(f"Restore blocked: {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
