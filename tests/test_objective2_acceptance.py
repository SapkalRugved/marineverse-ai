"""End-to-end contract acceptance against genuine NOAA/Natural Earth excerpts.

Tests use retained real source excerpts and a disposable data root. These do
not assert live worldwide coverage, production deployment, or private AWS.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.marine_data.platform.pipeline import run, MARTS
from backend.marine_data.platform.verify import verify
from backend.marine_data.platform.s3_release import release_paths

FIXTURE = Path(__file__).resolve().parent / "fixtures"
SOURCES = {
    "ibtracs": (
        FIXTURE / "ibtracs_real_excerpt.csv",
        "https://www.ncei.noaa.gov/products/international-best-track-archive",
        "Real NOAA IBTrACS excerpt for contract verification only",
    ),
    "coastline": (
        FIXTURE / "coastline_real_excerpt.geojson",
        "https://www.naturalearthdata.com/",
        "Real Natural Earth coastline excerpt for contract verification only",
    ),
}


@pytest.fixture
def published(tmp_path, monkeypatch):
    monkeypatch.setenv("MARINEVERSE_DATA_DIR", str(tmp_path))
    receipts = {}
    for dataset, (path, source_url, coverage) in SOURCES.items():
        receipts[dataset] = run(
            dataset, path, root=tmp_path,
            source_url=source_url, coverage=coverage,
        )
        assert verify(tmp_path, dataset)["verified"]
    return tmp_path, receipts


@pytest.mark.parametrize("dataset", list(SOURCES))
def test_complete_pipeline_to_all_three_api_contracts(published, dataset):
    root, receipts = published
    receipt = receipts[dataset]
    client = TestClient(app)
    catalog = client.get("/api/v1/products")
    assert catalog.status_code == 200
    assert catalog.json()["worldwide_live_coverage"] is False
    assert any(x["dataset"] == dataset for x in catalog.json()["datasets"])

    for mart in MARTS:
        response = client.get(f"/api/v1/products/{dataset}/{mart}", params={"limit": 1})
        assert response.status_code == 200
        page = response.json()
        assert page["dataset"] == dataset
        assert page["mart"] == mart
        assert page["release"] == receipt["release"]
        assert page["total"] == receipt["products"][mart]["records"]
        assert len(page["records"]) == 1
        assert page["coverage"] == receipt["coverage"]
        assert "source_url" in page["records"][0]["provenance"]
        if mart == "objective1":
            assert page["records"][0]["type"] == "Feature"
        elif mart == "objective3":
            assert "evidence_id" in page["records"][0]
            assert "facts" in page["records"][0]
        elif dataset == "coastline":
            assert page["records"][0]["geometry"]["type"] in (
                "LineString", "MultiLineString",
            )
        else:
            assert page["records"][0]["coverage"] == "available_records_only"
    _, selected_files = release_paths(root, dataset)
    assert len(selected_files) >= 7
    assert all(path.is_file() for path, _ in selected_files)


def test_api_page_cursor_and_missing_data_contract(published):
    _, receipts = published
    client = TestClient(app)
    response = client.get("/api/v1/products/ibtracs/objective1?limit=1")
    page = response.json()
    assert response.status_code == 200
    assert page["next_offset"] == 1
    next_page = client.get(
        f"/api/v1/products/ibtracs/objective1?limit=1&offset={page['next_offset']}"
    )
    assert next_page.status_code == 200
    assert next_page.json()["records"] != page["records"]
    assert client.get("/api/v1/products/ais/objective1").status_code == 404
    assert client.get("/api/v1/products/ocean/objective3").status_code == 404
    assert client.get("/api/v1/products/ibtracs/objective1?limit=0").status_code == 422


def test_catalog_receipts_do_not_pretend_global_live_coverage(published):
    _, receipts = published
    for receipt in receipts.values():
        assert receipt["worldwide_live_coverage"] is False
        assert receipt["accepted"] > 0
        assert receipt["rejected"] == 0
        assert all(receipt["products"][m]["records"] > 0 for m in MARTS)
        assert "excerpt" in receipt["coverage"].lower()


def test_api_survives_local_data_integrity_failure_without_data_leak(published):
    root, receipts = published
    receipt = receipts["ibtracs"]
    product_path = root / receipt["products"]["objective1"]["path"]
    product_path.write_text("not valid JSON\n", encoding="utf-8")
    assert verify(root, "ibtracs")["verified"] is False
    response = TestClient(app).get("/api/v1/products/ibtracs/objective1?limit=1")
    # API may return 503 or show a transient parse error: must not reveal storage path or bytes.
    assert response.status_code == 503
    assert str(root) not in response.text
