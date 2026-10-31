"""Preview-first publication of a verified local release to a private S3 bucket.

Uses a named AWS profile, never root, never provisions AWS resources, and never
prints credentials, checksums or account IDs. Uploads immutable content before
a final catalog pointer. Remote integrity checking is streaming SHA-256, not ETag.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from backend.marine_data.platform.pipeline import MARTS
from backend.marine_data.platform.verify import verify
from backend.marine_data.storage import resolve_data_root


def release_paths(root: Path, dataset: str) -> tuple[dict, list[tuple[Path, str]]]:
    root = Path(root).resolve()
    integrity = verify(root, dataset)
    if not integrity["verified"]:
        raise ValueError("Local publication must pass integrity checks before S3 upload")
    receipt = json.loads(
        (root / "catalog" / dataset / "current.json").read_text(encoding="utf-8")
    )
    release = receipt["release"]
    bronze = root / "bronze" / dataset / receipt["bronze_sha256"]
    paths = [bronze / entry["name"] for entry in receipt["bronze_files"]]
    silver = root / "silver" / dataset / release
    paths += [silver / n for n in ("records.jsonl", "rejections.jsonl", "report.json")]
    gold = root / "gold" / dataset / release
    paths += [gold / f"{mart}.jsonl" for mart in MARTS]
    result = []
    for path in paths:
        resolved = path.resolve()
        if not resolved.is_relative_to(root) or not path.is_file():
            raise ValueError("Release file missing or outside data root")
        result.append((resolved, resolved.relative_to(root).as_posix()))
    # The pointer is deliberately excluded until all immutable files succeed.
    return receipt, result


def stream_remote_sha256(client, bucket: str, key: str) -> str:
    response = client.get_object(Bucket=bucket, Key=key)
    body = response["Body"]
    hash_value = hashlib.sha256()
    try:
        for chunk in body.iter_chunks(chunk_size=1024 * 1024):
            if chunk:
                hash_value.update(chunk)
    finally:
        body.close()
    return hash_value.hexdigest()


def stream_local_sha256(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def publish(root: Path, dataset: str, bucket: str, *,
            profile="marineverse", region="ap-south-1",
            execute=False, client=None) -> dict:
    if not bucket or not bucket.strip() or "/" in bucket:
        raise ValueError("Explicit existing bucket name required")
    receipt, objects = release_paths(root, dataset)
    summary = {
        "dataset": dataset, "release": receipt["release"],
        "bucket": bucket, "execute": execute,
        "planned_objects": len(objects), "planned_bytes": sum(p.stat().st_size for p, _ in objects),
        "uploaded": 0, "verified": 0, "skipped_existing_verified": 0,
        "catalog_published": False,
    }
    if not execute:
        return summary
    if client is None:
        import boto3
        session = boto3.Session(profile_name=profile, region_name=region)
        sts = session.client("sts")
        arn = sts.get_caller_identity()["Arn"]
        if not arn.endswith(":user/marineverse-data-engineer"):
            raise PermissionError("Refusing publication without expected IAM identity")
        client = session.client("s3")

    # Non-destructive: for an existing object, stream and compare bytes, or fail.
    # For newly uploaded files, round-trip the remote body before final pointer.
    for source, key in objects:
        local_digest = stream_local_sha256(source)
        try:
            metadata = client.head_object(Bucket=bucket, Key=key)
        except client.exceptions.NoSuchKey:
            metadata = None
        except Exception as exc:
            # boto3 commonly returns ClientError for 404, not NoSuchKey.
            if getattr(exc, "response", {}).get("Error", {}).get("Code") not in {"404", "NoSuchKey", "NotFound"}:
                raise
            metadata = None
        if metadata is not None:
            if metadata["ContentLength"] != source.stat().st_size:
                raise ValueError("Existing remote object has wrong size; refusing overwrite")
            if stream_remote_sha256(client, bucket, key) != local_digest:
                raise ValueError("Existing remote object checksum mismatch; refusing overwrite")
            summary["skipped_existing_verified"] += 1
        else:
            client.upload_file(str(source), bucket, key)
            summary["uploaded"] += 1
            if stream_remote_sha256(client, bucket, key) != local_digest:
                raise ValueError("Uploaded remote object integrity mismatch; no catalog published")
        summary["verified"] += 1

    # Last step: publish the receipt after all objects passed round-trip hashing.
    pointer = Path(root).resolve() / "catalog" / dataset / "current.json"
    pointer_key = f"catalog/{dataset}/current.json"
    # Windows JSON paths contain backslashes; normalize only the *S3* receipt.
    remote_receipt = json.loads(pointer.read_text(encoding="utf-8"))
    for mart in MARTS:
        remote_receipt["products"][mart]["path"] = remote_receipt["products"][mart]["path"].replace("\\", "/")
    remote_receipt["publication_backend"] = "private_s3"
    remote_receipt["publication_complete"] = True
    remote_body = (json.dumps(remote_receipt, sort_keys=True, ensure_ascii=False, separators=(",", ":"))+"\n").encode()
    # A pointer is mutable by design, unlike immutable release objects.
    client.put_object(Bucket=bucket, Key=pointer_key, Body=remote_body, ContentType="application/json")
    received = client.get_object(Bucket=bucket, Key=pointer_key)["Body"]
    try:
        if received.read() != remote_body:
            raise ValueError("S3 catalog pointer round-trip mismatch")
    finally:
        received.close()
    summary["catalog_published"] = True
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset")
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--profile", default="marineverse")
    parser.add_argument("--region", default="ap-south-1")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    try:
        result = publish(
            resolve_data_root(args.data_root), args.dataset, args.bucket,
            profile=args.profile, region=args.region, execute=args.execute,
        )
    except (OSError, ValueError, RuntimeError, PermissionError) as exc:
        print(f"Release publication failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
