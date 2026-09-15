"""Latest-news prompting: browse mode answers with the newest stories.

A question with only news/recency words ("Mbwira inkuru ziheruka") has no
topic to search for; the retriever switches to browse mode and the model
is asked for a cited round-up of the newest articles. Topic + recency cue
keeps the lexical path but boosts recent matches.
"""

from fastapi.testclient import TestClient

import apps.api.main as api
from apps.api.main import app

client = TestClient(app)

# Newest fixture article is wp 107 (2024-09-10); oldest is wp 106 (2011).
NEWEST_FIXTURE_ID = 107


def _events(resp):
    return [line[len("event: ") :] for line in resp.text.splitlines() if line.startswith("event: ")]


def test_latest_news_is_recency_ordered():
    _, sources, _ = api.answer_question("Mbwira inkuru ziheruka", {})
    assert sources[0]["wp_id"] == NEWEST_FIXTURE_ID
    dates = [s["published_at"] for s in sources]
    assert dates == sorted(dates, reverse=True)
    assert [s["n"] for s in sources] == list(range(1, len(sources) + 1))


def test_generic_recency_question_answers_with_citation():
    text, sources, _ = api.answer_question("Ni izihe nkuru zigezweho?", {})
    assert sources and "[1]" in text


def test_latest_news_over_sse_has_sources_and_model():
    resp = client.post(
        "/v1/chat", json={"session_id": "latest-2", "message": "Ni iki gishya mu nkuru za IGIHE?"}
    )
    assert resp.status_code == 200
    events = _events(resp)
    assert "retrieval" in events and "sources" in events and "done" in events
    assert "[1]" in resp.text
    assert f'"model": "{api.generator.model_id}"' in resp.text
    assert '"retrieval": "trigram-fts5"' in resp.text


def test_topic_with_recency_cue_stays_on_topic():
    _, sources, _ = api.answer_question("Ni iki gishya ku mazi i Kigali?", {})
    assert sources and sources[0]["wp_id"] in (101, 109)
