# AISStream Live Vessel Data Ingestion

## Purpose

This pipeline captures near-real-time AIS vessel broadcasts for the configured
Indian marine region, retains the raw WebSocket events, validates and
normalizes supported messages, and loads vessel and position data into
PostgreSQL/PostGIS.

It provides:

- Vessel identity and static details when available
- Position timestamps
- Latitude and longitude
- PostGIS geography points using SRID 4326
- Speed converted to metres per second
- Course and heading in degrees
- Navigation status
- Audited ingestion outcomes

## Data source

Source identifier:

~~~text
aisstream
~~~

Provider:

~~~text
AISStream
~~~

AISStream delivers live messages through a WebSocket subscription. Message
availability depends on vessel activity and provider coverage. A successful
capture window can contain no vessel broadcasts.

## Authentication

Create a local `.env` file from `.env.example` and configure:

~~~text
AISSTREAM_API_KEY=<your-api-key>
~~~

The real API key must never be committed to Git. The pipeline loads `.env`
from the project root, including scheduled executions.

## Complete live pipeline

Run the default five-minute capture:

~~~powershell
python -m backend.marine_data.ais.run_aisstream_pipeline
~~~

Run a shorter bounded capture:

~~~powershell
python -m backend.marine_data.ais.run_aisstream_pipeline `
    --duration-seconds 120 `
    --max-events 250
~~~

The complete pipeline performs:

1. WebSocket subscription
2. Raw-event retention
3. Transformation and validation
4. Vessel upserts
5. Position insertion
6. PostGIS location creation
7. Ingestion auditing

## Raw-data retention

Raw captures are stored under:

~~~text
data/raw/ais/
~~~

Filenames follow this pattern:

~~~text
aisstream_india_probe_<UTC timestamp>.json
~~~

Captured JSON files are ignored by Git. Only the directory placeholder is
tracked.

## Individual pipeline stages

Capture a bounded live sample:

~~~powershell
python -m backend.marine_data.ais.probe_aisstream `
    --duration-seconds 120 `
    --max-events 250
~~~

Select the latest retained capture:

~~~powershell
$aisCapture = Get-ChildItem `
    data\raw\ais\aisstream_india_probe_*.json |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
~~~

Transform and inspect it:

~~~powershell
python -m backend.marine_data.ais.transform_aisstream `
    "$($aisCapture.FullName)"
~~~

Transform and load it:

~~~powershell
python -m backend.marine_data.ais.load_aisstream_capture `
    "$($aisCapture.FullName)"
~~~

## Transformation and validation

The transformer:

- Ignores subscription-confirmation control events
- Validates supported AIS messages
- Normalizes MMSI and available vessel details
- Validates coordinates
- Normalizes timestamps
- Converts speed to metres per second
- Normalizes course, heading, and navigation status
- Removes duplicate positions within a capture
- Reports rejected events

## Database loading

Vessel data is loaded into `vessels`. Position data is loaded into
`vessel_positions`.

The loader:

- Upserts vessels using their AIS identity
- Links positions to vessels
- Creates PostGIS geography points
- Prevents replayed positions from being inserted again
- Uses one database transaction per load

## Ingestion auditing

Executions write to `ingestion_runs` using:

~~~text
pipeline = aisstream_india
source = aisstream
~~~

`records_read` excludes subscription-confirmation events.
`records_written` counts processed vessel rows and newly inserted positions.

A confirmed quiet capture is a successful no-op with zero records read and
written.

## Automation

The protected automation command is:

~~~powershell
python -m backend.marine_data.automation.runner ais
~~~

The Windows task is:

~~~text
MarineVerse-AIS-ETL
~~~

It runs every 10 minutes. Each default capture lasts at most five minutes.
PostgreSQL advisory lock `17003` prevents overlap.

Logs are stored under:

~~~text
logs/automation/
~~~

## Tests

Run AIS tests:

~~~powershell
python -m unittest discover `
    -s tests `
    -p "test_ais*.py" `
    -v
~~~

Run the complete suite:

~~~powershell
python -m unittest discover `
    -s tests `
    -p "test_*.py" `
    -v
~~~

## Verified behavior

Verified executions demonstrated:

- Successful live WebSocket subscription
- Raw JSON retention
- Successful quiet-window handling
- Vessel and position loading
- Replay-safe position insertion
- Valid SRID 4326 locations
- Zero coordinate mismatches
- Recurring Windows Task Scheduler execution
- Real vessel observations in Indian waters

## Local MVP limitations

AIS availability depends on provider coverage and vessel activity. Local
automation also depends on the development laptop, network connection,
PostgreSQL service, and an interactive Windows user session.

Production deployment should use managed scheduling, secret storage,
monitoring, and durable raw-event storage.
