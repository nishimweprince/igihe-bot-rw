"""FastAPI contract: /v1/chat SSE, health, sources, feedback."""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from igihe_assistant.config import Settings
from igihe_assistant.embeddings.embedder import FakeHashEmbedder
from igihe_assistant.generation.generator import FakeGenerator
from igihe_assistant.generation.ollama_gen import OllamaGenerator
from igihe_assistant.generation.validator import CITE, validate
from igihe_assistant.normalization.normalize import content_terms, normalize_search
from igihe_assistant.observability import metrics
from igihe_assistant.pipeline import build_index
from igihe_assistant.prompting.builder import NO_EVIDENCE_RW, build_prompt
from igihe_assistant.retrieval.hybrid import retrieve

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "wp"

app = FastAPI(title="igihe-assistant", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
settings = Settings()
embedder = FakeHashEmbedder()
fake_generator = FakeGenerator()
if settings.ollama_model:
    generator = OllamaGenerator(settings.ollama_model, settings.ollama_base_url)
else:
    generator = fake_generator
semaphore = asyncio.Semaphore(settings.max_concurrent_generations)
_rate: dict[str, list[float]] = {}
_state: dict = {}


def _load_posts() -> list[dict]:
    sample_dir = os.environ.get("SAMPLE_DIR", "")
    if sample_dir:
        posts = []
        for path in sorted(Path(sample_dir).glob("page-*.json")):
            posts.extend(json.loads(path.read_text(encoding="utf-8")))
        if posts:
            return posts
    posts = []
    for path in sorted(FIXTURES.glob("*.json")):
        posts.append(json.loads(path.read_text(encoding="utf-8")))
    return posts


def get_state() -> dict:
    if "backend" not in _state:
        backend, by_id, articles = build_index(_load_posts(), embedder)
        _state.update(backend=backend, by_id=by_id, articles=articles)
    return _state


class Filters(BaseModel):
    published_after: str | None = None
    published_before: str | None = None
    category_ids: list = Field(default_factory=list)


class ChatRequest(BaseModel):
    session_id: str
    message: str
    article_id: int | None = None
    filters: Filters = Field(default_factory=Filters)


class FeedbackRequest(BaseModel):
    session_id: str
    helpful: bool
    reason: str = ""


def _check_rate(session_id: str) -> None:
    now = time.time()
    hits = [t for t in _rate.get(session_id, []) if now - t < 60]
    if len(hits) >= 30:
        raise HTTPException(status_code=429, detail="Nyongera ugerageze nyuma.")
    hits.append(now)
    _rate[session_id] = hits


def answer_question(
    message: str, filters: dict, article_id: int | None = None
) -> tuple[str, list[dict]]:
    st = get_state()
    backend, by_id = st["backend"], st["by_id"]
    if article_id is None:
        terms = content_terms(message)
        # No content-term lexical support in the archive: refuse rather than
        # guess from dense similarity alone (dense always ranks something,
        # and function words like "ni"/"ku" match almost every article).
        if not terms or not backend.lexical(" ".join(terms), 5, filters):
            metrics.incr("requests.refusal")
            return NO_EVIDENCE_RW, []
    if article_id is not None:
        cids = [cid for cid, ch in by_id.items() if ch["wp_id"] == article_id]
        ranked = cids[:6]
    else:
        qvec = embedder.embed(normalize_search(message))
        ranked = retrieve(
            normalize_search(message),
            qvec,
            backend,
            final_n=6,
            filters=filters,
            candidates=settings.retrieval_candidates,
        )
    sources = []
    for cid in ranked:
        ch = by_id[cid]
        art = st["articles"][ch["wp_id"]]
        sources.append(
            {
                "n": len(sources) + 1,
                "wp_id": ch["wp_id"],
                "title": art["title"],
                "published_at": art["published_at"],
                "url": art["url"],
                "content": ch["content"],
            }
        )
    if not sources:
        return NO_EVIDENCE_RW, []
    # Evidence budget for the model: small local models lose the citation
    # instruction over long contexts. Citations still resolve to full
    # articles; only the prompt copy is trimmed. Tune via env for the demo.
    sources = sources[: settings.max_evidence_sources]
    if settings.max_evidence_chars > 0:
        sources = [
            {**s, "content": s["content"][: settings.max_evidence_chars]} for s in sources
        ]
    prompt = build_prompt(message, sources)

    def _generate(prompt_text: str) -> str:
        try:
            return generator.generate(prompt_text, sources, settings.max_output_tokens)
        except Exception:
            # Real-model failure must degrade to the fake, never to a 500.
            metrics.incr("generator.ollama_fallback")
            return fake_generator.generate(prompt_text, sources, settings.max_output_tokens)

    def _rejected(text: str) -> str | None:
        ok, reason = validate(text, sources)
        if not ok:
            return reason
        # Contract requires citations on factual answers; a citation-less
        # answer is replaced rather than streamed as authoritative.
        if not CITE.search(text):
            return "no-citation"
        return None

    text = _generate(prompt)
    reason = _rejected(text)
    if reason and generator is not fake_generator:
        # One bounded retry with an explicit citation nudge; small models
        # often answer correctly but drop the [n] markers on the first pass.
        metrics.incr(f"validation.{reason}-retry")
        text = _generate(prompt + "\nOngera usubize, rangiza buri nteruro na [1].")
        reason = _rejected(text)
    if reason:
        metrics.incr(f"validation.{reason}")
        return NO_EVIDENCE_RW, []
    return text, sources


@app.get("/health/live")
def live():
    return {"status": "ok"}


@app.get("/health/ready")
def ready():
    st = get_state()
    return {
        "status": "ready",
        "backend": settings.backend,
        "articles": len(st["articles"]),
        "ollama_model": settings.ollama_model or "fake-gen-v1",
    }


@app.get("/v1/sources/{article_id}")
def source(article_id: int):
    st = get_state()
    art = st["articles"].get(article_id)
    if not art:
        raise HTTPException(status_code=404, detail="Article not found")
    return art


@app.post("/v1/feedback")
def feedback(req: FeedbackRequest):
    metrics.incr("feedback." + ("helpful" if req.helpful else "unhelpful"))
    return {"status": "recorded"}


@app.post("/v1/chat")
async def chat(req: ChatRequest, request: Request):
    if len(req.message) > settings.max_query_chars:
        raise HTTPException(status_code=413, detail="Ubutumwa burarenze urugero.")
    if not req.message.strip():
        raise HTTPException(status_code=422, detail="Ubutumwa ntibushobora kuba ubusa.")
    _check_rate(req.session_id)
    if semaphore.locked():

        async def busy():
            yield 'event: error\ndata: {"message": "Serivisi iruzuye, ongera ugerageze."}\n\n'

        return StreamingResponse(busy(), media_type="text/event-stream")
    filt = {
        "published_after": req.filters.published_after,
        "published_before": req.filters.published_before,
        "category_ids": req.filters.category_ids,
    }

    async def stream():
        yield 'event: retrieval\ndata: {"status": "searching"}\n\n'
        async with semaphore:
            text, sources = answer_question(req.message, filt, req.article_id)
        metrics.incr("requests.chat")
        if not sources:
            metrics.incr("requests.refusal")
        for sentence in text.split(". "):
            yield f"event: token\ndata: {json.dumps({'text': sentence})}\n\n"
        pub = [
            {
                "n": s["n"],
                "wp_id": s["wp_id"],
                "title": s["title"],
                "published_at": s["published_at"],
                "url": s["url"],
            }
            for s in sources
        ]
        yield f"event: sources\ndata: {json.dumps(pub)}\n\n"
        yield (
            "event: done\ndata: "
            + json.dumps({"model": generator.model_id, "retrieval": embedder.model_id})
            + "\n\n"
        )

    return StreamingResponse(stream(), media_type="text/event-stream")
