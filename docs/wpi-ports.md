# Genuine worldwide port directory fallback

Overpass returned HTTP 406 in the implementation environment. The NGA public
World Port Index CSV was reachable from its official publication endpoint.
This is an additive source for the existing `ports` dataset; existing OSM
commands, database columns and API response envelopes remain unchanged.

NGA reference: https://msi.nga.mil/Publications/WPI

Download at most 20 MiB with one bounded provider request:

```powershell
python -m backend.marine_data.platform.sources ports-wpi
python -m backend.marine_data.platform.sources ports-wpi --execute --data-root C:\MarineVerseData
```

The second command prints the new retained CSV path. Publish that exact path:

```powershell
python -m backend.marine_data.platform.pipeline ports "PATH_PRINTED_ABOVE" --data-root C:\MarineVerseData --source-url "https://msi.nga.mil/api/publications/download?key=16920959/SFH00000/UpdatedPub150.csv&type=view" --coverage "NGA World Port Index snapshot; selected worldwide ports and facilities, not exhaustive or live"
```

The adapter recognizes only a CSV with the required WPI columns. It validates
finite geographic coordinates, positive integral WPI identifiers and text
lengths compatible with the frozen ports table. Source is `nga-world-port-index`,
and `source_id` is the WPI number, including normalization of CSV values such as
`7950.0` to `7950`. Records are never relabeled as OSM. Country labels are retained
as supplied by NGA; no ISO code conversion is inferred. `updated_at` identifies
snapshot ingestion; the source does not provide a verified update time per port.
Gold records carry those interpretation limits explicitly. The WPI directory
includes terminals and shipping facilities under the broad `port` category.

The 2026-10-31 download contained 3,807 rows and two repeated WPI identifiers.
The existing first-record deduplication contract retained 3,805 identities,
with zero rejected rows. No assertion of exhaustive worldwide port coverage
or navigational safety follows from this directory.

Weather can then use the published port release with source lineage intact:

```powershell
python -m backend.marine_data.platform.refresh weather --execute --data-root C:\MarineVerseData --max-weather-locations 10
```

The default is 10; the allowed range is 1–100, using batches of at most 10.
Only selected coordinates are covered. Existing tasks remain disabled unless
the owner separately authorizes enabling them. This command publishes file
marts; it does not load the workstation database or deploy a server.
