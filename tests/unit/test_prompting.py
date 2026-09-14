"""Prompt contract: concise, conversational, citation-demanding, splitter-safe."""

from igihe_assistant.generation.generator import FakeGenerator
from igihe_assistant.generation.validator import CITE
from igihe_assistant.prompting.builder import (
    ECHO_PHRASES,
    SYSTEM_KINYARWANDA,
    build_messages,
    build_prompt,
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
