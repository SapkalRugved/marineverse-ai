# Worldwide Objective 2: executable MVP

## Audit and preserved contracts

Audited published `main` at `28838384e13346ad70fbfe5b3722bfdece0960bd`.
`feat/aws-s3-deployment` was absent from the remote on 2026-10-31.
`feat/global-ibtracs-silver` pointed at the same merge as main and contained
no IBTrACS code. Local-only changes on the developer's Windows computer
were not accessible. Do not replace that checkout with this work blindly.

Reuse: existing ports/weather/ocean/AIS transformers, HTTP retry session,
storage resolver, FastAPI application and optional S3 adapter. Existing
regional ETL commands, seven SQL files defining six tables, and API contracts
remain unchanged. New file products are additive and do not require migrations.
Existing API readers continue to query PostgreSQL, not these files.

Baseline here: 158 tests passed; 17 existing PostGIS integration tests could
not connect because there was no PostgreSQL service/password. Those are
required integration checks, not passing or silently skipped tests.

## Data flow and publication

`real source files -> content-addressed Bronze -> normalized Silver JSONL
-> three separate Gold JSONL marts -> additive read-only FastAPI endpoints`.

Install `python -m pip install -r requirements-dev.txt` for development or
`-r requirements-platform.txt` for runtime. Use Python 3.12. All commands run
from the repository root. Use external storage, e.g. set
`MARINEVERSE_DATA_DIR=C:\MarineVerseData` in your existing untracked `.env`.
CLI `--data-root` overrides it. Nothing automatically uploads to AWS.

Runtime structure:

- `bronze/<dataset>/<bundle-sha256>/`: original input bytes; ocean includes
  sibling NetCDF dependencies. A hash covers each filename, size and checksum.
- `silver/<dataset>/<release>/records.jsonl`: UTC timestamps, WGS84 coordinates,
  contract units and stable logical record IDs.
- `silver/<dataset>/<release>/rejections.jsonl`: rejected source row numbers and
  reasons. Legacy transformers only expose aggregate rejection counts, so their
  rejected row numbers are NULL; this limitation is explicit.
- `silver/<dataset>/<release>/report.json`: quality counts, null counts, bounds,
  time span, source URL, coverage, checksums, timestamps and product receipts.
- `gold/<dataset>/<release>/objective{1,3,4}.jsonl`: independent consumer outputs.
- `catalog/<dataset>/current.json`: the complete successful release receipt.

Publication uses one final atomic pointer replacement. Failure leaves the
previous release selected. OS file locks serialize each dataset's publication
and release automatically after process exit/crash. A failed run retains its
report and partial outputs for investigation; it never becomes current.
SQLite provides disk-backed deduplication and aggregation; temporary databases
are removed after use. Unchanged input reuses Bronze bytes; each replay creates
a new release, with stable logical IDs. No automatic deletion of old releases.
Plan retention explicitly before frequent full-archive rebuilds.

Reject threshold defaults to 5% of rows read. Zero accepted records always
fails. Tune `--max-rejection-fraction` explicitly for known masked ocean cells;
review reports rather than treating masked land cells as bad ocean observations.
World coverage describes **available source records**, never a guarantee of
live observations everywhere. No missing dataset or quantity is synthesized.

## Independent Gold contracts (version 1)

| Mart | Consumers | Product |
|---|---|---|
| Objective 1 | Digital Twin | GeoJSON Features serialized one per line; original geometries or WGS84 points, typed properties and provenance. Static vessel profiles have NULL geometry. |
| Objective 3 | AI Assistant | Evidence objects with stable evidence ID, typed facts and Bronze/release provenance. No generated answers or embeddings. |
| Objective 4 | Decision Support | UTC daily 1-degree cells with record counts, maximum available wind/wave, minimum pressure/water depth; separate agency groups. Vector sources retain individual geometry and attributes. Descriptive inputs only. |

NULL extrema mean unavailable, never calm seas, zero depth or safe conditions.
Cell counts are records, **not vessel counts, storm counts, congestion scores or
probabilities**. Dataset-level receipts supply actual geographic/time coverage.
Historical, forecast, provisional and interpolated source metadata are retained.
No route risk model, tidal prediction or legal restriction inference is included.

API additions:

- `GET /api/v1/products`: successful release catalog and quality receipts.
- `GET /api/v1/products/{dataset}/{objective1|objective3|objective4}`:
  `limit=1..1000`, `offset=0..1000000`, release ID, total, next offset and records.
- Unknown dataset/mart and invalid pagination: 422; absent release: 404;
  unreadable/corrupt catalog/product: sanitized 503.

Pages resolve the current release independently. For a stable bulk export use
the immutable file path/checksum in the catalog receipt. These MVP endpoints
scan to the offset; they are not a large-scale search index. Deploy behind the
same private access controls as the current API; no new public hosting is created.

## Run the already downloaded global IBTrACS file

Renew the existing **IAM** session separately if necessary. Never substitute
root credentials into that profile. Local processing needs no AWS credentials.

```powershell
python -m backend.marine_data.platform.pipeline ibtracs `
  "C:\MarineVerseData\raw\ibtracs\ibtracs.ALL.list.v04r01.csv" `
  --source-url "https://www.ncei.noaa.gov/products/international-best-track-archive" `
  --coverage "Global NOAA tropical cyclone archive v04r01; historical/provisional; not live alerts"
```

The adapter validates header and units row; preserves basin `NA`, blank/−9999
missing values, WMO agency, track type, nature and interpolation flags; converts
knots to m/s; keeps mb as numerically equivalent hPa. Longitude values spanning
0..360 are wrapped into −180..180 and original longitude is retained. Wind
averaging periods remain agency-native; there is no undocumented conversion
between 1-, 3- and 10-minute winds. Unavailable WMO wind stays NULL, with no
silent substitution of another agency's measurement.

Optional fresh real-data acquisition (preview by default):

```powershell
python -m backend.marine_data.platform.sources ibtracs
python -m backend.marine_data.platform.sources ibtracs --execute --period ALL
python -m backend.marine_data.platform.refresh ibtracs --execute
```

The downloader uses a new timestamped directory and never overwrites the
validated local file. `--period last3years` is useful for smaller real-data smoke
runs. NOAA source and column definitions:
https://www.ncei.noaa.gov/products/international-best-track-archive
https://www.ncei.noaa.gov/sites/default/files/2025-09/IBTrACS_v04r01_column_documentation.pdf

## Source execution and actual limits

| Dataset | Implementation | Access/coverage limits |
|---|---|---|
| IBTrACS | Streaming v04r01 CSV, fresh download or existing file, all three marts | Historical/provisional tropical cyclone archive, not a live warning feed |
| OSM ports | 72 world tiles at 30°, checkpointed retrieval, cross-tile dedup; unknown country NULL | Port/harbour query subset, volunteered incompleteness; shared Overpass quotas/timeouts; full world retrieval not verified here |
| Open-Meteo | Existing batched retrieval at normalized ports from selected ports release; all three marts | Available OSM port coordinates only; provider quota/usage terms; not a continuous ocean grid |
| Copernicus | Existing bounded retrieval and manifest/NetCDF transformation reused | Auth required; existing India default retained, CLI bounds already configurable; no automatic global high-resolution download |
| AISStream | Existing capture/load retained; optional validated `MARINEVERSE_AIS_BOUNDING_BOXES` | Key required; global subscription does not guarantee offshore receivers; retained capture replay works; historical AIS archive not supplied |
| Coastline / land | WGS84 shapefile ZIP or RFC7946 GeoJSON, geometry validity/bounds checks | Natural Earth is generalized visualization data; GSHHG can use equivalent WGS84 inputs; neither is a navigation chart |
| GEBCO bathymetry | Real local NetCDF `lat/lon/elevation`, units/coordinate checks, per-row processing | Bounded subset only, max 2 million cells; source-positive-upward elevation, not chart datum; no full raster download/regridding |
| Protected zones | Licensed real WGS84 polygon GeoJSON or shapefile ZIP | Acquire data under provider terms; source attributes retained; no licensed dataset fabricated or automatically downloaded |
| IOC sea level | Deliberately deferred | API group approval pending; no calls or placeholder measurements |

For worldwide AIS, explicitly set this local environment value before using the
existing pipeline (the legacy India pipeline/file labels remain for compatibility):

```powershell
$env:MARINEVERSE_AIS_BOUNDING_BOXES='[[[-90,-180],[90,180]]]'
```

Default remains the original India bounding box. Split crossing boxes at the
dateline. Global captures remain bounded by existing duration/event limits and
can be biased samples; do not call them full global vessel coverage.

World OSM plan and explicit execution:

```powershell
python -m backend.marine_data.platform.sources ports
python -m backend.marine_data.platform.refresh ports --execute
python -m backend.marine_data.platform.refresh weather --execute
```

Interrupted ports acquisition resumes `raw/ports-worldwide/pending-30` tiles.
After all tiles succeed, that directory moves to a timestamped completed bundle;
a subsequent refresh starts fresh. Inspect tile timestamps to assess acquisition
skew. Cached successful tiles are not a simultaneous snapshot. HTTP/Overpass
errors abort; valid empty tiles are recorded, not guessed. The default query
covers harbours and industrial ports, not every pier/ferry/marina feature.

Existing retained sources can be published with the same `pipeline` command,
substituting dataset `ports`, `weather`, `ocean`, `ais`, `coastline`, `land`,
`protected_zones` or `bathymetry`, an appropriate file and honest source URL/coverage.
Ocean manifests and sibling files are bundled and checked together. Legacy
transformers still load bounded inputs into memory; only IBTrACS normalization,
Gold generation/deduplication and GEBCO row access are streamed. Do not submit a
whole high-resolution world NetCDF to the existing ocean transformer.

## Remaining operational work

1. Review local-only `feat/aws-s3-deployment` changes before integrating PRs.
2. Run PostGIS tests in a disposable database with frozen migrations applied.
3. Run worldwide OSM refresh within Overpass usage policy, inspect receipt, then
   weather refresh within Open-Meteo limits. Verify provider quotas first.
4. With existing provider credentials, run bounded Copernicus and AIS acquisition
   and publish their retained sources. Choose global ocean sampling/tiles based
   on storage and rate budgets; this MVP does not claim worldwide live grids.
5. Supply licensed protected-zone, GEBCO subsets and historical AIS data as
   available. Route-time alignment, congestion derivation and voyage segmentation
   remain additional engineering scope; these are not implied by cell counts.
6. Renew IAM, validate caller identity locally, preview exact upload scope using
   existing `s3_storage`; upload only to an existing approved bucket after review.
   This work performs no AWS calls/provisioning and never reads root credentials.
7. IOC integration stays last, after API approval.

The repository contains only code, docs and small real source excerpts for tests.
No credentials, `.env` files or bulk raw/processed datasets are committed.
