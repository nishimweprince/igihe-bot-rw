"""Unicode NFC normalization with separate original/search copies."""

from __future__ import annotations

import re
import unicodedata

WS = re.compile(r"\s+")
FOLD = str.maketrans(
    {
        "\u00a0": " ",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
    }
)

NORMALIZATION_VERSION = "norm-v1"


def normalize_original(text: str) -> str:
    text = unicodedata.normalize("NFC", text.replace("\u00a0", " "))
    return WS.sub(" ", text).strip()


def normalize_search(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = text.translate(FOLD)
    text = WS.sub(" ", text.replace("\u00a0", " ")).strip()
    return text.lower()


# Slice heuristic: Kinyarwanda function words and interrogatives that must
# not license an answer by themselves. A refusal gate keyed on raw lexical
# hits would pass any query containing "ni" or "ku".
STOPWORDS = frozenset({
    "ni", "si", "iki", "ikihe", "ibihe", "icyo", "ibyo", "uyo", "uyu",
    "uru", "izi", "izo", "ibi", "iyi", "iyo", "he", "ryari", "gute",
    "ese", "mbese", "ku", "kuri", "mu", "muri", "i", "a", "u", "o", "e",
    "na", "nka", "ngo", "ko", "kandi", "cyangwa", "ariko", "wa", "ya",
    "za", "bya", "bwa", "rya", "rwa", "kwa", "kya", "ejo", "ubu",
    "none", "munsi",
})


def content_terms(text: str) -> list[str]:
    toks = re.findall(r"[a-z0-9']+", text.lower())
    return [t for t in toks if len(t.strip("'")) > 1 and t.strip("'") not in STOPWORDS]
