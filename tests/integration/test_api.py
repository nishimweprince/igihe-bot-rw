from fastapi.testclient import TestClient

import apps.api.main as api
from apps.api.main import app

client = TestClient(app)


def _events(resp):
    out = []
    for line in resp.text.splitlines():
        if line.startswith("event: "):
            out.append(line[len("event: ") :])
    return out


def test_health():
    assert client.get("/health/live").json() == {"status": "ok"}
    ready = client.get("/health/ready").json()
    assert ready["status"] == "ready" and ready["articles"] >= 9


def test_factual_chat_returns_sources_and_citations():
    resp = client.post(
        "/v1/chat", json={"session_id": "t1", "message": "Ni izihe nkuru ku mazi i Kigali?"}
    )
    assert resp.status_code == 200
    events = _events(resp)
    assert "retrieval" in events and "sources" in events and "done" in events
    assert "[1]" in resp.text


def test_unanswerable_returns_no_evidence_wording():
    resp = client.post("/v1/chat", json={"session_id": "t2", "message": "xyzzy blorpt quux nabi?"})
    assert resp.status_code == 200
    assert "nta bimenyetso" in resp.text.lower()


def test_realistic_unanswerable_with_shared_function_words_refuses():
    # "Mars" shares ni/ku/ejo with the corpus but no content term matches.
    resp = client.post(
        "/v1/chat", json={"session_id": "t2b", "message": "Ni iki cyabaye ku mubumbe Mars ejo?"}
    )
    assert resp.status_code == 200
    low = resp.text.lower()
    assert "nta bimenyetso" in low
    # Refusal must not answer; nothing in the fixtures is close to Mars.
    assert "[1]" not in resp.text
    assert "event: sources\ndata: []" in resp.text


# Shares "mazi" with the water stories but nothing else: coverage too low
# to answer, high enough to show the water stories as disclaimed near matches.
NEAR_MISS = "Amazi ku mubumbe Mars?"


def test_no_evidence_points_to_origin_and_disclaims_close_matches():
    text, sources, _suggestions = api.answer_question(NEAR_MISS, {})
    assert "—" not in text
    low = text.lower()
    assert "nta bimenyetso" in low
    assert "[IGIHE](https://old.igihe.com)" in text
    assert "nzikwereka" in low
    assert "egereye" in low
    assert "ibisubizo nyabyo" in low
    assert sources, "expected closest articles alongside the refusal"
    assert len(sources) <= api.CLOSE_MATCH_N
    assert [s["n"] for s in sources] == list(range(1, len(sources) + 1))
    for s in sources:
        assert s["url"], "close matches must resolve to readable articles"


def test_no_close_match_suggests_another_prompt():
    text, sources, suggestions = api.answer_question(
        "xyzzy blorpt quux nabi?",
        {
            "published_after": "2999-01-01",
            "published_before": None,
            "category_ids": [],
        },
    )
    assert sources == []
    assert "—" not in text
    # Chips carry the invitation now; the prose must not restate it.
    assert "Mbwira inkuru ziheruka." not in text
    assert suggestions
    assert "Mbwira inkuru ziheruka." in suggestions


def test_no_close_match_streams_sendable_suggestions():
    resp = client.post(
        "/v1/chat",
        json={
            "session_id": "t-sugg",
            "message": "xyzzy blorpt quux nabi?",
            "filters": {
                "published_after": "2999-01-01",
                "published_before": None,
                "category_ids": [],
            },
        },
    )
    assert resp.status_code == 200
    assert "event: suggestions" in resp.text
    assert "Mbwira inkuru ziheruka" in resp.text


def test_near_match_refusal_streams_headline_suggestions():
    _text, sources, suggestions = api.answer_question(NEAR_MISS, {})
    assert sources, "expected closest articles alongside the refusal"
    assert suggestions, "near-match refusal must carry follow-up prompts"
    assert sources[0]["title"] in suggestions
    resp = client.post("/v1/chat", json={"session_id": "t-sugg-near", "message": NEAR_MISS})
    assert resp.status_code == 200
    assert "event: suggestions" in resp.text
    assert sources[0]["title"] in resp.text


def test_oversized_rejected():
    resp = client.post("/v1/chat", json={"session_id": "t3", "message": "x" * 2000})
    assert resp.status_code == 413


def test_no_prompt_or_trace_leak():
    resp = client.post("/v1/chat", json={"session_id": "t4", "message": "Amazi i Kigali?"})
    low = resp.text.lower()
    assert "traceback" not in low and "ibimenyetso (ntabwo" not in low


def test_index_reused_across_clients_and_threads():
    # Guards the cross-thread SQLite regression: index built during one
    # request must serve later requests from other threads, not refuse.
    other = TestClient(app)
    assert other.get("/health/ready").status_code == 200
    resp = other.post("/v1/chat", json={"session_id": "tX", "message": "Amazi meza i Kigali?"})
    assert resp.status_code == 200
    assert "[1]" in resp.text


def test_citationless_answer_replaced_with_refusal(monkeypatch):
    # Contract: factual answers without [n] markers never stream as
    # authoritative, even when retrieval found sources.
    class NoCite:
        model_id = "nocite"

        def generate(self, system, messages, max_tokens=400):
            return "Al Hilal yatsinze umukino."

        def stream(self, system, messages, max_tokens=400):
            yield "Al Hilal yatsinze umukino."

    monkeypatch.setattr(api, "generator", NoCite())
    text, sources, suggestions = api.answer_question("APR yatsinze Rayon gute?", {})
    assert "nta bimenyetso" in text.lower()
    assert suggestions, "validation-failure refusal must carry follow-up prompts"


def test_feedback_recorded():
    resp = client.post(
        "/v1/feedback", json={"session_id": "t1", "helpful": True, "reason": "citation"}
    )
    assert resp.json() == {"status": "recorded"}


def test_gibberish_has_no_near_matches_but_fallback_suggestions():
    text, sources, suggestions = api.answer_question("xyzzy blorpt quux nabi?", {})
    assert sources == [] and "nta bimenyetso" in text.lower()
    assert "Mbwira inkuru ziheruka." in suggestions


def test_history_gives_a_one_word_follow_up_context():
    history = [
        {"role": "user", "content": "Ni izihe nkuru ku mazi i Kigali?"},
        {"role": "assistant", "content": "Amazi meza yageze i Kigali [1]."},
    ]
    _text, sources, _ = api.answer_question("Icosora?", {}, history=history)
    assert sources and {s["wp_id"] for s in sources} & {101, 109}


def test_sources_endpoint_returns_article_or_404():
    assert client.get("/v1/sources/107").json()["title"].startswith("Umusaruro")
    assert client.get("/v1/sources/424242").status_code == 404
