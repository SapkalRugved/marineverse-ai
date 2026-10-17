\# Marine Data Pipeline Automation



\## Purpose



MarineVerse automatically retrieves and loads near-real-time weather and

ocean-condition snapshots into PostgreSQL/PostGIS.



The local MVP uses Windows Task Scheduler. Pipeline advisory locks prevent

overlapping executions, and the freshness API reports whether stored datasets

are current enough for downstream applications.



\## Automated schedules



| Dataset | Schedule | Retention | Freshness threshold |

|---|---:|---:|---:|

| Weather | Every 15 minutes | 30 days | 30 minutes |

| Ocean | Every 6 hours | 14 days | 9 hours |

| Ports | Manual or monthly refresh | Not automatically deleted | 30 days |



Weather uses Open-Meteo current conditions for selected port locations.



Ocean conditions use Copernicus Marine physics and wave model datasets.



\## Components



\- `backend/marine\_data/automation/runner.py`

&#x20; - Dispatches weather and ocean pipelines.

&#x20; - Uses PostgreSQL advisory locks to prevent overlap.

&#x20; - Returns a nonzero exit code when a pipeline fails.

\- `backend/marine\_data/automation/retention.py`

&#x20; - Evaluates weather and ocean database retention.

&#x20; - Runs in dry-run mode by default.

&#x20; - Requires `--apply` before deleting database rows.

&#x20; - Always protects the newest snapshot.

\- `backend/app/services/freshness.py`

&#x20; - Calculates dataset age and freshness status.

\- `backend/app/api/freshness.py`

&#x20; - Exposes freshness through `GET /api/v1/freshness`.

\- `scripts/automation/run\_marine\_job.ps1`

&#x20; - Executes one scheduled job using the project virtual environment.

&#x20; - Writes timestamped logs under `logs/automation/`.

\- `scripts/automation/register\_windows\_tasks.ps1`

&#x20; - Registers the local Windows schedules.



\## Database authentication



Scheduled jobs cannot prompt for a PostgreSQL password.



The local setup uses the standard PostgreSQL password file:



```text

%APPDATA%\\postgresql\\pgpass.conf

```



Example format:



```text

localhost:5432:marineverse:postgres:<password>

```



The password file is outside the repository and must never be committed.



Copernicus Marine credentials are stored in the current Windows user's

Copernicus configuration directory.



\## Register Windows tasks



Activate the project virtual environment and run:



```powershell

powershell.exe `

&#x20;   -NoProfile `

&#x20;   -ExecutionPolicy Bypass `

&#x20;   -File scripts\\automation\\register\_windows\_tasks.ps1

```



The script registers:



\- `MarineVerse-Weather-ETL`

\- `MarineVerse-Ocean-ETL`

\- `MarineVerse-Retention-DryRun`



The tasks run under the current Windows user while that user is logged in.

Missed executions are started when possible after the computer resumes.



\## Inspect task status



```powershell

Get-ScheduledTask |

&#x20;   Where-Object TaskName -Like "MarineVerse-\*" |

&#x20;   ForEach-Object {

&#x20;       $taskInfo = $\_ | Get-ScheduledTaskInfo



&#x20;       \[PSCustomObject]@{

&#x20;           TaskName = $\_.TaskName

&#x20;           State = $\_.State

&#x20;           LastRunTime = $taskInfo.LastRunTime

&#x20;           NextRunTime = $taskInfo.NextRunTime

&#x20;           LastTaskResult = $taskInfo.LastTaskResult

&#x20;       }

&#x20;   } |

&#x20;   Format-Table -AutoSize

```



A successful execution has `LastTaskResult` equal to `0`.



\## Run jobs manually



Weather:



```powershell

python -m backend.marine\_data.automation.runner weather

```



Ocean:



```powershell

python -m backend.marine\_data.automation.runner ocean

```



Retention dry run:



```powershell

python -m backend.marine\_data.automation.retention

```



Evaluate retention through the PowerShell wrapper:



```powershell

powershell.exe `

&#x20;   -NoProfile `

&#x20;   -ExecutionPolicy Bypass `

&#x20;   -File scripts\\automation\\run\_marine\_job.ps1 `

&#x20;   -Job retention-dry-run

```



\## Retention safety



The scheduled retention task is intentionally dry-run only.



Current database policies are:



\- Weather records older than 30 days become deletion candidates.

\- Ocean records older than 14 days become deletion candidates.

\- The newest snapshot in each table is always protected.



Actual deletion requires the explicit command:



```powershell

python -m backend.marine\_data.automation.retention --apply

```



Review dry-run candidate counts before using `--apply`.



Database retention does not currently delete retained raw JSON or NetCDF

files. Raw-file lifecycle management should be added before cloud deployment.



\## Freshness monitoring



With the API running:



```powershell

Invoke-RestMethod `

&#x20;   "http://127.0.0.1:8000/api/v1/freshness" |

&#x20;   ConvertTo-Json -Depth 6

```



Possible dataset states are:



\- `fresh`

\- `stale`

\- `missing`



The overall status uses the worst dataset state.



\## Logs



Scheduled execution logs are stored in:



```text

logs/automation/

```



The `logs/` directory is ignored by Git.



Inspect the latest weather log:



```powershell

Get-ChildItem logs\\automation\\weather\_\*.log |

&#x20;   Sort-Object LastWriteTime -Descending |

&#x20;   Select-Object -First 1 |

&#x20;   Get-Content

```



Temporary DNS or provider failures return a nonzero task result and are

recorded in the log. The next scheduled interval provides another attempt.



\## Remove local schedules



```powershell

Unregister-ScheduledTask `

&#x20;   -TaskName "MarineVerse-Weather-ETL" `

&#x20;   -Confirm:$false



Unregister-ScheduledTask `

&#x20;   -TaskName "MarineVerse-Ocean-ETL" `

&#x20;   -Confirm:$false



Unregister-ScheduledTask `

&#x20;   -TaskName "MarineVerse-Retention-DryRun" `

&#x20;   -Confirm:$false

```



\## Local MVP limitation



Windows Task Scheduler depends on the development laptop, its network

connection, and the user session. Production deployment should move these

schedules to managed cloud infrastructure with centralized secrets, logs,

alerts, and durable raw-data storage.

