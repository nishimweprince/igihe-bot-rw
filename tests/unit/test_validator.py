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
    text = "Koresha gusa ibimenyetso (inkuru) wahawe kandi usubize [1]."
    ok, reason = validate(text, SRC)
    assert not ok and reason == "evidence-echo"


def test_allows_ordinary_prose_mentioning_evidence():
    ok, _ = validate("Dushingiye ku bimenyetso byatanzwe, amande azacibwa [1].", SRC)
    assert ok


def test_echo_phrases_stay_in_sync_with_template():
    from igihe_assistant.prompting.builder import ECHO_PHRASES, build_messages

    src = [{"wp_id": 1, "title": "T", "published_at": "2024-01-01", "url": "u", "content": "C"}]
    system, messages = build_messages("Ikibazo cy'igerageza?", src)
    _, browse = build_messages("Ikibazo cy'igerageza?", src, browse=True)
    template = system + "\n".join(m["content"] for m in messages + browse)
    for phrase in ECHO_PHRASES:
        assert phrase in template, phrase
        ok, reason = validate(f"Igisubizo: {phrase} ikindi.", SRC)
        assert not ok and reason == "evidence-echo", phrase


def test_rejects_question_echoed_with_a_citation():
    ok, reason = validate(
        "Ninde watwaye igikombe cy'isi cya 2030 [1].",
        SRC,
        "Ninde watwaye igikombe cy'isi cya 2030?",
    )
    assert not ok and reason == "question-echo"
    ok, _ = validate(
        "Ntawe uratwara igikombe cya 2030 [1].", SRC, "Ninde watwaye igikombe cya 2030?"
    )
    assert ok
