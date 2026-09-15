import json
from pathlib import Path

from igihe_assistant.index.builder import bulk_build, iter_posts, published_day, upsert_posts
from igihe_assistant.retrieval.store import IndexStore

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "wp"


def _posts():
    return [json.loads(p.read_text()) for p in sorted(FIXTURES.glob("*.json"))]


def test_published_day():
    assert published_day("1970-01-02T00:00:00") == 1
    assert published_day("garbage") == 0


def test_bulk_build_to_file_then_reopen_read_only(tmp_path):
    path = str(tmp_path / "idx.sqlite")
    store = IndexStore.create(path)
    stats = bulk_build(store, _posts())
    store.close()
    assert stats.posts == 9 and stats.inserted == 9 and stats.chunks >= 9
    ro = IndexStore(path)
    assert ro.stats()["articles"] == 9
    assert ro.meta()["tokenizer"] == "trigram"
    assert ro.meta()["max_published_at"] == "2024-09-10T09:00:00"
    hits = ro.lexical('"kawa"', 5)
    assert hits and hits[0].wp_id == 107
    assert ro.get_article(107)["url"].startswith("https://")
    assert ro.get_article(999) is None


def test_upsert_updates_fts_and_skips_unchanged(tmp_path):
    store = IndexStore.create(str(tmp_path / "idx.sqlite"))
    bulk_build(store, _posts())
    post = next(p for p in _posts() if p["id"] == 105)
    assert store.lexical('"zebra"', 5) == []
    changed = {**post, "modified": "2030-01-01T00:00:00",
               "title": {"rendered": "Zebra itangazo"}}
    stats = upsert_posts(store, [changed, post])
    assert stats.updated == 1 and stats.skipped == 1
    assert store.lexical('"zebra"', 5)[0].wp_id == 105
    assert store.get_article(105)["title"] == "Zebra itangazo"


def test_unpublished_post_is_removed(tmp_path):
    store = IndexStore.create(str(tmp_path / "idx.sqlite"))
    bulk_build(store, _posts())
    stats = upsert_posts(store, [{"id": 107, "status": "draft"}])
    assert stats.deleted == 1
    assert store.get_article(107) is None
    assert store.lexical('"kawa"', 5) == []


def test_iter_posts_reads_page_files_in_numeric_order(tmp_path):
    for n in (10, 2, 1):
        (tmp_path / f"page-{n}.json").write_text(json.dumps([{"id": n}]))
    assert [p["id"] for p in iter_posts(tmp_path)] == [1, 2, 10]
    assert [p["id"] for p in iter_posts(tmp_path, limit=2)] == [1, 2]
