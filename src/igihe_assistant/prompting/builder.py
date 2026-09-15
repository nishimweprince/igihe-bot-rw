"""Prompt contract: Kinyarwanda system turn, few-shots, delimited evidence.

Everything the model sees is built here so the validator's echo detection
(`ECHO_PHRASES`) can stay in sync with the exact template sentences.
"""

from __future__ import annotations

import html
import re

Message = dict[str, str]  # {"role": "user" | "assistant", "content": str}

REFUSAL_SHORT = "Mbabarira, nta bimenyetso bihagije."

SYSTEM_RW = (
    "Uri umufasha w'amakuru wa IGIHE. Usubiza mu Kinyarwanda gusa, mu magambo "
    "yawe bwite, mu buryo bugufi kandi bworoshye nk'uganira n'inshuti. "
    "Koresha gusa ibimenyetso (inkuru) wahawe; ntukongeremo ibyo utahawe kandi "
    "ntugakoporore inkuru uko yakabaye. "
    "Subiza mu nteruro 1-3 ngufi; buri nteruro ivuga ukuri irangira n'inomero "
    "y'inkuru yavuyemo nka [1] cyangwa [2]. Ntushyiremo URL. "
    f"Niba ibimenyetso bidasubiza ikibazo, andika gusa: {REFUSAL_SHORT}"
)

# Backwards-compatible alias (older tests/docs import this name).
SYSTEM_KINYARWANDA = SYSTEM_RW

USER_INSTRUCTION = (
    "Subiza mu Kinyarwanda mu nteruro 1-3 ngufi, ukoresheje gusa ibimenyetso; "
    "rangiza buri nteruro na [n]."
)

BROWSE_INSTRUCTION = (
    "Tanga incamake ngufi y'inkuru ziheruka ziri mu bimenyetso by'iki kibazo "
    "gusa, interuro 2-4, buri nteruro ivuga inkuru imwe irangira na [n]."
)

# Few-shot pairs on fictional-but-plausible stories. The answer sentences are
# deliberately distinctive so an echoed few-shot is caught by ECHO_PHRASES.
FEW_SHOT_SOURCES: list[list[dict]] = [
    [
        {
            "n": 1,
            "title": "Nyagatare igiye kubaka isoko rishya rya Karama",
            "published_at": "2025-03-04T09:00:00",
            "content": (
                "Akarere ka Nyagatare kagiye kubaka isoko rishya mu Murenge wa "
                "Karama. Isoko riteganyijwe gutwara miliyari 2 z'amafaranga y'u "
                "Rwanda kandi rizarangira mu mpera za 2026. Rizafasha abahinzi "
                "n'abacuruzi bo mu Karere."
            ),
        }
    ],
    [
        {
            "n": 1,
            "title": "Gasabo United yatsinze Kicukiro FC 3-1",
            "published_at": "2025-05-18T18:00:00",
            "content": (
                "Gasabo United yatsinze Kicukiro FC ibitego 3-1 mu mukino wabereye "
                "kuri Stade ya Remera. Ibitego byatsinzwe na Mugisha (2) na Habimana."
            ),
        },
        {
            "n": 2,
            "title": "Umutoza wa Gasabo United yashimye abakinnyi",
            "published_at": "2025-05-19T08:00:00",
            "content": (
                "Umutoza wa Gasabo United yavuze ko abakinnyi be bagaragaje umuhate "
                "udasanzwe kandi ko bazakomeza kwitegura shampiyona."
            ),
        },
    ],
    [
        {
            "n": 1,
            "title": "Umuhanda Rubavu-Nyabihu ugiye gusanwa",
            "published_at": "2025-02-10T10:00:00",
            "content": (
                "Umuhanda uhuza Rubavu na Nyabihu ugiye gusanwa mu mezi atandatu "
                "ari imbere. Imirimo izatangira mu kwezi gutaha."
            ),
        }
    ],
]
# Browse-mode example: a cited round-up of the newest stories.
FEW_SHOT_BROWSE_SOURCES: list[dict] = [
    {
        "n": 1,
        "title": "Huye: hafunguwe ikigo gishya cy'ubuvuzi",
        "published_at": "2025-06-02T08:00:00",
        "content": (
            "Ikigo gishya cy'ubuvuzi cyafunguwe mu Karere ka Huye, kizakira abarwayi 200 "
            "ku munsi."
        ),
    },
    {
        "n": 2,
        "title": "Ikipe y'igihugu yatangiye imyitozo",
        "published_at": "2025-06-02T07:00:00",
        "content": (
            "Amavubi yatangiye imyitozo yo kwitegura umukino wa Kenya uzaba ku wa Gatandatu."
        ),
    },
    {
        "n": 3,
        "title": "Ibiciro by'amavuta yagabanutse",
        "published_at": "2025-06-01T18:00:00",
        "content": (
            "Ibiciro by'amavuta ya moteri byagabanutseho amafaranga 40 kuri litiro guhera ejo."
        ),
    },
]
FEW_SHOT_BROWSE: tuple[str, str] = (
    "Mbwira inkuru ziheruka",
    "Huye hafunguwe ikigo gishya cy'ubuvuzi kizakira abarwayi 200 ku munsi [1]. "
    "Amavubi yatangiye imyitozo yo kwitegura umukino wa Kenya [2]. "
    "Ibiciro by'amavuta ya moteri byagabanutseho amafaranga 40 kuri litiro [3].",
)

FEW_SHOTS: list[tuple[str, str]] = [
    (
        "Isoko rishya rya Karama rizatwara amafaranga angahe?",
        "Isoko rishya rya Karama riteganyijwe gutwara miliyari 2 z'amafaranga "
        "y'u Rwanda kandi rizarangira mu mpera za 2026 [1].",
    ),
    (
        "Gasabo United yakinnye ite?",
        "Gasabo United yatsinze Kicukiro FC ibitego 3-1 kuri Stade ya Remera [1]. "
        "Umutoza wayo yashimiye abakinnyi umuhate bagaragaje [2].",
    ),
    (
        "Igiciro cy'ikawa i Huye ni angahe?",
        REFUSAL_SHORT,
    ),
]

# Template sentences that must never appear verbatim in an answer.
ECHO_PHRASES = (
    "Uri umufasha w'amakuru wa IGIHE",
    "Usubiza mu Kinyarwanda gusa, mu magambo yawe bwite",
    "Koresha gusa ibimenyetso (inkuru) wahawe",
    "ntugakoporore inkuru uko yakabaye",
    "Subiza mu nteruro 1-3 ngufi",
    "rangiza buri nteruro na [n]",
    "Tanga incamake ngufi y'inkuru ziheruka ziri mu bimenyetso",
    "Ibimenyetso:",
    "Ikibazo:",
    "Isoko rishya rya Karama riteganyijwe gutwara miliyari 2",
    "Gasabo United yatsinze Kicukiro FC ibitego 3-1 kuri Stade ya Remera",
    "Umutoza wayo yashimiye abakinnyi umuhate bagaragaje",
    "Huye hafunguwe ikigo gishya cy'ubuvuzi kizakira abarwayi 200",
    "Amavubi yatangiye imyitozo yo kwitegura umukino wa Kenya [2]",
    # Fictional few-shot entities: any of these in an answer is a leak.
    "isoko rishya rya Karama",
    "Gasabo United",
    "Kicukiro FC",
    "Rubavu-Nyabihu",
)

NO_EVIDENCE_RW = (
    "Mbabarira, nta bimenyetso bihagije mbona mu nkuru za IGIHE zo gusubiza "
    "icyo kibazo. Reba inkuru z'umwimerere kuri "
    "[IGIHE](https://old.igihe.com). "
    "Nzikwereka hasi inkuru zegereye ikibazo cyawe, ariko si ibisubizo nyabyo."
)

NO_CLOSE_MATCH_RW = (
    "Mbabarira, nta bimenyetso bihagije mbona mu nkuru za IGIHE zo gusubiza "
    "icyo kibazo. Reba inkuru z'umwimerere kuri "
    "[IGIHE](https://old.igihe.com)."
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


def build_evidence_block(sources: list[dict]) -> str:
    parts = []
    for i, s in enumerate(sources, start=1):
        date = str(s.get("published_at", ""))[:10]
        parts.append(f"[{i}] {s['title']} ({date})\n{s['content']}")
    return "\n\n".join(parts)


_EVIDENCE_HEAD = re.compile(r"^\[(\d+)\] (.+?) \((\d{4}-\d{2}-\d{2})?\)$", re.M)


def parse_evidence_block(user_content: str) -> list[dict]:
    """Inverse of `build_evidence_block` (used by the fake generator)."""
    if "Ibimenyetso:\n" not in user_content:
        return []
    block = user_content.split("Ibimenyetso:\n", 1)[1].split("\n\nIkibazo:", 1)[0]
    heads = list(_EVIDENCE_HEAD.finditer(block))
    out = []
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(block)
        out.append(
            {
                "n": int(m.group(1)),
                "title": m.group(2),
                "published_at": m.group(3) or "",
                "content": block[m.end() : end].strip(),
            }
        )
    return out


def _user_turn(question: str, sources: list[dict], instruction: str) -> str:
    return f"Ibimenyetso:\n{build_evidence_block(sources)}\n\nIkibazo: {question}\n{instruction}"


def _trim_history(history: list[Message] | tuple, turns: int, max_chars: int) -> list[Message]:
    out: list[Message] = []
    for m in list(history)[-turns:]:
        role = m.get("role")
        content = (m.get("content") or "").strip()
        if role not in ("user", "assistant") or not content:
            continue
        # Keep roles alternating; drop a repeated role's older message.
        if out and out[-1]["role"] == role:
            out.pop()
        out.append({"role": role, "content": content[:max_chars]})
    if out and out[0]["role"] == "assistant":
        out.pop(0)
    if out and out[-1]["role"] == "user":
        out.pop()
    return out


def build_messages(
    question: str,
    sources: list[dict],
    history: list[Message] | tuple = (),
    *,
    history_turns: int = 6,
    history_chars: int = 400,
    browse: bool = False,
    few_shots: bool = True,
) -> tuple[str, list[Message]]:
    """System text + chat turns for chat-templated models.

    Layout: few-shot pairs, then the conversation's last turns, then the
    user turn carrying the evidence block, the question and a one-line
    reminder. The system prompt is stated once (Gemma has a real system role).
    """
    messages: list[Message] = []
    if few_shots:
        shots = list(zip(FEW_SHOT_SOURCES, FEW_SHOTS, strict=True))
        instructions = [USER_INSTRUCTION] * len(shots)
        if browse:
            # One round-up example only: with more examples in context the
            # small model rounds up *their* stories too.
            shots = [(FEW_SHOT_BROWSE_SOURCES, FEW_SHOT_BROWSE)]
            instructions = [BROWSE_INSTRUCTION]
        for (srcs, (q, a)), instr in zip(shots, instructions, strict=True):
            messages.append({"role": "user", "content": _user_turn(q, srcs, instr)})
            messages.append({"role": "assistant", "content": a})
    messages.extend(_trim_history(history, history_turns, history_chars))
    instruction = BROWSE_INSTRUCTION if browse else USER_INSTRUCTION
    messages.append({"role": "user", "content": _user_turn(question, sources, instruction)})
    return SYSTEM_RW, messages


def build_prompt(question: str, sources: list[dict]) -> str:
    """Flat text for logs/evals: system + the final user turn (no few-shots)."""
    system, messages = build_messages(question, sources, few_shots=False)
    return f"{system}\n\n{messages[-1]['content']}"
