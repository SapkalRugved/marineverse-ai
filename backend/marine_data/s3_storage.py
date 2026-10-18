
"""Explicit, local-first S3 upload adapter for MarineVerse."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from backend.marine_data.aws_config import get_aws_config
from backend.marine_data.storage import resolve_data_root


def plan_uploads(
    source: str | Path,
    data_root: str | Path | None = None,
    prefix: str = "",
) -> list[tuple[Path, str]]:
    """Build upload pairs without contacting AWS or changing files."""

    root = resolve_data_root(data_root).resolve()
    source_path = Path(source).expanduser().resolve()

    if not source_path.is_relative_to(root):
        raise ValueError("Source must remain inside the data root.")

    if not source_path.exists():
        raise FileNotFoundError(source_path)

    if not source_path.is_file() and not source_path.is_dir():
        raise ValueError("Source must be a file or directory.")

    normalized_prefix = prefix.strip("/")

    if (
        "\\" in normalized_prefix
        or any(
            part in {"", ".", ".."}
            for part in normalized_prefix.split("/")
        ) and normalized_prefix
    ):
        raise ValueError("Invalid S3 key prefix.")

    if source_path.is_file():
        files = [source_path]
    else:
        files = sorted(
            path
            for path in source_path.rglob("*")
            if path.is_file()
        )

    uploads = []

    for path in files:
        resolved = path.resolve()

        if not resolved.is_relative_to(root):
            raise ValueError(
                "A source file escapes the configured data root."
            )

        relative_key = resolved.relative_to(root).as_posix()
        key = (
            f"{normalized_prefix}/{relative_key}"
            if normalized_prefix
            else relative_key
        )

        uploads.append((resolved, key))

    return uploads


def upload_files(
    uploads: list[tuple[Path, str]],
    bucket: str,
    *,
    execute: bool = False,
    s3_client: Any = None,
) -> int:
    """Preview uploads by default; upload only when execute=True."""

    if not bucket:
        if execute:
            raise ValueError("S3 bucket must be configured.")
        bucket = "<unconfigured-bucket>"

    if not execute:
        for path, key in uploads:
            print(f"DRY RUN: {path} -> s3://{bucket}/{key}")

        print(f"Planned files: {len(uploads)}")
        return len(uploads)

    if s3_client is None:
        try:
            import boto3
        except ImportError as exc:
            raise RuntimeError(
                "Install boto3 before enabling S3 uploads."
            ) from exc

        config = get_aws_config()
        s3_client = boto3.client(
            "s3",
            region_name=config["region"],
        )

    for path, key in uploads:
        s3_client.upload_file(
            str(path),
            bucket,
            key,
        )

    print(f"Uploaded files: {len(uploads)}")
    return len(uploads)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Preview or explicitly upload MarineVerse raw files."
    )
    parser.add_argument(
        "source",
        help="Local file or directory inside the data root.",
    )
    parser.add_argument(
        "--data-root",
        default=None,
        help="Override MARINEVERSE_DATA_DIR.",
    )
    parser.add_argument(
        "--prefix",
        default="",
        help="Optional S3 object-key prefix.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually upload files. AWS access and costs may apply.",
    )

    args = parser.parse_args()

    uploads = plan_uploads(
        source=args.source,
        data_root=args.data_root,
        prefix=args.prefix,
    )

    config = get_aws_config()

    upload_files(
        uploads,
        bucket=config["bucket"] or "",
        execute=args.execute,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
