# MarineVerse AI

MarineVerse AI is a multi-agent digital twin platform for intelligent vessel
journey simulation and maritime decision support.

## Objective 2 — Marine Data Platform

Objective 2 integrates heterogeneous marine data sources into a unified
platform for real-time monitoring and environmental awareness.

The platform ingests, validates, normalizes, stores, and exposes marine data
for the MarineVerse digital twin, AI assistant, risk analysis, forecasting,
and geospatial visualization modules.

## MVP data flow

Marine data sources → ingestion → raw retention → validation and normalization
→ PostgreSQL/PostGIS → API and data-access layer → MarineVerse modules

## Implemented data sources

| Dataset | Source | Mode |
|---|---|---|
| Ports | OpenStreetMap | Static refresh |
| Weather and wind | Open-Meteo | Near-real-time |
| Ocean, waves, and SST | Copernicus Marine | Analysis and forecast |
| Vessel AIS | AISStream | Live WebSocket capture |

## Current capabilities

- PostgreSQL/PostGIS marine data schema
- Idempotent ports ingestion
- Weather and wind ingestion
- Ocean-current, wave, and sea-surface-temperature ingestion
- Live AIS vessel and position ingestion
- Raw data retention
- Transformation and data-quality validation
- Ingestion audit records
- Marine data API
- Dataset freshness monitoring
- Protected Windows pipeline automation

## Runtime data storage

MarineVerse supports configurable raw-data storage for AISStream,
Open-Meteo weather, Copernicus ocean, and OpenStreetMap ports.

Storage directory precedence:

1. Explicit output directory supplied by the caller, where supported.
2. `MARINEVERSE_DATA_DIR` environment variable.
3. Existing repository-relative `data/` directory.

For Windows PowerShell, configure external storage for the current session:

```powershell
$env:MARINEVERSE_DATA_DIR = "C:\MarineVerseData"
```

Or add this line to your local `.env`:

```dotenv
MARINEVERSE_DATA_DIR=C:\MarineVerseData
```

The variable is optional. Leave it completely unset to preserve
the existing repository storage behavior.

Expected external structure:

```text
C:\MarineVerseData\
└── raw\
    ├── ais\
    ├── weather\
    ├── ocean\
    └── ports\
```

The pipelines create required dataset directories when writing.

Copernicus physics NetCDF files, wave NetCDF files, and their JSON
manifest must remain in the same directory because the transformer
resolves NetCDF filenames relative to the manifest.

Existing files are not automatically moved. Configure external storage
only after planning any necessary migration.

Do not commit raw datasets, `.env`, credentials, or generated logs.

This storage configuration does not change PostgreSQL/PostGIS schemas
or existing FastAPI endpoint contracts.


## Documentation

- [Ports ingestion](docs/ports-ingestion.md)
- [Weather ingestion](docs/weather-ingestion.md)
- [Ocean ingestion](docs/ocean-ingestion.md)
- [AIS ingestion](docs/ais-ingestion.md)
- [Pipeline automation](docs/pipeline-automation.md)
- [Marine data API](docs/marine-data-api.md)

## Status

Objective 2 MVP implementation is in progress. The core ports, weather, ocean,
AIS, API, and local automation foundations are operational.

## Worldwide Bronze / Silver / Gold MVP

The additive [worldwide platform](docs/worldwide-platform.md) publishes real
source data into independent Digital Twin, AI Assistant and Decision Support
marts, with immutable Bronze bundles, quality reports and read-only product APIs.
It preserves the existing PostGIS schema, regional ETL commands and API contracts.
See the guide for executable commands and precise source/access limitations.

Read-only [release integrity and consumer verification](docs/objective2-integrity-verification.md) checks retained hashes, counts, lineage and API pagination without changing scheduling or AWS permissions.

See the [runtime evidence and remaining completion gates](docs/objective2-runtime-report.md)
and [NGA World Port Index alternative](docs/wpi-ports.md). Weather refresh defaults
to 10 selected port coordinates to bound provider use; it does not claim global
live observations. CI exercises unchanged SQL on PostGIS 16/3.4 and 18/3.6.
