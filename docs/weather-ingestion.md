\# Open-Meteo Current Weather Ingestion



\## Purpose



This pipeline retrieves near-real-time weather conditions for Indian port

locations and stores normalized time-series records in PostgreSQL/PostGIS.



The values are model-based current conditions from Open-Meteo, not direct

measurements from physical weather stations or ocean buoys.



\## Data scope



Port locations are selected dynamically from the `ports` table using:



\- Source: `openstreetmap`

\- Port type: `port`

\- Non-null latitude and longitude



The verified dataset currently contains 61 monitoring locations.



\## Source



\- Provider: Open-Meteo

\- API endpoint: `https://api.open-meteo.com/v1/forecast`

\- Source value: `open-meteo`

\- Dataset value: `best\_match\_current`

\- Pipeline value: `weather\_open\_meteo\_ports`

\- Timezone: UTC

\- Batch size: 10 locations



Temporary HTTP failures, including status codes 429 and 500–504, are retried

automatically.



\## Field mapping



| Open-Meteo field | Database column | Unit |

|---|---|---|

| `current.time` | `valid\_time` | UTC |

| Requested latitude | `latitude` | Degrees |

| Requested longitude | `longitude` | Degrees |

| `temperature\_2m` | `air\_temperature\_c` | °C |

| `pressure\_msl` | `pressure\_hpa` | hPa |

| `precipitation` | `precipitation\_mm` | mm |

| `wind\_speed\_10m` | `wind\_speed\_mps` | m/s |

| `wind\_direction\_10m` | `wind\_direction\_deg` | Degrees |

| `wind\_gusts\_10m` | `wind\_gust\_mps` | m/s |



`is\_forecast` is `false` because this pipeline requests the API's current

conditions rather than its hourly forecast series.



\## Pipeline



1\. Read OSM port coordinates from PostgreSQL.

2\. Request current conditions from Open-Meteo in batches.

3\. Retain the complete raw JSON response locally.

4\. Validate timestamps, units, coordinates, and numeric ranges.

5\. Normalize records into the frozen weather schema.

6\. Insert or update records in `weather\_conditions`.

7\. Create a success or failure record in `ingestion\_runs`.



\## Run the complete ETL



From the repository root with the virtual environment active:



```powershell

python -m backend.marine\_data.weather.run\_open\_meteo\_weather\_pipeline

```



The command performs retrieval, raw retention, transformation, loading, and

audit logging with one PostgreSQL password prompt.



\## Component commands



Retrieve raw data only:



```powershell

python -m backend.marine\_data.weather.retrieve\_open\_meteo\_weather

```



Transform a retained file without loading:



```powershell

python -m backend.marine\_data.weather.transform\_open\_meteo\_weather `

&#x20;   data\\raw\\weather\\<raw-file-name>.json

```



Load a retained file:



```powershell

python -m backend.marine\_data.weather.load\_open\_meteo\_weather `

&#x20;   data\\raw\\weather\\<raw-file-name>.json

```



\## Raw-data retention



Raw files are written under `data/raw/weather/` with UTC timestamps. Downloaded

JSON files are excluded from Git, while `.gitkeep` preserves the directory.



\## Time-series and idempotency



A weather condition is identified by:



\- Source

\- Source dataset

\- Valid time

\- Latitude

\- Longitude

\- Forecast status



Repeating the same valid-time snapshot updates existing records without

creating duplicates. A later valid time creates another set of records,

building weather history.



The frozen table has no unique constraint for this identity. Idempotency is

therefore enforced by loader SQL. Concurrent executions should be prevented

when scheduling this pipeline.



\## Audit logging



Every execution records:



\- Start and completion timestamps

\- Running, success, or failed status

\- Records read

\- Records written

\- Error message when applicable



The verified executions read and processed 61 records successfully.



\## Tests



Run the complete suite:



```powershell

python -m unittest discover -s tests -p "test\_\*.py" -v

```



The verified suite contains 36 tests covering ports, ingestion auditing,

weather transformation, PostGIS loading, stable IDs, and idempotency.



\## Limitations



\- Current conditions are numerical weather-model output, not sensor readings.

\- OpenStreetMap port classifications determine the monitored locations.

\- Provider terms and usage limits must be reviewed before production use.

\- Scheduling and cloud deployment will be added after the local pipeline is

&#x20; merged and the deployment database is selected.
