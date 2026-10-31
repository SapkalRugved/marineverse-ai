# Verified MarineVerse data archive restore

This tool restores **only published immutable Bronze/Silver/Gold objects**
and catalog receipts, excluding transient crash/retry files from the handoff ZIP.

It validates every restored dataset against the repository's full source-backed
quality, lineage, counts, SHA-256 and immutable-receipt audit before atomically
promoting the prepared directory. A failed or interrupted validation never
replaces or creates a final data root.

It does not contact AWS, create hosting resources, modify the frozen
PostgreSQL/PostGIS schema, invoke the Windows scheduler, or fabricate marine
data. It cannot prove private S3 publication or deployed API operation.

Run from the repository root with the verified private ZIP available:

```powershell
python -m scripts.operations.restore_verified_archive `
  --archive "MarineVerse_Objective2_Verified_Data_2026-10-31.zip" `
  --destination "C:\\MarineVerseData\\verified-20261031"
```

The destination must **not exist**. This safeguard preserves an existing
developer workstation data root. Configure an instance's
`MARINEVERSE_DATA_DIR` to the verified new location only after deployment
review. No raw data, local hashes or credentials belong in GitHub.

The five published source-backed releases contain global historical/provisional
NOAA IBTrACS; an NGA directory sample of worldwide ports; generalized Natural
Earth coastline/land; and weather model values for ten selected port locations.
This is **not** full worldwide live AIS or complete ocean data.
Retained regional GEBCO and provider-dependent AIS/ocean publications remain
explicit operational blockers. See Issue #16.
