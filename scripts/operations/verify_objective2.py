"""Read-only integrity audit; optional loopback API and explicit S3 GET check."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

from backend.marine_data.platform.adapters import DATASETS
from backend.marine_data.platform.pipeline import MARTS
from backend.marine_data.platform.verify import audit_release, verify_s3_file
from backend.marine_data.storage import resolve_data_root


def check_api(client, base_url, audit):
    """Check a pinned release and first/last pages for each consumer contract.

    Full file integrity is the audit's responsibility; this is a bounded HTTP
    smoke check, not a substitute for Objective team acceptance.
    """
    result = {"verified": False, "marts": {}}
    if not audit.get("verified"):
        return result
    try:
        for mart in MARTS:
            total = audit["gold_counts"][mart]
            for offset in sorted({0, max(0, total - 1), total}):
                response = client.get(f"{base_url}/api/v1/products/{audit['dataset']}/{mart}",
                                      params={"limit": 1, "offset": offset})
                response.raise_for_status()
                page = response.json()
                expected = int(offset < total)
                if (page["dataset"] != audit["dataset"] or page["mart"] != mart
                        or page["release"] != audit["release"] or page["total"] != total
                        or page["offset"] != offset or page["count"] != expected
                        or len(page["records"]) != expected
                        or page["coverage"] != audit["coverage"]
                        or page["next_offset"] != (offset + expected if offset + expected < total else None)):
                    raise ValueError("API contract mismatch")
            result["marts"][mart] = True
        result["verified"] = True
    except Exception:
        # Network errors may include URLs/credentials. Keep operational output private.
        result["problem"] = "API unavailable, changed during verification or contract mismatch"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", choices=DATASETS)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--api-url", help="Optional loopback FastAPI base URL")
    parser.add_argument("--s3-source", type=Path, help="Explicit local file to compare using a full S3 GET")
    parser.add_argument("--bucket")
    parser.add_argument("--key")
    parser.add_argument("--profile", default="marineverse")
    parser.add_argument("--region", default="ap-south-1")
    args = parser.parse_args()
    if args.api_url:
        url = urlsplit(args.api_url)
        if (url.scheme not in {"http", "https"} or url.hostname not in {"localhost", "127.0.0.1", "::1"}
                or url.username or url.password or url.path not in {"", "/"} or url.query or url.fragment):
            parser.error("API verification requires a loopback base URL without credentials")
    if any((args.s3_source, args.bucket, args.key)) and not all((args.s3_source, args.bucket, args.key)):
        parser.error("S3 verification requires --s3-source, --bucket and --key together")
    audit = audit_release(resolve_data_root(args.data_root), args.dataset)
    report = {"local_release": audit}
    if args.api_url:
        import httpx2
        with httpx2.Client(timeout=30, follow_redirects=False, trust_env=False) as client:
            report["api"] = check_api(client, args.api_url.rstrip("/"), audit)
    if args.s3_source:
        try:
            import boto3
            session = boto3.Session(profile_name=args.profile, region_name=args.region)
            arn = session.client("sts").get_caller_identity()["Arn"]
            if not arn.endswith(":user/marineverse-data-engineer"):
                raise ValueError("Expected IAM user required")
            report["s3"] = verify_s3_file(args.s3_source, args.bucket, args.key, session.client("s3"))
        except Exception:
            report["s3"] = {"verified": False, "problem": "S3 verification failed; check local IAM session, file and object access"}
    print(json.dumps(report, indent=2))
    return 0 if all(item.get("verified") for item in report.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
