"""Validated file imports for real shoreline, zone and bathymetric products."""

import io
import json
import math
from zipfile import ZipFile


def validate_feature(feature, dataset, index):
    from shapely.geometry import shape, mapping

    if feature.get("type") != "Feature":
        raise ValueError("Expected GeoJSON Feature")
    geometry = shape(feature.get("geometry"))
    if geometry.is_empty or not geometry.is_valid:
        raise ValueError("Empty or invalid source geometry; no automatic repair")
    west, south, east, north = geometry.bounds
    if not all(math.isfinite(v) for v in geometry.bounds) or not (
        -180 <= west <= east <= 180 and -90 <= south <= north <= 90
    ):
        raise ValueError("Geometry outside WGS84 longitude/latitude bounds")
    if dataset in {"land", "protected_zones"} and geometry.geom_type not in {
        "Polygon",
        "MultiPolygon",
    }:
        raise ValueError("Polygon geometry required")
    if dataset == "coastline" and geometry.geom_type not in {
        "LineString",
        "MultiLineString",
    }:
        raise ValueError("Line geometry required")
    properties = feature.get("properties") or {}
    if not isinstance(properties, dict):
        raise ValueError("Feature properties must be an object")
    identity = feature.get("id")
    if identity is None:
        identity = properties.get("WDPAID") or properties.get("ne_id") or index
    return {
        "source_id": str(identity),
        "source": dataset,
        "geometry": mapping(geometry),
        "geometry_bounds": list(geometry.bounds),
        "attributes": properties,
        "authority": "source_dataset_only; not a navigational or legal determination",
    }


def vector_rows(path, dataset):
    """Accept RFC7946 GeoJSON or a single WGS84 shapefile ZIP; never extract ZIP paths."""
    if path.suffix.lower() == ".zip":
        import shapefile
        from pyproj import CRS

        with ZipFile(path) as archive:
            names = archive.namelist()
            shp = [n for n in names if n.lower().endswith(".shp")]
            if len(shp) != 1:
                raise ValueError("ZIP must contain exactly one shapefile")
            stem = shp[0][:-4]
            if sum(i.file_size for i in archive.infolist()) > 1024**3:
                raise ValueError("ZIP uncompressed size exceeds 1 GiB import limit")
            crs = CRS.from_wkt(archive.read(stem + ".prj").decode())
            if not crs.equals(CRS.from_epsg(4326), ignore_axis_order=True):
                raise ValueError("Shapefile must use WGS84 geographic coordinates")
            with shapefile.Reader(
                shp=io.BytesIO(archive.read(stem + ".shp")),
                shx=io.BytesIO(archive.read(stem + ".shx")),
                dbf=io.BytesIO(archive.read(stem + ".dbf")),
            ) as reader:
                for index, record in enumerate(reader.iterShapeRecords(), 1):
                    try:
                        yield (
                            index,
                            validate_feature(record.__geo_interface__, dataset, index),
                            None,
                        )
                    except (ValueError, TypeError) as exc:
                        yield index, None, str(exc)
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("type") != "FeatureCollection" or "crs" in payload:
            raise ValueError(
                "Require RFC7946 WGS84 FeatureCollection without legacy CRS"
            )
        for index, feature in enumerate(payload["features"], 1):
            try:
                yield index, validate_feature(feature, dataset, index), None
            except (ValueError, TypeError, AttributeError) as exc:
                yield index, None, str(exc)


def bathymetry_rows(path):
    """Import bounded GEBCO NetCDF subsets; elevation is positive upward in metres.

    Reject full-resolution world rasters rather than silently downsample them.
    Plan/prepare documented subsets upstream to keep MVP resource use bounded.
    """
    import xarray as xr

    with xr.open_dataset(path) as grid:
        if not {"lat", "lon", "elevation"}.issubset(grid.variables):
            raise ValueError("Expected GEBCO lat/lon/elevation variables")
        elevation = grid["elevation"]
        if set(elevation.dims) != {"lat", "lon"} or elevation.attrs.get(
            "units"
        ) not in {"m", "meters", "metres"}:
            raise ValueError("Require two-dimensional elevation in metres")
        if elevation.size > 2_000_000:
            raise ValueError(
                "GEBCO subset exceeds two million cells; prepare bounded tiles first"
            )
        if (
            grid["lat"].attrs.get("units") != "degrees_north"
            or grid["lon"].attrs.get("units") != "degrees_east"
        ):
            raise ValueError("Require geographic degree coordinate units")
        elevation = elevation.transpose("lat", "lon")
        index = 0
        for lat_index, lat in enumerate(grid["lat"].values):
            values = elevation.isel(lat=lat_index).values
            for lon, value in zip(grid["lon"].values, values, strict=True):
                index += 1
                lat, lon, value = float(lat), float(lon), float(value)
                if not all(math.isfinite(v) for v in (lat, lon, value)) or not (
                    -90 <= lat <= 90 and -180 <= lon <= 180 and -12000 <= value <= 10000
                ):
                    yield index, None, "invalid GEBCO cell"
                    continue
                yield (
                    index,
                    {
                        "source": "gebco",
                        "source_dataset": str(grid.attrs.get("title", "GEBCO subset")),
                        "latitude": lat,
                        "longitude": lon,
                        "elevation_m": value,
                        "water_depth_m": -value if value < 0 else None,
                        "vertical_convention": "source elevation positive upward; not chart datum",
                    },
                    None,
                )
