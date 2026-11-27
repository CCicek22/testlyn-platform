"""Scoring helpers in the eval runner. No database needed."""

from __future__ import annotations

import math

import pytest
from testlyn_api.knowledge.evaluation.dataset import Query, RelevantSpan
from testlyn_api.knowledge.evaluation.runner import (
    gold_matches,
    score_query,
)


def _query(*spans: tuple[str, str]) -> Query:
    return Query(
        id="q1",
        query="What is alpha?",
        kind="keyword",
        relevant=tuple(RelevantSpan(document=d, answer_span=s) for d, s in spans),
    )


def test_same_span_in_another_document_does_not_match() -> None:
    query = _query(("docA", "alpha value is 7"))
    assert gold_matches(query, "docB", "the alpha value is 7 here") == frozenset()
    assert gold_matches(query, "docA", "the alpha value is 7 here") == frozenset({"0"})


def test_one_chunk_covering_two_gold_entries_matches_both() -> None:
    query = _query(("docA", "alpha value"), ("docA", "beta value"))
    matches = gold_matches(query, "docA", "alpha value and beta value together")
    assert matches == frozenset({"0", "1"})


def test_one_chunk_with_two_gold_entries_scores_recall_and_single_gain() -> None:
    query = _query(("docA", "alpha value"), ("docA", "beta value"))
    ranked = [("c1", "docA", "alpha value and beta value", 0)]
    result = score_query(query, ranked, top_k=5)
    assert result.metrics["hit@5"] == 1.0
    assert result.metrics["recall@5"] == 1.0
    assert result.metrics["mrr"] == 1.0
    # One gain for the chunk, ideal DCG assumes two gold ids: 1 / (1 + 1/log2(3)).
    expected = 1.0 / (1.0 + 1.0 / math.log2(3))
    assert result.metrics["ndcg@5"] == pytest.approx(expected)
