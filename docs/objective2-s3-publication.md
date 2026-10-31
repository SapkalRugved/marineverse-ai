# Objective 2: private S3 release publication

This publishes **existing verified local** Bronze/Silver/Gold releases to
the pre-existing private bucket. It does not provision AWS resources or
enable Windows scheduled jobs. No secrets or raw data are committed to GitHub.

## Safety gates

- Requires a locally verified source-backed dataset and three Gold marts.
- Requires the preconfigured named IAM user on execute; rejects root identity.
- Preview-by-default without AWS calls.
- Copies only files in the current immutable release; never walks all of `data/`.
- Existing immutable S3 objects must match *both* size and a full streamed
  SHA-256 comparison; otherwise publication aborts rather than overwrites.
- Uploads missing immutable objects and verifies their remote bytes via S3 GET.
- Publishes the mutable `catalog/<dataset>/current.json` only after all of
  those validations succeed.
- Does not print source hashes, credentials, account IDs or records.
- Does not infer or claim worldwide live coverage.
- Remote S3 pointer is a **file artifact catalog**, not a hosted FastAPI
  endpoint or a database. Objective 1/3/4 consumers still require explicit
  storage access or an API server.

## Offline preview

```powershell
python -m backend.marine_data.platform.s3_release ibtracs --bucket marineverse-ai-data-lake-apsit
```

The command returns object count and bytes without accessing AWS.

## Authorized execution

Requires currently authenticated IAM-user profile `marineverse`:

```powershell
python -m backend.marine_data.platform.s3_release ibtracs --bucket marineverse-ai-data-lake-apsit --execute
```

The owner should review S3 transfer cost and storage budget before execution.
Verification GET downloads source bytes from the same S3 region; network/data
transfer charges may apply depending on location. This can transfer several
gigabytes for large Gold releases. Do not run from CI or an automated schedule.

The existing direct `bronze/cyclones/ibtracs/ibtracs.ALL.list.v04r01.csv`
is a **different legacy S3 key** from the new content-addressed
`bronze/ibtracs/<bundle>/...` objects. Publication does not delete or
overwrite that existing file; it may store another copy. This is intentional
until a reviewed lifecycle/retention strategy exists.

After success, the S3 artifact catalog is published. **It does not establish
live service availability**. Global bathymetry and provider-limited AIS/ocean
coverage remain separate tasks; IOC remains last.
