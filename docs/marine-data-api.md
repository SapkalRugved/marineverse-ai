\# MarineVerse Marine Data API



\## Purpose



The Marine Data API provides one HTTP interface for querying normalized

port, weather, and ocean-condition records stored in PostgreSQL/PostGIS.



The API reads data already loaded by the MarineVerse ETL pipelines. It

does not contact OpenStreetMap, Open-Meteo, or Copernicus Marine during

each API request.



\## Data provenance



| Dataset | Provider | Characteristics |

|---|---|---|

| Ports | OpenStreetMap Overpass API | Real, relatively static port data |

| Weather | Open-Meteo | Real near-real-time weather snapshots |

| Ocean | Copernicus Marine | Modelled ocean analysis and forecast data |



The API test fixtures are synthetic and are used only by mocked unit

tests. They are not written to PostgreSQL.



\## Environment



Create a local `.env` file based on `.env.example`.



```text

PGHOST=localhost

PGPORT=5432

PGDATABASE=marineverse

PGUSER=postgres

PGPASSWORD=your-local-password

AISSTREAM\_API\_KEY=

```



Never commit the local `.env` file.



\## Install dependencies



```powershell

python -m venv .venv

.\\.venv\\Scripts\\Activate.ps1

python -m pip install -r requirements.txt

```



\## Start the API



```powershell

python -m uvicorn backend.app.main:app `

&#x20;   --host 127.0.0.1 `

&#x20;   --port 8000 `

&#x20;   --reload

```



Interactive OpenAPI documentation is available at:



```text

http://127.0.0.1:8000/docs

```



\## Operational endpoints



\### Liveness



```http

GET /health

```



This endpoint does not depend on PostgreSQL.



\### Readiness



```http

GET /ready

```



This endpoint verifies that PostgreSQL is available.



\## Ports endpoint



```http

GET /api/v1/ports

```



Supported filters:



\- `port\_type`

\- `name`

\- `minimum\_latitude`

\- `maximum\_latitude`

\- `minimum\_longitude`

\- `maximum\_longitude`

\- `limit` from 1 to 500



Example:



```powershell

Invoke-RestMethod `

&#x20;   "http://127.0.0.1:8000/api/v1/ports?port\_type=port\&limit=5"

```



\## Weather endpoint



```http

GET /api/v1/weather

```



Supported filters:



\- `source`

\- `source\_dataset`

\- `is\_forecast`

\- `start\_time`

\- `end\_time`

\- `minimum\_latitude`

\- `maximum\_latitude`

\- `minimum\_longitude`

\- `maximum\_longitude`

\- `latest\_only`

\- `limit` from 1 to 500



`latest\_only` defaults to `true`. The result therefore contains the

latest matching weather snapshot unless historical mode is requested.



Example:



```powershell

Invoke-RestMethod `

&#x20;   "http://127.0.0.1:8000/api/v1/weather?source=open-meteo\&limit=5"

```



Historical example:



```powershell

Invoke-RestMethod `

&#x20;   "http://127.0.0.1:8000/api/v1/weather?latest\_only=false\&limit=100"

```



\## Ocean endpoint



```http

GET /api/v1/ocean

```



Supported filters:



\- `source`

\- `source\_dataset`

\- `is\_forecast`

\- `start\_time`

\- `end\_time`

\- `minimum\_depth\_m`

\- `maximum\_depth\_m`

\- `minimum\_latitude`

\- `maximum\_latitude`

\- `minimum\_longitude`

\- `maximum\_longitude`

\- `latest\_only`

\- `limit` from 1 to 5000

\- `offset`



The response includes:



\- Eastward and northward current components

\- Calculated current speed and direction

\- Sea-surface temperature

\- Significant wave height

\- Wave direction

\- Wave period

\- Forecast status



Example:



```powershell

Invoke-RestMethod `

&#x20;   "http://127.0.0.1:8000/api/v1/ocean?minimum\_latitude=18.7\&maximum\_latitude=19.1\&minimum\_longitude=72.3\&maximum\_longitude=72.6\&limit=50"

```



Pagination example:



```powershell

Invoke-RestMethod `

&#x20;   "http://127.0.0.1:8000/api/v1/ocean?limit=500\&offset=500"

```



\## Data freshness



The API returns the latest data currently stored in PostgreSQL.

`valid\_time` indicates when a weather or ocean condition is valid, while

`ingested\_at` indicates when MarineVerse loaded it.



Until pipeline scheduling is configured, data is refreshed only when the

corresponding ETL command is run manually.



\## Error behavior



\- Invalid query parameters or reversed ranges return HTTP `422`.

\- Temporary database failures return HTTP `503`.

\- Internal database connection details are not exposed to API clients.



\## Testing



Run API tests:



```powershell

python -m unittest discover `

&#x20;   -s tests `

&#x20;   -p "test\_api\_\*.py" `

&#x20;   -v

```



Run the complete test suite:



```powershell

python -m unittest discover `

&#x20;   -s tests `

&#x20;   -p "test\_\*.py" `

&#x20;   -v

```

