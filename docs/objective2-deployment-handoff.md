# Objective 2: private deployment handoff

The repository contains a worldwide-capable Bronze/Silver/three-Gold **MVP**, but local AWS accounts, source-provider credentials and file locations are not accessible through GitHub. Green CI validates the code; it does not prove continuous worldwide marine observations.

## Privacy-first status check (PowerShell, repository root)

On the latest `main` checkout:

```powershell
python -m scripts.operations.objective2_readiness
python -m scripts.operations.objective2_readiness --check-aws
```

By default, the script performs **read-only local checks**. With `--check-aws`, it runs only AWS STS GetCallerIdentity, checks that the expected named IAM user is active, and prints **no AWS account number, full ARN, authorization code or secret**. It does **not** fix logins, upload files or provision anything. The local data-root can be set with `MARINEVERSE_DATA_DIR` or `--data-root`. Existing `.env` values aren't automatically sourced by the readiness script, so set the environment variable explicitly when needed.

It reports whether each local source file exists and whether all three Gold product files are present for each dataset's latest catalog receipt. A local product receipt **does not prove the file is deployed to AWS**, complete worldwide coverage, or consumer authorization.

For full file integrity, S3 full-content comparison and bounded API checks, see
[release verification](objective2-integrity-verification.md). Presence checks alone
are insufficient. Keep the four intentionally disabled Windows tasks disabled.

## Completion gates

1. Reconcile the owner's unpublished local branch before pulling; **do not** reset, force-clean, overwrite local modifications or commit downloaded data. Verify locally with `git status` and `git branch --show-current`.
2. Run offline retained-file ingestion, then confirm quality report and three independent Gold products for real NOAA and GEBCO data. GEBCO source is regional and requires geographic tiling for worldwide operations.
3. Renew the **IAM** CLI session through the owner's browser/MFA; if AWS asks to overwrite the IAM profile with root, answer **no**. Never post login codes or AWS account identifiers.
4. Upload only explicit approved Bronze/Silver/Gold paths to the existing private bucket, with verified file integrity and dataset/coverage metadata. Confirm provider redistribution terms.
5. Verify available worldwide OSM ports in a quota-respecting process; previous HTTP 406 means worldwide port completion remains unverified.
6. Validate actual time-bounded, worldwide-provider AIS/weather/ocean observations. Missing coverage must be reported, never invented.
7. Register or deploy scheduling only with owner's approval; verify 2 scheduled executions and a failure alert. Cost controls must be reviewed before cloud compute.
8. Exercise all three Gold data marts through existing FastAPI endpoints with the other Objective teams and record tested API contracts.
9. IOC Sea Level Monitoring is the **last source**, when gauges_API access is approved.

Record evidence and then close Issue #16. Do not mark items complete based only on the presence of code or tests.

## Public repository safety

Keep `.env`, credentials, secrets, API keys, auth codes, raw files and generated data outside Git. The optional tracked-file hygiene CI guard detects several common secret formats and large committed files. It is **not** comprehensive secret detection and **does not scan Git history**. GitHub secret scanning and push protection (where available) and credential rotation are separate security controls. If a real AWS credential or login token was disclosed, invalidate it promptly; file SHA-256 checksums are non-secret fingerprints and cannot authorize AWS access.
