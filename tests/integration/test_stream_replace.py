"""SSE contract for real streaming: token pieces concatenate to the answer;
validation failures arrive as `event: replace` with near matches."""

import json
import time

from fastapi.testclient import TestClient

import apps.api.main as api
from apps.api.main import app

client = TestClient(app)


def _parse(text):
    events = []
    for block in text.strip().split("\n\n"):
        lines = block.splitlines()
        name = lines[0][len("event: "):]
        data = json.loads(lines[1][len("data: "):])
        events.append((name, data))
    return events


def test_tokens_concatenate_to_the_final_answer():
    resp = client.post("/v1/chat", json={"session_id": "st1", "message": "Amazi meza i Kigali?"})
    events = _parse(resp.text)
    tokens = [d["text"] for n, d in events if n == "token"]
    assert len(tokens) > 3, "expected piece-wise streaming, not one blob"
    text = "".join(tokens)
    assert "[1]" in text
    assert not any(n == "replace" for n, _ in events)
    assert [n for n, _ in events][-2:] == ["sources", "done"]


def test_mid_stream_echo_is_replaced_and_generation_cancelled(monkeypatch):
    class Echo:
        model_id = "echo"
        produced = 0

        def stream(self, system, messages, max_tokens=400):
            for piece in ["Amazi ", "meza. ", "Ibimenyetso: ", "never ", "sent "]:
                self.produced += 1
                yield piece
                time.sleep(0.05)  # a real model is slower than the consumer

        def generate(self, system, messages, max_tokens=400):
            return "".join(self.stream(system, messages, max_tokens))

    gen = Echo()
    monkeypatch.setattr(api, "generator", gen)
    resp = client.post("/v1/chat", json={"session_id": "st2", "message": "Amazi meza i Kigali?"})
    events = _parse(resp.text)
    names = [n for n, _ in events]
    assert "replace" in names
    replace = next(d for n, d in events if n == "replace")
    assert replace["reason"] == "evidence-echo"
    assert "nta bimenyetso" in replace["text"].lower()
    assert gen.produced < 5, "worker must stop after the rejected piece"
    sources = next(d for n, d in events if n == "sources")
    assert sources, "refusal keeps the retrieved stories as disclaimed near matches"
    assert any(n == "suggestions" for n in names)


def test_citationless_stream_is_replaced_at_the_end(monkeypatch):
    class NoCite:
        model_id = "nocite"

        def stream(self, system, messages, max_tokens=400):
            yield "Amazi "
            yield "meza yageze."

        def generate(self, system, messages, max_tokens=400):
            return "Amazi meza yageze."

    monkeypatch.setattr(api, "generator", NoCite())
    resp = client.post("/v1/chat", json={"session_id": "st3", "message": "Amazi meza i Kigali?"})
    events = _parse(resp.text)
    assert [d["text"] for n, d in events if n == "token"] == ["Amazi ", "meza yageze."]
    assert next(d for n, d in events if n == "replace")["reason"] == "no-citation"


def test_generator_crash_mid_stream_falls_back_to_fake(monkeypatch):
    class Crash:
        model_id = "crash"

        def stream(self, system, messages, max_tokens=400):
            yield "Amazi "
            raise RuntimeError("gpu on fire")

        def generate(self, system, messages, max_tokens=400):
            raise RuntimeError("gpu on fire")

    monkeypatch.setattr(api, "generator", Crash())
    resp = client.post("/v1/chat", json={"session_id": "st4", "message": "Amazi meza i Kigali?"})
    events = _parse(resp.text)
    replace = next(d for n, d in events if n == "replace")
    assert replace["reason"] == "generator-fallback" and "[1]" in replace["text"]
    assert "traceback" not in resp.text.lower()
