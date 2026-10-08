\# OSM Ports Ingestion



\## Purpose



This pipeline retrieves port-related reference data for India from

OpenStreetMap, validates and normalizes the records, and loads them into

PostgreSQL/PostGIS.



OSM port data is reference data, not real-time vessel or ocean data.



\## Pipeline



1\. Retrieve OSM elements through the Overpass API.

2\. Retain the raw JSON response under `data/raw/ports/`.

3\. Transform nodes, ways, and relations into a common port structure.

4\. Reject records with missing names or invalid coordinates.

5\. Load valid records into the `ports` PostGIS table.

6\. Record the execution in `ingestion\_runs`.



\## Data source



\- Provider: OpenStreetMap

\- API: Overpass API

\- Geographic scope: India

\- Source identifier: `openstreetmap`

\- Pipeline identifier: `ports\_osm\_india`



The query includes ports, harbours, ferry terminals, fishing harbours,

marinas, piers, harbour facilities, and harbour basins.



\## Environment



Create and activate a virtual environment:



```powershell

python -m venv .venv

.\\.venv\\Scripts\\Activate.ps1

python -m pip install -r requirements.txt

