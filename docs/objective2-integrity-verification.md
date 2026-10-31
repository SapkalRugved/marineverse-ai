# Objective 2 release integrity and consumer checks

Issue #16 remains the operational completion tracker. This procedure is read-only:
no schema migrations, uploads, permission changes, scheduling changes or data deletion.
Keep the four intentionally disabled Windows tasks disabled. IOC remains last,
after API group approval.

## Audit the retained release on Windows

From the repository root with the intended data root explicitly selected:

```powershell
python -m scripts.operations.verify_objective2 ibtracs --data-root "C:\MarineVerseData"
python -m scripts.operations.verify_objective2 coastline --data-root "C:\MarineVerseData"
python -m scripts.operations.verify_objective2 land --data-root "C:\MarineVerseData"
```

The existing `backend.marine_data.platform.verify` command now runs this same
extended audit. Unlike the lightweight `objective2_readiness` presence check, it reads
all Bronze bundle files, Silver and all three Gold marts. It verifies retained
SHA-256 values, bundle identity, quality accounting/gates, Silver/Gold counts,
per-record Gold provenance and basic consumer record structure. It rejects
cross-release paths and symlinks outside a release. A missing or inconsistent
release returns exit code 1 and a privacy-safe failure summary. No fingerprints,
source rows, bucket names or object keys are printed.

The receipt is pinned for the audit. Files must remain immutable while checked;
stop external writers before retrying a failure. Do not edit receipts to make
them pass or delete a failed release. Use a fresh replay through the existing
pipeline if retained data has been damaged. This checks integrity against local
receipts; it cannot authenticate an upstream provider or detect coordinated
replacement of both records and all their checksums.

## Verify the actual API

Start the existing FastAPI app against the same data root, then run:

```powershell
$env:MARINEVERSE_DATA_DIR = "C:\MarineVerseData"
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
# In a second terminal:
python -m scripts.operations.verify_objective2 ibtracs --data-root "C:\MarineVerseData" --api-url http://127.0.0.1:8000
```

Only loopback URLs without embedded credentials are supported by this helper.
It checks each mart's first page, last page and end-of-data response against the
pinned audited release, including totals, pagination and coverage. Each request
is bounded to one record, which can still contain a large land multipolygon.
The existing maximum API offset is 1,000,000; releases exceeding that need a
separate pagination design before this full boundary check can pass. A release
change during verification requires rerunning the check. This is a smoke check,
not acceptance by Objectives 1, 3 and 4 or proof of public/cloud deployment.

## Full S3 content comparison for the existing Bronze object

Use the exact local file that was uploaded and its existing private object key.
Replace placeholders locally; do not paste account details into GitHub.

```powershell
python -m scripts.operations.verify_objective2 ibtracs --data-root "C:\MarineVerseData" --s3-source "C:\MarineVerseData\raw\cyclones\ibtracs\ibtracs.ALL.list.v04r01.csv" --bucket "YOUR_EXISTING_PRIVATE_BUCKET" --key "EXACT_EXISTING_OBJECT_KEY" --profile marineverse --region ap-south-1
```

This explicitly requests STS identity plus one full S3 GetObject download into a
streaming hash, without saving a second copy. It checks the existing
`marineverse-data-engineer` IAM user, rejects root/other identities, compares
full SHA-256 and byte counts, and rechecks that the local source did not change.
Multipart ETags and matching object sizes are insufficient. The stream is
closed even on interrupted reads. Standard existing-bucket GET/transfer charges
may apply; no cloud resources are provisioned. Existing provider terms and
approved account usage still apply. `boto3` must be installed (it is also a
current dependency of the repository's Copernicus client).

This does not renew login, overwrite profiles, upload Silver/Gold, authorize
consumers or change AWS permissions. A green S3 check alone cannot complete the
publication/consumer checklist. CLI success requires every requested check to
pass; a failed local audit cannot be hidden by a successful remote comparison.

## Evidence collected during this implementation

- Full uploaded Natural Earth coastline archive: 4,133 accepted, 0 rejected;
  three marts contain 4,133 records each.
- Full uploaded Natural Earth land archive: 11 accepted multipolygon features,
  0 rejected; three marts contain 11 records each. These are grouped geometries,
  not 11 countries or a measure of coverage completeness.
- Coastline archive `.VERSION.txt`: `5.0.0-pre9`; its embedded README labels
  the download `4.1.0`. Preserve this upstream discrepancy when describing
  provenance. Land archive `.VERSION.txt` and README identify `5.1.1`.
- Full hashes/counts/provenance and API checks are recorded only after they pass.
  One initial land audit detected a checksum mismatch and blocked handoff; a
  fresh immutable replay passed. The transient mismatch was not reproduced;
  its cause is unresolved. Retain and audit workstation outputs before handoff.
- These runs use uploaded archives and a local temporary data root. They do not
  certify the Windows outputs, AWS publication, or live worldwide coverage.
- NOAA source rows in regression tests are the existing retained real excerpt.
  The owner's 730,378-observation run and S3 size verification remain owner-reported
  in this session; no AWS session or full NOAA file is available here.

Natural Earth is generalized cartographic data. GEBCO elevation is not chart-datum
navigational depth. Regional GEBCO, provider refreshes, quota-respecting global
ports acquisition and team acceptance remain separate operational gates.
