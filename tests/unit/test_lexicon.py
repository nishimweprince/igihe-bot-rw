from igihe_assistant.normalization.lexicon import EN_KI, KI_EN, translations


def test_reverse_map_is_consistent():
    for ki, ens in KI_EN.items():
        for en in ens:
            for tok in en.split():
                assert ki in EN_KI[tok]


def test_translations_exclude_self_and_dedupe():
    out = translations("umupira")
    assert out == ["football", "soccer"]
    assert "umupira" in translations("football")
    assert translations("kagame") == []


def test_entries_are_lowercase_single_tokens():
    for ki in KI_EN:
        assert ki == ki.lower() and " " not in ki and "'" not in ki
