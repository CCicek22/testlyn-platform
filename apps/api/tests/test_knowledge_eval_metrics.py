from __future__ import annotations

import math

import pytest
from testlyn_api.knowledge.evaluation.metrics import (
    hit_at_k,
    mrr,
    ndcg_at_k,
    recall_at_k,
)

# ranking: a(miss), b(g1), c(miss), d(g2). gold g1, g2 and g3 (g3 never found).
RANKING = ["a", "b", "c", "d"]
MATCHES = {"b": frozenset({"g1"}), "d": frozenset({"g2"})}
GOLD = frozenset({"g1", "g2", "g3"})


def test_hit_at_k_hand_values() -> None:
    assert hit_at_k(RANKING, MATCHES, GOLD, 1) == 0.0
    assert hit_at_k(RANKING, MATCHES, GOLD, 2) == 1.0


def test_recall_at_k_hand_values() -> None:
    assert recall_at_k(RANKING, MATCHES, GOLD, 1) == 0.0
    assert recall_at_k(RANKING, MATCHES, GOLD, 2) == pytest.approx(1 / 3)
    assert recall_at_k(RANKING, MATCHES, GOLD, 4) == pytest.approx(2 / 3)


def test_mrr_hand_value() -> None:
    assert mrr(RANKING, MATCHES, GOLD) == 0.5


def test_ndcg_at_k_hand_value() -> None:
    # DCG: gains at ranks 2 and 4. IDCG: min(3 gold, k=4) = 3 ideal gains.
    dcg = 1 / math.log2(3) + 1 / math.log2(5)
    idcg = 1 + 1 / math.log2(3) + 1 / math.log2(4)
    assert ndcg_at_k(RANKING, MATCHES, GOLD, 4) == pytest.approx(dcg / idcg)


@pytest.mark.parametrize(
    "fn",
    [
        lambda r, m, g: hit_at_k(r, m, g, 3),
        lambda r, m, g: recall_at_k(r, m, g, 3),
        lambda r, m, g: mrr(r, m, g),
        lambda r, m, g: ndcg_at_k(r, m, g, 3),
    ],
)
def test_no_gold_is_undefined(fn) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError, match="no gold"):
        fn(RANKING, MATCHES, frozenset())


@pytest.mark.parametrize("bad_k", [0, -1])
def test_k_below_one_is_rejected(bad_k: int) -> None:
    with pytest.raises(ValueError, match="k must be"):
        hit_at_k(RANKING, MATCHES, GOLD, bad_k)
    with pytest.raises(ValueError, match="k must be"):
        recall_at_k(RANKING, MATCHES, GOLD, bad_k)
    with pytest.raises(ValueError, match="k must be"):
        ndcg_at_k(RANKING, MATCHES, GOLD, bad_k)


def test_no_relevant_results_scores_zero() -> None:
    ranking = ["a", "b"]
    assert hit_at_k(ranking, {}, GOLD, 2) == 0.0
    assert recall_at_k(ranking, {}, GOLD, 2) == 0.0
    assert mrr(ranking, {}, GOLD) == 0.0
    assert ndcg_at_k(ranking, {}, GOLD, 2) == 0.0


def test_k_larger_than_ranking_uses_whole_ranking() -> None:
    ranking = ["b"]
    matches = {"b": frozenset({"g1"})}
    gold = frozenset({"g1"})
    assert hit_at_k(ranking, matches, gold, 50) == 1.0
    assert recall_at_k(ranking, matches, gold, 50) == 1.0
    assert ndcg_at_k(ranking, matches, gold, 50) == pytest.approx(1.0)


def test_duplicate_results_do_not_take_rank() -> None:
    ranking = ["b", "b", "d"]
    matches = {"b": frozenset({"g1"}), "d": frozenset({"g2"})}
    gold = frozenset({"g1", "g2"})
    assert mrr(ranking, matches, gold) == 1.0
    assert recall_at_k(ranking, matches, gold, 2) == 1.0
    assert ndcg_at_k(ranking, matches, gold, 2) == pytest.approx(1.0)


def test_second_chunk_for_same_gold_gains_nothing() -> None:
    # Overlapping chunks can both contain the answer; only the first earns gain.
    ranking = ["x", "y"]
    matches = {"x": frozenset({"g1"}), "y": frozenset({"g1"})}
    gold = frozenset({"g1"})
    assert ndcg_at_k(ranking, matches, gold, 2) == pytest.approx(1.0)
    assert recall_at_k(ranking, matches, gold, 2) == 1.0


def test_match_outside_gold_is_not_a_hit() -> None:
    # Rank 1 satisfies a gold-less entry only: no metric may credit it.
    ranking = ["x", "b"]
    matches = {"x": frozenset({"other"}), "b": frozenset({"g1"})}
    gold = frozenset({"g1"})
    assert hit_at_k(ranking, matches, gold, 1) == 0.0
    assert recall_at_k(ranking, matches, gold, 1) == 0.0
    assert hit_at_k(ranking, matches, gold, 2) == 1.0
