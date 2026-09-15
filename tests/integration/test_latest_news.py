"""Latest-news prompting: contract behavior for recency-style questions.

Current pipeline reality (locked in here, not assumed): retrieval is
relevance-ranked with no date ordering, so a "latest news" prompt either
refuses (no lexical support) or returns a cited relevance-ranked answer.
What must always hold: no uncited factual claims, sources resolve, and the
SSE envelope stays intact. If recency ranking is added later, the
relevance-not-recency test below is the one to update.
"""

import pytest
from fastapi.testclient import TestClient

import apps.api.main as api
from apps.api.main import app

client = TestClient(app)

# Newest fixture article is wp 107 (2024-09-10); oldest is wp 106 (2011).
NEWEST_FIXTURE_ID = 107


def _events(resp):
    return [line[len("event: ") :] for line in resp.text.splitlines() if line.startswith("event: ")]


def test_latest_news_without_lexical_support_refuses():
    text, sources = api.answer_question("Ni izihe nkuru zigezweho?", {})
    assert "nta bimenyetso" in text.lower()
    assert "[1]" not in text
    assert sources, "refusal must still attach disclaimed near matches"


def test_latest_news_refusal_over_sse():
    resp = client.post(
        "/v1/chat", json={"session_id": "latest-1", "message": "Ni iki gishya mu nkuru za IGIHE?"}
    )
    assert resp.status_code == 200
    assert "nta bimenyetso" in resp.text.lower()
    assert "[1]" not in resp.text
    assert '"wp_id"' in resp.text


def test_latest_news_with_support_returns_cited_answer():
    text, sources = api.answer_question("Mbwira inkuru ziheruka", {})
    assert sources, "expected relevance-ranked sources, not a refusal"
    assert "[1]" in text
    assert [s["n"] for s in sources] == list(range(1, len(sources) + 1))
    for s in sources:
        assert s["published_at"], "sources must carry dates so clients can sort"


def test_latest_news_over_sse_has_sources_and_model():
    resp = client.post(
        "/v1/chat", json={"session_id": "latest-2", "message": "Mbwira inkuru ziheruka"}
    )
    assert resp.status_code == 200
    events = _events(resp)
    assert "retrieval" in events and "sources" in events and "done" in events
    assert "[1]" in resp.text
    assert f'"model": "{api.generator.model_id}"' in resp.text


@pytest.mark.xfail(reason="retrieval is relevance-ranked; no recency ordering yet")
def test_latest_news_is_recency_ordered():
    _, sources = api.answer_question("Mbwira inkuru ziheruka", {})
    assert sources[0]["wp_id"] == NEWEST_FIXTURE_ID
