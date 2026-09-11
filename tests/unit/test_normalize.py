from igihe_assistant.normalization.normalize import (
    content_terms,
    normalize_original,
    normalize_search,
)


def test_search_folds_quotes_and_lowercases_only_search_copy():
    original = normalize_original("APR \u2019itsinze\u201c Rayon")
    assert "\u2019" in original  # faithful copy keeps typography
    search = normalize_search("APR \u2019itsinze\u201c Rayon")
    assert search == search.lower()
    assert "'" in search and '"' in search


def test_nfc_and_whitespace():
    assert normalize_search("e\u0301cole   test") == normalize_search("\u00e9cole test")


def test_content_terms_drops_function_words():
    assert content_terms("Ni iki cyabaye ku mubumbe Mars ejo?") == ["cyabaye", "mubumbe", "mars"]
    assert content_terms("ni ku mu?") == []
