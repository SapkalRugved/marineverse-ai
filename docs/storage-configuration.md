
# MarineVerse Runtime Storage Contract v1

## Scope

Applies to existing AISStream, Open-Meteo, Copernicus Marine,
and OpenStreetMap raw-data retrieval.

## Precedence

1. Explicit output directory where supported.
2. MARINEVERSE_DATA_DIR.
3. Repository-relative data/ directory.

An explicit output directory means the final dataset directory.
The shared storage resolver's explicit_root parameter instead
means the parent data root.

## Compatibility

- Existing filenames and raw JSON structures are preserved.
- Existing PostgreSQL/PostGIS schemas remain unchanged.
- Existing FastAPI response contracts remain unchanged.
- Copernicus NetCDF files and manifest remain colocated.
- Existing datasets are not automatically migrated.
- External storage is optional during local development.

## Operational safeguards

- Keep secrets and runtime datasets outside Git.
- Do not delete existing raw datasets during migration.
- Confirm disk capacity before large downloads.
- Maintain the frozen 50 GB stop-and-review threshold:
  30 GB retained, 15 GB temporary, 5 GB safety reserve.
- Require an approved migration plan before moving existing files.
- Verify backup restoration before relying on backups.
- Use checksum manifests for future source-data migration workflows.

## Verification

Run:

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
git diff --check
```

Expected baseline after ports integration: 155 tests.

## Current limitations

- External storage changes apply to future writes.
- Existing raw files remain at their original locations.
- The broader processed-data, backup, log and migration lifecycle
  is not yet implemented.
- Cloud object storage is not implemented by this configuration.
- Direct `.env` loading is not yet verified for every entry point.
```
