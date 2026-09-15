"""Request/answer logging for /v1/chat: every turn must leave a diagnosable trail."""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from apps.api.main import app


def _logs(caplog, fragment):
    return [
        r
        for r in caplog.records
        if r.name == "igihe.api" and fragment in r.getMessage()
    ]


def test_off_corpus_chat_logs_request_and_refusal_reason(caplog):
    with caplog.at_level(logging.INFO, logger="igihe.api"):
        resp = TestClient(app).post(
            "/v1/chat",
            json={
                "session_id": "log-test",
                "message": "Ni iki cyabaye ku mubumbe Mars?",
            },
        )
    assert resp.status_code == 200
    assert _logs(caplog, "chat.request session=log-test"), (
        "expected a chat.request log line for the turn"
    )
    refusals = _logs(caplog, "chat.refusal session=log-test reason=no_lexical_support")
    assert refusals, "expected a refusal log naming the retrieval reason"
    assert "articles_indexed=0" in refusals[0].getMessage()


def test_oversize_message_logs_rejection(caplog):
    with caplog.at_level(logging.INFO, logger="igihe.api"):
        resp = TestClient(app).post(
            "/v1/chat", json={"session_id": "log-test", "message": "x" * 501}
        )
    assert resp.status_code == 413
    assert _logs(caplog, "chat.rejected session=log-test status=413")
