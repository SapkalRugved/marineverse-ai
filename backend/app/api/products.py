"""Read-only, bounded access to independently published Gold products."""

import json
from itertools import islice
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from backend.marine_data.platform.adapters import DATASETS
from backend.marine_data.storage import resolve_data_root
from backend.marine_data.platform.verify import load_receipt, confined

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
                products.append(load_receipt(root, dataset))
        return {"datasets": products, "worldwide_live_coverage": False}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
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
        report = load_receipt(root, dataset)
        product = report["products"][mart]
        path = confined(root.resolve(), product["path"], f"gold/{dataset}/{report['release']}")
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
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        raise HTTPException(503, "Gold product is temporarily unavailable.") from None
