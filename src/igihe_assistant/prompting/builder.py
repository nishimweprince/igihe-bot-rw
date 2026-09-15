"""Prompt contract: delimited untrusted evidence, [n] citations."""

from __future__ import annotations

import html
import re

SYSTEM_KINYARWANDA = (
    "Urasubiza mu Kinyarwanda cyoroshye kandi cya bugufi, "
    "nk'uko waganira na mugenzi wawe. Koresha GUSA ibimenyetso biri hasi. "
    "Subiza mu nteruro 1-3 ngufi; buri nteruro ivuga ukuri irangira na "
    "[1] cyangwa [2]. "
    "Niba ibimenyetso bidahagije, subiza gusa: Mbabarira, nta bimenyetso bihagije. "
    "Ntusubiremo ibimenyetso uko byakabaye; subiza ikibazo gusa."
)

REFUSAL_SHORT = "Mbabarira, nta bimenyetso bihagije."

# Template sentences that must never appear verbatim in an answer. The small
# demo model sometimes echoes instructions instead of answering; ordinary
# answers never contain these exact strings. Keep in sync with the template.
ECHO_PHRASES = (
    "Urasubiza mu Kinyarwanda cyoroshye",
    "waganira na mugenzi wawe",
    "Koresha GUSA ibimenyetso biri hasi",
    "Ntusubiremo ibimenyetso uko byakabaye",
    "Subiza mu nteruro 1-3 ngufi",
    "nko kuganira",
    "Urugero: Abahinga bazacibwa amande [1].",
    "Ongera usubize, rangiza buri nteruro na [1].",
    "Ibimenyetso:",
)

NO_EVIDENCE_RW = (
    "Mbabarira, nta bimenyetso bihagije mbona mu nkuru za IGIHE zo gusubiza "
    "icyo kibazo. Reba inkuru z'umwimerere kuri "
    "[IGIHE](https://old.igihe.com). "
    "Nzikwereka hasi inkuru zegereye ikibazo cyawe, ariko si ibisubizo nyabyo."
)

#: Broad, always-answerable prompts used when nothing close was retrieved.
FALLBACK_SUGGESTIONS = [
    "Mbwira inkuru ziheruka.",
    "Ni izihe nkuru zigezweho mu Rwanda?",
    "Habaye iki mu mupira w'amaguru?",
]

#: Backwards-compatible alias; prefer FALLBACK_SUGGESTIONS.
NO_CLOSE_MATCH_SUGGESTIONS = FALLBACK_SUGGESTIONS

SUGGESTION_MAX_CHARS = 80


def follow_up_suggestions(closest: list[dict], limit: int = 3) -> list[str]:
    """Sendable prompts for a refusal: near-match headlines, then fallbacks.

    A headline is the strongest possible query for its own article — it is
    exactly the lexical support the retriever needs — so clicking one lands
    on real content instead of re-refusing.
    """
    out: list[str] = []
    seen: set[str] = set()
    for source in closest:
        raw = source.get("title", "") if isinstance(source, dict) else ""
        title = re.sub(r"\s+", " ", html.unescape(str(raw))).strip()
        if not title or len(title) > SUGGESTION_MAX_CHARS:
            continue
        key = title.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(title)
        if len(out) >= limit:
            return out
    for fallback in FALLBACK_SUGGESTIONS:
        key = fallback.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(fallback)
        if len(out) >= limit:
            break
    return out


NO_CLOSE_MATCH_RW = (
    "Mbabarira, nta bimenyetso bihagije mbona mu nkuru za IGIHE zo gusubiza "
    "icyo kibazo. Reba inkuru z'umwimerere kuri "
    "[IGIHE](https://old.igihe.com)."
)


def build_evidence_block(sources: list[dict]) -> str:
    parts = []
    for i, s in enumerate(sources, start=1):
        parts.append(
            f"[{i}] id={s['wp_id']} title={s['title']} date={s['published_at']} "
            f"url={s['url']}\n{s['content']}"
        )
    return "\n\n".join(parts)


def build_messages(question: str, sources: list[dict]) -> tuple[str, str]:
    """System + user messages for chat-templated models (Ollama /api/chat)."""
    user = (
        "Ibimenyetso:\n"
        f"{build_evidence_block(sources)}\n\n"
        f"Ikibazo: {question}\n"
        "Subiza mu nteruro 1-3 ngufi, mu Kinyarwanda cyoroshye nko kuganira; "
        "koresha gusa ibimenyetso; rangiza interuro na [1]. "
        "Urugero: Abahinga bazacibwa amande [1].\n"
        "Igisubizo:"
    )
    return SYSTEM_KINYARWANDA, user


def build_prompt(question: str, sources: list[dict]) -> str:
    system, user = build_messages(question, sources)
    return f"{system}\n\n{user}"
