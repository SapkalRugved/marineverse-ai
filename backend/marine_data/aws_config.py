
"""Validate AWS staging configuration without contacting AWS."""

import os
import re
from dotenv import load_dotenv
from backend.marine_data.database import ENVIRONMENT_FILE

load_dotenv(
    dotenv_path=ENVIRONMENT_FILE,
    override=False,
)

def get_aws_config():
    region = os.getenv("AWS_REGION", "ap-south-1")
    bucket = os.getenv("MARINEVERSE_S3_BUCKET", "").strip()

    if not re.fullmatch(r"[a-z]{2}(?:-gov)?-[a-z]+-\d", region):
        raise ValueError("Invalid AWS_REGION.")

    if bucket:
        if not (3 <= len(bucket) <= 63):
            raise ValueError("S3 bucket name must have 3-63 characters.")
        if not re.fullmatch(r"[a-z0-9][a-z0-9.-]*[a-z0-9]", bucket):
            raise ValueError("Invalid S3 bucket name.")
        if ".." in bucket or re.fullmatch(r"\d+\.\d+\.\d+\.\d+", bucket):
            raise ValueError("Invalid S3 bucket name.")
        if bucket.startswith(("xn--", "sthree-", "amzn-s3-demo-")):
            raise ValueError("Reserved S3 bucket prefix.")
        if bucket.endswith(("-s3alias", "--ol-s3", ".mrap",
                            "--x-s3", "--table-s3")):
            raise ValueError("Reserved S3 bucket suffix.")

    return {
        "region": region,
        "bucket": bucket or None,
        "storage_ready": bool(bucket),
    }
