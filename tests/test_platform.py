"""Regression tests using NOAA real rows; invalid inputs are explicit mutations."""

import csv
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.marine_data.platform.adapters import ibtracs_rows
from backend.marine_data.platform.pipeline import run, dataset_lock
from backend.marine_data.platform.sources import tiles

FIXTURE = Path(__file__).parent / "fixtures" / "ibtracs_real_excerpt.csv"
URL = "https://www.ncei.noaa.gov/products/international-best-track-archive"


def publish(root, path=FIXTURE, **kwargs):
    return run(
        "ibtracs",
        path,
        root=root,
        source_url=URL,
        coverage="Selected real NOAA observations; not full worldwide coverage",
        **kwargs,
    )


def mutate(path, change):
    with FIXTURE.open(newline="") as stream:
        rows = list(csv.reader(stream))
    change(rows)
    with path.open("w", newline="") as stream:
        csv.writer(stream).writerows(rows)
    return path


def test_real_noaa_units_missing_basin_and_dateline():
    rows = [record for _, record, error in ibtracs_rows(FIXTURE) if not error]
    assert any(r["basin"] == "NA" for r in rows)
    assert any(r["wind_speed_mps"] is None for r in rows)
    wrapped = next(r for r in rows if r["source_longitude"] > 180)
    assert wrapped["longitude"] == pytest.approx(wrapped["source_longitude"] - 360)
    assert all(-180 <= r["longitude"] < 180 for r in rows)


def test_three_independent_products_and_replay(tmp_path):
    first = publish(tmp_path)
    second = publish(tmp_path)
    assert first["accepted"] == second["accepted"]
    assert first["bronze_sha256"] == second["bronze_sha256"]
    assert first["silver_sha256"] == second["silver_sha256"]
    assert first["release"] != second["release"]
    products = second["products"]
    twin = json.loads(
        (tmp_path / products["objective1"]["path"]).read_text().splitlines()[0]
    )
    evidence = json.loads(
        (tmp_path / products["objective3"]["path"]).read_text().splitlines()[0]
    )
    decision = json.loads(
        (tmp_path / products["objective4"]["path"]).read_text().splitlines()[0]
    )
    assert twin["type"] == "Feature"
    assert evidence["evidence_id"] == twin["properties"]["_record_id"]
    assert decision["coverage"] == "available_records_only"
    assert len({p["sha256"] for p in products.values()}) == 3
    assert all((tmp_path / p["path"]).is_file() for p in products.values())


def test_deduplication(tmp_path):
    source = mutate(tmp_path / "duplicate.csv", lambda rows: rows.append(rows[2]))
    result = publish(tmp_path, source)
    assert result["duplicates"] == 1
    assert (
        result["read"] == result["accepted"] + result["rejected"] + result["duplicates"]
    )


def test_bad_units_preserve_prior_release(tmp_path):
    first = publish(tmp_path)
    bad = mutate(
        tmp_path / "bad.csv",
        lambda rows: rows[1].__setitem__(rows[0].index("WMO_WIND"), "m/s"),
    )
    with pytest.raises(ValueError, match="units"):
        publish(tmp_path, bad)
    current = json.loads((tmp_path / "catalog/ibtracs/current.json").read_text())
    assert current["release"] == first["release"]
    reports = [
        json.loads(p.read_text())
        for p in (tmp_path / "silver/ibtracs").glob("*/report.json")
    ]
    assert {r["status"] for r in reports} == {"success", "failed"}


def test_quality_gate_and_quarantine(tmp_path):
    def change(rows):
        for row in rows[2:]:
            row[rows[0].index("LAT")] = "999"

    source = mutate(tmp_path / "invalid.csv", change)
    with pytest.raises(ValueError, match="quality gate"):
        publish(tmp_path, source)
    assert not (tmp_path / "catalog/ibtracs/current.json").exists()
    assert (
        next((tmp_path / "silver/ibtracs").glob("*/rejections.jsonl")).stat().st_size
        > 0
    )


def test_gold_failure_does_not_publish(tmp_path):
    first = publish(tmp_path)
    with patch(
        "backend.marine_data.platform.pipeline.build_gold",
        side_effect=OSError("disk full"),
    ):
        with pytest.raises(OSError):
            publish(tmp_path)
    assert (
        json.loads((tmp_path / "catalog/ibtracs/current.json").read_text())["release"]
        == first["release"]
    )


def test_os_lock_prevents_overlap(tmp_path):
    with dataset_lock(tmp_path, "ibtracs"):
        with pytest.raises(OSError):
            publish(tmp_path)
    assert publish(tmp_path)["status"] == "success"


def test_api_and_validation(tmp_path, monkeypatch):
    monkeypatch.setenv("MARINEVERSE_DATA_DIR", str(tmp_path))
    client = TestClient(app)
    assert client.get("/api/v1/products/ibtracs/objective1").status_code == 404
    report = publish(tmp_path)
    assert client.get("/api/v1/products").json()["worldwide_live_coverage"] is False
    for mart in report["products"]:
        page = client.get(f"/api/v1/products/ibtracs/{mart}?limit=1").json()
        assert page["count"] == 1
        assert page["release"] == report["release"]
    assert client.get("/api/v1/products/unknown/objective1").status_code == 422
    assert (
        client.get("/api/v1/products/ibtracs/objective1?limit=1001").status_code == 422
    )
    pointer = tmp_path / "catalog/ibtracs/current.json"
    pointer.write_text("{")
    assert client.get("/api/v1/products/ibtracs/objective1").status_code == 503


def test_products_reject_path_escape(tmp_path, monkeypatch):
    monkeypatch.setenv("MARINEVERSE_DATA_DIR", str(tmp_path))
    report = publish(tmp_path)
    report["products"]["objective1"]["path"] = "../private.json"
    (tmp_path / "catalog/ibtracs/current.json").write_text(json.dumps(report))
    assert TestClient(app).get("/api/v1/products/ibtracs/objective1").status_code == 503


def test_world_tiles_are_complete_and_bounded():
    plan = tiles()
    assert len(plan) == 72
    assert (
        sum((t["north"] - t["south"]) * (t["east"] - t["west"]) for t in plan)
        == 180 * 360
    )
    assert min(t["west"] for t in plan) == -180
    assert max(t["east"] for t in plan) == 180


def test_real_coastline_to_all_marts(tmp_path):
    source = FIXTURE.parent / "coastline_real_excerpt.geojson"
    result = run(
        "coastline",
        source,
        source_url="https://www.naturalearthdata.com/",
        coverage="One real Natural Earth coastline feature",
        root=tmp_path,
    )
    assert result["accepted"] == 1
    assert result["bounds"] is not None
    for mart in result["products"]:
        product = json.loads((tmp_path / result["products"][mart]["path"]).read_text())
        assert result["products"][mart]["records"] == 1
        if mart != "objective3":
            assert product["geometry"]["type"] == "LineString"


def test_invalid_geometry_is_rejected(tmp_path):
    source = json.loads((FIXTURE.parent / "coastline_real_excerpt.geojson").read_text())
    source["features"][0]["geometry"]["coordinates"][0] = [999, 999]
    path = tmp_path / "invalid.geojson"
    path.write_text(json.dumps(source))
    with pytest.raises(ValueError, match="quality gate"):
        run(
            "coastline",
            path,
            source_url=URL,
            coverage="Explicit invalid mutation",
            root=tmp_path,
        )


def test_ais_worldwide_config_is_validated(monkeypatch):
    from backend.marine_data.ais.probe_aisstream import (
        build_subscription,
        AisProbeError,
    )

    monkeypatch.setenv("MARINEVERSE_AIS_BOUNDING_BOXES", "[[[-90,-180],[90,180]]]")
    assert build_subscription("test-only-key")["BoundingBoxes"] == [
        [[-90, -180], [90, 180]]
    ]
    monkeypatch.setenv("MARINEVERSE_AIS_BOUNDING_BOXES", "[[[90,180],[-90,-180]]]")
    with pytest.raises(AisProbeError):
        build_subscription("test-only-key")


def test_bronze_checksum_tampering_fails_closed(tmp_path):
    result = publish(tmp_path)
    bronze = next((tmp_path / "bronze/ibtracs" / result["bronze_sha256"]).glob("*.csv"))
    bronze.write_text("corrupted")
    with pytest.raises(ValueError, match="checksum"):
        publish(tmp_path)
    assert (
        json.loads((tmp_path / "catalog/ibtracs/current.json").read_text())["release"]
        == result["release"]
    )


def test_legacy_ais_source_counts_are_not_output_counts(tmp_path):
    """Isolated mock: one AIS event expands to a vessel and position output."""
    from datetime import datetime, timezone
    from types import SimpleNamespace
    from backend.marine_data.ais.transformer import VesselRecord, VesselPositionRecord
    from backend.marine_data.platform.adapters import transform

    stamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    # Synthetic unit-test objects only; never used in real-data products.
    vessel = VesselRecord(123456789, None, None, None, None, None, "aisstream", stamp)
    position = VesselPositionRecord(
        123456789, stamp, 0, 0, None, None, None, None, "aisstream", stamp
    )
    result = SimpleNamespace(
        source_events_read=1,
        vessel_records=(vessel,),
        position_records=(position,),
        rejected_events=0,
        ignored_events=1,
        duplicates_removed=0,
    )
    path = tmp_path / "mock_capture.json"
    path.write_text("{}")
    with patch(
        "backend.marine_data.ais.transformer.transform_capture", return_value=result
    ):
        rows = list(transform(path, "ais", stamp))
    assert rows[0][1]["_adapter_quality"]["records_read"] == 1
    assert rows[0][1]["_adapter_quality"]["ignored"] == 1
    assert len(rows[1:]) == 2
    assert all(row[0] is None for row in rows[1:])
