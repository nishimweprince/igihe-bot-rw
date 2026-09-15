from igihe_assistant.normalization.langid import is_drifted, kinyarwanda_score

RW = (
    "Umushinga w'amazi wa Kigali uzatwara miliyari 12 z'amafaranga y'u Rwanda "
    "kandi uzarangira mu 2025 [1]."
)
EN = "The Kigali water project will cost 12 billion Rwandan francs and it ends in 2025 [1]."
MIXED = "Umushinga wa Kigali water project uzatwara miliyari 12 [1]."


def test_kinyarwanda_scores_positive_english_negative():
    assert kinyarwanda_score(RW) > 0
    assert kinyarwanda_score(EN) < 0
    assert kinyarwanda_score("") == 0.0


def test_drift_detection():
    assert not is_drifted(RW)
    assert is_drifted(EN)
    assert not is_drifted(MIXED), "a couple of English nouns are normal code-switching"
    assert not is_drifted("Mbabarira, nta bimenyetso bihagije.")
