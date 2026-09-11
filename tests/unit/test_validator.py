from igihe_assistant.generation.validator import validate

SRC = [{"url": "https://igihe.com/a"}]


def test_rejects_unknown_citation():
    ok, reason = validate("Ibyo [5]", SRC)
    assert not ok and reason == "unknown-citation"


def test_rejects_unindexed_url():
    ok, reason = validate("Reba https://evil.example/x [1]", SRC)
    assert not ok and reason == "unindexed-url"


def test_rejects_empty():
    ok, _ = validate("   ", SRC)
    assert not ok


def test_rejects_evidence_echo():
    ok, reason = validate("Ibimenyetso:\n[1] id=5 title=X url=https://igihe.com/a", SRC)
    assert not ok and reason == "evidence-echo"


def test_rejects_system_instruction_echo():
    text = "Subiza mu Kinyarwanda gusa. Koresha GUSA ibimenyetso biri hasi [1]."
    ok, reason = validate(text, SRC)
    assert not ok and reason == "evidence-echo"


def test_allows_ordinary_prose_mentioning_evidence():
    ok, _ = validate("Dushingiye ku bimenyetso byatanzwe, amande azacibwa [1].", SRC)
    assert ok


def test_echo_phrases_stay_in_sync_with_template():
    from igihe_assistant.prompting.builder import ECHO_PHRASES, build_messages

    system, user = build_messages(
        "Ikibazo cy'igerageza?",
        [{"wp_id": 1, "title": "T", "published_at": "2024-01-01", "url": "u", "content": "C"}],
    )
    template = f"{system}\n{user}"
    for phrase in ECHO_PHRASES:
        if phrase.startswith("Ongera usubize"):
            continue  # retry nudge appended at call time, not in template
        assert phrase in template, phrase
        ok, reason = validate(f"Igisubizo: {phrase} ikindi.", SRC)
        assert not ok and reason == "evidence-echo", phrase
