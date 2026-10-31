"""Non-destructive Objective 2 deployment readiness report.

Checks local data files and published Gold catalog, with optional read-only
AWS IAM identity verification. Never prints passwords, tokens, or full AWS ARNs.

Run from repository root:
    python -m scripts.operations.objective2_readiness
    python -m scripts.operations.objective2_readiness --check-aws
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

from backend.marine_data.storage import resolve_data_root

DATASETS = ("ibtracs", "ports", "weather", "ocean", "ais", "coastline",
            "land", "protected_zones", "bathymetry")
MARTS = ("objective1", "objective3", "objective4")


def inspect(root: Path) -> dict:
    root = Path(root)
    local_candidates = {
        "global_ibtracs": [
            root / "raw" / "cyclones" / "ibtracs" / "ibtracs.ALL.list.v04r01.csv",
            root / "raw" / "ibtracs" / "ibtracs.ALL.list.v04r01.csv",
        ],
        "regional_gebco": list((root / "raw" / "geospatial" / "gebco").glob("*.zip")),
        "natural_earth": list((root / "raw" / "geospatial" / "natural_earth").glob("*.zip")),
    }
    sources = {}
    for key, candidates in local_candidates.items():
        found = [p for p in candidates if p.is_file()]
        sources[key] = {
            "available": bool(found),
            "files": [str(p.relative_to(root)) for p in found],
            "bytes": sum(p.stat().st_size for p in found),
        }
    releases = {}
    for dataset in DATASETS:
        pointer = root / "catalog" / dataset / "current.json"
        result = {"published": False, "marts": {mart: False for mart in MARTS}}
        if pointer.is_file():
            try:
                receipt = json.loads(pointer.read_text(encoding="utf-8"))
                if receipt.get("dataset") != dataset:
                    raise ValueError("Unexpected dataset in receipt")
                for mart in MARTS:
                    product = receipt.get("products", {}).get(mart, {})
                    path = (root / product.get("path", "")).resolve()
                    result["marts"][mart] = (
                        path.is_relative_to((root / "gold").resolve()) and path.is_file()
                    )
                result["published"] = all(result["marts"].values())
                result["coverage"] = receipt.get("coverage")
                result["accepted"] = receipt.get("accepted")
            except (OSError, ValueError, TypeError, AttributeError) as exc:
                result["problem"] = type(exc).__name__
        releases[dataset] = result
    return {
        "data_root": str(root),
        "local_sources": sources,
        "published_marts": releases,
        "all_dataset_marts_published": all(r["published"] for r in releases.values()),
        "note": "A passing local receipt check is not proof of global live coverage.",
    }


def check_aws(profile: str, region: str) -> dict:
    """Read-only identity check; never output account ID or the full ARN."""
    try:
        proc = subprocess.run(
            ["aws", "sts", "get-caller-identity", "--profile", profile,
             "--region", region, "--output", "json"],
            capture_output=True, text=True, timeout=25, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"ready": False, "reason": "AWS CLI missing or timed out"}
    if proc.returncode:
        return {"ready": False, "reason": "AWS session missing, expired or denied"}
    try:
        arn = json.loads(proc.stdout)["Arn"]
    except (ValueError, KeyError, TypeError):
        return {"ready": False, "reason": "Could not parse identity response"}
    # Never use root for MarineVerse uploads. Avoid returning account identifiers.
    return {
        "ready": ":user/marineverse-data-engineer" in arn and not arn.endswith(":root"),
        "principal_kind": "iam_user" if ":user/" in arn else "not_iam_user",
        "expected_user": arn.endswith(":user/marineverse-data-engineer"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--check-aws", action="store_true")
    parser.add_argument("--profile", default="marineverse")
    parser.add_argument("--region", default="ap-south-1")
    args = parser.parse_args()
    report = inspect(resolve_data_root(args.data_root))
    if args.check_aws:
        report["aws"] = check_aws(args.profile, args.region)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
