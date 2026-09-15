import json
from pathlib import Path

from igihe_assistant.pipeline import build_index
from igihe_assistant.retrieval.query import analyze
from igihe_assistant.retrieval.rank import (
    group_near_duplicates,
    recency_multiplier,
    retrieve,
    rrf_merge,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "wp"


def _store():
    return build_index([json.loads(p.read_text()) for p in sorted(FIXTURES.glob("*.json"))])


def test_rrf_prefers_item_ranked_high_in_both_lists():
    merged = dict(rrf_merge([["a", "b", "c"], ["b", "a", "d"]]))
    assert merged["a"] > merged["c"] and merged["b"] > merged["d"]


def test_grouping_keeps_best_per_article_and_story():
    by_id = {
        "c1": {"wp_id": 1, "title": "Amazi i Kigali"},
        "c2": {"wp_id": 1, "title": "Amazi i Kigali"},
        "c3": {"wp_id": 2, "title": "Amazi i Kigali"},
        "c4": {"wp_id": 3, "title": "Ikawa yazamutse"},
    }
    out = group_near_duplicates(["c1", "c2", "c3", "c4"], by_id)
    assert out == ["c1", "c4"]


def test_recency_multiplier_decays_with_half_life():
    assert recency_multiplier(0, 1.0, 30) == 2.0
    assert abs(recency_multiplier(30, 1.0, 30) - 1.5) < 1e-9
    assert recency_multiplier(30, 0.0, 30) == 1.0


def test_factual_question_ranks_matching_article_first():
    store = _store()
    cands = retrieve(analyze("Ni izihe nkuru ku mazi i Kigali?"), store)
    assert cands and cands[0].wp_id in (101, 109)
    assert cands[0].coverage == 1.0
    assert len({c.wp_id for c in cands}) == len(cands), "one chunk per article"


def test_strict_tier_then_loose_tier():
    store = _store()
    # "kigali" + "ikawa" never co-occur in the fixtures: strict AND is empty,
    # so the loose OR tier must still surface both stories.
    cands = retrieve(analyze("ikawa i Kigali"), store)
    wp = {c.wp_id for c in cands}
    assert 107 in wp and (101 in wp or 109 in wp)
    assert all(c.coverage < 1.0 for c in cands)


def test_off_corpus_question_has_no_candidates():
    assert retrieve(analyze("Ni iki cyabaye ku mubumbe Mars ejo?"), _store()) == []


def _twin_posts():
    body = "<p>Ikipe ya Musanze yatsinze umukino w'igikombe.</p>"
    return [
        {"id": 1, "date": "2015-01-01T00:00:00", "modified": "2015-01-01T00:00:00",
         "link": "https://x/1", "title": {"rendered": "Musanze: umukino wa kera"},
         "content": {"rendered": body}, "categories": [1], "status": "publish"},
        {"id": 2, "date": "2025-01-01T00:00:00", "modified": "2025-01-01T00:00:00",
         "link": "https://x/2", "title": {"rendered": "Musanze: umukino mushya"},
         "content": {"rendered": body}, "categories": [1], "status": "publish"},
    ]


def test_recency_cue_prefers_newer_article():
    store = build_index(_twin_posts())
    plain = retrieve(analyze("Musanze umukino"), store, recency_weight=0.0)
    recent = retrieve(analyze("Musanze umukino vuba"), store, recency_window_days=100000)
    assert {c.wp_id for c in plain} == {1, 2}
    assert recent[0].wp_id == 2 and recent[0].score > recent[1].score * 1.5


def test_recency_window_falls_back_when_too_few_recent_hits():
    store = build_index(_twin_posts())
    # 180-day window relative to the newest article (2025-01-01) keeps only
    # wp 2; below min_window_hits the search reruns without the window.
    cands = retrieve(analyze("Musanze umukino vuba"), store)
    assert [c.wp_id for c in cands] == [2, 1]


def test_browse_mode_returns_newest_first():
    cands = retrieve(analyze("Mbwira inkuru ziheruka"), _store(), final_n=3)
    days = [c.published_day for c in cands]
    assert cands[0].wp_id == 107 and days == sorted(days, reverse=True)


def test_date_filter_applies_in_sql():
    store = _store()
    cands = retrieve(analyze("amazi i Kigali"), store, {"published_after": "2024-03-03"})
    assert [c.wp_id for c in cands] == [109]
    assert retrieve(analyze("amazi"), store, {"published_after": "2999-01-01"}) == []


def test_rerank_blends_with_lexical_order():
    from igihe_assistant.retrieval.rerank import rerank

    class Reverse:
        model_id = "reverse"

        def score(self, query, passages):
            return list(range(len(passages)))  # last lexical candidate scores highest

    cands = retrieve(analyze("amazi i Kigali"), _store())
    assert len(cands) >= 2
    out = rerank("amazi i Kigali", cands, Reverse())
    assert {c.cid for c in out} == {c.cid for c in cands}
    assert out[0].cid in (cands[0].cid, cands[-1].cid)
