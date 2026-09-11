"""Article-aware chunking with stable UUIDs."""

from __future__ import annotations

import hashlib
import re
import uuid

SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'“(])")

CHUNK_VERSION = "chunk-v1"


def _tokens(text: str) -> int:
    return len(text.split())


def split_sentences(paragraph: str) -> list[str]:
    parts = SENT_SPLIT.split(paragraph.strip())
    return [p.strip() for p in parts if p.strip()]


def chunk_id(wp_id: int, extraction_version: str, index: int, content: str) -> str:
    digest = hashlib.sha256(f"{wp_id}|{extraction_version}|{index}|{content}".encode()).hexdigest()
    return str(uuid.uuid5(uuid.NAMESPACE_URL, digest))


def chunk_article(
    wp_id: int,
    title: str,
    category: str,
    pub_date: str,
    blocks: list[tuple[str, str]],
    extraction_version: str = "extract-v1",
    target_tokens: int = 450,
    max_tokens: int = 600,
    overlap_tokens: int = 80,
) -> list[dict]:
    """Pack blocks into chunks; never split a sentence for a token target."""
    units: list[tuple[str | None, str]] = []
    for kind, text in blocks:
        if kind == "heading":
            units.append((text, ""))
            continue
        for sent in split_sentences(text):
            units.append((None, sent))
    # Short article -> one chunk.
    total = sum(_tokens(t) for _, t in units if t)
    chunks: list[dict] = []
    if total <= max_tokens:
        body = "\n".join(t for _, t in units if t)
        chunks.append(_make(wp_id, title, category, pub_date, blocks, body, 0, extraction_version))
        return chunks
    cur: list[str] = []
    cur_tokens = 0
    heading: str | None = None
    idx = 0
    for h, sent in units:
        if h and not sent:
            heading = h
            continue
        size = _tokens(sent)
        if cur_tokens + size > max_tokens and cur:
            body = "\n".join(cur)
            chunks.append(
                _make(
                    wp_id, title, category, pub_date, blocks, body, idx, extraction_version, heading
                )
            )
            idx += 1
            # Overlap: carry trailing sentences up to overlap_tokens.
            carry: list[str] = []
            carry_tokens = 0
            for s in reversed(cur):
                carry_tokens += _tokens(s)
                carry.append(s)
                if carry_tokens >= overlap_tokens:
                    break
            cur = list(reversed(carry))
            cur_tokens = sum(_tokens(s) for s in cur)
        cur.append(sent)
        cur_tokens += size
    if cur:
        body = "\n".join(cur)
        chunks.append(
            _make(wp_id, title, category, pub_date, blocks, body, idx, extraction_version, heading)
        )
    return chunks


def _make(
    wp_id, title, category, pub_date, blocks, body, idx, extraction_version, heading=None
) -> dict:
    prefix = f"{title} | {category} | {pub_date}"
    if heading:
        prefix += f" | {heading}"
    return {
        "id": chunk_id(wp_id, extraction_version, idx, body),
        "wp_id": wp_id,
        "chunk_index": idx,
        "heading": heading or "",
        "content": body,
        "embed_text": f"{prefix}\n{body}",
        "paragraph_start": 0,
        "paragraph_end": len(blocks),
        "token_count": _tokens(prefix) + _tokens(body),
        "extraction_version": extraction_version,
        "chunk_version": CHUNK_VERSION,
    }
