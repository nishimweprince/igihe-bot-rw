"""Prompt contract: delimited untrusted evidence, [n] citations."""

from __future__ import annotations

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
    "icyo kibazo. Ongera ubaze mu yandi magambo cyangwa ubaze ikindi."
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
