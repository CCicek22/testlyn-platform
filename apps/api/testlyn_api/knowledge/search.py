"""Knowledge search: reciprocal rank fusion, plus the Postgres candidate legs."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

RRF_K = 60


@dataclass(frozen=True)
class FusedHit:
    chunk_id: uuid.UUID
    score: float
    vector_rank: int | None
    keyword_rank: int | None


def rrf_fuse(
    vector_ids: Sequence[uuid.UUID],
    keyword_ids: Sequence[uuid.UUID],
    *,
    k: int = RRF_K,
) -> list[FusedHit]:
    """Fuse two ranked id lists: score = sum over legs of 1 / (k + rank).

    Ranks are 1-based positions in each leg after dropping repeats (the first
    occurrence counts). Output is sorted by score, highest first, then by
    chunk id, so equal scores always come out in the same order.
    """
    ranks: dict[uuid.UUID, list[int | None]] = {}
    for leg_index, leg in enumerate((vector_ids, keyword_ids)):
        seen: set[uuid.UUID] = set()
        position = 0
        for chunk_id in leg:
            if chunk_id in seen:
                continue
            seen.add(chunk_id)
            position += 1
            ranks.setdefault(chunk_id, [None, None])[leg_index] = position

    fused: list[FusedHit] = []
    for chunk_id, (vector_rank, keyword_rank) in ranks.items():
        score = 0.0
        if vector_rank is not None:
            score += 1 / (k + vector_rank)
        if keyword_rank is not None:
            score += 1 / (k + keyword_rank)
        fused.append(
            FusedHit(
                chunk_id=chunk_id,
                score=score,
                vector_rank=vector_rank,
                keyword_rank=keyword_rank,
            )
        )
    fused.sort(key=lambda hit: (-hit.score, hit.chunk_id))
    return fused
