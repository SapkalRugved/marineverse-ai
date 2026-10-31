"""Preview or publish retained genuine Natural Earth inputs without network/AWS.

This command never attempts fresh downloads or re-enables background tasks.
It reuses frozen Bronze/Silver/Gold pipeline and skips already-published sources.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from backend.marine_data.storage import resolve_data_root
from backend.marine_data.platform.pipeline import run

SOURCE = {
    "coastline": {
        "relative_path": "raw/geospatial/natural_earth/ne_10m_coastline.zip",
        "source_url": "https://www.naturalearthdata.com/",
        "coverage": "Natural Earth 1:10m global generalized coastline lines; visualization, not navigation",
    },
    "land": {
        "relative_path": "raw/geospatial/natural_earth/ne_10m_land.zip",
        "source_url": "https://www.naturalearthdata.com/",
        "coverage": "Natural Earth 1:10m global generalized land polygons; visualization, not navigation",
    },
}


def plan(root: Path, *, include_existing=False) -> list[dict]:
    """Offline, read-only source discovery; no arbitrary ZIP files selected."""
    root = Path(root).resolve()
    result = []
    for name, spec in SOURCE.items():
        source = root / spec["relative_path"]
        current = root / "catalog" / name / "current.json"
        # Never consider the receipt valid merely because a file is present.
        is_published = False
        if current.is_file():
            try:
                receipt = json.loads(current.read_text(encoding="utf-8"))
                is_published = (
                    receipt.get("dataset") == name
                    and receipt.get("status") == "success"
                    and all(
                        (
                            root / receipt["products"][mart]["path"]
                        ).resolve().is_relative_to((root / "gold").resolve())
                        and (root / receipt["products"][mart]["path"]).is_file()
                        for mart in ("objective1", "objective3", "objective4")
                    )
                )
            except (ValueError, KeyError, OSError, TypeError):
                is_published = False
        result.append({
            "dataset": name,
            "source": str(source.relative_to(root)),
            "available": source.is_file(),
            "bytes": source.stat().st_size if source.is_file() else 0,
            "published": is_published,
            "action": (
                "missing_source" if not source.is_file() else
                "skip_published" if is_published and not include_existing else
                "publish"
            ),
        })
    return result


def execute(root: Path, *, include_existing=False) -> dict:
    root = Path(root).resolve()
    steps = plan(root, include_existing=include_existing)
    receipts = {}
    errors = {}
    for item in steps:
        if item["action"] != "publish":
            continue
        name = item["dataset"]
        spec = SOURCE[name]
        try:
            receipt = run(
                name, root / spec["relative_path"],
                source_url=spec["source_url"],
                coverage=spec["coverage"], root=root,
            )
            receipts[name] = {
                "status": receipt["status"],
                "accepted": receipt["accepted"],
                "rejected": receipt["rejected"],
                "gold_counts": receipt["gold_counts"],
            }
        except (OSError, ValueError, RuntimeError) as exc:
            errors[name] = type(exc).__name__ + ": " + str(exc)
    return {"plan": steps, "receipts": receipts, "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--execute", action="store_true",
                        help="Process source ZIPs and publish three marts")
    parser.add_argument("--reprocess", action="store_true",
                        help="Explicitly reprocess already-published ZIPs")
    args = parser.parse_args()
    root = resolve_data_root(args.data_root)
    if not args.execute:
        print(json.dumps({"execute": False, "plan": plan(root, include_existing=args.reprocess)},
                         indent=2))
        return 0
    outcome = execute(root, include_existing=args.reprocess)
    print(json.dumps(outcome, indent=2))
    return int(bool(outcome["errors"]) or any(
        row["action"] == "missing_source" for row in outcome["plan"]
    ))


if __name__ == "__main__":
    sys.exit(main())
