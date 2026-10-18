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
