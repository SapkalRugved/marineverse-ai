"""Read-only, bounded access to independently published Gold products."""

import json
from itertools import islice
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from backend.marine_data.platform.adapters import DATASETS
from backend.marine_data.storage import resolve_data_root

router = APIRouter(prefix="/api/v1/products", tags=["Gold products"])
Dataset = Literal[
    "ibtracs",
    "ports",
    "weather",
    "ocean",
    "ais",
    "coastline",
    "land",
    "protected_zones",
    "bathymetry",
]
Mart = Literal["objective1", "objective3", "objective4"]


@router.get("")
def catalog():
    root = resolve_data_root()
    products = []
    try:
        for dataset in DATASETS:
            path = root / "catalog" / dataset / "current.json"
            if path.is_file():
                products.append(json.loads(path.read_text(encoding="utf-8")))
        return {"datasets": products, "worldwide_live_coverage": False}
    except (OSError, ValueError):
        raise HTTPException(
            503, "Product catalog is temporarily unavailable."
        ) from None


@router.get("/{dataset}/{mart}")
def records(
    dataset: Dataset,
    mart: Mart,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0, le=1000000),
):
    root = resolve_data_root()
    pointer = root / "catalog" / dataset / "current.json"
    if not pointer.is_file():
        raise HTTPException(404, "No published release for this dataset.")
    try:
        report = json.loads(pointer.read_text(encoding="utf-8"))
        product = report["products"][mart]
        path = (root / product["path"]).resolve()
        if not path.is_relative_to((root / "gold").resolve()):
            raise ValueError("Product escapes Gold storage")
        with path.open(encoding="utf-8") as stream:
            page = [json.loads(line) for line in islice(stream, offset, offset + limit)]
        return {
            "dataset": dataset,
            "mart": mart,
            "release": report["release"],
            "count": len(page),
            "total": product["records"],
            "offset": offset,
            "next_offset": offset + len(page)
            if offset + len(page) < product["records"]
            else None,
            "coverage": report["coverage"],
            "records": page,
        }
    except (OSError, ValueError, KeyError):
        raise HTTPException(503, "Gold product is temporarily unavailable.") from None
