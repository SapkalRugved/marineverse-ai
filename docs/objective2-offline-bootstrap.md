# Objective 2: offline publication and content-integrity gates

These commands were added to automate **already retained genuine marine data**.
They do not need AWS credentials and do not start any Windows scheduled tasks.
They do not fabricate observations, acquire new worldwide datasets or publish
anything to a public GitHub repository.

## Natural Earth coastline and land

From the repository root, default data storage is `data/`.
Both authentic local archives are expected at:

- `data/raw/geospatial/natural_earth/ne_10m_coastline.zip`
- `data/raw/geospatial/natural_earth/ne_10m_land.zip`

Preview is read-only:

```powershell
python -m backend.marine_data.platform.bootstrap
```

Actual local Bronze → Silver → three Gold publication requires explicit action:

```powershell
python -m backend.marine_data.platform.bootstrap --execute
```

The command skips already-published sources by default. If a source is missing
it reports `missing_source` and returns an error for execute mode; it never
substitutes synthetic data. Use `--reprocess` only if a new release is truly
needed. WGS84 CRS, valid geometry and dataset-specific shape types are enforced
by existing validated adapters. Coverage is generalized global visualization,
**not** nautical-chart coastline or navigation-safe data.

## Verify completed real NOAA / geospatial publication

```powershell
python -m backend.marine_data.platform.verify ibtracs
python -m backend.marine_data.platform.verify coastline
python -m backend.marine_data.platform.verify land
```

Checks the current release receipt, original immutable Bronze content
(including sibling source files), Silver checksum and checksums for each of
the three independent Gold outputs, plus receipt record counts. Only statuses,
counts and stage names are printed; no file checksums, individual records or
AWS account details are printed.

A PASS is evidence of local data integrity only. It is not proof that S3
contains the same content or that teammates can use deployed HTTP endpoints.
The verifier scans large files and may perform substantial disk I/O.
To use external data storage, pass `--data-root` to either CLI.

## Remaining non-automatable checkpoints

The real global IBTrACS CSV was uploaded to the existing **private** S3 bucket
and its expected object length and AES256 server-side encryption were observed.
Independent S3 content-integrity verification and Silver/Gold remote publication
remain unverified. AWS account access cannot be inferred from GitHub CI.

GEBCO regional archive must be inspected and tiled into supported bounded
NetCDF cells before running existing bathymetry adapter. The unbounded regional
source exceeds the current two-million-cell safeguard; do not bypass it.
Ocean and AIS refresh require provider access and cannot imply global live
coverage. The original Windows automatic ETL tasks have been intentionally
disabled. IOC sea-level integration remains **last**, pending provider approval.

See Issue #16 for the canonical end-to-end, S3 and teammate handoff gates.
