"""Read-only release integrity checks. No downloads, writes or database access."""

import hashlib
import json
import re
from pathlib import Path

from backend.marine_data.platform.adapters import DATASETS
from backend.marine_data.platform.pipeline import MARTS, digest, dumps


def confined(root, relative, directory):
    """Reject absolute paths, traversal and symlinks outside the expected area."""
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise ValueError("Invalid product path")
    path = (root / relative.replace("\\", "/")).resolve()
    if not path.is_relative_to((root / directory).resolve()):
        raise ValueError("Path outside release directory")
    return path


def load_receipt(root, dataset):
    root = Path(root).resolve()
    if dataset not in DATASETS:
        raise ValueError("Unknown dataset")
    receipt = json.loads((root / "catalog" / dataset / "current.json").read_text(encoding="utf-8"))
    if not isinstance(receipt, dict):
        raise ValueError("Invalid receipt")
    release = receipt.get("release")
    if not isinstance(release, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", release):
        raise ValueError("Invalid release identifier")
    if (receipt.get("dataset") != dataset or receipt.get("status") != "success"
            or receipt.get("contract_version") != "1"
            or not isinstance(receipt.get("coverage"), str)
            or not receipt["coverage"].strip()
            or not str(receipt.get("source_url", "")).startswith("https://")):
        raise ValueError("Invalid release metadata")
    products = receipt.get("products")
    if not isinstance(products, dict) or set(products) != set(MARTS):
        raise ValueError("Three independent marts required")
    for mart, product in products.items():
        if not isinstance(product, dict):
            raise ValueError("Invalid product metadata")
        expected = f"gold/{dataset}/{release}/{mart}.jsonl"
        if product.get("path", "").replace("\\", "/") != expected:
            raise ValueError("Product belongs to a different release")
        confined(root, product["path"], f"gold/{dataset}/{release}")
        if type(product.get("records")) is not int or product["records"] < 0:
            raise ValueError("Invalid product count")
        if not re.fullmatch(r"[0-9a-f]{64}", str(product.get("sha256", ""))):
            raise ValueError("Invalid product checksum")
    return receipt


def audit_release(root, dataset):
    """Stream every retained file and Gold row; pin one receipt for this audit.

    Checks integrity against the receipt, not authenticity of upstream claims.
    Errors intentionally exclude file paths, source records and fingerprints.
    """
    root = Path(root).resolve()
    result = {"dataset": dataset, "verified": False, "checks": {}}
    if not (root / "catalog" / dataset / "current.json").is_file():
        result["reason"] = "no_published_receipt"
        return result
    try:
        report = load_receipt(root, dataset)
        release = report["release"]
        result["release"] = release
        if type(report.get("accepted")) is not int or report["accepted"] <= 0:
            raise ValueError("Invalid accepted count")
        if any(type(report.get(k)) is not int or report[k] < 0
               for k in ("read", "rejected", "duplicates")):
            raise ValueError("Invalid quality counts")
        if report["read"] != sum(report[k] for k in ("accepted", "rejected", "duplicates")):
            raise ValueError("Quality counts disagree")
        fraction = report["rejected"] / max(1, report.get("source_quality", {}).get("records_read", report["read"]))
        if not 0 <= fraction <= report["max_rejection_fraction"] <= 1:
            raise ValueError("Quality gate failed")
        files = report["bronze_files"]
        bundle = hashlib.sha256(dumps(files).encode()).hexdigest()
        if bundle != report["bronze_sha256"] or not files:
            raise ValueError("Bronze manifest mismatch")
        for item in files:
            name = item["name"]
            if Path(name).name != name or "\\" in name:
                raise ValueError("Invalid Bronze filename")
            path = confined(root, f"bronze/{dataset}/{bundle}/{name}", f"bronze/{dataset}/{bundle}")
            if path.stat().st_size != item["bytes"] or digest(path) != item["sha256"]:
                result["checks"]["bronze"] = False
                raise ValueError("Bronze integrity mismatch")
        result["checks"]["bronze"] = True
        silver = confined(root, f"silver/{dataset}/{release}/records.jsonl", f"silver/{dataset}/{release}")
        result["checks"]["silver"] = digest(silver) == report["silver_sha256"]
        if not result["checks"]["silver"]:
            raise ValueError("Silver integrity mismatch")
        with silver.open(encoding="utf-8") as stream:
            count = sum(1 for line in stream if isinstance(json.loads(line), dict))
        if count != report["accepted"]:
            raise ValueError("Silver count mismatch")
        provenance = {key: report[key] for key in
                      ("dataset", "source_url", "bronze_sha256", "release", "contract_version", "coverage")}
        counts = {}
        for mart, product in report["products"].items():
            path = confined(root, product["path"], f"gold/{dataset}/{release}")
            result["checks"][mart] = digest(path) == product["sha256"]
            if not result["checks"][mart]:
                raise ValueError("Gold integrity mismatch")
            count = 0
            with path.open(encoding="utf-8") as stream:
                for line in stream:
                    row = json.loads(line)
                    if row["provenance"] != provenance:
                        raise ValueError("Gold lineage mismatch")
                    if mart == "objective1" and (row["type"] != "Feature" or not isinstance(row["properties"], dict)):
                        raise ValueError("Invalid Digital Twin record")
                    if mart == "objective3" and row["evidence_id"] != row["facts"]["_record_id"]:
                        raise ValueError("Invalid evidence record")
                    if mart == "objective4" and not ("geometry" in row or row.get("coverage") == "available_records_only"):
                        raise ValueError("Invalid Decision Support record")
                    count += 1
            if count != product["records"] or count != report["gold_counts"][mart]:
                raise ValueError("Gold count mismatch")
            if mart != "objective4" and count != report["accepted"]:
                raise ValueError("Gold/Silver count mismatch")
            counts[mart] = count
        result["checks"]["record_counts"] = True
        result["checks"]["lineage"] = True
        result.update(verified=True, accepted=report["accepted"], rejected=report["rejected"],
                      gold_counts=counts, coverage=report["coverage"],
                      worldwide_live_coverage=False)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, ZeroDivisionError):
        result["reason"] = "invalid_or_unreadable_receipt"
        result["problem"] = "Missing, corrupt or inconsistent release; inspect private files locally"
    return result


def verify_s3_file(source, bucket, key, client):
    """One streaming GET; compare full bytes, never trust multipart ETags.

    Does not save remote data or print bucket names, keys or checksums. Caller
    supplies an authenticated client; no credential/profile changes occur.
    """
    source = Path(source)
    expected = digest(source)
    size = source.stat().st_size
    response = client.get_object(Bucket=bucket, Key=key)
    body = response["Body"]
    actual = hashlib.sha256()
    received = 0
    try:
        for chunk in body.iter_chunks(chunk_size=1024 * 1024):
            actual.update(chunk)
            received += len(chunk)
    finally:
        body.close()
    return {"verified": received == size == response["ContentLength"]
            and actual.hexdigest() == expected and digest(source) == expected,
            "bytes_compared": received, "method": "full_object_sha256"}


def verify(root, dataset):
    """Compatibility entry point for the established local verification command."""
    return audit_release(root, dataset)


def main():
    import argparse
    from backend.marine_data.storage import resolve_data_root
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", choices=DATASETS)
    parser.add_argument("--data-root", type=Path)
    args = parser.parse_args()
    output = verify(resolve_data_root(args.data_root), args.dataset)
    print(json.dumps(output, indent=2))
    return int(not output["verified"])


if __name__ == "__main__":
    raise SystemExit(main())
