# MarineVerse Marine Data API

## Purpose

The API exposes normalized ports, weather, ocean, and AIS vessel data stored
in PostgreSQL/PostGIS. API requests read previously ingested data and do not
contact external providers directly.

## Data sources

| Dataset | Provider | Data type |
|---|---|---|
| Ports | OpenStreetMap | Relatively static |
| Weather | Open-Meteo | Near-real-time |
| Ocean | Copernicus Marine | Analysis and forecast |
| Vessels | AISStream | Live AIS broadcasts |

## Environment

Create an untracked `.env` file:

~~~text
PGHOST=localhost
PGPORT=5432
PGDATABASE=marineverse
PGUSER=postgres
PGPASSWORD=your-local-password
AISSTREAM_API_KEY=your-local-key
~~~

Never commit `.env` or real credentials.

## Start the API

~~~powershell
python -m uvicorn backend.app.main:app `
    --host 127.0.0.1 `
    --port 8000 `
    --reload
~~~

OpenAPI documentation:

~~~text
http://127.0.0.1:8000/docs
~~~

## Operational endpoints

- `GET /health`: liveness without a database dependency
- `GET /ready`: PostgreSQL readiness
- `GET /api/v1/freshness`: dataset freshness monitoring

## Ports

~~~http
GET /api/v1/ports
~~~

Filters include `port_type`, `name`, geographic bounds, and `limit` from
1 to 500.

~~~powershell
Invoke-RestMethod `
    "http://127.0.0.1:8000/api/v1/ports?port_type=port&limit=5"
~~~

## Weather

~~~http
GET /api/v1/weather
~~~

Filters include source, dataset, forecast status, time range, geographic
bounds, `latest_only`, and `limit`.

~~~powershell
Invoke-RestMethod `
    "http://127.0.0.1:8000/api/v1/weather?source=open-meteo&limit=5"
~~~

## Ocean

~~~http
GET /api/v1/ocean
~~~

Filters include source, dataset, forecast status, time range, depth,
geographic bounds, `latest_only`, `limit`, and `offset`.

~~~powershell
Invoke-RestMethod `
    "http://127.0.0.1:8000/api/v1/ocean?limit=50"
~~~

## Vessels

~~~http
GET /api/v1/vessels
~~~

The endpoint returns one record per vessel with its newest stored position.

Supported filters:

- `mmsi`: nine-digit vessel identity
- `name`: case-insensitive partial name
- `ship_type`
- `source`
- `minimum_latitude`
- `maximum_latitude`
- `minimum_longitude`
- `maximum_longitude`
- `observed_after`: ISO 8601 timestamp
- `limit` from 1 to 500

~~~powershell
Invoke-RestMethod `
    "http://127.0.0.1:8000/api/v1/vessels?source=aisstream&limit=5" |
    ConvertTo-Json -Depth 6
~~~

`latest_position` includes the observation time, coordinates, speed, course,
heading, navigation status, source, and ingestion time.

A vessel without a stored position has `latest_position` set to `null`.
Geographic and `observed_after` filters require a matching latest position.

## Freshness monitoring

~~~http
GET /api/v1/freshness
~~~

~~~powershell
Invoke-RestMethod `
    "http://127.0.0.1:8000/api/v1/freshness" |
    ConvertTo-Json -Depth 6
~~~

Possible states are `fresh`, `stale`, and `missing`.

| Dataset | Maximum age |
|---|---:|
| AIS | 30 minutes |
| Weather | 30 minutes |
| Ocean | 9 hours |
| Ports | 30 days |

AIS age uses the newest live `vessel_positions.observed_at` timestamp.

## Error behavior

- Invalid parameters and reversed ranges return HTTP `422`.
- Temporary database failures return HTTP `503`.
- Empty queries return HTTP `200` with `count` equal to zero.
- Internal database details are not exposed.

## Testing

~~~powershell
python -m unittest discover `
    -s tests `
    -p "test_api_*.py" `
    -v

python -m unittest discover `
    -s tests `
    -p "test_*.py" `
    -v
~~~
