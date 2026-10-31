"""Verified ZIP restore tests: source-backed fixture and deliberate mutations."""
import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from backend.marine_data.platform.pipeline import run
from backend.marine_data.platform.verify import audit_release
from scripts.operations.restore_verified_archive import restore

FIXTURE = Path(__file__).parent / "fixtures" / "ibtracs_real_excerpt.csv"


def make_archive(tmp_path, *, tamper=False):
    root = tmp_path / "original"
    receipt = run("ibtracs", FIXTURE, root=root,
                  source_url="https://www.ncei.noaa.gov/products/international-best-track-archive",
                  coverage="Genuine NOAA fixture excerpt; not global live coverage")
    archive = tmp_path / "published.zip"
    with ZipFile(archive, "w") as zipped:
        for directory in ("catalog", "bronze", "silver", "gold"):
            for path in (root / directory).rglob("*"):
                if not path.is_file():
                    continue
                relative = path.relative_to(root).as_posix()
                contents = path.read_bytes()
                if tamper and relative.endswith("objective3.jsonl"):
                    contents += b"invalid"
                zipped.writestr(relative, contents)
        zipped.writestr("silver/ibtracs/" + receipt["release"] + "/.partial.tmp",
                        b"should never be extracted")
    return archive


def test_restore_excludes_temp_and_validates_real_fixture(tmp_path):
    archive = make_archive(tmp_path)
    dest = tmp_path / "restored"
    result = restore(archive, dest)
    assert result["verified"]
    assert result["restored_datasets"] == ["ibtracs"]
    assert result["excluded_nonpublication_entries"] >= 1
    assert audit_release(dest, "ibtracs")["verified"]
    assert not any(p.name.startswith(".partial") for p in dest.rglob("*"))


def test_corrupted_mart_is_not_restored(tmp_path):
    archive = make_archive(tmp_path, tamper=True)
    dest = tmp_path / "restored"
    with pytest.raises(ValueError, match="integrity"):
        restore(archive, dest)
    assert not dest.exists()


def test_existing_destination_not_overwritten(tmp_path):
    archive = make_archive(tmp_path)
    dest = tmp_path / "restored"
    dest.mkdir()
    sentinel = dest / "keep.txt"
    sentinel.write_text("valuable local data")
    with pytest.raises(FileExistsError):
        restore(archive, dest)
    assert sentinel.read_text() == "valuable local data"


def test_missing_published_file_fails_closed(tmp_path):
    archive = make_archive(tmp_path)
    broken = tmp_path / "broken.zip"
    with ZipFile(archive) as source, ZipFile(broken, "w") as target:
        for item in source.infolist():
            if item.filename.endswith("objective4.jsonl"):
                continue
            target.writestr(item.filename, source.read(item))
    with pytest.raises(ValueError, match="canonical"):
        restore(broken, tmp_path / "restored")


def test_archive_traversal_member_ignored(tmp_path):
    archive = make_archive(tmp_path)
    with ZipFile(archive, "a") as zipped:
        zipped.writestr("../../outside.txt", "evil")
    result = restore(archive, tmp_path / "restored")
    assert result["verified"]
    assert not (tmp_path / "outside.txt").exists()
