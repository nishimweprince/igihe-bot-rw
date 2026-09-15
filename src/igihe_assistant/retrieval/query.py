"""Question -> FTS5 trigram MATCH expressions (+ recency/browse intent).

Trigram matching gives free tolerance to Kinyarwanda inflection: we search
for the full token and for a class-prefix-stripped stem so "abanyeshuri",
"umunyeshuri" and "banyeshuri" all meet on "nyeshuri". Each content term
becomes an OR group (full | stem | translations); the strict expression ANDs
the groups, the loose one ORs them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..normalization.lexicon import translations
from ..normalization.normalize import STOPWORDS, normalize_search

MIN_TERM_CHARS = 3  # trigram tokenizer cannot match shorter strings
MIN_STEM_CHARS = 5

# Noun-class / augment prefixes, longest first. Stripping only happens when a
# useful stem (>= MIN_STEM_CHARS) remains.
CLASS_PREFIXES = (
    "aba", "ama", "ibi", "iby", "iki", "icy", "imi", "umu", "umw", "uru", "urw",
    "inz", "iny", "ing", "aka", "utu", "ubu", "ubw", "aga", "uku", "ugu",
    "gu", "ku", "ba", "mu", "u", "i", "a",
)

# Recency cues. Multi-word phrases are matched on the normalised question.
RECENCY_PHRASES = (
    "uyu munsi", "iki cyumweru", "uku kwezi", "uyu mwaka", "vuba aha",
    "ejo hashize", "muri iki gihe", "iki gihe", "this week", "this month",
    "this year", "these days", "right now",
)
RECENCY_TOKENS = frozenset({
    "ziheruka", "iheruka", "giheruka", "riheruka", "biheruka", "zaheruka",
    "gishya", "bishya", "nshya", "rishya", "zigezweho", "igezweho",
    "bigezweho", "rigezweho", "ubu", "ubungubu", "vuba", "none", "ejo",
    "latest", "recent", "recently", "today", "now", "newest", "current",
})

# Words that name the act of asking for news rather than a topic.
GENERIC_TERMS = frozenset({
    "inkuru", "nkuru", "amakuru", "makuru", "mbwira", "mbwire", "izihe",
    "ikihe", "ibihe", "uwuhe", "ababe", "igihe", "rwanda", "news", "story",
    "stories", "tell", "about", "what", "which", "who", "when", "where",
    "how", "did", "does", "the", "and", "for", "with", "are", "was", "were",
    "have", "has", "any", "some", "there", "happened", "habaye", "byabaye",
    "cyabaye", "yabaye", "ryabaye", "zabaye", "hari", "kuri", "kubyerekeye",
    # interrogatives / copulas / reporting verbs that carry no topic
    "wari", "yari", "bari", "cyari", "byari", "ungana", "angana", "bangana",
    "zingana", "ingana", "ninde", "bande", "kuki", "gute", "ate", "ibiki",
    "nde", "yavuze", "avuga", "bavuga", "yavuzeko", "yatangaje", "batangaje",
    "yakoze", "bakoze", "byavuzwe", "said", "says", "say",
})


@dataclass
class Query:
    raw: str
    terms: list[str] = field(default_factory=list)
    groups: list[list[str]] = field(default_factory=list)
    recency: bool = False
    browse: bool = False

    @property
    def match_strict(self) -> str:
        return to_match(self.groups, "AND")

    @property
    def match_loose(self) -> str:
        return to_match(self.groups, "OR")


def tokens(text: str) -> list[str]:
    """Lowercase alphanumeric tokens; apostrophes split (w'ikawa -> ikawa)."""
    return re.findall(r"[a-z0-9]+", normalize_search(text).replace("'", " "))


def stem(term: str) -> str | None:
    for p in CLASS_PREFIXES:
        if term.startswith(p) and len(term) - len(p) >= MIN_STEM_CHARS:
            return term[len(p):]
    return None


def term_group(term: str) -> list[str]:
    group = [term]
    s = stem(term)
    if s and s not in group:
        group.append(s)
    for alt in translations(term):
        if len(alt) >= MIN_TERM_CHARS and alt not in group:
            group.append(alt)
    return group


def _phrase(t: str) -> str:
    return '"' + t.replace('"', '""') + '"'


def to_match(groups: list[list[str]], op: str) -> str:
    parts = ["(" + " OR ".join(_phrase(t) for t in g) + ")" for g in groups if g]
    return f" {op} ".join(parts)


def analyze(question: str) -> Query:
    norm = normalize_search(question).replace("'", " ")
    recency = False
    for phrase in RECENCY_PHRASES:
        if phrase in norm:
            recency = True
            norm = norm.replace(phrase, " ")
    toks = re.findall(r"[a-z0-9]+", norm)
    terms: list[str] = []
    saw_generic = False
    for t in toks:
        if t in RECENCY_TOKENS:
            recency = True
            continue
        if t in STOPWORDS or t in GENERIC_TERMS:
            saw_generic = saw_generic or t in GENERIC_TERMS
            continue
        if len(t) < MIN_TERM_CHARS or t in terms:
            continue
        terms.append(t)
    q = Query(raw=question, terms=terms, recency=recency)
    q.groups = [term_group(t) for t in terms]
    q.browse = not terms and (recency or saw_generic)
    return q


def coverage(text: str, groups: list[list[str]]) -> float:
    """Share of query term weight (by length) present in `text`."""
    if not groups:
        return 0.0
    low = text.lower()
    total = sum(len(g[0]) for g in groups)
    hit = sum(len(g[0]) for g in groups if any(alt in low for alt in g))
    return hit / total if total else 0.0
