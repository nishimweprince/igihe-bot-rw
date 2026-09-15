import sqlite3

from igihe_assistant.retrieval.query import analyze, coverage, stem, term_group, to_match


def _fts_ok(match: str) -> bool:
    c = sqlite3.connect(":memory:")
    c.execute("CREATE VIRTUAL TABLE t USING fts5(x, tokenize='trigram')")
    c.execute("INSERT INTO t VALUES ('abanyeshuri ba kaminuza bakina umupira')")
    c.execute("SELECT * FROM t WHERE t MATCH ?", (match,)).fetchall()
    return True


def test_content_terms_drop_stopwords_and_short_tokens():
    q = analyze("Ni izihe nkuru ku mazi i Kigali?")
    assert q.terms == ["mazi", "kigali"]
    assert not q.recency and not q.browse


def test_apostrophe_splits_and_numbers_kept():
    q = analyze("Umusaruro w'ikawa mu 2024 wari ungana iki?")
    assert q.terms == ["umusaruro", "ikawa", "2024"]


def test_match_expressions_are_valid_fts5():
    q = analyze("abanyeshuri ba kaminuza")
    assert q.match_strict == (
        '("abanyeshuri" OR "nyeshuri" OR "students") AND ("kaminuza" OR "university")'
    )
    assert " OR " in q.match_loose and " AND " not in q.match_loose
    assert _fts_ok(q.match_strict) and _fts_ok(q.match_loose)
    assert _fts_ok(to_match([['he said "hi"']], "AND"))


def test_stem_strips_one_class_prefix_when_stem_is_long_enough():
    assert stem("abanyeshuri") == "nyeshuri"
    assert stem("umusaruro") == "saruro"
    assert stem("mazi") is None  # remainder too short
    assert stem("kagame") is None


def test_term_group_adds_translations_both_ways():
    assert "president" in term_group("perezida")
    assert "perezida" in term_group("president")
    assert term_group("2024") == ["2024"]


def test_recency_cues_and_phrase_tokens_removed():
    q = analyze("football results iki cyumweru")
    assert q.recency and q.terms == ["football", "results"]
    assert "umupira" in q.groups[0]
    assert analyze("Perezida Kagame yavuze iki vuba?").terms == ["perezida", "kagame"]


def test_browse_when_only_generic_and_recency_words():
    assert analyze("Mbwira inkuru ziheruka").browse
    assert analyze("Ni izihe nkuru zigezweho mu Rwanda?").browse
    assert not analyze("Ni izihe nkuru zigezweho ku mupira?").browse


def test_coverage_counts_group_alternates():
    groups = [["umupira", "football"], ["kagame"]]
    assert coverage("football match report", groups) == len("umupira") / (7 + 6)
    assert coverage("Kagame yakinnye umupira", groups) == 1.0
    assert coverage("", groups) == 0.0
