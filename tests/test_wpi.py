"""Synthetic WPI-shaped test rows; never production data or source evidence."""
import csv
from datetime import datetime, timezone

import pytest

from backend.marine_data.platform.wpi import rows, URL
from backend.marine_data.platform.pipeline import run
from backend.marine_data.platform.verify import audit_release


def csv_file(tmp_path, **overrides):
    row = {"World Port Index Number": "123.0", "Main Port Name": "TEST ONLY",
           "Country Code": "Test Country", "Latitude": "18.9", "Longitude": "72.8"}
    row.update(overrides)
    path = tmp_path / "test.csv"
    with path.open("w", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=row)
        writer.writeheader()
        writer.writerow(row)
    return path


def test_existing_ports_contract_and_all_three_marts(tmp_path):
    path = csv_file(tmp_path)
    report = run("ports", path, root=tmp_path, source_url=URL, coverage="Synthetic test only")
    assert report["accepted"] == 1
    assert audit_release(tmp_path, "ports")["verified"]
    record = next(rows(path, datetime.now(timezone.utc)))[1]
    assert record["source_id"] == "123"
    assert record["source"] == "nga-world-port-index"
    assert record["country"] == "Test Country"
    assert "upstream per-port update time unavailable" in record["timestamp_basis"]


@pytest.mark.parametrize("field,value", [
    ("Latitude", "NaN"), ("Longitude", "181"), ("World Port Index Number", "1.5"),
    ("World Port Index Number", "NaN"), ("Main Port Name", " "),
])
def test_invalid_source_rows_are_quarantined(tmp_path, field, value):
    path = csv_file(tmp_path, **{field: value})
    _, record, error = next(rows(path, datetime.now(timezone.utc)))
    assert record is None and error


def test_non_wpi_csv_fails_closed(tmp_path):
    path = tmp_path / "wrong.csv"
    path.write_text("lat,lon\n1,2\n")
    with pytest.raises(ValueError, match="columns"):
        list(rows(path, datetime.now(timezone.utc)))


def test_download_rejects_oversize_without_retaining_partial(tmp_path, monkeypatch):
    from unittest.mock import MagicMock
    from backend.marine_data.platform import wpi
    response = MagicMock()
    response.__enter__.return_value = response
    response.iter_content.return_value = [b"12345"]
    monkeypatch.setattr("requests.get", lambda *a, **kw: response)
    monkeypatch.setattr(wpi, "MAX_BYTES", 4)
    with pytest.raises(ValueError, match="limit"):
        wpi.download(tmp_path)
    assert not list(tmp_path.rglob("*.tmp"))
    assert not list(tmp_path.rglob("*.csv"))


def test_weather_refresh_enforces_small_provider_budget(tmp_path):
    from backend.marine_data.platform.refresh import _refresh
    with pytest.raises(ValueError, match="location limit"):
        _refresh("weather", tmp_path, max_weather_locations=101)
