"""Prompt contract: Kinyarwanda-only, cited, few-shot anchored, history-aware."""

from igihe_assistant.generation.generator import FakeGenerator
from igihe_assistant.generation.validator import CITE
from igihe_assistant.prompting.builder import (
    BROWSE_INSTRUCTION,
    ECHO_PHRASES,
    FALLBACK_SUGGESTIONS,
    FEW_SHOTS,
    NO_CLOSE_MATCH_RW,
    NO_EVIDENCE_RW,
    REFUSAL_SHORT,
    SUGGESTION_MAX_CHARS,
    SYSTEM_RW,
    USER_INSTRUCTION,
    build_messages,
    build_prompt,
    follow_up_suggestions,
    parse_evidence_block,
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


def test_system_demands_kinyarwanda_brief_cited_answers():
    assert "Kinyarwanda" in SYSTEM_RW
    assert "1-3" in SYSTEM_RW
    assert "[1]" in SYSTEM_RW and "[2]" in SYSTEM_RW
    assert "URL" in SYSTEM_RW
    assert SYSTEM_RW.endswith(REFUSAL_SHORT)


def test_no_evidence_message_points_to_origin_and_disclaims_close_matches():
    assert "[IGIHE](https://old.igihe.com)" in NO_EVIDENCE_RW
    assert "egereye" in NO_EVIDENCE_RW.lower()
    assert "—" not in NO_EVIDENCE_RW


def test_no_close_match_message_suggests_another_prompt():
    assert "[IGIHE](https://old.igihe.com)" in NO_CLOSE_MATCH_RW
    assert "Mbwira inkuru ziheruka." in FALLBACK_SUGGESTIONS


def test_follow_up_suggestions_derive_from_headlines():
    closest = [{"title": "Amazi meza ageze i Kigali"}, {"title": "APR itsinze Rayon"}]
    out = follow_up_suggestions(closest)
    assert out[:2] == ["Amazi meza ageze i Kigali", "APR itsinze Rayon"]
    assert len(out) == 3 and out[2] in FALLBACK_SUGGESTIONS


def test_follow_up_suggestions_unescape_entities():
    assert follow_up_suggestions([{"title": "Ikawa &amp; icyayi"}])[0] == "Ikawa & icyayi"


def test_follow_up_suggestions_drop_over_long_titles():
    out = follow_up_suggestions([{"title": "x" * (SUGGESTION_MAX_CHARS + 1)}])
    assert out == FALLBACK_SUGGESTIONS[:3]


def test_follow_up_suggestions_dedupe_case_insensitively():
    out = follow_up_suggestions([{"title": "Amazi"}, {"title": "AMAZI"}])
    assert out[0] == "Amazi" and out[1] != "AMAZI"


def test_follow_up_suggestions_fallbacks_alone_when_nothing_close():
    assert follow_up_suggestions([]) == FALLBACK_SUGGESTIONS[:3]


def test_messages_layout_few_shots_then_question():
    system, messages = build_messages("Amazi?", SOURCES)
    assert system == SYSTEM_RW
    roles = [m["role"] for m in messages]
    assert roles == ["user", "assistant"] * len(FEW_SHOTS) + ["user"]
    last = messages[-1]["content"]
    assert last.startswith("Ibimenyetso:\n[1] Amazi (2024-03-02)")
    assert "Ikibazo: Amazi?" in last
    assert last.rstrip().endswith(USER_INSTRUCTION)
    assert "https://" not in last, "evidence must not tempt the model into pasting URLs"
    assert messages[2 * len(FEW_SHOTS) - 1]["content"] == FEW_SHOTS[-1][1] == REFUSAL_SHORT


def test_history_is_trimmed_and_alternating():
    history = [
        {"role": "assistant", "content": "orphan"},
        {"role": "user", "content": "Q1"},
        {"role": "assistant", "content": "A1 " * 300},
        {"role": "user", "content": "Q2"},
        {"role": "user", "content": "Q3"},  # repeated role: older one dropped
        {"role": "assistant", "content": "A3"},
        {"role": "user", "content": "dangling user turn"},
    ]
    _, messages = build_messages("Q4?", SOURCES, history, history_turns=6, few_shots=False)
    convo = messages[:-1]
    assert [m["role"] for m in convo] == ["user", "assistant", "user", "assistant"]
    assert convo[0]["content"] == "Q1"
    assert len(convo[1]["content"]) == 400
    assert convo[2]["content"] == "Q3"
    assert messages[-1]["content"].startswith("Ibimenyetso:")


def test_browse_mode_uses_round_up_instruction_and_example():
    from igihe_assistant.prompting.builder import FEW_SHOT_BROWSE

    _, messages = build_messages("Mbwira inkuru ziheruka", SOURCES, browse=True)
    assert messages[-1]["content"].rstrip().endswith(BROWSE_INSTRUCTION)
    assert messages[-2]["content"] == FEW_SHOT_BROWSE[1]
    assert messages[-3]["content"].rstrip().endswith(BROWSE_INSTRUCTION)
    assert len(messages) == 3, "browse mode carries the round-up example only"


def test_build_prompt_is_flat_system_plus_user():
    prompt = build_prompt("Amazi?", SOURCES)
    assert prompt.startswith(SYSTEM_RW)
    assert "Ikibazo: Amazi?" in prompt
    assert "Gasabo United" not in prompt, "few-shots are not part of the log copy"


def test_parse_evidence_block_round_trips():
    _, messages = build_messages("Amazi?", SOURCES, few_shots=False)
    parsed = parse_evidence_block(messages[-1]["content"])
    assert [p["n"] for p in parsed] == [1, 2, 3]
    assert parsed[0]["title"] == "Amazi"
    assert parsed[2]["content"] == SOURCES[2]["content"]


def test_echo_phrases_stay_in_sync_with_template():
    system, messages = build_messages("test?", SOURCES, browse=True)
    _, plain = build_messages("test?", SOURCES)
    template = system + "\n".join(m["content"] for m in messages + plain)
    for phrase in ECHO_PHRASES:
        assert phrase in template, f"echo phrase not in any template: {phrase!r}"


def test_fake_generator_is_concise_and_warm():
    system, messages = build_messages("Amazi?", SOURCES)
    text = FakeGenerator().generate(system, messages, 400)
    assert "[1]" in text
    assert len(CITE.findall(text)) <= 2, "fake should stay to two short snippets"
    assert len(text) < 400, "fake should stay concise"
    assert "".join(FakeGenerator().stream(system, messages, 400)) == text
