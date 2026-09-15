"""Prompt contract: concise, conversational, citation-demanding, splitter-safe."""

from igihe_assistant.generation.generator import FakeGenerator
from igihe_assistant.generation.validator import CITE
from igihe_assistant.prompting.builder import (
    ECHO_PHRASES,
    FALLBACK_SUGGESTIONS,
    NO_CLOSE_MATCH_RW,
    NO_EVIDENCE_RW,
    SUGGESTION_MAX_CHARS,
    SYSTEM_KINYARWANDA,
    build_messages,
    build_prompt,
    follow_up_suggestions,
)

SOURCES = [
    {
        "n": 1,
        "wp_id": 101,
        "title": "Amazi",
        "published_at": "2024-03-02T08:00:00",
        "url": "https://igihe.com/a",
        "content": "Umujyi wa Kigali watangije umushinga w'amazi meza.",
    },
    {
        "n": 2,
        "wp_id": 109,
        "title": "Icosora",
        "published_at": "2024-03-03T08:00:00",
        "url": "https://igihe.com/b",
        "content": "Imibare y'amazi i Kigali yiyongereye.",
    },
    {
        "n": 3,
        "wp_id": 107,
        "title": "Ikawa",
        "published_at": "2024-09-10T09:00:00",
        "url": "https://igihe.com/c",
        "content": "Umusaruro w'ikawa wazamutse cyane uyu mwaka.",
    },
]


def test_system_demands_brief_conversational_cited_answers():
    assert "1-3" in SYSTEM_KINYARWANDA
    assert "mugenzi wawe" in SYSTEM_KINYARWANDA
    assert "[1]" in SYSTEM_KINYARWANDA and "[2]" in SYSTEM_KINYARWANDA
    assert "Mbabarira, nta bimenyetso bihagije" in SYSTEM_KINYARWANDA


def test_no_evidence_message_points_to_origin_and_disclaims_close_matches():
    assert "—" not in NO_EVIDENCE_RW
    low = NO_EVIDENCE_RW.lower()
    assert "nta bimenyetso" in low
    assert "[IGIHE](https://old.igihe.com)" in NO_EVIDENCE_RW
    assert "nzikwereka" in low
    assert "egereye" in low


def test_no_close_match_message_suggests_another_prompt():
    assert "—" not in NO_CLOSE_MATCH_RW
    assert "nta bimenyetso" in NO_CLOSE_MATCH_RW.lower()
    assert "[IGIHE](https://old.igihe.com)" in NO_CLOSE_MATCH_RW
    # Chips below the refusal carry the invitation now; the prose must not
    # restate a suggestion.
    assert FALLBACK_SUGGESTIONS
    for suggestion in FALLBACK_SUGGESTIONS:
        assert suggestion not in NO_CLOSE_MATCH_RW


def test_follow_up_suggestions_derive_from_headlines():
    closest = [
        {"title": "Amazi meza i Kigali"},
        {"title": "Ikawa yazamutse"},
    ]
    assert follow_up_suggestions(closest) == [
        "Amazi meza i Kigali",
        "Ikawa yazamutse",
        FALLBACK_SUGGESTIONS[0],
    ]


def test_follow_up_suggestions_unescape_entities():
    closest = [{"title": "Ibiciro bya lisansi &#8217; byiyongereye"}]
    assert follow_up_suggestions(closest)[0] == "Ibiciro bya lisansi ’ byiyongereye"


def test_follow_up_suggestions_drop_over_long_titles():
    closest = [{"title": "x" * (SUGGESTION_MAX_CHARS + 1)}]
    assert follow_up_suggestions(closest) == FALLBACK_SUGGESTIONS[:3]


def test_follow_up_suggestions_dedupe_case_insensitively():
    closest = [
        {"title": "Amazi meza"},
        {"title": "  AMAZI  MEZA "},
        {"title": FALLBACK_SUGGESTIONS[0].upper()},
    ]
    out = follow_up_suggestions(closest)
    assert out[0] == "Amazi meza"
    assert len(out) == 3
    assert len({s.casefold() for s in out}) == 3


def test_follow_up_suggestions_fallbacks_alone_when_nothing_close():
    assert follow_up_suggestions([]) == FALLBACK_SUGGESTIONS[:3]
    assert follow_up_suggestions([{"title": ""}, {"title": "   "}]) == FALLBACK_SUGGESTIONS[:3]


def test_splitter_markers_preserved_for_chat_generators():
    # OllamaGenerator/MlxGenerator split the flat prompt on these markers.
    system, user = build_messages("Amazi?", SOURCES)
    assert "Ikibazo: Amazi?" in user
    assert user.rstrip().endswith("Igisubizo:")
    assert "Ibimenyetso:" in user
    assert build_prompt("Amazi?", SOURCES).startswith(system)


def test_echo_phrases_stay_in_sync_with_template():
    retry_nudge = "Ongera usubize, rangiza buri nteruro na [1]."
    template = SYSTEM_KINYARWANDA + build_prompt("test?", SOURCES) + retry_nudge
    for phrase in ECHO_PHRASES:
        assert phrase in template, f"echo phrase not in any template: {phrase!r}"


def test_fake_generator_is_concise_and_warm():
    text = FakeGenerator().generate("prompt", SOURCES, 400)
    assert "[1]" in text
    assert "Dushingiye" not in text
    assert len(CITE.findall(text)) <= 2, "fake should stay to two short snippets"
    assert len(text) < 400, "fake should stay concise"
