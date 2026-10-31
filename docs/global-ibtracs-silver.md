# Worldwide IBTrACS Silver Pipeline

## Scope

- **GitHub:** Objective 2 worldwide Bronze-to-Silver delivery. Branch `feat/global-ibtracs-silver`.
- **Input:** Authentic NOAA `ibtracs.ALL.list.v04r01.csv` in local Bronze staging; previously verified structurally at 730,378 observations and 13,631 unique storms (as of 2026-10-31).
- **Output:** Parquet Silver data plus JSON quality report. **No database changes and no API contract changes.**
- **Important:** Global source coverage varies by basin and year; do not claim a complete current live cyclone feed. Keep regional NI file in Bronze for provenance, but **do not merge NI into ALL**, which duplicates storms.
- **IOC tide-gauge API:** Deferred to the **last source acquisition milestone**, pending gauges_API moderator approval.

## Run on Windows PowerShell, from repository root

\`\`\`powershell
python -m pip install -r requirements-silver.txt
python -m unittest discover -s tests -p test_ibtracs_silver.py -v
python -m backend.marine_data.cyclones.ibtracs_silver --input "data/raw/cyclones/ibtracs/ibtracs.ALL.list.v04r01.csv" --output "data/processed/cyclones/ibtracs/global_cyclone_tracks.parquet"
\`\`\`

The importer streams rows in batches and writes a compressed Parquet dataset without loading the entire CSV into memory. It skips the IBTrACS units row, normalizes longitudes to [-180, 180), converts WMO wind from knots to m/s, keeps pressure in hPa, and stores UTC-aware timestamps. Missing wind/pressure remain null. Invalid rows are rejected and counted in `quality_report.json` (first 10 rejection examples only).

## Dataset contract (Silver v1)

| Field | Meaning |
|---|---|
| storm_id | Stable IBTrACS SID |
| season | IBTrACS season label, may exceed calendar year for Southern Hemisphere |
| basin | Original source basin code |
| name | Nullable storm name |
| observed_at_utc | UTC timestamp |
| latitude, longitude | WGS84 degrees; longitude normalized to [-180, 180) |
| wind_speed_ms | Nullable WMO wind measurement, m/s |
| pressure_hpa | Nullable WMO pressure measurement, hPa |
| source | Literal `NOAA_IBTrACS_v04r01_ALL` |

Silver v1 intentionally retains a reduced common data contract. Some source-specific agency values are **not included**, and missing WMO fields are **not filled** from incompatible agency observations. The quality report contains the local source SHA-256, basin counts, rejections and missing-field counts.

## Storage and collaboration

- Bronze local original: `data/raw/cyclones/ibtracs/ibtracs.ALL.list.v04r01.csv`.
- Silver local: `data/processed/cyclones/ibtracs/global_cyclone_tracks.parquet`.
- Intended Bronze S3: `s3://marineverse-ai-data-lake-apsit/bronze/cyclones/ibtracs/ibtracs.ALL.list.v04r01.csv`.
- Intended Silver S3: `s3://marineverse-ai-data-lake-apsit/silver/cyclones/ibtracs/global_cyclone_tracks.parquet`.

S3 upload is **not executed by this pipeline** and currently needs an authenticated `marineverse-data-engineer` IAM session. Never use root credentials or commit local datasets, `.env`, or AWS secrets. Keep Gold exports separate by consumer objective.

## Verification

Tests are designed to run with synthetic sample rows (no real NOAA CSV required). Before publishing Silver remotely, run the tests and compare `source_sha256` in `quality_report.json` to the original SHA-256. Do not interpret a structural validation PASS as a source-authenticity or full scientific-quality guarantee.
