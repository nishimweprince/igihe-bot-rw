import json
from pathlib import Path

from igihe_assistant.extraction.parser import extract, rendered_text

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "wp"


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def test_all_fixtures_extract_or_quarantine_with_reason():
    for path in sorted(FIX.glob("*.json")):
        post = json.loads(path.read_text(encoding="utf-8"))
        parsed = extract(rendered_text(post))
        assert parsed["status"] in ("ok", "quarantined")
        if parsed["status"] == "ok":
            assert sum(len(t) for _, t in parsed["blocks"]) >= 20


def test_video_embed_text_preserved_without_iframe():
    parsed = extract(rendered_text(load("102_video.json")))
    assert parsed["status"] == "ok"
    joined = " ".join(t for _, t in parsed["blocks"])
    assert "APR" in joined and "Rayon" in joined


def test_captions_preserved():
    parsed = extract(rendered_text(load("103_photos.json")))
    joined = " ".join(t for _, t in parsed["blocks"])
    assert "Ababyinnyi" in joined


def test_malformed_legacy_html_still_extracts():
    parsed = extract(rendered_text(load("106_malformed.json")))
    assert parsed["status"] == "ok"
