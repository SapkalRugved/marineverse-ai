# Marine Data Pipeline Automation

## Purpose

MarineVerse automatically retrieves and loads near-real-time weather, ocean,
and AIS vessel data into PostgreSQL/PostGIS.

The local MVP uses Windows Task Scheduler. PostgreSQL advisory locks prevent
overlapping pipeline executions, while timestamped logs and `ingestion_runs`
provide operational evidence.

## Automated schedules

| Dataset | Schedule | Retention | Freshness threshold |
|---|---:|---:|---:|
| AIS | Every 10 minutes | Not automatically deleted | 30 minutes |
| Weather | Every 15 minutes | 30 days | 30 minutes |
| Ocean | Every 6 hours | 14 days | 9 hours |
| Ports | Manual or monthly | Not automatically deleted | 30 days |

AIS uses a five-minute live AISStream capture during each scheduled execution.

Weather uses Open-Meteo current conditions for selected port locations.

Ocean conditions use Copernicus Marine physics and wave model datasets.

## Components

- `backend/marine_data/automation/runner.py`
  - Dispatches AIS, weather, and ocean pipelines.
  - Uses PostgreSQL advisory locks to prevent overlap.
  - Returns a nonzero exit code when a pipeline fails.
- `backend/marine_data/automation/retention.py`
  - Evaluates weather and ocean database retention.
  - Runs in dry-run mode by default.
  - Requires `--apply` before deleting rows.
  - Always protects the newest snapshot.
- `backend/app/services/freshness.py`
  - Calculates dataset age and freshness status.
- `backend/app/api/freshness.py`
  - Exposes freshness through `GET /api/v1/freshness`.
- `scripts/automation/run_marine_job.ps1`
  - Executes scheduled jobs with the project virtual environment.
  - Writes timestamped logs under `logs/automation/`.
- `scripts/automation/register_windows_tasks.ps1`
  - Registers local Windows schedules.

## Pipeline locks

| Pipeline | Advisory lock |
|---|---:|
| Weather | `17001` |
| Ocean | `17002` |
| AIS | `17003` |

A scheduled execution exits successfully without starting a second pipeline
when its lock is already held.

## Database authentication

Scheduled jobs cannot prompt for a PostgreSQL password.

The local setup uses the standard PostgreSQL password file:

~~~text
%APPDATA%\postgresql\pgpass.conf
~~~

Example:

~~~text
localhost:5432:marineverse:postgres:<password>
~~~

The password file is outside the repository and must never be committed.

## Provider authentication

Copernicus Marine credentials are stored outside the repository in the current
Windows user's Copernicus configuration.

The AISStream key is stored in the untracked project `.env` file:

~~~text
AISSTREAM_API_KEY=<your-api-key>
~~~

Never commit the real API key.

## Register Windows tasks

Run:

~~~powershell
powershell.exe `
    -NoProfile `
    -ExecutionPolicy Bypass `
    -File scripts\automation\register_windows_tasks.ps1
~~~

The script registers:

- `MarineVerse-AIS-ETL`
- `MarineVerse-Weather-ETL`
- `MarineVerse-Ocean-ETL`
- `MarineVerse-Retention-DryRun`

The tasks run as the current Windows user while that user is logged in.
Missed executions are started when possible after the computer resumes.

## Inspect task status

~~~powershell
Get-ScheduledTask |
    Where-Object TaskName -Like "MarineVerse-*" |
    ForEach-Object {
        $taskInfo = $_ | Get-ScheduledTaskInfo

        [PSCustomObject]@{
            TaskName = $_.TaskName
            State = $_.State
            LastRunTime = $taskInfo.LastRunTime
            NextRunTime = $taskInfo.NextRunTime
            LastTaskResult = $taskInfo.LastTaskResult
        }
    } |
    Format-Table -AutoSize
~~~

Important task result values:

- `0`: the last execution completed successfully.
- `267009` (`0x41301`): the task is currently running.
- `267011` (`0x41303`): the task has not run yet.

## Run jobs manually

AIS:

~~~powershell
python -m backend.marine_data.automation.runner ais
~~~

Weather:

~~~powershell
python -m backend.marine_data.automation.runner weather
~~~

Ocean:

~~~powershell
python -m backend.marine_data.automation.runner ocean
~~~

Retention dry run:

~~~powershell
python -m backend.marine_data.automation.retention
~~~

Evaluate retention through the wrapper:

~~~powershell
powershell.exe `
    -NoProfile `
    -ExecutionPolicy Bypass `
    -File scripts\automation\run_marine_job.ps1 `
    -Job retention-dry-run
~~~

## Retention safety

The scheduled retention task is intentionally dry-run only.

Current policies are:

- Weather records older than 30 days become deletion candidates.
- Ocean records older than 14 days become deletion candidates.
- The newest snapshot in each table is always protected.
- AIS vessel positions are not currently deleted automatically.

Actual weather and ocean deletion requires:

~~~powershell
python -m backend.marine_data.automation.retention --apply
~~~

Review dry-run candidate counts before using `--apply`.

Database retention does not delete retained raw JSON or NetCDF files. Raw-file
lifecycle management should be added before production deployment.

## Freshness monitoring

With the API running:

~~~powershell
Invoke-RestMethod `
    "http://127.0.0.1:8000/api/v1/freshness" |
    ConvertTo-Json -Depth 6
~~~

Possible dataset states are:

- `fresh`
- `stale`
- `missing`

The freshness endpoint includes AIS using the newest `vessel_positions.observed_at`
timestamp. AIS is fresh when that position is no more than 30 minutes old.

## Logs

Scheduled logs are stored in:

~~~text
logs/automation/
~~~

The directory is ignored by Git.

Inspect the latest AIS log:

~~~powershell
Get-ChildItem logs\automation\ais_*.log |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1 |
    Get-Content
~~~

Inspect the latest weather log:

~~~powershell
Get-ChildItem logs\automation\weather_*.log |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1 |
    Get-Content
~~~

Temporary network or provider failures return a nonzero result and are
recorded in the log. The next interval provides another attempt.

A confirmed AIS subscription with no vessel broadcasts is a successful no-op,
not a pipeline failure.

## Remove local schedules

~~~powershell
Unregister-ScheduledTask `
    -TaskName "MarineVerse-AIS-ETL" `
    -Confirm:$false

Unregister-ScheduledTask `
    -TaskName "MarineVerse-Weather-ETL" `
    -Confirm:$false

Unregister-ScheduledTask `
    -TaskName "MarineVerse-Ocean-ETL" `
    -Confirm:$false

Unregister-ScheduledTask `
    -TaskName "MarineVerse-Retention-DryRun" `
    -Confirm:$false
~~~

## Local MVP limitation

Windows Task Scheduler depends on the development laptop, network connection,
PostgreSQL service, and interactive user session.

Production deployment should move schedules to managed infrastructure with
centralized secrets, logs, alerts, and durable raw-data storage.
