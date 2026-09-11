"""HTML extraction with a real parser (never regex)."""

from __future__ import annotations

import html as html_mod

from bs4 import BeautifulSoup

BOILERPLATE_SELECTORS = [
    "script",
    "style",
    "form",
    "nav",
    "footer",
    "aside",
    ".share-buttons",
    ".advertisement",
    ".ads",
    ".tracking",
    ".related-posts",
]
BOILERPLATE_PHRASES = ("sangiza", "share this", "advertisement", "subscribe")


def extract(rendered_html: str) -> dict:
    """Return paragraphs/headings/captions or a quarantine record."""
    text_html = html_mod.unescape(rendered_html or "")
    soup = BeautifulSoup(text_html, "lxml")
    for sel in BOILERPLATE_SELECTORS:
        for tag in soup.select(sel):
            tag.decompose()
    blocks: list[tuple[str, str]] = []
    for tag in soup.find_all(["h1", "h2", "h3", "p", "blockquote", "li", "figcaption"]):
        text = tag.get_text(" ", strip=True)
        if not text:
            continue
        lowered = text.lower()
        if any(p in lowered for p in BOILERPLATE_PHRASES) and len(text) < 120:
            continue
        kind = "heading" if tag.name in ("h1", "h2", "h3") else "paragraph"
        blocks.append((kind, text))
    if not blocks:
        # Fallback: line-break layout -> paragraphs.
        raw = soup.get_text("\n", strip=True)
        paras = [p.strip() for p in raw.splitlines() if p.strip()]
        blocks = [("paragraph", p) for p in paras if len(p) > 1]
    total = sum(len(t) for _, t in blocks)
    if not blocks or total < 20:
        return {"status": "quarantined", "reason": "empty", "blocks": []}
    if total > 200_000:
        return {"status": "quarantined", "reason": "enormous", "blocks": []}
    # Drop repeated boilerplate paragraphs.
    seen: set[str] = set()
    deduped = []
    for kind, text in blocks:
        if text in seen and len(text) < 200:
            continue
        seen.add(text)
        deduped.append((kind, text))
    return {"status": "ok", "blocks": deduped}


def rendered_text(post: dict) -> str:
    content = post.get("content") or {}
    return content.get("rendered", "") if isinstance(content, dict) else str(content)


def rendered_title(post: dict) -> str:
    title = post.get("title") or {}
    return title.get("rendered", "") if isinstance(title, dict) else str(title)
