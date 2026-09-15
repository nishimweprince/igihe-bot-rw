"""Cheap Kinyarwanda-vs-English drift detector for generated answers.

Not a general language identifier: it only needs to catch a small model
answering in English when the question and evidence were Kinyarwanda.
Scores are function-word and orthography hits per token.
"""

from __future__ import annotations

import re

RW_FUNCTION = frozenset(
    {
        "ni",
        "mu",
        "ku",
        "na",
        "ya",
        "wa",
        "za",
        "bya",
        "cya",
        "rya",
        "ko",
        "ngo",
        "ariko",
        "kandi",
        "cyangwa",
        "uyu",
        "iyi",
        "iki",
        "uwo",
        "icyo",
        "ibyo",
        "muri",
        "kuri",
        "nta",
        "hari",
        "yari",
        "bari",
        "kuko",
        "nyuma",
        "mbere",
        "ubwo",
        "igihe",
        "ibi",
        "izi",
        "aba",
        "abo",
        "buri",
        "gusa",
        "cyane",
        "nka",
        "nk",
        "n",
        "w",
        "y",
        "b",
        "z",
        "cy",
        "ry",
        "bw",
        "rw",
        "tw",
    }
)
EN_FUNCTION = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "or",
        "but",
        "of",
        "to",
        "in",
        "on",
        "at",
        "for",
        "with",
        "by",
        "from",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "has",
        "have",
        "had",
        "that",
        "this",
        "these",
        "those",
        "it",
        "its",
        "as",
        "not",
        "will",
        "would",
        "can",
        "could",
        "there",
        "their",
        "they",
        "he",
        "she",
        "we",
        "you",
        "which",
        "who",
        "what",
        "when",
        "where",
        "about",
        "into",
        "than",
        "then",
        "also",
        "more",
        "most",
        "some",
        "any",
        "all",
        "no",
    }
)
# Letter sequences that are common in Kinyarwanda and rare in English.
RW_ORTHO = re.compile(
    r"(nya|nye|nyi|nyo|nyu|mwa|mwe|rwa|rwe|bwa|bwe|byo|bya|shy|cy[aeiou]|jy[aeiou]"
    r"|zwa|kw[aei]|gw[aei]|mbw|nkw)"
)


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z']+", text.lower())


def kinyarwanda_score(text: str) -> float:
    """> 0 leans Kinyarwanda, < 0 leans English; 0 for empty text."""
    toks = _tokens(text)
    if not toks:
        return 0.0
    rw = sum(1 for t in toks for part in t.split("'") if part in RW_FUNCTION)
    en = sum(1 for t in toks if t in EN_FUNCTION)
    ortho = len(RW_ORTHO.findall(" ".join(toks)))
    return (rw + ortho - 2 * en) / len(toks)


def is_drifted(text: str, min_en_hits: int = 3) -> bool:
    """True when the answer reads as English rather than Kinyarwanda."""
    toks = _tokens(text)
    en = sum(1 for t in toks if t in EN_FUNCTION)
    if en < min_en_hits:
        return False
    return kinyarwanda_score(text) < 0
