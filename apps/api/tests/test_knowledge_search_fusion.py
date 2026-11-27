"""Reciprocal Rank Fusion: pure function, no database."""

from __future__ import annotations

import uuid

import pytest

from testlyn_api.knowledge.search import RRF_K, rrf_fuse

A = uuid.UUID("00000000-0000-4000-8000-00000000000a")
B = uuid.UUID("00000000-0000-4000-8000-00000000000b")
C = uuid.UUID("00000000-0000-4000-8000-00000000000c")
D = uuid.UUID("00000000-0000-4000-8000-00000000000d")


def test_rrf_k_is_sixty() -> None:
    assert RRF_K == 60


def test_single_leg_keeps_order_and_reports_only_that_rank() -> None:
    fused = rrf_fuse([B, A, C], [])

    assert [h.chunk_id for h in fused] == [B, A, C]
    assert [h.vector_rank for h in fused] == [1, 2, 3]
    assert all(h.keyword_rank is None for h in fused)
    assert fused[0].score == pytest.approx(1 / 61)


def test_chunk_in_both_legs_sums_reciprocal_ranks() -> None:
    fused = rrf_fuse([A, B], [B, C])

    by_id = {h.chunk_id: h for h in fused}
    assert by_id[B].score == pytest.approx(1 / 62 + 1 / 61)
    assert by_id[B].vector_rank == 2
    assert by_id[B].keyword_rank == 1
    assert by_id[A].keyword_rank is None
    assert by_id[C].vector_rank is None
    assert fused[0].chunk_id == B


def test_exact_score_for_known_ranks() -> None:
    fused = rrf_fuse([A], [A], k=60)

    assert fused[0].score == pytest.approx(2 / 61)


def test_custom_k_changes_the_score() -> None:
    fused = rrf_fuse([A], [], k=10)

    assert fused[0].score == pytest.approx(1 / 11)


@pytest.mark.parametrize("vector_ids, keyword_ids", [([A], [B]), ([B], [A])])
def test_equal_scores_are_ordered_by_chunk_id(
    vector_ids: list[uuid.UUID], keyword_ids: list[uuid.UUID]
) -> None:
    # A (rank 1 in one leg) and B (rank 1 in the other) tie exactly.
    fused = rrf_fuse(vector_ids, keyword_ids)

    assert fused[0].score == fused[1].score
    assert [h.chunk_id for h in fused] == [A, B]


def test_fusion_output_is_sorted_by_score_then_id() -> None:
    fused = rrf_fuse([D, C, A], [A, B, D])
    keys = [(-h.score, h.chunk_id) for h in fused]

    assert keys == sorted(keys)


def test_duplicate_ids_in_a_leg_count_once_at_first_position() -> None:
    fused = rrf_fuse([A, A, B], [])

    assert [h.chunk_id for h in fused] == [A, B]
    assert fused[0].vector_rank == 1
    assert fused[1].vector_rank == 2


def test_empty_legs_return_nothing() -> None:
    assert rrf_fuse([], []) == []
