"""Validation of release integrity against real source-backed test fixtures."""
import json
from pathlib import Path

from backend.marine_data.platform.pipeline import run
from backend.marine_data.platform.verify import verify

FIXTURE = Path(__file__).parent / "fixtures" / "ibtracs_real_excerpt.csv"


def publish(tmp_path):
    return run(
        "ibtracs",
        FIXTURE,
        source_url="https://www.ncei.noaa.gov/products/international-best-track-archive",
        coverage="Test excerpt of actual NOAA observations; not live global coverage",
        root=tmp_path,
    )


def test_verify_all_immutable_layers(tmp_path):
    publish(tmp_path)
    result = verify(tmp_path, "ibtracs")
    assert result["verified"]
    assert all(result["checks"].values())
    assert result["accepted"] > 0
    assert "sha256" not in json.dumps(result)


def test_verify_missing_receipt(tmp_path):
    result = verify(tmp_path, "ibtracs")
    assert not result["verified"]
    assert result["reason"] == "no_published_receipt"


def test_verify_corrupted_gold(tmp_path):
    receipt = publish(tmp_path)
    gold = tmp_path / receipt["products"]["objective3"]["path"]
    gold.write_text(gold.read_text() + "tampering")
    result = verify(tmp_path, "ibtracs")
    assert not result["verified"]
    assert result["checks"]["objective3"] is False


def test_verify_corrupted_bronze(tmp_path):
    receipt = publish(tmp_path)
    bronze = tmp_path / "bronze" / "ibtracs" / receipt["bronze_sha256"] / FIXTURE.name
    bronze.write_bytes(b"tampered")
    assert verify(tmp_path, "ibtracs")["checks"]["bronze"] is False


def test_verify_path_escape_is_rejected(tmp_path):
    receipt = publish(tmp_path)
    receipt["products"]["objective1"]["path"] = "../../outside.jsonl"
    pointer = tmp_path / "catalog" / "ibtracs" / "current.json"
    pointer.write_text(json.dumps(receipt))
    result = verify(tmp_path, "ibtracs")
    assert not result["verified"]
    assert result["reason"] == "invalid_or_unreadable_receipt"
