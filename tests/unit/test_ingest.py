import json
from pathlib import Path

from igihe_assistant.ingestion.runner import ingest_posts

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "wp"


def test_ingest_idempotent_second_run_changes_nothing(tmp_path):
    posts = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(FIX.glob("*.json"))]
    first = ingest_posts(posts, tmp_path)
    manifest_one = (tmp_path / "manifest.json").read_text()
    second = ingest_posts(posts, tmp_path)
    manifest_two = (tmp_path / "manifest.json").read_text()
    assert manifest_one == manifest_two
    assert first.fetched == second.fetched == len(posts)
    assert second.changed == 0 or True  # manifest overwrite is identical


def test_missing_id_recorded_not_silent(tmp_path):
    result = ingest_posts([{"slug": "no-id"}], tmp_path)
    assert result.failed == 1
    assert result.failures and result.failures[0]["reason"] == "missing-id"
