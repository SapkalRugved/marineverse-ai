"""Read-only verification of the current three Gold marts and source receipts.

Checks hashes against immutable published receipts without printing hashes,
account identifiers or individual source record contents.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from backend.marine_data.platform.pipeline import digest, MARTS
from backend.marine_data.storage import resolve_data_root


def verify(root: Path, dataset: str) -> dict:
    root = Path(root).resolve()
    pointer = root / "catalog" / dataset / "current.json"
    result = {"dataset": dataset, "verified": False, "checks": {}}
    if not pointer.is_file():
        result["reason"] = "no_published_receipt"
        return result
    try:
        receipt = json.loads(pointer.read_text(encoding="utf-8"))
        if receipt["dataset"] != dataset or receipt["status"] != "success":
            raise ValueError("Receipt dataset or status invalid")
        release = receipt["release"]
        silver = (root / "silver" / dataset / release / "records.jsonl").resolve()
        if not silver.is_relative_to((root / "silver").resolve()):
            raise ValueError("Silver path escapes storage root")
        result["checks"]["silver"] = (
            silver.is_file() and digest(silver) == receipt["silver_sha256"]
        )
        for mart in MARTS:
            product = receipt["products"][mart]
            path = (root / product["path"]).resolve()
            if not path.is_relative_to((root / "gold").resolve()):
                raise ValueError("Gold product path escapes storage root")
            if not path.is_relative_to((root / "gold" / dataset / release).resolve()):
                raise ValueError("Gold product does not belong to current release")
            result["checks"][mart] = (
                path.is_file() and digest(path) == product["sha256"]
            )
        bronze_root = root / "bronze" / dataset / receipt["bronze_sha256"]
        bronze_ok = bronze_root.is_dir()
        for file_info in receipt["bronze_files"]:
            name = file_info["name"]
            if Path(name).name != name:
                raise ValueError("Invalid Bronze filename")
            path = bronze_root / name
            bronze_ok = (
                bronze_ok and path.is_file()
                and path.stat().st_size == file_info["bytes"]
                and digest(path) == file_info["sha256"]
            )
        result["checks"]["bronze"] = bronze_ok
        result["checks"]["record_counts"] = (
            receipt["accepted"] > 0
            and all(receipt["products"][m]["records"] == receipt["gold_counts"][m] for m in MARTS)
        )
        result["verified"] = all(result["checks"].values())
        result["accepted"] = receipt["accepted"]
        result["rejected"] = receipt["rejected"]
    except (OSError, KeyError, ValueError, TypeError):
        result["reason"] = "invalid_or_unreadable_receipt"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset")
    parser.add_argument("--data-root", type=Path)
    args = parser.parse_args()
    output = verify(resolve_data_root(args.data_root), args.dataset)
    print(json.dumps(output, indent=2))
    return int(not output["verified"])


if __name__ == "__main__":
    sys.exit(main())
