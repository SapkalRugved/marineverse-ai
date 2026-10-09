# Copernicus Ocean Data Ingestion

## Purpose

This pipeline retrieves near-real-time modelled ocean conditions for the
Indian marine region, transforms the gridded data into validated records,
and bulk-loads them into PostgreSQL/PostGIS.

The pipeline provides:

- Surface eastward and northward ocean currents
- Calculated current speed and direction
- Sea-surface temperature
- Significant wave height
- Wave-from direction
- Mean wave period

Copernicus Marine provides numerical model analysis and forecast data.
It is not a live buoy or direct sensor observation source.

## Data sources

Source identifier:

```text
copernicus-marine
```

Physics dataset:

```text
cmems_mod_glo_phy_anfc_0.083deg_PT1H-m
```

Physics variables:

- `thetao`: sea-water potential temperature
- `uo`: eastward sea-water velocity
- `vo`: northward sea-water velocity

Wave dataset:

```text
cmems_mod_glo_wav_anfc_0.083deg_PT3H-i
```

Wave variables:

- `VHM0`: significant wave height
- `VMDR`: mean wave-from direction
- `VTM02`: mean wave period

## Authentication

Create a free Copernicus Marine account and authenticate locally:

```powershell
copernicusmarine login
copernicusmarine login --check-credentials-valid
```

Credentials are stored outside this repository and must never be committed.

## Default retrieval

The default geographic bounds are:

- Longitude: 65°E to 100°E
- Latitude: 5°N to 25°N

The default model time is the previous completed three-hour interval in UTC.

Run the complete retrieval, transformation, validation, and loading pipeline:

```powershell
python -m backend.marine_data.ocean.run_copernicus_ocean_pipeline
```

Run the pipeline for an explicit time and geographic region:

```powershell
python -m backend.marine_data.ocean.run_copernicus_ocean_pipeline `
    --valid-time "2026-10-07T12:00:00Z" `
    --minimum-longitude 72.3 `
    --maximum-longitude 72.6 `
    --minimum-latitude 18.7 `
    --maximum-latitude 19.1
```

## Individual pipeline stages

Retrieve raw Copernicus datasets:

```powershell
python -m backend.marine_data.ocean.retrieve_copernicus_ocean
```

Select the most recently retained manifest:

```powershell
$manifest = Get-ChildItem `
    data\raw\ocean\copernicus_ocean_india_*_manifest.json |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

$manifest.FullName
```

Transform and inspect the selected manifest:

```powershell
python -m backend.marine_data.ocean.transform_copernicus_ocean `
    "$($manifest.FullName)"
```

Transform and load the selected manifest:

```powershell
python -m backend.marine_data.ocean.load_copernicus_ocean `
    "$($manifest.FullName)"
```

## Raw-data retention

The retrieval stage retains:

- One physics NetCDF file
- One wave NetCDF file
- One JSON manifest describing the retrieval

Files are stored under:

```text
data/raw/ocean/
```

Downloaded datasets and manifests are ignored by Git. Only the directory
placeholder is tracked.

## Transformation

The transformer:

- Verifies the manifest source and dataset metadata
- Validates timestamps and measurement units
- Aligns the physics and wave grids
- Rejects invalid or incomplete grid cells
- Calculates current speed from the `uo` and `vo` components
- Calculates current direction clockwise from north
- Produces records matching the `ocean_conditions` schema

Current speed is calculated as:

```text
sqrt(current_u_mps² + current_v_mps²)
```

## Database loading

Validated records are loaded into `ocean_conditions`.

The loader uses:

- A temporary staging table
- PostgreSQL `COPY` for bulk ingestion
- Set-based updates and inserts
- PostGIS geography points using SRID 4326
- A single database transaction

A logical ocean record is identified by:

- Source
- Source dataset
- Valid time
- Latitude
- Longitude
- Depth
- Forecast flag

Rerunning the same dataset updates existing records without creating duplicates.

## Ingestion auditing

Each complete or load-only execution writes an audit record to
`ingestion_runs` using this pipeline identifier:

```text
ocean_copernicus_india
```

The audit record includes:

- Start and completion timestamps
- Success or failure status
- Source records read
- Records written
- Failure message, when applicable

## Tests

Run the ocean test suite:

```powershell
python -m unittest discover `
    -s tests `
    -p "test_ocean*.py" `
    -v
```

Run the complete project test suite:

```powershell
python -m unittest discover `
    -s tests `
    -p "test_*.py" `
    -v
```

Database integration tests require a running PostgreSQL/PostGIS database and
valid PostgreSQL credentials.

## Verified full-region run

A full India-region execution produced:

- 101,461 source grid cells
- 63,196 valid ocean-condition records
- 38,265 rejected land or incomplete grid cells
- Zero duplicate logical records
- Zero missing PostGIS locations
- Zero coordinate or SRID mismatches
- Zero calculated-current-speed mismatches
