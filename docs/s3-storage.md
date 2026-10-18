
# MarineVerse S3 Storage Contract v1

## Purpose

Provide optional S3 uploads for raw marine datasets without
changing existing local ingestion pipelines.

## Local storage

MARINEVERSE_DATA_DIR controls the local data root.

Existing AIS, weather, ocean and ports pipelines continue
writing to their existing configured local directories.

## AWS configuration

- AWS_REGION: AWS region, proposed default ap-south-1
- MARINEVERSE_S3_BUCKET: destination bucket name

No AWS access keys are stored in source code.

## Upload contract

Local relative paths become S3 object keys.

Example:

data/raw/ocean/manifest.json
  -> s3://<bucket>/raw/ocean/manifest.json

data/raw/ocean/currents.nc
  -> s3://<bucket>/raw/ocean/currents.nc

Related files retain their relative directory structure.

## Dry-run

Preview files without AWS access:

python -m backend.marine_data.s3_storage .\data\raw\ocean

The command defaults to dry-run.

## Real uploads

Real uploads require all of the following:

1. Explicit AWS resource and cost approval.
2. An existing authorized S3 bucket.
3. Appropriate AWS credentials and IAM permissions.
4. Installed boto3 dependency.
5. Explicit --execute flag.

Do not use --execute during local staging preparation.

## Limitations

- No automatic synchronization.
- No upload checksums or remote integrity verification yet.
- No retry/recovery orchestration.
- No download/restore implementation.
- No lifecycle or backup policy.
- No cloud database migration.

## Compatibility

No changes to existing database schemas, FastAPI contracts,
or raw marine data formats.
