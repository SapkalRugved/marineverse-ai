"""Local-only GEBCO NetCDF ZIP preparation, synthetic test grids only."""
from zipfile import ZipFile

import numpy as np
import pytest
import xarray as xr

from backend.marine_data.platform import prepare_gebco as impl


def archive(root, *, invalid=False):
    source = root / "raw" / "geospatial" / "gebco" / "sample_gebco.zip"
    source.parent.mkdir(parents=True)
    nc = root / "synthetic_test.nc"
    grid = xr.Dataset(
        {"elevation": (("lat", "lon"), np.arange(48, dtype=np.float32).reshape(6, 8) - 24)},
        coords={"lat": np.arange(6), "lon": np.arange(8)},
    )
    grid["lat"].attrs["units"] = "degrees_north"
    grid["lon"].attrs["units"] = "degrees_east"
    grid["elevation"].attrs["units"] = "feet" if invalid else "m"
    grid.to_netcdf(nc)
    with ZipFile(source, "w") as zipped:
        zipped.write(nc, "archive/path/gebco_grid.nc")
    nc.unlink()
    return source


def test_preview_does_not_persist_prepared_data(tmp_path, monkeypatch):
    monkeypatch.setattr(impl, "MAX_CELLS", 12)
    source = archive(tmp_path)
    result = impl.prepare(source, tmp_path)
    assert not result["execute"]
    assert result["source_cells"] == 48
    assert result["selected_cells"] <= 12
    assert result["sample_stride"] > 1
    assert not (tmp_path / "raw" / "bathymetry").exists()


def test_prepared_grid_keeps_original_points_and_provenance(tmp_path, monkeypatch):
    monkeypatch.setattr(impl, "MAX_CELLS", 12)
    source = archive(tmp_path)
    result = impl.prepare(source, tmp_path, execute=True)
    prepared = tmp_path / result["prepared_path"]
    with xr.open_dataset(prepared) as grid:
        stride = result["sample_stride"]
        assert grid["elevation"].size == result["selected_cells"]
        assert list(grid["lon"].values) == list(range(0, 8, stride))
        assert list(grid["lat"].values) == list(range(0, 6, stride))
        assert grid["elevation"].attrs["units"] == "m"
        assert "NOT navigation chart" in grid.attrs["title"]
        assert grid.attrs["sampling_stride"] == str(stride)
    again = impl.prepare(source, tmp_path, execute=True)
    assert again["prepared_path"] == result["prepared_path"]


def test_cannot_publish_from_preview(tmp_path):
    source = archive(tmp_path)
    with pytest.raises(ValueError, match="requires"):
        impl.prepare(source, tmp_path, execute=False, publish=True)


def test_invalid_units_are_rejected(tmp_path):
    source = archive(tmp_path, invalid=True)
    with pytest.raises(ValueError, match="units"):
        impl.prepare(source, tmp_path)


def test_extra_nc_members_are_rejected(tmp_path):
    source = archive(tmp_path)
    with ZipFile(source, "a") as zipped:
        zipped.writestr("extra.nc", b"fake")
    with pytest.raises(ValueError, match="exactly one"):
        impl.prepare(source, tmp_path)


def test_prepared_source_can_be_published_to_three_marts(tmp_path, monkeypatch):
    monkeypatch.setattr(impl, "MAX_CELLS", 12)
    source = archive(tmp_path)
    result = impl.prepare(source, tmp_path, execute=True, publish=True)
    assert result["publication"]["status"] == "success"
    assert result["publication"]["accepted"] == result["selected_cells"]
    assert result["publication"]["gold_counts"]["objective1"] > 0
    assert result["publication"]["gold_counts"]["objective3"] > 0
    assert result["publication"]["gold_counts"]["objective4"] > 0
