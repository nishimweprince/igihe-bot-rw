import pytest
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
    assert "nta bimenyetso" in resp.text.lower()
    assert "data: []" in resp.text


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

        def generate(self, prompt, sources, max_tokens=400):
            return "Al Hilal yatsinze umukino."

    monkeypatch.setattr(api, "generator", NoCite())
    text, sources = api.answer_question("APR yatsinze Rayon gute?", {})
    assert sources == []
    assert "nta bimenyetso" in text.lower()


def test_feedback_recorded():
    resp = client.post(
        "/v1/feedback", json={"session_id": "t1", "helpful": True, "reason": "citation"}
    )
    assert resp.json() == {"status": "recorded"}


@pytest.mark.skip(reason="requires live PostgreSQL + pgvector")
def test_postgres_parity():
    from igihe_assistant.retrieval.store import PostgresBackend

    PostgresBackend("postgresql://localhost/assistant").lexical("amazi", 5)
