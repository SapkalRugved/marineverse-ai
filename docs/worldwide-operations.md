# Running and verifying the platform

Depends on the worldwide platform implementation PR. Nothing in this document
has been registered on the user's Windows machine or deployed to AWS.

## Tests

`python -m pip install -r requirements-dev.txt`, then `python -m pytest -q`.
The Actions workflow creates a disposable PostGIS service, applies the unchanged
001–007 SQL files and runs **all** tests, including the 17 existing integration
checks. It uses no user database or account credentials. CI is PR/push triggered;
there are no scheduled network downloads in Actions.

On a workstation, run the full suite against a **disposable test database**.
The existing integration tests delete their own test rows, so do not point them
at a production database. Supply existing local PostgreSQL environment settings;
no password or `.env` belongs in Git. The host used for implementation had no
PostgreSQL binaries/service, and package installation was unavailable; local
172 passing tests therefore exclude those 17 integration tests. The first remote CI run passed all 189 tests and 22 subtests, including those
17 database checks. See `worldwide-verification.json` for the tested commit;
subsequent heads must pass CI separately.

## Practical Windows scheduling

Keep the existing weather/ocean/AIS/retention tasks. The new scripts create
separate tasks, never replace them, and register only with `-Execute`.
They run as the current interactive user; laptop, network and session availability
still matter. All times below use the computer's local timezone.

Preview a daily NOAA acquisition plus Bronze→Silver→Gold publication:

```powershell
.\scripts\automation\register_platform_task.ps1 -Job ibtracs -At "03:30"
```

After reviewing the preview, registration is explicit:

```powershell
.\scripts\automation\register_platform_task.ps1 -Job ibtracs -At "03:30" -Execute
```

Smoke-run without registering a task:

```powershell
.\scripts\automation\run_platform_job.ps1 -Job ibtracs
.\scripts\automation\run_platform_job.ps1 -Job ibtracs -Execute
```

The first command previews. The second actually downloads a fresh global
archive and publishes products; storage grows because raw/release retention
is intentionally non-destructive. Prefer provider update cadence and your disk
budget over needless repeated full-archive refreshes. NOAA's archive is not a
live warning service. Runtime logs go to ignored `logs/platform`.

Ports acquisition should initially be a supervised manual run because the world
query can hit Overpass limits; weather should follow a successful port release.
Do not schedule both at the same time. `refresh` serializes each source and
publication uses its own OS lock; separate datasets can still run concurrently.
Registration uses IgnoreNew for overlapping scheduled instances, a four-hour
execution limit and StartWhenAvailable. Interrupted jobs leave a failed/partial
release unselected; inspect logs and rerun. An existing task name is not
silently overwritten (registration does not use `-Force`).

For offline replay of the already validated local file, create an **untracked**
`C:\MarineVerseData\platform.jobs.local.json` containing:

```json
[
  {
    "dataset": "ibtracs",
    "source": "C:\\MarineVerseData\\raw\\ibtracs\\ibtracs.ALL.list.v04r01.csv",
    "source_url": "https://www.ncei.noaa.gov/products/international-best-track-archive",
    "coverage": "Global NOAA archive v04r01; historical/provisional, not live alerts"
  }
]
```

```powershell
.\scripts\automation\run_platform_job.ps1 -Job replay -ConfigFile "C:\MarineVerseData\platform.jobs.local.json"
.\scripts\automation\register_platform_task.ps1 -Job replay -ConfigFile "C:\MarineVerseData\platform.jobs.local.json" -At "04:00"
```

Offline replay creates new release directories each time; a one-time replay is
usually sufficient for unchanged source files. Job failures return nonzero;
replay runs independent subsequent jobs and reports each outcome. Relative
paths in JSON are resolved from the repository root. Use absolute paths to avoid
ambiguity. Do not put credentials in job configurations.

## AWS and IOC handoff

Renew the **existing IAM** profile on the local computer using its established
login method. Check caller identity locally before any upload. Never run
`aws configure` with root keys over the IAM profile. No change here reads or
writes AWS credential/profile files, provisions resources or executes S3 uploads.
Use the existing `backend.marine_data.s3_storage` preview with an exact dataset
subdirectory. Do not upload the entire data root (which may contain local job
configuration and unrelated datasets). The existing adapter's `--execute`
remains the explicit upload action, for an already approved bucket.

IOC Sea Level Monitoring remains the final integration, after API group
approval. No task includes it and no synthetic sea-level data exists.
