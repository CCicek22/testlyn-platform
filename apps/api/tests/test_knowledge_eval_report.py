from __future__ import annotations

from testlyn_api.knowledge.evaluation.report import render_markdown
from testlyn_api.knowledge.evaluation.runner import EvalReport, ModeReport


def _report(top_k: int) -> EvalReport:
    values = {
        f"hit@{top_k}": 1.0,
        f"recall@{top_k}": 0.5,
        "mrr": 0.25,
        f"ndcg@{top_k}": 0.75,
    }
    mode = ModeReport(mode="hybrid", overall=values, by_kind={}, queries=())
    return EvalReport(
        embedder="test",
        documents=12,
        queries=0,
        top_k=top_k,
        modes={"hybrid": mode},
    )


def test_report_names_columns_after_top_k() -> None:
    text = render_markdown(_report(3))
    assert "| hit@3 | recall@3 | MRR | nDCG@3 |" in text
    assert "| hybrid | overall | 0 | 1.000 | 0.500 | 0.250 | 0.750 |" in text
    assert "n/a" not in text
