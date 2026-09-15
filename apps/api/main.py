"""FastAPI contract: /v1/chat SSE, health, sources, feedback."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from igihe_assistant.config import Settings
from igihe_assistant.generation.factory import build_generator
from igihe_assistant.generation.generator import FakeGenerator
from igihe_assistant.generation.streaming import stream_tokens
from igihe_assistant.generation.validator import CITE, validate
from igihe_assistant.observability import metrics
from igihe_assistant.pipeline import build_index
from igihe_assistant.prompting.builder import (
    ECHO_PHRASES,
    NO_CLOSE_MATCH_RW,
    NO_EVIDENCE_RW,
    build_messages,
    follow_up_suggestions,
)
from igihe_assistant.retrieval.query import Query, analyze, term_group
from igihe_assistant.retrieval.rank import Candidate, evidence_coverage, retrieve
from igihe_assistant.retrieval.store import IndexStore

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "wp"
RETRIEVAL_ID = "trigram-fts5"

log = logging.getLogger("igihe.api")
_root = logging.getLogger("igihe")  # igihe.api, igihe.mlx, ... share one handler
if not _root.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    _root.addHandler(_handler)
_root.setLevel(logging.INFO)

settings = Settings()
fake_generator = FakeGenerator()
try:
    generator = build_generator(settings)
except FileNotFoundError as exc:
    # A missing local checkpoint degrades to the fake so the API still
    # starts; an unknown GENERATOR value is a config error and raises.
    metrics.incr("generator.config_fallback")
    log.warning("generator.config_fallback error=%s", exc)
    generator = fake_generator
semaphore = asyncio.Semaphore(max(settings.max_concurrent_generations, 1))
_rate: dict[str, list[float]] = {}
_state: dict = {}


def _preview(text: str, limit: int = 200) -> str:
    """Message/answer detail for logs. Raw text only when LOG_CONTENT=true."""
    if settings.log_content:
        return text[:limit]
    return f"<{len(text)} chars>"


def _load_posts() -> list[dict]:
    if settings.sample_dir:
        posts = []
        for path in sorted(Path(settings.sample_dir).glob("page-*.json")):
            posts.extend(json.loads(path.read_text(encoding="utf-8")))
        if posts:
            return posts
    posts = []
    for path in sorted(FIXTURES.glob("*.json")):
        posts.append(json.loads(path.read_text(encoding="utf-8")))
    return posts


def get_state() -> dict:
    if "store" not in _state:
        if settings.index_path:
            store = IndexStore(settings.index_path, cache_mb=settings.sqlite_cache_mb)
            source = settings.index_path
        else:
            store = build_index(_load_posts())
            source = settings.sample_dir or "fixtures"
        _state["store"] = store
        _state["source"] = source
        stats = store.stats()
        log.info(
            "index.ready source=%s articles=%d chunks=%d newest=%s generator=%s retrieval=%s",
            source,
            stats["articles"],
            stats["chunks"],
            stats["max_published_at"],
            generator.model_id,
            RETRIEVAL_ID,
        )
        if not stats["articles"]:
            log.warning(
                "index.empty source=%s hint=no articles indexed; every question "
                "will take the refusal path",
                source,
            )
    return _state


@asynccontextmanager
async def lifespan(_app: FastAPI):
    get_state()
    if settings.warmup and hasattr(generator, "load"):
        try:
            t0 = time.perf_counter()
            await asyncio.to_thread(generator.load)
            await asyncio.to_thread(
                generator.generate, "Subiza: yego.", [{"role": "user", "content": "Yego?"}], 5
            )
            log.info("generator.warm model=%s ms=%d", generator.model_id,
                     int((time.perf_counter() - t0) * 1000))
        except Exception as exc:  # noqa: BLE001 - warm-up must never block startup
            log.warning("generator.warmup_failed model=%s error=%s", generator.model_id, exc)
    yield


app = FastAPI(title="igihe-assistant", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://igihebot.nishimweprince.dev"],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class Filters(BaseModel):
    published_after: str | None = None
    published_before: str | None = None
    category_ids: list = Field(default_factory=list)


class Turn(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    session_id: str
    message: str
    article_id: int | None = None
    filters: Filters = Field(default_factory=Filters)
    history: list[Turn] = Field(default_factory=list)


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


CLOSE_MATCH_N = 3


@dataclass
class Prepared:
    """Everything the streaming loop needs; retrieval done, nothing generated."""

    query: Query | None
    question: str = ""
    sources: list[dict] = field(default_factory=list)  # prompt copy (trimmed)
    closest: list[dict] = field(default_factory=list)  # near matches for refusals
    suggestions: list[str] = field(default_factory=list)
    refusal: str | None = None
    system: str = ""
    messages: list[dict] = field(default_factory=list)
    browse: bool = False

    @property
    def public_sources(self) -> list[dict]:
        return [_public(s) for s in (self.sources if self.refusal is None else self.closest)]


def _public(s: dict) -> dict:
    return {k: s[k] for k in ("n", "wp_id", "title", "published_at", "url")}


def _sources_from(cands: list[Candidate], store: IndexStore) -> list[dict]:
    arts = store.get_articles([c.wp_id for c in cands])
    out = []
    for c in cands:
        art = arts.get(c.wp_id)
        if not art:
            continue
        out.append(
            {
                "n": len(out) + 1,
                "wp_id": c.wp_id,
                "title": art["title"],
                "published_at": art["published_at"],
                "url": art["url"],
                "content": c.chunk["content"],
            }
        )
    return out


def _refusal(prep: Prepared, closest: list[dict]) -> Prepared:
    prep.closest = [{**s, "n": i + 1} for i, s in enumerate(closest[:CLOSE_MATCH_N])]
    prep.refusal = NO_EVIDENCE_RW if prep.closest else NO_CLOSE_MATCH_RW
    prep.suggestions = follow_up_suggestions(prep.closest)
    if prep.closest:
        metrics.incr("requests.close_match")
    return prep


def _with_context(q: Query, history: list[dict]) -> Query:
    """Cheap coreference: a one-term follow-up borrows the previous question's terms."""
    if len(q.terms) >= 2 or not history:
        return q
    prev = [m for m in history if m.get("role") == "user"]
    if not prev:
        return q
    for t in analyze(prev[-1].get("content", "")).terms:
        if t not in q.terms:
            q.terms.append(t)
            q.groups.append(term_group(t))
    q.browse = False
    return q


def prepare_answer(
    message: str,
    filters: dict,
    article_id: int | None = None,
    history: list[dict] | None = None,
    session_id: str = "?",
) -> Prepared:
    st = get_state()
    store: IndexStore = st["store"]
    history = history or []
    log.info(
        "chat.request session=%s msg=%r article_id=%s filters=%s history=%d",
        session_id, _preview(message), article_id, filters, len(history),
    )
    if article_id is not None:
        chunks = store.chunks_for_article(article_id)[:6]
        art = store.get_article(article_id)
        prep = Prepared(query=None, question=message)
        if not chunks or not art:
            return _refusal(prep, [])
        prep.sources = [
            {
                "n": i + 1,
                "wp_id": article_id,
                "title": art["title"],
                "published_at": art["published_at"],
                "url": art["url"],
                "content": ch["content"],
            }
            for i, ch in enumerate(chunks)
        ]
    else:
        q = _with_context(analyze(message), history)
        cands = retrieve(
            q,
            store,
            filters,
            candidates_n=settings.candidates_n,
            final_n=6,
            recency_weight=settings.recency_weight,
            half_life_days=settings.recency_half_life_days,
            recency_window_days=settings.recency_window_days,
        )
        prep = Prepared(query=q, question=message, browse=q.browse)
        top_cov = evidence_coverage(cands, q)
        if not cands or (not q.browse and top_cov < settings.min_coverage):
            metrics.incr("requests.refusal")
            log.info(
                "chat.refusal session=%s reason=no_lexical_support terms=%d "
                "candidates=%d coverage=%.2f articles_indexed=%d msg=%r",
                session_id, len(q.terms), len(cands), top_cov,
                store.stats()["articles"], _preview(message),
            )
            return _refusal(prep, _sources_from(cands, store))
        prep.sources = _sources_from(cands, store)
        if not prep.sources:
            return _refusal(prep, [])
    # Evidence budget for the model: small local models lose the citation
    # instruction over long contexts. Citations still resolve to full
    # articles; only the prompt copy is trimmed.
    prep.sources = prep.sources[: settings.max_evidence_sources]
    if settings.max_evidence_chars > 0:
        prep.sources = [
            {**s, "content": s["content"][: settings.max_evidence_chars]} for s in prep.sources
        ]
    prep.system, prep.messages = build_messages(
        message, prep.sources, history, history_turns=settings.history_turns, browse=prep.browse
    )
    log.info(
        "chat.retrieval session=%s evidence=%d browse=%s recency=%s",
        session_id, len(prep.sources), prep.browse,
        bool(prep.query and prep.query.recency),
    )
    return prep


def _rejected(text: str, sources: list[dict], question: str = "") -> str | None:
    ok, reason = validate(text, sources, question)
    if not ok:
        return reason
    # Contract requires citations on factual answers; a citation-less
    # answer is replaced rather than streamed as authoritative.
    if not CITE.search(text):
        return "no-citation"
    return None


def _incremental_reject(partial: str, sources: list[dict]) -> str | None:
    """Cheap checks that are safe on a prefix (no URL check: may be partial)."""
    low = partial.lower()
    if any(p.lower() in low for p in ECHO_PHRASES):
        return "evidence-echo"
    nums = [int(n) for n in CITE.findall(partial)]
    if nums and max(nums) > len(sources):
        return "unknown-citation"
    return None


RETRY_NUDGE = "\nOngera usubize mu Kinyarwanda, rangiza buri nteruro na [1]."


def _generate_sync(prep: Prepared, session_id: str, nudge: str = "") -> str:
    messages = prep.messages
    if nudge:
        messages = [*messages[:-1], {**messages[-1], "content": messages[-1]["content"] + nudge}]
    g0 = time.perf_counter()
    try:
        text = generator.generate(prep.system, messages, settings.max_output_tokens)
    except Exception as exc:  # noqa: BLE001 - real-model failure degrades to the fake
        metrics.incr("generator.fallback")
        log.warning(
            "chat.generator_fallback session=%s model=%s error=%s",
            session_id, generator.model_id, type(exc).__name__,
        )
        text = fake_generator.generate(prep.system, messages, settings.max_output_tokens)
    log.info(
        "chat.generated session=%s model=%s output_chars=%d latency_ms=%d",
        session_id, generator.model_id, len(text), int((time.perf_counter() - g0) * 1000),
    )
    return text


def answer_question(
    message: str,
    filters: dict,
    article_id: int | None = None,
    session_id: str = "?",
    history: list[dict] | None = None,
) -> tuple[str, list[dict], list[str]]:
    """Synchronous full path (tests, evals): (text, sources, suggestions)."""
    t0 = time.perf_counter()
    prep = prepare_answer(message, filters, article_id, history, session_id)
    if prep.refusal is not None:
        return prep.refusal, prep.public_sources, prep.suggestions
    text = _generate_sync(prep, session_id)
    reason = _rejected(text, prep.sources, prep.question)
    if reason and settings.validation_retry and not isinstance(generator, FakeGenerator):
        metrics.incr(f"validation.{reason}-retry")
        text = _generate_sync(prep, session_id, RETRY_NUDGE)
        reason = _rejected(text, prep.sources, prep.question)
    if reason:
        metrics.incr(f"validation.{reason}")
        log.info("chat.refusal session=%s reason=validation_%s answer=%r",
                 session_id, reason, _preview(text))
        _refusal(prep, prep.sources)
        return prep.refusal, prep.public_sources, prep.suggestions
    log.info(
        "chat.answer session=%s model=%s sources=%d output_chars=%d latency_ms=%d",
        session_id, generator.model_id, len(prep.sources), len(text),
        int((time.perf_counter() - t0) * 1000),
    )
    return text, prep.public_sources, []


@app.get("/health/live")
def live():
    return {"status": "ok"}


@app.get("/health/ready")
def ready():
    st = get_state()
    stats = st["store"].stats()
    return {
        "status": "ready",
        "index": st["source"],
        "articles": stats["articles"],
        "chunks": stats["chunks"],
        "newest": stats["max_published_at"],
        "model": generator.model_id,
        "retrieval": RETRIEVAL_ID,
    }


@app.get("/v1/sources/{article_id}")
def source(article_id: int):
    art = get_state()["store"].get_article(article_id)
    if not art:
        raise HTTPException(status_code=404, detail="Article not found")
    return art


@app.post("/v1/feedback")
def feedback(req: FeedbackRequest):
    metrics.incr("feedback." + ("helpful" if req.helpful else "unhelpful"))
    return {"status": "recorded"}


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/v1/chat")
async def chat(req: ChatRequest, request: Request):
    if len(req.message) > settings.max_query_chars:
        log.warning("chat.rejected session=%s status=413 msg_chars=%d max=%d",
                    req.session_id, len(req.message), settings.max_query_chars)
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
            yield _sse("error", {"message": "Serivisi iruzuye, ongera ugerageze."})

        return StreamingResponse(busy(), media_type="text/event-stream")
    filt = {
        "published_after": req.filters.published_after,
        "published_before": req.filters.published_before,
        "category_ids": req.filters.category_ids,
    }
    history = [{"role": t.role, "content": t.content} for t in req.history]

    async def stream():
        t0 = time.perf_counter()
        yield _sse("retrieval", {"status": "searching"})
        prep = await asyncio.to_thread(
            prepare_answer, req.message, filt, req.article_id, history, req.session_id
        )
        metrics.incr("requests.chat")
        if prep.refusal is None:
            async for event in _stream_answer(prep, req.session_id, request, t0):
                yield event
        else:
            yield _sse("token", {"text": prep.refusal})
        yield _sse("sources", prep.public_sources)
        if prep.suggestions:
            yield _sse("suggestions", {"suggestions": prep.suggestions})
        yield _sse("done", {"model": generator.model_id, "retrieval": RETRIEVAL_ID})

    return StreamingResponse(stream(), media_type="text/event-stream")


async def _stream_answer(prep: Prepared, session_id: str, request: Request, t0: float):
    """Stream tokens live; validate incrementally and at the end.

    On any validation failure the client receives `event: replace` with the
    refusal text (or, when VALIDATION_RETRY is on, a buffered second answer),
    and `prep` is switched to the refusal state so the caller emits near
    matches + suggestions instead of the sources.
    """
    acc = ""
    reason: str | None = None
    cancel = asyncio.Event()
    async with semaphore:
        g0 = time.perf_counter()
        try:
            async for piece in stream_tokens(
                generator, prep.system, prep.messages, settings.max_output_tokens, cancel=cancel
            ):
                acc += piece
                yield _sse("token", {"text": piece})
                reason = _incremental_reject(acc, prep.sources)
                if reason:
                    cancel.set()
                    break
                if await request.is_disconnected():
                    cancel.set()
                    log.info("chat.disconnected session=%s", session_id)
                    return
        except Exception as exc:  # noqa: BLE001 - degrade to the fake, never a 500
            metrics.incr("generator.fallback")
            log.warning("chat.generator_fallback session=%s model=%s error=%s",
                        session_id, generator.model_id, type(exc).__name__)
            acc = fake_generator.generate(prep.system, prep.messages, settings.max_output_tokens)
            yield _sse("replace", {"text": acc, "reason": "generator-fallback"})
        log.info("chat.generated session=%s model=%s output_chars=%d latency_ms=%d",
                 session_id, generator.model_id, len(acc), int((time.perf_counter() - g0) * 1000))
        reason = reason or _rejected(acc, prep.sources, prep.question)
        if reason and settings.validation_retry and not isinstance(generator, FakeGenerator):
            metrics.incr(f"validation.{reason}-retry")
            log.info("chat.validation_retry session=%s reason=%s", session_id, reason)
            acc = await asyncio.to_thread(_generate_sync, prep, session_id, RETRY_NUDGE)
            reason = _rejected(acc, prep.sources, prep.question)
            if not reason:
                yield _sse("replace", {"text": acc, "reason": "retry"})
    if reason:
        metrics.incr(f"validation.{reason}")
        log.info("chat.refusal session=%s reason=validation_%s answer=%r",
                 session_id, reason, _preview(acc))
        _refusal(prep, prep.sources)
        yield _sse("replace", {"text": prep.refusal, "reason": reason})
        return
    log.info(
        "chat.answer session=%s model=%s sources=%d output_chars=%d latency_ms=%d",
        session_id, generator.model_id, len(prep.sources), len(acc),
        int((time.perf_counter() - t0) * 1000),
    )
