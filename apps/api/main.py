"""FastAPI contract: /v1/chat SSE, health, sources, feedback."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from igihe_assistant.config import Settings
from igihe_assistant.embeddings.embedder import FakeHashEmbedder
from igihe_assistant.generation.generator import FakeGenerator
from igihe_assistant.generation.mlx_gen import MlxGenerator
from igihe_assistant.generation.ollama_gen import OllamaGenerator
from igihe_assistant.generation.openai_gen import OpenAIGenerator
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
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://igihebot.nishimweprince.dev",
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
settings = Settings()
embedder = FakeHashEmbedder()
fake_generator = FakeGenerator()
if settings.openai_api_key and settings.openai_model:
    generator = OpenAIGenerator(
        settings.openai_model, settings.openai_api_key, settings.openai_base_url
    )
elif settings.mlx_model_path:
    try:
        generator = MlxGenerator(settings.mlx_model_path)
    except Exception:
        # Badly configured local path must degrade, never prevent startup.
        metrics.incr("generator.mlx_config_fallback")
        if settings.ollama_model:
            generator = OllamaGenerator(settings.ollama_model, settings.ollama_base_url)
        else:
            generator = fake_generator
elif settings.ollama_model:
    generator = OllamaGenerator(settings.ollama_model, settings.ollama_base_url)
else:
    generator = fake_generator
semaphore = asyncio.Semaphore(settings.max_concurrent_generations)
_rate: dict[str, list[float]] = {}
_state: dict = {}

log = logging.getLogger("igihe.api")
if not log.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    log.addHandler(_handler)
log.setLevel(logging.INFO)


def _preview(text: str, limit: int = 200) -> str:
    """Message/answer detail for logs. Raw text only when LOG_CONTENT=true."""
    if settings.log_content:
        return text[:limit]
    return f"<{len(text)} chars>"


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
        posts = _load_posts()
        backend, by_id, articles = build_index(posts, embedder)
        _state.update(backend=backend, by_id=by_id, articles=articles)
        log.info(
            "index.ready backend=%s posts=%d articles=%d chunks=%d "
            "embedder=%s generator=%s retrieval=%s",
            settings.backend,
            len(posts),
            len(articles),
            len(by_id),
            embedder.model_id,
            generator.model_id,
            settings.retrieval_candidates,
        )
        if not articles:
            log.warning(
                "index.empty backend=%s posts=%d "
                "hint=SAMPLE_DIR=%r has no page-*.json and no fixtures; "
                "every question will take the refusal path",
                settings.backend,
                len(posts),
                os.environ.get("SAMPLE_DIR", ""),
            )
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
    message: str,
    filters: dict,
    article_id: int | None = None,
    session_id: str = "?",
) -> tuple[str, list[dict]]:
    t0 = time.perf_counter()
    st = get_state()
    backend, by_id = st["backend"], st["by_id"]
    log.info(
        "chat.request session=%s msg=%r article_id=%s filters=%s",
        session_id,
        _preview(message),
        article_id,
        filters,
    )
    if article_id is None:
        terms = content_terms(message)
        # No content-term lexical support in the archive: refuse rather than
        # guess from dense similarity alone (dense always ranks something,
        # and function words like "ni"/"ku" match almost every article).
        lex_hits = backend.lexical(" ".join(terms), 5, filters) if terms else []
        if not terms or not lex_hits:
            metrics.incr("requests.refusal")
            log.info(
                "chat.refusal session=%s reason=no_lexical_support terms=%d "
                "lexical_hits=%d articles_indexed=%d msg=%r",
                session_id,
                len(terms),
                len(lex_hits),
                len(st["articles"]),
                _preview(message),
            )
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
        log.info(
            "chat.refusal session=%s reason=no_sources ranked=%d "
            "articles_indexed=%d msg=%r",
            session_id,
            len(ranked),
            len(st["articles"]),
            _preview(message),
        )
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

    log.info(
        "chat.retrieval session=%s ranked=%d evidence=%d mode=%s",
        session_id,
        len(ranked),
        len(sources),
        settings.retrieval_candidates,
    )

    def _generate(prompt_text: str) -> str:
        g0 = time.perf_counter()
        try:
            text = generator.generate(prompt_text, sources, settings.max_output_tokens)
            log.info(
                "chat.generated session=%s model=%s output_chars=%d "
                "latency_ms=%d",
                session_id,
                generator.model_id,
                len(text),
                int((time.perf_counter() - g0) * 1000),
            )
            return text
        except Exception as exc:
            # Real-model failure must degrade to the fake, never to a 500.
            metrics.incr("generator.ollama_fallback")
            log.warning(
                "chat.generator_fallback session=%s model=%s error=%s",
                session_id,
                generator.model_id,
                type(exc).__name__,
            )
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
        log.info(
            "chat.validation_retry session=%s reason=%s", session_id, reason
        )
        text = _generate(prompt + "\nOngera usubize, rangiza buri nteruro na [1].")
        reason = _rejected(text)
    if reason:
        metrics.incr(f"validation.{reason}")
        log.info(
            "chat.refusal session=%s reason=validation_%s answer=%r",
            session_id,
            reason,
            _preview(text),
        )
        return NO_EVIDENCE_RW, []
    log.info(
        "chat.answer session=%s model=%s sources=%d output_chars=%d "
        "latency_ms=%d",
        session_id,
        generator.model_id,
        len(sources),
        len(text),
        int((time.perf_counter() - t0) * 1000),
    )
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
        "model": generator.model_id,
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
        log.warning(
            "chat.rejected session=%s status=413 msg_chars=%d max=%d",
            req.session_id,
            len(req.message),
            settings.max_query_chars,
        )
        raise HTTPException(status_code=413, detail="Ubutumwa burarenze urugero.")
    if not req.message.strip():
        log.warning("chat.rejected session=%s status=422 reason=empty", req.session_id)
        raise HTTPException(status_code=422, detail="Ubutumwa ntibushobora kuba ubusa.")
    try:
        _check_rate(req.session_id)
    except HTTPException:
        log.warning("chat.rejected session=%s status=429 reason=rate_limit", req.session_id)
        raise
    if semaphore.locked():
        log.warning("chat.rejected session=%s status=busy reason=semaphore", req.session_id)

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
            text, sources = answer_question(
                req.message, filt, req.article_id, session_id=req.session_id
            )
        metrics.incr("requests.chat")
        if not sources:
            metrics.incr("requests.refusal")
        # Stream one sentence per token event, keeping terminal punctuation
        # so the client can join chunks with a single space.
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            if sentence:
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
