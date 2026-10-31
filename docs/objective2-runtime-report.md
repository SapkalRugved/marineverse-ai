# Objective 2 runtime verification — 31 October 2026

**Status: source-backed file-platform MVP verified in an isolated implementation
workspace; operational deployment and team acceptance remain incomplete.**
Issue #16 remains open. This report does not certify the Windows workstation,
private S3 contents or a continuously available service.

## Real source processing and contracts

| Source | Accepted Silver | Rejected | Duplicates | Gold Objective 1 / 3 / 4 | Coverage actually demonstrated |
| --- | ---: | ---: | ---: | --- | --- |
| NOAA IBTrACS ALL v04r01 | 730,378 | 0 | 0 | 730,378 / 730,378 / 526,838 | Global historical/provisional archive, 1842-10-25 through 2026-10-29 UTC; not live warnings |
| NGA World Port Index | 3,805 | 0 | 2 | 3,805 / 3,805 / 1,833 | Selected ports, terminals and facilities worldwide; not exhaustive or live |
| Open-Meteo current model weather | 10 | 0 | 0 | 10 / 10 / 10 | Ten selected WPI coordinates; valid time 2026-10-31 10:15 UTC, not station observations or worldwide live coverage |
| Natural Earth coastline ZIP | 4,133 | 0 | 0 | 4,133 / 4,133 / 4,133 | Global generalized cartography, not navigational geometry |
| Natural Earth land ZIP | 11 | 0 | 0 | 11 / 11 / 11 | Grouped global multipolygons; count does not represent countries |

The fresh NOAA ALL download was **333,165,979 bytes**. This independently
reproduced the operator-reported counts but cannot establish equality to the
previous Windows file or S3 object without access to their retained receipts
and full remote contents. No source fingerprints or records are published here.

All five current releases passed full Bronze and Silver checksums, every Gold
checksum, actual JSONL counts, per-record lineage, quality accounting and equality
between the mutable catalog and retained immutable release report. An actual
Uvicorn loopback HTTP server served all fifteen dataset/mart combinations;
first-record, last-record and end-of-data requests passed against pinned
releases. The server was temporary and was stopped after verification.

Objective 1 receives GeoJSON features; Objective 3 receives structured evidence;
Objective 4 receives source-backed features or descriptive aggregates. The
Objective 4 values are not trained predictive models or safety classifications.
No consumer module source code or team environment was available, so these are
provider-side contract checks, not end-user acceptance by those teams.

The retained Natural Earth coastline archive has conflicting embedded version
labels (VERSION 5.0.0-pre9 versus README download label 4.1.0); land identifies
5.1.1. Preserve this discrepancy in provenance. The earlier #19 investigation
reported a transient land mismatch; this run's full integrity checks passed.

## Implementation and tests

This branch incorporates the open #19 integrity and API verification work onto
current main, adds the WPI source without replacing OSM, bounds weather refreshes
to ten selected locations by default (configurable 1–100), and hardens publication:

- Retained immutable receipt must agree with the catalog; extra non-object
  Silver rows fail verification even when their checksum has been updated.
- S3 publication pins the verified receipt and refuses changed releases.
- Immutable objects use conditional create to prevent HEAD/PUT overwrite races;
  encryption is explicitly AES256. Stream sizes are checked and bodies closed.
- Preview reports a combined upload/GET byte estimate. Execution stops before
  AWS access if it exceeds the configured budget (default 1 GiB).
- The complete NOAA release preview contains approximately 2.75 GB of files and
  5.49 GB of logical upload/verification transfer, including a new Bronze copy.
  Network retries and monetary charges are not included in that estimate.

The non-database suite passed **239 tests and 22 subtests** locally. An initial
full-suite attempt had 17 database setup errors because no PostgreSQL service
was available; those errors are not described as passing tests. Installing a
local service was not successful in the execution environment. Existing GitHub
Actions applies the unchanged frozen schema to disposable databases and runs
the full suite; the branch extends it to PostgreSQL/PostGIS **16/3.4 and 18/3.6**.
Use the pull request's actual head CI results as the authority for those runs.

No database SQL files or successful FastAPI response envelopes were changed.
Source files, receipts, authentication material and generated marts remain
outside GitHub; only implementation, tests and this aggregate evidence are
committed. Source data are retained with their original attribution.

## Exact remaining access and integration gates

| Gate | Evidence or blocker | Required next execution |
| --- | --- | --- |
| Existing private S3 Bronze integrity | No AWS profile, credentials or AWS connector in this session; empty cloud browser has no console session | Authenticate the existing IAM user, then stream and compare the exact legacy Bronze object to its retained source receipt |
| Private Silver/Gold publication | Local integrity and offline upload previews pass; no AWS execution occurred | Review byte estimate and execute against the existing bucket with the expected IAM identity; retain full-content verification results |
| Retained regional GEBCO ZIP | Not present in attached workspace or accessible file search; Windows filesystem is unavailable | Make the retained ZIP accessible, run bounded preparation, publish and audit; regional sampling must remain labeled regional |
| Ocean and AIS refresh | No retained genuine files or provider account credentials accessible | Run existing Copernicus/AIS capture pipelines within account permissions and quotas, retain real source receipts and audit products |
| Windows PostgreSQL 18/PostGIS | No native desktop, terminal bridge or service endpoint reaches that machine | Verify the existing marineverse database on port 5433 and load source-backed ports/weather/ocean/AIS through existing loaders |
| Deployed FastAPI | Temporary loopback service passed; no deployment host was provided | Start a persistent authorized service against verified data and test database-backed and product endpoints |
| Objectives 1, 3 and 4 acceptance | Consumer repositories/environments unavailable | Run consumers against pinned real releases and retain team acceptance evidence |
| Scheduled operation | Four Windows tasks intentionally disabled | Keep disabled until owner separately authorizes execution/scheduling |
| IOC sea level | Provider group authorization still pending | Integrate last after authorization |

Overpass returned HTTP 406. NGA WPI supplies a genuine directory alternative,
so useful worldwide port data are available without treating the OSM acquisition
as successful. Neither directory data nor historical cyclone coverage proves
continuous worldwide monitoring.

No paid infrastructure, IAM changes, data deletions or schedule re-enabling were
performed. Objective 2 must remain incomplete until the operational gates pass.
