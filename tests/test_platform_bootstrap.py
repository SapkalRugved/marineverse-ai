"""Regression coverage for offline Natural Earth bootstrap (no provider calls)."""
import json
from pathlib import Path
from unittest.mock import patch

from backend.marine_data.platform.bootstrap import SOURCE, plan, execute


def seed(root: Path, dataset: str):
    p = root / SOURCE[dataset]["relative_path"]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"placeholder ZIP; never parsed by mocked pipeline")
    return p


def test_preview_without_data_is_non_destructive(tmp_path):
    result = plan(tmp_path)
    assert len(result) == 2
    assert all(row["action"] == "missing_source" for row in result)
    assert list(tmp_path.iterdir()) == []


def test_source_detected_and_does_not_reach_aws(tmp_path):
    seed(tmp_path, "coastline")
    result = plan(tmp_path)
    assert result[0]["action"] == "publish"
    assert result[1]["action"] == "missing_source"


def test_execute_uses_existing_pipeline_without_network(tmp_path):
    seed(tmp_path, "coastline")
    seed(tmp_path, "land")
    with patch("backend.marine_data.platform.bootstrap.run") as publish:
        publish.side_effect = lambda dataset, *args, **kwargs: {
            "status": "success", "accepted": 5, "rejected": 0,
            "gold_counts": {m: 5 for m in ("objective1", "objective3", "objective4")}
        }
        outcome = execute(tmp_path)
    assert not outcome["errors"]
    assert set(outcome["receipts"]) == {"coastline", "land"}
    assert publish.call_count == 2
    assert all(
        call.kwargs["source_url"].startswith("https://")
        for call in publish.call_args_list
    )
    assert all(call.kwargs["root"] == tmp_path for call in publish.call_args_list)


def test_existing_published_dataset_is_skipped(tmp_path):
    seed(tmp_path, "coastline")
    root = tmp_path
    gold = root / "gold" / "coastline" / "release1"
    gold.mkdir(parents=True)
    products = {}
    for mart in ("objective1", "objective3", "objective4"):
        p = gold / (mart + ".jsonl")
        p.write_text("{}\n")
        products[mart] = {"path": str(p.relative_to(root))}
    current = root / "catalog" / "coastline" / "current.json"
    current.parent.mkdir(parents=True)
    current.write_text(json.dumps({
        "dataset": "coastline", "status": "success", "products": products,
    }))
    assert plan(root)[0]["action"] == "skip_published"
    assert plan(root, include_existing=True)[0]["action"] == "publish"


def test_failed_release_does_not_stop_other_source(tmp_path):
    seed(tmp_path, "coastline")
    seed(tmp_path, "land")
    with patch("backend.marine_data.platform.bootstrap.run") as publish:
        publish.side_effect = ValueError("Invalid source")
        outcome = execute(tmp_path)
    assert set(outcome["errors"]) == {"coastline", "land"}
    assert publish.call_count == 2
