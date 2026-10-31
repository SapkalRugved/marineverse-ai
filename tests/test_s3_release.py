"""No-network tests for private S3 release integrity and safe publication."""
import hashlib
import io
from pathlib import Path

import pytest

from backend.marine_data.platform.pipeline import run
from backend.marine_data.platform.s3_release import publish, release_paths

FIXTURE = Path(__file__).parent / "fixtures" / "ibtracs_real_excerpt.csv"
URL = "https://www.ncei.noaa.gov/products/international-best-track-archive"


class Body:
    def __init__(self, data):
        self.handle = io.BytesIO(data)
    def iter_chunks(self, chunk_size):
        while True:
            block = self.handle.read(chunk_size)
            if not block:
                break
            yield block
    def read(self):
        return self.handle.read()
    def close(self):
        self.handle.close()


class MissingObject(Exception):
    def __init__(self):
        self.response = {"Error": {"Code": "404"}}


class MemoryS3:
    class exceptions:
        NoSuchKey = MissingObject

    def __init__(self):
        self.objects = {}
        self.uploads = 0
        self.puts = 0

    def head_object(self, *, Bucket, Key):
        if Key not in self.objects:
            raise MissingObject()
        return {"ContentLength": len(self.objects[Key])}

    def get_object(self, *, Bucket, Key):
        return {"Body": Body(self.objects[Key])}

    def upload_file(self, source, bucket, key):
        self.objects[key] = Path(source).read_bytes()
        self.uploads += 1

    def put_object(self, *, Bucket, Key, Body, ContentType):
        self.objects[Key] = Body
        self.puts += 1


def seed(root):
    return run(
        "ibtracs", FIXTURE, source_url=URL,
        coverage="Real NOAA fixture excerpt only", root=root
    )


def test_preview_is_read_only_and_safe(tmp_path):
    seed(tmp_path)
    result = publish(tmp_path, "ibtracs", "existing-private-bucket")
    assert result["planned_objects"] >= 7
    assert result["execute"] is False
    assert result["catalog_published"] is False
    assert result["verified"] == 0
    assert "sha256" not in str(result).lower()


def test_refuses_unpublished_release(tmp_path):
    with pytest.raises(ValueError, match="integrity"):
        release_paths(tmp_path, "ibtracs")


def test_remote_round_trip_and_idempotency(tmp_path):
    seed(tmp_path)
    client = MemoryS3()
    first = publish(tmp_path, "ibtracs", "existing-private-bucket",
                    execute=True, client=client)
    assert first["verified"] == first["planned_objects"]
    assert first["uploaded"] == first["planned_objects"]
    assert first["catalog_published"]
    assert client.puts == 1
    again = publish(tmp_path, "ibtracs", "existing-private-bucket",
                    execute=True, client=client)
    assert again["uploaded"] == 0
    assert again["skipped_existing_verified"] == first["planned_objects"]
    assert client.puts == 2


def test_existing_remote_tamper_fails_before_catalog(tmp_path):
    seed(tmp_path)
    client = MemoryS3()
    _, files = release_paths(tmp_path, "ibtracs")
    client.objects[files[0][1]] = b"x" * files[0][0].stat().st_size
    with pytest.raises(ValueError, match="checksum mismatch"):
        publish(tmp_path, "ibtracs", "existing-private-bucket",
                execute=True, client=client)
    assert client.puts == 0


def test_cannot_replace_object_with_wrong_size(tmp_path):
    seed(tmp_path)
    client = MemoryS3()
    _, files = release_paths(tmp_path, "ibtracs")
    client.objects[files[0][1]] = b"bad"
    with pytest.raises(ValueError, match="wrong size"):
        publish(tmp_path, "ibtracs", "existing-private-bucket",
                execute=True, client=client)
    assert client.puts == 0


def test_refuse_bad_bucket(tmp_path):
    with pytest.raises(ValueError, match="bucket"):
        publish(tmp_path, "ibtracs", "../unsafe")
