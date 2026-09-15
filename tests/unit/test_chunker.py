from igihe_assistant.chunking.chunker import chunk_article


def test_short_article_is_single_chunk():
    blocks = [("paragraph", "Inama y'abaminisitiri izaterana ku wa gatanu.")]
    chunks = chunk_article(105, "Itangazo", "general", "2024-06-01", blocks)
    assert len(chunks) == 1
    assert chunks[0]["chunk_index"] == 0


def test_long_article_splits_on_sentence_boundaries_and_ids_stable():
    paras = [("paragraph", " ".join(f"Icyo gihe cyaje {i}. " * 40 for i in range(6)))]
    a = chunk_article(999, "Title", "news", "2024-01-01", paras)
    b = chunk_article(999, "Title", "news", "2024-01-01", paras)
    assert len(a) > 1
    assert [c["id"] for c in a] == [c["id"] for c in b]
    for c in a:
        assert c["token_count"] <= 700
