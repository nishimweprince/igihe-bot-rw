from igihe_assistant.retrieval.hybrid import group_near_duplicates, rrf_merge


def test_rrf_prefers_item_ranked_high_in_both_lists():
    merged = dict(rrf_merge([["a", "b", "c"], ["b", "a", "d"]]))
    assert merged["a"] > merged["c"] and merged["b"] > merged["d"]


def test_lexical_mode_keeps_dense_noise_out():
    from igihe_assistant.retrieval.hybrid import retrieve

    class FakeBackend:
        chunks = {
            "lex1": {"wp_id": 1, "title": "Xaverine igare"},
            "a": {"wp_id": 10, "title": "Alpha story"},
            "b": {"wp_id": 11, "title": "Beta story"},
            "noise": {"wp_id": 2, "title": "Unrelated farming"},
            "x": {"wp_id": 20, "title": "Xray story"},
            "y": {"wp_id": 21, "title": "Yankee story"},
        }

        def lexical(self, query, top_n, filters=None):
            return [(n, 30.0 - i) for i, n in enumerate(["lex1", "a", "b", "noise"])]

        def dense(self, query_vec, top_n, filters=None):
            # Placeholder dense vectors rank noise first, miss lex1 entirely.
            return [("noise", 0.99), ("x", 0.5), ("y", 0.4)]

    backend = FakeBackend()
    hybrid = retrieve("xaverine", [1.0], backend)
    assert hybrid[0] == "noise"  # dense noise wins pure RRF here
    tuned = retrieve("xaverine", [1.0], backend, candidates="lexical")
    assert tuned[0] == "lex1"


def test_grouping_keeps_best_per_article_and_story():
    by_id = {
        "c1": {"wp_id": 1, "title": "Amazi i Kigali"},
        "c2": {"wp_id": 1, "title": "Amazi i Kigali"},
        "c3": {"wp_id": 2, "title": "Amazi i Kigali"},
        "c4": {"wp_id": 3, "title": "Ikawa yazamutse"},
    }
    out = group_near_duplicates(["c1", "c2", "c3", "c4"], by_id)
    assert out == ["c1", "c4"]
