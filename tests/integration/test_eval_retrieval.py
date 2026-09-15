from evals.common import ROOT, load_rows, open_store
from evals.run_retrieval import run_rows
from igihe_assistant.config import Settings


def test_mini_dataset_is_fully_recalled_on_fixtures():
    rows = load_rows(ROOT / "evals" / "datasets" / "mini-v1.jsonl")
    report = run_rows(open_store(None), rows, Settings())
    assert report["overall"]["recall@10"] == 1.0
    assert report["overall"]["refusal_rate_unanswerable"] == 1.0
    assert report["overall"]["answer_rate_answerable"] == 1.0
    assert report["latency_ms"]["p95"] < 200
